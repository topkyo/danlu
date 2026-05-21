#!/usr/bin/env bash
# Probe all discovered LLM backends; summarize compatibility (read-only).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT="${AIWIKI_DOGFOOD_VAULT:-${AIWIKI_ROOT:-$PROJECT_ROOT}}"
WRITE_JSON="${BACKEND_PROBE_WRITE:-1}"
PROBE_TIMEOUT="${BACKEND_PROBE_TIMEOUT:-25}"
STRICT="${BACKEND_PROBE_STRICT:-0}"

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -d "$VAULT" ]]; then
  echo "[FAIL] vault missing: $VAULT" >&2
  exit 1
fi

echo "=== Backend Probe Matrix ==="
echo "vault: $VAULT"
echo "timeout: ${PROBE_TIMEOUT}s"
echo "strict: $STRICT"
echo

RESULT_JSON="$(python3 -m aiwiki.cli --root "$VAULT" llm-check --probe-all --format json --probe-timeout "$PROBE_TIMEOUT")"

python3 - <<'PY' "$RESULT_JSON" "$STRICT"
import json
import sys

payload = json.loads(sys.argv[1])
strict = str(sys.argv[2]).strip().lower() in {"1", "true", "yes", "on"}
if not payload.get("configured"):
    level = "FAIL" if strict else "WARN"
    print(f"[{level}] LLM runner not configured (set AIWIKI_LLM_BACKEND / API keys)")
    sys.exit(2 if strict else 0)

probes = payload.get("probes") or []
if not probes and isinstance(payload.get("probe"), dict):
    probes = [payload["probe"]]

compatible = 0
rows = []
for item in probes:
    if not isinstance(item, dict):
        continue
    compat = str(item.get("compatibility") or "unknown")
    if compat == "compatible":
        compatible += 1
    rows.append(
        (
            str(item.get("backend") or ""),
            str(item.get("model") or ""),
            compat,
            item.get("duration_ms"),
            str(item.get("compatibility_hint") or "")[:80],
        )
    )

print(f"Effective: {payload.get('backend')}/{payload.get('model')}")
print("")
print(f"{'Backend':<18} {'Model':<24} {'Status':<22} {'Ms':<8} Hint")
print("-" * 100)
for backend, model, status, ms, hint in rows:
    print(f"{backend:<18} {model:<24} {status:<22} {str(ms or '-'):<8} {hint or '-'}")

print("")
print(f"compatible_count={compatible} total_probed={len(rows)}")
if compatible < 1:
    level = "FAIL" if strict else "WARN"
    print(f"[{level}] no compatible backend")
    sys.exit(1 if strict else 0)
print("[OK] at least one compatible backend")
PY

if [[ "$WRITE_JSON" == "1" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT_DIR="$VAULT/output/control"
  mkdir -p "$OUT_DIR"
  OUT_FILE="$OUT_DIR/backend-probe-${STAMP}.json"
  python3 - <<'PY' "$RESULT_JSON" "$OUT_FILE" "$STAMP"
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
out = Path(sys.argv[2])
report = {
    "kind": "backend-probe-matrix",
    "version": 1,
    "generated_at": sys.argv[3],
    "configured": payload.get("configured"),
    "effective_backend": payload.get("backend"),
    "effective_model": payload.get("model"),
    "probe_timeout_seconds": payload.get("probe_timeout_seconds"),
    "probes": payload.get("probes") or ([payload["probe"]] if isinstance(payload.get("probe"), dict) else []),
}
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote: {out}")
PY
fi
