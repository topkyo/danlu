#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/configure_local_worktree.sh --apply [--repo-root PATH]
  bash scripts/configure_local_worktree.sh --undo [--repo-root PATH]
  bash scripts/configure_local_worktree.sh --status [--repo-root PATH]

This helper only affects the current git repository:
- tracked runtime files are hidden via skip-worktree
- local-only runtime paths are hidden via .git/info/exclude
EOF
}

ACTION=""
REPO_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply|--undo|--status)
      if [[ -n "$ACTION" ]]; then
        echo "Only one action may be specified." >&2
        exit 1
      fi
      ACTION="${1#--}"
      shift
      ;;
    --repo-root)
      REPO_ROOT="${2:-}"
      if [[ -z "$REPO_ROOT" ]]; then
        echo "--repo-root requires a path." >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$ACTION" ]]; then
  usage >&2
  exit 1
fi

resolve_repo_root() {
  if [[ -n "$REPO_ROOT" ]]; then
    (cd "$REPO_ROOT" && pwd)
  else
    git rev-parse --show-toplevel
  fi
}

ROOT="$(resolve_repo_root)"
if ! git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "Not a git repository: $ROOT" >&2
  exit 1
fi

MARKER_BEGIN="# >>> aiwiki-local-worktree >>>"
MARKER_END="# <<< aiwiki-local-worktree <<<"
EXCLUDE_FILE="$ROOT/.git/info/exclude"
STATE_FILE="$ROOT/.git/info/aiwiki-local-worktree.state"

TRACKED_RUNTIME_FILES=(
  ".obsidian/app.json"
  ".obsidian/core-plugins.json"
  ".obsidian/workspace.json"
  "wiki/indexes/compile-status.md"
  "wiki/indexes/sources.md"
  "wiki/indexes/concepts.md"
  "wiki/indexes/decisions.md"
  "wiki/indexes/judgments.md"
  "wiki/indexes/index.md"
  "wiki/indexes/log.md"
  "wiki/indexes/machine-memory.md"
  "wiki/indexes/graph-health.md"
  "wiki/indexes/drift-report.md"
  "wiki/indexes/repair-backlog.md"
  "wiki/indexes/review-queue.md"
)

LOCAL_EXCLUDE_PATTERNS=(
  ".obsidian/appearance.json"
  ".obsidian/graph.json"
  "raw/"
  "wiki/sources/"
  "wiki/concepts/"
  "wiki/indexes/agent-workbench.md"
  "wiki/indexes/aging-report.md"
  "wiki/indexes/cognitive-history.md"
  "wiki/indexes/domain-pilots.md"
  "wiki/indexes/execution-audit.md"
  "wiki/indexes/execution-center.md"
  "wiki/indexes/machine-memory-topology.md"
  "wiki/indexes/output-packs.md"
  "*.canvas"
)

ensure_parent_dir() {
  mkdir -p -- "$(dirname "$1")"
}

remove_exclude_block() {
  local source_file="$1"
  local target_file="$2"
  if [[ ! -f "$source_file" ]]; then
    : >"$target_file"
    return
  fi
  awk -v begin="$MARKER_BEGIN" -v end="$MARKER_END" '
    $0 == begin {skip = 1; next}
    $0 == end {skip = 0; next}
    !skip {print}
  ' "$source_file" >"$target_file"
}

write_exclude_block() {
  local clean_file="$1"
  cp "$clean_file" "$EXCLUDE_FILE"
  if [[ -s "$EXCLUDE_FILE" ]]; then
    printf '\n' >>"$EXCLUDE_FILE"
  fi
  printf '%s\n' "$MARKER_BEGIN" >>"$EXCLUDE_FILE"
  for pattern in "${LOCAL_EXCLUDE_PATTERNS[@]}"; do
    printf '%s\n' "$pattern" >>"$EXCLUDE_FILE"
  done
  printf '%s\n' "$MARKER_END" >>"$EXCLUDE_FILE"
}

is_tracked() {
  local path="$1"
  git -C "$ROOT" ls-files --error-unmatch -- "$path" >/dev/null 2>&1
}

set_skip_state() {
  local flag="$1"
  local path="$2"
  if is_tracked "$path"; then
    git -C "$ROOT" update-index "$flag" -- "$path"
  fi
}

tracked_state() {
  local path="$1"
  if ! is_tracked "$path"; then
    printf 'missing'
    return
  fi
  local line
  line="$(git -C "$ROOT" ls-files -v -- "$path")"
  case "${line%% *}" in
    S) printf 'skip-worktree' ;;
    *) printf 'tracked' ;;
  esac
}

exclude_block_present() {
  [[ -f "$EXCLUDE_FILE" ]] && grep -Fqx "$MARKER_BEGIN" "$EXCLUDE_FILE"
}

tracked_head_oid() {
  local path="$1"
  if ! is_tracked "$path"; then
    printf 'missing'
    return
  fi
  git -C "$ROOT" rev-parse --verify "HEAD:$path" 2>/dev/null || printf 'missing'
}

write_state_file() {
  : >"$STATE_FILE"
  for path in "${TRACKED_RUNTIME_FILES[@]}"; do
    printf '%s\t%s\n' "$path" "$(tracked_head_oid "$path")" >>"$STATE_FILE"
  done
}

baseline_oid() {
  local path="$1"
  if [[ ! -f "$STATE_FILE" ]]; then
    printf 'unknown'
    return
  fi
  local line
  line="$(awk -F '\t' -v target="$path" '$1 == target {print $2; exit}' "$STATE_FILE")"
  if [[ -n "$line" ]]; then
    printf '%s' "$line"
  else
    printf 'unknown'
  fi
}

drift_state() {
  local path="$1"
  local baseline
  local current
  baseline="$(baseline_oid "$path")"
  current="$(tracked_head_oid "$path")"
  if [[ "$baseline" == "unknown" ]]; then
    printf 'unknown'
    return
  fi
  if [[ "$baseline" == "$current" ]]; then
    printf 'aligned'
  else
    printf 'repo-drift'
  fi
}

apply_config() {
  local tmp
  ensure_parent_dir "$EXCLUDE_FILE"
  ensure_parent_dir "$STATE_FILE"
  tmp="$(mktemp)"
  remove_exclude_block "$EXCLUDE_FILE" "$tmp"
  write_exclude_block "$tmp"
  rm -f -- "$tmp"
  for path in "${TRACKED_RUNTIME_FILES[@]}"; do
    set_skip_state --skip-worktree "$path"
  done
  write_state_file
  echo "Applied local worktree hygiene for $ROOT"
}

undo_config() {
  local tmp
  ensure_parent_dir "$EXCLUDE_FILE"
  tmp="$(mktemp)"
  remove_exclude_block "$EXCLUDE_FILE" "$tmp"
  mv -- "$tmp" "$EXCLUDE_FILE"
  for path in "${TRACKED_RUNTIME_FILES[@]}"; do
    set_skip_state --no-skip-worktree "$path"
  done
  rm -f -- "$STATE_FILE"
  echo "Removed local worktree hygiene for $ROOT"
}

status_config() {
  echo "repo_root=$ROOT"
  if exclude_block_present; then
    echo "exclude_block=present"
  else
    echo "exclude_block=absent"
  fi
  if [[ -f "$STATE_FILE" ]]; then
    echo "baseline_state=present"
  else
    echo "baseline_state=absent"
  fi
  echo "tracked_runtime:"
  for path in "${TRACKED_RUNTIME_FILES[@]}"; do
    printf '  %s: %s %s\n' "$path" "$(tracked_state "$path")" "$(drift_state "$path")"
  done
}

case "$ACTION" in
  apply) apply_config ;;
  undo) undo_config ;;
  status) status_config ;;
esac
