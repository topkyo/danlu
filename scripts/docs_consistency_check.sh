#!/usr/bin/env bash
# Docs consistency scan for AGOS-004 / P2-B gate.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

FAIL=0

check_no_match() {
  local label="$1"
  local pattern="$2"
  local glob="$3"
  if rg -n "$pattern" $glob >/tmp/docs-consistency-hits.txt 2>/dev/null; then
    echo "[FAIL] $label"
    cat /tmp/docs-consistency-hits.txt
    FAIL=1
  else
    echo "[OK] $label"
  fi
}

# Active SoT must not claim implicit cross-backend fallback.
check_no_match "no implicit cross-backend fallback in README" \
  "automatically fall back to|auto.?fallback.*backend" README.md

# Active ops doc should document explicit backend selection.
if rg -n "opencode-api" docs/Furnace-Optional-Deps-Matrix.md docs/Furnace\ Runtime\ Operations.md README.md >/dev/null; then
  echo "[OK] explicit backend docs present"
else
  echo "[FAIL] missing explicit backend documentation" >&2
  FAIL=1
fi

exit "$FAIL"
