#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="${PYTHONPATH:-$PROJECT_ROOT/src}"

INTERVAL="${AIWIKI_WATCH_INTERVAL:-5}"
COMPILE_LIMIT="${AIWIKI_WATCH_COMPILE_LIMIT:-5}"

ARGS=(
  --root "$PROJECT_ROOT"
  watch
  --interval "$INTERVAL"
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "${AIWIKI_WATCH_DETERMINISTIC_ONLY:-0}" == "1" ]]; then
  ARGS+=(--deterministic-only)
fi

if [[ "${AIWIKI_WATCH_NO_SEMANTIC_LINT:-0}" == "1" ]]; then
  ARGS+=(--no-semantic-lint)
fi

if [[ "${AIWIKI_WATCH_SKIP_INITIAL:-0}" == "1" ]]; then
  ARGS+=(--skip-initial)
fi

exec python3 -m aiwiki.cli "${ARGS[@]}"
