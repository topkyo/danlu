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

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"

log() {
  printf '[aiwiki-nightly] %s\n' "$*" >&2
}

PYTHON_BIN="${AIWIKI_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(bash "$SCRIPT_DIR/pick_python.sh")"
fi

log "running deterministic run-nightly"
exec "$PYTHON_BIN" -m aiwiki.cli --root "$TARGET_ROOT" advanced run-nightly --compile-limit "$COMPILE_LIMIT"
