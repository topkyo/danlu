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
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    export "$line"
  done < <(
    python3 - "$PLUGIN_DATA" <<'PY'
import json
import os
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
profiles = {
    "opencode-api": {
        "model": "deepseek-v4-pro",
        "key_setting": "llmOpencodeApiKey",
        "key_env": "AIWIKI_OPENCODE_API_KEY",
        "base_setting": "llmOpencodeBaseUrl",
        "base_env": "AIWIKI_OPENCODE_BASE_URL",
    },
    "nvidia-nim-api": {
        "model": "openai/gpt-oss-120b",
        "key_setting": "llmNvidiaNimApiKey",
        "key_env": "AIWIKI_NVIDIA_NIM_API_KEY",
        "base_setting": "llmNvidiaNimBaseUrl",
        "base_env": "AIWIKI_NVIDIA_NIM_BASE_URL",
    },
    "openrouter-api": {
        "model": "",
        "key_setting": "llmOpenrouterApiKey",
        "key_env": "AIWIKI_OPENROUTER_API_KEY",
        "base_setting": "llmOpenrouterBaseUrl",
        "base_env": "AIWIKI_OPENROUTER_BASE_URL",
    },
    "anthropic-api": {
        "model": "claude-sonnet-4-20250514",
        "key_setting": "llmAnthropicApiKey",
        "key_env": "AIWIKI_ANTHROPIC_API_KEY",
        "base_setting": "llmAnthropicBaseUrl",
        "base_env": "AIWIKI_ANTHROPIC_BASE_URL",
    },
    "openai-api": {
        "model": "gpt-4.1-mini",
        "key_setting": "llmCustomOpenaiApiKey",
        "key_env": "AIWIKI_LLM_API_KEY",
        "base_setting": "llmCustomOpenaiBaseUrl",
        "base_env": "AIWIKI_LLM_BASE_URL",
    },
}
profile = profiles.get(backend, {"model": ""})
default_models = {str(item.get("model") or "") for item in profiles.values() if item.get("model")}
configured_model = str(settings.get("llmModel") or "").strip()
profile_model = str(profile.get("model") or "").strip()
if profile_model and configured_model and configured_model != profile_model and configured_model in default_models:
    configured_model = profile_model
mapping = {
    "AIWIKI_LLM_BACKEND": backend,
    "AIWIKI_LLM_MODEL": configured_model or profile_model,
}
key_setting = profile.get("key_setting")
key_env = profile.get("key_env")
if key_setting and key_env:
    mapping[key_env] = settings.get(key_setting, "")
base_setting = profile.get("base_setting")
base_env = profile.get("base_env")
if base_setting and base_env:
    mapping[base_env] = settings.get(base_setting, "")
for env_name, value in mapping.items():
    if os.environ.get(env_name):
        continue
    if isinstance(value, str) and value.strip():
        print(f"{env_name}={value.strip()}")
PY
  )
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m aiwiki.cli --root "$TARGET_ROOT" "$@"
