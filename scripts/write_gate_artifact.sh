#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/worktree_fingerprint.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/contract_artifacts.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
GATE_NAME=""
STATUS=""
SUMMARY=""
CHECKED_AT="$(date +%F)"
BODY_FILE=""
REVIEWER_MODE=""
REVIEWER_FALLBACK_REASON=""
REVIEWER_IDENTITY=""
REVIEWER_SCOPE=""
RUNTIME_MODE=""
RUNTIME_IDENTITY=""
OUTPUT_PATH=""
APPEND_CALIBRATION=0
CALIBRATION_TASK=""
CALIBRATION_DATE=""
CALIBRATION_AGENT=""
CALIBRATION_FILE=""
QA_REVIEW_HIT=""
QA_REVIEW_MISS=""
QA_REVIEW_FALSE_POSITIVE=""
QA_RUNTIME_HIT=""
QA_RUNTIME_MISS=""
QA_RUNTIME_FALSE_POSITIVE=""
CONTRACT_SCOPE_CHANGED=""
NEW_SESSION=""
PROGRESS_READ=""
CALIBRATION_NOTES=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/write_gate_artifact.sh <qa-review|qa-runtime> --status <pass|fail|blocked|not-required> --summary <text> [options]

Options:
  --checked-at <YYYY-MM-DD>
  --body-file <path>
  --output <path>
  --append-calibration
  --calibration-task <text>
  --calibration-date <YYYY-MM-DD>
  --calibration-agent <name>
  --calibration-file <path>
  --qa-review-hit <count>
  --qa-review-miss <count>
  --qa-review-false-positive <count>
  --qa-runtime-hit <count>
  --qa-runtime-miss <count>
  --qa-runtime-false-positive <count>
  --contract-scope-changed <yes|no|not-applicable>
  --new-session <yes|no>
  --progress-read <yes|no|not-applicable>
  --notes <text>

qa-review options:
  --reviewer-mode <isolated-agent|external-agent|fresh-session|same-context|human>
  --reviewer-fallback-reason <text>
  --reviewer-identity <text>
  --reviewer-scope <contract+diff+touched-files|full-repo|custom>

qa-runtime options:
  --runtime-mode <scripted|isolated-agent|same-context|human>
  --runtime-identity <text>
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

append_calibration_note() {
  local note="$1"

  [[ -n "$note" ]] || return 0
  if [[ -n "$CALIBRATION_NOTES" ]]; then
    CALIBRATION_NOTES="$CALIBRATION_NOTES; $note"
  else
    CALIBRATION_NOTES="$note"
  fi
}

apply_calibration_defaults_for_current_gate() {
  case "$GATE_NAME:$STATUS" in
    qa-review:pass)
      if [[ -z "$QA_REVIEW_HIT" && -z "$QA_REVIEW_MISS" && -z "$QA_REVIEW_FALSE_POSITIVE" ]]; then
        QA_REVIEW_HIT="0"
        QA_REVIEW_MISS="0"
        QA_REVIEW_FALSE_POSITIVE="0"
        append_calibration_note "auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass"
      fi
      ;;
    qa-runtime:pass)
      if [[ -z "$QA_RUNTIME_HIT" && -z "$QA_RUNTIME_MISS" && -z "$QA_RUNTIME_FALSE_POSITIVE" ]]; then
        QA_RUNTIME_HIT="0"
        QA_RUNTIME_MISS="0"
        QA_RUNTIME_FALSE_POSITIVE="0"
        append_calibration_note "auto-defaulted qa-runtime hit/miss/false-positive to 0 from write_gate_artifact pass"
      fi
      ;;
  esac
}

append_calibration_entry() {
  local cmd=()

  [[ -n "$CALIBRATION_TASK" ]] || fail "--append-calibration requires --calibration-task"
  [[ -f "$SCRIPT_DIR/write_calibration_entry.sh" ]] || fail "Missing calibration helper: $SCRIPT_DIR/write_calibration_entry.sh"
  apply_calibration_defaults_for_current_gate

  cmd=(bash "$SCRIPT_DIR/write_calibration_entry.sh" --from-current-gates --task "$CALIBRATION_TASK")

  [[ -n "$CALIBRATION_DATE" ]] && cmd+=(--date "$CALIBRATION_DATE")
  [[ -n "$CALIBRATION_AGENT" ]] && cmd+=(--agent "$CALIBRATION_AGENT")
  [[ -n "$CALIBRATION_FILE" ]] && cmd+=(--file "$CALIBRATION_FILE")
  [[ -n "$QA_REVIEW_HIT" ]] && cmd+=(--qa-review-hit "$QA_REVIEW_HIT")
  [[ -n "$QA_REVIEW_MISS" ]] && cmd+=(--qa-review-miss "$QA_REVIEW_MISS")
  [[ -n "$QA_REVIEW_FALSE_POSITIVE" ]] && cmd+=(--qa-review-false-positive "$QA_REVIEW_FALSE_POSITIVE")
  [[ -n "$QA_RUNTIME_HIT" ]] && cmd+=(--qa-runtime-hit "$QA_RUNTIME_HIT")
  [[ -n "$QA_RUNTIME_MISS" ]] && cmd+=(--qa-runtime-miss "$QA_RUNTIME_MISS")
  [[ -n "$QA_RUNTIME_FALSE_POSITIVE" ]] && cmd+=(--qa-runtime-false-positive "$QA_RUNTIME_FALSE_POSITIVE")
  [[ -n "$CONTRACT_SCOPE_CHANGED" ]] && cmd+=(--contract-scope-changed "$CONTRACT_SCOPE_CHANGED")
  [[ -n "$NEW_SESSION" ]] && cmd+=(--new-session "$NEW_SESSION")
  [[ -n "$PROGRESS_READ" ]] && cmd+=(--progress-read "$PROGRESS_READ")
  [[ -n "$CALIBRATION_NOTES" ]] && cmd+=(--notes "$CALIBRATION_NOTES")

  HARNESS_DIR="$HARNESS_DIR" "${cmd[@]}"
}

append_optional_header() {
  local key="$1"
  local value="$2"
  [[ -n "$value" ]] || return 0
  printf '%s: %s\n' "$key" "$value"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    qa-review|qa-runtime)
      [[ -z "$GATE_NAME" ]] || fail "Gate name already set: $GATE_NAME"
      GATE_NAME="$1"
      shift
      ;;
    --status)
      require_value "$1" "${2:-}"
      STATUS="$2"
      shift 2
      ;;
    --summary)
      require_value "$1" "${2:-}"
      SUMMARY="$2"
      shift 2
      ;;
    --checked-at)
      require_value "$1" "${2:-}"
      CHECKED_AT="$2"
      shift 2
      ;;
    --body-file)
      require_value "$1" "${2:-}"
      BODY_FILE="$2"
      shift 2
      ;;
    --output)
      require_value "$1" "${2:-}"
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --append-calibration)
      APPEND_CALIBRATION=1
      shift
      ;;
    --calibration-task)
      require_value "$1" "${2:-}"
      CALIBRATION_TASK="$2"
      shift 2
      ;;
    --calibration-date)
      require_value "$1" "${2:-}"
      CALIBRATION_DATE="$2"
      shift 2
      ;;
    --calibration-agent)
      require_value "$1" "${2:-}"
      CALIBRATION_AGENT="$2"
      shift 2
      ;;
    --calibration-file)
      require_value "$1" "${2:-}"
      CALIBRATION_FILE="$2"
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
      CALIBRATION_NOTES="$2"
      shift 2
      ;;
    --reviewer-mode)
      require_value "$1" "${2:-}"
      REVIEWER_MODE="$2"
      shift 2
      ;;
    --reviewer-fallback-reason)
      require_value "$1" "${2:-}"
      REVIEWER_FALLBACK_REASON="$2"
      shift 2
      ;;
    --reviewer-identity)
      require_value "$1" "${2:-}"
      REVIEWER_IDENTITY="$2"
      shift 2
      ;;
    --reviewer-scope)
      require_value "$1" "${2:-}"
      REVIEWER_SCOPE="$2"
      shift 2
      ;;
    --runtime-mode)
      require_value "$1" "${2:-}"
      RUNTIME_MODE="$2"
      shift 2
      ;;
    --runtime-identity)
      require_value "$1" "${2:-}"
      RUNTIME_IDENTITY="$2"
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

[[ -n "$GATE_NAME" ]] || {
  usage >&2
  fail "Missing gate name"
}
[[ "$STATUS" =~ ^(pass|fail|blocked|not-required)$ ]] || fail "Invalid status: $STATUS"
[[ -n "$SUMMARY" ]] || fail "Missing --summary"

CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
[[ -f "$CONTRACT_FILE" ]] || fail "Missing contract: $CONTRACT_FILE"

case "$GATE_NAME" in
  qa-review)
    DEFAULT_OUTPUT="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-review")"
    [[ -n "$DEFAULT_OUTPUT" ]] || fail "Contract missing qa-review artifact path"
    harness_is_valid_gate_artifact_path "$HARNESS_DIR" "$DEFAULT_OUTPUT" || fail "qa-review artifact path must stay under $HARNESS_DIR/gates/: $DEFAULT_OUTPUT"
    if [[ "$STATUS" == "pass" ]]; then
      [[ "$REVIEWER_MODE" =~ ^(isolated-agent|external-agent|fresh-session|same-context|human)$ ]] || fail "qa-review pass requires valid --reviewer-mode"
      if [[ "$REVIEWER_MODE" == "same-context" ]]; then
        [[ -n "$REVIEWER_FALLBACK_REASON" ]] || fail "qa-review same-context pass requires --reviewer-fallback-reason"
      fi
    fi
    ;;
  qa-runtime)
    DEFAULT_OUTPUT="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-runtime")"
    [[ -n "$DEFAULT_OUTPUT" ]] || fail "Contract missing qa-runtime artifact path"
    harness_is_valid_gate_artifact_path "$HARNESS_DIR" "$DEFAULT_OUTPUT" || fail "qa-runtime artifact path must stay under $HARNESS_DIR/gates/: $DEFAULT_OUTPUT"
    if [[ "$STATUS" == "pass" ]]; then
      [[ "$RUNTIME_MODE" =~ ^(scripted|isolated-agent|same-context|human)$ ]] || fail "qa-runtime pass requires valid --runtime-mode"
    fi
    ;;
esac

OUTPUT_PATH="${OUTPUT_PATH:-$DEFAULT_OUTPUT}"
CONTRACT_SHA="$(sha256sum -- "$CONTRACT_FILE" | awk '{print $1}')"
WORKTREE_FINGERPRINT="$(harness_compute_project_fingerprint "$PROJECT_ROOT" "$HARNESS_DIR")"

mkdir -p "$(dirname "$OUTPUT_PATH")"
{
  printf 'status: %s\n' "$STATUS"
  printf 'checked_at: %s\n' "$CHECKED_AT"
  printf 'contract_sha: %s\n' "$CONTRACT_SHA"
  printf 'worktree_fingerprint: %s\n' "$WORKTREE_FINGERPRINT"
  printf 'summary: %s\n' "$SUMMARY"

  case "$GATE_NAME" in
    qa-review)
      append_optional_header "reviewer_mode" "$REVIEWER_MODE"
      append_optional_header "reviewer_fallback_reason" "$REVIEWER_FALLBACK_REASON"
      append_optional_header "reviewer_identity" "$REVIEWER_IDENTITY"
      append_optional_header "reviewer_scope" "$REVIEWER_SCOPE"
      ;;
    qa-runtime)
      append_optional_header "runtime_mode" "$RUNTIME_MODE"
      append_optional_header "runtime_identity" "$RUNTIME_IDENTITY"
      ;;
  esac

  if [[ -n "$BODY_FILE" ]]; then
    [[ -f "$BODY_FILE" ]] || fail "Missing body file: $BODY_FILE"
    printf '\n'
    cat -- "$BODY_FILE"
    tail -c1 "$BODY_FILE" 2>/dev/null | grep -q '^$' || printf '\n'
  fi
} > "$OUTPUT_PATH"

echo "[OK] Wrote $OUTPUT_PATH"

if [[ "$APPEND_CALIBRATION" -eq 1 ]]; then
  append_calibration_entry
fi
