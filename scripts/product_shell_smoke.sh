#!/usr/bin/env bash

set -euo pipefail

DEFAULT_ROOT="/home/tim/danlu/炼丹炉"
WITH_DROP_NOTE=0
ROOT=""
SMOKE_DEGRADED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-drop-note)
      WITH_DROP_NOTE=1
      shift
      ;;
    -*)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
    *)
      ROOT="$1"
      shift
      ;;
  esac
done

ROOT="${ROOT:-$DEFAULT_ROOT}"
LAUNCHER="$ROOT/scripts/aiwiki-launcher.sh"

if [[ ! -x "$LAUNCHER" ]]; then
  echo "launcher not executable: $LAUNCHER" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"
ASK_QUERY="Product Shell smoke ask ${STAMP}"
RUN_ASK_QUERY="Reply with one short sentence confirming Product Shell smoke ${STAMP}."
DROP_TITLE="Product Shell smoke ${STAMP}"
DROP_TEXT="Smoke note generated at ${STAMP} UTC."

run_json() {
  local label="$1"
  shift
  local payload
  local temp_json
  local temp_stdout
  local temp_stderr
  local status=0
  echo "[smoke] $label"
  temp_stdout="$(mktemp)"
  temp_stderr="$(mktemp)"
  if [[ "$label" == "run-ask" ]]; then
    set +e
    AIWIKI_LLM_TIMEOUT_SECONDS="${AIWIKI_LLM_TIMEOUT_SECONDS:-300}" "$LAUNCHER" "$@" >"$temp_stdout" 2>"$temp_stderr"
    status=$?
    set -e
  else
    set +e
    "$LAUNCHER" "$@" >"$temp_stdout" 2>"$temp_stderr"
    status=$?
    set -e
  fi
  if [[ "$status" -ne 0 ]]; then
    payload="$(cat "$temp_stdout")"
    if [[ "$label" == "run-ask" ]] && llm_backend_unavailable "$(cat "$temp_stderr")"$'\n'"$payload"; then
      SMOKE_DEGRADED=1
      echo "  run-ask backend unavailable; verified deterministic ask fallback instead"
      rm -f "$temp_stdout" "$temp_stderr"
      run_json "ask-fallback" ask "$RUN_ASK_QUERY" --format report
      return 0
    fi
    cat "$temp_stderr" >&2
    rm -f "$temp_stdout" "$temp_stderr"
    return "$status"
  fi
  payload="$(cat "$temp_stdout")"
  rm -f "$temp_stdout" "$temp_stderr"
  temp_json="$(mktemp)"
  printf '%s\n' "$payload" >"$temp_json"
  python3 - "$label" "$temp_json" <<'PY'
import json
import sys

label = sys.argv[1]
with open(sys.argv[2], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

if label == "shell-status":
    print(f"  active_protocol={payload.get('active_protocol', '')} summary_path={payload.get('summary_path', '')}")
elif label == "llm-check":
    print(f"  backend={payload.get('backend', '')} model={payload.get('effective_model', payload.get('model', ''))}")
else:
    path = payload.get("path") or payload.get("output_path") or payload.get("receipt_path") or ""
    print(f"  path={path}")
PY
  rm -f "$temp_json"
}

llm_backend_unavailable() {
  local message="$1"
  local normalized
  normalized="$(printf '%s' "$message" | tr '[:upper:]' '[:lower:]')"
  [[ "$normalized" == *"usage limit"* ]] \
    || [[ "$normalized" == *"no quota"* ]] \
    || [[ "$normalized" == *"timed out"* ]] \
    || [[ "$normalized" == *"login again"* ]] \
    || [[ "$normalized" == *"not have access to claude"* ]] \
    || [[ "$normalized" == *"authentication"* ]] \
    || [[ "$normalized" == *"upgrade to pro"* ]]
}

run_json "shell-status" shell-status
run_json "llm-check" llm-check
run_json "ask" ask "$ASK_QUERY" --format report
run_json "run-ask" run-ask "$RUN_ASK_QUERY" --format report

if [[ "$WITH_DROP_NOTE" == "1" ]]; then
  run_json "drop-note" drop-note --title "$DROP_TITLE" --text "$DROP_TEXT" --kind note
else
  echo "[smoke] drop-note skipped (pass --with-drop-note to include write-path validation)"
fi

if [[ "$SMOKE_DEGRADED" == "1" ]]; then
  echo "[smoke] Product Shell smoke passed for $ROOT (degraded: deterministic ask fallback verified)"
else
  echo "[smoke] Product Shell smoke passed for $ROOT"
fi
