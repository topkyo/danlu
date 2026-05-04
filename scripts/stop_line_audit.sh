#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash scripts/stop_line_audit.sh [--baseline <git-ref>] [--contract <path>] [--json]

Audits contract Stop Lines against files changed since a git baseline.
EOF
}

die() {
  printf 'stop_line_audit error: %s\n' "$1" >&2
  exit "${2:-2}"
}

baseline=""
contract=".codex/contracts/active.md"
json=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline)
      [[ $# -ge 2 ]] || die "missing value for --baseline"
      baseline="$2"
      shift 2
      ;;
    --contract)
      [[ $# -ge 2 ]] || die "missing value for --contract"
      contract="$2"
      shift 2
      ;;
    --json)
      json=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $1"
      ;;
  esac
done

cd "$PROJECT_ROOT"

if [[ -z "$baseline" ]]; then
  # Prefer the current branch's actual upstream over hard-coded origin/main.
  if upstream_ref="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)" \
      && merge_base="$(git merge-base HEAD "$upstream_ref" 2>/dev/null)"; then
    baseline="$merge_base"
  elif merge_base="$(git merge-base HEAD origin/main 2>/dev/null)"; then
    baseline="$merge_base"
  else
    baseline="HEAD~1"
  fi
fi

if [[ ! -f "$contract" ]]; then
  die "ContractNotFound: contract file does not exist: $contract"
fi

if ! baseline_sha="$(git rev-parse --short "$baseline^{commit}" 2>/dev/null)"; then
  die "GitBaselineError: cannot resolve baseline git ref: $baseline"
fi

diff_file="$(mktemp)"
trap 'rm -f "$diff_file"' EXIT

committed_diff="$(git diff --name-only "$baseline..HEAD" 2>&1)" || die "GitDiffError: git diff --name-only $baseline..HEAD failed: $committed_diff"
worktree_diff="$(git diff --name-only "$baseline" 2>&1)" || die "GitDiffError: git diff --name-only $baseline failed: $worktree_diff"
# Untracked-but-not-ignored files are part of the worktree change scope; without
# this, Stop Line audits can be silently bypassed by leaving violating files
# untracked at commit time.
untracked="$(git ls-files --others --exclude-standard 2>&1)" || die "GitLsFilesError: git ls-files --others --exclude-standard failed: $untracked"

{
  printf '%s\n' "$committed_diff"
  printf '%s\n' "$worktree_diff"
  printf '%s\n' "$untracked"
} | python3 -c 'import sys
files = sorted({line.strip() for line in sys.stdin if line.strip()})
for path in files:
    print(path)
' > "$diff_file"

python_args=(
  "$SCRIPT_DIR/stop_line_audit.py"
  --contract "$contract"
  --baseline-label "$baseline"
  --baseline-sha "$baseline_sha"
  --diff-list "$diff_file"
)

if [[ "$json" -eq 1 ]]; then
  python_args+=(--json)
fi

python3 "${python_args[@]}"
