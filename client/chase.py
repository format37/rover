"""
Chase state machine for rover object tracking.

States:
  TRACKING   — object visible, driving forward with differential steering.
               Speed scales with distance (slow near, fast far).
  LOST       — object just disappeared. Smooth deceleration, wait SEARCH_TIMEOUT.
  SEARCHING  — rotate body 360° in sequence right→left→right, repeating,
               until object is found.
  ORIENTING  — object found off-center during search. Rotate body to face it,
               then verify.

Search sweeps are time-based: each sweep is SEARCH_SWEEP_DEG / ROTATION_DEG_PER_SEC
seconds. ROTATION_DEG_PER_SEC is a hardware calibration constant in config.py.

Forward driving uses differential steering: x_normalized < 0.5 means target is
to the right (camera is mirrored), so left track speeds up.
"""
import requests
import time
import logging
from config import (
    CAMERA_FOV,
    STOP_DISTANCE, BACK_DISTANCE, BACK_SPEED, FAR_DISTANCE,
    SPEED_MAX, SPEED_MIN, STEERING_GAIN, DECEL_STEP,
    ROTATION_SPEED, ROTATION_DEG_PER_SEC,
    SEARCH_TIMEOUT, SEARCH_SWEEP_DEG,
    SAFETY_TIMEOUT,
)

logger = logging.getLogger(__name__)

# States
STATE_TRACKING = "tracking"
STATE_LOST = "lost"
STATE_SEARCHING = "searching"
STATE_ORIENTING = "orienting"
STATE_BACKING = "backing"
STATE_CLIFF = "cliff"

# Search rotation sequence: right(0), left(1), right(0), then repeat
_SEARCH_SEQUENCE = [0, 1, 0]

# Module state
_api_url = ''
_state = STATE_LOST
_current_speed = 0.0
_last_detection_time = None
_search_sweep_index = 0
_search_sweep_end = None    # None = sweep not yet started
_orient_phase = "rotating"  # "rotating" | "verifying"
_orient_pivot_end = None
_tracks_moving = False


def init(api_url='http://localhost:8000'):
    global _api_url, _state, _current_speed, _last_detection_time
    _api_url = api_url
    _state = STATE_LOST
    _current_speed = 0.0
    _last_detection_time = time.monotonic()
    logger.info("Chase initialized")


def shutdown():
    _stop_tracks()


def get_state():
    return _state


def update(detection, x_normalized, min_distance=None, cliff=False):
    """Main tick — called every frame.

    detection: dict with 'bbox', 'confidence', 'relative_position_deg', 'distance',
               'centroid_x_norm' (from detection server) or None
    x_normalized: object centroid 0-1 or None
    min_distance: closest detected object distance (meters) across all detections, or None
    cliff: True if camera server reports an edge/cliff ahead
    Returns dict with 'state', 'action', 'distance'.
    """
    # HIGHEST priority: cliff ahead → stop immediately, stay stopped until clear
    if cliff:
        if _state != STATE_CLIFF:
            _enter_state(STATE_CLIFF)
            _stop_tracks()
        return _result("cliff_stop")

    # Cliff cleared: resume
    if _state == STATE_CLIFF:
        _enter_state(STATE_LOST)

    # Collision override: any detected object closer than BACK_DISTANCE → back up immediately
    if min_distance is not None and min_distance <= BACK_DISTANCE:
        if _state != STATE_BACKING:
            _enter_state(STATE_BACKING)
        return _do_backing(min_distance)

    # Clear of danger: if we were backing, stop and reset to LOST
    if _state == STATE_BACKING:
        _stop_tracks()
        _enter_state(STATE_LOST)

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


def _send_tracks(left_speed, left_dir, right_speed, right_dir):
    global _tracks_moving
    _tracks_moving = True
    logger.info(f"TrackCmd: L={left_speed:.3f} dir={left_dir}  R={right_speed:.3f} dir={right_dir}")
    try:
        requests.post(f"{_api_url}/tracks/move",
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
        requests.post(f"{_api_url}/tracks/rotate",
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
        requests.post(f"{_api_url}/tracks/stop", timeout=0.5)
    except requests.exceptions.RequestException:
        pass


def _result(action, distance=None):
    return {
        'state': _state,
        'action': action,
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

    distance = detection.get('distance')
    if distance is None:
        logger.warning("Depth returned None, stopping tracks")
        _stop_tracks()
        _current_speed = 0.0
        return _result("no_depth")

    if distance <= STOP_DISTANCE:
        logger.info(f"Too close ({distance:.2f}m), stopping")
        _stop_tracks()
        _current_speed = 0.0
        return _result("too_close", distance=distance)

    # Speed based on distance
    t = min(1.0, (distance - STOP_DISTANCE) / (FAR_DISTANCE - STOP_DISTANCE))
    base_speed = SPEED_MIN + t * (SPEED_MAX - SPEED_MIN)
    _current_speed = base_speed

    # Differential steering from x_normalized
    # x_normalized < 0.5 means target is to the right (camera mirrored convention)
    steering = (x_normalized - 0.5) * STEERING_GAIN
    left_speed = max(0.0, min(SPEED_MAX, base_speed * (1 - steering)))
    right_speed = max(0.0, min(SPEED_MAX, base_speed * (1 + steering)))

    logger.info(f"Track: L={left_speed:.3f} R={right_speed:.3f} dist={distance:.2f}m")
    _send_tracks(left_speed, 1, right_speed, 1)  # both dir=1 = forward

    return _result("driving", distance=distance)


def _do_lost(detection, x_normalized):
    global _current_speed

    if detection:
        _enter_state(STATE_TRACKING)
        return _result("reacquired")

    # Decelerate
    if _current_speed > 0:
        _current_speed = max(0.0, _current_speed - DECEL_STEP)
        if _current_speed > 0:
            _send_tracks(_current_speed, 1, _current_speed, 1)
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
    global _search_sweep_index, _search_sweep_end

    if detection:
        _stop_tracks()
        angle_diff = detection.get('relative_position_deg')
        if angle_diff is None:
            angle_diff = (0.5 - x_normalized) * CAMERA_FOV
        _enter_state(STATE_ORIENTING)
        _orient_start(angle_diff)
        return _result("found_in_search")

    # Time-based rotation sweep
    now = time.monotonic()
    if _search_sweep_end is None or now >= _search_sweep_end:
        direction = _SEARCH_SEQUENCE[_search_sweep_index % len(_SEARCH_SEQUENCE)]
        duration = SEARCH_SWEEP_DEG / ROTATION_DEG_PER_SEC
        _send_rotate(ROTATION_SPEED, direction, duration)
        _search_sweep_end = now + duration
        _search_sweep_index += 1
        dir_name = 'right' if direction == 0 else 'left'
        logger.info(f"Search sweep {_search_sweep_index}: {dir_name} {SEARCH_SWEEP_DEG}deg "
                    f"({duration:.1f}s)")

    return _result("searching")


def _do_orienting(detection, x_normalized):
    global _orient_phase, _orient_pivot_end

    if _orient_phase == "rotating":
        if time.monotonic() >= _orient_pivot_end:
            _stop_tracks()
            _orient_phase = "verifying"
        return _result("orient_rotating")

    elif _orient_phase == "verifying":
        if detection:
            _enter_state(STATE_TRACKING)
            return _result("orient_done")
        else:
            _enter_state(STATE_SEARCHING)
            _search_start()
            return _result("orient_not_found")

    return _result("orienting")


def _do_backing(distance):
    logger.info(f"Collision avoidance: {distance:.2f}m <= {BACK_DISTANCE}m, reversing")
    _send_tracks(BACK_SPEED, 0, BACK_SPEED, 0)  # both dir=0 = backward
    return _result("backing", distance=distance)


# --- Helpers ---

def _orient_start(angle_diff):
    """Begin body rotation to center detected object.

    angle_diff: degrees to rotate. Positive = right of center → dir=0.
                Computed from relative_position_deg or x_normalized * FOV.
    """
    global _orient_phase, _orient_pivot_end
    _orient_phase = "rotating"
    duration = abs(angle_diff) / ROTATION_DEG_PER_SEC
    direction = 0 if angle_diff > 0 else 1  # positive = target is right → rotate right
    logger.info(f"Orient: {angle_diff:+.1f}deg → dir={'right' if direction==0 else 'left'}, "
                f"dur={duration:.2f}s")
    _send_rotate(ROTATION_SPEED, direction, duration)
    _orient_pivot_end = time.monotonic() + duration


def _search_start():
    global _search_sweep_index, _search_sweep_end
    _search_sweep_index = 0
    _search_sweep_end = None  # triggers immediate first sweep in _do_searching
    _stop_tracks()
    logger.info("Search: starting right→left→right sweep sequence")
