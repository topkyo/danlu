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

if SUMMARY="$(python3 scripts/dogfood_maturity_gate.py --root "$VAULT" summarize --days 3 --require-current-day)"; then
  echo "[OK] strict maturity summary command pass"
else
  echo "[FAIL] strict maturity summary command failed" >&2
  FAIL=1
fi
echo "$SUMMARY"
if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); sys.exit(0 if payload.get("status") == "pass" else 1)' "$SUMMARY"; then
  echo "[OK] strict maturity summary pass"
else
  echo "[FAIL] strict maturity summary status not pass" >&2
  FAIL=1
fi
if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); sys.exit(0 if payload.get("freshness_status") == "pass" else 1)' "$SUMMARY"; then
  echo "[OK] freshness pass"
else
  echo "[FAIL] freshness not pass" >&2
  FAIL=1
fi
if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); snapshot=payload.get("snapshot_consistency", {}); sys.exit(0 if (not snapshot.get("snapshot_newer_than_latest_run") or snapshot.get("status") == "pass") else 1)' "$SUMMARY"; then
  echo "[OK] snapshot consistency pass"
else
  echo "[FAIL] snapshot consistency failed" >&2
  FAIL=1
fi
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
if python3 -c 'import json, sys; payload=json.loads(sys.argv[1]); sys.exit(0 if payload.get("elixir_quality_status") == "pass" else 1)' "$SUMMARY"; then
  echo "[OK] elixir quality proof pass"
else
  echo "[WARN] elixir quality proof not pass yet" >&2
  FAIL=1
fi

LLM_LIMIT="${AIWIKI_RELEASE_LLM_SAMPLE_LIMIT:-50}"
LLM_MIN_SUCCESS_RATE="${AIWIKI_RELEASE_LLM_MIN_SUCCESS_RATE:-0.8}"
LLM_MAX_TIMEOUT_FAILURES="${AIWIKI_RELEASE_LLM_MAX_TIMEOUT_FAILURES:-3}"
LLM_SUMMARY="$(python3 -m aiwiki.cli --root "$VAULT" llm-telemetry --limit "$LLM_LIMIT")"
BACKEND_SUMMARY="$(python3 -m aiwiki.cli --root "$VAULT" backend-telemetry --limit "$LLM_LIMIT")"
echo "$LLM_SUMMARY"
echo "$BACKEND_SUMMARY"
if python3 - "$LLM_SUMMARY" "$BACKEND_SUMMARY" "$LLM_MIN_SUCCESS_RATE" "$LLM_MAX_TIMEOUT_FAILURES" <<'PY'
import json
import sys

llm = json.loads(sys.argv[1])
backend = json.loads(sys.argv[2])
min_success = float(sys.argv[3])
max_timeouts = int(sys.argv[4])
success_rate = llm.get("success_rate")
categories = backend.get("llm_failure_category_counts", {})
auth_failures = int(categories.get("auth") or 0)
timeout_failures = int(categories.get("timeout") or 0)
if success_rate is None:
    raise SystemExit(1)
if float(success_rate) < min_success:
    raise SystemExit(1)
if auth_failures > 0:
    raise SystemExit(1)
if timeout_failures > max_timeouts:
    raise SystemExit(1)
PY
then
  echo "[OK] LLM reliability gate pass"
else
  echo "[FAIL] LLM reliability gate failed" >&2
  FAIL=1
fi

exit "$FAIL"
