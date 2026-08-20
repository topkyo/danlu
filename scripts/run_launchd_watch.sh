#!/bin/bash
set -euo pipefail

if [ -z "${AIWIKI_VAULT:-}" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  launchd watcher requires an explicit vault path." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="${AIWIKI_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(/bin/bash "$SCRIPT_DIR/pick_python.sh")"
fi

INTERVAL="${AIWIKI_WATCH_INTERVAL:-5}"
COMPILE_LIMIT="${AIWIKI_WATCH_COMPILE_LIMIT:-5}"

ARGS=(
  --root "$AIWIKI_VAULT"
  advanced
  watch
  --interval "$INTERVAL"
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "${AIWIKI_WATCH_SKIP_INITIAL:-0}" == "1" ]]; then
  ARGS+=(--skip-initial)
fi

exec "$PYTHON_BIN" -m aiwiki.cli "${ARGS[@]}"
