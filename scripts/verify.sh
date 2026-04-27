#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src"

bash -n scripts/run_watch.sh
bash -n scripts/run_nightly.sh
bash -n scripts/configure_local_worktree.sh
bash -n scripts/setup_local_harness.sh
bash -n scripts/install_user_service.sh
bash -n scripts/uninstall_user_service.sh
python3 -m ruff check src tests
python3 -m compileall src tests >/dev/null
python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tests -p 'test_*.py'
python3 -m coverage report --skip-covered
python3 -m aiwiki.cli --help >/dev/null
bash scripts/run_acceptance.sh
