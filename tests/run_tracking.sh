#!/bin/bash
# Test TRACKING state: drive toward visible target with differential steering.
# A target (person) must be visible in camera view.
#
# Usage: ./run_tracking.sh [label] [duration_seconds]
#   e.g.: ./run_tracking.sh person 30

set -e
cd "$(dirname "$0")"

LABEL="${1:-person}"
DURATION="${2:-30}"

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

echo "=== TEST: TRACKING ==="
echo "Label: $LABEL  Duration: ${DURATION}s"
echo "Place target in front of rover, then press Enter..."
read -r

python3.8 test_tracking.py --label "$LABEL" --duration "$DURATION"
