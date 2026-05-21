#!/usr/bin/env bash
# P0 operational proof setup + status (wall-clock maturity remains operator-scheduled).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"

cd "$PROJECT_ROOT"

echo "=== P0 Operational Proof Setup ==="
echo "vault: $VAULT"
echo

if [[ "${AIWIKI_INSTALL_DOGFOOD_MATURITY:-0}" == "1" ]]; then
  AIWIKI_INSTALL_DOGFOOD_MATURITY=1 bash scripts/install_user_service.sh
else
  echo "Tip: AIWIKI_INSTALL_DOGFOOD_MATURITY=1 bash scripts/install_user_service.sh"
  systemctl --user is-active aiwiki-dogfood-maturity.timer 2>/dev/null || echo "timer: not active"
fi

echo
bash scripts/agos9_dogfood_proof_status.sh

echo
python3 "$PROJECT_ROOT/scripts/dogfood_maturity_gate.py" --root "$VAULT" summarize --days 3 || true

echo
echo "P0 wall-clock: run 'bash scripts/run_dogfood_maturity.sh' once per UTC day for 3 days."
echo "Compounding: see docs/AGOS-9-Dogfood-Proof-Runbook.md"
echo "Release audit: bash scripts/agos9_release_audit.sh (after summarize pass)"
