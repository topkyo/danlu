#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="aiwiki-watch.service"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$SYSTEMD_USER_DIR/$SERVICE_NAME"

systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -f "$UNIT_PATH"
systemctl --user daemon-reload

echo "[OK] Uninstalled $SERVICE_NAME"
