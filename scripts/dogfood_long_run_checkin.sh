#!/usr/bin/env bash
# WS6 long-run dogfood check-in helper.
# Writes one wall-clock observation into the live vault.
# Does NOT grade 14/30-day PASS/FAIL and does not recreate maturity gate.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${AIWIKI_DOGFOOD_VAULT:-}" ]]; then
  echo "error: set AIWIKI_DOGFOOD_VAULT to your live dogfood vault root" >&2
  echo "example: export AIWIKI_DOGFOOD_VAULT=\"\$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉\"" >&2
  exit 2
fi

VAULT="$(cd -- "$AIWIKI_DOGFOOD_VAULT" && pwd)"
if [[ ! -d "$VAULT/raw" || ! -d "$VAULT/.aiwiki" ]]; then
  echo "error: AIWIKI_DOGFOOD_VAULT does not look like an aiwiki vault: $VAULT" >&2
  echo "expected raw/ and .aiwiki/ under the vault root" >&2
  exit 2
fi

if command -v aiwiki >/dev/null 2>&1; then
  AIWIKI=(aiwiki --root "$VAULT")
else
  export PYTHONPATH="$RUNTIME_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
  AIWIKI=(python3 -m aiwiki.cli --root "$VAULT")
fi

UTC_DATE="$(date -u +%Y%m%d)"
UTC_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT_DIR="$VAULT/output/control/dogfood-long-run"
mkdir -p "$OUT_DIR"
CHECKIN_MD="$OUT_DIR/checkin-${UTC_DATE}.md"
CHECKIN_JSON="$OUT_DIR/checkin-${UTC_DATE}.json"
LATEST_JSON="$OUT_DIR/latest.json"

echo "== WS6 dogfood check-in $UTC_TS =="
echo "vault: $VAULT"

set +e
SHELL_STATUS="$("${AIWIKI[@]}" advanced shell-status 2>&1)"
SHELL_RC=$?
TODAY_OUT="$("${AIWIKI[@]}" today 2>&1)"
TODAY_RC=$?
METRICS_JSON="$("${AIWIKI[@]}" metrics --json 2>&1)"
METRICS_RC=$?
set -e

python3 - "$VAULT" "$UTC_DATE" "$UTC_TS" "$CHECKIN_MD" "$CHECKIN_JSON" "$LATEST_JSON" \
  "$SHELL_RC" "$TODAY_RC" "$METRICS_RC" \
  "$SHELL_STATUS" "$TODAY_OUT" "$METRICS_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

(
    vault,
    utc_date,
    utc_ts,
    checkin_md,
    checkin_json,
    latest_json,
    shell_rc,
    today_rc,
    metrics_rc,
    shell_status,
    today_out,
    metrics_raw,
) = sys.argv[1:]

shell_rc_i = int(shell_rc)
today_rc_i = int(today_rc)
metrics_rc_i = int(metrics_rc)

metrics_obj: object
try:
    metrics_obj = json.loads(metrics_raw) if metrics_rc_i == 0 else {"error": metrics_raw[:2000]}
except json.JSONDecodeError:
    metrics_obj = {"error": "metrics JSON parse failed", "raw": metrics_raw[:2000]}

payload = {
    "window_id": "ws6-2026-07",
    "kind": "dogfood-long-run-checkin",
    "utc_date": utc_date,
    "checked_at": utc_ts,
    "vault_root": vault,
    "commands": {
        "shell_status": {"exit_code": shell_rc_i},
        "today": {"exit_code": today_rc_i},
        "metrics": {"exit_code": metrics_rc_i},
    },
    "metrics": metrics_obj,
    "pass_claim": "none",
    "notes": (
        "Observation only. Does not constitute 14/30-day natural proof PASS. "
        "See docs/Furnace Dogfood Long-Run Window 2026-07.md."
    ),
}

Path(checkin_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path(latest_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

md = f"""# Dogfood long-run check-in {utc_date}

- checked_at: `{utc_ts}`
- vault: `{vault}`
- window_id: `ws6-2026-07`
- pass_claim: **none** (observation only)

## Command exit codes

| command | exit |
|---|---:|
| advanced shell-status | {shell_rc_i} |
| today | {today_rc_i} |
| metrics --json | {metrics_rc_i} |

## today (truncated)

```text
{today_out[:4000]}
```

## shell-status (truncated)

```text
{shell_status[:4000]}
```

## Reminder

Do not mark Scorecard `long-run natural proof` PASS from a single check-in.
Append a one-line summary to `PROGRESS.md` if useful.
"""
Path(checkin_md).write_text(md, encoding="utf-8")
print(f"wrote {checkin_md}")
print(f"wrote {checkin_json}")
print(f"PROGRESS hint: - {utc_ts} WS6 check-in vault=`{vault}` shell={shell_rc_i} today={today_rc_i} metrics={metrics_rc_i} (not-yet 14/30 PASS)")
PY

if [[ "$SHELL_RC" -ne 0 || "$TODAY_RC" -ne 0 || "$METRICS_RC" -ne 0 ]]; then
  echo "warning: one or more observation commands failed; check-in still written" >&2
  exit 1
fi
