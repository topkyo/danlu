#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/json_helpers.sh"

ARTIFACTS_ONLY=0
REQUIRE_CONTRACT=0
CHECK_CALIBRATION_REPORT=0
JSON_OUTPUT=0
HARNESS_DIR="${HARNESS_DIR:-.claude}"
declare -a ALLOW_ACTIONS=("none")
declare -a ALLOW_QA_REVIEW_RECOMMENDATIONS=("KEEP current qa-review requirement" "KEEP qa-review required" "INSUFFICIENT DATA")
declare -a ALLOW_CONTRACT_RECOMMENDATIONS=("KEEP standalone contract" "INSUFFICIENT DATA")
declare -a ALLOW_PROGRESS_RECOMMENDATIONS=("KEEP normal PROGRESS.md usage" "INSUFFICIENT DATA")

CLOSED_LOOP_JSON="null"
RECOMMENDED_ACTION=""
NOTE_STATUS=""
QA_REVIEW_REQUIREMENT=""
CALIBRATION_REPORT_AVAILABLE=""
CALIBRATION_QA_REVIEW_RECOMMENDATION=""
CALIBRATION_CONTRACT_RECOMMENDATION=""
CALIBRATION_PROGRESS_RECOMMENDATION=""
POLICY_ERROR=""
declare -a VIOLATION_FIELDS=()
declare -a VIOLATION_VALUES=()
declare -a REMEDIATIONS=()
SCHEMA_VERSION=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/enforce_closed_loop_policy.sh [options]

Options:
  --artifacts-only
  --require-contract
  --check-calibration-report
  --json
  --allow-action <none|backfill-structured-note|normalize-legacy-note|review-stale-note>
  --allow-qa-review-recommendation <value>
  --allow-contract-recommendation <value>
  --allow-progress-recommendation <value>
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

value_is_allowed() {
  local candidate="$1"
  local allowlist_name="$2"
  local allowed=""
  local -n allowlist_ref="$allowlist_name"

  for allowed in "${allowlist_ref[@]}"; do
    if [[ "$candidate" == "$allowed" ]]; then
      return 0
    fi
  done

  return 1
}

add_violation() {
  local field="$1"
  local value="$2"

  VIOLATION_FIELDS+=("$field")
  VIOLATION_VALUES+=("$value")
}

add_remediation() {
  REMEDIATIONS+=("$1")
}

format_violation_summary() {
  local summary=""
  local i=""

  for i in "${!VIOLATION_FIELDS[@]}"; do
    if [[ -n "$summary" ]]; then
      summary="$summary "
    fi
    summary+="${VIOLATION_FIELDS[i]}=${VIOLATION_VALUES[i]}"
  done

  printf '%s' "$summary"
}

emit_json_violations() {
  local i=""

  if [[ "${#VIOLATION_FIELDS[@]}" -eq 0 ]]; then
    printf '[]'
    return
  fi

  printf '[\n'
  for i in "${!VIOLATION_FIELDS[@]}"; do
    printf '    {"field": %s, "value": %s}' \
      "$(harness_emit_json_string "${VIOLATION_FIELDS[i]}")" \
      "$(harness_emit_json_string "${VIOLATION_VALUES[i]}")"
    if [[ "$i" -lt $((${#VIOLATION_FIELDS[@]} - 1)) ]]; then
      printf ','
    fi
    printf '\n'
  done
  printf '  ]'
}

emit_json_string_array() {
  local array_name="$1"
  local -n array_ref="$array_name"
  local i=""

  if [[ "${#array_ref[@]}" -eq 0 ]]; then
    printf '[]'
    return
  fi

  printf '[\n'
  for i in "${!array_ref[@]}"; do
    printf '    %s' "$(harness_emit_json_string "${array_ref[i]}")"
    if [[ "$i" -lt $((${#array_ref[@]} - 1)) ]]; then
      printf ','
    fi
    printf '\n'
  done
  printf '  ]'
}

emit_json_result() {
  local status="$1"
  local policy_passed=0

  if [[ "$status" == "pass" ]]; then
    policy_passed=1
  fi

  printf '{\n'
  printf '  "schema_version": %s,\n' "$(harness_emit_json_string "closed-loop-policy-v1")"
  printf '  "status": %s,\n' "$(harness_emit_json_string "$status")"
  printf '  "policy_passed": %s,\n' "$(harness_emit_json_boolean "$policy_passed")"
  printf '  "error_message": %s,\n' "$(harness_emit_json_string_or_null "$POLICY_ERROR")"
  printf '  "artifacts_only": %s,\n' "$(harness_emit_json_boolean "$ARTIFACTS_ONLY")"
  printf '  "require_contract": %s,\n' "$(harness_emit_json_boolean "$REQUIRE_CONTRACT")"
  printf '  "check_calibration_report": %s,\n' "$(harness_emit_json_boolean "$CHECK_CALIBRATION_REPORT")"
  printf '  "policy_state": {\n'
  printf '    "recommended_action": %s,\n' "$(harness_emit_json_string_or_null "$RECOMMENDED_ACTION")"
  printf '    "note_status": %s,\n' "$(harness_emit_json_string_or_null "$NOTE_STATUS")"
  printf '    "qa_review_requirement": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_REQUIREMENT")"
  printf '    "calibration_report_available": %s,\n' "$(harness_emit_json_string_or_null "$CALIBRATION_REPORT_AVAILABLE")"
  printf '    "qa_review_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$CALIBRATION_QA_REVIEW_RECOMMENDATION")"
  printf '    "contract_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$CALIBRATION_CONTRACT_RECOMMENDATION")"
  printf '    "progress_recommendation": %s\n' "$(harness_emit_json_string_or_null "$CALIBRATION_PROGRESS_RECOMMENDATION")"
  printf '  },\n'
  printf '  "violations": %s,\n' "$(emit_json_violations)"
  printf '  "remediations": %s,\n' "$(emit_json_string_array REMEDIATIONS)"
  printf '  "closed_loop": %s\n' "$CLOSED_LOOP_JSON"
  printf '}\n'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifacts-only)
      ARTIFACTS_ONLY=1
      shift
      ;;
    --require-contract)
      REQUIRE_CONTRACT=1
      shift
      ;;
    --check-calibration-report)
      CHECK_CALIBRATION_REPORT=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    --allow-action)
      require_value "$1" "${2:-}"
      ALLOW_ACTIONS+=("$2")
      shift 2
      ;;
    --allow-qa-review-recommendation)
      require_value "$1" "${2:-}"
      ALLOW_QA_REVIEW_RECOMMENDATIONS+=("$2")
      shift 2
      ;;
    --allow-contract-recommendation)
      require_value "$1" "${2:-}"
      ALLOW_CONTRACT_RECOMMENDATIONS+=("$2")
      shift 2
      ;;
    --allow-progress-recommendation)
      require_value "$1" "${2:-}"
      ALLOW_PROGRESS_RECOMMENDATIONS+=("$2")
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

declare -a CLOSED_LOOP_ARGS=("--json")
if [[ "$ARTIFACTS_ONLY" -eq 1 ]]; then
  CLOSED_LOOP_ARGS+=("--artifacts-only")
fi
if [[ "$REQUIRE_CONTRACT" -eq 1 ]]; then
  CLOSED_LOOP_ARGS+=("--require-contract")
fi

STDERR_FILE="$(mktemp)"
trap 'rm -f "$STDERR_FILE"' EXIT

if ! CLOSED_LOOP_JSON="$(
  HARNESS_DIR="$HARNESS_DIR" bash "$SCRIPT_DIR/closed_loop.sh" "${CLOSED_LOOP_ARGS[@]}" 2>"$STDERR_FILE"
)"; then
  if [[ -s "$STDERR_FILE" ]]; then
    cat "$STDERR_FILE" >&2
  fi
  POLICY_ERROR="closed_loop.sh failed while collecting policy state"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    emit_json_result "error"
    exit 1
  fi
  fail "$POLICY_ERROR"
fi

if [[ -s "$STDERR_FILE" ]]; then
  cat "$STDERR_FILE" >&2
fi

SCHEMA_VERSION="$(harness_extract_top_level_json_string "schema_version" "$CLOSED_LOOP_JSON")"
[[ "$SCHEMA_VERSION" == "closed-loop-v1" ]] || POLICY_ERROR="closed_loop.sh JSON schema_version is '${SCHEMA_VERSION:-missing}' (expected closed-loop-v1)"
if [[ -n "$POLICY_ERROR" ]]; then
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    emit_json_result "error"
    exit 1
  fi
  fail "$POLICY_ERROR"
fi

RECOMMENDED_ACTION="$(harness_extract_top_level_json_string "compat_policy_recommended_action" "$CLOSED_LOOP_JSON")"
NOTE_STATUS="$(harness_extract_top_level_json_string "compat_policy_note_status" "$CLOSED_LOOP_JSON")"
QA_REVIEW_REQUIREMENT="$(harness_extract_top_level_json_string "compat_policy_qa_review_requirement" "$CLOSED_LOOP_JSON")"
CALIBRATION_REPORT_AVAILABLE="$(harness_extract_top_level_json_literal "compat_calibration_report_available" "$CLOSED_LOOP_JSON")"
CALIBRATION_QA_REVIEW_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_calibration_qa_review_recommendation" "$CLOSED_LOOP_JSON")"
CALIBRATION_CONTRACT_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_calibration_contract_recommendation" "$CLOSED_LOOP_JSON")"
CALIBRATION_PROGRESS_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_calibration_progress_recommendation" "$CLOSED_LOOP_JSON")"

if [[ -z "$RECOMMENDED_ACTION" ]]; then
  POLICY_ERROR="closed_loop.sh JSON did not include compat_policy_recommended_action"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    emit_json_result "error"
    exit 1
  fi
  fail "$POLICY_ERROR"
fi

if ! value_is_allowed "$RECOMMENDED_ACTION" "ALLOW_ACTIONS"; then
  add_violation "recommended_action" "$RECOMMENDED_ACTION"
  case "$RECOMMENDED_ACTION" in
    backfill-structured-note|normalize-legacy-note)
      add_remediation "Run HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --apply"
      add_remediation "Allow this action explicitly with: bash scripts/enforce_closed_loop_policy.sh --allow-action $RECOMMENDED_ACTION"
      ;;
    review-stale-note)
      add_remediation "Review $HARNESS_DIR/contracts/active.md and decide whether to remove the stale calibration_note or intentionally downgrade qa-review again."
      add_remediation "Allow this action explicitly with: bash scripts/enforce_closed_loop_policy.sh --allow-action $RECOMMENDED_ACTION"
      ;;
  esac
fi

if [[ "$CHECK_CALIBRATION_REPORT" -eq 1 ]]; then
  if [[ "$CALIBRATION_REPORT_AVAILABLE" != "true" ]]; then
    add_violation "calibration.report" "unavailable"
    add_remediation "Ensure $HARNESS_DIR calibration scaffolding is present and that closed_loop.sh can read calibration_report.sh --json."
  else
    if [[ -z "$CALIBRATION_QA_REVIEW_RECOMMENDATION" ]]; then
      POLICY_ERROR="closed_loop.sh JSON did not include compat_calibration_qa_review_recommendation"
      if [[ "$JSON_OUTPUT" -eq 1 ]]; then
        emit_json_result "error"
        exit 1
      fi
      fail "$POLICY_ERROR"
    fi
    if [[ -z "$CALIBRATION_CONTRACT_RECOMMENDATION" ]]; then
      POLICY_ERROR="closed_loop.sh JSON did not include compat_calibration_contract_recommendation"
      if [[ "$JSON_OUTPUT" -eq 1 ]]; then
        emit_json_result "error"
        exit 1
      fi
      fail "$POLICY_ERROR"
    fi
    if [[ -z "$CALIBRATION_PROGRESS_RECOMMENDATION" ]]; then
      POLICY_ERROR="closed_loop.sh JSON did not include compat_calibration_progress_recommendation"
      if [[ "$JSON_OUTPUT" -eq 1 ]]; then
        emit_json_result "error"
        exit 1
      fi
      fail "$POLICY_ERROR"
    fi

    if ! value_is_allowed "$CALIBRATION_QA_REVIEW_RECOMMENDATION" "ALLOW_QA_REVIEW_RECOMMENDATIONS"; then
      add_violation "qa_review_recommendation" "$CALIBRATION_QA_REVIEW_RECOMMENDATION"
      add_remediation "Review HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --dry-run and decide whether to keep or apply the qa-review downgrade recommendation."
      add_remediation "Allow this recommendation explicitly with: bash scripts/enforce_closed_loop_policy.sh --check-calibration-report --allow-qa-review-recommendation \"$CALIBRATION_QA_REVIEW_RECOMMENDATION\""
    fi

    if ! value_is_allowed "$CALIBRATION_CONTRACT_RECOMMENDATION" "ALLOW_CONTRACT_RECOMMENDATIONS"; then
      add_violation "contract_recommendation" "$CALIBRATION_CONTRACT_RECOMMENDATION"
      add_remediation "Review HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --dry-run and decide whether future low-risk work should inline scope into PROGRESS.md."
      add_remediation "Allow this recommendation explicitly with: bash scripts/enforce_closed_loop_policy.sh --check-calibration-report --allow-contract-recommendation \"$CALIBRATION_CONTRACT_RECOMMENDATION\""
    fi

    if ! value_is_allowed "$CALIBRATION_PROGRESS_RECOMMENDATION" "ALLOW_PROGRESS_RECOMMENDATIONS"; then
      add_violation "progress_recommendation" "$CALIBRATION_PROGRESS_RECOMMENDATION"
      add_remediation "Review HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --dry-run and decide whether PROGRESS.md should be treated as blockers-only."
      add_remediation "Allow this recommendation explicitly with: bash scripts/enforce_closed_loop_policy.sh --check-calibration-report --allow-progress-recommendation \"$CALIBRATION_PROGRESS_RECOMMENDATION\""
    fi
  fi
fi

if [[ "${#VIOLATION_FIELDS[@]}" -eq 0 ]]; then
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    emit_json_result "pass"
  elif [[ "$CHECK_CALIBRATION_REPORT" -eq 1 ]]; then
    echo "[PASS] closed-loop policy OK (recommended_action=$RECOMMENDED_ACTION, note_status=${NOTE_STATUS:-unknown}, qa_review_requirement=${QA_REVIEW_REQUIREMENT:-unknown}, qa_review_recommendation=${CALIBRATION_QA_REVIEW_RECOMMENDATION:-n/a}, contract_recommendation=${CALIBRATION_CONTRACT_RECOMMENDATION:-n/a}, progress_recommendation=${CALIBRATION_PROGRESS_RECOMMENDATION:-n/a})"
  else
    echo "[PASS] closed-loop policy OK (recommended_action=$RECOMMENDED_ACTION, note_status=${NOTE_STATUS:-unknown}, qa_review_requirement=${QA_REVIEW_REQUIREMENT:-unknown})"
  fi
  exit 0
fi

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  emit_json_result "fail"
  exit 1
fi

echo "[FAIL] closed-loop policy requires follow-up ($(format_violation_summary))" >&2
for remediation in "${REMEDIATIONS[@]}"; do
  echo "$remediation" >&2
done
exit 1
