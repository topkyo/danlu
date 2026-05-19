#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src"

usage() {
  cat <<'USAGE'
Usage: scripts/verify.sh [target]

Targets:
  scripts  Check project shell scripts only.
  all      Run the full project verification suite. Default.
USAGE
}

TARGET="${1:-all}"
if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ "$TARGET" == "-h" || "$TARGET" == "--help" ]]; then
  usage
  exit 0
fi

verify_scripts() {
  bash -n scripts/run_watch.sh
  bash -n scripts/run_nightly.sh
  bash -n scripts/configure_local_worktree.sh
  bash -n scripts/setup_local_harness.sh
  bash -n scripts/install_user_service.sh
  bash -n scripts/uninstall_user_service.sh
}

case "$TARGET" in
  scripts)
    verify_scripts
    exit 0
    ;;
  all|full)
    verify_scripts
    ;;
  *)
    echo "Unknown verify target: $TARGET" >&2
    usage >&2
    exit 2
    ;;
esac

python3 -m ruff check src tests
python3 -m compileall src tests >/dev/null
python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tests -p 'test_*.py'
python3 -m coverage report --skip-covered --fail-under=92
python3 -m aiwiki.cli --help >/dev/null
bash scripts/run_acceptance.sh
