"""Chasing behavior: head tracking, differential steering, search sweep."""
import requests
import time
import logging

logger = logging.getLogger(__name__)

# --- Servo ---
SERVO_CENTER = 90.0
SERVO_RANGE = 180
NORMAL_SERVO_SPEED = 120
SEARCH_SERVO_SPEED = 15
CAMERA_FOV = 87               # RealSense D435 horizontal FOV

# --- Head tracking ---
HEAD_OFFSET_THRESHOLD = 10    # Min camera offset (degrees) to move head
SERVO_UPDATE_INTERVAL = 2.0   # Min seconds between servo commands

# --- Track movement ---
SPEED_MAX = 0.10               # Max track speed (far)
SPEED_MIN = 0.03               # Min track speed (near stop distance)
STOP_DISTANCE = 0.8            # Stop when closer (meters)
FAR_DISTANCE = 3.0             # Full speed when farther (meters)
STEERING_GAIN = 1.0            # Steering from head deviation (1.0 = pivot at 90°)
SAFETY_TIMEOUT = 2.0           # Auto-stop if no new command

# --- Depth ---
DEPTH_BBOX_SHRINK = 0.2

# --- Search ---
SEARCH_TIMEOUT = 2.0           # Seconds without detection before sweep

# --- State ---
servo_api_url = 'http://localhost:8000'
camera_server_url = 'http://localhost:8080'

_last_servo_update = None
_last_detection = None
_search_active = False
_search_target = 0
_tracks_moving = False


def init(servo_url='http://localhost:8000', camera_url='http://localhost:8080'):
    global servo_api_url, camera_server_url, _last_detection
    servo_api_url = servo_url
    camera_server_url = camera_url
    _last_detection = time.monotonic()

    r = requests.post(f"{servo_api_url}/move",
                      json={"angle": SERVO_CENTER}, timeout=2.0)
    if r.status_code != 200:
        raise RuntimeError(f"Servo init failed: {r.status_code}")
    logger.info("Servo centered")

    requests.post(f"{servo_api_url}/speed",
                  json={"steps_per_second": NORMAL_SERVO_SPEED}, timeout=0.5)


def shutdown():
    stop_tracks()
    try:
        requests.post(f"{servo_api_url}/stop", timeout=1.0)
    except requests.exceptions.RequestException:
        pass


def get_servo_status():
    try:
        r = requests.get(f"{servo_api_url}/status", timeout=0.3)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Servo status failed: {e}")
    return None


def track_head(x_normalized):
    """Move head to center the object in camera view. Returns current servo angle."""
    global _last_servo_update
    status = get_servo_status()
    servo_angle = SERVO_CENTER
    if status:
        servo_angle = status.get('current_position', SERVO_CENTER)
        cam_offset = (x_normalized - 0.5) * CAMERA_FOV
        if abs(cam_offset) > HEAD_OFFSET_THRESHOLD:
            goal = max(0, min(SERVO_RANGE, servo_angle + cam_offset))
            now = time.monotonic()
            can_update = (_last_servo_update is None or
                          now - _last_servo_update >= SERVO_UPDATE_INTERVAL)
            if status.get('status') != 'moving' and can_update:
                try:
                    requests.post(f"{servo_api_url}/move",
                                  json={"angle": goal}, timeout=0.1)
                    _last_servo_update = now
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Servo move failed: {e}")
                    _last_servo_update = now
    return servo_angle


def get_distance(bbox):
    """Query depth distance for a bounding box. Returns meters or None."""
    try:
        r = requests.post(f"{camera_server_url}/distance",
                          json={"bbox": bbox, "shrink": DEPTH_BBOX_SHRINK},
                          timeout=0.5)
        if r.status_code == 200:
            return r.json().get('distance')
    except requests.exceptions.RequestException as e:
        logger.error(f"Distance query failed: {e}")
    return None


def drive(servo_angle, distance):
    """Drive forward with differential steering. Returns action string."""
    global _tracks_moving

    if distance <= STOP_DISTANCE:
        logger.info(f"Too close ({distance:.2f}m), stopping")
        stop_tracks()
        return "too_close"

    t = min(1.0, (distance - STOP_DISTANCE) / (FAR_DISTANCE - STOP_DISTANCE))
    base_speed = SPEED_MIN + t * (SPEED_MAX - SPEED_MIN)

    deviation = servo_angle - SERVO_CENTER
    steering = (deviation / 90.0) * STEERING_GAIN
    left_speed = max(0.0, min(1.0, base_speed * (1 - steering)))
    right_speed = max(0.0, min(1.0, base_speed * (1 + steering)))

    if not _tracks_moving:
        logger.info("Driving forward")
        _tracks_moving = True
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


def stop_tracks():
    global _tracks_moving
    if _tracks_moving:
        logger.info("Tracks: stopped")
    _tracks_moving = False
    try:
        requests.post(f"{servo_api_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


def search_step():
    """Slow continuous head sweep between 0° and 180°."""
    global _search_active, _search_target
    if not _search_active:
        _search_active = True
        _search_target = 0
        logger.info("Search: starting sweep")
        try:
            requests.post(f"{servo_api_url}/speed",
                          json={"steps_per_second": SEARCH_SERVO_SPEED}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
        try:
            requests.post(f"{servo_api_url}/move",
                          json={"angle": _search_target}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
        return

    status = get_servo_status()
    if status and status.get('status') == 'arrived':
        _search_target = 180 if _search_target == 0 else 0
        logger.info(f"Search: sweeping to {_search_target}°")
        try:
            requests.post(f"{servo_api_url}/move",
                          json={"angle": _search_target}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass


def reset_search():
    global _search_active, _search_target, _last_detection
    if _search_active:
        logger.info("Search: object found, resuming tracking")
        try:
            requests.post(f"{servo_api_url}/speed",
                          json={"steps_per_second": NORMAL_SERVO_SPEED}, timeout=0.1)
        except requests.exceptions.RequestException:
            pass
    _search_active = False
    _search_target = 0
    _last_detection = time.monotonic()


def time_since_detection():
    if _last_detection is None:
        return 0.0
    return time.monotonic() - _last_detection
