#!/bin/bash
# Stop all object chaser processes.

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.pids"

if [ ! -f "$PIDFILE" ]; then
    echo "No pidfile found; killing by name only."
    pkill -f "camera_server\.py|yolo_server\.py|servo_api\.py|detection_server\.py|body_follow\.py" 2>/dev/null || true
    echo "All stopped."
    exit 0
fi

PIDS=$(cat "$PIDFILE")
echo "Stopping processes: $PIDS"

for PID in $PIDS; do
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        echo "  Stopped PID $PID"
    else
        echo "  PID $PID already dead"
    fi
done

# Wait briefly then force-kill any survivors
sleep 2
for PID in $PIDS; do
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null
        echo "  Force-killed PID $PID"
    fi
done

rm -f "$PIDFILE"

# Safety net: catch any processes started outside start.sh
pkill -f "camera_server\.py|yolo_server\.py|servo_api\.py|detection_server\.py|body_follow\.py" 2>/dev/null || true

echo "All stopped."
