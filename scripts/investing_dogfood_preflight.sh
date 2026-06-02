#!/usr/bin/env bash
# Investing dogfood preflight: llm-check, protocol, vault layout. Does NOT start maturity clock.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"
SMOKE_DROP=0

usage() {
  echo "Usage: $0 [--smoke-drop-markdown]" >&2
  echo "  --smoke-drop-markdown  drop a test markdown material + compile (no maturity receipt)" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke-drop-markdown|--smoke-drop-note) SMOKE_DROP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -d "$VAULT" ]]; then
  echo "[FAIL] vault missing: $VAULT" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== Investing Dogfood Preflight ==="
echo "vault: $VAULT"
echo

python3 -m aiwiki.cli --root "$VAULT" llm-check --probe --format human
echo

python3 -m aiwiki.cli --root "$VAULT" protocol-set investing
python3 -m aiwiki.cli --root "$VAULT" protocol-status
echo

for path in wiki/judgments schema prompts/ask.md; do
  if [[ ! -e "$VAULT/$path" ]]; then
    echo "[FAIL] missing vault path: $path" >&2
    exit 1
  fi
  echo "[OK] $path"
done

if [[ "$SMOKE_DROP" == "1" ]]; then
  NOTE_TITLE="preflight-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
  python3 -m aiwiki.cli --root "$VAULT" drop markdown --title "$NOTE_TITLE" --text "investing preflight smoke material"
  python3 -m aiwiki.cli --root "$VAULT" compile --deterministic-only
  echo "[OK] smoke drop+compile"
fi

echo
echo "[OK] investing preflight complete (this is NOT maturity/compounding pass)"
