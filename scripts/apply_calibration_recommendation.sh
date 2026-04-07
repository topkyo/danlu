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
source "$SCRIPT_DIR/lib/json_helpers.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CALIBRATION_FILE="$(harness_default_calibration_file "$HARNESS_DIR")"
PROJECT_TIER="${PROJECT_TIER:-}"
APPLY=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/apply_calibration_recommendation.sh [options]

Options:
  --file <path>
  --tier <lite|standard|strict>
  --dry-run
  --apply
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

qa_review_note_is_aligned() {
  local contract_file="$1"
  local note_kind=""
  local note_action=""
  local note_target=""
  local note_source=""
  local note_date=""
  local note_basis=""

  note_kind="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "kind" || true)"
  note_action="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "action" || true)"
  note_target="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "target" || true)"
  note_source="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "source" || true)"
  note_date="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "date" || true)"
  note_basis="$(harness_extract_contract_gate_note_field "$contract_file" "qa-review" "basis" || true)"

  [[ "$note_kind" == "calibration" ]] &&
    [[ "$note_action" == "downgrade" ]] &&
    [[ "$note_target" == "not-required" ]] &&
    [[ "$note_source" == "apply_calibration_recommendation.sh" ]] &&
    [[ -n "$note_date" ]] &&
    [[ -n "$note_basis" ]]
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
    --dry-run)
      shift
      ;;
    --apply)
      APPLY=1
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

if [[ ! -f "$CALIBRATION_FILE" ]]; then
  echo "[INFO] Calibration file not found: $CALIBRATION_FILE"
  exit 0
fi

REPORT_JSON="$(
  HARNESS_DIR="$HARNESS_DIR" bash "$SCRIPT_DIR/calibration_report.sh" \
    --file "$CALIBRATION_FILE" \
    --tier "$PROJECT_TIER" \
    --json
)"

REPORT_SCHEMA_VERSION="$(harness_extract_top_level_json_string "schema_version" "$REPORT_JSON")"
[[ "$REPORT_SCHEMA_VERSION" == "calibration-report-v1" ]] || fail "calibration_report.sh JSON schema_version is '${REPORT_SCHEMA_VERSION:-missing}' (expected calibration-report-v1)"

QA_REVIEW_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_qa_review_recommendation" "$REPORT_JSON")"
QA_REVIEW_DETAIL="$(harness_extract_top_level_json_string "compat_qa_review_detail" "$REPORT_JSON")"
CONTRACT_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_contract_recommendation" "$REPORT_JSON")"
CONTRACT_DETAIL="$(harness_extract_top_level_json_string "compat_contract_detail" "$REPORT_JSON")"
PROGRESS_RECOMMENDATION="$(harness_extract_top_level_json_string "compat_progress_recommendation" "$REPORT_JSON")"
PROGRESS_DETAIL="$(harness_extract_top_level_json_string "compat_progress_detail" "$REPORT_JSON")"

CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
PROGRESS_FILE="$PROJECT_ROOT/PROGRESS.md"
CALIBRATION_NOTE_DATE="$(date +%F)"
QA_REVIEW_CALIBRATION_NOTE="$(
  harness_format_contract_gate_note_json \
    "calibration" \
    "downgrade" \
    "not-required" \
    "apply_calibration_recommendation.sh" \
    "$CALIBRATION_NOTE_DATE" \
    "$CALIBRATION_FILE"
)"

if [[ "$APPLY" -eq 1 ]]; then
  echo "=== Calibration Apply ==="
else
  echo "=== Calibration Apply Plan (dry-run) ==="
fi
echo "Calibration file: $CALIBRATION_FILE"
echo "Tier: $PROJECT_TIER"

if [[ "$QA_REVIEW_RECOMMENDATION" == "DOWNGRADE to not-required" ]]; then
  if [[ -f "$CONTRACT_FILE" ]]; then
    current_requirement="$(harness_extract_contract_requirement "$CONTRACT_FILE" "qa-review")"
    current_note="$(harness_extract_contract_gate_note "$CONTRACT_FILE" "qa-review")"
    case "$current_requirement" in
      required)
        if [[ "$APPLY" -eq 1 ]]; then
          harness_replace_contract_requirement "$CONTRACT_FILE" "qa-review" "not-required"
          harness_upsert_contract_gate_note "$CONTRACT_FILE" "qa-review" "$QA_REVIEW_CALIBRATION_NOTE"
          echo "- qa-review: updated $CONTRACT_FILE Gate Requirements from \`required\` to \`not-required\` and inserted a structured calibration note ($QA_REVIEW_DETAIL)"
        else
          echo "- qa-review: would update $CONTRACT_FILE Gate Requirements from \`required\` to \`not-required\` and insert a structured calibration note ($QA_REVIEW_DETAIL)"
          echo "  exact replacement: - \`qa-review\`: required -> - \`qa-review\`: not-required"
          echo "  note to add:   calibration_note: qa-review $QA_REVIEW_CALIBRATION_NOTE"
        fi
        ;;
      not-required)
        if [[ -z "$current_note" ]]; then
          if [[ "$APPLY" -eq 1 ]]; then
            harness_upsert_contract_gate_note "$CONTRACT_FILE" "qa-review" "$QA_REVIEW_CALIBRATION_NOTE"
            echo "- qa-review: requirement was already \`not-required\`; inserted a missing structured calibration note in $CONTRACT_FILE ($QA_REVIEW_DETAIL)"
          else
            echo "- qa-review: requirement is already \`not-required\`, but would insert a missing structured calibration note into $CONTRACT_FILE ($QA_REVIEW_DETAIL)"
            echo "  note to add:   calibration_note: qa-review $QA_REVIEW_CALIBRATION_NOTE"
          fi
        elif qa_review_note_is_aligned "$CONTRACT_FILE"; then
          echo "- qa-review: recommendation is already aligned in $CONTRACT_FILE (\`qa-review\` is \`not-required\` and a structured calibration note is already present) ($QA_REVIEW_DETAIL)"
        elif [[ "$APPLY" -eq 1 ]]; then
          harness_upsert_contract_gate_note "$CONTRACT_FILE" "qa-review" "$QA_REVIEW_CALIBRATION_NOTE"
          echo "- qa-review: requirement was already \`not-required\`; normalized the existing calibration note to structured format in $CONTRACT_FILE ($QA_REVIEW_DETAIL)"
        else
          echo "- qa-review: requirement is already \`not-required\`, but would normalize the existing calibration note to structured format in $CONTRACT_FILE ($QA_REVIEW_DETAIL)"
          echo "  note to add:   calibration_note: qa-review $QA_REVIEW_CALIBRATION_NOTE"
        fi
        ;;
      *)
        echo "- qa-review: recommendation is to downgrade, but $CONTRACT_FILE does not expose a parseable \`qa-review\` requirement ($QA_REVIEW_DETAIL)"
        ;;
    esac
  else
    echo "- qa-review: recommendation is to downgrade, but no active contract exists at $CONTRACT_FILE to edit ($QA_REVIEW_DETAIL)"
  fi
else
  echo "- qa-review: no file edit suggested ($QA_REVIEW_RECOMMENDATION; $QA_REVIEW_DETAIL)"
fi

if [[ "$CONTRACT_RECOMMENDATION" == "INLINE into PROGRESS.md" ]]; then
  if [[ -f "$PROGRESS_FILE" ]]; then
    echo "- contract: no safe in-place edit suggested; future low-risk tasks can inline scope into $PROGRESS_FILE instead of refreshing $CONTRACT_FILE ($CONTRACT_DETAIL)"
  else
    echo "- contract: no safe in-place edit suggested; future low-risk tasks can inline scope into PROGRESS.md, but $PROGRESS_FILE is not present ($CONTRACT_DETAIL)"
  fi
else
  echo "- contract: no file edit suggested ($CONTRACT_RECOMMENDATION; $CONTRACT_DETAIL)"
fi

if [[ "$PROGRESS_RECOMMENDATION" == "DOWNGRADE to blockers-only" ]]; then
  if [[ -f "$PROGRESS_FILE" ]]; then
    echo "- PROGRESS.md: no safe in-place edit suggested; future sessions should treat $PROGRESS_FILE as blockers-only state instead of a full task log ($PROGRESS_DETAIL)"
  else
    echo "- PROGRESS.md: recommendation is blockers-only and $PROGRESS_FILE is already absent ($PROGRESS_DETAIL)"
  fi
else
  echo "- PROGRESS.md: no file edit suggested ($PROGRESS_RECOMMENDATION; $PROGRESS_DETAIL)"
fi

echo ""
if [[ "$APPLY" -eq 1 ]]; then
  echo "Only the active contract \`qa-review\` requirement and its structured calibration note are auto-applied today. Contract inlining and PROGRESS downgrade remain advisory."
else
  echo "This helper does not edit files. Use the dry-run output to decide whether to update the active contract or team protocol manually."
fi
