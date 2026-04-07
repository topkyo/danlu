#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

HARNESS_DIR="${HARNESS_DIR:-.codex}"
CONTRACT_FILE="$HARNESS_DIR/contracts/active.md"
MESSAGE=""
STAGE_MODE="all"
declare -a PATHS=()

usage() {
  cat <<'EOF'
Usage:
  bash scripts/finalize_task.sh [--message "commit message"]
  bash scripts/finalize_task.sh --staged-only [--message "commit message"]
  bash scripts/finalize_task.sh [--message "commit message"] --paths <path> [<path> ...]

Behavior:
  1. Runs closed_loop.sh with --require-contract
  2. Stages changes according to the selected mode
  3. Creates one local git commit

Staging modes:
  default        stage all non-ignored changes with `git add -A`
  --staged-only  do not change the index; commit only what is already staged
  --paths        stage only the listed paths; this option must appear last

Notes:
  - This script never pushes.
  - If --message is omitted, the commit message is derived from the active contract goal.
EOF
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)
      [[ $# -ge 2 ]] || fail "Missing value for --message"
      MESSAGE="$2"
      shift 2
      ;;
    --staged-only)
      [[ "$STAGE_MODE" == "all" ]] || fail "--staged-only cannot be combined with another staging mode"
      STAGE_MODE="staged-only"
      shift
      ;;
    --paths)
      [[ "$STAGE_MODE" == "all" ]] || fail "--paths cannot be combined with another staging mode"
      shift
      [[ $# -gt 0 ]] || fail "--paths requires at least one path"
      STAGE_MODE="paths"
      while [[ $# -gt 0 ]]; do
        PATHS+=("$1")
        shift
      done
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

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "Not inside a git worktree"
[[ -f "$CONTRACT_FILE" ]] || fail "Missing active contract: $CONTRACT_FILE"

HARNESS_DIR="$HARNESS_DIR" bash "$SCRIPT_DIR/closed_loop.sh" --require-contract

if [[ -z "$MESSAGE" ]]; then
  goal_line="$(awk '
    /^## Goal$/ { in_goal=1; next }
    /^## / && in_goal { exit }
    in_goal && NF { print; exit }
  ' "$CONTRACT_FILE")"
  goal_line="$(printf '%s' "$goal_line" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  [[ -n "$goal_line" ]] || goal_line="closed-loop update"
  MESSAGE="Closed loop: $goal_line"
fi

case "$STAGE_MODE" in
  all)
    git add -A
    ;;
  staged-only)
    ;;
  paths)
    git add -A -- "${PATHS[@]}"
    ;;
  *)
    fail "Unknown staging mode: $STAGE_MODE"
    ;;
esac

if git diff --cached --quiet --ignore-submodules --; then
  echo "[OK] No staged changes to commit"
  exit 0
fi

git commit -m "$MESSAGE"
echo "[OK] Created local commit: $MESSAGE"
