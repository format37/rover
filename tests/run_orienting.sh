#!/bin/bash
# Test ORIENTING state: center head then pivot body to face target direction.
# No target needed for the orient sequence itself.
#
# Usage: ./run_orienting.sh [start_angle] [label] [max_duration]
#   e.g.: ./run_orienting.sh 135 person 30
#         ./run_orienting.sh 45    # 45deg right of center

set -e
cd "$(dirname "$0")"

ANGLE="${1:-135}"
LABEL="${2:-person}"
DURATION="${3:-30}"

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

echo "=== TEST: ORIENTING ==="
echo "Start angle: ${ANGLE}deg (center=90), Label: $LABEL, Max: ${DURATION}s"
echo "Press Enter to start..."
read -r

python3.8 test_orienting.py --angle "$ANGLE" --label "$LABEL" --duration "$DURATION"
