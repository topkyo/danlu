#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AIWIKI_VAULT:-}" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  launchd watcher requires an explicit vault path." >&2
  exit 1
fi

LAUNCHER="$AIWIKI_VAULT/scripts/aiwiki-launcher.sh"
if [ ! -x "$LAUNCHER" ]; then
  echo "error: vault launcher is missing or not executable: $LAUNCHER" >&2
  exit 1
fi

INTERVAL="${AIWIKI_WATCH_INTERVAL:-5}"
COMPILE_LIMIT="${AIWIKI_WATCH_COMPILE_LIMIT:-5}"

ARGS=(
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

exec "$LAUNCHER" "${ARGS[@]}"
