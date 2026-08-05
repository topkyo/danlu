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
  unit                  Run library-level unit tests (security / vault / library surfaces / repair / alchemy-revert).
  acceptance            Run acceptance replay checks.
  llm-integration       Run LLM integration tests (85 tests, mock backends).
  cli-smoke             Check aiwiki CLI startup/help.
  product-shell-static  Run Product Shell JS syntax + bundle drift gate + Jest.
  coverage              Print coverage report over all tests (informational, no gate).
  all                   Run scripts + product-shell-static + cli-smoke + smoke + python-static + unit + acceptance (24) + llm-integration (85) + coverage report. Default.
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

verify_llm_integration() {
  "$PYTHON" -m pytest tests/test_llm_integration.py -q
}

verify_unit() {
  "$PYTHON" -m pytest \
    tests/test_security.py \
    tests/test_vault_plugin.py \
    tests/test_library_surfaces.py \
    tests/test_repair.py \
    tests/test_alchemy_revert.py \
    -q
}

# Informational only: prints a coverage report over the full test suite.
# Never gates (no threshold); if coverage is not installed, skips with a note.
verify_coverage() {
  if ! "$PYTHON" -m coverage --version >/dev/null 2>&1; then
    echo "coverage not installed; skipping coverage report (pip install -e '.[dev]')"
    return 0
  fi
  "$PYTHON" -m coverage run --source=src/aiwiki -m pytest \
    tests/test_acceptance_loop.py tests/test_llm_integration.py \
    tests/test_security.py tests/test_vault_plugin.py tests/test_library_surfaces.py \
    tests/test_repair.py tests/test_alchemy_revert.py -q
  "$PYTHON" -m coverage report | tail -n 5
}

verify_cli_smoke() {
  "$PYTHON" -m aiwiki.cli --help >/dev/null
  # Top-level operator verbs must fail (no legacy argv rewrite).
  if "$PYTHON" -m aiwiki.cli compile >/dev/null 2>&1; then
    echo "expected top-level 'compile' to be rejected" >&2
    return 1
  fi
}

verify_smoke() {
  local tmp
  tmp="$(mktemp -d)"
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

  # Bundle drift hard-gate: committed main.js must equal a fresh build of src/.
  # The bundle is the only file Obsidian actually loads and the only file
  # sync_product_shell_plugin distributes, so it must never diverge from src/.
  local bundle_out=""
  bundle_out="$(mktemp "${TMPDIR:-/tmp}/furnace-mainjs.XXXXXX")"
  if ! OUT="$bundle_out" bash "$product_shell_dir/build.sh" >/dev/null; then
    rm -f "$bundle_out"
    echo "Product Shell build.sh failed; cannot verify bundle freshness" >&2
    return 1
  fi
  if ! diff -q "$bundle_out" "$product_shell_dir/main.js" >/dev/null; then
    rm -f "$bundle_out"
    echo "main.js has drifted from src/; run 'bash $product_shell_dir/build.sh' and commit the result" >&2
    return 1
  fi
  rm -f "$bundle_out"

  # Jest hard-gate (package.json tracked). Set AIWIKI_SKIP_PRODUCT_SHELL_JS_TESTS=1 only for emergency local bypass.
  if [[ "${AIWIKI_SKIP_PRODUCT_SHELL_JS_TESTS:-}" == "1" ]]; then
    echo "warning: skipping Product Shell Jest (AIWIKI_SKIP_PRODUCT_SHELL_JS_TESTS=1)" >&2
    return 0
  fi
  if [[ ! -f "$product_shell_dir/package.json" ]]; then
    echo "Product Shell package.json missing; cannot hard-gate Jest" >&2
    return 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required for Product Shell Jest hard-gate" >&2
    return 1
  fi
  (
    cd "$product_shell_dir"
    if [[ -f package-lock.json ]]; then
      npm ci --silent
    else
      npm install --silent
    fi
    npm test
  )
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
  llm-integration)
    verify_llm_integration
    exit 0
    ;;
  unit)
    verify_unit
    exit 0
    ;;
  coverage)
    verify_coverage
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
verify_unit
verify_acceptance
verify_llm_integration
verify_coverage
