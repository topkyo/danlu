#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
if [[ -z "${AIWIKI_VAULT:-}" ]]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  install_user_service.sh requires an explicit vault path; it will not default to the project root." >&2
  echo "  Example: AIWIKI_VAULT=/path/to/vault scripts/install_user_service.sh" >&2
  exit 1
fi
VAULT_ROOT="$AIWIKI_VAULT"
PYTHON_BIN="${PYTHON:-python3}"

WATCH_SERVICE_NAME="aiwiki-watch.service"
NIGHTLY_SERVICE_NAME="aiwiki-nightly.service"
NIGHTLY_TIMER_NAME="aiwiki-nightly.timer"
DOGFOOD_MATURITY_SERVICE_NAME="aiwiki-dogfood-maturity.service"
DOGFOOD_MATURITY_TIMER_NAME="aiwiki-dogfood-maturity.timer"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AIWIKI_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/aiwiki"
WATCH_UNIT_PATH="$SYSTEMD_USER_DIR/$WATCH_SERVICE_NAME"
NIGHTLY_SERVICE_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_SERVICE_NAME"
NIGHTLY_TIMER_PATH="$SYSTEMD_USER_DIR/$NIGHTLY_TIMER_NAME"
DOGFOOD_MATURITY_SERVICE_PATH="$SYSTEMD_USER_DIR/$DOGFOOD_MATURITY_SERVICE_NAME"
DOGFOOD_MATURITY_TIMER_PATH="$SYSTEMD_USER_DIR/$DOGFOOD_MATURITY_TIMER_NAME"
WATCH_ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-watch.env"
NIGHTLY_ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-nightly.env"
DOGFOOD_MATURITY_ENV_PATH="$AIWIKI_CONFIG_DIR/aiwiki-dogfood-maturity.env"
WATCH_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-watch.service.template"
NIGHTLY_SERVICE_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-nightly.service.template"
NIGHTLY_TIMER_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-nightly.timer.template"
DOGFOOD_MATURITY_SERVICE_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-dogfood-maturity.service.template"
DOGFOOD_MATURITY_TIMER_TEMPLATE_PATH="$PROJECT_ROOT/systemd/aiwiki-dogfood-maturity.timer.template"
NIGHTLY_ON_CALENDAR="${AIWIKI_NIGHTLY_ON_CALENDAR:-daily}"
NIGHTLY_PERSISTENT="${AIWIKI_NIGHTLY_PERSISTENT:-true}"
INSTALL_DOGFOOD_MATURITY="${AIWIKI_INSTALL_DOGFOOD_MATURITY:-0}"
DOGFOOD_MATURITY_ON_CALENDAR="${AIWIKI_DOGFOOD_MATURITY_ON_CALENDAR:-*-*-* 00:15:00 UTC}"
DOGFOOD_MATURITY_PERSISTENT="${AIWIKI_DOGFOOD_MATURITY_PERSISTENT:-true}"
DOGFOOD_MATURITY_VAULT_DEFAULT="${AIWIKI_DOGFOOD_VAULT:-}"

truthy() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

if truthy "$INSTALL_DOGFOOD_MATURITY" && [[ -z "$DOGFOOD_MATURITY_VAULT_DEFAULT" ]]; then
  echo "error: AIWIKI_INSTALL_DOGFOOD_MATURITY=1 requires AIWIKI_DOGFOOD_VAULT to be set" >&2
  exit 1
fi

ensure_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if ! grep -q "^${key}=" "$file"; then
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

set_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp "${file}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    index($0, key "=") == 1 { print key "=" value; updated = 1; next }
    { print }
    END { if (!updated) print key "=" value }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}

env_key_value() {
  local file="$1"
  local key="$2"
  local default="$3"
  local line
  line="$(grep -m 1 "^${key}=" "$file" || true)"
  if [[ -n "$line" ]]; then
    printf '%s\n' "${line#*=}"
  else
    printf '%s\n' "$default"
  fi
}

mkdir -p "$SYSTEMD_USER_DIR" "$AIWIKI_CONFIG_DIR"

PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m aiwiki.cli \
  --root "$PROJECT_ROOT" advanced sync-product-shell "$VAULT_ROOT" >/dev/null

if [[ ! -f "$WATCH_ENV_PATH" ]]; then
  cat >"$WATCH_ENV_PATH" <<EOF
AIWIKI_VAULT=$VAULT_ROOT
AIWIKI_LLM_TIMEOUT=120
AIWIKI_LLM_MAX_CONTEXT_CHARS=24000
AIWIKI_WATCH_INTERVAL=5
AIWIKI_WATCH_COMPILE_LIMIT=5
AIWIKI_WATCH_DETERMINISTIC_ONLY=1
AIWIKI_WATCH_NO_SEMANTIC_LINT=0
AIWIKI_WATCH_SKIP_INITIAL=0
EOF
fi

if [[ ! -f "$NIGHTLY_ENV_PATH" ]]; then
  cat >"$NIGHTLY_ENV_PATH" <<EOF
AIWIKI_VAULT=$VAULT_ROOT
AIWIKI_LLM_TIMEOUT=120
AIWIKI_LLM_MAX_CONTEXT_CHARS=24000
AIWIKI_NIGHTLY_COMPILE_LIMIT=5
AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0
AIWIKI_NIGHTLY_NO_SEMANTIC_LINT=0
AIWIKI_AUTONOMY_PROFILE=${AIWIKI_AUTONOMY_PROFILE:-agentic}
AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=${AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT:-${AUTO_APPLY_LIGHT:-0}}
AIWIKI_NIGHTLY_AUTO_ADOPT_L1=${AIWIKI_NIGHTLY_AUTO_ADOPT_L1:-${AUTO_ADOPT_L1:-0}}
AIWIKI_NIGHTLY_AUTO_ADOPT_L2=${AIWIKI_NIGHTLY_AUTO_ADOPT_L2:-${AUTO_ADOPT_L2:-0}}
AIWIKI_NIGHTLY_AUTO_ADOPT_L3=${AIWIKI_NIGHTLY_AUTO_ADOPT_L3:-${AUTO_ADOPT_L3:-0}}
AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=${AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS:-${AUTO_ADOPT_JUDGMENTS:-0}}
AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC=${AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC:-0}
AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3=${AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3:-0}
EOF
fi

if truthy "$INSTALL_DOGFOOD_MATURITY" && [[ ! -f "$DOGFOOD_MATURITY_ENV_PATH" ]]; then
  cat >"$DOGFOOD_MATURITY_ENV_PATH" <<EOF
AIWIKI_DOGFOOD_VAULT=$DOGFOOD_MATURITY_VAULT_DEFAULT
AIWIKI_DOGFOOD_MATURITY_PREVIEW_LIMIT=1000
AIWIKI_DOGFOOD_MATURITY_L3_LIMIT=1000
AIWIKI_DOGFOOD_MATURITY_COMPILE_LIMIT=0
AIWIKI_DOGFOOD_MATURITY_NO_SEMANTIC_LINT=1
EOF
fi

ensure_env_key "$WATCH_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_AUTONOMY_PROFILE" "${AIWIKI_AUTONOMY_PROFILE:-agentic}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT" "${AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT:-${AUTO_APPLY_LIGHT:-0}}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_ADOPT_L1" "${AIWIKI_NIGHTLY_AUTO_ADOPT_L1:-${AUTO_ADOPT_L1:-0}}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_ADOPT_L2" "${AIWIKI_NIGHTLY_AUTO_ADOPT_L2:-${AUTO_ADOPT_L2:-0}}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_ADOPT_L3" "${AIWIKI_NIGHTLY_AUTO_ADOPT_L3:-${AUTO_ADOPT_L3:-0}}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS" "${AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS:-${AUTO_ADOPT_JUDGMENTS:-0}}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC" "${AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC:-0}"
ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3" "${AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3:-0}"
if truthy "$INSTALL_DOGFOOD_MATURITY"; then
  ensure_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_VAULT" "$DOGFOOD_MATURITY_VAULT_DEFAULT"
  ensure_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_PREVIEW_LIMIT" "1000"
  ensure_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_L3_LIMIT" "1000"
  ensure_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_COMPILE_LIMIT" "0"
  ensure_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_NO_SEMANTIC_LINT" "1"
  if [[ -n "${AIWIKI_DOGFOOD_MATURITY_ENVRC:-}" ]]; then
    set_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_ENVRC" "$AIWIKI_DOGFOOD_MATURITY_ENVRC"
  fi
fi

WATCH_VAULT_ROOT="$(env_key_value "$WATCH_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT")"
NIGHTLY_VAULT_ROOT="$(env_key_value "$NIGHTLY_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT")"

render_template() {
  local template="$1"
  local dest="$2"
  shift 2
  "$PYTHON_BIN" - "$template" "$dest" "$@" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1])
dest = Path(sys.argv[2])
text = template.read_text(encoding="utf-8")
args = sys.argv[3:]
if len(args) % 2 != 0:
    raise SystemExit("render_template expects KEY VALUE pairs")
for i in range(0, len(args), 2):
    text = text.replace(args[i], args[i + 1])
dest.write_text(text, encoding="utf-8")
PY
}

render_template "$WATCH_TEMPLATE_PATH" "$WATCH_UNIT_PATH" \
  __PROJECT_ROOT__ "$PROJECT_ROOT" \
  __ENV_FILE__ "$WATCH_ENV_PATH" \
  __VAULT__ "$WATCH_VAULT_ROOT"

render_template "$NIGHTLY_SERVICE_TEMPLATE_PATH" "$NIGHTLY_SERVICE_PATH" \
  __PROJECT_ROOT__ "$PROJECT_ROOT" \
  __ENV_FILE__ "$NIGHTLY_ENV_PATH" \
  __VAULT__ "$NIGHTLY_VAULT_ROOT"

render_template "$NIGHTLY_TIMER_TEMPLATE_PATH" "$NIGHTLY_TIMER_PATH" \
  __ON_CALENDAR__ "$NIGHTLY_ON_CALENDAR" \
  __PERSISTENT__ "$NIGHTLY_PERSISTENT"

if truthy "$INSTALL_DOGFOOD_MATURITY"; then
  render_template "$DOGFOOD_MATURITY_SERVICE_TEMPLATE_PATH" "$DOGFOOD_MATURITY_SERVICE_PATH" \
    __PROJECT_ROOT__ "$PROJECT_ROOT" \
    __ENV_FILE__ "$DOGFOOD_MATURITY_ENV_PATH" \
    __DOGFOOD_VAULT__ "$DOGFOOD_MATURITY_VAULT_DEFAULT"

  render_template "$DOGFOOD_MATURITY_TIMER_TEMPLATE_PATH" "$DOGFOOD_MATURITY_TIMER_PATH" \
    __ON_CALENDAR__ "$DOGFOOD_MATURITY_ON_CALENDAR" \
    __PERSISTENT__ "$DOGFOOD_MATURITY_PERSISTENT"
else
  systemctl --user disable --now "$DOGFOOD_MATURITY_TIMER_NAME" >/dev/null 2>&1 || true
  systemctl --user stop "$DOGFOOD_MATURITY_SERVICE_NAME" >/dev/null 2>&1 || true
  rm -f "$DOGFOOD_MATURITY_SERVICE_PATH" "$DOGFOOD_MATURITY_TIMER_PATH"
fi

systemctl --user daemon-reload
systemctl --user enable --now "$WATCH_SERVICE_NAME"
if ! systemctl --user is-active --quiet "$WATCH_SERVICE_NAME"; then
  systemctl --user start "$WATCH_SERVICE_NAME"
fi
systemctl --user is-active --quiet "$WATCH_SERVICE_NAME"
systemctl --user enable --now "$NIGHTLY_TIMER_NAME"
systemctl --user is-enabled --quiet "$NIGHTLY_TIMER_NAME"
if truthy "$INSTALL_DOGFOOD_MATURITY"; then
  systemctl --user enable --now "$DOGFOOD_MATURITY_TIMER_NAME"
  systemctl --user is-enabled --quiet "$DOGFOOD_MATURITY_TIMER_NAME"
fi

echo "[OK] Installed $WATCH_SERVICE_NAME and $NIGHTLY_TIMER_NAME"
echo "      watch unit:    $WATCH_UNIT_PATH"
echo "      watch env:     $WATCH_ENV_PATH"
echo "      nightly svc:   $NIGHTLY_SERVICE_PATH"
echo "      nightly timer: $NIGHTLY_TIMER_PATH"
echo "      nightly env:   $NIGHTLY_ENV_PATH"
echo "      on-calendar:   $NIGHTLY_ON_CALENDAR"
echo "      plugin:        synced Product Shell release files (data.json preserved)"
echo "      note:          change AIWIKI_NIGHTLY_ON_CALENDAR / AIWIKI_NIGHTLY_PERSISTENT and rerun this script to rewrite the timer"
echo "Note: nightly auto-adopt/apply defaults are on for the full local furnace profile."
echo "      Set AIWIKI_NIGHTLY_AUTO_* or legacy AUTO_* env vars to 0 before install to narrow automation."
echo "      LLM backend/key are read from the vault Product Shell UI via scripts/aiwiki-launcher.sh."
if truthy "$INSTALL_DOGFOOD_MATURITY"; then
  echo "      maturity svc:  $DOGFOOD_MATURITY_SERVICE_PATH"
  echo "      maturity timer:$DOGFOOD_MATURITY_TIMER_PATH"
  echo "      maturity env:  $DOGFOOD_MATURITY_ENV_PATH"
  echo "      maturity cal:  $DOGFOOD_MATURITY_ON_CALENDAR"
  echo "      note:          dogfood maturity is a validation harness, not a default product service"
else
  echo "      maturity:      not installed (set AIWIKI_INSTALL_DOGFOOD_MATURITY=1 for validation runs)"
fi
