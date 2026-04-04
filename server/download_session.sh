#!/bin/bash
# Run on local machine to archive + download a session from the Jetson.
# Usage: ./download_session.sh [session_name]
# If no session_name given, downloads the most recent session.

set -e

JETSON="jetson@192.168.0.212"
SSH_OPTS="-o PubkeyAuthentication=no"
REMOTE_DIR="/home/jetson/projects/rover/server"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)/sessions"

mkdir -p "$LOCAL_DIR"

SESSION="${1:-}"

echo "==> Archiving session on Jetson..."
sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
    "cd $REMOTE_DIR && bash archive_session.sh $SESSION"

# Get the actual session name (most recent if not specified)
if [ -z "$SESSION" ]; then
    SESSION="$(sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
        "ls -1t $REMOTE_DIR/sessions/ | grep -v '\.tar\.gz$' | head -1")"
fi

ARCHIVE="${SESSION}.tar.gz"
echo "==> Downloading $ARCHIVE..."
sshpass -p 3212321 scp $SSH_OPTS "$JETSON:$REMOTE_DIR/sessions/$ARCHIVE" "$LOCAL_DIR/"

echo "==> Extracting..."
tar -xzf "$LOCAL_DIR/$ARCHIVE" -C "$LOCAL_DIR"
rm "$LOCAL_DIR/$ARCHIVE"

echo "==> Downloading logs..."
REMOTE_LOG_DIR="/home/jetson/projects/rover/logs"
LOCAL_LOG_DIR="$LOCAL_DIR/$SESSION/logs"
mkdir -p "$LOCAL_LOG_DIR"
sshpass -p 3212321 scp $SSH_OPTS "$JETSON:$REMOTE_LOG_DIR/*.log" "$LOCAL_LOG_DIR/" 2>/dev/null || echo "  (no logs found)"

echo "==> Cleaning up on Jetson..."
sshpass -p 3212321 ssh $SSH_OPTS "$JETSON" \
    "rm -f $REMOTE_DIR/sessions/$ARCHIVE && rm -rf $REMOTE_DIR/sessions/$SESSION"

echo "==> Done: $LOCAL_DIR/$SESSION"
echo "Files: $(find "$LOCAL_DIR/$SESSION" -type f | wc -l)"
echo "Size:  $(du -sh "$LOCAL_DIR/$SESSION" | cut -f1)"

echo "==> Composing video..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python "$SCRIPT_DIR/compose_video.py" "$LOCAL_DIR/$SESSION"
