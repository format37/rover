"""Shared configuration for chase state machine and body_follow."""

# Servo
SERVO_CENTER = 90.0
SERVO_RANGE = 180
NORMAL_SERVO_SPEED = 120
SEARCH_SERVO_SPEED = 15
CAMERA_FOV = 87 # RGB: 87° × 58°
# Depth: 69° × 42°

# Detection
DETECTION_CONFIDENCE_MIN = 0.7 # Ignore detections below this confidence

# Tracking thresholds
FORWARD_HEAD_THRESHOLD = 5.0   # Max head deviation (deg) to allow forward driving
STOP_DISTANCE = 0.7            # Stop when closer (meters)
FAR_DISTANCE = 3.0             # Full speed when farther (meters)
SPEED_MAX = 0.20               # Max track speed
SPEED_MIN = 0.03               # Min track speed

# Steering
STEERING_GAIN = 1.0            # How aggressively tracks steer from x_normalized offset

# Deceleration
DECEL_STEP = 0.02              # Speed reduction per frame when losing object

# Body rotation (time-based)
ROTATION_SPEED = 0.08          # Track speed during pivot
ROTATION_DEG_PER_SEC = 15.0    # Degrees of body rotation per second at ROTATION_SPEED

# Search
SEARCH_TIMEOUT = 2.0           # Seconds without detection -> start search
SEARCH_SWEEPS_BEFORE_TURN = 10 # Full sweeps before 180 deg body turn

# Depth
DEPTH_BBOX_SHRINK = 0.2        # Shrink bbox by 20% per side before sampling depth

# Safety
SAFETY_TIMEOUT = 2.0           # Tracks auto-stop if no new command

# URLs
SERVO_API_URL = 'http://localhost:8000'
CAMERA_SERVER_URL = 'http://localhost:8080'
YOLO_URL = 'http://localhost:8765'
