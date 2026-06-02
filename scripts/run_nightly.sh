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
DETERMINISTIC_ONLY="${AIWIKI_NIGHTLY_DETERMINISTIC_ONLY:-0}"
REQUIRE_LLM="${AIWIKI_NIGHTLY_REQUIRE_LLM:-0}"
NO_SEMANTIC_LINT="${AIWIKI_NIGHTLY_NO_SEMANTIC_LINT:-0}"

log() {
  printf '[aiwiki-nightly] %s\n' "$*" >&2
}

llm_configured() {
  python3 - <<'PY'
from aiwiki.config import LLMConfig
import sys

status = LLMConfig.status_from_env()
sys.exit(0 if status.get("configured") else 1)
PY
}

append_run_nightly_args() {
  ARGS+=(run-nightly --compile-limit "$COMPILE_LIMIT")
  if [[ "$NO_SEMANTIC_LINT" == "1" ]]; then
    ARGS+=(--no-semantic-lint)
  fi
}

run_deterministic_nightly() {
  ARGS=(--root "$TARGET_ROOT" nightly)
  log "running deterministic nightly"
  exec python3 -m aiwiki.cli "${ARGS[@]}"
}

require_llm() {
  case "$REQUIRE_LLM" in
    1|true|True|TRUE|yes|Yes|YES|on|On|ON) return 0 ;;
    *) return 1 ;;
  esac
}

if [[ "$DETERMINISTIC_ONLY" == "1" ]]; then
  run_deterministic_nightly
else
  llm_attempted=0
  llm_failure_status=2
  if llm_configured; then
    llm_attempted=1
    ARGS=(--root "$TARGET_ROOT")
    append_run_nightly_args
    if python3 -m aiwiki.cli "${ARGS[@]}"; then
      exit 0
    else
      primary_status=$?
      llm_failure_status="$primary_status"
      log "primary run-nightly failed with status $primary_status"
    fi
  else
    log "primary LLM backend is not configured"
  fi

  if [[ "$llm_attempted" == "1" ]]; then
    log "deterministic nightly fallback suppressed after run-nightly failure"
    exit "$llm_failure_status"
  fi

  if require_llm; then
    log "deterministic nightly fallback disabled by AIWIKI_NIGHTLY_REQUIRE_LLM=1"
    exit "$llm_failure_status"
  fi

  run_deterministic_nightly
fi
