#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

WATCH_SERVICE_NAME="aiwiki-watch.service"
NIGHTLY_SERVICE_NAME="aiwiki-nightly.service"
NIGHTLY_TIMER_NAME="aiwiki-nightly.timer"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AIWIKI_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/aiwiki"
WATCH_UNIT_PATH="$SYSTEMD_USER_DIR/$WATCH_SERVICE_NAME"
NIGHTLY_SERVICE_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_SERVICE_NAME"
NIGHTLY_TIMER_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_TIMER_NAME"
WATCH_ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-watch.env"
NIGHTLY_ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-nightly.env"
WATCH_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-watch.service.template"
NIGHTLY_SERVICE_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-nightly.service.template"
NIGHTLY_TIMER_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-nightly.timer.template"
NIGHTLY_ON_CALENDAR="${AIWIKI_NIGHTLY_ON_CALENDAR:-daily}"
NIGHTLY_PERSISTENT="${AIWIKI_NIGHTLY_PERSISTENT:-true}"
NIGHTLY_FALLBACK_ENV_DEFAULT="$HOME/.aiwiki-secrets/nvidia.env"

ensure_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if ! grep -q "^${key}=" "$file"; then
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

mkdir -p "$SYSTEMD_USER_DIR" "$AIWIKI_CONFIG_DIR"

if [[ ! -f "$WATCH_ENV_PATH" ]]; then
  cat >"$WATCH_ENV_PATH" <<EOF
AIWIKI_LLM_BACKEND=codex-cli
AIWIKI_LLM_MODEL=gpt-5.5
AIWIKI_LLM_TIMEOUT=120
AIWIKI_LLM_MAX_CONTEXT_CHARS=24000
AIWIKI_WATCH_INTERVAL=5
AIWIKI_WATCH_COMPILE_LIMIT=5
AIWIKI_WATCH_DETERMINISTIC_ONLY=1
AIWIKI_WATCH_NO_SEMANTIC_LINT=0
AIWIKI_WATCH_SKIP_INITIAL=0
AIWIKI_CODEX_COMMAND=codex
AIWIKI_CLAUDE_COMMAND=claude
EOF
fi

if [[ ! -f "$NIGHTLY_ENV_PATH" ]]; then
  cat >"$NIGHTLY_ENV_PATH" <<EOF
AIWIKI_LLM_BACKEND=codex-cli
AIWIKI_LLM_MODEL=gpt-5.5
AIWIKI_LLM_TIMEOUT=120
AIWIKI_LLM_MAX_CONTEXT_CHARS=24000
AIWIKI_NIGHTLY_COMPILE_LIMIT=5
AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0
AIWIKI_NIGHTLY_NO_SEMANTIC_LINT=0
AIWIKI_NIGHTLY_FALLBACK_ENABLED=1
AIWIKI_NIGHTLY_FALLBACK_BACKEND=nvidia-nim-api
AIWIKI_NIGHTLY_FALLBACK_MODEL=openai/gpt-oss-120b
AIWIKI_NIGHTLY_FALLBACK_ENV=$NIGHTLY_FALLBACK_ENV_DEFAULT
AIWIKI_CODEX_COMMAND=codex
AIWIKI_CLAUDE_COMMAND=claude
EOF
fi

ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_FALLBACK_ENABLED" "1"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_FALLBACK_BACKEND" "nvidia-nim-api"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_FALLBACK_MODEL" "openai/gpt-oss-120b"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_FALLBACK_ENV" "$NIGHTLY_FALLBACK_ENV_DEFAULT"

sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__ENV_FILE__|$WATCH_ENV_PATH|g" \
  "$WATCH_TEMPLATE_PATH" >"$WATCH_UNIT_PATH"

sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__ENV_FILE__|$NIGHTLY_ENV_PATH|g" \
  "$NIGHTLY_SERVICE_TEMPLATE_PATH" >"$NIGHTLY_SERVICE_PATH"

sed \
  -e "s|__ON_CALENDAR__|$NIGHTLY_ON_CALENDAR|g" \
  -e "s|__PERSISTENT__|$NIGHTLY_PERSISTENT|g" \
  "$NIGHTLY_TIMER_TEMPLATE_PATH" >"$NIGHTLY_TIMER_PATH"

systemctl --user daemon-reload
systemctl --user enable --now "$WATCH_SERVICE_NAME"
if ! systemctl --user is-active --quiet "$WATCH_SERVICE_NAME"; then
  systemctl --user start "$WATCH_SERVICE_NAME"
fi
systemctl --user is-active --quiet "$WATCH_SERVICE_NAME"
systemctl --user enable --now "$NIGHTLY_TIMER_NAME"
systemctl --user is-enabled --quiet "$NIGHTLY_TIMER_NAME"

echo "[OK] Installed $WATCH_SERVICE_NAME and $NIGHTLY_TIMER_NAME"
echo "      watch unit:    $WATCH_UNIT_PATH"
echo "      watch env:     $WATCH_ENV_PATH"
echo "      nightly svc:   $NIGHTLY_SERVICE_PATH"
echo "      nightly timer: $NIGHTLY_TIMER_PATH"
echo "      nightly env:   $NIGHTLY_ENV_PATH"
echo "      on-calendar:   $NIGHTLY_ON_CALENDAR"
echo "      note:          change AIWIKI_NIGHTLY_ON_CALENDAR / AIWIKI_NIGHTLY_PERSISTENT and rerun this script to rewrite the timer"
