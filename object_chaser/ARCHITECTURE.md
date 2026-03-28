# object_chaser Architecture

## Process Map

```
┌──────────────────────────────────────────────────────┐
│              CLIENT (body_follow.py)                  │
│   python3.8 — async aiohttp + chase state machine     │
│   GET /detection  (once per control loop, ~20fps)     │
└──────────────┬───────────────────────────────────────┘
               │                      │ movement commands
               ▼                      ▼
  ┌────────────────────────┐   ┌──────────────────────┐
  │  Detection Server :8090 │   │  Servo + Track :8000  │
  │  FastAPI, python3.8     │   │  FastAPI, python3.8   │
  │  async inference cache  │   │  I2C: servo + tracks  │
  └───┬──────────┬──────────┘   └──────────────────────┘
      │          │          └──────────────┐
      ▼          ▼                         ▼
┌──────────┐  ┌────────┐     ┌──────────────────────┐
│ Camera   │  │  YOLO  │     │  Servo + Track :8000  │
│ :8080    │  │ :8765  │     │  GET /status only     │
│ python3.8│  │python3.6│    └──────────────────────┘
└──────────┘  └────────┘
```

**Client → Servo+Track** directly for all movement commands (unchanged).
**Detection server → Servo+Track** only to read `current_position` (no I2C, in-memory float).

---

## Startup Order

```bash
python3.8 camera_server.py       # 1 — RealSense capture, frame serving
python3.6 yolo_server.py         # 2 — YOLO inference (Jetson GPU via python3.6)
python3.8 servo_api.py           # 3 — I2C servo + track control
python3.8 detection_server.py    # 4 — async inference cache (depends on 1, 2, 3)
python3.8 body_follow.py         # 5 — behavior client
```

Or use the managed script from `object_chaser/`:
```bash
./start.sh [label]   # starts all 5, waits for readiness, activates saving, tails log
./stop.sh            # kills all 5 by PID + by name (catches stale processes)
```

---

## Endpoints & Calls

### Detection Server `:8090`  *(new)*

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| GET | `/detection` | body_follow.py (each loop) | Last cached inference result — instant, no I/O |
| GET | `/status` | monitoring | Loop FPS, result age, detection presence |

Response shape:
```json
{
  "timestamp": 1711615200.123,
  "frame_ts": "20260328_103345_119188",
  "servo_angle": 78.5,
  "detections": [
    {
      "label": "person",
      "confidence": 0.87,
      "bbox": [210, 95, 180, 320],
      "centroid_x_norm": 0.54,
      "distance": 1.42,
      "relative_position_deg": -14.2
    }
  ]
}
```

### Camera Server `:8080`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| GET | `/frame` | detection_server (each loop) | Latest RGB JPEG from RealSense |
| POST | `/distance` | detection_server (per detection) | Depth (meters) at bbox pixel coords |
| GET | `/session` | body_follow.py (startup) | Session paths: rgb/, depth/, yolo/, servo/ dirs |
| GET | `/status` | start.sh readiness probe | Server health, frame count |
| POST | `/start-saving` | start.sh (after YOLO warmup) | Enable RGB frame saving |
| POST | `/depth-saving?enabled=true\|false` | detection_server (each loop) | Enable depth saving only when target detected |

### YOLO Server `:8765`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| POST | `/detect/` | detection_server (each loop) | Send JPEG → receive bounding boxes + labels + confidence |
| GET | `/ready` | start.sh readiness probe | Warmup check (triggers one inference pass) |

### Servo + Track API `:8000`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| GET | `/status` | detection_server (each loop), chase.py | Current head angle (`current_position`), moving flag |
| POST | `/move` | chase.py | Move head servo to absolute angle |
| POST | `/move_normalized` | — | Move head to normalized position [0..1] |
| POST | `/speed` | chase.py | Set servo steps/second |
| POST | `/stop` | chase.py | Stop head servo |
| POST | `/tracks/move` | chase.py | Drive tracks: speed + direction per side |
| POST | `/tracks/rotate` | chase.py | Rotate in place: speed + direction |
| POST | `/tracks/stop` | chase.py | Stop tracks (also fires on 2s safety timeout) |

---

## Data Flows

### Detection server inference loop (~1fps on Jetson, YOLO-limited)

```
loop forever (no sleep):
  1. GET  :8080/frame          → JPEG bytes + X-Timestamp header
  2. POST :8765/detect/        → [{label, confidence, bbox}, ...]
  3. GET  :8000/status         → current_position (in-memory, no I2C)
  4. for each detection above CONFIDENCE_MIN:
       POST :8080/distance     → depth median at shrunk bbox
       compute centroid_x_norm, relative_position_deg
  5. POST :8080/depth-saving   → enabled=true if any detections
  6. write DetectionResult to asyncio cache
```

### Client control loop (~20fps, no longer YOLO-bottlenecked)

```
loop every ~50ms:
  1. GET  :8090/detection      → cached result (microsecond latency)
  2. filter by label + age (DETECTION_MAX_AGE_MS = 500ms)
  3. chase.update(detection, x_normalized)  → state machine tick
     ├── TRACKING:   POST :8000/tracks/move  (forward + steering)
     ├── LOST:       POST :8000/tracks/stop  (decelerate)
     ├── SEARCHING:  POST :8000/move         (head sweep)
     └── ORIENTING:  POST :8000/tracks/rotate (body pivot)
  4. append to detections.jsonl
```

### `relative_position_deg` computation (in detection_server)

```
head_offset_deg   = SERVO_DIR * (servo_angle - SERVO_CENTER)
pixel_offset_deg  = (0.5 - centroid_x_norm) * CAMERA_FOV
relative_position_deg = head_offset_deg + pixel_offset_deg
```

Convention: positive = right of rover forward, negative = left.
`SERVO_DIR` (±1) **must be validated on hardware** before use in control logic — see spec for procedure.

---

## Hardware Behind servo_api

```
I2C bus 1
├── 0x42  Head servo      → /move, /move_normalized, /speed, /stop
├── 0x40  Left track PCA9685  → /tracks/move, /tracks/rotate, /tracks/stop
└── 0x41  Right track PCA9685 → /tracks/move, /tracks/rotate, /tracks/stop
```

Track directions: forward = track0 dir=0 + track1 dir=1.
Safety: all movement commands include a 2s auto-stop timeout refreshed each frame.

---

## Session File Layout

```
sessions/<timestamp>/
├── rgb/        ← JPEG frames (every frame, while saving_active=True)
├── depth/      ← .npy depth arrays (every ~3rd frame, only when target detected)
├── yolo/
│   └── detections.jsonl   ← per-loop detection log written by body_follow.py
└── servo/
    └── state.jsonl        ← servo position log written by servo_api.py
```

Saving is activated by `POST /start-saving` (called by start.sh after YOLO warmup).
Depth saving is toggled per-loop by detection_server based on whether detections are present.

---

## Config Constants (`client/config.py`)

Key constants added with detection_server:

| Constant | Value | Purpose |
|----------|-------|---------|
| `DETECTION_SERVER_URL` | `http://localhost:8090` | Detection server base URL |
| `DETECTION_MAX_AGE_MS` | `500` | Discard cached result older than this; treat as no detection |
| `SERVO_DIR` | `-1` | Sign of servo direction — validate on hardware before using `relative_position_deg` in control logic |
