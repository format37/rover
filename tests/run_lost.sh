#!/bin/bash
# Test LOST state: deceleration after losing target, transition to SEARCHING.
# Phase 1: drives forward briefly to build speed (needs target visible).
# Phase 2: ignores detections to simulate loss — observe deceleration.
#
# Usage: ./run_lost.sh [label] [prime_seconds] [max_duration]
#   e.g.: ./run_lost.sh person 3 30

set -e
cd "$(dirname "$0")"

LABEL="${1:-person}"
PRIME="${2:-3}"
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

echo "=== TEST: LOST ==="
echo "Label: $LABEL  Prime: ${PRIME}s  Max duration: ${DURATION}s"
echo "Target can be in view during prime phase, then press Enter..."
read -r

python3.8 test_lost.py --label "$LABEL" --duration "$DURATION" --prime "$PRIME"
