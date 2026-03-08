"""
Chase state machine for rover object tracking.

States:
  TRACKING   — object visible, head centered, driving forward with
               differential steering based on object position in frame.
               Speed scales with distance (slow near, fast far).
  LOST       — object just disappeared. Smooth deceleration, wait 2s.
  SEARCHING  — head sweeps 0-180 looking for object.
               After 10 full sweeps, pivot body 180 and retry.
  ORIENTING  — object found off-center. Center head, then time-based
               body pivot to face object.

Body rotation is time-based: ROTATION_DEG_PER_SEC degrees per second
at ROTATION_SPEED.

Forward driving only when head is within +-5 deg of center and object
is farther than STOP_DISTANCE.
"""
import requests
import time
import logging
from config import (
    SERVO_CENTER, SERVO_RANGE, NORMAL_SERVO_SPEED, SEARCH_SERVO_SPEED,
    FORWARD_HEAD_THRESHOLD, STOP_DISTANCE, FAR_DISTANCE,
    SPEED_MAX, SPEED_MIN, STEERING_GAIN, DECEL_STEP,
    ROTATION_SPEED, ROTATION_DEG_PER_SEC,
    SEARCH_TIMEOUT, SEARCH_SWEEPS_BEFORE_TURN,
    DEPTH_BBOX_SHRINK, SAFETY_TIMEOUT,
)

logger = logging.getLogger(__name__)

# States
STATE_TRACKING = "tracking"
STATE_LOST = "lost"
STATE_SEARCHING = "searching"
STATE_ORIENTING = "orienting"

# Module state
_servo_url = ''
_camera_url = ''
_state = STATE_LOST
_current_speed = 0.0
_last_detection_time = None
_detected_angle = SERVO_CENTER
_search_sweeps = 0
_search_target = 0
_search_started = False
_search_direction = 0          # 0 = start right (toward 0), 1 = start left (toward 180)
_orient_phase = "centering"
_orient_pivot_end = None
_tracks_moving = False


def init(servo_url='http://localhost:8000', camera_url='http://localhost:8080'):
    global _servo_url, _camera_url, _state, _current_speed, _last_detection_time
    _servo_url = servo_url
    _camera_url = camera_url
    _state = STATE_LOST
    _current_speed = 0.0
    _last_detection_time = time.monotonic()

    r = requests.post(f"{_servo_url}/move",
                      json={"angle": SERVO_CENTER}, timeout=2.0)
    if r.status_code != 200:
        raise RuntimeError(f"Servo init failed: {r.status_code}")
    logger.info("Servo centered")

    requests.post(f"{_servo_url}/speed",
                  json={"steps_per_second": NORMAL_SERVO_SPEED}, timeout=0.5)


def shutdown():
    _stop_tracks()
    try:
        requests.post(f"{_servo_url}/stop", timeout=1.0)
    except requests.exceptions.RequestException:
        pass


def get_state():
    return _state


def update(detection, x_normalized):
    """Main tick — called every frame.

    detection: dict with 'bbox', 'confidence' or None
    x_normalized: object x position 0-1 (1=right in servo space) or None
    Returns: dict with 'state', 'action', 'servo_angle', 'distance', etc.
    """
    if _state == STATE_TRACKING:
        return _do_tracking(detection, x_normalized)
    elif _state == STATE_LOST:
        return _do_lost(detection, x_normalized)
    elif _state == STATE_SEARCHING:
        return _do_searching(detection, x_normalized)
    elif _state == STATE_ORIENTING:
        return _do_orienting(detection, x_normalized)


def _enter_state(new_state):
    global _state
    old = _state
    _state = new_state
    logger.info(f"State: {old} -> {new_state}")


def _get_servo_status():
    try:
        r = requests.get(f"{_servo_url}/status", timeout=0.3)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Servo status failed: {e}")
    return None


def _get_distance(bbox):
    try:
        r = requests.post(f"{_camera_url}/distance",
                          json={"bbox": bbox, "shrink": DEPTH_BBOX_SHRINK},
                          timeout=0.5)
        if r.status_code == 200:
            return r.json().get('distance')
    except requests.exceptions.RequestException as e:
        logger.error(f"Distance query failed: {e}")
    return None


def _send_servo(angle):
    try:
        requests.post(f"{_servo_url}/move",
                      json={"angle": angle}, timeout=0.1)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Servo move failed: {e}")


def _send_servo_speed(speed):
    try:
        requests.post(f"{_servo_url}/speed",
                      json={"steps_per_second": speed}, timeout=0.1)
    except requests.exceptions.RequestException:
        pass


def _send_tracks(left_speed, left_dir, right_speed, right_dir):
    global _tracks_moving
    _tracks_moving = True
    logger.info(f"TrackCmd: L={left_speed:.3f} dir={left_dir}  R={right_speed:.3f} dir={right_dir}")
    try:
        requests.post(f"{_servo_url}/tracks/move",
                      json={"left_speed": left_speed, "left_dir": left_dir,
                            "right_speed": right_speed, "right_dir": right_dir,
                            "duration": SAFETY_TIMEOUT},
                      timeout=0.5)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Track move failed: {e}")


def _send_rotate(speed, direction, duration):
    global _tracks_moving
    _tracks_moving = True
    logger.info(f"RotateCmd: speed={speed:.3f} dir={direction} dur={duration:.2f}s")
    try:
        requests.post(f"{_servo_url}/tracks/rotate",
                      json={"speed": speed, "direction": direction,
                            "duration": duration},
                      timeout=0.5)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Rotate failed: {e}")


def _stop_tracks():
    global _tracks_moving
    if _tracks_moving:
        logger.info("Tracks: stopped")
    _tracks_moving = False
    try:
        requests.post(f"{_servo_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


def _head_deviation(status):
    """Return degrees head is away from center. None if status unavailable."""
    if not status:
        return None
    angle = status.get('current_position', SERVO_CENTER)
    return angle - SERVO_CENTER


def _result(action, servo_angle=None, distance=None):
    return {
        'state': _state,
        'action': action,
        'servo_angle': servo_angle,
        'distance': distance,
    }


# --- State handlers ---

def _do_tracking(detection, x_normalized):
    global _last_detection_time, _current_speed

    if not detection:
        _enter_state(STATE_LOST)
        _last_detection_time = time.monotonic()
        return _result("lost_object")

    _last_detection_time = time.monotonic()

    # Keep head at center
    status = _get_servo_status()
    servo_angle = SERVO_CENTER
    if status:
        servo_angle = status.get('current_position', SERVO_CENTER)
        if abs(servo_angle - SERVO_CENTER) > 1.0:
            _send_servo(SERVO_CENTER)

    # Safety: if head drifted too far, orient
    if abs(servo_angle - SERVO_CENTER) > FORWARD_HEAD_THRESHOLD:
        _detected_angle_set(servo_angle)
        _enter_state(STATE_ORIENTING)
        _orient_start()
        _stop_tracks()
        return _result("orienting", servo_angle=servo_angle)

    # Distance
    distance = _get_distance(detection['bbox'])
    if distance is None:
        logger.warning("Depth returned None, stopping tracks")
        _stop_tracks()
        _current_speed = 0.0
        return _result("no_depth", servo_angle=servo_angle)

    if distance <= STOP_DISTANCE:
        logger.info(f"Too close ({distance:.2f}m), stopping")
        _stop_tracks()
        _current_speed = 0.0
        return _result("too_close", servo_angle=servo_angle, distance=distance)

    # Speed based on distance
    t = min(1.0, (distance - STOP_DISTANCE) / (FAR_DISTANCE - STOP_DISTANCE))
    base_speed = SPEED_MIN + t * (SPEED_MAX - SPEED_MIN)
    _current_speed = base_speed

    # Differential steering from x_normalized
    steering = (x_normalized - 0.5) * STEERING_GAIN
    left_speed = base_speed * (1 - steering)
    right_speed = base_speed * (1 + steering)
    left_speed = max(0.0, min(SPEED_MAX, left_speed))
    right_speed = max(0.0, min(SPEED_MAX, right_speed))

    logger.info(f"Track: L={left_speed:.3f} R={right_speed:.3f} "
                f"dist={distance:.2f}m")

    # Forward: left_dir=1, right_dir=1
    _send_tracks(left_speed, 1, right_speed, 1)

    return _result("driving", servo_angle=servo_angle, distance=distance)


def _do_lost(detection, x_normalized):
    global _current_speed

    if detection:
        status = _get_servo_status()
        dev = _head_deviation(status)
        if dev is not None and abs(dev) <= FORWARD_HEAD_THRESHOLD:
            _enter_state(STATE_TRACKING)
            return _result("reacquired")
        else:
            angle = status.get('current_position', SERVO_CENTER) if status else SERVO_CENTER
            _detected_angle_set(angle)
            _enter_state(STATE_ORIENTING)
            _orient_start()
            _stop_tracks()
            return _result("orienting_from_lost")

    # Decelerate
    if _current_speed > 0:
        _current_speed = max(0.0, _current_speed - DECEL_STEP)
        if _current_speed > 0:
            _send_tracks(_current_speed, 0, _current_speed, 1)
        else:
            _stop_tracks()
    else:
        _stop_tracks()

    elapsed = time.monotonic() - _last_detection_time
    logger.info(f"Lost ({elapsed:.1f}s), speed={_current_speed:.3f}")

    if elapsed > SEARCH_TIMEOUT:
        _enter_state(STATE_SEARCHING)
        _search_start()
        return _result("search_start")

    return _result("decelerating")


def _do_searching(detection, x_normalized):
    global _search_sweeps, _search_target, _search_started

    if detection:
        # Found object during sweep
        status = _get_servo_status()
        angle = status.get('current_position', SERVO_CENTER) if status else SERVO_CENTER
        # Stop head movement
        try:
            requests.post(f"{_servo_url}/stop", timeout=0.1)
        except requests.exceptions.RequestException:
            pass
        _detected_angle_set(angle)
        _enter_state(STATE_ORIENTING)
        _orient_start()
        return _result("found_in_search", servo_angle=angle)

    # Head sweep logic
    status = _get_servo_status()
    if status and status.get('status') == 'arrived':
        # Arrived at sweep endpoint, flip direction
        _search_sweeps += 1
        _search_target = 180 if _search_target == 0 else 0
        logger.info(f"Search: sweep {_search_sweeps // 2}, heading to {_search_target}deg")

        # After enough full sweeps (2 half-sweeps = 1 full), pivot body
        if _search_sweeps >= SEARCH_SWEEPS_BEFORE_TURN * 2:
            logger.info("Search: pivoting body 180deg")
            duration = 180.0 / ROTATION_DEG_PER_SEC
            _send_rotate(ROTATION_SPEED, 0, duration)
            _search_sweeps = 0
            # Continue searching after pivot (tracks auto-stop via duration)

        _send_servo(_search_target)

    servo_angle = status.get('current_position', SERVO_CENTER) if status else None
    return _result("searching", servo_angle=servo_angle)


def _do_orienting(detection, x_normalized):
    global _orient_phase, _orient_pivot_end

    if _orient_phase == "centering":
        status = _get_servo_status()
        if status and status.get('status') == 'arrived':
            # Head arrived at center, start body pivot
            angle_diff = _detected_angle - SERVO_CENTER
            if abs(angle_diff) < 3.0:
                # Already centered, skip pivot
                _orient_phase = "verifying"
                return _result("orient_verify")

            duration = abs(angle_diff) / ROTATION_DEG_PER_SEC
            # angle > 0 means servo was left of center -> rotate left (dir=1)
            # angle < 0 means servo was right of center -> rotate right (dir=0)
            direction = 1 if angle_diff > 0 else 0
            logger.info(f"Orient: pivoting {angle_diff:+.0f}deg, "
                        f"dur={duration:.2f}s, dir={direction}")
            _send_rotate(ROTATION_SPEED, direction, duration)
            _orient_pivot_end = time.monotonic() + duration
            _orient_phase = "pivoting"
            return _result("orient_pivoting")
        return _result("orient_centering")

    elif _orient_phase == "pivoting":
        if time.monotonic() >= _orient_pivot_end:
            _stop_tracks()
            _orient_phase = "verifying"
            return _result("orient_verify")
        return _result("orient_pivoting")

    elif _orient_phase == "verifying":
        if detection:
            _enter_state(STATE_TRACKING)
            return _result("orient_done")
        else:
            _enter_state(STATE_SEARCHING)
            _search_start()
            return _result("orient_not_found")

    return _result("orienting")


# --- Helpers ---

def _detected_angle_set(angle):
    global _detected_angle
    _detected_angle = angle


def _orient_start():
    global _orient_phase, _orient_pivot_end
    _orient_phase = "centering"
    _orient_pivot_end = None
    _send_servo_speed(NORMAL_SERVO_SPEED)
    _send_servo(SERVO_CENTER)


def _search_start():
    global _search_sweeps, _search_target, _search_started, _search_direction
    _search_sweeps = 0
    # Alternate start direction: 0 = look right first, 1 = look left first
    _search_target = 0 if _search_direction == 0 else 180
    _search_direction = 1 - _search_direction  # swap for next time
    _search_started = True
    _stop_tracks()
    _send_servo_speed(SEARCH_SERVO_SPEED)
    _send_servo(_search_target)
    logger.info(f"Search: starting sweep toward {_search_target}deg")
