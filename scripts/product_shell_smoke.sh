#!/usr/bin/env bash

set -euo pipefail

DEFAULT_ROOT="${AIWIKI_DOGFOOD_VAULT:-}"
WITH_NOTE_WRITE=0
ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-note-write)
      WITH_NOTE_WRITE=1
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

if [[ -z "$ROOT" ]]; then
  echo "error: vault root is required (set AIWIKI_DOGFOOD_VAULT or pass path as argument)" >&2
  exit 1
fi

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
      echo "  run-ask backend unavailable; smoke failed without deterministic fallback" >&2
      cat "$temp_stderr" >&2
      rm -f "$temp_stdout" "$temp_stderr"
      return "$status"
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
    path = (
        payload.get("path")
        or payload.get("output_path")
        or payload.get("report_path")
        or payload.get("note_path")
        or payload.get("stored_path")
        or payload.get("asset_path")
        or payload.get("receipt_path")
        or ""
    )
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
    || [[ "$normalized" == *"upgrade to pro"* ]] \
    || [[ "$normalized" == *"llm backend resolution failed"* ]]
}

run_json "shell-status" advanced shell-status
run_json "llm-check" advanced llm-check
run_json "ask" advanced ask "$ASK_QUERY" --format report
run_json "run-ask" advanced run-ask "$RUN_ASK_QUERY" --format report

if [[ "$WITH_NOTE_WRITE" == "1" ]]; then
  run_json "drop markdown" drop markdown --title "$DROP_TITLE" --text "$DROP_TEXT" --kind note
else
  echo "[smoke] drop markdown skipped (pass --with-note-write to include write-path validation)"
fi

echo "[smoke] Product Shell smoke passed for $ROOT"
