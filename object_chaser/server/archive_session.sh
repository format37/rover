#!/bin/bash
# Archive a session folder into a .tar.gz for fast transfer.
# Usage: ./archive_session.sh [session_name]
# If no session_name given, archives the most recent session.

set -e

SESSIONS_DIR="$(cd "$(dirname "$0")" && pwd)/sessions"

if [ ! -d "$SESSIONS_DIR" ]; then
    echo "No sessions directory found at $SESSIONS_DIR"
    exit 1
fi

if [ -n "$1" ]; then
    SESSION="$1"
else
    SESSION="$(ls -1t "$SESSIONS_DIR" | grep -v '\.tar\.gz$' | head -1)"
fi

if [ -z "$SESSION" ] || [ ! -d "$SESSIONS_DIR/$SESSION" ]; then
    echo "Session not found: $SESSION"
    exit 1
fi

ARCHIVE="$SESSIONS_DIR/${SESSION}.tar.gz"

if [ -f "$ARCHIVE" ]; then
    echo "Archive already exists: $ARCHIVE ($(du -sh "$ARCHIVE" | cut -f1))"
    exit 0
fi

echo "Archiving: $SESSIONS_DIR/$SESSION"
echo "Files: $(find "$SESSIONS_DIR/$SESSION" -type f | wc -l)"
echo "Size:  $(du -sh "$SESSIONS_DIR/$SESSION" | cut -f1)"

tar -czf "$ARCHIVE" -C "$SESSIONS_DIR" "$SESSION"

echo "Archive: $ARCHIVE ($(du -sh "$ARCHIVE" | cut -f1))"
