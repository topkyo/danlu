#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
TASK_NAME=""
STATUS="auto"
SUMMARY=""
BODY_FILE=""
HANDOFF_FILE=""
OUTPUT_FILE=""
CAPABILITIES_FILE=""
REVIEW_MODE_PREFERENCE=""
SKIP_LAUNCH=0
APPEND_CALIBRATION=0
CALIBRATION_TASK=""
CALIBRATION_DATE=""
CALIBRATION_AGENT=""
CALIBRATION_FILE=""
QA_REVIEW_HIT=""
QA_REVIEW_MISS=""
QA_REVIEW_FALSE_POSITIVE=""
REVIEW_FINDINGS_COUNT=""
REVIEW_FINDINGS_HIGHEST_SEVERITY=""
CONTRACT_SCOPE_CHANGED=""
NEW_SESSION=""
PROGRESS_READ=""
CALIBRATION_NOTES=""
declare -a FORWARD_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_qa_review.sh [options] [-- write_gate_artifact args...]

Options:
  --task <text>
  --status <auto|pass|fail|blocked|not-required>
  --summary <text>
  --body-file <path>
  --handoff-file <path>
  --output-file <path>
  --capabilities-file <path>
  --review-mode-preference <mode,mode,...>
  --skip-launch
  --append-calibration
  --calibration-task <text>
  --calibration-date <YYYY-MM-DD>
  --calibration-agent <name>
  --calibration-file <path>
  --qa-review-hit <count>
  --qa-review-miss <count>
  --qa-review-false-positive <count>
  --review-findings-count <count>
  --review-findings-highest-severity <critical|high|medium|low>
  --contract-scope-changed <yes|no|not-applicable>
  --new-session <yes|no>
  --progress-read <yes|no|not-applicable>
  --notes <text>

Behavior:
  - runs launch_qa_review.sh unless --skip-launch
  - defaults body file to the review output target from launch_qa_review.sh
  - if --status auto is used, infers pass when the review body says "no findings"
  - writes the qa-review gate artifact via write_gate_artifact.sh --resolve-reviewer-mode
  - can append calibration in the same command; --append-calibration defaults --calibration-task to --task when available
EOF
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

info() {
  echo "[INFO] $1"
}

pass() {
  echo "[OK] $1"
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

load_capability_defaults() {
  REVIEW_HANDOFF_DIR_DEFAULT="$HARNESS_DIR/review-handoffs"
  REVIEW_OUTPUT_FILE_DEFAULT="$REVIEW_HANDOFF_DIR_DEFAULT/qa-review.output.md"
}

load_capabilities_file() {
  [[ -n "$CAPABILITIES_FILE" ]] || CAPABILITIES_FILE="$HARNESS_DIR/review-capabilities.env"
  [[ -f "$CAPABILITIES_FILE" ]] || return 0

  # shellcheck source=/dev/null
  source "$CAPABILITIES_FILE"
}

derive_summary_from_body() {
  local body_file="$1"
  local mode="$2"
  local first_line=""

  if [[ -f "$body_file" ]]; then
    first_line="$(
      awk '
        NF == 0 { next }
        /^#/ { next }
        /^[[:space:]]*[-*][[:space:]]/ { sub(/^[[:space:]]*[-*][[:space:]]/, "", $0) }
        { print; exit }
      ' "$body_file"
    )"
  fi

  if [[ -n "$first_line" ]]; then
    printf 'qa-review %s (%s)\n' "$first_line" "$mode"
  else
    printf 'qa-review completed via %s\n' "$mode"
  fi
}

infer_status_from_body() {
  local body_file="$1"

  [[ -f "$body_file" ]] || fail "--status auto requires a review output/body file"

  if grep -Eiq '(^|[^[:alpha:]])(no findings|no issues found|no material findings)([^[:alpha:]]|$)' "$body_file"; then
    printf '%s\n' "pass"
    return 0
  fi

  printf '%s\n' "fail"
}

count_explicit_findings_from_body() {
  local body_file="$1"

  awk '
    BEGIN {
      in_findings = 0
      count = 0
    }

    {
      lower = tolower($0)
    }

    lower ~ /^[[:space:]]*#+[[:space:]]*findings?([[:space:]]*[:.-].*)?$/ {
      in_findings = 1
      next
    }

    /^[[:space:]]*#/ {
      if (in_findings) {
        in_findings = 0
      }
      next
    }

    lower ~ /^[[:space:]]*findings?:[[:space:]]+/ {
      count++
      next
    }

    in_findings && /^[[:space:]]*([0-9]+\.[[:space:]]+|[-*][[:space:]]+)/ {
      count++
      next
    }

    END {
      print count
    }
  ' "$body_file"
}

infer_qa_review_hit_from_body() {
  local body_file="$1"
  local status="$2"
  local explicit_count=""

  [[ -f "$body_file" ]] || return 0

  if grep -Eiq '(^|[^[:alpha:]])(no findings|no issues found|no material findings)([^[:alpha:]]|$)' "$body_file"; then
    printf '%s\n' "0"
    return 0
  fi

  explicit_count="$(count_explicit_findings_from_body "$body_file")"
  if [[ "$explicit_count" =~ ^[0-9]+$ ]] && [[ "$explicit_count" -gt 0 ]]; then
    printf '%s\n' "$explicit_count"
    return 0
  fi

  if [[ "$status" == "fail" ]] && grep -q '[[:alnum:]]' "$body_file"; then
    printf '%s\n' "1"
    return 0
  fi

  printf '%s\n' ""
}

normalize_review_severity_marker() {
  local marker="${1,,}"

  case "$marker" in
    *critical*|*blocker*|*p0*|*sev0*|*s0*)
      printf '%s\n' "critical"
      ;;
    *high*|*major*|*p1*|*sev1*|*s1*)
      printf '%s\n' "high"
      ;;
    *medium*|*moderate*|*med*|*p2*|*sev2*|*s2*)
      printf '%s\n' "medium"
      ;;
    *low*|*minor*|*p3*|*sev3*|*s3*)
      printf '%s\n' "low"
      ;;
    *)
      printf '%s\n' ""
      ;;
  esac
}

review_severity_rank() {
  case "$1" in
    critical)
      printf '%s\n' "4"
      ;;
    high)
      printf '%s\n' "3"
      ;;
    medium)
      printf '%s\n' "2"
      ;;
    low)
      printf '%s\n' "1"
      ;;
    *)
      printf '%s\n' "0"
      ;;
  esac
}

infer_review_findings_highest_severity_from_body() {
  local body_file="$1"
  local marker=""
  local normalized=""
  local highest=""
  local highest_rank=0
  local current_rank=0

  [[ -f "$body_file" ]] || return 0

  while IFS= read -r marker; do
    normalized="$(normalize_review_severity_marker "$marker")"
    [[ -n "$normalized" ]] || continue
    current_rank="$(review_severity_rank "$normalized")"
    if [[ "$current_rank" =~ ^[0-9]+$ ]] && (( current_rank > highest_rank )); then
      highest="$normalized"
      highest_rank="$current_rank"
    fi
  done < <(
    grep -Eio '\[[[:space:]]*(critical|high|medium|med|moderate|low|minor|major|blocker|p[0-3]|sev[0-3]|s[0-3])[[:space:]]*\]|severity[[:space:]]*[:=-]?[[:space:]]*(critical|high|medium|med|moderate|low|minor|major|blocker|p[0-3]|sev[0-3]|s[0-3])|priority[[:space:]]*[:=-]?[[:space:]]*(p[0-3])' "$body_file" 2>/dev/null || true
  )

  printf '%s\n' "$highest"
}

run_launcher() {
  local cmd=()

  cmd=(bash "$SCRIPT_DIR/launch_qa_review.sh")
  [[ -n "$TASK_NAME" ]] && cmd+=(--task "$TASK_NAME")
  [[ -n "$HANDOFF_FILE" ]] && cmd+=(--handoff-file "$HANDOFF_FILE")
  [[ -n "$OUTPUT_FILE" ]] && cmd+=(--output-file "$OUTPUT_FILE")
  [[ -n "$CAPABILITIES_FILE" ]] && cmd+=(--capabilities-file "$CAPABILITIES_FILE")
  [[ -n "$REVIEW_MODE_PREFERENCE" ]] && cmd+=(--review-mode-preference "$REVIEW_MODE_PREFERENCE")
  HARNESS_DIR="$HARNESS_DIR" "${cmd[@]}"
}

resolve_mode() {
  local cmd=()
  local resolved_output=""

  cmd=(bash "$SCRIPT_DIR/resolve_review_mode.sh")
  [[ -n "$CAPABILITIES_FILE" ]] && cmd+=(--capabilities-file "$CAPABILITIES_FILE")
  [[ -n "$REVIEW_MODE_PREFERENCE" ]] && cmd+=(--preference "$REVIEW_MODE_PREFERENCE")
  resolved_output="$(HARNESS_DIR="$HARNESS_DIR" "${cmd[@]}")"

  # shellcheck disable=SC1091
  source /dev/stdin <<< "$resolved_output"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      require_value "$1" "${2:-}"
      TASK_NAME="$2"
      shift 2
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
    --body-file)
      require_value "$1" "${2:-}"
      BODY_FILE="$2"
      shift 2
      ;;
    --handoff-file)
      require_value "$1" "${2:-}"
      HANDOFF_FILE="$2"
      shift 2
      ;;
    --output-file)
      require_value "$1" "${2:-}"
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --capabilities-file)
      require_value "$1" "${2:-}"
      CAPABILITIES_FILE="$2"
      shift 2
      ;;
    --review-mode-preference)
      require_value "$1" "${2:-}"
      REVIEW_MODE_PREFERENCE="$2"
      shift 2
      ;;
    --skip-launch)
      SKIP_LAUNCH=1
      shift
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
    --review-findings-count)
      require_value "$1" "${2:-}"
      REVIEW_FINDINGS_COUNT="$2"
      shift 2
      ;;
    --review-findings-highest-severity)
      require_value "$1" "${2:-}"
      REVIEW_FINDINGS_HIGHEST_SEVERITY="$2"
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
    --)
      shift
      FORWARD_ARGS+=("$@")
      break
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

[[ "$STATUS" =~ ^(auto|pass|fail|blocked|not-required)$ ]] || fail "Invalid --status: $STATUS"

load_capability_defaults
load_capabilities_file
if [[ -z "$HANDOFF_FILE" ]]; then
  HANDOFF_FILE="$REVIEW_HANDOFF_DIR_DEFAULT/qa-review.md"
fi
if [[ -z "$OUTPUT_FILE" ]]; then
  OUTPUT_FILE="$REVIEW_OUTPUT_FILE_DEFAULT"
fi
if [[ -z "$BODY_FILE" ]]; then
  BODY_FILE="$OUTPUT_FILE"
fi

if [[ "$SKIP_LAUNCH" -eq 0 ]]; then
  run_launcher
else
  info "skipping qa-review launch as requested"
fi

resolve_mode

if [[ "$STATUS" == "auto" ]]; then
  STATUS="$(infer_status_from_body "$BODY_FILE")"
  info "auto-inferred qa-review status: $STATUS"
fi

if [[ -z "$SUMMARY" ]]; then
  SUMMARY="$(derive_summary_from_body "$BODY_FILE" "$REVIEWER_MODE")"
fi
if [[ -z "$REVIEW_FINDINGS_COUNT" ]]; then
  REVIEW_FINDINGS_COUNT="$(infer_qa_review_hit_from_body "$BODY_FILE" "$STATUS")"
fi
if [[ -z "$REVIEW_FINDINGS_HIGHEST_SEVERITY" ]]; then
  REVIEW_FINDINGS_HIGHEST_SEVERITY="$(infer_review_findings_highest_severity_from_body "$BODY_FILE")"
fi
if [[ "$APPEND_CALIBRATION" -eq 1 && -z "$CALIBRATION_TASK" && -n "$TASK_NAME" ]]; then
  CALIBRATION_TASK="$TASK_NAME"
fi
if [[ "$APPEND_CALIBRATION" -eq 1 && "$STATUS" != "pass" && -z "$QA_REVIEW_HIT" ]]; then
  QA_REVIEW_HIT="$REVIEW_FINDINGS_COUNT"
  if [[ -n "$QA_REVIEW_HIT" ]]; then
    append_calibration_note "auto-inferred qa-review hit=$QA_REVIEW_HIT from review output"
  fi
fi

cmd=(
  bash "$SCRIPT_DIR/write_gate_artifact.sh"
  qa-review
  --status "$STATUS"
  --summary "$SUMMARY"
)

if [[ "$STATUS" == "not-required" ]]; then
  cmd+=(--reviewer-mode "$REVIEWER_MODE")
  if [[ -n "$REVIEWER_FALLBACK_REASON" ]]; then
    cmd+=(--reviewer-fallback-reason "$REVIEWER_FALLBACK_REASON")
  fi
  if [[ -n "$REVIEWER_IDENTITY" ]]; then
    cmd+=(--reviewer-identity "$REVIEWER_IDENTITY")
  fi
  if [[ -n "$REVIEWER_SCOPE" ]]; then
    cmd+=(--reviewer-scope "$REVIEWER_SCOPE")
  fi
else
  cmd+=(--resolve-reviewer-mode)
  if [[ -n "$CAPABILITIES_FILE" ]]; then
    cmd+=(--review-capabilities-file "$CAPABILITIES_FILE")
  fi
  if [[ -n "$REVIEW_MODE_PREFERENCE" ]]; then
    cmd+=(--review-mode-preference "$REVIEW_MODE_PREFERENCE")
  fi
fi
if [[ -f "$BODY_FILE" ]]; then
  cmd+=(--body-file "$BODY_FILE")
fi
if [[ -n "$REVIEW_FINDINGS_COUNT" ]]; then
  cmd+=(--review-findings-count "$REVIEW_FINDINGS_COUNT")
fi
if [[ -n "$REVIEW_FINDINGS_HIGHEST_SEVERITY" ]]; then
  cmd+=(--review-findings-highest-severity "$REVIEW_FINDINGS_HIGHEST_SEVERITY")
fi
if [[ "$APPEND_CALIBRATION" -eq 1 ]]; then
  cmd+=(--append-calibration)
fi
if [[ -n "$CALIBRATION_TASK" ]]; then
  cmd+=(--calibration-task "$CALIBRATION_TASK")
fi
if [[ -n "$CALIBRATION_DATE" ]]; then
  cmd+=(--calibration-date "$CALIBRATION_DATE")
fi
if [[ -n "$CALIBRATION_AGENT" ]]; then
  cmd+=(--calibration-agent "$CALIBRATION_AGENT")
fi
if [[ -n "$CALIBRATION_FILE" ]]; then
  cmd+=(--calibration-file "$CALIBRATION_FILE")
fi
if [[ -n "$QA_REVIEW_HIT" ]]; then
  cmd+=(--qa-review-hit "$QA_REVIEW_HIT")
fi
if [[ -n "$QA_REVIEW_MISS" ]]; then
  cmd+=(--qa-review-miss "$QA_REVIEW_MISS")
fi
if [[ -n "$QA_REVIEW_FALSE_POSITIVE" ]]; then
  cmd+=(--qa-review-false-positive "$QA_REVIEW_FALSE_POSITIVE")
fi
if [[ -n "$CONTRACT_SCOPE_CHANGED" ]]; then
  cmd+=(--contract-scope-changed "$CONTRACT_SCOPE_CHANGED")
fi
if [[ -n "$NEW_SESSION" ]]; then
  cmd+=(--new-session "$NEW_SESSION")
fi
if [[ -n "$PROGRESS_READ" ]]; then
  cmd+=(--progress-read "$PROGRESS_READ")
fi
if [[ -n "$CALIBRATION_NOTES" ]]; then
  cmd+=(--notes "$CALIBRATION_NOTES")
fi
if [[ "${#FORWARD_ARGS[@]}" -gt 0 ]]; then
  cmd+=("${FORWARD_ARGS[@]}")
fi

HARNESS_DIR="$HARNESS_DIR" "${cmd[@]}"
pass "qa-review artifact recorded with status $STATUS"
