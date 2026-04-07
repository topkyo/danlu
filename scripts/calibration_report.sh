#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/calibration.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/json_helpers.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CALIBRATION_FILE="$(harness_default_calibration_file "$HARNESS_DIR")"
PROJECT_TIER="${PROJECT_TIER:-}"
SUMMARY_ONLY=0
JSON_OUTPUT=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/calibration_report.sh [options]

Options:
  --file <path>
  --tier <lite|standard|strict>
  --summary-only
  --json
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

print_recommendation() {
  local label="$1"
  local recommendation="$2"
  local detail="$3"

  printf -- '- %s: %s (%s)\n' "$label" "$recommendation" "$detail"
}

emit_json_report() {
  local calibration_present="$1"
  local entries_parsed="$2"
  local qa_review_rounds="$3"
  local qa_review_zero_hit_streak="$4"
  local qa_review_threshold="$5"
  local qa_review_streak_misses="$6"
  local qa_review_streak_false_positives="$7"
  local qa_review_recommendation="$8"
  local qa_review_detail="$9"
  local contract_rounds="${10}"
  local contract_zero_adjustment_streak="${11}"
  local contract_threshold="${12}"
  local contract_recommendation="${13}"
  local contract_detail="${14}"
  local progress_sessions="${15}"
  local progress_skip_streak="${16}"
  local progress_threshold="${17}"
  local progress_recommendation="${18}"
  local progress_detail="${19}"

  printf '{\n'
  printf '  "schema_version": %s,\n' "$(harness_emit_json_string "calibration-report-v1")"
  printf '  "calibration_file": %s,\n' "$(harness_emit_json_string "$CALIBRATION_FILE")"
  printf '  "present": %s,\n' "$calibration_present"
  printf '  "tier": %s,\n' "$(harness_emit_json_string "$PROJECT_TIER")"
  printf '  "entries_parsed": %s,\n' "$entries_parsed"
  printf '  "compat_qa_review_recommendation": %s,\n' "$(harness_emit_json_string "$qa_review_recommendation")"
  printf '  "compat_qa_review_detail": %s,\n' "$(harness_emit_json_string "$qa_review_detail")"
  printf '  "compat_contract_recommendation": %s,\n' "$(harness_emit_json_string "$contract_recommendation")"
  printf '  "compat_contract_detail": %s,\n' "$(harness_emit_json_string "$contract_detail")"
  printf '  "compat_progress_recommendation": %s,\n' "$(harness_emit_json_string "$progress_recommendation")"
  printf '  "compat_progress_detail": %s,\n' "$(harness_emit_json_string "$progress_detail")"
  printf '  "qa_review": {\n'
  printf '    "rounds_logged": %s,\n' "$qa_review_rounds"
  printf '    "consecutive_zero_hit_rounds": %s,\n' "$qa_review_zero_hit_streak"
  printf '    "threshold": %s,\n' "$qa_review_threshold"
  printf '    "recent_misses_in_streak": %s,\n' "$qa_review_streak_misses"
  printf '    "recent_false_positives_in_streak": %s,\n' "$qa_review_streak_false_positives"
  printf '    "recommendation": %s,\n' "$(harness_emit_json_string "$qa_review_recommendation")"
  printf '    "detail": %s\n' "$(harness_emit_json_string "$qa_review_detail")"
  printf '  },\n'
  printf '  "contract": {\n'
  printf '    "rounds_logged": %s,\n' "$contract_rounds"
  printf '    "consecutive_zero_adjustment_rounds": %s,\n' "$contract_zero_adjustment_streak"
  printf '    "threshold": %s,\n' "$contract_threshold"
  printf '    "recommendation": %s,\n' "$(harness_emit_json_string "$contract_recommendation")"
  printf '    "detail": %s\n' "$(harness_emit_json_string "$contract_detail")"
  printf '  },\n'
  printf '  "progress": {\n'
  printf '    "new_sessions_logged": %s,\n' "$progress_sessions"
  printf '    "consecutive_skipped_reads": %s,\n' "$progress_skip_streak"
  printf '    "threshold": %s,\n' "$progress_threshold"
  printf '    "recommendation": %s,\n' "$(harness_emit_json_string "$progress_recommendation")"
  printf '    "detail": %s\n' "$(harness_emit_json_string "$progress_detail")"
  printf '  }\n'
  printf '}\n'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      require_value "$1" "${2:-}"
      CALIBRATION_FILE="$2"
      shift 2
      ;;
    --tier)
      require_value "$1" "${2:-}"
      PROJECT_TIER="$2"
      shift 2
      ;;
    --summary-only)
      SUMMARY_ONLY=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
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

if [[ -z "$PROJECT_TIER" ]]; then
  if PROJECT_TIER="$(harness_detect_project_tier "$PROJECT_ROOT" 2>/dev/null)"; then
    :
  else
    PROJECT_TIER="standard"
  fi
fi

case "$PROJECT_TIER" in
  lite|standard|strict)
    ;;
  *)
    fail "Invalid tier: $PROJECT_TIER"
    ;;
esac

qa_review_threshold="$(harness_calibration_zero_hit_threshold "$PROJECT_TIER")"
contract_threshold=3
progress_threshold=3
calibration_present=true

if [[ ! -f "$CALIBRATION_FILE" ]]; then
  calibration_present=false
  if [[ "$JSON_OUTPUT" -eq 0 ]]; then
    echo "[INFO] Calibration file not found: $CALIBRATION_FILE"
    exit 0
  fi
  ENTRIES=()
else
  mapfile -t ENTRIES < <(harness_emit_calibration_entries "$CALIBRATION_FILE")
  if [[ "${#ENTRIES[@]}" -eq 0 && "$JSON_OUTPUT" -eq 0 ]]; then
    echo "[INFO] No calibration entries recorded in $CALIBRATION_FILE"
    exit 0
  fi
fi

declare -a REVIEW_HITS=()
declare -a REVIEW_MISSES=()
declare -a REVIEW_FALSE_POSITIVES=()
declare -a CONTRACT_SCOPE_CHANGES=()
declare -a PROGRESS_READS=()

qa_review_rounds=0
contract_rounds=0
progress_sessions=0

for entry in "${ENTRIES[@]}"; do
  IFS=$'\t' read -r \
    _entry_date \
    _entry_agent \
    _entry_task \
    review_mode \
    review_hit \
    review_miss \
    review_false_positive \
    _runtime_mode \
    _runtime_hit \
    _runtime_miss \
    _runtime_false_positive \
    contract_scope_changed \
    new_session \
    progress_read \
    _entry_notes <<< "$entry"

  if harness_calibration_mode_recorded "$review_mode"; then
    review_hit="$(harness_normalize_calibration_counter "$review_hit")"
    review_miss="$(harness_normalize_calibration_counter "$review_miss")"
    review_false_positive="$(harness_normalize_calibration_counter "$review_false_positive")"
    if [[ -n "$review_hit" && -n "$review_miss" && -n "$review_false_positive" ]]; then
      REVIEW_HITS+=("$review_hit")
      REVIEW_MISSES+=("$review_miss")
      REVIEW_FALSE_POSITIVES+=("$review_false_positive")
      qa_review_rounds=$((qa_review_rounds + 1))
    fi
  fi

  contract_scope_changed="$(harness_normalize_calibration_boolean "$contract_scope_changed")"
  if [[ "$contract_scope_changed" == "yes" || "$contract_scope_changed" == "no" ]]; then
    CONTRACT_SCOPE_CHANGES+=("$contract_scope_changed")
    contract_rounds=$((contract_rounds + 1))
  fi

  new_session="$(harness_normalize_calibration_boolean "$new_session")"
  progress_read="$(harness_normalize_calibration_boolean "$progress_read")"
  if [[ "$new_session" == "yes" && ( "$progress_read" == "yes" || "$progress_read" == "no" ) ]]; then
    PROGRESS_READS+=("$progress_read")
    progress_sessions=$((progress_sessions + 1))
  fi
done

qa_review_zero_hit_streak=0
qa_review_streak_misses=0
qa_review_streak_false_positives=0
for ((i=${#REVIEW_HITS[@]} - 1; i >= 0; i--)); do
  if (( REVIEW_HITS[i] != 0 )); then
    break
  fi
  qa_review_zero_hit_streak=$((qa_review_zero_hit_streak + 1))
  qa_review_streak_misses=$((qa_review_streak_misses + REVIEW_MISSES[i]))
  qa_review_streak_false_positives=$((qa_review_streak_false_positives + REVIEW_FALSE_POSITIVES[i]))
done

contract_zero_adjustment_streak=0
for ((i=${#CONTRACT_SCOPE_CHANGES[@]} - 1; i >= 0; i--)); do
  if [[ "${CONTRACT_SCOPE_CHANGES[i]}" != "no" ]]; then
    break
  fi
  contract_zero_adjustment_streak=$((contract_zero_adjustment_streak + 1))
done

progress_skip_streak=0
for ((i=${#PROGRESS_READS[@]} - 1; i >= 0; i--)); do
  if [[ "${PROGRESS_READS[i]}" != "no" ]]; then
    break
  fi
  progress_skip_streak=$((progress_skip_streak + 1))
done

qa_review_recommendation="KEEP current qa-review requirement"
qa_review_detail="$qa_review_zero_hit_streak consecutive zero-hit rounds; threshold $qa_review_threshold"
if (( qa_review_rounds == 0 )); then
  qa_review_recommendation="INSUFFICIENT DATA"
  qa_review_detail="no qa-review calibration rounds recorded"
elif (( qa_review_zero_hit_streak >= qa_review_threshold )) && (( qa_review_streak_misses == 0 )) && (( qa_review_streak_false_positives == 0 )); then
  qa_review_recommendation="DOWNGRADE to not-required"
  qa_review_detail="$qa_review_zero_hit_streak consecutive zero-hit rounds with no misses/false positives"
elif (( qa_review_zero_hit_streak >= qa_review_threshold )); then
  qa_review_recommendation="KEEP qa-review required"
  qa_review_detail="$qa_review_zero_hit_streak zero-hit rounds but recent misses/false positives block downgrade"
fi

contract_recommendation="KEEP standalone contract"
contract_detail="$contract_zero_adjustment_streak consecutive zero-adjustment rounds; threshold $contract_threshold"
if (( contract_rounds == 0 )); then
  contract_recommendation="INSUFFICIENT DATA"
  contract_detail="no contract-scope calibration rounds recorded"
elif (( contract_zero_adjustment_streak >= contract_threshold )); then
  contract_recommendation="INLINE into PROGRESS.md"
  contract_detail="$contract_zero_adjustment_streak consecutive rounds recorded no contract scope changes"
fi

progress_recommendation="KEEP normal PROGRESS.md usage"
progress_detail="$progress_skip_streak consecutive new sessions without reading PROGRESS.md; threshold $progress_threshold"
if (( progress_sessions == 0 )); then
  progress_recommendation="INSUFFICIENT DATA"
  progress_detail="no new-session PROGRESS.md calibration entries recorded"
elif (( progress_skip_streak >= progress_threshold )); then
  progress_recommendation="DOWNGRADE to blockers-only"
  progress_detail="$progress_skip_streak consecutive new sessions completed without reading PROGRESS.md"
fi

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  emit_json_report \
    "$calibration_present" \
    "${#ENTRIES[@]}" \
    "$qa_review_rounds" \
    "$qa_review_zero_hit_streak" \
    "$qa_review_threshold" \
    "$qa_review_streak_misses" \
    "$qa_review_streak_false_positives" \
    "$qa_review_recommendation" \
    "$qa_review_detail" \
    "$contract_rounds" \
    "$contract_zero_adjustment_streak" \
    "$contract_threshold" \
    "$contract_recommendation" \
    "$contract_detail" \
    "$progress_sessions" \
    "$progress_skip_streak" \
    "$progress_threshold" \
    "$progress_recommendation" \
    "$progress_detail"
  exit 0
fi

if [[ "$SUMMARY_ONLY" -eq 1 ]]; then
  echo "=== Calibration Recommendations ==="
  echo "Calibration file: $CALIBRATION_FILE"
  echo "Tier: $PROJECT_TIER"
  print_recommendation "qa-review" "$qa_review_recommendation" "$qa_review_detail"
  print_recommendation "contract" "$contract_recommendation" "$contract_detail"
  print_recommendation "PROGRESS.md" "$progress_recommendation" "$progress_detail"
  exit 0
fi

echo "=== Calibration Report ==="
echo "Calibration file: $CALIBRATION_FILE"
echo "Tier: $PROJECT_TIER"
echo "Entries parsed: ${#ENTRIES[@]}"
echo ""
echo "qa-review"
echo "  rounds logged: $qa_review_rounds"
echo "  consecutive zero-hit rounds: $qa_review_zero_hit_streak"
echo "  threshold: $qa_review_threshold"
echo "  recent misses in streak: $qa_review_streak_misses"
echo "  recent false positives in streak: $qa_review_streak_false_positives"
echo "  recommendation: $qa_review_recommendation"
echo "  detail: $qa_review_detail"
echo ""
echo "contract"
echo "  rounds logged: $contract_rounds"
echo "  consecutive zero-adjustment rounds: $contract_zero_adjustment_streak"
echo "  threshold: $contract_threshold"
echo "  recommendation: $contract_recommendation"
echo "  detail: $contract_detail"
echo ""
echo "PROGRESS.md"
echo "  new sessions logged: $progress_sessions"
echo "  consecutive skipped reads: $progress_skip_streak"
echo "  threshold: $progress_threshold"
echo "  recommendation: $progress_recommendation"
echo "  detail: $progress_detail"
