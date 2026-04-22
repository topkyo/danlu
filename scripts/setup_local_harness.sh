#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
HARNESS_ROOT="/home/tim/open-harness"
EXCLUDE_FILE="$PROJECT_ROOT/.git/info/exclude"
LEGACY_MARKER_BEGIN="# >>> aiwiki-local-harness >>>"
LEGACY_MARKER_END="# <<< aiwiki-local-harness <<<"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/setup_local_harness.sh --apply [--tier lite|standard|strict] [--platforms p1,p2,...]
  bash scripts/setup_local_harness.sh --clean
  bash scripts/setup_local_harness.sh --status

This helper keeps generic open-harness scaffold local-only:
- is a convenience alias for /home/tim/open-harness/scripts/bootstrap_local_scaffold.sh
- preserves ai-wiki's local command surface while open-harness owns local-only scaffold behavior
- removes the old aiwiki-local-harness exclude block if it still exists
EOF
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

require_harness_root() {
  [[ -d "$HARNESS_ROOT" ]] || fail "Missing open-harness root: $HARNESS_ROOT"
  [[ -f "$HARNESS_ROOT/scripts/bootstrap_local_scaffold.sh" ]] || fail "Missing bootstrap_local_scaffold.sh: $HARNESS_ROOT/scripts/bootstrap_local_scaffold.sh"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_harness_root

remove_legacy_exclude_block() {
  local tmp=""

  [[ -f "$EXCLUDE_FILE" ]] || return 0
  tmp="$(mktemp)"
  awk -v begin="$LEGACY_MARKER_BEGIN" -v end="$LEGACY_MARKER_END" '
    $0 == begin {skip = 1; next}
    $0 == end {skip = 0; next}
    !skip {print}
  ' "$EXCLUDE_FILE" > "$tmp"
  cp "$tmp" "$EXCLUDE_FILE"
  rm -f -- "$tmp"
}

remove_legacy_exclude_block
cd "$PROJECT_ROOT"
exec bash "$HARNESS_ROOT/scripts/bootstrap_local_scaffold.sh" "$@"
