import requests
import time
import argparse
import asyncio
from camera_controls import CameraController
import cv2
import logging
import aiohttp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

servo_api_url = 'http://localhost:8000'

# Servo center angle - when head faces forward
SERVO_CENTER = 90.0
SERVO_RANGE = 180

# Body rotation thresholds and parameters
BODY_ROTATE_THRESHOLD = 20.0  # Start body rotation when head deviates this many degrees from center
BODY_ROTATE_DEADZONE = 8.0    # Stop body rotation when within this many degrees of center
MIN_TRACK_SPEED = 0.03        # Minimum track speed for rotation
MAX_TRACK_SPEED = 0.08        # Maximum track speed for rotation
BODY_ROTATE_DURATION = 0.3    # Duration of each rotation pulse (seconds)

# Forward movement parameters
FORWARD_HEAD_THRESHOLD = 15.0  # Head must be within this many degrees of center to move forward
FORWARD_SPEED = 0.05           # Track speed when moving forward
FORWARD_DURATION = 0.3         # Duration of each forward pulse (seconds)

# Head tracking parameters
HEAD_OFFSET_THRESHOLD = 10    # Minimum camera offset (degrees) to trigger head movement
SERVO_UPDATE_INTERVAL = 2.0   # Minimum seconds between servo updates

last_servo_update_time = None


def get_servo_status():
    """Get current servo angle and status from API"""
    try:
        response = requests.get(f"{servo_api_url}/status", timeout=0.1)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to get servo status: {e}")
    return None


def update_head(new_goal):
    """Move head servo to normalized position (0-1)"""
    global last_servo_update_time
    if not 0 <= new_goal <= 1:
        logger.warning(f"Goal {new_goal} out of range, clamping")
        new_goal = max(0, min(1, new_goal))

    now = time.monotonic()
    if last_servo_update_time is not None:
        elapsed = now - last_servo_update_time
        if elapsed < SERVO_UPDATE_INTERVAL:
            logger.info(f"Skipping servo update; only {elapsed:.2f}s since last command")
            return

    target_angle = new_goal * SERVO_RANGE
    try:
        response = requests.post(f"{servo_api_url}/move",
                                 json={"angle": target_angle},
                                 timeout=0.1)
        if response.status_code != 200:
            logger.warning(f"Servo API error: {response.status_code}")
        last_servo_update_time = now
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to update servo: {e}")
        last_servo_update_time = now


def rotate_body(servo_angle):
    """Rotate body to bring head back toward center. Returns True if rotating."""
    deviation = servo_angle - SERVO_CENTER  # positive = head looking left, negative = right

    if abs(deviation) < BODY_ROTATE_DEADZONE:
        return False

    # Proportional speed: larger deviation = faster rotation
    speed_factor = min(abs(deviation) / 90.0, 1.0)
    track_speed = MIN_TRACK_SPEED + speed_factor * (MAX_TRACK_SPEED - MIN_TRACK_SPEED)

    # Direction: rotate body toward where the head is looking
    # deviation > 0 means head is looking left -> rotate body left
    # From move.py: direction=1,1 for both tracks = rotate one way; direction=0,0 = rotate other way
    # 'a' (direction=1,1) is labeled "tracks go right" in move.py comments
    # 'd' (direction=0,0) is labeled "tracks go left"
    # If head looks left (deviation>0), we need body to rotate left -> direction=0 for both
    # If head looks right (deviation<0), we need body to rotate right -> direction=1 for both
    if deviation > 0:
        rotate_dir = 1  # rotate body left
    else:
        rotate_dir = 0  # rotate body right

    logger.info(f"Body rotate: deviation={deviation:.1f}, speed={track_speed:.3f}, dir={rotate_dir}")

    try:
        response = requests.post(f"{servo_api_url}/tracks/rotate",
                                 json={"speed": track_speed,
                                        "direction": rotate_dir,
                                        "duration": BODY_ROTATE_DURATION},
                                 timeout=0.5)
        if response.status_code != 200:
            logger.warning(f"Track rotate error: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to rotate body: {e}")
        return False

    return True


def move_forward():
    """Move forward in a short pulse. Returns True if command sent."""
    logger.info(f"Moving forward: speed={FORWARD_SPEED}, duration={FORWARD_DURATION}")
    try:
        # Forward: track0 dir=0, track1 dir=1 (from move.py)
        response = requests.post(f"{servo_api_url}/tracks/move",
                                 json={"left_speed": FORWARD_SPEED,
                                        "left_dir": 0,
                                        "right_speed": FORWARD_SPEED,
                                        "right_dir": 1,
                                        "duration": FORWARD_DURATION},
                                 timeout=0.5)
        if response.status_code != 200:
            logger.warning(f"Forward move error: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to move forward: {e}")
        return False
    return True


def stop_body():
    """Stop all track movement"""
    try:
        requests.post(f"{servo_api_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


async def process_camera_feed(server_url, label='person', output_dir='.', enable_depth=False):
    print(f"Body follow mode: tracking label='{label}' (Ctrl+C to stop)")
    url = f"{server_url}/detect/"
    server_times = []
    start_time = time.time()
    request_count = 0

    async with CameraController(output_dir=output_dir, enable_depth=enable_depth) as camera:
        async with aiohttp.ClientSession() as session:
            try:
                while True:
                    depth_image, color_image = await camera.get_frames()
                    _, img_encoded = cv2.imencode('.jpg', color_image)
                    image_data = img_encoded.tobytes()

                    async with session.post(url, data={'file': image_data}) as response:
                        if response.status == 200:
                            result = await response.json()
                            server_times.append(result['processing_time'])

                            # Filter detections by label
                            label_detections = [d for d in result['detections'] if d['label'] == label]

                            if label_detections:
                                best = max(label_detections, key=lambda d: d['confidence'])
                                x_middle = best['bbox'][0] + best['bbox'][2] / 2
                                x_normalized = x_middle / color_image.shape[1]
                                x_normalized = 1 - x_normalized  # Invert: 0=right, 1=left
                                logger.info(f"Best '{label}': conf={best['confidence']:.2f}, x_norm={x_normalized:.2f}")

                                # --- Step 1: Head tracking ---
                                status = get_servo_status()
                                if status:
                                    current_servo_angle = status.get('current_position', SERVO_CENTER)
                                    servo_status = status.get('status')
                                    logger.info(f"Servo: angle={current_servo_angle}, status={servo_status}")

                                    fov = 87  # Realsense D435 horizontal FOV
                                    camera_offset = (x_normalized - 0.5) * fov

                                    if abs(camera_offset) > HEAD_OFFSET_THRESHOLD:
                                        new_goal_angle = current_servo_angle + camera_offset
                                        new_goal_angle = max(0, min(SERVO_RANGE, new_goal_angle))
                                        new_goal = new_goal_angle / SERVO_RANGE

                                        if servo_status != 'moving':
                                            update_head(new_goal)

                                    # --- Step 2: Body rotation to re-center head ---
                                    head_deviation = abs(current_servo_angle - SERVO_CENTER)
                                    if head_deviation > BODY_ROTATE_THRESHOLD:
                                        rotate_body(current_servo_angle)
                                    # --- Step 3: Move forward when facing the object ---
                                    elif head_deviation < FORWARD_HEAD_THRESHOLD:
                                        move_forward()

                            else:
                                logger.info(f"No '{label}' detected")

                            # Draw annotations
                            annotated_image = color_image.copy()
                            for detection in result['detections']:
                                x, y, w, h = detection['bbox']
                                color = (0, 255, 0) if detection['label'] == label else (128, 128, 128)
                                cv2.rectangle(annotated_image, (x, y), (x + w, y + h), color, 2)
                                det_label = f"{detection['label']} {detection['confidence']:.2f}"
                                cv2.putText(annotated_image, det_label, (x, y - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                        else:
                            print(f"Error: {response.status}, {await response.text()}")

                    request_count += 1

            except KeyboardInterrupt:
                print("\nInterrupted by user.")
                stop_body()

    total_time = time.time() - start_time
    fps = request_count / total_time if total_time > 0 else 0
    return fps, total_time, server_times


async def main():
    parser = argparse.ArgumentParser(description='Body follow - head tracking + body rotation')
    parser.add_argument('--label', type=str, default='person', help='YOLO label to track (default: person)')
    args = parser.parse_args()

    server_url = 'http://localhost:8765'
    output_dir = 'camera_output'
    enable_depth = False

    logger.info("Initializing servo via API")
    try:
        response = requests.post(f"{servo_api_url}/move",
                                 json={"angle": SERVO_CENTER},
                                 timeout=2.0)
        if response.status_code == 200:
            logger.info("Servo initialized to center position")
        else:
            logger.error(f"Failed to initialize servo: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot connect to servo API: {e}")
        logger.error("Make sure servo_api.py is running on localhost:8000")
        return

    # Set servo speed
    try:
        requests.post(f"{servo_api_url}/speed",
                       json={"steps_per_second": 200},
                       timeout=0.5)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error setting servo speed: {e}")

    try:
        logger.info(f"Starting body follow, tracking '{args.label}'")
        fps, total_time, server_times = await process_camera_feed(
            server_url,
            label=args.label,
            output_dir=output_dir,
            enable_depth=enable_depth
        )
        logger.info(f"Total time: {total_time:.2f}s, Average FPS: {fps:.2f}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        stop_body()
        try:
            requests.post(f"{servo_api_url}/stop", timeout=1.0)
            logger.info("Servo stopped")
        except requests.exceptions.RequestException:
            logger.warning("Could not stop servo via API")
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
