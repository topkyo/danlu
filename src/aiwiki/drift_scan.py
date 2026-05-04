"""炼丹炉 P3 / M8.3 — Drift / Aging nightly scanner.

Scans the curated knowledge base for three classes of self-maintenance signals
that no upstream event log will ever surface on its own:

1. **stale judgments** — `wiki/judgments/*.md` whose `last_reviewed` (fallback:
   `updated_at` / `last_compiled_at` / file mtime) is older than
   ``STALE_JUDGMENT_DAYS`` days relative to ``now``.
2. **changed evidence** — judgments / elixirs whose ``citation_snapshots``
   (path#sha256 anchors) no longer match the current ``evidence_path_digest``
   on disk, or whose anchored path has disappeared entirely.
3. **dependency breaks** — elixirs whose ``derived_from`` references a
   judgment / decision page that no longer exists on disk.

The scanner is purely **derived**: it reads frontmatter and current digests
only; it never mutates curated pages. It writes two outputs:

- appends fully-validated records to ``.aiwiki/state/signals.jsonl`` using the
  exact same schema as the replay collector (kinds: ``drift`` /
  ``elixir_dependency_break``); ``compute_dedupe_key`` makes re-runs idempotent
  on identical findings.
- overwrites ``.aiwiki/state/drift-aging.json`` with the latest scan result so
  the product shell can surface warnings without re-scanning.

To anchor signals to a real ``source_event_ref`` line (required by the schema
for ``runtime_history`` source_kind), the scanner also appends a single
``drift-scan`` event to ``runtime-history.jsonl`` per run and points all
emitted signals at that line. This keeps drift findings auditable from the
existing runtime-history surface without inventing a new source_kind.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import clock
from .app_state import runtime_history_path
from .app_utils import (
    analyze_citation_snapshots,
    atomic_append_jsonl,
    atomic_append_line,
    parse_frontmatter,
    parse_iso_datetime,
    relative_path,
    runtime_write_lock,
    utc_now,
)
from .signals.collector import SIGNALS_REL_PATH
from .signals.schema import (
    PROTOCOLS,
    SCHEMA_VERSION,
    canonical_dumps,
    compute_dedupe_key,
    validate,
)

DEFAULT_PROTOCOL = "general"
STALE_JUDGMENT_DAYS_DEFAULT = 180
DRIFT_AGING_REL_PATH = ".aiwiki/state/drift-aging.json"


def _stale_threshold_days() -> int:
    raw = os.environ.get("AIWIKI_STALE_JUDGMENT_DAYS", "").strip()
    if not raw:
        return STALE_JUDGMENT_DAYS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return STALE_JUDGMENT_DAYS_DEFAULT
    return value if value > 0 else STALE_JUDGMENT_DAYS_DEFAULT


def drift_scan(root: Path, *, now: str | None = None) -> dict[str, Any]:
    """Run the three drift scanners, emit signals, and persist aging state.

    Returns a structured summary; never raises on individual page parse
    failures (collected into ``errors``).
    """

    resolved_now = now or utc_now()
    now_dt = parse_iso_datetime(resolved_now)
    if now_dt is None:
        raise ValueError(f"drift_scan: invalid now={resolved_now!r}")
    emitted_at = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    stale_threshold_days = _stale_threshold_days()
    errors: list[dict[str, Any]] = []

    with runtime_write_lock(root):
        stale = _scan_stale_judgments(
            root, now_dt=now_dt, threshold_days=stale_threshold_days, errors=errors
        )
        changed = _scan_changed_evidence(root, errors=errors)
        breaks = _scan_dependency_breaks(root, errors=errors)

        findings_count = len(stale) + len(changed) + len(breaks)
        signals_appended = 0
        history_ref: str | None = None
        if findings_count > 0:
            history_ref = _append_drift_scan_event(
                root,
                emitted_at=emitted_at,
                stale_count=len(stale),
                changed_count=len(changed),
                breaks_count=len(breaks),
            )
            signals_appended = _emit_signals(
                root,
                emitted_at=emitted_at,
                history_ref=history_ref,
                stale=stale,
                changed=changed,
                breaks=breaks,
                errors=errors,
            )

        warnings = _build_warnings(stale, changed, breaks)
        state = {
            "version": 1,
            "scanned_at": resolved_now,
            "stale_threshold_days": stale_threshold_days,
            "stale_judgments": stale,
            "changed_evidence": changed,
            "dependency_breaks": breaks,
            "warnings": warnings,
            "signals_appended": signals_appended,
            "history_ref": history_ref or "",
            "errors": errors,
        }
        _write_aging_state(root, state)

    return {
        "stale_judgments": stale,
        "changed_evidence": changed,
        "dependency_breaks": breaks,
        "warnings": warnings,
        "signals_appended": signals_appended,
        "errors": errors,
        "scanned_at": resolved_now,
    }


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------


def _scan_stale_judgments(
    root: Path,
    *,
    now_dt,
    threshold_days: int,
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    judgments_dir = root / "wiki" / "judgments"
    if not judgments_dir.is_dir():
        return []

    cutoff = now_dt - timedelta(days=threshold_days)
    findings: list[dict[str, Any]] = []
    for path in sorted(judgments_dir.glob("*.md")):
        frontmatter = _safe_frontmatter(path, errors)
        if frontmatter is None:
            continue
        last_reviewed_raw = (
            frontmatter.get("last_reviewed")
            or frontmatter.get("updated_at")
            or frontmatter.get("last_compiled_at")
            or ""
        )
        last_dt = parse_iso_datetime(str(last_reviewed_raw)) if last_reviewed_raw else None
        if last_dt is None:
            try:
                from datetime import datetime as _dt
                last_dt = _dt.fromtimestamp(path.stat().st_mtime, tz=now_dt.tzinfo)
            except OSError:
                last_dt = None
        if last_dt is None or last_dt > cutoff:
            continue

        days_since = max(0, int((now_dt - last_dt).total_seconds() // 86400))
        rel = relative_path(root, path)
        judgment_id = str(frontmatter.get("id") or path.stem)
        protocol = _protocol_or_default(frontmatter.get("protocol"))
        findings.append(
            {
                "judgment_id": judgment_id,
                "path": rel,
                "protocol": protocol,
                "last_reviewed": str(last_reviewed_raw or ""),
                "days_since_review": days_since,
                "threshold_days": threshold_days,
            }
        )
    return findings


def _scan_changed_evidence(
    root: Path,
    *,
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for subdir in ("wiki/judgments", "wiki/elixirs"):
        target = root / subdir
        if not target.is_dir():
            continue
        for path in sorted(target.glob("*.md")):
            frontmatter = _safe_frontmatter(path, errors)
            if frontmatter is None:
                continue
            citations_raw = frontmatter.get("citations") or []
            if not isinstance(citations_raw, list):
                continue
            citations = [str(item) for item in citations_raw if isinstance(item, str)]
            if not citations:
                continue
            snapshots_raw = frontmatter.get("citation_snapshots")
            if not isinstance(snapshots_raw, list) or not snapshots_raw:
                continue
            try:
                analysis = analyze_citation_snapshots(root, citations, frontmatter)
            except Exception as exc:  # defensive — never abort scan
                errors.append(
                    {
                        "phase": "changed_evidence",
                        "path": relative_path(root, path),
                        "reason": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            drifted = list(analysis.get("drifted", []))
            stale = list(analysis.get("stale", []))
            if not drifted and not stale:
                continue
            asset_id = str(frontmatter.get("id") or path.stem)
            kind = "judgment" if subdir == "wiki/judgments" else "elixir"
            findings.append(
                {
                    "asset_kind": kind,
                    "asset_id": asset_id,
                    "path": relative_path(root, path),
                    "protocol": _protocol_or_default(frontmatter.get("protocol")),
                    "drifted_paths": sorted(drifted),
                    "stale_paths": sorted(stale),
                }
            )
    return findings


def _scan_dependency_breaks(
    root: Path,
    *,
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    elixirs_dir = root / "wiki" / "elixirs"
    if not elixirs_dir.is_dir():
        return []

    findings: list[dict[str, Any]] = []
    for path in sorted(elixirs_dir.glob("*.md")):
        frontmatter = _safe_frontmatter(path, errors)
        if frontmatter is None:
            continue
        derived_from_raw = frontmatter.get("derived_from") or []
        if not isinstance(derived_from_raw, list):
            continue
        missing: list[str] = []
        for item in derived_from_raw:
            if not isinstance(item, str) or not item.strip():
                continue
            normalized = item.strip()
            if not normalized.endswith(".md"):
                continue
            if normalized.startswith("/"):
                continue
            if not (root / normalized).exists():
                missing.append(normalized)
        if not missing:
            continue
        elixir_id = str(frontmatter.get("id") or path.stem)
        findings.append(
            {
                "elixir_id": elixir_id,
                "path": relative_path(root, path),
                "protocol": _protocol_or_default(frontmatter.get("protocol")),
                "missing_dependencies": sorted(set(missing)),
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Signal emission
# ---------------------------------------------------------------------------


def _emit_signals(
    root: Path,
    *,
    emitted_at: str,
    history_ref: str,
    stale: list[dict[str, Any]],
    changed: list[dict[str, Any]],
    breaks: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> int:
    signals_path = root / SIGNALS_REL_PATH
    existing_keys = _load_existing_dedupe_keys(signals_path)
    new_records: list[dict[str, Any]] = []

    def _try_emit(seed: dict[str, Any], source_identity: str, label: str) -> None:
        try:
            dedupe_key = compute_dedupe_key(seed, source_identity)
        except Exception as exc:
            errors.append(
                {"phase": label, "reason": f"dedupe_key_failed: {exc}", "source_identity": source_identity}
            )
            return
        if dedupe_key in existing_keys:
            return
        record = {
            **seed,
            "schema_version": SCHEMA_VERSION,
            "signal_id": _new_signal_id(),
            "dedupe_key": dedupe_key,
            "trace_id": str(uuid.uuid4()),
        }
        validation = validate(record)
        if not validation.ok:
            errors.append(
                {
                    "phase": label,
                    "reason": "; ".join(validation.errors),
                    "source_identity": source_identity,
                }
            )
            return
        new_records.append(record)
        existing_keys.add(dedupe_key)

    for finding in stale:
        protocol = finding["protocol"]
        seed = {
            "kind": "drift",
            "scope": {
                "protocol": protocol,
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": [],
                "judgment_refs": [finding["judgment_id"]],
            },
            "severity": "medium",
            "evidence_refs": [finding["path"]],
            "emitted_at": emitted_at,
            "emitted_by": "nightly",
            "source_kind": "runtime_history",
            "source_event_ref": history_ref,
        }
        _try_emit(seed, f"drift::stale_judgment::{finding['judgment_id']}", "stale_judgment")

    for finding in changed:
        protocol = finding["protocol"]
        evidence = sorted(set([finding["path"], *finding["drifted_paths"], *finding["stale_paths"]]))
        if finding["asset_kind"] == "judgment":
            judgment_refs = [finding["asset_id"]]
            elixir_refs: list[str] = []
        else:
            judgment_refs = []
            elixir_refs = [finding["asset_id"]]
        seed = {
            "kind": "drift",
            "scope": {
                "protocol": protocol,
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": elixir_refs,
                "judgment_refs": judgment_refs,
            },
            "severity": "high",
            "evidence_refs": evidence,
            "emitted_at": emitted_at,
            "emitted_by": "nightly",
            "source_kind": "runtime_history",
            "source_event_ref": history_ref,
        }
        identity = (
            f"drift::changed_evidence::{finding['asset_kind']}::{finding['asset_id']}"
            f"::{','.join(finding['drifted_paths'])}::{','.join(finding['stale_paths'])}"
        )
        _try_emit(seed, identity, "changed_evidence")

    for finding in breaks:
        protocol = finding["protocol"]
        seed = {
            "kind": "elixir_dependency_break",
            "scope": {
                "protocol": protocol,
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": [finding["elixir_id"]],
                "judgment_refs": [],
            },
            "severity": "high",
            "evidence_refs": sorted(set([finding["path"], *finding["missing_dependencies"]])),
            "emitted_at": emitted_at,
            "emitted_by": "nightly",
            "source_kind": "runtime_history",
            "source_event_ref": history_ref,
        }
        identity = (
            f"drift::dependency_break::{finding['elixir_id']}"
            f"::{','.join(finding['missing_dependencies'])}"
        )
        _try_emit(seed, identity, "dependency_break")

    if not new_records:
        return 0
    _append_signal_records(signals_path, new_records)
    return len(new_records)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_frontmatter(path: Path, errors: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(
            {"phase": "read", "path": str(path), "reason": str(exc), "error_type": type(exc).__name__}
        )
        return None
    try:
        return parse_frontmatter(text)
    except Exception as exc:
        errors.append(
            {
                "phase": "parse_frontmatter",
                "path": str(path),
                "reason": str(exc),
                "error_type": type(exc).__name__,
            }
        )
        return None


def _protocol_or_default(value: Any) -> str:
    if isinstance(value, str) and value in PROTOCOLS:
        return value
    return DEFAULT_PROTOCOL


def _build_warnings(
    stale: list[dict[str, Any]],
    changed: list[dict[str, Any]],
    breaks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for f in stale:
        warnings.append(
            {
                "kind": "judgment-stale",
                "path": f["path"],
                "message": (
                    f"Judgment `{f['judgment_id']}` not reviewed in "
                    f"{f['days_since_review']}d (>{f['threshold_days']}d)."
                ),
            }
        )
    for f in changed:
        drifted = f["drifted_paths"]
        stale_paths = f["stale_paths"]
        detail_parts: list[str] = []
        if drifted:
            detail_parts.append(f"changed: {', '.join(drifted[:2])}")
        if stale_paths:
            detail_parts.append(f"missing: {', '.join(stale_paths[:2])}")
        warnings.append(
            {
                "kind": "evidence-changed",
                "path": f["path"],
                "message": (
                    f"{f['asset_kind'].capitalize()} `{f['asset_id']}` evidence drift "
                    f"({'; '.join(detail_parts)})."
                ),
            }
        )
    for f in breaks:
        warnings.append(
            {
                "kind": "elixir-dependency-break",
                "path": f["path"],
                "message": (
                    f"Elixir `{f['elixir_id']}` references missing dependency: "
                    f"{', '.join(f['missing_dependencies'][:2])}."
                ),
            }
        )
    return warnings


def _append_drift_scan_event(
    root: Path,
    *,
    emitted_at: str,
    stale_count: int,
    changed_count: int,
    breaks_count: int,
) -> str:
    """Append a single ``drift-scan`` row to runtime-history.jsonl and return
    the ``<rel>#L<n>`` reference for downstream signals."""

    path = runtime_history_path(root)
    event = {
        "event_type": "drift-scan",
        "occurred_at": emitted_at,
        "protocol": DEFAULT_PROTOCOL,
        "stale_count": stale_count,
        "changed_count": changed_count,
        "breaks_count": breaks_count,
    }
    # Compute the line number that the new row will occupy.
    line_number = 1
    if path.exists():
        with path.open("rb") as handle:
            line_number += sum(1 for _ in handle)
    atomic_append_jsonl(path, event)
    return f"{relative_path(root, path)}#L{line_number}"


def _load_existing_dedupe_keys(signals_path: Path) -> set[str]:
    keys: set[str] = set()
    if not signals_path.exists():
        return keys
    with signals_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            dedupe_key = record.get("dedupe_key")
            if isinstance(dedupe_key, str) and dedupe_key:
                keys.add(dedupe_key)
    return keys


def _append_signal_records(signals_path: Path, records: list[dict[str, Any]]) -> None:
    for record in records:
        atomic_append_line(signals_path, canonical_dumps(record))


def _new_signal_id() -> str:
    day = clock.utc_now().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:12]
    return f"sig-{day}-{suffix}"


def _write_aging_state(root: Path, state: dict[str, Any]) -> None:
    path = root / DRIFT_AGING_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


__all__ = [
    "drift_scan",
    "DRIFT_AGING_REL_PATH",
    "STALE_JUDGMENT_DAYS_DEFAULT",
]
