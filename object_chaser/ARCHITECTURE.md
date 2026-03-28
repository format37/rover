# object_chaser Architecture

## Process Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (body_follow.py)                  │
│               python3.8 — async aiohttp + chase.py              │
└────────────┬──────────────────────┬────────────────────────┬────┘
             │                      │                        │
             ▼                      ▼                        ▼
   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
   │  Camera Server   │   │   YOLO Server    │   │  Servo + Track API   │
   │  :8080  FastAPI  │   │  :8765  Flask    │   │  :8000  FastAPI      │
   │  python3.8       │   │  python3.6       │   │  python3.8           │
   └──────────────────┘   └──────────────────┘   └──────────────────────┘
           ▲                                               │
           └───────────────────────────────────────────────
                    (servo_api fetches /session on startup)
```

---

## Endpoints & Calls

### Camera Server `:8080`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| GET | `/frame` | client (each loop) | Latest RGB JPEG from RealSense |
| POST | `/distance` | chase.py | Depth (meters) at bbox pixel coords |
| GET | `/session` | client (startup), servo_api (startup) | Session paths: rgb/, depth/, yolo/ dirs |
| GET | `/status` | — | Server health, frame count |
| POST | `/start-saving` | — | Enable RGB frame saving |
| POST | `/depth-saving?enabled=true\|false` | client (each loop) | Enable depth saving only when target detected |

### YOLO Server `:8765`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| POST | `/detect/` | client (each loop) | Send JPEG → receive bounding boxes + labels + confidence |
| GET | `/ready` | — | Readiness probe |

### Servo + Track API `:8000`

| Method | Endpoint | Called by | Purpose |
|--------|----------|-----------|---------|
| GET | `/status` | chase.py | Current head angle, moving flag |
| POST | `/move` | chase.py | Move head servo to absolute angle |
| POST | `/move_normalized` | — | Move head to normalized position [0..1] |
| POST | `/speed` | chase.py | Set servo steps/second |
| POST | `/stop` | chase.py | Stop head servo |
| POST | `/tracks/move` | chase.py | Drive tracks: speed + direction per side |
| POST | `/tracks/rotate` | chase.py | Rotate in place: speed + direction |
| POST | `/tracks/stop` | chase.py | Stop tracks (also fires on 2s safety timeout) |

---

## Per-Loop Data Flow

```
Each ~30fps iteration:

1. GET  :8080/frame          → JPEG bytes
2. POST :8765/detect/        → [{label, confidence, bbox}]
3. POST :8080/depth-saving   → toggle depth write (save only when target seen)

if detection found:
4. GET  :8000/status         → current head angle
5. POST :8080/distance       → depth at bbox center (collision check)
6. POST :8000/move           → head tracking (pan to target)
7. POST :8000/speed          → adjust servo speed
8. POST :8000/tracks/move    → forward drive (if head near center)
   OR
   POST :8000/tracks/rotate  → body rotation (if target far off-axis)
   OR
   POST :8000/tracks/stop    → stop (if within stop distance)

if no detection:
9. POST :8000/tracks/stop
   POST :8000/move           → search sweep
```

---

## Hardware Behind servo_api

```
I2C bus
├── 0x42  Head servo      → /move, /move_normalized, /speed, /stop
├── 0x40  Left track PCA9685  → /tracks/move, /tracks/rotate, /tracks/stop
└── 0x41  Right track PCA9685 → /tracks/move, /tracks/rotate, /tracks/stop
```

Track directions: forward = track0 dir=0 + track1 dir=1
Safety: all movement has 2s auto-stop timeout refreshed each client frame.

---

## Session File Layout

```
sessions/<timestamp>/
├── rgb/        ← JPEG frames (every frame)
├── depth/      ← .npy depth arrays (every 3rd frame, only when target seen)
└── yolo/
    └── detections.jsonl   ← per-frame detection log
```
