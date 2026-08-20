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
  "wiki/indexes/(furnace-center|review-center|graph-view|protocols|review-queue)" \
  README.md HOME.md

# Retired index pages must not reappear on Active entry surfaces.
check_no_match "README/HOME do not link retired wiki/indexes pages" \
  "wiki/indexes/(execution-center|Outputs|aging-report|agent-workbench|output-packs|execution-audit|log)" \
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
  docs/commercial/EULA.md \
  CONTRIBUTING.md \
  SECURITY.md \
  .env.example \
  AGENTS.local.md.example \
  NOTICE \
  .gitattributes
do
  check_exists "oss hygiene pack: $path" "$path"
done

# Active docs/scripts should not hard-code developer home paths (archive exempt).
if git grep -nE "^/home/" -- scripts/ docs/ ':!docs/archive/' >"$HITS_FILE" 2>/dev/null; then
  echo "[FAIL] no /home/ hard paths in active docs/scripts"
  cat "$HITS_FILE"
  FAIL=1
else
  echo "[OK] no /home/ hard paths in active docs/scripts"
fi

# Maintainer home / iCloud vault paths belong in gitignored AGENTS.local.md.
# Do not scan docs/archive, docs/plans, CHANGELOG, or PROGRESS (historical).
check_no_match "no maintainer /Users/ht paths on public surfaces" \
  '/Users/ht' \
  AGENTS.md README.md HOME.md CONTRIBUTING.md SECURITY.md .env.example \
  AGENTS.local.md.example src docs/INSTALL.md docs/USER_GUIDE.md \
  docs/DEVELOPER.md docs/README.md docs/commercial \
  scripts/sync_product_shell_to_vault.sh \
  scripts/relocate_aiwiki_state_out_of_icloud.sh \
  "docs/Furnace Agent Architecture.md" \
  "docs/Furnace Evolution Mechanics.md" \
  "docs/Furnace Runtime Operations.md" \
  "docs/Furnace Product Shell.md" \
  "docs/Furnace Elixir.md"
check_no_match "no iCloud vault paths on public surfaces" \
  'iCloud~md~obsidian' \
  AGENTS.md README.md HOME.md CONTRIBUTING.md SECURITY.md .env.example \
  AGENTS.local.md.example src docs/INSTALL.md docs/USER_GUIDE.md \
  docs/DEVELOPER.md docs/README.md docs/commercial \
  scripts/sync_product_shell_to_vault.sh \
  scripts/relocate_aiwiki_state_out_of_icloud.sh \
  "docs/Furnace Agent Architecture.md" \
  "docs/Furnace Evolution Mechanics.md" \
  "docs/Furnace Runtime Operations.md" \
  "docs/Furnace Product Shell.md" \
  "docs/Furnace Elixir.md"

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

check_match "verify.sh usage pins acceptance 25" 'acceptance \(25\)' scripts/verify.sh
# Pin the per-target usage line (not only the `all` summary) so a stale
# "83 tests" description cannot hide behind `llm-integration (84)` on `all`.
check_match "verify.sh usage line pins llm-integration 88 tests" 'Run LLM integration tests \(88 tests' scripts/verify.sh
check_match "verify.sh all line pins llm-integration 88" 'llm-integration \(88\)' scripts/verify.sh
check_match "AGENTS.md pins acceptance 25" 'acceptance 25 fixture replay' AGENTS.md
check_match "AGENTS.md pins llm 88" 'LLM integration 88' AGENTS.md
check_match "AGENTS.md pins unit 172" 'unit 172' AGENTS.md
check_no_match "AGENTS.md does not pin stale unit 176 in verify summary" \
  '\+ \*\*176\*\* unit' AGENTS.md
check_match "AGENTS.md pins Jest 209" 'Jest 209' AGENTS.md
check_match "Scorecard pins llm 88" 'LLM integration \| \*\*88\*\* passed' docs/AGOS-9-Scorecard.md
check_match "Scorecard pins acceptance 25" 'Acceptance \| \*\*25\*\* passed' docs/AGOS-9-Scorecard.md
check_match "Scorecard pins unit 172" 'Unit（library 级） \| \*\*172\*\* passed' docs/AGOS-9-Scorecard.md
check_match "Scorecard pins Jest 209" 'Product Shell Jest \| \*\*209\*\* passed' docs/AGOS-9-Scorecard.md
check_match "DEVELOPER.md pins acceptance 25" '\*\*25\*\* tests — `tests/test_acceptance_loop.py`' docs/DEVELOPER.md
check_match "DEVELOPER.md pins llm 88" '\*\*88\*\* tests' docs/DEVELOPER.md
check_match "DEVELOPER.md pins unit 172" '\*\*172\*\* tests' docs/DEVELOPER.md
check_match "DEVELOPER.md pins Jest 209" 'Jest \*\*209\*\*' docs/DEVELOPER.md
POST_CLEANUP="docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md"
if [[ -f "$POST_CLEANUP" ]]; then
  check_match "Post-Cleanup §1 pins acceptance 25" 'acceptance \*\*25\*\*' "$POST_CLEANUP"
  check_match "Post-Cleanup §1 pins unit 172" 'unit \*\*172\*\*' "$POST_CLEANUP"
else
  echo "[OK] Post-Cleanup pins skipped (file not in this tree)"
fi
check_match "CHANGELOG Unreleased pins acceptance 25" 'acceptance \*\*25\*\*' CHANGELOG.md
check_match "CHANGELOG Unreleased pins unit 172" 'unit \*\*172\*\*' CHANGELOG.md
check_match "Scorecard pins coverage 71%" 'Coverage \| \*\*71%\*\*' docs/AGOS-9-Scorecard.md
check_match "DEVELOPER.md pins coverage 71%" '实测全量 \*\*71%\*\*' docs/DEVELOPER.md

# Single-entry drift guards (2026-08-12): the launcher script is retired and
# must not reappear; vault README/HOME templates only carry vault-local facts
# (no launcher commands, no backend-routing narrative); active entry docs must
# not point users at the deleted launcher.
if [[ -e scripts/aiwiki-launcher.sh ]]; then
  echo "[FAIL] scripts/aiwiki-launcher.sh must stay deleted" >&2
  FAIL=1
else
  echo "[OK] scripts/aiwiki-launcher.sh stays deleted"
fi
check_no_match "active entry docs carry no launcher refs" \
  'aiwiki-launcher' README.md HOME.md docs/INSTALL.md docs/USER_GUIDE.md AGENTS.md
check_no_match "vault templates carry no launcher refs" \
  'aiwiki-launcher' src/aiwiki/vault/templates.py
check_no_match "vault templates carry no backend routing narrative" \
  'opencode' src/aiwiki/vault/templates.py

# Product default model pin (2026-08-12 ask-web-research): runtime constant is flash.
check_match "config.py pins DEFAULT_DEEPSEEK_MODEL flash" \
  'DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"' src/aiwiki/config.py
check_match "AGENTS.md documents default flash route" \
  'deepseek-api/deepseek-v4-flash' AGENTS.md
check_no_match "active SoT does not claim pro as product default" \
  'deepseek-api/deepseek-v4-pro.*\*\*产品默认\*\*|deepseek-api \+ `deepseek-v4-pro`.*产品默认|只承诺 `deepseek-api/deepseek-v4-pro`|The default LLM route is DeepSeek.*\(`deepseek-api` \+ `deepseek-v4-pro`\)' \
  AGENTS.md README.md docs/INSTALL.md docs/DEVELOPER.md "docs/Furnace Runtime Operations.md"

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
if rg -n 'from \.\.execution|from aiwiki\.execution' src/aiwiki/memory --glob '*.py' >/dev/null 2>&1; then
  echo "[FAIL] memory must not import execution" >&2
  FAIL=1
else
  echo "[OK] memory ↛ execution"
fi
for facade_path in src/aiwiki/memory/scoring.py src/aiwiki/memory/action_rank.py; do
  if [[ -e "$facade_path" ]]; then
    echo "[FAIL] memory facade resurrection: $facade_path must not exist" >&2
    FAIL=1
  else
    echo "[OK] memory facade absent: $facade_path"
  fi
done
if rg -n '_CompatModule' src/aiwiki/app_shell/__init__.py src/aiwiki/app_linting/__init__.py >/dev/null 2>&1; then
  echo "[FAIL] app_shell/app_linting __init__ must not contain _CompatModule" >&2
  FAIL=1
else
  echo "[OK] app_shell/app_linting façade cleared"
fi

exit "$FAIL"
