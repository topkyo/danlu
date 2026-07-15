#!/usr/bin/env bash
# Run Product Shell Jest tests. Discover deps from the plugin directory.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRODUCT_SHELL_DIR="$PROJECT_ROOT/.obsidian/plugins/furnace-product-shell"
TEST_DIR="$PRODUCT_SHELL_DIR/src/__tests__"

if [[ ! -d "$TEST_DIR" ]]; then
  echo "[SKIP] No Product Shell test directory: $TEST_DIR"
  exit 0
fi

if [[ ! -d "$PRODUCT_SHELL_DIR" ]]; then
  echo "[FAIL] Product Shell directory missing: $PRODUCT_SHELL_DIR" >&2
  exit 1
fi

cd "$PRODUCT_SHELL_DIR"

jest_available() {
  if [[ -x "$PRODUCT_SHELL_DIR/node_modules/.bin/jest" ]]; then
    return 0
  fi
  npx --no-install jest --version >/dev/null 2>&1
}

jsdom_available() {
  node -e "require.resolve('jest-environment-jsdom')" >/dev/null 2>&1
}

if ! jest_available; then
  if [[ "${AIWIKI_REQUIRE_PRODUCT_SHELL_JS_TESTS:-0}" == "1" ]]; then
    echo "[FAIL] Jest is not installed in $PRODUCT_SHELL_DIR (AIWIKI_REQUIRE_PRODUCT_SHELL_JS_TESTS=1)" >&2
    exit 1
  fi
  echo "[SKIP] Jest is not installed; run 'npm install' in $PRODUCT_SHELL_DIR to enable JS tests"
  exit 0
fi

if ! jsdom_available; then
  if [[ "${AIWIKI_REQUIRE_PRODUCT_SHELL_JS_TESTS:-0}" == "1" ]]; then
    echo "[FAIL] jest-environment-jsdom is not installed in $PRODUCT_SHELL_DIR (AIWIKI_REQUIRE_PRODUCT_SHELL_JS_TESTS=1)" >&2
    exit 1
  fi
  echo "[SKIP] jest-environment-jsdom is not installed; run 'npm install' in $PRODUCT_SHELL_DIR to enable Product Shell JS tests"
  exit 0
fi

TMP_CONFIG="$(mktemp /tmp/furnace-jest.XXXXXX.js)"
RESULTS_JSON="$(mktemp)"
STDERR_LOG="$(mktemp)"
trap 'rm -f "$TMP_CONFIG" "$RESULTS_JSON" "$STDERR_LOG"' EXIT

cat > "$TMP_CONFIG" <<EOF
module.exports = { testEnvironment: 'jsdom', rootDir: '$PRODUCT_SHELL_DIR' };
EOF

set +e
npx --no-install jest --config "$TMP_CONFIG" --json --silent > "$RESULTS_JSON" 2>"$STDERR_LOG"
JEST_EXIT=$?
set -e

if ! node -e "JSON.parse(require('fs').readFileSync('$RESULTS_JSON', 'utf8'))" >/dev/null 2>&1; then
  echo "[FAIL] Product Shell JS tests produced no usable JSON output" >&2
  cat "$STDERR_LOG" >&2 || true
  exit 1
fi

node -e "
const r = JSON.parse(require('fs').readFileSync('$RESULTS_JSON', 'utf8'));
const failed = (r.numFailedTests || 0) + (r.numRuntimeErrorTestSuites || 0);
if (failed > 0 || $JEST_EXIT !== 0) {
  console.error('[FAIL] Product Shell JS tests failed:', failed, 'failures, exit', $JEST_EXIT);
  process.exit(1);
}
console.log('[PASS] Product Shell JS tests:', r.numPassedTests || 0, 'passed');
"
