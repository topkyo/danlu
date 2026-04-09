#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

HARNESS_DIR="${HARNESS_DIR:-.claude}"
CAPABILITIES_FILE=""
PREFERENCE_OVERRIDE=""
AVAILABLE_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/resolve_review_mode.sh [options]

Options:
  --capabilities-file <path>
  --preference <mode,mode,...>
  --available <mode,mode,...>

Outputs shell-safe assignments:
  REVIEWER_MODE
  REVIEWER_FALLBACK_REASON
  REVIEWER_SCOPE
  REVIEWER_IDENTITY
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

normalize_yes_no() {
  local name="$1"
  local value="$2"

  case "$value" in
    yes|no)
      printf '%s\n' "$value"
      ;;
    *)
      fail "Invalid $name: $value (expected yes or no)"
      ;;
  esac
}

mode_is_valid() {
  case "$1" in
    isolated-agent|external-agent|fresh-session|same-context|human)
      return 0
      ;;
  esac

  return 1
}

set_mode_capability() {
  local mode="$1"
  local value="$2"

  case "$mode" in
    isolated-agent)
      REVIEW_CAPABILITY_ISOLATED_AGENT="$value"
      ;;
    external-agent)
      REVIEW_CAPABILITY_EXTERNAL_AGENT="$value"
      ;;
    fresh-session)
      REVIEW_CAPABILITY_FRESH_SESSION="$value"
      ;;
    same-context)
      REVIEW_CAPABILITY_SAME_CONTEXT="$value"
      ;;
    human)
      REVIEW_CAPABILITY_HUMAN="$value"
      ;;
    *)
      fail "Unknown reviewer mode in capability map: $mode"
      ;;
  esac
}

mode_capability_enabled() {
  local mode="$1"
  local value=""

  case "$mode" in
    isolated-agent)
      value="$REVIEW_CAPABILITY_ISOLATED_AGENT"
      ;;
    external-agent)
      value="$REVIEW_CAPABILITY_EXTERNAL_AGENT"
      ;;
    fresh-session)
      value="$REVIEW_CAPABILITY_FRESH_SESSION"
      ;;
    same-context)
      value="$REVIEW_CAPABILITY_SAME_CONTEXT"
      ;;
    human)
      value="$REVIEW_CAPABILITY_HUMAN"
      ;;
    *)
      return 1
      ;;
  esac

  [[ "$value" == "yes" ]]
}

load_defaults() {
  REVIEW_CAPABILITY_ISOLATED_AGENT="no"
  REVIEW_CAPABILITY_EXTERNAL_AGENT="no"
  REVIEW_CAPABILITY_FRESH_SESSION="no"
  REVIEW_CAPABILITY_SAME_CONTEXT="yes"
  REVIEW_CAPABILITY_HUMAN="no"
  REVIEW_MODE_PREFERENCE="isolated-agent,external-agent,fresh-session,same-context,human"
  REVIEWER_SCOPE_DEFAULT="contract+diff+touched-files"
  REVIEWER_IDENTITY_DEFAULT=""
  SAME_CONTEXT_FALLBACK_REASON_DEFAULT="isolated reviewer capability not configured in the current environment"
}

validate_loaded_configuration() {
  REVIEW_CAPABILITY_ISOLATED_AGENT="$(normalize_yes_no "REVIEW_CAPABILITY_ISOLATED_AGENT" "$REVIEW_CAPABILITY_ISOLATED_AGENT")"
  REVIEW_CAPABILITY_EXTERNAL_AGENT="$(normalize_yes_no "REVIEW_CAPABILITY_EXTERNAL_AGENT" "$REVIEW_CAPABILITY_EXTERNAL_AGENT")"
  REVIEW_CAPABILITY_FRESH_SESSION="$(normalize_yes_no "REVIEW_CAPABILITY_FRESH_SESSION" "$REVIEW_CAPABILITY_FRESH_SESSION")"
  REVIEW_CAPABILITY_SAME_CONTEXT="$(normalize_yes_no "REVIEW_CAPABILITY_SAME_CONTEXT" "$REVIEW_CAPABILITY_SAME_CONTEXT")"
  REVIEW_CAPABILITY_HUMAN="$(normalize_yes_no "REVIEW_CAPABILITY_HUMAN" "$REVIEW_CAPABILITY_HUMAN")"
}

load_capabilities_file() {
  [[ -n "$CAPABILITIES_FILE" ]] || CAPABILITIES_FILE="$HARNESS_DIR/review-capabilities.env"
  [[ -f "$CAPABILITIES_FILE" ]] || return 0

  # shellcheck source=/dev/null
  source "$CAPABILITIES_FILE"
}

apply_available_override() {
  local mode=""
  local csv="$1"

  REVIEW_CAPABILITY_ISOLATED_AGENT="no"
  REVIEW_CAPABILITY_EXTERNAL_AGENT="no"
  REVIEW_CAPABILITY_FRESH_SESSION="no"
  REVIEW_CAPABILITY_SAME_CONTEXT="no"
  REVIEW_CAPABILITY_HUMAN="no"

  IFS=',' read -r -a modes <<< "$csv"
  for mode in "${modes[@]}"; do
    mode="${mode//[[:space:]]/}"
    [[ -n "$mode" ]] || continue
    mode_is_valid "$mode" || fail "Invalid reviewer mode in --available: $mode"
    set_mode_capability "$mode" "yes"
  done
}

resolve_mode() {
  local preference_csv="$1"
  local mode=""
  local chosen=""

  IFS=',' read -r -a preferred_modes <<< "$preference_csv"
  for mode in "${preferred_modes[@]}"; do
    mode="${mode//[[:space:]]/}"
    [[ -n "$mode" ]] || continue
    mode_is_valid "$mode" || fail "Invalid reviewer mode in preference list: $mode"
    if mode_capability_enabled "$mode"; then
      chosen="$mode"
      break
    fi
  done

  [[ -n "$chosen" ]] || fail "No supported reviewer mode matched preference '$preference_csv' (capabilities file: ${CAPABILITIES_FILE:-none})"
  printf '%s\n' "$chosen"
}

emit_shell_assignment() {
  local key="$1"
  local value="$2"
  printf '%s=%q\n' "$key" "$value"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --capabilities-file)
      require_value "$1" "${2:-}"
      CAPABILITIES_FILE="$2"
      shift 2
      ;;
    --preference)
      require_value "$1" "${2:-}"
      PREFERENCE_OVERRIDE="$2"
      shift 2
      ;;
    --available)
      require_value "$1" "${2:-}"
      AVAILABLE_OVERRIDE="$2"
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

load_defaults
load_capabilities_file
validate_loaded_configuration

if [[ -n "$AVAILABLE_OVERRIDE" ]]; then
  apply_available_override "$AVAILABLE_OVERRIDE"
fi

if [[ -n "$PREFERENCE_OVERRIDE" ]]; then
  REVIEW_MODE_PREFERENCE="$PREFERENCE_OVERRIDE"
fi

REVIEWER_MODE="$(resolve_mode "$REVIEW_MODE_PREFERENCE")"
REVIEWER_FALLBACK_REASON=""
if [[ "$REVIEWER_MODE" == "same-context" ]]; then
  REVIEWER_FALLBACK_REASON="$SAME_CONTEXT_FALLBACK_REASON_DEFAULT"
fi

emit_shell_assignment "REVIEWER_MODE" "$REVIEWER_MODE"
emit_shell_assignment "REVIEWER_FALLBACK_REASON" "$REVIEWER_FALLBACK_REASON"
emit_shell_assignment "REVIEWER_SCOPE" "$REVIEWER_SCOPE_DEFAULT"
emit_shell_assignment "REVIEWER_IDENTITY" "$REVIEWER_IDENTITY_DEFAULT"
