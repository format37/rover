#!/bin/bash
# Start all 5 processes for the object chaser.
# Targets are configured in targets.yaml (repo root).
# Usage: ./start.sh

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$DIR/server"
CLIENT_DIR="$DIR/client"
LOG_DIR="$DIR/logs"
PIDFILE="$DIR/.pids"

mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PIDFILE" ]; then
    echo "Already running (pidfile exists). Run ./stop.sh first."
    exit 1
fi

cleanup() {
    echo "Startup failed, cleaning up..."
    [ -f "$PIDFILE" ] && bash "$DIR/stop.sh"
    rm -f "$PIDFILE"
    exit 1
}

wait_for_http() {
    local name="$1" url="$2" pid="$3" timeout="$4" log="$5"
    echo "Waiting for $name..."
    for i in $(seq 1 "$timeout"); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "$name died. Log tail:"
            tail -10 "$log"
            cleanup
        fi
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)
        if [ "$STATUS" = "200" ]; then
            echo "$name ready."
            return 0
        fi
        sleep 1
    done
    echo "$name did not become ready in ${timeout}s. Log tail:"
    tail -10 "$log"
    cleanup
}

export PYTHONUNBUFFERED=1

echo "Starting object chaser (targets from targets.yaml)..."

# 1. YOLO server
echo "[1/5] Starting YOLO server..."
cd "$SERVER_DIR"
python3.6 yolo_server.py > "$LOG_DIR/yolo.log" 2>&1 &
YOLO_PID=$!
echo "  PID=$YOLO_PID"

# 2. Servo + Track API
echo "[2/5] Starting servo API..."
python3.8 servo_api.py > "$LOG_DIR/servo.log" 2>&1 &
SERVO_PID=$!
echo "  PID=$SERVO_PID"

# 3. Camera server
echo "[3/5] Starting camera server..."
python3.8 camera_server.py > "$LOG_DIR/camera.log" 2>&1 &
CAMERA_PID=$!
echo "  PID=$CAMERA_PID"

# Save PIDs
echo "$YOLO_PID $SERVO_PID $CAMERA_PID" > "$PIDFILE"

# Wait for all three servers
wait_for_http "Servo API"     "http://localhost:8000/status" "$SERVO_PID"  60  "$LOG_DIR/servo.log"
wait_for_http "Camera server" "http://localhost:8080/status" "$CAMERA_PID" 30  "$LOG_DIR/camera.log"
wait_for_http "YOLO (warmup)" "http://localhost:8765/ready"  "$YOLO_PID"   120 "$LOG_DIR/yolo.log"

# 4. Detection server (depends on camera, YOLO, servo all being ready)
echo "[4/5] Starting detection server..."
cd "$SERVER_DIR"
python3.8 detection_server.py > "$LOG_DIR/detection.log" 2>&1 &
DETECTION_PID=$!
echo "  PID=$DETECTION_PID"
echo "$YOLO_PID $SERVO_PID $CAMERA_PID $DETECTION_PID" > "$PIDFILE"
wait_for_http "Detection server" "http://localhost:8090/detection" "$DETECTION_PID" 30 "$LOG_DIR/detection.log"

# 5. Body follow client
echo "[5/5] Starting body follow..."
cd "$CLIENT_DIR"
python3.8 body_follow.py > "$LOG_DIR/body_follow.log" 2>&1 &
BODY_PID=$!
echo "  PID=$BODY_PID"

# Update pidfile
echo "$YOLO_PID $SERVO_PID $CAMERA_PID $DETECTION_PID $BODY_PID" > "$PIDFILE"

# Activate frame saving now that all processes are ready
echo "Activating frame saving..."
curl -s -X POST http://localhost:8080/start-saving > /dev/null

echo ""
echo "All processes started. Tailing body_follow log (Ctrl+C to stop monitoring)..."
echo "Run ./stop.sh to stop all processes."
echo "---"
tail -f "$LOG_DIR/body_follow.log"
