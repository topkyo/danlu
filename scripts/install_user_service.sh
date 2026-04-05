#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

SERVICE_NAME="aiwiki-watch.service"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AIWIKI_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/aiwiki"
UNIT_PATH="$SYSTEMD_USER_DIR/$SERVICE_NAME"
ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-watch.env"
TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-watch.service.template"

mkdir -p "$SYSTEMD_USER_DIR" "$AIWIKI_CONFIG_DIR"

if [[ ! -f "$ENV_PATH" ]]; then
  cat >"$ENV_PATH" <<EOF
AIWIKI_LLM_BACKEND=codex-cli
AIWIKI_LLM_MODEL=
AIWIKI_LLM_TIMEOUT=120
AIWIKI_LLM_MAX_CONTEXT_CHARS=24000
AIWIKI_WATCH_INTERVAL=5
AIWIKI_WATCH_COMPILE_LIMIT=5
AIWIKI_WATCH_DETERMINISTIC_ONLY=0
AIWIKI_WATCH_NO_SEMANTIC_LINT=0
AIWIKI_WATCH_SKIP_INITIAL=0
AIWIKI_CODEX_COMMAND=codex
AIWIKI_CLAUDE_COMMAND=claude
EOF
fi

sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__ENV_FILE__|$ENV_PATH|g" \
  "$TEMPLATE_PATH" >"$UNIT_PATH"

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"
if ! systemctl --user is-active --quiet "$SERVICE_NAME"; then
  systemctl --user start "$SERVICE_NAME"
fi
systemctl --user is-active --quiet "$SERVICE_NAME"

echo "[OK] Installed $SERVICE_NAME"
echo "      unit: $UNIT_PATH"
echo "      env:  $ENV_PATH"
