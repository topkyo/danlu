#!/usr/bin/env bash
# Remove aiwiki user-level systemd services: watcher + nightly timer.
# Note: dogfood maturity validation units are also cleaned up for users upgrading
# from an older install.
set -euo pipefail

WATCH_SERVICE_NAME="aiwiki-watch.service"
NIGHTLY_SERVICE_NAME="aiwiki-nightly.service"
NIGHTLY_TIMER_NAME="aiwiki-nightly.timer"
DOGFOOD_MATURITY_SERVICE_NAME="aiwiki-dogfood-maturity.service"
DOGFOOD_MATURITY_TIMER_NAME="aiwiki-dogfood-maturity.timer"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WATCH_UNIT_PATH="$SYSTEMD_USER_DIR/$WATCH_SERVICE_NAME"
NIGHTLY_SERVICE_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_SERVICE_NAME"
NIGHTLY_TIMER_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_TIMER_NAME"
DOGFOOD_MATURITY_SERVICE_PATH="$SYSTEMD_USER_DIR/$DOGFOOD_MATURITY_SERVICE_NAME"
DOGFOOD_MATURITY_TIMER_PATH="$SYSTEMD_USER_DIR/$DOGFOOD_MATURITY_TIMER_NAME"

cleanup_dogfood_maturity() {
  systemctl --user disable --now "$DOGFOOD_MATURITY_TIMER_NAME" >/dev/null 2>&1 || true
  systemctl --user stop "$DOGFOOD_MATURITY_SERVICE_NAME" >/dev/null 2>&1 || true
  rm -f "$DOGFOOD_MATURITY_SERVICE_PATH" "$DOGFOOD_MATURITY_TIMER_PATH"
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      cat <<'EOF'
Usage: scripts/uninstall_user_service.sh

Removes aiwiki watcher, nightly timer, and any leftover dogfood maturity
validation units from previous installs. Env files and vault data are preserved.
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

systemctl --user disable --now "$WATCH_SERVICE_NAME" >/dev/null 2>&1 || true
systemctl --user disable --now "$NIGHTLY_TIMER_NAME" >/dev/null 2>&1 || true
systemctl --user stop "$NIGHTLY_SERVICE_NAME" >/dev/null 2>&1 || true
cleanup_dogfood_maturity
rm -f "$WATCH_UNIT_PATH" "$NIGHTLY_SERVICE_PATH" "$NIGHTLY_TIMER_PATH"
systemctl --user daemon-reload

echo "[OK] Uninstalled $WATCH_SERVICE_NAME and $NIGHTLY_TIMER_NAME"
echo "      env files and vault data preserved"
echo "      dogfood maturity units removed if present"
