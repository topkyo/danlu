#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/.obsidian/plugins/furnace-product-shell/src/__tests__"

if [[ ! -d "$TEST_DIR" ]]; then
  echo "[SKIP] No Product Shell test directory: $TEST_DIR"
  exit 0
fi

if ! npx --no-install jest --version >/dev/null 2>&1; then
  echo "[SKIP] Jest is not installed; run 'npm install jest jest-environment-jsdom' in the Product Shell plugin directory to enable JS tests"
  exit 0
fi

if ! node -e "require.resolve('jest-environment-jsdom')" >/dev/null 2>&1; then
  echo "[SKIP] jest-environment-jsdom is not installed; run 'npm install jest-environment-jsdom' to enable Product Shell JS tests"
  exit 0
fi

PRODUCT_SHELL_DIR="$PROJECT_ROOT/.obsidian/plugins/furnace-product-shell"
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
const fs = require('fs');
const path = require('path');
const results = JSON.parse(fs.readFileSync('$RESULTS_JSON', 'utf8'));
let failed = 0;
results.testResults.forEach((suite) => {
  const status = suite.status === 'passed' ? 'OK' : 'FAIL';
  if (suite.status !== 'passed') failed += 1;
  console.log('[' + status + '] ' + path.basename(suite.name));
});
console.log('Product Shell JS tests: ' + results.testResults.length + ' files, ' + (failed === 0 ? 'all passed' : 'has failures'));
process.exit(failed === 0 ? 0 : 1);
"
