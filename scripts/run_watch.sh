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
LAUNCHER="$TARGET_ROOT/scripts/aiwiki-launcher.sh"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

INTERVAL="${AIWIKI_WATCH_INTERVAL:-5}"
COMPILE_LIMIT="${AIWIKI_WATCH_COMPILE_LIMIT:-5}"

ARGS=(
  --root "$TARGET_ROOT"
  advanced
  watch
  --interval "$INTERVAL"
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "${AIWIKI_WATCH_SKIP_INITIAL:-0}" == "1" ]]; then
  ARGS+=(--skip-initial)
fi

if [ -x "$LAUNCHER" ]; then
  exec "$LAUNCHER" "${ARGS[@]:2}"
fi

# Fallback: repo launcher (picks Python ≥3.10) then bare python3.
REPO_LAUNCHER="$PROJECT_ROOT/scripts/aiwiki-launcher.sh"
if [ -x "$REPO_LAUNCHER" ]; then
  export AIWIKI_VAULT="$TARGET_ROOT"
  exec "$REPO_LAUNCHER" "${ARGS[@]:2}"
fi

exec python3 -m aiwiki.cli "${ARGS[@]}"
