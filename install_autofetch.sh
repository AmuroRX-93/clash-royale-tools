#!/bin/bash
# Install the hourly auto-fetch LaunchAgent (macOS).
#
# This registers a launchd job that runs auto_fetch.py every hour, archiving
# your Clash Royale battle history + trophy snapshots into archive.db even when
# the dashboard isn't open.
#
# Run this in YOUR OWN Terminal (not inside a sandboxed environment):
#   ./install_autofetch.sh
#
# Manage it later:
#   launchctl bootout gui/$(id -u)/com.yuzhe.clashroyale.autofetch   # stop/remove
#   tail -f auto_fetch.log                                            # watch runs

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.yuzhe.clashroyale.autofetch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
MYUID="$(id -u)"

if [ ! -f "$PLIST" ]; then
  echo "ERROR: $PLIST not found. Expected it to be created already."
  exit 1
fi

echo "Booting out any existing job (ignore 'No such process')..."
launchctl bootout "gui/$MYUID/$LABEL" 2>/dev/null || true

echo "Bootstrapping LaunchAgent..."
launchctl bootstrap "gui/$MYUID" "$PLIST"

echo "Kickstarting one run now..."
launchctl kickstart -k "gui/$MYUID/$LABEL" || true

sleep 2
echo
echo "Status:"
launchctl print "gui/$MYUID/$LABEL" 2>/dev/null | grep -E "state =|program =|run interval" || true
echo
echo "Done. It will run every hour. Watch logs with:  tail -f \"$HERE/auto_fetch.log\""
