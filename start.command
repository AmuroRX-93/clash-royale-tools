#!/bin/bash
# Double-click this file in Finder to launch the Clash Royale dashboard.
cd "$(dirname "$0")" || exit 1

PORT="8787"
URL="http://127.0.0.1:${PORT}"

echo "Starting Clash Royale dashboard on ${URL} ..."

# Kill any stale server still holding the port (old code / previous run).
OLD_PIDS="$(lsof -ti :${PORT} 2>/dev/null)"
if [ -n "$OLD_PIDS" ]; then
  echo "Stopping old server (PID: $OLD_PIDS) ..."
  kill $OLD_PIDS 2>/dev/null
  sleep 1
  # Force-kill anything still alive.
  STILL="$(lsof -ti :${PORT} 2>/dev/null)"
  [ -n "$STILL" ] && kill -9 $STILL 2>/dev/null
fi

( sleep 1.5; open "$URL" 2>/dev/null ) &
python3 app.py "$PORT"
