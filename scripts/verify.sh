#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src"
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

usage() {
  cat <<'USAGE'
Usage: scripts/verify.sh [target]

Targets:
  scripts               Check project shell scripts only.
  smoke                 Run lightweight aiwiki CLI smoke.
  python-static         Run Python lint and bytecode compile checks.
  acceptance            Run acceptance replay checks.
  cli-smoke             Check aiwiki CLI startup/help.
  product-shell-static  Run Product Shell JavaScript syntax checks.
  all                   Run static + smoke + acceptance (no pytest, no coverage). Default.
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
    "$PYTHON" -m py_compile "$script"
  done
  bash scripts/docs_consistency_check.sh
}

verify_python_static() {
  "$PYTHON" -m ruff check src tests
  "$PYTHON" -m compileall src tests >/dev/null
}

verify_acceptance() {
  bash scripts/run_acceptance.sh
}

verify_cli_smoke() {
  "$PYTHON" -m aiwiki.cli --help >/dev/null
}

verify_smoke() {
  local tmp
  tmp="$(mktemp -d)"
  "$PYTHON" -m aiwiki.cli --root "$tmp" advanced layout 2>/dev/null
  "$PYTHON" -m aiwiki.cli --root "$tmp" drop markdown --title "smoke" --text "smoke test" 2>/dev/null
  "$PYTHON" -m aiwiki.cli --root "$tmp" advanced compile 2>/dev/null
  "$PYTHON" -m aiwiki.cli --root "$tmp" advanced lint 2>/dev/null
  "$PYTHON" -m aiwiki.cli --root "$tmp" today 2>/dev/null
  rm -rf "$tmp"
}

verify_product_shell_static() {
  local product_shell_dir=".obsidian/plugins/furnace-product-shell"
  local file=""

  if [[ ! -d "$product_shell_dir" ]]; then
    echo "Product Shell directory not found: $product_shell_dir" >&2
    return 1
  fi

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
  smoke)
    verify_smoke
    exit 0
    ;;
  python-static)
    verify_python_static
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
    verify_product_shell_static
    verify_cli_smoke
    verify_smoke
    ;;
  *)
    echo "Unknown verify target: $TARGET" >&2
    usage >&2
    exit 2
    ;;
esac

verify_python_static
verify_acceptance
