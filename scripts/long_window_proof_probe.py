#!/usr/bin/env python3
"""Probe whether a dogfood vault has natural 14/30-day maturity proof.

This script never invents PASS. Missing or short windows report not-yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path


def _parse_day(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def collect_receipt_days(root: Path) -> list[date]:
    gate_dir = root / "output" / "control" / "maturity-gate"
    days: set[date] = set()
    if not gate_dir.is_dir():
        return []
    for path in gate_dir.glob("run-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("status") or "").lower() != "pass":
            continue
        for key in ("generated_at", "day", "date"):
            parsed = _parse_day(str(payload.get(key) or ""))
            if parsed is not None:
                days.add(parsed)
                break
        else:
            # Filename fallback: run-YYYYMMDDTHHMMSSZ.json
            stem = path.stem
            if stem.startswith("run-") and len(stem) >= 12:
                parsed = _parse_day(f"{stem[4:8]}-{stem[8:10]}-{stem[10:12]}")
                if parsed is not None:
                    days.add(parsed)
    return sorted(days)


def evaluate(days: list[date], *, window: int) -> dict:
    if not days:
        return {
            "status": "not-yet",
            "window_days": window,
            "pass_days": 0,
            "span_days": 0,
            "reason": "no pass maturity receipts found",
        }
    span = (days[-1] - days[0]).days + 1
    status = "pass" if span >= window and len(days) >= window else "not-yet"
    return {
        "status": status,
        "window_days": window,
        "pass_days": len(days),
        "span_days": span,
        "first_day": days[0].isoformat(),
        "last_day": days[-1].isoformat(),
        "reason": (
            "natural pass window satisfied"
            if status == "pass"
            else f"need span>={window} with enough pass days; found span={span}, pass_days={len(days)}"
        ),
        "probed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="dogfood vault root")
    parser.add_argument("--window", type=int, choices=(14, 30), default=14)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2

    report = evaluate(collect_receipt_days(root), window=args.window)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"status={report['status']} window={report['window_days']} "
            f"pass_days={report['pass_days']} span_days={report['span_days']} "
            f"reason={report['reason']}"
        )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
