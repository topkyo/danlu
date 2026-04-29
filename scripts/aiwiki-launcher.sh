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
mapping = {
    "AIWIKI_LLM_BACKEND": settings.get("llmBackend", ""),
    "AIWIKI_LLM_MODEL": settings.get("llmModel", ""),
    "AIWIKI_NVIDIA_NIM_API_KEY": settings.get("llmNvidiaNimApiKey", ""),
    "AIWIKI_NVIDIA_NIM_BASE_URL": settings.get("llmNvidiaNimBaseUrl", ""),
}
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
