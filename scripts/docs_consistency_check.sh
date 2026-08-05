#!/usr/bin/env bash
# Docs consistency scan for AGOS-004 / P2-B gate + commercial cleanup residuals.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Negative checks below silently "pass" when rg is missing (command-not-found
# exits non-zero, which the if-else reads as "no match"). Fail loudly instead.
if ! command -v rg >/dev/null 2>&1; then
  echo "[FAIL] rg (ripgrep) is required for docs consistency checks" >&2
  exit 1
fi

# GNU mktemp (Linux CI) requires ≥3 trailing X's in the template; macOS
# `mktemp -t name` is different. Use an explicit XXXXXX path for both.
HITS_FILE="$(mktemp "${TMPDIR:-/tmp}/docs-consistency-hits.XXXXXX")"
trap 'rm -f "$HITS_FILE"' EXIT

FAIL=0

check_no_match() {
  local label="$1"
  local pattern="$2"
  shift 2
  if rg -n "$pattern" "$@" >"$HITS_FILE" 2>/dev/null; then
    echo "[FAIL] $label"
    cat "$HITS_FILE"
    FAIL=1
  else
    echo "[OK] $label"
  fi
}

check_exists() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    echo "[OK] $label"
  else
    echo "[FAIL] $label (missing: $path)" >&2
    FAIL=1
  fi
}

# Active SoT must not claim implicit cross-backend fallback.
check_no_match "no implicit cross-backend fallback in README" \
  "automatically fall back to|auto.?fallback.*backend" README.md

# Active ops doc should document explicit backend selection.
if rg -n "opencode-api" docs/Furnace\ Runtime\ Operations.md README.md >/dev/null; then
  echo "[OK] explicit backend docs present"
else
  echo "[FAIL] missing explicit backend documentation" >&2
  FAIL=1
fi

# Post-A5: README/HOME must not link to untracked generated wiki/indexes pages.
check_no_match "README does not hard-link generated wiki/indexes pages" \
  "wiki/indexes/(furnace-center|execution-center|review-center|graph-view|protocols|review-queue)" \
  README.md HOME.md

# D4 structural gate: developer content lives in docs/DEVELOPER.md.
check_exists "docs/DEVELOPER.md exists" "docs/DEVELOPER.md"
check_no_match "README has no owner map section" \
  "^## 当前 runtime 实现" README.md
check_no_match "README has no Developer Guide section" \
  "^### Developer Guide" README.md

# Commercial pack presence.
for path in \
  LICENSE \
  CHANGELOG.md \
  docs/INSTALL.md \
  docs/USER_GUIDE.md \
  docs/commercial/PRICING.md \
  docs/commercial/BOUNDARIES.md \
  docs/commercial/PRIVACY.md \
  docs/commercial/SUPPORT.md \
  docs/commercial/COMPARE.md \
  docs/commercial/EULA.md
do
  check_exists "commercial pack: $path" "$path"
done

# Active docs/scripts should not hard-code developer home paths (archive exempt).
if git grep -nE "^/home/" -- scripts/ docs/ ':!docs/archive/' >"$HITS_FILE" 2>/dev/null; then
  echo "[FAIL] no /home/ hard paths in active docs/scripts"
  cat "$HITS_FILE"
  FAIL=1
else
  echo "[OK] no /home/ hard paths in active docs/scripts"
fi

# Active SoT docs must not cite deleted hub modules as current paths.
ACTIVE_DOCS=(
  README.md
  docs/DEVELOPER.md
  docs/AGOS-9-Scorecard.md
  "docs/Furnace Agent Architecture.md"
  "docs/Furnace Evolution Mechanics.md"
  "docs/Furnace Runtime Operations.md"
  docs/USER_GUIDE.md
  docs/INSTALL.md
)
for doc in "${ACTIVE_DOCS[@]}"; do
  check_no_match "no legacy hub paths in $doc" \
    'src/aiwiki/app_[a-z_]+\.py|src/aiwiki/drop\.py\b' \
    "$doc"
done

# Verify-gate count pins: keep verify.sh usage and SoT docs in sync with the
# real test counts. Update these pins whenever test counts change.
check_match() {
  local label="$1"
  local pattern="$2"
  local file="$3"
  if rg -q "$pattern" "$file" 2>/dev/null; then
    echo "[OK] $label"
  else
    echo "[FAIL] $label (missing /$pattern/ in $file)" >&2
    FAIL=1
  fi
}

check_match "verify.sh usage pins acceptance 24" 'acceptance \(24\)' scripts/verify.sh
# Pin the per-target usage line (not only the `all` summary) so a stale
# "83 tests" description cannot hide behind `llm-integration (85)` on `all`.
check_match "verify.sh usage line pins llm-integration 85 tests" 'Run LLM integration tests \(85 tests' scripts/verify.sh
check_match "verify.sh all line pins llm-integration 85" 'llm-integration \(85\)' scripts/verify.sh
check_match "AGENTS.md pins acceptance 24" 'acceptance 24 fixture replay' AGENTS.md
check_match "AGENTS.md pins llm 85" 'LLM integration 85' AGENTS.md
check_match "AGENTS.md pins unit 166" 'unit 166' AGENTS.md
check_match "AGENTS.md pins Jest 203" 'Jest 203' AGENTS.md
check_match "Scorecard pins llm 85" 'LLM integration \| \*\*85\*\* passed' docs/AGOS-9-Scorecard.md
check_match "Scorecard pins unit 166" 'Unit（library 级） \| \*\*166\*\* passed' docs/AGOS-9-Scorecard.md
check_match "Scorecard pins Jest 203" 'Product Shell Jest \| \*\*203\*\* passed' docs/AGOS-9-Scorecard.md
check_match "DEVELOPER.md pins llm 85" '\*\*85\*\* tests' docs/DEVELOPER.md
check_match "DEVELOPER.md pins unit 166" '\*\*166\*\* tests' docs/DEVELOPER.md
check_match "DEVELOPER.md pins Jest 203" 'Jest \*\*203\*\*' docs/DEVELOPER.md
check_match "Post-Cleanup §1 pins unit 166" 'unit \*\*166\*\*' "docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md"
check_match "CHANGELOG Unreleased pins unit 166" 'unit \*\*166\*\*' CHANGELOG.md
check_match "Scorecard pins coverage 71%" 'Coverage \| \*\*71%\*\*' docs/AGOS-9-Scorecard.md
check_match "DEVELOPER.md pins coverage 71%" '实测全量 \*\*71%\*\*' docs/DEVELOPER.md

# Layering: content ↛ memory; memory ↛ content; corpus ↛ content/memory
if rg -n 'from \.\.memory|from aiwiki\.memory' src/aiwiki/content --glob '*.py' >/dev/null 2>&1; then
  echo "[FAIL] content must not import memory" >&2
  FAIL=1
else
  echo "[OK] content ↛ memory"
fi
if rg -n 'from \.\.content|from aiwiki\.content' src/aiwiki/memory --glob '*.py' >/dev/null 2>&1; then
  echo "[FAIL] memory must not import content" >&2
  FAIL=1
else
  echo "[OK] memory ↛ content"
fi
if rg -n 'from \.\.content|from \.\.memory|from aiwiki\.(content|memory)' src/aiwiki/corpus --glob '*.py' >/dev/null 2>&1; then
  echo "[FAIL] corpus must not import content/memory" >&2
  FAIL=1
else
  echo "[OK] corpus ↛ content/memory"
fi
if rg -n '_CompatModule' src/aiwiki/app_shell/__init__.py src/aiwiki/app_linting/__init__.py >/dev/null 2>&1; then
  echo "[FAIL] app_shell/app_linting __init__ must not contain _CompatModule" >&2
  FAIL=1
else
  echo "[OK] app_shell/app_linting façade cleared"
fi

exit "$FAIL"
