#!/usr/bin/env bash
# AGOS-009 release audit helper (read-only checks).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

FAIL=0
check() {
  if "$@"; then
    echo "[OK] $*"
  else
    echo "[FAIL] $*" >&2
    FAIL=1
  fi
}

echo "=== AGOS-9 Release Audit ==="

check bash scripts/verify.sh product-shell-static
check bash scripts/docs_consistency_check.sh

SUMMARY="$(python3 scripts/dogfood_maturity_gate.py --root "$VAULT" summarize --days 3)"
echo "$SUMMARY"
if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); sys.exit(0 if payload.get("operational_maturity", {}).get("status") == "pass" else 1)' "$SUMMARY"; then
  echo "[OK] operational maturity pass path visible"
else
  echo "[WARN] operational_maturity not pass yet (expected until 3 UTC days)" >&2
  FAIL=1
fi

if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); sys.exit(0 if payload.get("knowledge_compounding_proof", {}).get("status") == "pass" else 1)' "$SUMMARY"; then
  echo "[OK] compounding proof pass"
else
  echo "[WARN] compounding proof not pass yet" >&2
  FAIL=1
fi

exit "$FAIL"
