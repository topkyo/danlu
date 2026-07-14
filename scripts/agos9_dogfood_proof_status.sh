#!/usr/bin/env bash
# Report AGOS-9 live dogfood proof status.
# Writes a local dogfood maturity snapshot via collect --write; never deletes data or prints credentials.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-}"

if [[ -z "$VAULT" ]]; then
  echo "error: AIWIKI_DOGFOOD_VAULT is required" >&2
  exit 1
fi

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
python3 "$PROJECT_ROOT/scripts/dogfood_maturity_gate.py" --root "$VAULT" summarize --days 3 --require-current-day
echo
python3 -m aiwiki.cli --root "$VAULT" advanced llm-telemetry --limit 20
echo
python3 -m aiwiki.cli --root "$VAULT" advanced backend-telemetry --limit 50
