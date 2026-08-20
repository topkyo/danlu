#!/bin/bash
set -euo pipefail

if [ -z "${AIWIKI_VAULT:-}" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  launchd nightly requires an explicit vault path." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="${AIWIKI_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(/bin/bash "$SCRIPT_DIR/pick_python.sh")"
fi

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"

exec "$PYTHON_BIN" -m aiwiki.cli --root "$AIWIKI_VAULT" advanced run-nightly --compile-limit "$COMPILE_LIMIT"
