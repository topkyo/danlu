#!/usr/bin/env bash
set -euo pipefail

WATCH_LABEL="${AIWIKI_LAUNCHD_WATCH_LABEL:-com.aiwiki.watch}"
NIGHTLY_LABEL="${AIWIKI_LAUNCHD_NIGHTLY_LABEL:-com.aiwiki.nightly}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
WATCH_PLIST="$LAUNCH_AGENTS_DIR/$WATCH_LABEL.plist"
NIGHTLY_PLIST="$LAUNCH_AGENTS_DIR/$NIGHTLY_LABEL.plist"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: launchd uninstall is only supported on macOS" >&2
  exit 1
fi

DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN" "$WATCH_PLIST" >/dev/null 2>&1 || true
launchctl bootout "$DOMAIN" "$NIGHTLY_PLIST" >/dev/null 2>&1 || true
rm -f "$WATCH_PLIST" "$NIGHTLY_PLIST"

echo "[OK] Uninstalled launchd watcher and nightly jobs"
