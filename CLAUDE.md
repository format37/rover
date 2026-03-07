# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Jetson Nano autonomous rover with vision-based object tracking. Uses a RealSense D435 camera (87° FOV), a head servo for camera aiming, and tank tracks for body movement. All hardware is on I2C: servo at 0x42, left track PCA9685 at 0x40, right track at 0x41.

## Architecture

The active system is **object_chaser/** with a 4-process architecture:

```
[Camera Server :8080]    ←  FastAPI, python3.8 (RealSense capture @ 30fps, frame saving, depth queries)
[YOLO Server :8765]      ←  Flask, python3.6 (Jetson GPU via older OpenCV)
[Servo+Track API :8000]  ←  FastAPI, python3.8 (I2C hardware control)
[Client]                 ←  python3.8 (fetches frames from camera server, detection loop, behavior logic)
```

**Server** (`object_chaser/server/`):
- `camera_server.py` — CameraManager: RealSense capture thread (30fps), writer thread (saves RGB JPEGs + depth .npy to session folders), serves latest JPEG via `/frame`, depth distance via `/distance`. Auto-computes frame limit from available disk space.
- `yolo_server.py` — YOLOv5s ONNX detection, receives JPEG frames, returns bounding boxes
- `servo_api.py` — ServoController (smooth threaded movement) + TrackController (PCA9685 tank tracks). All movement has safety auto-stop timeouts.

**Client** (`object_chaser/client/`):
- `client.py` — Head-only tracking (servo follows detected object, owns camera directly via CameraController)
- `body_follow.py` — Full autonomous behavior: fetches frames from camera server, head tracking → body rotation → forward driving with differential steering → depth-based collision avoidance → search mode when target lost. Logs detections to `yolo/detections.jsonl` in the session folder.
- `camera_controls.py` — RealSense async wrapper with optional depth alignment and filtering (used by client.py only)

**Track directions** (from `object_chaser/examples/move.py`):
- Forward: track0 dir=0, track1 dir=1
- Backward: track0 dir=1, track1 dir=0
- Rotate left: both dir=1
- Rotate right: both dir=0

## Running

```bash
# Terminal 1: Camera server (RealSense capture + frame saving)
cd ~/projects/rover/object_chaser/server/
python3.8 camera_server.py

# Terminal 2: YOLO server
cd ~/projects/rover/object_chaser/server/
python3.6 yolo_server.py

# Terminal 3: Servo + Track API
cd ~/projects/rover/object_chaser/server/
python3.8 servo_api.py

# Terminal 4: Client (pick one)
cd ~/projects/rover/object_chaser/client/
python3.8 client.py --label person           # head tracking only (uses own camera)
python3.8 body_follow.py --label person      # full body follow (uses camera server)
```

## Key behavior parameters (body_follow.py)

All tunable constants are at the top of the file. Key ones:
- `FORWARD_SPEED` — base track speed (currently 0.10)
- `STOP_DISTANCE` — collision avoidance threshold in meters (0.8m)
- `BODY_ROTATE_THRESHOLD` / `BODY_ROTATE_DEADZONE` — when body rotation starts/stops (20°/8°)
- `FORWARD_HEAD_THRESHOLD` — max head deviation to allow forward driving (30°)
- `STEERING_FACTOR` — differential steering aggressiveness (0.6)
- `SEARCH_TIMEOUT` — seconds without detection before search sweep (10s)

## Other directories

- `rover.py`, `start.py`, `head.py` — older monolithic approach with MiniGPT-4 LLM agent (uses `settings.json` and `prompt.txt`)
- `langchain/` — experimental LLM integration
- `archive/` — deprecated implementations, useful as hardware reference (e.g., `rsmove.py` for depth-based movement, `move.py` for raw track control)
- `tests/` — audio recording/playback tests

## Development notes

- No test suite or CI — all testing is manual on hardware
- Python version split: YOLO server needs 3.6 for Jetson GPU OpenCV; everything else uses 3.8
- Movement commands use safety timeouts (2s) refreshed each frame — tracks auto-stop if client crashes
- The servo API handles smooth interpolation internally via a threaded movement loop
- Depth frames are aligned to color by camera_server.py (and CameraController), so YOLO bbox coordinates map directly to depth pixels
- Camera server saves sessions to `sessions/<timestamp>/` with `rgb/`, `depth/`, `yolo/` subdirs. Depth is saved every 3rd frame. Frame limit auto-computed from free disk space.
