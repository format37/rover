#!/bin/bash
# Test raw download speed from Jetson (no archiving, no compression).
# Usage: ./test-download.sh [session_name]

set -e

JETSON="jetson@192.168.0.212"
SSH_OPTS="-o PubkeyAuthentication=no"
REMOTE_DIR="/home/jetson/projects/rover/server"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)/sessions"

mkdir -p "$LOCAL_DIR"

SESSION="${1:-}"

if [ -z "$SESSION" ]; then
    SESSION="$(sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
        "ls -1t $REMOTE_DIR/sessions/ | grep -v '\.tar\.gz$' | head -1")"
fi

echo "Session: $SESSION"
sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
    "echo \"Files: \$(find $REMOTE_DIR/sessions/$SESSION -type f | wc -l)\" && \
     echo \"Size:  \$(du -sh $REMOTE_DIR/sessions/$SESSION | cut -f1)\""
echo ""

echo "Downloading..."
T_START=$(date +%s%N)

sshpass -p 3212321 rsync -a --no-compress \
    -e "ssh $SSH_OPTS" \
    "$JETSON:$REMOTE_DIR/sessions/$SESSION/" "$LOCAL_DIR/$SESSION/"

T_END=$(date +%s%N)
ELAPSED_MS=$(( (T_END - T_START) / 1000000 ))
ELAPSED_S=$(( ELAPSED_MS / 1000 ))

echo ""
echo "Time: ${ELAPSED_S}s (${ELAPSED_MS}ms)"
echo "Saved: $LOCAL_DIR/$SESSION"
