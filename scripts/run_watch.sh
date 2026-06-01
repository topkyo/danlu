#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AIWIKI_VAULT:-}" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  Service scripts require an explicit vault path." >&2
  echo "  Example: AIWIKI_VAULT=/path/to/vault $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="$AIWIKI_VAULT"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

INTERVAL="${AIWIKI_WATCH_INTERVAL:-5}"
COMPILE_LIMIT="${AIWIKI_WATCH_COMPILE_LIMIT:-5}"

ARGS=(
  --root "$TARGET_ROOT"
  watch
  --interval "$INTERVAL"
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "${AIWIKI_WATCH_DETERMINISTIC_ONLY:-1}" == "0" ]]; then
  ARGS+=(--with-llm)
fi

if [[ "${AIWIKI_WATCH_NO_SEMANTIC_LINT:-0}" == "1" ]]; then
  ARGS+=(--no-semantic-lint)
fi

if [[ "${AIWIKI_WATCH_SKIP_INITIAL:-0}" == "1" ]]; then
  ARGS+=(--skip-initial)
fi

exec python3 -m aiwiki.cli "${ARGS[@]}"
