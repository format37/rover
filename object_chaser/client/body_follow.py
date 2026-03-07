import requests
import time
import argparse
import asyncio
import json
import logging
import aiohttp
import cv2
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

servo_api_url = 'http://localhost:8000'
camera_server_url = 'http://localhost:8080'

# Servo
SERVO_CENTER = 90.0
SERVO_RANGE = 180
NORMAL_SERVO_SPEED = 120
SEARCH_SERVO_SPEED = 15

# Head tracking
HEAD_OFFSET_THRESHOLD = 10    # Min camera offset (degrees) to trigger head movement
SERVO_UPDATE_INTERVAL = 2.0   # Min seconds between servo updates

# Track movement
SPEED_MAX = 0.10               # Max track speed (far from object)
SPEED_MIN = 0.03               # Min track speed (near stop distance)
STOP_DISTANCE = 0.8            # Stop when closer than this (meters)
FAR_DISTANCE = 3.0             # Full speed when farther than this (meters)
STEERING_GAIN = 1.0            # Steering aggressiveness from head deviation
SAFETY_TIMEOUT = 2.0           # Auto-stop tracks if no new command

# Depth
DEPTH_BBOX_SHRINK = 0.2

# Search
SEARCH_TIMEOUT = 2.0           # Seconds without detection before search sweep

# Stale frame detection
STALE_FRAME_SECONDS = 1.0      # Frame is stale if timestamp unchanged this long

# ---- state ----
last_servo_update_time = None
last_detection_time = None
prev_frame_ts = None
prev_frame_ts_time = None
search_active = False
search_target = 0
tracks_moving = False


def get_servo_status():
    try:
        r = requests.get(f"{servo_api_url}/status", timeout=0.1)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Servo status failed: {e}")
    return None


def update_head(goal_angle):
    """Move head servo to angle (0-180). Respects update interval."""
    global last_servo_update_time
    goal_angle = max(0.0, min(float(SERVO_RANGE), goal_angle))
    now = time.monotonic()
    if last_servo_update_time is not None:
        if now - last_servo_update_time < SERVO_UPDATE_INTERVAL:
            return
    try:
        requests.post(f"{servo_api_url}/move",
                      json={"angle": goal_angle}, timeout=0.1)
        last_servo_update_time = now
    except requests.exceptions.RequestException as e:
        logger.warning(f"Servo move failed: {e}")
        last_servo_update_time = now


def stop_tracks():
    global tracks_moving
    if tracks_moving:
        logger.info("Tracks: stopped")
    tracks_moving = False
    try:
        requests.post(f"{servo_api_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


def drive(servo_angle, distance):
    """Drive forward with differential steering. Speed scales with distance.
    Returns action string."""
    global tracks_moving

    if distance is None:
        stop_tracks()
        return "no_depth"

    if distance <= STOP_DISTANCE:
        logger.info(f"Too close ({distance:.2f}m), stopping")
        stop_tracks()
        return "too_close"

    # Speed: ramp from SPEED_MIN to SPEED_MAX based on distance
    t = min(1.0, (distance - STOP_DISTANCE) / (FAR_DISTANCE - STOP_DISTANCE))
    base_speed = SPEED_MIN + t * (SPEED_MAX - SPEED_MIN)

    # Steering from head deviation
    deviation = servo_angle - SERVO_CENTER  # positive = head left
    steering = (deviation / 90.0) * STEERING_GAIN
    left_speed = max(0.0, min(1.0, base_speed * (1 - steering)))
    right_speed = max(0.0, min(1.0, base_speed * (1 + steering)))

    if not tracks_moving:
        logger.info("Driving forward")
        tracks_moving = True
    logger.info(f"Drive: L={left_speed:.3f} R={right_speed:.3f} "
                f"dist={distance:.2f}m head={deviation:+.0f}°")

    try:
        requests.post(f"{servo_api_url}/tracks/move",
                      json={"left_speed": left_speed, "left_dir": 0,
                            "right_speed": right_speed, "right_dir": 1,
                            "duration": SAFETY_TIMEOUT},
                      timeout=0.5)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Drive failed: {e}")

    return "driving"


def search_step():
    """Slow head sweep between 0 and 180. No pauses."""
    global search_active, search_target
    if not search_active:
        search_active = True
        search_target = 0
        logger.info("Search: starting sweep")
        try:
            requests.post(f"{servo_api_url}/speed",
                          json={"steps_per_second": SEARCH_SERVO_SPEED}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
        try:
            requests.post(f"{servo_api_url}/move",
                          json={"angle": search_target}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
        return

    status = get_servo_status()
    if status and status.get('status') == 'arrived':
        search_target = 180 if search_target == 0 else 0
        logger.info(f"Search: sweeping to {search_target}°")
        try:
            requests.post(f"{servo_api_url}/move",
                          json={"angle": search_target}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass


def reset_search():
    global search_active, search_target, last_detection_time
    if search_active:
        logger.info("Search: object found, resuming tracking")
        try:
            requests.post(f"{servo_api_url}/speed",
                          json={"steps_per_second": NORMAL_SERVO_SPEED}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
    search_active = False
    search_target = 0
    last_detection_time = time.monotonic()


def is_frame_stale(frame_ts):
    """Detect stale frames (camera server returning same frame repeatedly)."""
    global prev_frame_ts, prev_frame_ts_time
    now = time.monotonic()
    if frame_ts != prev_frame_ts:
        prev_frame_ts = frame_ts
        prev_frame_ts_time = now
        return False
    if prev_frame_ts_time is not None:
        return (now - prev_frame_ts_time) > STALE_FRAME_SECONDS
    return False


async def process_camera_feed(server_url, label='person'):
    print(f"Body follow: tracking '{label}' (Ctrl+C to stop)")
    yolo_url = f"{server_url}/detect/"
    server_times = []
    start_time = time.time()
    request_count = 0

    global last_detection_time
    last_detection_time = time.monotonic()

    try:
        session_resp = requests.get(f"{camera_server_url}/session", timeout=2.0)
        session_info = session_resp.json()
        yolo_dir = session_info['yolo_dir']
        logger.info(f"Session: {session_info['session_path']}")
    except Exception as e:
        logger.error(f"Cannot connect to camera server: {e}")
        return 0, 0, []

    jsonl_path = f"{yolo_dir}/detections.jsonl"
    jsonl_file = open(jsonl_path, 'a')
    logger.info(f"Logging to {jsonl_path}")

    async with aiohttp.ClientSession() as session:
        try:
            while True:
                # Fetch frame
                async with session.get(f"{camera_server_url}/frame") as frame_resp:
                    if frame_resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await frame_resp.read()
                    frame_timestamp = frame_resp.headers.get('X-Timestamp', '')

                # Skip stale frames
                if is_frame_stale(frame_timestamp):
                    logger.warning("Stale frame, skipping")
                    await asyncio.sleep(0.1)
                    continue

                # YOLO detection
                async with session.post(yolo_url, data={'file': image_data}) as response:
                    if response.status != 200:
                        continue

                    result = await response.json()
                    server_times.append(result['processing_time'])
                    detections = [d for d in result['detections'] if d['label'] == label]

                    action = "no_detection"
                    target_bbox = None
                    target_conf = None
                    x_normalized = None
                    distance = None
                    servo_angle = None

                    if detections:
                        reset_search()
                        best = max(detections, key=lambda d: d['confidence'])
                        target_bbox = best['bbox']
                        target_conf = best['confidence']

                        # Object position in frame
                        img_array = np.frombuffer(image_data, dtype=np.uint8)
                        color_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        img_width = color_image.shape[1]
                        x_middle = best['bbox'][0] + best['bbox'][2] / 2
                        x_normalized = 1 - (x_middle / img_width)
                        logger.info(f"'{label}': conf={best['confidence']:.2f}, "
                                    f"x={x_normalized:.2f}")

                        # Head tracking
                        status = get_servo_status()
                        servo_angle = SERVO_CENTER
                        if status:
                            servo_angle = status.get('current_position', SERVO_CENTER)
                            servo_status = status.get('status')

                            fov = 87
                            camera_offset = (x_normalized - 0.5) * fov
                            if abs(camera_offset) > HEAD_OFFSET_THRESHOLD:
                                goal = servo_angle + camera_offset
                                goal = max(0, min(SERVO_RANGE, goal))
                                if servo_status != 'moving':
                                    update_head(goal)

                        # Distance
                        try:
                            dist_resp = requests.post(
                                f"{camera_server_url}/distance",
                                json={"bbox": best['bbox'],
                                      "shrink": DEPTH_BBOX_SHRINK},
                                timeout=0.5)
                            if dist_resp.status_code == 200:
                                distance = dist_resp.json().get('distance')
                        except requests.exceptions.RequestException:
                            pass

                        if distance is not None:
                            logger.info(f"Distance: {distance:.2f}m")

                        # Drive with steering
                        action = drive(servo_angle, distance)

                    else:
                        # No detection
                        stop_tracks()
                        now = time.monotonic()
                        if last_detection_time is None:
                            last_detection_time = now
                        elapsed = now - last_detection_time
                        if elapsed > SEARCH_TIMEOUT:
                            search_step()
                            action = "searching"
                        else:
                            logger.info(f"No '{label}' ({elapsed:.1f}s)")

                    # Log to JSONL
                    log_entry = {
                        "timestamp": frame_timestamp,
                        "detections": result['detections'],
                        "target_label": label,
                        "target_bbox": target_bbox,
                        "target_confidence": target_conf,
                        "x_normalized": x_normalized,
                        "distance": distance,
                        "servo_angle": servo_angle,
                        "action": action,
                    }
                    jsonl_file.write(json.dumps(log_entry) + "\n")
                    jsonl_file.flush()

                request_count += 1

        except KeyboardInterrupt:
            print("\nStopped.")
            stop_tracks()
        finally:
            jsonl_file.close()

    total_time = time.time() - start_time
    fps = request_count / total_time if total_time > 0 else 0
    return fps, total_time, server_times


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='person')
    args = parser.parse_args()

    logger.info("Initializing servo")
    try:
        r = requests.post(f"{servo_api_url}/move",
                          json={"angle": SERVO_CENTER}, timeout=2.0)
        if r.status_code == 200:
            logger.info("Servo centered")
        else:
            logger.error(f"Servo init failed: {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot connect to servo API: {e}")
        return

    try:
        requests.post(f"{servo_api_url}/speed",
                      json={"steps_per_second": NORMAL_SERVO_SPEED}, timeout=0.5)
    except requests.exceptions.RequestException:
        pass

    try:
        logger.info(f"Tracking '{args.label}'")
        await process_camera_feed('http://localhost:8765', label=args.label)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        stop_tracks()
        try:
            requests.post(f"{servo_api_url}/stop", timeout=1.0)
        except requests.exceptions.RequestException:
            pass
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
