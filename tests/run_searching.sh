#!/bin/bash
# Test SEARCHING state: head sweeps 0-180 looking for target.
# No target needed — detections are ignored so the search runs fully.
#
# Usage: ./run_searching.sh [duration_seconds]
#   e.g.: ./run_searching.sh 120

set -e
cd "$(dirname "$0")"

DURATION="${1:-120}"

# Check servers
for port in 8080 8765 8000; do
    if ! curl -s -o /dev/null -w '' "http://localhost:$port/" 2>/dev/null; then
        if ! curl -s -o /dev/null -w '' "http://localhost:$port/status" 2>/dev/null; then
            echo "ERROR: Server on port $port not responding. Start all servers first."
            echo "  8080 = camera_server, 8765 = yolo_server, 8000 = servo_api"
            exit 1
        fi
    fi
done

echo "=== TEST: SEARCHING ==="
echo "Duration: ${DURATION}s (head sweeps, body pivot after full sweeps)"
echo "Press Enter to start..."
read -r

python3.8 test_searching.py --duration "$DURATION"
