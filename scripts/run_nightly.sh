#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="${PYTHONPATH:-$PROJECT_ROOT/src}"

COMPILE_LIMIT="${AIWIKI_NIGHTLY_COMPILE_LIMIT:-5}"
DETERMINISTIC_ONLY="${AIWIKI_NIGHTLY_DETERMINISTIC_ONLY:-0}"
NO_SEMANTIC_LINT="${AIWIKI_NIGHTLY_NO_SEMANTIC_LINT:-0}"

if [[ "$DETERMINISTIC_ONLY" == "1" ]]; then
  ARGS=(--root "$PROJECT_ROOT" nightly)
else
  if python3 - <<'PY'
from aiwiki.config import LLMConfig
import sys

status = LLMConfig.status_from_env()
sys.exit(0 if status.get("configured") else 1)
PY
  then
    ARGS=(--root "$PROJECT_ROOT" run-nightly --compile-limit "$COMPILE_LIMIT")
    if [[ "$NO_SEMANTIC_LINT" == "1" ]]; then
      ARGS+=(--no-semantic-lint)
    fi
  else
    ARGS=(--root "$PROJECT_ROOT" nightly)
  fi
fi

exec python3 -m aiwiki.cli "${ARGS[@]}"
