# Object Chaser

Autonomous object tracking system using 5 processes: camera capture, YOLO detection, track control, a detection cache server, and client behavior logic.

The detection server decouples YOLO inference from the control loop — the client polls a cached result at ~20fps without ever blocking on inference latency (~1fps on Jetson).

## Installation

> **Required before first run:** Follow [`docs/installation.md`](docs/installation.md) to set up YOLO+OpenCV GPU support, the RealSense depth camera, and Wi-Fi on Jetson Nano. These cannot be installed via pip alone — both require source builds for the ARM architecture.

```bash
cd ~/projects
git clone https://github.com/format37/rover.git
cd rover
sudo apt-get install python3-setuptools python3-pip libjpeg-dev zlib1g-dev
```

## Configuration

### `targets.yaml` — chase targets

Defines which objects the rover tracks, in priority order. When multiple targets are visible, the rover follows the highest-priority group; within a group it picks the highest confidence detection.

```yaml
targets:
  - name: cat
    priority: 0        # 0 = highest priority
    confidence: 0.8    # minimum detection confidence (0.0–1.0)
  - name: person
    priority: 1
    confidence: 0.8
```

### `server/hud_config.yaml` — video HUD overlay

Controls the visual overlay rendered by `compose_video.py` — track speed indicators, depth projection map, 3D mesh style, colors, font, and layout. Edit before composing video to adjust the HUD appearance.

## Running

```bash
cd ~/projects/rover/
./start.sh      # starts all 5 processes, waits for readiness, tails log
./stop.sh       # kills all 5 cleanly
```

## Session file layout

```
sessions/<timestamp>/
  rgb/          # JPEG frames (every frame while saving active)
  depth/        # .npy depth arrays (every ~3rd frame, only when target detected)
  yolo/         # detections.jsonl (written by body_follow.py)
  servo/        # state.jsonl (written by servo_api.py)
```

## Downloading sessions and composing video

Run on the **local machine** after a session on the rover:

```bash
cd ~/projects/rover/server/

# Download the most recent session (archives on Jetson, downloads, extracts, auto-composes video)
bash download_session.sh

# Or download a specific session by name
bash download_session.sh <session_name>
```

`download_session.sh` will:
1. Archive the session on the Jetson
2. Download and extract it to `server/sessions/<session_name>/`
3. Copy runtime logs into `sessions/<session_name>/logs/`
4. Clean up the archive on the Jetson
5. Auto-run `compose_video.py` to render the annotated video with HUD overlay

## Track directions

```
Forward:       track0 dir=0, track1 dir=1
Backward:      track0 dir=1, track1 dir=0
Rotate left:   both dir=1
Rotate right:  both dir=0
```
