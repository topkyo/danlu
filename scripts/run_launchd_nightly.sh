#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AIWIKI_VAULT:-}" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  launchd nightly requires an explicit vault path." >&2
  exit 1
fi

LAUNCHER="$AIWIKI_VAULT/scripts/aiwiki-launcher.sh"
if [ ! -x "$LAUNCHER" ]; then
  echo "error: vault launcher is missing or not executable: $LAUNCHER" >&2
  exit 1
fi

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"

exec "$LAUNCHER" advanced run-nightly --compile-limit "$COMPILE_LIMIT"
