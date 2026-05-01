#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"
DETERMINISTIC_ONLY="${AIWIKI_NIGHTLY_DETERMINISTIC_ONLY:-0}"
NO_SEMANTIC_LINT="${AIWIKI_NIGHTLY_NO_SEMANTIC_LINT:-0}"
FALLBACK_ENABLED="${AIWIKI_NIGHTLY_FALLBACK_ENABLED:-1}"
FALLBACK_BACKEND="${AIWIKI_NIGHTLY_FALLBACK_BACKEND:-nvidia-nim-api}"
FALLBACK_MODEL="${AIWIKI_NIGHTLY_FALLBACK_MODEL:-openai/gpt-oss-120b}"
FALLBACK_ENV="${AIWIKI_NIGHTLY_FALLBACK_ENV:-$HOME/.aiwiki-secrets/nvidia.env}"
FALLBACK_MODEL_CHAIN="${AIWIKI_NIGHTLY_FALLBACK_MODEL_FALLBACK:-}"

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

fallback_enabled() {
  case "${FALLBACK_ENABLED,,}" in
    0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

load_fallback_env() {
  if [[ -f "$FALLBACK_ENV" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$FALLBACK_ENV"
    set +a
  fi
}

primary_matches_fallback() {
  local primary_backend="${AIWIKI_LLM_BACKEND:-}"
  local primary_model="${AIWIKI_LLM_MODEL:-}"
  [[ "$primary_backend" == "$FALLBACK_BACKEND" && ( -z "$primary_model" || "$primary_model" == "$FALLBACK_MODEL" ) ]]
}

run_fallback_nightly() {
  fallback_enabled || return 1
  if primary_matches_fallback; then
    log "fallback skipped because primary backend already matches $FALLBACK_BACKEND/$FALLBACK_MODEL"
    return 1
  fi

  load_fallback_env
  export AIWIKI_LLM_BACKEND="$FALLBACK_BACKEND"
  export AIWIKI_LLM_MODEL="$FALLBACK_MODEL"
  if [[ -n "$FALLBACK_MODEL_CHAIN" ]]; then
    export AIWIKI_MODEL_FALLBACK="$FALLBACK_MODEL_CHAIN"
  fi

  if ! llm_configured; then
    log "fallback $FALLBACK_BACKEND/$FALLBACK_MODEL is not configured; falling back to deterministic nightly"
    return 1
  fi

  ARGS=(--root "$TARGET_ROOT")
  append_run_nightly_args
  log "retrying nightly with fallback $FALLBACK_BACKEND/$FALLBACK_MODEL"
  python3 -m aiwiki.cli "${ARGS[@]}"
}

if [[ "$DETERMINISTIC_ONLY" == "1" ]]; then
  run_deterministic_nightly
else
  if llm_configured; then
    ARGS=(--root "$TARGET_ROOT")
    append_run_nightly_args
    if python3 -m aiwiki.cli "${ARGS[@]}"; then
      exit 0
    else
      primary_status=$?
      log "primary run-nightly failed with status $primary_status"
    fi
  else
    log "primary LLM backend is not configured"
  fi

  if run_fallback_nightly; then
    exit 0
  fi

  run_deterministic_nightly
fi
