#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"
cd "$PROJECT_ROOT"

for candidate in "$HOME/.local/bin" "$HOME/.local/npm/bin" "$HOME/bin"; do
  if [ -d "$candidate" ]; then
    case ":${PATH:-}:" in
      *":$candidate:"*) ;;
      *) PATH="$candidate${PATH:+:$PATH}" ;;
    esac
  fi
done
export PATH

PLUGIN_DATA="$TARGET_ROOT/.obsidian/plugins/furnace-product-shell/data.json"
if [ -f "$PLUGIN_DATA" ]; then
  for env_name in \
    AIWIKI_LLM_BACKEND AIWIKI_LLM_MODEL AIWIKI_MODEL_FALLBACK \
    AIWIKI_DEEPSEEK_API_KEY AIWIKI_DEEPSEEK_BASE_URL \
    AIWIKI_OPENCODE_API_KEY AIWIKI_OPENCODE_BASE_URL \
    AIWIKI_ANTHROPIC_API_KEY AIWIKI_ANTHROPIC_BASE_URL \
    AIWIKI_LLM_API_KEY AIWIKI_LLM_BASE_URL \
    DEEPSEEK_API_KEY DEEPSEEK_BASE_URL \
    OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
    ANTHROPIC_API_KEY ANTHROPIC_BASE_URL; do
    unset "$env_name"
  done
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    export "$line"
  done < <(
    python3 - "$PLUGIN_DATA" <<'PY'
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

exec python3 -m aiwiki.cli --root "$TARGET_ROOT" "$@"
