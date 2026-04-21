#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
HARNESS_ROOT="/home/tim/open-harness"
ACTION=""
TIER="standard"
PLATFORMS="claude,codex"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/setup_local_harness.sh --apply [--tier lite|standard|strict] [--platforms p1,p2,...]
  bash scripts/setup_local_harness.sh --clean
  bash scripts/setup_local_harness.sh --status

This helper keeps generic open-harness scaffold local-only:
- removes vendored harness files from the current worktree when asked
- regenerates fresh scaffold from /home/tim/open-harness
- hides regenerated local scaffold via .git/info/exclude
EOF
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

info() {
  echo "[INFO] $1"
}

require_harness_root() {
  [[ -d "$HARNESS_ROOT" ]] || fail "Missing open-harness root: $HARNESS_ROOT"
  [[ -f "$HARNESS_ROOT/init.sh" ]] || fail "Missing open-harness init.sh: $HARNESS_ROOT/init.sh"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply|--clean|--status)
      [[ -z "$ACTION" ]] || fail "Only one action may be specified"
      ACTION="${1#--}"
      shift
      ;;
    --tier)
      TIER="${2:-}"
      [[ -n "$TIER" ]] || fail "--tier requires a value"
      shift 2
      ;;
    --platforms)
      PLATFORMS="${2:-}"
      [[ -n "$PLATFORMS" ]] || fail "--platforms requires a value"
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

[[ -n "$ACTION" ]] || fail "Specify one of --apply, --clean, or --status"

TRACKED_GENERIC_HARNESS=(
  ".claude"
  ".codex"
  ".copilot"
  ".open-harness-tier"
  ".opencode"
  "scripts/apply_calibration_recommendation.sh"
  "scripts/calibration_report.sh"
  "scripts/closed_loop.sh"
  "scripts/deploy_gate.sh"
  "scripts/deploy_with_gate.sh"
  "scripts/enforce_closed_loop_policy.sh"
  "scripts/finalize_task.sh"
  "scripts/launch_qa_review.sh"
  "scripts/resolve_review_mode.sh"
  "scripts/run_qa_review.sh"
  "scripts/write_calibration_entry.sh"
  "scripts/write_gate_artifact.sh"
  "scripts/lib"
)

LOCAL_HARNESS_PATTERNS=(
  ".claude/"
  ".codex/"
  ".copilot/"
  ".open-harness-tier"
  ".open-harness.conf"
  ".open-harness-upgrade/"
  ".opencode/"
  "scripts/apply_calibration_recommendation.sh"
  "scripts/calibration_report.sh"
  "scripts/closed_loop.sh"
  "scripts/deploy_gate.sh"
  "scripts/deploy_with_gate.sh"
  "scripts/enforce_closed_loop_policy.sh"
  "scripts/finalize_task.sh"
  "scripts/launch_qa_review.sh"
  "scripts/resolve_review_mode.sh"
  "scripts/run_qa_review.sh"
  "scripts/write_calibration_entry.sh"
  "scripts/write_gate_artifact.sh"
  "scripts/lib/"
  "scripts/platforms/"
)

EXCLUDE_FILE="$PROJECT_ROOT/.git/info/exclude"
MARKER_BEGIN="# >>> aiwiki-local-harness >>>"
MARKER_END="# <<< aiwiki-local-harness <<<"

remove_exclude_block() {
  local src="$1"
  local dst="$2"
  if [[ ! -f "$src" ]]; then
    : > "$dst"
    return 0
  fi
  awk -v begin="$MARKER_BEGIN" -v end="$MARKER_END" '
    $0 == begin {skip = 1; next}
    $0 == end {skip = 0; next}
    !skip {print}
  ' "$src" > "$dst"
}

write_exclude_block() {
  local tmp
  tmp="$(mktemp)"
  mkdir -p "$(dirname "$EXCLUDE_FILE")"
  remove_exclude_block "$EXCLUDE_FILE" "$tmp"
  cp "$tmp" "$EXCLUDE_FILE"
  rm -f -- "$tmp"
  if [[ -s "$EXCLUDE_FILE" ]]; then
    printf '\n' >> "$EXCLUDE_FILE"
  fi
  printf '%s\n' "$MARKER_BEGIN" >> "$EXCLUDE_FILE"
  for pattern in "${LOCAL_HARNESS_PATTERNS[@]}"; do
    printf '%s\n' "$pattern" >> "$EXCLUDE_FILE"
  done
  printf '%s\n' "$MARKER_END" >> "$EXCLUDE_FILE"
}

clean_local_harness() {
  local path=""
  for path in "${TRACKED_GENERIC_HARNESS[@]}"; do
    if git -C "$PROJECT_ROOT" ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
      git -C "$PROJECT_ROOT" rm -r --cached --ignore-unmatch -- "$path" >/dev/null 2>&1 || true
    fi
  done

  rm -rf \
    "$PROJECT_ROOT/.claude" \
    "$PROJECT_ROOT/.codex" \
    "$PROJECT_ROOT/.copilot" \
    "$PROJECT_ROOT/.open-harness-upgrade" \
    "$PROJECT_ROOT/.opencode" \
    "$PROJECT_ROOT/scripts/lib" \
    "$PROJECT_ROOT/scripts/platforms"
  rm -f \
    "$PROJECT_ROOT/.open-harness-tier" \
    "$PROJECT_ROOT/.open-harness.conf" \
    "$PROJECT_ROOT/scripts/apply_calibration_recommendation.sh" \
    "$PROJECT_ROOT/scripts/calibration_report.sh" \
    "$PROJECT_ROOT/scripts/closed_loop.sh" \
    "$PROJECT_ROOT/scripts/deploy_gate.sh" \
    "$PROJECT_ROOT/scripts/deploy_with_gate.sh" \
    "$PROJECT_ROOT/scripts/enforce_closed_loop_policy.sh" \
    "$PROJECT_ROOT/scripts/finalize_task.sh" \
    "$PROJECT_ROOT/scripts/launch_qa_review.sh" \
    "$PROJECT_ROOT/scripts/resolve_review_mode.sh" \
    "$PROJECT_ROOT/scripts/run_qa_review.sh" \
    "$PROJECT_ROOT/scripts/write_calibration_entry.sh" \
    "$PROJECT_ROOT/scripts/write_gate_artifact.sh"
}

apply_local_harness() {
  require_harness_root
  clean_local_harness
  write_exclude_block
  info "Generating local harness from $HARNESS_ROOT"
  bash "$HARNESS_ROOT/init.sh" --tier "$TIER" --platforms "$PLATFORMS"
}

status_local_harness() {
  echo "project_root=$PROJECT_ROOT"
  echo "harness_root=$HARNESS_ROOT"
  if [[ -d "$PROJECT_ROOT/.claude" || -d "$PROJECT_ROOT/.codex" ]]; then
    echo "local_harness=present"
  else
    echo "local_harness=absent"
  fi
  if [[ -f "$EXCLUDE_FILE" ]] && grep -Fqx "$MARKER_BEGIN" "$EXCLUDE_FILE"; then
    echo "exclude_block=present"
  else
    echo "exclude_block=absent"
  fi
}

case "$ACTION" in
  apply)
    apply_local_harness
    ;;
  clean)
    clean_local_harness
    write_exclude_block
    ;;
  status)
    status_local_harness
    ;;
esac
