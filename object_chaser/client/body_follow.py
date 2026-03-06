import requests
import time
import argparse
import asyncio
from camera_controls import CameraController
import cv2
import logging
import aiohttp
import numpy as np

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
FORWARD_HEAD_THRESHOLD = 30.0  # Head must be within this many degrees of center to move forward
FORWARD_SPEED = 0.05           # Base track speed when moving forward
FORWARD_SAFETY_TIMEOUT = 2.0   # Auto-stop if no new command within this time (safety)
STEERING_FACTOR = 0.6          # How much to steer based on object offset (0=none, 1=full)

# Depth / collision avoidance parameters
STOP_DISTANCE = 0.8            # Stop moving forward when object is closer than this (meters)
DEPTH_BBOX_SHRINK = 0.2        # Shrink bbox by this fraction on each side to avoid edge noise

# Head tracking parameters
HEAD_OFFSET_THRESHOLD = 10    # Minimum camera offset (degrees) to trigger head movement
SERVO_UPDATE_INTERVAL = 2.0   # Minimum seconds between servo updates

# Search mode parameters
SEARCH_TIMEOUT = 10.0          # Start searching after this many seconds without detection
SEARCH_WAIT_DURATION = 10.0    # Pause at center after full sweep before repeating
# Sweep: center → left in 45° steps → right in 45° steps → back to center
SEARCH_ANGLES = [90, 45, 0, 135, 180, 135, 90, 45, 0, 45, 90]

last_servo_update_time = None
last_detection_time = None
is_driving = False
search_phase = -1              # -1 = not searching, 0..N = index in SEARCH_ANGLES, len = waiting
search_phase_start_time = None
search_command_sent = False


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


def estimate_distance(depth_image, depth_scale, bbox):
    """Estimate distance to object using depth data within its bounding box.
    Returns distance in meters, or None if depth data is unavailable."""
    if depth_image is None:
        return None

    x, y, w, h = bbox
    img_h, img_w = depth_image.shape[:2]

    # Shrink bbox inward to avoid noisy edges
    margin_x = int(w * DEPTH_BBOX_SHRINK)
    margin_y = int(h * DEPTH_BBOX_SHRINK)
    x1 = max(0, x + margin_x)
    y1 = max(0, y + margin_y)
    x2 = min(img_w, x + w - margin_x)
    y2 = min(img_h, y + h - margin_y)

    if x2 <= x1 or y2 <= y1:
        return None

    region = depth_image[y1:y2, x1:x2]
    # Filter out zero (invalid) depth values
    valid = region[region > 0]
    if len(valid) == 0:
        return None

    # Median is robust against outliers
    distance = float(np.median(valid)) * depth_scale
    return distance


def drive_toward(x_normalized):
    """Drive forward with differential steering based on object position.
    x_normalized: 0=right, 1=left (inverted camera coords).
    Refreshes safety timeout each call so tracks run continuously."""
    global is_driving
    # Steering: offset from center, positive = object is left
    offset = x_normalized - 0.5  # range -0.5 to 0.5
    steering = offset * STEERING_FACTOR

    # Differential speed: slow the inner track to steer toward the object
    # Object left (offset>0): slow left track → turn left
    # Object right (offset<0): slow right track → turn right
    left_speed = FORWARD_SPEED * (1 - steering)
    right_speed = FORWARD_SPEED * (1 + steering)

    # Clamp speeds to valid range
    left_speed = max(0.01, min(1.0, left_speed))
    right_speed = max(0.01, min(1.0, right_speed))

    if not is_driving:
        logger.info(f"Driving: starting continuous forward movement")
        is_driving = True
    logger.info(f"Driving: L={left_speed:.3f} R={right_speed:.3f} (offset={offset:+.2f})")

    try:
        # Forward: track0 dir=0, track1 dir=1 (from move.py)
        # Safety timeout auto-stops if client crashes / stops sending
        response = requests.post(f"{servo_api_url}/tracks/move",
                                 json={"left_speed": left_speed,
                                        "left_dir": 0,
                                        "right_speed": right_speed,
                                        "right_dir": 1,
                                        "duration": FORWARD_SAFETY_TIMEOUT},
                                 timeout=0.5)
        if response.status_code != 200:
            logger.warning(f"Drive error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to drive: {e}")


def search_step():
    """Advance the search state machine. At each angle: move, wait for arrival, dwell for YOLO."""
    global search_phase, search_phase_start_time, search_command_sent

    now = time.monotonic()

    # First entry into search mode
    if search_phase == -1:
        search_phase = 0
        search_phase_start_time = now
        search_command_sent = False
        logger.info("Search mode: starting systematic scan")

    # Sweep through angles
    if search_phase < len(SEARCH_ANGLES):
        # Send move command once per phase
        if not search_command_sent:
            angle = SEARCH_ANGLES[search_phase]
            logger.info(f"Search mode: looking at {angle} degrees (step {search_phase + 1}/{len(SEARCH_ANGLES)})")
            try:
                requests.post(f"{servo_api_url}/move",
                              json={"angle": angle}, timeout=0.1)
            except requests.exceptions.RequestException:
                pass
            search_command_sent = True
            search_phase_start_time = now
            return

        # Wait for servo to arrive, then dwell 1s for YOLO to process
        status = get_servo_status()
        arrived = status and status.get('status') == 'arrived'
        elapsed = now - search_phase_start_time
        if arrived and elapsed > 1.0:
            # No detection at this angle, advance to next
            search_phase += 1
            search_command_sent = False
        return

    # All angles exhausted — wait at center before repeating
    elapsed = now - search_phase_start_time
    if elapsed < SEARCH_WAIT_DURATION:
        remaining = SEARCH_WAIT_DURATION - elapsed
        if int(elapsed) != int(elapsed - 1):
            logger.info(f"Search mode: no target found, waiting ({remaining:.0f}s before next sweep)")
        return

    # Restart sweep
    logger.info("Search mode: restarting sweep")
    search_phase = 0
    search_phase_start_time = now
    search_command_sent = False


def reset_search():
    """Reset search state when object is found."""
    global search_phase, search_phase_start_time, search_command_sent, last_detection_time
    if search_phase != -1:
        logger.info("Search mode: object found, resuming tracking")
    search_phase = -1
    search_phase_start_time = None
    search_command_sent = False
    last_detection_time = time.monotonic()


def stop_body():
    """Stop all track movement"""
    global is_driving
    if is_driving:
        logger.info("Driving: stopped")
    is_driving = False
    try:
        requests.post(f"{servo_api_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


async def process_camera_feed(server_url, label='person', output_dir='.'):
    print(f"Body follow mode: tracking label='{label}', depth enabled (Ctrl+C to stop)")
    url = f"{server_url}/detect/"
    server_times = []
    start_time = time.time()
    request_count = 0

    global last_detection_time
    last_detection_time = time.monotonic()

    async with CameraController(output_dir=output_dir, enable_depth=True) as camera:
        depth_scale = camera.depth_scale
        logger.info(f"Depth scale: {depth_scale}")
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
                                reset_search()
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

                                    # --- Step 2 & 3: Body rotation + forward movement ---
                                    head_deviation = abs(current_servo_angle - SERVO_CENTER)

                                    # Rotate body to re-center head when needed
                                    if head_deviation > BODY_ROTATE_DEADZONE:
                                        rotate_body(current_servo_angle)

                                    # Move forward unless severely off-center
                                    if head_deviation < FORWARD_HEAD_THRESHOLD:
                                        distance = estimate_distance(depth_image, depth_scale, best['bbox'])
                                        if distance is not None:
                                            logger.info(f"Distance to '{label}': {distance:.2f}m")
                                            if distance > STOP_DISTANCE:
                                                drive_toward(x_normalized)
                                            else:
                                                logger.info(f"Too close ({distance:.2f}m < {STOP_DISTANCE}m), stopping")
                                                stop_body()
                                        else:
                                            logger.warning("No valid depth data, skipping forward movement")
                                    else:
                                        # Head too far off center — stop driving, rotate only
                                        if is_driving:
                                            stop_body()

                            else:
                                # No detection — stop driving immediately
                                if is_driving:
                                    stop_body()
                                # Check if we should enter search mode
                                now = time.monotonic()
                                if last_detection_time is None:
                                    last_detection_time = now
                                no_detect_duration = now - last_detection_time
                                if no_detect_duration > SEARCH_TIMEOUT:
                                    search_step()
                                else:
                                    logger.info(f"No '{label}' detected ({no_detect_duration:.1f}s)")

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
            output_dir=output_dir
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
