#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AIWIKI_DOGFOOD_VAULT:-}" ]]; then
  echo "error: AIWIKI_DOGFOOD_VAULT is not set" >&2
  echo "  Dogfood maturity receipts require an explicit vault path." >&2
  echo "  Example: AIWIKI_DOGFOOD_VAULT=/path/to/vault $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="$AIWIKI_DOGFOOD_VAULT"

if [[ ! -d "$TARGET_ROOT" ]]; then
  echo "error: AIWIKI_DOGFOOD_VAULT does not exist: $TARGET_ROOT" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PREVIEW_LIMIT="${AIWIKI_DOGFOOD_MATURITY_PREVIEW_LIMIT:-1000}"
L3_LIMIT="${AIWIKI_DOGFOOD_MATURITY_L3_LIMIT:-1000}"
COMPILE_LIMIT="${AIWIKI_DOGFOOD_MATURITY_COMPILE_LIMIT:-0}"
NO_SEMANTIC_LINT="${AIWIKI_DOGFOOD_MATURITY_NO_SEMANTIC_LINT:-1}"
FORCE_RUN="${AIWIKI_DOGFOOD_MATURITY_FORCE:-0}"

DOGFOOD_ENVRC="${AIWIKI_DOGFOOD_MATURITY_ENVRC:-}"
if [[ -n "$DOGFOOD_ENVRC" ]]; then
  if [[ ! -f "$DOGFOOD_ENVRC" ]]; then
    echo "error: AIWIKI_DOGFOOD_MATURITY_ENVRC does not exist: $DOGFOOD_ENVRC" >&2
    exit 1
  fi
  set -a
  # shellcheck source=/dev/null
  source "$DOGFOOD_ENVRC"
  set +a
fi

if [[ "$FORCE_RUN" != "1" ]]; then
  TODAY_UTC="$(python3 - <<'PY'
from datetime import datetime, timezone

print(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
PY
)"
  if EXISTING_RECEIPT="$(python3 - "$TARGET_ROOT" "$TODAY_UTC" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
today = sys.argv[2]
run_dir = root / "output" / "control" / "maturity-gate"
for path in sorted(run_dir.glob("run-*.json"), reverse=True):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    generated_at = str(payload.get("generated_at") or "")
    filename_day = ""
    stem = path.stem
    if stem.startswith("run-") and len(stem) >= 12:
        filename_day = f"{stem[4:8]}-{stem[8:10]}-{stem[10:12]}"
    if generated_at[:10] == today or filename_day == today:
        print(path.relative_to(root))
        raise SystemExit(0)
raise SystemExit(1)
PY
)"; then
    printf '[aiwiki-dogfood-maturity] skip: receipt already exists for %s at %s\n' "$TODAY_UTC" "$EXISTING_RECEIPT"
    exit 0
  fi
fi

ARGS=(
  "$PROJECT_ROOT/scripts/dogfood_maturity_gate.py"
  --root "$TARGET_ROOT"
  run
  --preview-limit "$PREVIEW_LIMIT"
  --l3-limit "$L3_LIMIT"
  --compile-limit "$COMPILE_LIMIT"
)

if [[ "$NO_SEMANTIC_LINT" == "1" ]]; then
  ARGS+=(--no-semantic-lint)
fi

exec python3 "${ARGS[@]}"
