#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"
cd "$PROJECT_ROOT"

for candidate in "$HOME/.local/bin" "$HOME/.local/npm/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin"; do
  if [ -d "$candidate" ]; then
    case ":${PATH:-}:" in
      *":$candidate:"*) ;;
      *) PATH="$candidate${PATH:+:$PATH}" ;;
    esac
  fi
done
export PATH

# Obsidian/GUI launches often get a minimal PATH where `python3` is Apple
# /usr/bin/python3 (3.9). Prefer an explicit ≥3.10 interpreter.
_aiwiki_pick_python() {
  local cand version
  for cand in \
    ${AIWIKI_PYTHON:+"$AIWIKI_PYTHON"} \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    "$HOME/.local/bin/python3" \
    python3.14 python3.13 python3.12 python3.11 python3.10 \
    python3; do
    [ -n "$cand" ] || continue
    if ! command -v "$cand" >/dev/null 2>&1 && [ ! -x "$cand" ]; then
      continue
    fi
    version="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    case "$version" in
      3.1[0-9]|3.[2-9][0-9]|[4-9].*)
        printf '%s\n' "$cand"
        return 0
        ;;
    esac
  done
  echo "error: need Python >= 3.10 for aiwiki (Obsidian PATH often hits 3.9). Set AIWIKI_PYTHON." >&2
  return 1
}
AIWIKI_PYTHON_BIN="$(_aiwiki_pick_python)"

PLUGIN_DATA="$TARGET_ROOT/.obsidian/plugins/furnace-product-shell/data.json"
# Merge data.json into empty LLM env slots only. Product Shell may already inject
# AIWIKI_LLM_BACKEND (and sometimes keys); never overwrite non-empty values, and
# still fill missing keys when backend was injected without a secret.
if [ -f "$PLUGIN_DATA" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    env_name="${line%%=*}"
    env_value="${line#*=}"
    if [ -z "${!env_name:-}" ] && [ -n "$env_value" ]; then
      export "$env_name=$env_value"
    fi
  done < <(
    "$AIWIKI_PYTHON_BIN" - "$PLUGIN_DATA" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
if not isinstance(settings, dict):
    raise SystemExit(0)
backend = str(settings.get("llmBackend") or "opencode-api").strip() or "opencode-api"
profiles = [
    ("deepseek-api", "deepseek-v4-pro", "llmDeepseekApiKey", "AIWIKI_DEEPSEEK_API_KEY", "llmDeepseekBaseUrl", "AIWIKI_DEEPSEEK_BASE_URL"),
    ("opencode-api", "deepseek-v4-pro", "llmOpencodeApiKey", "AIWIKI_OPENCODE_API_KEY", "llmOpencodeBaseUrl", "AIWIKI_OPENCODE_BASE_URL"),
    ("anthropic-api", "claude-sonnet-4-20250514", "llmAnthropicApiKey", "AIWIKI_ANTHROPIC_API_KEY", "llmAnthropicBaseUrl", "AIWIKI_ANTHROPIC_BASE_URL"),
    ("openai-api", "gpt-4.1-mini", "llmCustomOpenaiApiKey", "AIWIKI_LLM_API_KEY", "llmCustomOpenaiBaseUrl", "AIWIKI_LLM_BASE_URL"),
]
profile_model = ""
key_setting = ""
key_env = ""
base_setting = ""
base_env = ""
default_models = []
for item in profiles:
    item_backend, item_model, item_key_setting, item_key_env, item_base_setting, item_base_env = item
    if item_model:
        default_models.append(item_model)
    if item_backend == backend:
        profile_model = item_model
        key_setting = item_key_setting
        key_env = item_key_env
        base_setting = item_base_setting
        base_env = item_base_env
configured_model = str(settings.get("llmModel") or "").strip()
if profile_model and configured_model and configured_model != profile_model and configured_model in default_models:
    configured_model = profile_model
exports = [("AIWIKI_LLM_BACKEND", backend), ("AIWIKI_LLM_MODEL", configured_model or profile_model)]
if key_setting and key_env:
    exports.append((key_env, settings.get(key_setting, "")))
if base_setting and base_env:
    exports.append((base_env, settings.get(base_setting, "")))
for env_name, value in exports:
    if isinstance(value, str) and value.strip():
        print(env_name + "=" + value.strip())
PY
  )
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$AIWIKI_PYTHON_BIN" -m aiwiki.cli --root "$TARGET_ROOT" "$@"
