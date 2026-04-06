#!/bin/bash
# Download a session from the Jetson and compose video.
# Usage: ./download_session.sh [session_name] [--archive]
# If no session_name given, downloads the most recent session.
# --archive: use tar.gz archiving instead of direct rsync

set -e

JETSON="jetson@192.168.0.212"
SSH_OPTS="-o PubkeyAuthentication=no"
REMOTE_DIR="/home/jetson/projects/rover/server"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)/sessions"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$LOCAL_DIR"

# Parse args
SESSION=""
USE_ARCHIVE=false
for arg in "$@"; do
    if [ "$arg" = "--archive" ]; then
        USE_ARCHIVE=true
    elif [ -z "$SESSION" ]; then
        SESSION="$arg"
    fi
done

# Resolve session name
if [ -z "$SESSION" ]; then
    SESSION="$(sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
        "ls -1t $REMOTE_DIR/sessions/ | grep -v '\.tar\.gz$' | head -1")"
fi

echo "Session: $SESSION"

if [ "$USE_ARCHIVE" = true ]; then
    echo "==> Archiving session on Jetson..."
    sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
        "cd $REMOTE_DIR && bash archive_session.sh $SESSION"

    ARCHIVE="${SESSION}.tar.gz"
    echo "==> Downloading $ARCHIVE..."
    sshpass -p 3212321 scp $SSH_OPTS "$JETSON:$REMOTE_DIR/sessions/$ARCHIVE" "$LOCAL_DIR/"

    echo "==> Extracting..."
    tar -xzf "$LOCAL_DIR/$ARCHIVE" -C "$LOCAL_DIR"
    rm "$LOCAL_DIR/$ARCHIVE"

    echo "==> Cleaning up archive on Jetson..."
    sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" "rm -f $REMOTE_DIR/sessions/$ARCHIVE"
else
    echo "==> Downloading session (rsync)..."
    sshpass -p 3212321 rsync -a --no-compress \
        -e "ssh $SSH_OPTS" \
        "$JETSON:$REMOTE_DIR/sessions/$SESSION/" "$LOCAL_DIR/$SESSION/"
fi

echo "==> Downloading logs..."
REMOTE_LOG_DIR="/home/jetson/projects/rover/logs"
LOCAL_LOG_DIR="$LOCAL_DIR/$SESSION/logs"
mkdir -p "$LOCAL_LOG_DIR"
sshpass -p 3212321 scp $SSH_OPTS "$JETSON:$REMOTE_LOG_DIR/*.log" "$LOCAL_LOG_DIR/" 2>/dev/null || echo "  (no logs found)"

echo "==> Cleaning up session on Jetson..."
sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" "rm -rf $REMOTE_DIR/sessions/$SESSION"

echo "==> Done: $LOCAL_DIR/$SESSION"
echo "Files: $(find "$LOCAL_DIR/$SESSION" -type f | wc -l)"
echo "Size:  $(du -sh "$LOCAL_DIR/$SESSION" | cut -f1)"

echo "==> Composing video..."
python "$SCRIPT_DIR/compose_video.py" "$LOCAL_DIR/$SESSION"
