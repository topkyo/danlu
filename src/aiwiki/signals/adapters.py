from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SUPPORTED_SOURCES: tuple[str, str, str] = ("runtime_history", "llm_receipt", "archive")

RUNTIME_HISTORY_REL_PATH = ".aiwiki/state/runtime-history.jsonl"
LLM_RECEIPTS_REL_PATH = ".aiwiki/logs/llm-receipts.jsonl"
ARCHIVE_RECEIPTS_REL_PATH = ".aiwiki/state/execution-receipts.jsonl"


@dataclass(frozen=True)
class SignalSeed:
    record_base: dict[str, Any]
    source_identity: str


def source_rel_path(source: str) -> str:
    if source == "runtime_history":
        return RUNTIME_HISTORY_REL_PATH
    if source == "llm_receipt":
        return LLM_RECEIPTS_REL_PATH
    if source == "archive":
        return ARCHIVE_RECEIPTS_REL_PATH
    raise ValueError(f"unsupported source: {source}")


def source_path(root: Path, source: str) -> Path:
    return root / source_rel_path(source)


def iter_source_lines(root: Path, source: str) -> Iterator[tuple[int, str, str]]:
    rel_path = source_rel_path(source)
    path = root / rel_path
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            yield line_no, payload, rel_path


def _runtime_history_to_signals(event: dict[str, Any], *, line_no: int, rel_path: str) -> list[SignalSeed]:
    event_type = str(event.get("event_type") or "")
    if event_type not in {"review", "nightly"}:
        return []

    protocol = event.get("protocol")
    emitted_at = _normalize_emitted_at(event.get("occurred_at"))
    if not isinstance(protocol, str) or not protocol or emitted_at is None:
        return []

    if event_type == "review":
        kind = "review_feedback"
        severity = "medium"
        emitted_by = "user"
        evidence = _unique_sorted_strings([event.get("page_path"), event.get("subject")])
    else:
        kind = "schedule_tick"
        severity = "low"
        emitted_by = "nightly"
        evidence = _unique_sorted_strings(
            _string_list(event.get("overdue_pages")) + _string_list(event.get("escalated_pages"))
        )

    scope: dict[str, Any] = {
        "protocol": protocol,
        "source_ids": _unique_sorted_strings(_string_list(event.get("source_ids"))),
        "concept_slugs": _unique_sorted_strings(_string_list(event.get("concept_slugs"))),
        "elixir_refs": _unique_sorted_strings(_string_list(event.get("elixir_refs"))),
        "judgment_refs": _unique_sorted_strings(_string_list(event.get("judgment_refs"))),
    }
    corpus_id = event.get("corpus_id")
    if isinstance(corpus_id, str) and corpus_id:
        scope["corpus_id"] = corpus_id

    return [
        SignalSeed(
            record_base={
                "kind": kind,
                "scope": scope,
                "severity": severity,
                "evidence_refs": evidence,
                "emitted_at": emitted_at,
                "emitted_by": emitted_by,
                "source_kind": "runtime_history",
                "source_event_ref": f"{rel_path}#L{line_no}",
            },
            source_identity=_source_identity(event),
        )
    ]


def _llm_receipt_to_signals(
    event: dict[str, Any],
    *,
    line_no: int,
    rel_path: str,
    allowed_protocols: set[str],
) -> list[SignalSeed]:
    if str(event.get("status") or "") != "failed":
        return []

    protocol = event.get("protocol")
    emitted_at = _normalize_emitted_at(event.get("created_at"))
    if not isinstance(protocol, str) or protocol not in allowed_protocols or emitted_at is None:
        return []

    evidence = _unique_sorted_strings([event.get("target")])
    scope: dict[str, Any] = {
        "protocol": protocol,
        "source_ids": [],
        "concept_slugs": [],
        "elixir_refs": [],
        "judgment_refs": [],
    }

    return [
        SignalSeed(
            record_base={
                "kind": "runtime_failure",
                "scope": scope,
                "severity": "high",
                "evidence_refs": evidence,
                "emitted_at": emitted_at,
                "emitted_by": "external",
                "source_kind": "llm_receipt",
                "source_event_ref": f"{rel_path}#L{line_no}",
            },
            source_identity=_source_identity(event),
        )
    ]


def _archive_receipt_to_signals(
    receipt: dict[str, Any],
    *,
    receipt_rel_path: str,
    history_line_no: int | None,
) -> list[SignalSeed]:
    del receipt
    del receipt_rel_path
    del history_line_no
    return []


def _source_identity(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"sha256-{digest}"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _unique_sorted_strings(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if isinstance(value, str) and value:
            normalized.append(value)
    return sorted(set(normalized))


def _normalize_emitted_at(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    if raw.endswith("Z"):
        candidate = raw[:-1] + "+00:00"
    else:
        candidate = raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
