# Object Chaser

Autonomous object tracking system using 5 processes: camera capture, YOLO detection, track control, a detection cache server, and client behavior logic.

The detection server decouples YOLO inference from the control loop — the client polls a cached result at ~20fps without ever blocking on inference latency (~1fps on Jetson).

## Installation

> **Required before first run:** Follow [`docs/installation.md`](docs/installation.md) to set up YOLO+OpenCV GPU support and the RealSense depth camera on Jetson Nano. These cannot be installed via pip alone — both require source builds for the ARM architecture.

```bash
sudo apt-get install python3-setuptools python3-pip libjpeg-dev zlib1g-dev
```

## Running

### Quick start (recommended)

```bash
cd ~/projects/rover/
./start.sh person      # starts all 5 processes, waits for readiness, tails log
./stop.sh              # kills all 5 cleanly
```

### Manual (5 terminals, in order)

```bash
# Terminal 1: Camera server — RealSense capture + frame serving
cd ~/projects/rover/server/
python3.8 camera_server.py

# Terminal 2: YOLO server — GPU inference (python3.6 required for Jetson GPU)
cd ~/projects/rover/server/
python3.6 yolo_server.py

# Terminal 3: Track API — I2C hardware control (PCA9685)
cd ~/projects/rover/server/
python3.8 servo_api.py

# Terminal 4: Detection server — async inference cache
cd ~/projects/rover/server/
python3.8 detection_server.py

# Terminal 5: Client — behavior logic
cd ~/projects/rover/client/
python3.8 body_follow.py --label person
```

Start in order: camera → yolo → tracks → detection → client.
After YOLO is ready, call `curl -X POST http://localhost:8080/start-saving` to begin saving RGB frames (done automatically by `start.sh`).

### camera_server.py CLI options
- `--session-dir sessions` — base directory for session folders
- `--jpeg-quality 95` — JPEG encoding quality
- `--frame-limit N` — override auto-computed frame limit (default: computed from free disk space)

## Session file layout

```
sessions/<timestamp>/
  rgb/          # JPEG frames (every frame while saving active)
  depth/        # .npy depth arrays (every ~3rd frame, only when target detected)
  yolo/         # detections.jsonl (written by body_follow.py)
  servo/        # state.jsonl (written by servo_api.py)
```

## API Endpoints

### Detection server (:8090)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detection` | GET | Last cached inference result. Returns detections with `label`, `confidence`, `bbox`, `centroid_x_norm`, `distance`, `relative_position_deg` |
| `/status` | GET | `loop_fps`, `last_result_age_ms`, `cache_has_detections` |

### Camera server (:8080)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/frame` | GET | Latest JPEG frame. Headers: `X-Timestamp`, `X-Frame-Number`, `X-Saving-Active` |
| `/distance` | POST | Depth distance for a bbox. Body: `{"bbox": [x,y,w,h], "shrink": 0.2}`. Returns: `{"distance": 1.23}` |
| `/session` | GET | Session metadata: path, yolo_dir, servo_dir, frame_count, saving_active |
| `/status` | GET | Health check: capture_fps, frame_count, saving status |
| `/start-saving` | POST | Enable RGB frame saving (called by start.sh after YOLO warmup) |
| `/depth-saving` | POST | `?enabled=true\|false` — toggle depth saving (called by detection_server) |

### Track API (:8000)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tracks/move` | POST | Move both tracks. Body: `{"left_speed": 0.1, "left_dir": 0, "right_speed": 0.1, "right_dir": 1, "duration": 2}` |
| `/tracks/rotate` | POST | Rotate in place. Body: `{"speed": 0.05, "direction": 1, "duration": 2}` |
| `/tracks/stop` | POST | Stop both tracks |
| `/status` | GET | Current track state |

### YOLO server (:8765)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detect/` | POST | Send JPEG, get bounding boxes. Form field: `file` |
| `/ready` | GET | Readiness probe (triggers warmup inference if needed) |

## Track directions

```
Forward:       track0 dir=0, track1 dir=1
Backward:      track0 dir=1, track1 dir=0
Rotate left:   both dir=1
Rotate right:  both dir=0
```

## Network

```bash
sudo nmcli device wifi connect "YOUR_HOTSPOT_SSID" password "YOUR_PASSWORD"
```
