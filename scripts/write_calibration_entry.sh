#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/calibration.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/contract_artifacts.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/gate_artifacts.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CALIBRATION_FILE="$(harness_default_calibration_file "$HARNESS_DIR")"
CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
ENTRY_DATE="$(date +%F)"
AGENT_NAME="$(harness_default_calibration_agent "$HARNESS_DIR")"
TASK=""
FROM_CURRENT_GATES=0
QA_REVIEW_MODE="not-run"
QA_REVIEW_MODE_EXPLICIT=0
QA_REVIEW_HIT="0"
QA_REVIEW_MISS="0"
QA_REVIEW_FALSE_POSITIVE="0"
QA_RUNTIME_MODE="not-run"
QA_RUNTIME_MODE_EXPLICIT=0
QA_RUNTIME_HIT="0"
QA_RUNTIME_MISS="0"
QA_RUNTIME_FALSE_POSITIVE="0"
CONTRACT_SCOPE_CHANGED="not-applicable"
NEW_SESSION="yes"
PROGRESS_READ="not-applicable"
NOTES=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/write_calibration_entry.sh --task <text> [options]

Options:
  --date <YYYY-MM-DD>
  --agent <name>
  --file <path>
  --from-current-gates
  --qa-review-mode <isolated-agent|external-agent|fresh-session|same-context|human|not-run>
  --qa-review-hit <count>
  --qa-review-miss <count>
  --qa-review-false-positive <count>
  --qa-runtime-mode <scripted|isolated-agent|same-context|human|not-run>
  --qa-runtime-hit <count>
  --qa-runtime-miss <count>
  --qa-runtime-false-positive <count>
  --contract-scope-changed <yes|no|not-applicable>
  --new-session <yes|no>
  --progress-read <yes|no|not-applicable>
  --notes <text>
EOF
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || fail "Missing value for $flag"
}

require_counter() {
  local flag="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$flag must be a non-negative integer"
}

derive_mode_from_gate_artifact() {
  local gate_name="$1"
  local path="$2"
  local status=""
  local mode=""
  local header_name=""

  [[ -f "$path" ]] || {
    printf '%s\n' "not-run"
    return 0
  }

  status="$(harness_extract_artifact_status "$path")"
  [[ -n "$status" ]] || fail "$gate_name artifact missing status: $path"

  case "$gate_name" in
    qa-review)
      header_name="reviewer_mode"
      ;;
    qa-runtime)
      header_name="runtime_mode"
      ;;
    *)
      fail "Unknown gate name: $gate_name"
      ;;
  esac

  case "$status" in
    not-required)
      printf '%s\n' "not-run"
      return 0
      ;;
    pass)
      mode="$(harness_extract_gate_execution_mode "$gate_name" "$path")"
      [[ -n "$mode" ]] || fail "$gate_name artifact missing $header_name: $path"
      harness_validate_gate_execution_mode "$gate_name" "$mode" || fail "$gate_name artifact $header_name is '$mode': $path"
      printf '%s\n' "$mode"
      return 0
      ;;
    fail|blocked)
      mode="$(harness_extract_gate_execution_mode "$gate_name" "$path")"
      [[ -n "$mode" ]] || fail "$gate_name artifact status is $status but $header_name is missing; add the optional header or pass --$gate_name-mode manually"
      harness_validate_gate_execution_mode "$gate_name" "$mode" || fail "$gate_name artifact $header_name is '$mode': $path"
      printf '%s\n' "$mode"
      return 0
      ;;
    *)
      fail "$gate_name artifact has unsupported status '$status': $path"
      ;;
  esac
}

populate_modes_from_current_gates() {
  local qa_review_artifact=""
  local qa_runtime_artifact=""

  [[ -f "$CONTRACT_FILE" ]] || fail "Missing contract for --from-current-gates: $CONTRACT_FILE"

  qa_review_artifact="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-review")"
  [[ -n "$qa_review_artifact" ]] || fail "Contract missing qa-review artifact path"

  qa_runtime_artifact="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-runtime")"
  [[ -n "$qa_runtime_artifact" ]] || fail "Contract missing qa-runtime artifact path"

  if [[ "$QA_REVIEW_MODE_EXPLICIT" -eq 0 ]]; then
    QA_REVIEW_MODE="$(derive_mode_from_gate_artifact "qa-review" "$qa_review_artifact")"
  fi

  if [[ "$QA_RUNTIME_MODE_EXPLICIT" -eq 0 ]]; then
    QA_RUNTIME_MODE="$(derive_mode_from_gate_artifact "qa-runtime" "$qa_runtime_artifact")"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      require_value "$1" "${2:-}"
      TASK="$2"
      shift 2
      ;;
    --date)
      require_value "$1" "${2:-}"
      ENTRY_DATE="$2"
      shift 2
      ;;
    --agent)
      require_value "$1" "${2:-}"
      AGENT_NAME="$2"
      shift 2
      ;;
    --file)
      require_value "$1" "${2:-}"
      CALIBRATION_FILE="$2"
      shift 2
      ;;
    --from-current-gates)
      FROM_CURRENT_GATES=1
      shift
      ;;
    --qa-review-mode)
      require_value "$1" "${2:-}"
      QA_REVIEW_MODE="$2"
      QA_REVIEW_MODE_EXPLICIT=1
      shift 2
      ;;
    --qa-review-hit)
      require_value "$1" "${2:-}"
      QA_REVIEW_HIT="$2"
      shift 2
      ;;
    --qa-review-miss)
      require_value "$1" "${2:-}"
      QA_REVIEW_MISS="$2"
      shift 2
      ;;
    --qa-review-false-positive)
      require_value "$1" "${2:-}"
      QA_REVIEW_FALSE_POSITIVE="$2"
      shift 2
      ;;
    --qa-runtime-mode)
      require_value "$1" "${2:-}"
      QA_RUNTIME_MODE="$2"
      QA_RUNTIME_MODE_EXPLICIT=1
      shift 2
      ;;
    --qa-runtime-hit)
      require_value "$1" "${2:-}"
      QA_RUNTIME_HIT="$2"
      shift 2
      ;;
    --qa-runtime-miss)
      require_value "$1" "${2:-}"
      QA_RUNTIME_MISS="$2"
      shift 2
      ;;
    --qa-runtime-false-positive)
      require_value "$1" "${2:-}"
      QA_RUNTIME_FALSE_POSITIVE="$2"
      shift 2
      ;;
    --contract-scope-changed)
      require_value "$1" "${2:-}"
      CONTRACT_SCOPE_CHANGED="$2"
      shift 2
      ;;
    --new-session)
      require_value "$1" "${2:-}"
      NEW_SESSION="$2"
      shift 2
      ;;
    --progress-read)
      require_value "$1" "${2:-}"
      PROGRESS_READ="$2"
      shift 2
      ;;
    --notes)
      require_value "$1" "${2:-}"
      NOTES="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$TASK" ]] || {
  usage >&2
  fail "Missing --task"
}
if [[ "$FROM_CURRENT_GATES" -eq 1 ]]; then
  populate_modes_from_current_gates
fi
[[ "$QA_REVIEW_MODE" =~ ^(isolated-agent|external-agent|fresh-session|same-context|human|not-run)$ ]] || fail "Invalid --qa-review-mode: $QA_REVIEW_MODE"
[[ "$QA_RUNTIME_MODE" =~ ^(scripted|isolated-agent|same-context|human|not-run)$ ]] || fail "Invalid --qa-runtime-mode: $QA_RUNTIME_MODE"
require_counter "--qa-review-hit" "$QA_REVIEW_HIT"
require_counter "--qa-review-miss" "$QA_REVIEW_MISS"
require_counter "--qa-review-false-positive" "$QA_REVIEW_FALSE_POSITIVE"
require_counter "--qa-runtime-hit" "$QA_RUNTIME_HIT"
require_counter "--qa-runtime-miss" "$QA_RUNTIME_MISS"
require_counter "--qa-runtime-false-positive" "$QA_RUNTIME_FALSE_POSITIVE"
[[ -n "$(harness_normalize_calibration_boolean "$CONTRACT_SCOPE_CHANGED")" ]] || fail "Invalid --contract-scope-changed: $CONTRACT_SCOPE_CHANGED"
[[ "$(harness_normalize_calibration_boolean "$NEW_SESSION")" =~ ^(yes|no)$ ]] || fail "Invalid --new-session: $NEW_SESSION"
[[ -n "$(harness_normalize_calibration_boolean "$PROGRESS_READ")" ]] || fail "Invalid --progress-read: $PROGRESS_READ"

mkdir -p "$(dirname "$CALIBRATION_FILE")"

if [[ ! -f "$CALIBRATION_FILE" ]]; then
  {
    printf '# %s QA Calibration Log\n\n' "$AGENT_NAME"
    printf 'Generated by scripts/write_calibration_entry.sh.\n'
    printf 'Use scripts/calibration_report.sh to review downgrade recommendations.\n'
  } > "$CALIBRATION_FILE"
fi

{
  printf '\n'
  printf -- '- Date: %s\n' "$ENTRY_DATE"
  printf -- '- Agent: %s\n' "$AGENT_NAME"
  printf -- '- Task: %s\n' "$TASK"
  printf -- '- qa-review Mode: %s\n' "$QA_REVIEW_MODE"
  printf -- '- qa-review Hit: %s\n' "$QA_REVIEW_HIT"
  printf -- '- qa-review Miss: %s\n' "$QA_REVIEW_MISS"
  printf -- '- qa-review False Positive: %s\n' "$QA_REVIEW_FALSE_POSITIVE"
  printf -- '- qa-runtime Mode: %s\n' "$QA_RUNTIME_MODE"
  printf -- '- qa-runtime Hit: %s\n' "$QA_RUNTIME_HIT"
  printf -- '- qa-runtime Miss: %s\n' "$QA_RUNTIME_MISS"
  printf -- '- qa-runtime False Positive: %s\n' "$QA_RUNTIME_FALSE_POSITIVE"
  printf -- '- Contract Scope Changed: %s\n' "$CONTRACT_SCOPE_CHANGED"
  printf -- '- New Session: %s\n' "$NEW_SESSION"
  printf -- '- PROGRESS Read: %s\n' "$PROGRESS_READ"
  printf -- '- Notes: %s\n' "${NOTES:-n/a}"
} >> "$CALIBRATION_FILE"

echo "[OK] Appended calibration entry to $CALIBRATION_FILE"
