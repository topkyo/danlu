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

if [[ "${AIWIKI_NIGHTLY_DETERMINISTIC_ONLY:-0}" == "1" ]]; then
  exec "$LAUNCHER" nightly
fi

ARGS=(
  run-nightly
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "${AIWIKI_NIGHTLY_NO_SEMANTIC_LINT:-0}" == "1" ]]; then
  ARGS+=(--no-semantic-lint)
fi

exec "$LAUNCHER" "${ARGS[@]}"
