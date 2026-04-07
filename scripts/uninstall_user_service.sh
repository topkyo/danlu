#!/usr/bin/env bash
set -euo pipefail

WATCH_SERVICE_NAME="aiwiki-watch.service"
NIGHTLY_SERVICE_NAME="aiwiki-nightly.service"
NIGHTLY_TIMER_NAME="aiwiki-nightly.timer"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WATCH_UNIT_PATH="$SYSTEMD_USER_DIR/$WATCH_SERVICE_NAME"
NIGHTLY_SERVICE_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_SERVICE_NAME"
NIGHTLY_TIMER_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_TIMER_NAME"

systemctl --user disable --now "$WATCH_SERVICE_NAME" >/dev/null 2>&1 || true
systemctl --user disable --now "$NIGHTLY_TIMER_NAME" >/dev/null 2>&1 || true
systemctl --user stop "$NIGHTLY_SERVICE_NAME" >/dev/null 2>&1 || true
rm -f "$WATCH_UNIT_PATH" "$NIGHTLY_SERVICE_PATH" "$NIGHTLY_TIMER_PATH"
systemctl --user daemon-reload

echo "[OK] Uninstalled $WATCH_SERVICE_NAME and $NIGHTLY_TIMER_NAME"
