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

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"

log() {
  printf '[aiwiki-nightly] %s\n' "$*" >&2
}

run_aiwiki() {
  if [ -x "$LAUNCHER" ]; then
    "$LAUNCHER" "$@"
    return $?
  fi
  python3 -m aiwiki.cli --root "$TARGET_ROOT" "$@"
}

log "running deterministic run-nightly"
exec run_aiwiki advanced run-nightly --compile-limit "$COMPILE_LIMIT"
