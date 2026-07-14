#!/usr/bin/env bash
# Verify furnace-product-shell main.js matches a fresh build.sh output.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="$PROJECT_ROOT/.obsidian/plugins/furnace-product-shell"
MAIN_JS="$PLUGIN_DIR/main.js"
EXPECTED="$(mktemp "${TMPDIR:-/tmp}/furnace-main-expected.XXXXXX.js")"

cleanup() {
  rm -f "$EXPECTED"
}
trap cleanup EXIT

if [[ ! -f "$PLUGIN_DIR/build.sh" ]]; then
  echo "[FAIL] missing build.sh: $PLUGIN_DIR/build.sh" >&2
  exit 1
fi

if [[ ! -f "$MAIN_JS" ]]; then
  echo "[FAIL] missing bundle: $MAIN_JS (run: bash .obsidian/plugins/furnace-product-shell/build.sh)" >&2
  exit 1
fi

OUT="$EXPECTED" bash "$PLUGIN_DIR/build.sh" >/dev/null

if python3 - "$MAIN_JS" "$EXPECTED" <<'PY'
from pathlib import Path
import sys


def normalized(path: str) -> bytes:
    return Path(path).read_bytes().rstrip(b"\n") + b"\n"


sys.exit(0 if normalized(sys.argv[1]) == normalized(sys.argv[2]) else 1)
PY
then
  echo "[OK] Product Shell bundle matches build.sh output"
  exit 0
fi

echo "[FAIL] Product Shell bundle drift detected." >&2
echo "  expected: fresh build.sh output" >&2
echo "  actual:   $MAIN_JS" >&2
echo "  fix:      bash .obsidian/plugins/furnace-product-shell/build.sh" >&2
exit 1
