#!/usr/bin/env bash
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

DOGFOOD_MATURITY_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --dogfood-maturity-only|--maturity-only)
      DOGFOOD_MATURITY_ONLY=1
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/uninstall_user_service.sh [--dogfood-maturity-only]

Without flags, remove the aiwiki watcher, nightly timer, and dogfood maturity validation units.
With --dogfood-maturity-only, remove only the dogfood maturity validation service/timer.
Env files and vault data are preserved.
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

cleanup_dogfood_maturity() {
  systemctl --user disable --now "$DOGFOOD_MATURITY_TIMER_NAME" >/dev/null 2>&1 || true
  systemctl --user stop "$DOGFOOD_MATURITY_SERVICE_NAME" >/dev/null 2>&1 || true
  rm -f "$DOGFOOD_MATURITY_SERVICE_PATH" "$DOGFOOD_MATURITY_TIMER_PATH"
}

if [[ "$DOGFOOD_MATURITY_ONLY" == "1" ]]; then
  cleanup_dogfood_maturity
  systemctl --user daemon-reload
  echo "[OK] Uninstalled $DOGFOOD_MATURITY_TIMER_NAME only; env files and vault data preserved"
  exit 0
fi

systemctl --user disable --now "$WATCH_SERVICE_NAME" >/dev/null 2>&1 || true
systemctl --user disable --now "$NIGHTLY_TIMER_NAME" >/dev/null 2>&1 || true
systemctl --user stop "$NIGHTLY_SERVICE_NAME" >/dev/null 2>&1 || true
cleanup_dogfood_maturity
rm -f "$WATCH_UNIT_PATH" "$NIGHTLY_SERVICE_PATH" "$NIGHTLY_TIMER_PATH"
systemctl --user daemon-reload

echo "[OK] Uninstalled $WATCH_SERVICE_NAME, $NIGHTLY_TIMER_NAME, and $DOGFOOD_MATURITY_TIMER_NAME"
