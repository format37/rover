#!/bin/bash
# Start all 4 processes for the object chaser.
# Usage: ./start.sh [label]   (default: person)

set -e

LABEL="${1:-person}"
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

echo "Starting object chaser (label=$LABEL)..."

# 1. YOLO server
echo "[1/4] Starting YOLO server..."
cd "$SERVER_DIR"
python3.6 yolo_server.py > "$LOG_DIR/yolo.log" 2>&1 &
YOLO_PID=$!
echo "  PID=$YOLO_PID"

# 2. Servo + Track API
echo "[2/4] Starting servo API..."
python3.8 servo_api.py > "$LOG_DIR/servo.log" 2>&1 &
SERVO_PID=$!
echo "  PID=$SERVO_PID"

# 3. Camera server
echo "[3/4] Starting camera server..."
python3.8 camera_server.py > "$LOG_DIR/camera.log" 2>&1 &
CAMERA_PID=$!
echo "  PID=$CAMERA_PID"

# Save PIDs (body_follow added after it starts)
echo "$YOLO_PID $SERVO_PID $CAMERA_PID" > "$PIDFILE"

# Wait for YOLO to be ready (model load + warmup inference)
echo "Waiting for YOLO warmup..."
for i in $(seq 1 120); do
    if ! kill -0 "$YOLO_PID" 2>/dev/null; then
        echo "YOLO server died. Check $LOG_DIR/yolo.log"
        cat "$LOG_DIR/yolo.log" | tail -5
        rm -f "$PIDFILE"
        exit 1
    fi
    READY=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/ready 2>/dev/null || true)
    if [ "$READY" = "200" ]; then
        echo "YOLO ready."
        break
    fi
    sleep 1
done
if [ "$READY" != "200" ]; then
    echo "YOLO server did not become ready in 120s. Check $LOG_DIR/yolo.log"
    rm -f "$PIDFILE"
    exit 1
fi

# Wait for camera server to be up
echo "Waiting for camera server..."
for i in $(seq 1 30); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/status 2>/dev/null || true)
    if [ "$STATUS" = "200" ]; then
        echo "Camera server ready."
        break
    fi
    sleep 1
done

# Activate saving now that YOLO is warm
echo "Activating frame saving..."
curl -s -X POST http://localhost:8080/start-saving > /dev/null

# 4. Body follow client
echo "[4/4] Starting body follow (label=$LABEL)..."
cd "$CLIENT_DIR"
python3.8 body_follow.py --label "$LABEL" > "$LOG_DIR/body_follow.log" 2>&1 &
BODY_PID=$!
echo "  PID=$BODY_PID"

# Update pidfile with body follow PID
echo "$YOLO_PID $SERVO_PID $CAMERA_PID $BODY_PID" > "$PIDFILE"

echo ""
echo "All processes started. Tailing body_follow log (Ctrl+C to stop monitoring)..."
echo "Run ./stop.sh to stop all processes."
echo "---"
tail -f "$LOG_DIR/body_follow.log"
