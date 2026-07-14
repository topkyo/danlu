#!/usr/bin/env bash
# P1+P2 gate review before starting P0 wall-clock dogfood proof.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== P1+P2 Gate Review ==="

bash scripts/verify.sh
bash scripts/product_shell_smoke.sh

WF_LOC="$(wc -l < src/aiwiki/runner/workflows.py | tr -d ' ')"
echo "workflows.py LOC=$WF_LOC"
if [[ "$WF_LOC" -ge 2100 ]]; then
  echo "[FAIL] workflows.py still >= 2100 LOC" >&2
  exit 1
fi

BACKEND_PROBE_STRICT="${BACKEND_PROBE_STRICT:-0}" bash scripts/backend_probe_matrix.sh
bash scripts/investing_dogfood_preflight.sh

echo
echo "[OK] P1+P2 gate passed — safe to start P0 operational proof (3 UTC-day wall-clock)"
