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
  scripts               Check project shell scripts only.
  python-static         Run Python lint and bytecode compile checks.
  unit                  Run Python unit tests without coverage reporting.
  acceptance            Run acceptance replay checks.
  cli-smoke             Check aiwiki CLI startup/help.
  product-shell-static  Run Product Shell JavaScript syntax checks.
  all                   Run the full project verification suite. Default.
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
  local script=""

  for script in scripts/*.sh; do
    [[ -e "$script" ]] || continue
    bash -n "$script"
  done
  for script in scripts/*.py; do
    [[ -e "$script" ]] || continue
    python3 -m py_compile "$script"
  done
  bash scripts/docs_consistency_check.sh
}

verify_python_static() {
  python3 -m ruff check src tests
  python3 -m compileall src tests >/dev/null
}

verify_unit() {
  python3 -m unittest discover -s tests -p 'test_*.py'
}

verify_acceptance() {
  bash scripts/run_acceptance.sh
}

verify_cli_smoke() {
  python3 -m aiwiki.cli --help >/dev/null
}

verify_product_shell_static() {
  local product_shell_dir=".obsidian/plugins/furnace-product-shell"
  local file=""

  if [[ ! -d "$product_shell_dir" ]]; then
    echo "Product Shell directory not found: $product_shell_dir" >&2
    return 1
  fi

  bash "$SCRIPT_DIR/check_product_shell_bundle.sh"

  if ! command -v node >/dev/null 2>&1; then
    echo "node is required for target: product-shell-static" >&2
    return 1
  fi

  while IFS= read -r -d '' file; do
    node --check "$file" >/dev/null
  done < <(find "$product_shell_dir" \
    \( -path "$product_shell_dir/node_modules" -o -path "$product_shell_dir/.git" \) -prune \
    -o -name '*.js' -print0)
}

case "$TARGET" in
  scripts)
    verify_scripts
    exit 0
    ;;
  python-static)
    verify_python_static
    exit 0
    ;;
  unit)
    verify_unit
    exit 0
    ;;
  acceptance)
    verify_acceptance
    exit 0
    ;;
  cli-smoke)
    verify_cli_smoke
    exit 0
    ;;
  product-shell-static)
    verify_product_shell_static
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

verify_python_static
python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tests -p 'test_*.py'
python3 -m coverage report --skip-covered --fail-under=92
verify_cli_smoke
verify_acceptance
