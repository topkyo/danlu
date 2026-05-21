#!/usr/bin/env bash
# Report AGOS-9 live dogfood proof status (read-only except optional collect --write).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"

if [[ ! -d "$VAULT" ]]; then
  echo "[FAIL] dogfood vault missing: $VAULT" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== AGOS-9 Dogfood Proof Status ==="
echo "vault: $VAULT"
echo

python3 "$PROJECT_ROOT/scripts/dogfood_maturity_gate.py" --root "$VAULT" collect --write
echo
python3 "$PROJECT_ROOT/scripts/dogfood_maturity_gate.py" --root "$VAULT" summarize --recent 3
echo
python3 -m aiwiki.cli --root "$VAULT" llm-telemetry --limit 20
echo
python3 -m aiwiki.cli --root "$VAULT" backend-telemetry --limit 50
