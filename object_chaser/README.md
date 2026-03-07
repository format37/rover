# Object Chaser

Autonomous object tracking system using 4 processes: camera capture, YOLO detection, servo/track control, and client behavior logic.

## Installation
```
sudo apt-get install python3-setuptools python3-pip libjpeg-dev zlib1g-dev
```

## Running

All 4 processes must run simultaneously. Start them in separate terminals:

### Terminal 1: Camera server
Captures RealSense frames at 30fps, saves RGB + depth to session folders, serves frames to the client.
```
cd ~/projects/rover/object_chaser/server/
python3.8 camera_server.py
```
CLI options:
- `--port 8080` — server port
- `--depth-interval 3` — save depth every Nth frame
- `--session-dir sessions` — base directory for session folders
- `--jpeg-quality 95` — JPEG encoding quality
- `--frame-limit N` — override auto-computed frame limit (default: computed from free disk space)

Session folder structure:
```
sessions/20260307_143021/
  rgb/          # JPEG frames (every frame)
  depth/        # .npy depth arrays (every Nth frame)
  yolo/         # detections.jsonl (written by client)
```

### Terminal 2: YOLO server
```
cd ~/projects/rover/object_chaser/server/
python3.6 yolo_server.py
```
Hardcoded port: 8765. No CLI options.

### Terminal 3: Servo + Track API
```
cd ~/projects/rover/object_chaser/server/
python3.8 servo_api.py
```
Hardcoded port: 8000. No CLI options.

### Terminal 4: Client
```
cd ~/projects/rover/object_chaser/client/
python3.8 body_follow.py --label person
```
CLI options:
- `--label person` — YOLO label to track (default: person)

## API Endpoints

### Camera server (:8080)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/frame` | GET | Latest JPEG frame. Headers: `X-Timestamp`, `X-Frame-Number`, `X-Session-Path`, `X-Saving-Active` |
| `/distance` | POST | Depth distance for a bbox. Body: `{"bbox": [x,y,w,h], "shrink": 0.2}`. Returns: `{"distance": 1.23}` |
| `/session` | GET | Session metadata: path, yolo_dir, frame_count, frame_limit, saving_active, depth_scale |
| `/status` | GET | Health check: capture_fps, frame_count, saving status |

### Servo + Track API (:8000)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Current servo position and status |
| `/move` | POST | Move servo to angle. Body: `{"angle": 90}` |
| `/move_normalized` | POST | Move servo to position 0-1. Body: `{"position": 0.5}` |
| `/speed` | POST | Set servo speed. Body: `{"steps_per_second": 50}` |
| `/stop` | POST | Stop servo movement |
| `/tracks/move` | POST | Move both tracks. Body: `{"left_speed": 0.1, "left_dir": 0, "right_speed": 0.1, "right_dir": 1, "duration": 2}` |
| `/tracks/rotate` | POST | Rotate in place. Body: `{"speed": 0.05, "direction": 1, "duration": 2}` |
| `/tracks/stop` | POST | Stop both tracks |

### YOLO server (:8765)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detect/` | POST | Send JPEG, get bounding boxes. Form field: `file` |
