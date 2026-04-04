"""Shared configuration for chase state machine and body_follow."""

CAMERA_FOV = 87  # RGB: 87° × 58°

# Detection
DETECTION_CONFIDENCE_MIN = 0.8  # Ignore detections below this confidence

# Tracking thresholds
STOP_DISTANCE = 0.7            # Stop when closer (meters)
BACK_DISTANCE = 0.5            # Back up when closer than this (meters)
BACK_SPEED = 0.3               # Speed for emergency reverse
FAR_DISTANCE = 3.0             # Full speed when farther (meters)
SPEED_MAX = 0.80               # Max track speed
SPEED_MIN = 0.03               # Min track speed

# Steering
STEERING_GAIN = 1.0            # How aggressively tracks steer from x_normalized offset

# Deceleration
DECEL_STEP = 0.02              # Speed reduction per frame when losing object

# Body rotation (time-based)
ROTATION_SPEED = 0.1          # Track speed during pivot/search
ROTATION_DEG_PER_SEC = 15.0   # Degrees per second at ROTATION_SPEED — calibrate on hardware

# Search
SEARCH_TIMEOUT = 2.0           # Seconds without detection -> start search
SEARCH_SWEEP_DEG = 360         # Degrees per search rotation sweep (full circle each)

# Depth
DEPTH_BBOX_SHRINK = 0.2        # Shrink bbox by 20% per side before sampling depth

# Safety
SAFETY_TIMEOUT = 2.0           # Tracks auto-stop if no new command
TRACK_MAX_DURATION = 30.0      # Max allowed duration for a single track command (seconds)

# URLs
API_URL = 'http://localhost:8000'
CAMERA_SERVER_URL = 'http://localhost:8080'
YOLO_URL = 'http://localhost:8765'
DETECTION_SERVER_URL = 'http://localhost:8090'

# Detection server
DETECTION_MAX_AGE_MS = 1000     # Discard result older than this → treat as no detection
