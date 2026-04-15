#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/contract_artifacts.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/worktree_fingerprint.sh"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CAPABILITIES_FILE=""
REVIEW_MODE_PREFERENCE=""
TASK_NAME=""
HANDOFF_FILE=""
OUTPUT_FILE=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/launch_qa_review.sh [options]

Options:
  --task <text>
  --handoff-file <path>
  --output-file <path>
  --capabilities-file <path>
  --review-mode-preference <mode,mode,...>
  --dry-run

Environment exported to launcher commands:
  OPEN_HARNESS_REVIEW_MODE
  OPEN_HARNESS_REVIEW_SCOPE
  OPEN_HARNESS_REVIEW_FALLBACK_REASON
  OPEN_HARNESS_REVIEW_IDENTITY
  OPEN_HARNESS_REVIEW_MODEL_PREFERENCE
  OPEN_HARNESS_REVIEW_TASK
  OPEN_HARNESS_REVIEW_HANDOFF_FILE
  OPEN_HARNESS_REVIEW_OUTPUT_FILE
  OPEN_HARNESS_REVIEW_ARTIFACT_FILE
  OPEN_HARNESS_REVIEW_CONTRACT_FILE
  OPEN_HARNESS_REVIEW_PROJECT_ROOT
  OPEN_HARNESS_REVIEW_TOUCHED_FILES
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

load_capability_defaults() {
  REVIEW_MODE_PREFERENCE_DEFAULT="isolated-agent,external-agent,fresh-session,same-context,human"
  REVIEW_HANDOFF_DIR_DEFAULT="$HARNESS_DIR/review-handoffs"
  REVIEW_OUTPUT_FILE_DEFAULT="$REVIEW_HANDOFF_DIR_DEFAULT/qa-review.output.md"
  REVIEW_LAUNCH_COMMAND_ISOLATED_AGENT=""
  REVIEW_LAUNCH_COMMAND_EXTERNAL_AGENT=""
  REVIEW_LAUNCH_COMMAND_FRESH_SESSION=""
  REVIEW_LAUNCH_COMMAND_SAME_CONTEXT=""
  REVIEW_LAUNCH_COMMAND_HUMAN=""
  REVIEW_MODEL_PREFERENCE_DEFAULT=""
}

load_capabilities_file() {
  [[ -n "$CAPABILITIES_FILE" ]] || CAPABILITIES_FILE="$HARNESS_DIR/review-capabilities.env"
  [[ -f "$CAPABILITIES_FILE" ]] || return 0

  # shellcheck source=/dev/null
  source "$CAPABILITIES_FILE"
}

resolve_mode() {
  local cmd=()
  local resolved_output=""

  [[ -f "$SCRIPT_DIR/resolve_review_mode.sh" ]] || fail "Missing review mode resolver: $SCRIPT_DIR/resolve_review_mode.sh"
  cmd=(bash "$SCRIPT_DIR/resolve_review_mode.sh")
  [[ -n "$CAPABILITIES_FILE" ]] && cmd+=(--capabilities-file "$CAPABILITIES_FILE")
  [[ -n "$REVIEW_MODE_PREFERENCE" ]] && cmd+=(--preference "$REVIEW_MODE_PREFERENCE")
  resolved_output="$(HARNESS_DIR="$HARNESS_DIR" "${cmd[@]}")"

  # shellcheck disable=SC1091
  source /dev/stdin <<< "$resolved_output"
}

is_review_handoff_path() {
  local path="$1"
  [[ "$path" == "$HARNESS_DIR/review-handoffs/"* ]]
}

collect_touched_files() {
  local line=""
  local path=""
  local status_output=""

  if ! harness_is_git_worktree "$PROJECT_ROOT"; then
    return 0
  fi

  status_output="$(git -C "$PROJECT_ROOT" status --porcelain=v1 --untracked-files=all -- . 2>/dev/null || true)"
  [[ -n "$status_output" ]] || return 0

  while IFS= read -r line; do
    path="${line:3}"
    if [[ "$path" == *" -> "* ]]; then
      path="${path##* -> }"
    fi
    [[ -n "$path" ]] || continue
    harness_is_gate_artifact_path "$HARNESS_DIR" "$path" && continue
    is_review_handoff_path "$path" && continue
    printf '%s\n' "$path"
  done <<< "$status_output" | sort -u
}

write_handoff_file() {
  local handoff_path="$1"
  local mode="$2"
  local scope="$3"
  local fallback_reason="$4"
  local identity="$5"
  local model_preference="$6"
  local artifact_file="$7"
  local contract_file="$8"
  local touched_files="$9"
  local generated_at=""

  generated_at="$(date +%F)"
  mkdir -p "$(dirname "$handoff_path")"

  {
    printf '# QA Review Handoff\n\n'
    printf -- '- Task: %s\n' "${TASK_NAME:-qa-review}"
    printf -- '- Generated At: %s\n' "$generated_at"
    printf -- '- Reviewer Mode: %s\n' "$mode"
    printf -- '- Reviewer Scope: %s\n' "$scope"
    if [[ -n "$fallback_reason" ]]; then
      printf -- '- Reviewer Fallback Reason: %s\n' "$fallback_reason"
    fi
    if [[ -n "$identity" ]]; then
      printf -- '- Reviewer Identity Hint: %s\n' "$identity"
    fi
    if [[ -n "$model_preference" ]]; then
      printf -- '- Preferred Review Models: %s\n' "$model_preference"
    fi
    printf -- '- Contract: %s\n' "$contract_file"
    printf -- '- Gate Artifact: %s\n' "$artifact_file"
    printf '\n## Touched Files\n\n'
    if [[ -n "$touched_files" ]]; then
      while IFS= read -r path; do
        [[ -n "$path" ]] || continue
        printf -- '- %s\n' "$path"
      done <<< "$touched_files"
    else
      printf -- '- (no changed files detected from git status in this worktree)\n'
    fi
    printf '\n## Reviewer Brief\n\n'
    printf 'Review from an independent reviewer perspective. Focus on behavior changes, cross-file consistency, dead code or half-removed state, missing exclusions, config duplication, and contract consistency.\n'
    if [[ "$mode" == "same-context" && -n "$fallback_reason" ]]; then
      printf '\nSame-context fallback reason: %s\n' "$fallback_reason"
    fi
  } > "$handoff_path"
}

launch_command_for_mode() {
  case "$1" in
    isolated-agent)
      printf '%s\n' "$REVIEW_LAUNCH_COMMAND_ISOLATED_AGENT"
      ;;
    external-agent)
      printf '%s\n' "$REVIEW_LAUNCH_COMMAND_EXTERNAL_AGENT"
      ;;
    fresh-session)
      printf '%s\n' "$REVIEW_LAUNCH_COMMAND_FRESH_SESSION"
      ;;
    same-context)
      printf '%s\n' "$REVIEW_LAUNCH_COMMAND_SAME_CONTEXT"
      ;;
    human)
      printf '%s\n' "$REVIEW_LAUNCH_COMMAND_HUMAN"
      ;;
    *)
      fail "Unsupported reviewer mode: $1"
      ;;
  esac
}

run_launch_command() {
  local launch_command="$1"

  (
    export HARNESS_DIR
    export OPEN_HARNESS_REVIEW_MODE="$REVIEWER_MODE"
    export OPEN_HARNESS_REVIEW_SCOPE="$REVIEWER_SCOPE"
    export OPEN_HARNESS_REVIEW_FALLBACK_REASON="$REVIEWER_FALLBACK_REASON"
    export OPEN_HARNESS_REVIEW_IDENTITY="$REVIEWER_IDENTITY"
    export OPEN_HARNESS_REVIEW_MODEL_PREFERENCE="$REVIEW_MODEL_PREFERENCE_DEFAULT"
    export OPEN_HARNESS_REVIEW_TASK="${TASK_NAME:-qa-review}"
    export OPEN_HARNESS_REVIEW_HANDOFF_FILE="$HANDOFF_FILE"
    export OPEN_HARNESS_REVIEW_OUTPUT_FILE="$OUTPUT_FILE"
    export OPEN_HARNESS_REVIEW_ARTIFACT_FILE="$QA_REVIEW_FILE"
    export OPEN_HARNESS_REVIEW_CONTRACT_FILE="$CONTRACT_FILE"
    export OPEN_HARNESS_REVIEW_PROJECT_ROOT="$PROJECT_ROOT"
    export OPEN_HARNESS_REVIEW_TOUCHED_FILES="$TOUCHED_FILES"
    bash -lc "$launch_command"
  )
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      require_value "$1" "${2:-}"
      TASK_NAME="$2"
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
    --dry-run)
      DRY_RUN=1
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

CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
[[ -f "$CONTRACT_FILE" ]] || fail "Missing contract: $CONTRACT_FILE"

QA_REVIEW_FILE="$(harness_extract_contract_artifact_path "$CONTRACT_FILE" "qa-review")"
[[ -n "$QA_REVIEW_FILE" ]] || fail "Contract missing qa-review artifact path"
harness_is_valid_gate_artifact_path "$HARNESS_DIR" "$QA_REVIEW_FILE" || fail "qa-review artifact path must stay under $HARNESS_DIR/gates/: $QA_REVIEW_FILE"

load_capability_defaults
load_capabilities_file
if [[ -z "$REVIEW_MODE_PREFERENCE" ]]; then
  REVIEW_MODE_PREFERENCE="${REVIEW_MODE_PREFERENCE_DEFAULT:-$REVIEW_MODE_PREFERENCE_DEFAULT}"
fi
resolve_mode

if [[ -z "$HANDOFF_FILE" ]]; then
  HANDOFF_FILE="$REVIEW_HANDOFF_DIR_DEFAULT/qa-review.md"
fi
if [[ -z "$OUTPUT_FILE" ]]; then
  OUTPUT_FILE="$REVIEW_OUTPUT_FILE_DEFAULT"
fi

TOUCHED_FILES="$(collect_touched_files || true)"
write_handoff_file \
  "$HANDOFF_FILE" \
  "$REVIEWER_MODE" \
  "$REVIEWER_SCOPE" \
  "$REVIEWER_FALLBACK_REASON" \
  "$REVIEWER_IDENTITY" \
  "$REVIEW_MODEL_PREFERENCE_DEFAULT" \
  "$QA_REVIEW_FILE" \
  "$CONTRACT_FILE" \
  "$TOUCHED_FILES"
mkdir -p "$(dirname "$OUTPUT_FILE")"
pass "prepared qa-review handoff at $HANDOFF_FILE"
info "review output target: $OUTPUT_FILE"
info "reviewer mode resolved to $REVIEWER_MODE"

LAUNCH_COMMAND="$(launch_command_for_mode "$REVIEWER_MODE")"
if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ -n "$LAUNCH_COMMAND" ]]; then
    info "dry-run launcher command for $REVIEWER_MODE: $LAUNCH_COMMAND"
  else
    info "dry-run found no launcher command for $REVIEWER_MODE"
  fi
  exit 0
fi

if [[ -n "$LAUNCH_COMMAND" ]]; then
  run_launch_command "$LAUNCH_COMMAND"
  pass "launched qa-review via $REVIEWER_MODE"
  exit 0
fi

if [[ "$REVIEWER_MODE" == "same-context" ]]; then
  info "no launcher configured for same-context; continue qa-review in the current session using $HANDOFF_FILE"
  exit 0
fi

fail "Resolved reviewer mode $REVIEWER_MODE but no launcher command is configured in $CAPABILITIES_FILE"
