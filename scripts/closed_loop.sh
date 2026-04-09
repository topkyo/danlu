#!/usr/bin/env bash
set -euo pipefail

ARTIFACTS_ONLY=0
REQUIRE_CONTRACT=0
JSON_OUTPUT=0

for arg in "$@"; do
  case "$arg" in
    --artifacts-only)
      ARTIFACTS_ONLY=1
      ;;
    --require-contract)
      REQUIRE_CONTRACT=1
      ;;
    --json)
      JSON_OUTPUT=1
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--artifacts-only] [--require-contract] [--json]" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/worktree_fingerprint.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/contract_artifacts.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/gate_artifacts.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/calibration.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/json_helpers.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
PROGRESS_FILE="$PROJECT_ROOT/PROGRESS.md"
QA_REVIEW_FILE=""
QA_RUNTIME_FILE=""
CONTRACT_SHA=""
WORKTREE_FINGERPRINT=""
EXECUTION_MODE=""
ASK_POLICY=""
MAX_DEBUG_ROUNDS=""
QA_REVIEW_REQUIREMENT=""
QA_RUNTIME_REQUIREMENT=""
QA_REVIEW_NOTE_STATUS="missing"
QA_REVIEW_NOTE_KIND=""
QA_REVIEW_NOTE_ACTION=""
QA_REVIEW_NOTE_TARGET=""
QA_REVIEW_NOTE_SOURCE=""
QA_REVIEW_NOTE_DATE=""
QA_REVIEW_NOTE_BASIS=""
QA_REVIEW_CALIBRATION_ACTION="none"
QA_REVIEW_ARTIFACT_PRESENT=0
QA_REVIEW_ARTIFACT_STATUS=""
QA_REVIEW_ARTIFACT_MODE=""
QA_REVIEW_ARTIFACT_FINDINGS_COUNT=""
QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY=""
QA_REVIEW_FINDINGS_THRESHOLD_READY=0
QA_REVIEW_RECOMMENDED_MAX_FINDINGS=""
QA_REVIEW_FINDINGS_THRESHOLD_DETAIL=""
QA_REVIEW_SEVERITY_THRESHOLD_READY=0
QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY=""
QA_REVIEW_SEVERITY_THRESHOLD_DETAIL=""

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

emit_log() {
  local message="$1"

  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    echo "$message" >&2
  else
    echo "$message"
  fi
}

pass() {
  emit_log "[PASS] $1"
}

info() {
  emit_log "[INFO] $1"
}

warn() {
  emit_log "[WARN] $1"
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Missing required file: $path"
}

check_contract_execution_policy() {
  local emit_guidance="${1:-1}"
  local execution_mode=""
  local ask_policy=""
  local max_debug_rounds=""

  if [[ ! -f "$CONTRACT_FILE" ]]; then
    if [[ "$REQUIRE_CONTRACT" -eq 1 ]]; then
      fail "Missing required contract: $CONTRACT_FILE"
    fi
    info "No contract found at $CONTRACT_FILE; skipping contract-driven gate checks"
    return 1
  fi

  harness_contract_has_section "$CONTRACT_FILE" "Execution Policy" || fail "Contract missing Execution Policy"
  harness_contract_has_section "$CONTRACT_FILE" "Stop Conditions" || fail "Contract missing Stop Conditions"
  harness_contract_has_section "$CONTRACT_FILE" "Gate Requirements" || fail "Contract missing Gate Requirements"
  harness_contract_has_section "$CONTRACT_FILE" "Gate Artifacts" || fail "Contract missing Gate Artifacts"
  harness_contract_section_has_list_items "$CONTRACT_FILE" "Stop Conditions" || fail "Contract Stop Conditions must include at least one list item"
  [[ "$(harness_extract_contract_requirement "$CONTRACT_FILE" "verify")" == "required" ]] || fail "Contract missing verify requirement"

  execution_mode="$(harness_extract_contract_section_value "$CONTRACT_FILE" "Execution Policy" "execution_mode")"
  [[ -n "$execution_mode" ]] || fail "Contract missing execution_mode in Execution Policy"
  ask_policy="$(harness_extract_contract_section_value "$CONTRACT_FILE" "Execution Policy" "ask_policy")"
  [[ -n "$ask_policy" ]] || fail "Contract missing ask_policy in Execution Policy"
  max_debug_rounds="$(harness_extract_contract_section_value "$CONTRACT_FILE" "Execution Policy" "max_debug_rounds")"
  [[ "$max_debug_rounds" =~ ^[1-9][0-9]*$ ]] || fail "Contract max_debug_rounds must be a positive integer"

  if [[ "$emit_guidance" -eq 1 ]]; then
    if [[ "$execution_mode" != "autonomous-closed-loop" ]]; then
      warn "execution_mode is '$execution_mode' (runner is optimized for autonomous-closed-loop)"
    fi
    if [[ "$ask_policy" != "blockers-only" ]]; then
      warn "ask_policy is '$ask_policy' (runner is optimized for blockers-only)"
    fi
  fi

  QA_REVIEW_FILE="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-review")"
  [[ -n "$QA_REVIEW_FILE" ]] || fail "Contract missing qa-review artifact path"
  harness_is_valid_gate_artifact_path "$HARNESS_DIR" "$QA_REVIEW_FILE" || fail "qa-review artifact path must stay under $HARNESS_DIR/gates/: $QA_REVIEW_FILE"

  QA_RUNTIME_FILE="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-runtime")"
  [[ -n "$QA_RUNTIME_FILE" ]] || fail "Contract missing qa-runtime artifact path"
  harness_is_valid_gate_artifact_path "$HARNESS_DIR" "$QA_RUNTIME_FILE" || fail "qa-runtime artifact path must stay under $HARNESS_DIR/gates/: $QA_RUNTIME_FILE"

  EXECUTION_MODE="$execution_mode"
  ASK_POLICY="$ask_policy"
  MAX_DEBUG_ROUNDS="$max_debug_rounds"
  return 0
}

refresh_contract_snapshot() {
  require_file "$CONTRACT_FILE"
  CONTRACT_SHA="$(sha256sum "$CONTRACT_FILE" | awk '{print $1}')"
  WORKTREE_FINGERPRINT="$(harness_compute_project_fingerprint "$PROJECT_ROOT" "$HARNESS_DIR")"
}

run_verify() {
  local verify_script="scripts/verify.sh"
  [[ -f "$verify_script" ]] || fail "Missing $verify_script — create it with your project's linter/formatter/type-check commands"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    bash "$verify_script" >&2
  else
    bash "$verify_script"
  fi

  if harness_is_git_worktree "$PROJECT_ROOT"; then
    git diff --check -- . >/dev/null || fail "git diff --check reported whitespace or conflict marker issues"
  fi
  bash -n scripts/lib/contract_artifacts.sh || fail "scripts/lib/contract_artifacts.sh has shell syntax errors"
  bash -n scripts/lib/gate_artifacts.sh || fail "scripts/lib/gate_artifacts.sh has shell syntax errors"
  bash -n scripts/lib/worktree_fingerprint.sh || fail "scripts/lib/worktree_fingerprint.sh has shell syntax errors"
  if [[ -f scripts/lib/calibration.sh ]]; then
    bash -n scripts/lib/calibration.sh || fail "scripts/lib/calibration.sh has shell syntax errors"
  fi
  if [[ -f scripts/lib/json_helpers.sh ]]; then
    bash -n scripts/lib/json_helpers.sh || fail "scripts/lib/json_helpers.sh has shell syntax errors"
  fi
  if [[ -f scripts/calibration_report.sh ]]; then
    bash -n scripts/calibration_report.sh || fail "scripts/calibration_report.sh has shell syntax errors"
  fi
  if [[ -f scripts/launch_qa_review.sh ]]; then
    bash -n scripts/launch_qa_review.sh || fail "scripts/launch_qa_review.sh has shell syntax errors"
  fi
  if [[ -f scripts/run_qa_review.sh ]]; then
    bash -n scripts/run_qa_review.sh || fail "scripts/run_qa_review.sh has shell syntax errors"
  fi
  if [[ -f scripts/resolve_review_mode.sh ]]; then
    bash -n scripts/resolve_review_mode.sh || fail "scripts/resolve_review_mode.sh has shell syntax errors"
  fi
  if [[ -f scripts/apply_calibration_recommendation.sh ]]; then
    bash -n scripts/apply_calibration_recommendation.sh || fail "scripts/apply_calibration_recommendation.sh has shell syntax errors"
  fi
  if [[ -f scripts/enforce_closed_loop_policy.sh ]]; then
    bash -n scripts/enforce_closed_loop_policy.sh || fail "scripts/enforce_closed_loop_policy.sh has shell syntax errors"
  fi
  if [[ -f scripts/write_calibration_entry.sh ]]; then
    bash -n scripts/write_calibration_entry.sh || fail "scripts/write_calibration_entry.sh has shell syntax errors"
  fi
  bash -n scripts/write_gate_artifact.sh || fail "scripts/write_gate_artifact.sh has shell syntax errors"
  bash -n scripts/closed_loop.sh || fail "scripts/closed_loop.sh has shell syntax errors"
  if [[ -f scripts/deploy_gate.sh ]]; then
    bash -n scripts/deploy_gate.sh || fail "scripts/deploy_gate.sh has shell syntax errors"
  fi
  if [[ -f scripts/deploy_with_gate.sh ]]; then
    bash -n scripts/deploy_with_gate.sh || fail "scripts/deploy_with_gate.sh has shell syntax errors"
  fi
  pass "verify passed"
}

run_gate_checks() {
  [[ -f "$CONTRACT_FILE" ]] || return 0

  QA_REVIEW_REQUIREMENT="$(harness_extract_contract_requirement "$CONTRACT_FILE" "qa-review")"
  [[ "$QA_REVIEW_REQUIREMENT" =~ ^(required|not-required)$ ]] || fail "Contract missing qa-review requirement"
  QA_RUNTIME_REQUIREMENT="$(harness_extract_contract_requirement "$CONTRACT_FILE" "qa-runtime")"
  [[ "$QA_RUNTIME_REQUIREMENT" =~ ^(required|not-required)$ ]] || fail "Contract missing qa-runtime requirement"

  harness_check_gate_file "qa-review" "$QA_REVIEW_FILE" "$QA_REVIEW_REQUIREMENT" "$CONTRACT_SHA" "$WORKTREE_FINGERPRINT"
  harness_check_gate_file "qa-runtime" "$QA_RUNTIME_FILE" "$QA_RUNTIME_REQUIREMENT" "$CONTRACT_SHA" "$WORKTREE_FINGERPRINT"
}

refresh_qa_review_calibration_state() {
  QA_REVIEW_REQUIREMENT=""
  QA_RUNTIME_REQUIREMENT=""
  QA_REVIEW_NOTE_STATUS="missing"
  QA_REVIEW_NOTE_KIND=""
  QA_REVIEW_NOTE_ACTION=""
  QA_REVIEW_NOTE_TARGET=""
  QA_REVIEW_NOTE_SOURCE=""
  QA_REVIEW_NOTE_DATE=""
  QA_REVIEW_NOTE_BASIS=""
  QA_REVIEW_CALIBRATION_ACTION="none"

  [[ -f "$CONTRACT_FILE" ]] || return 0

  if [[ -z "$QA_REVIEW_REQUIREMENT" ]]; then
    QA_REVIEW_REQUIREMENT="$(harness_extract_contract_requirement "$CONTRACT_FILE" "qa-review")"
  fi
  if [[ -z "$QA_RUNTIME_REQUIREMENT" ]]; then
    QA_RUNTIME_REQUIREMENT="$(harness_extract_contract_requirement "$CONTRACT_FILE" "qa-runtime")"
  fi
  [[ "$QA_REVIEW_REQUIREMENT" =~ ^(required|not-required)$ ]] || return 0

  QA_REVIEW_NOTE_STATUS="$(harness_contract_gate_note_format_status "$CONTRACT_FILE" "qa-review")"
  if [[ "$QA_REVIEW_NOTE_STATUS" == "structured" ]]; then
    QA_REVIEW_NOTE_KIND="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "kind" || true)"
    QA_REVIEW_NOTE_ACTION="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "action" || true)"
    QA_REVIEW_NOTE_TARGET="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "target" || true)"
    QA_REVIEW_NOTE_SOURCE="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "source" || true)"
    QA_REVIEW_NOTE_DATE="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "date" || true)"
    QA_REVIEW_NOTE_BASIS="$(harness_extract_contract_gate_note_field "$CONTRACT_FILE" "qa-review" "basis" || true)"
  fi

  case "$QA_REVIEW_REQUIREMENT:$QA_REVIEW_NOTE_STATUS" in
    not-required:missing)
      QA_REVIEW_CALIBRATION_ACTION="backfill-structured-note"
      ;;
    not-required:legacy)
      QA_REVIEW_CALIBRATION_ACTION="normalize-legacy-note"
      ;;
    not-required:structured)
      ;;
    required:missing)
      ;;
    required:legacy|required:structured)
      QA_REVIEW_CALIBRATION_ACTION="review-stale-note"
      ;;
  esac
}

refresh_qa_review_artifact_state() {
  QA_REVIEW_ARTIFACT_PRESENT=0
  QA_REVIEW_ARTIFACT_STATUS=""
  QA_REVIEW_ARTIFACT_MODE=""
  QA_REVIEW_ARTIFACT_FINDINGS_COUNT=""
  QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY=""

  [[ -n "$QA_REVIEW_FILE" ]] || return 0
  [[ -f "$QA_REVIEW_FILE" ]] || return 0

  QA_REVIEW_ARTIFACT_PRESENT=1
  QA_REVIEW_ARTIFACT_STATUS="$(harness_extract_artifact_status "$QA_REVIEW_FILE")"
  QA_REVIEW_ARTIFACT_MODE="$(harness_extract_artifact_header "reviewer_mode" "$QA_REVIEW_FILE")"
  QA_REVIEW_ARTIFACT_FINDINGS_COUNT="$(harness_extract_artifact_header "review_findings_count" "$QA_REVIEW_FILE")"
  QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY="$(harness_extract_artifact_header "review_findings_highest_severity" "$QA_REVIEW_FILE")"
}

next_stricter_deny_severity() {
  case "${1:-}" in
    low)
      printf '%s\n' "medium"
      ;;
    medium)
      printf '%s\n' "high"
      ;;
    high)
      printf '%s\n' "critical"
      ;;
    critical)
      printf '%s\n' ""
      ;;
    *)
      printf '%s\n' ""
      ;;
  esac
}

refresh_qa_review_threshold_state() {
  QA_REVIEW_FINDINGS_THRESHOLD_READY=0
  QA_REVIEW_RECOMMENDED_MAX_FINDINGS=""
  QA_REVIEW_FINDINGS_THRESHOLD_DETAIL=""
  QA_REVIEW_SEVERITY_THRESHOLD_READY=0
  QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY=""
  QA_REVIEW_SEVERITY_THRESHOLD_DETAIL=""

  if [[ "$QA_REVIEW_ARTIFACT_PRESENT" != "1" ]]; then
    QA_REVIEW_FINDINGS_THRESHOLD_DETAIL="qa-review artifact missing"
    QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="qa-review artifact missing"
    return 0
  fi

  if [[ "$QA_REVIEW_ARTIFACT_FINDINGS_COUNT" =~ ^[0-9]+$ ]]; then
    QA_REVIEW_FINDINGS_THRESHOLD_READY=1
    QA_REVIEW_RECOMMENDED_MAX_FINDINGS="$QA_REVIEW_ARTIFACT_FINDINGS_COUNT"
    QA_REVIEW_FINDINGS_THRESHOLD_DETAIL="current artifact would pass --max-qa-review-findings $QA_REVIEW_ARTIFACT_FINDINGS_COUNT"
  else
    QA_REVIEW_FINDINGS_THRESHOLD_DETAIL="qa-review artifact missing review_findings_count"
  fi

  case "$QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY" in
    critical|high|medium|low)
      QA_REVIEW_SEVERITY_THRESHOLD_READY=1
      QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY="$(next_stricter_deny_severity "$QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY")"
      if [[ -n "$QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY" ]]; then
        QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="current highest severity is $QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY; strictest passing deny threshold is $QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY"
      else
        QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="current highest severity is critical; no deny threshold would pass without fixing findings first"
      fi
      ;;
    "")
      if [[ "$QA_REVIEW_ARTIFACT_FINDINGS_COUNT" =~ ^[0-9]+$ ]] && [[ "$QA_REVIEW_ARTIFACT_FINDINGS_COUNT" -eq 0 ]]; then
        QA_REVIEW_SEVERITY_THRESHOLD_READY=1
        QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY="low"
        QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="artifact reports zero findings, so any deny severity threshold would currently pass"
      else
        QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="qa-review artifact missing review_findings_highest_severity"
      fi
      ;;
    *)
      QA_REVIEW_SEVERITY_THRESHOLD_DETAIL="qa-review artifact has invalid review_findings_highest_severity: $QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY"
      ;;
  esac
}

print_qa_review_calibration_state_hint() {
  refresh_qa_review_calibration_state

  case "$QA_REVIEW_REQUIREMENT:$QA_REVIEW_NOTE_STATUS" in
    not-required:missing)
      echo "- qa-review calibration state: active contract is \`not-required\` with no adjacent \`calibration_note\`; if this downgrade was calibration-driven, run HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --apply to backfill structured metadata."
      ;;
    not-required:legacy)
      echo "- qa-review calibration state: active contract is \`not-required\` but still carries a legacy free-text \`calibration_note\`; run HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --apply to normalize it."
      ;;
    not-required:structured)
      echo "- qa-review calibration state: active contract is \`not-required\` and already backed by a structured \`calibration_note\` (kind=$QA_REVIEW_NOTE_KIND, action=$QA_REVIEW_NOTE_ACTION, target=$QA_REVIEW_NOTE_TARGET, source=$QA_REVIEW_NOTE_SOURCE, date=$QA_REVIEW_NOTE_DATE, basis=$QA_REVIEW_NOTE_BASIS)."
      ;;
    required:legacy|required:structured)
      echo "- qa-review calibration state: active contract is \`required\` but still has an adjacent \`calibration_note\`; review whether the note is stale or whether the requirement should still be downgraded."
      ;;
  esac
}

writeback_hints() {
  local calibration_file=""

  echo "=== Writeback Hints ==="
  if [[ -f "$PROGRESS_FILE" ]]; then
    echo "- Update PROGRESS.md if status, blockers, or next steps changed."
  else
    echo "- PROGRESS.md not present; no state writeback required."
  fi

  if [[ -f "$CONTRACT_FILE" ]]; then
    echo "- Update $CONTRACT_FILE if scope, risks, or stop conditions changed."
  fi

  print_qa_review_calibration_state_hint

  if [[ -f "$QA_REVIEW_FILE" ]]; then
    echo "- Keep $QA_REVIEW_FILE aligned with the current diff and contract."
  fi

  if [[ -f "$QA_RUNTIME_FILE" ]]; then
    echo "- Keep $QA_RUNTIME_FILE aligned with the current runtime evidence."
  fi

  if [[ -f "scripts/write_calibration_entry.sh" && -f "$CONTRACT_FILE" ]]; then
    echo "- Append calibration via HARNESS_DIR=$HARNESS_DIR bash scripts/write_calibration_entry.sh --from-current-gates --task \"<task>\" ..."
  fi

  calibration_file="$(harness_default_calibration_file "$HARNESS_DIR")"
  if [[ -f "scripts/calibration_report.sh" && -f "$calibration_file" ]]; then
    HARNESS_DIR="$HARNESS_DIR" bash scripts/calibration_report.sh --summary-only
  fi
  if [[ -f "scripts/apply_calibration_recommendation.sh" && -f "$calibration_file" ]]; then
    echo "- Review dry-run apply plan via HARNESS_DIR=$HARNESS_DIR bash scripts/apply_calibration_recommendation.sh --dry-run"
  fi
}

emit_json_summary() {
  local has_contract="$1"
  local calibration_file=""
  local calibration_report_available=0
  local calibration_report_json="null"
  local calibration_report_schema_version=""
  local calibration_qa_review_recommendation=""
  local calibration_contract_recommendation=""
  local calibration_progress_recommendation=""

  refresh_qa_review_calibration_state
  refresh_qa_review_artifact_state
  refresh_qa_review_threshold_state

  calibration_file="$(harness_default_calibration_file "$HARNESS_DIR")"
  if [[ -f "scripts/calibration_report.sh" && -f "$calibration_file" ]]; then
    calibration_report_json="$(
      HARNESS_DIR="$HARNESS_DIR" bash scripts/calibration_report.sh --json
    )"
    calibration_report_schema_version="$(harness_extract_top_level_json_string "schema_version" "$calibration_report_json")"
    [[ "$calibration_report_schema_version" == "calibration-report-v1" ]] || fail "calibration_report.sh JSON schema_version is '${calibration_report_schema_version:-missing}' (expected calibration-report-v1)"
    calibration_report_available=1
    calibration_qa_review_recommendation="$(harness_extract_top_level_json_string "compat_qa_review_recommendation" "$calibration_report_json")"
    calibration_contract_recommendation="$(harness_extract_top_level_json_string "compat_contract_recommendation" "$calibration_report_json")"
    calibration_progress_recommendation="$(harness_extract_top_level_json_string "compat_progress_recommendation" "$calibration_report_json")"
  fi

  printf '{\n'
  printf '  "schema_version": %s,\n' "$(harness_emit_json_string "closed-loop-v1")"
  printf '  "status": "pass",\n'
  printf '  "project_root": %s,\n' "$(harness_emit_json_string "$PROJECT_ROOT")"
  printf '  "harness_dir": %s,\n' "$(harness_emit_json_string "$HARNESS_DIR")"
  printf '  "artifacts_only": %s,\n' "$(harness_emit_json_boolean "$ARTIFACTS_ONLY")"
  printf '  "require_contract": %s,\n' "$(harness_emit_json_boolean "$REQUIRE_CONTRACT")"
  printf '  "compat_policy_recommended_action": %s,\n' "$(harness_emit_json_string "$QA_REVIEW_CALIBRATION_ACTION")"
  printf '  "compat_policy_note_status": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_STATUS")"
  printf '  "compat_policy_qa_review_requirement": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_REQUIREMENT")"
  printf '  "compat_qa_review_artifact_present": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_ARTIFACT_PRESENT")"
  printf '  "compat_qa_review_artifact_status": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_STATUS")"
  printf '  "compat_qa_review_reviewer_mode": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_MODE")"
  printf '  "compat_qa_review_findings_count": %s,\n' "$(harness_emit_json_number_or_null "$QA_REVIEW_ARTIFACT_FINDINGS_COUNT")"
  printf '  "compat_qa_review_highest_severity": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY")"
  printf '  "compat_qa_review_findings_threshold_ready": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_FINDINGS_THRESHOLD_READY")"
  printf '  "compat_qa_review_recommended_max_findings": %s,\n' "$(harness_emit_json_number_or_null "$QA_REVIEW_RECOMMENDED_MAX_FINDINGS")"
  printf '  "compat_qa_review_findings_threshold_detail": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_FINDINGS_THRESHOLD_DETAIL")"
  printf '  "compat_qa_review_severity_threshold_ready": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_SEVERITY_THRESHOLD_READY")"
  printf '  "compat_qa_review_strictest_passing_deny_severity": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY")"
  printf '  "compat_qa_review_severity_threshold_detail": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_SEVERITY_THRESHOLD_DETAIL")"
  printf '  "compat_calibration_report_available": %s,\n' "$(harness_emit_json_boolean "$calibration_report_available")"
  printf '  "compat_calibration_qa_review_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_qa_review_recommendation")"
  printf '  "compat_calibration_contract_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_contract_recommendation")"
  printf '  "compat_calibration_progress_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_progress_recommendation")"
  printf '  "verify": {\n'
  printf '    "ran": %s\n' "$(harness_emit_json_boolean "$(( 1 - ARTIFACTS_ONLY ))")"
  printf '  },\n'
  printf '  "progress": {\n'
  printf '    "path": %s,\n' "$(harness_emit_json_string "$PROGRESS_FILE")"
  printf '    "present": %s\n' "$(harness_emit_json_boolean "$([[ -f "$PROGRESS_FILE" ]] && echo 1 || echo 0)")"
  printf '  },\n'
  printf '  "contract": {\n'
  printf '    "present": %s,\n' "$(harness_emit_json_boolean "$has_contract")"
  printf '    "path": %s,\n' "$(harness_emit_json_string "$CONTRACT_FILE")"
  printf '    "execution_mode": %s,\n' "$(harness_emit_json_string_or_null "$EXECUTION_MODE")"
  printf '    "ask_policy": %s,\n' "$(harness_emit_json_string_or_null "$ASK_POLICY")"
  printf '    "max_debug_rounds": %s,\n' "${MAX_DEBUG_ROUNDS:-null}"
  printf '    "sha": %s,\n' "$(harness_emit_json_string_or_null "$CONTRACT_SHA")"
  printf '    "worktree_fingerprint": %s,\n' "$(harness_emit_json_string_or_null "$WORKTREE_FINGERPRINT")"
  printf '    "qa_review_requirement": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_REQUIREMENT")"
  printf '    "qa_review_artifact": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_FILE")"
  printf '    "qa_runtime_requirement": %s,\n' "$(harness_emit_json_string_or_null "$QA_RUNTIME_REQUIREMENT")"
  printf '    "qa_runtime_artifact": %s\n' "$(harness_emit_json_string_or_null "$QA_RUNTIME_FILE")"
  printf '  },\n'
  printf '  "qa_review_calibration_state": {\n'
  printf '    "available": %s,\n' "$(harness_emit_json_boolean "$has_contract")"
  printf '    "requirement": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_REQUIREMENT")"
  printf '    "note_status": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_STATUS")"
  printf '    "recommended_action": %s,\n' "$(harness_emit_json_string "$QA_REVIEW_CALIBRATION_ACTION")"
  printf '    "note": {\n'
  printf '      "kind": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_KIND")"
  printf '      "action": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_ACTION")"
  printf '      "target": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_TARGET")"
  printf '      "source": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_SOURCE")"
  printf '      "date": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_DATE")"
  printf '      "basis": %s\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_NOTE_BASIS")"
  printf '    }\n'
  printf '  },\n'
  printf '  "qa_review_artifact_state": {\n'
  printf '    "path": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_FILE")"
  printf '    "present": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_ARTIFACT_PRESENT")"
  printf '    "status": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_STATUS")"
  printf '    "reviewer_mode": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_MODE")"
  printf '    "review_findings_count": %s,\n' "$(harness_emit_json_number_or_null "$QA_REVIEW_ARTIFACT_FINDINGS_COUNT")"
  printf '    "review_findings_highest_severity": %s\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_ARTIFACT_HIGHEST_SEVERITY")"
  printf '  },\n'
  printf '  "qa_review_threshold_state": {\n'
  printf '    "findings_threshold_ready": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_FINDINGS_THRESHOLD_READY")"
  printf '    "recommended_max_findings": %s,\n' "$(harness_emit_json_number_or_null "$QA_REVIEW_RECOMMENDED_MAX_FINDINGS")"
  printf '    "findings_threshold_detail": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_FINDINGS_THRESHOLD_DETAIL")"
  printf '    "severity_threshold_ready": %s,\n' "$(harness_emit_json_boolean "$QA_REVIEW_SEVERITY_THRESHOLD_READY")"
  printf '    "strictest_passing_deny_severity": %s,\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_STRICTEST_PASSING_DENY_SEVERITY")"
  printf '    "severity_threshold_detail": %s\n' "$(harness_emit_json_string_or_null "$QA_REVIEW_SEVERITY_THRESHOLD_DETAIL")"
  printf '  },\n'
  printf '  "calibration": {\n'
  printf '    "file": %s,\n' "$(harness_emit_json_string "$calibration_file")"
  printf '    "present": %s,\n' "$(harness_emit_json_boolean "$([[ -f "$calibration_file" ]] && echo 1 || echo 0)")"
  printf '    "report_available": %s,\n' "$(harness_emit_json_boolean "$calibration_report_available")"
  printf '    "dry_run_apply_available": %s,\n' "$(harness_emit_json_boolean "$([[ -f "scripts/apply_calibration_recommendation.sh" && -f "$calibration_file" ]] && echo 1 || echo 0)")"
  printf '    "qa_review_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_qa_review_recommendation")"
  printf '    "contract_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_contract_recommendation")"
  printf '    "progress_recommendation": %s,\n' "$(harness_emit_json_string_or_null "$calibration_progress_recommendation")"
  printf '    "report": %s\n' "$calibration_report_json"
  printf '  }\n'
  printf '}\n'
}

main() {
  if [[ "$JSON_OUTPUT" -eq 0 ]]; then
    echo "=== Closed Loop ==="
  fi

  local has_contract=0
  if check_contract_execution_policy 0; then
    has_contract=1
  fi

  if [[ "$ARTIFACTS_ONLY" -eq 0 ]]; then
    run_verify
  else
    info "verify skipped by --artifacts-only"
  fi

  if [[ "$has_contract" -eq 1 ]]; then
    check_contract_execution_policy 1
    refresh_contract_snapshot
    pass "Contract execution policy OK (execution_mode=$EXECUTION_MODE, ask_policy=$ASK_POLICY, max_debug_rounds=$MAX_DEBUG_ROUNDS)"
    run_gate_checks
  fi

  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    emit_json_summary "$has_contract"
  else
    writeback_hints
    echo "CLOSED LOOP PASS"
  fi
}

main "$@"
