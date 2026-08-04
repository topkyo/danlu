"""Shared helpers for alchemy execution."""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from ..content.material import load_active_corpora_state
from ..protocol.runtime_config import PROTOCOL_ELIXIR_REVIEW_DAYS
from ..utils.io import atomic_write_text
from ..utils.markdown import parse_frontmatter, strip_frontmatter
from .candidates import load_output_candidates_state

ELIXIR_DIR = "wiki/elixirs"


CANDIDATE_ELIXIR_DIR = ".aiwiki/staging/elixirs"


ELIXIR_STATE_VALUES = {"draft", "distilling", "candidate", "settled", "superseded"}


_ACTIVE_ELIXIR_STATES = {"draft", "distilling", "candidate"}


_PROMOTION_TS_FIELD = "promoted_at"


_PENDING_REFINEMENT_RE = re.compile(r"(?im)^\s*-\s*pending\s+refinement\.?\s*$")


logger = logging.getLogger("aiwiki")


class PromoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"promote_half_write_error[{phase}]: failed to rollback after promote failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class RevertHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"revert_half_write_error[{phase}]: failed to rollback after revert failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class DemoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"demote_half_write_error[{phase}]: failed to rollback after demote failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class ElixirMutationBoundaryError(RuntimeError):
    """Base for receipt-boundary failures where mutation has been rolled back successfully."""


class PromoteReceiptError(ElixirMutationBoundaryError):
    pass


class RevertReceiptError(ElixirMutationBoundaryError):
    pass


class DemoteReceiptError(ElixirMutationBoundaryError):
    pass


class LegacyMigrationPlanError(ElixirMutationBoundaryError):
    """Raised when legacy migration planning fails before any mutation occurs.

    No rollback is needed — planning is read-only.
    """

    pass


class LegacyMigrationApplyError(ElixirMutationBoundaryError):
    """Raised when legacy migration mutation or receipt persistence fails.

    Implies rollback has been attempted (and succeeded); callers must NOT retry
    without re-running preview because the in-memory plan is stale.
    """

    pass


LegacyMigrationReceiptError = LegacyMigrationApplyError


class LegacyMigrationHalfWriteError(RuntimeError):
    def __init__(self, *, phase: str = "rollback") -> None:
        self.phase = phase
        super().__init__(
            f"legacy_migration_half_write_error[{phase}]: failed to rollback after legacy migration failure; "
            "manual repair required"
        )


class SupersededCleanupPlanError(ElixirMutationBoundaryError):
    """Raised when superseded-cleanup planning fails before any mutation occurs."""

    pass


class SupersededCleanupApplyError(ElixirMutationBoundaryError):
    """Raised when superseded-cleanup mutation or receipt persistence fails.

    Implies rollback has been attempted.
    """

    pass


SupersededCleanupReceiptError = SupersededCleanupApplyError


class SupersededCleanupHalfWriteError(RuntimeError):
    def __init__(self, *, phase: str = "rollback") -> None:
        self.phase = phase
        super().__init__(
            f"superseded_cleanup_half_write_error[{phase}]: failed to rollback after superseded cleanup failure; "
            "manual repair required"
        )


def list_promoted_outputs_for_corpus(root: Path, corpus_id: str) -> list[dict[str, Any]]:
    """List every currently-promoted candidate belonging to ``corpus_id``.

    Authoritative provenance allowlist for elixir distill/seal: walks the full
    ``output_candidates`` state and returns every row whose ``corpus_id`` matches and
    whose ``candidate_state == "promoted"``.

    Deliberately does NOT use ``active_corpora.output_refs`` as an allowlist:
    ``output_refs`` is a recent-context ring buffer (last 8) maintained by
    ``upsert_active_corpus``; using it as a provenance allowlist would silently
    invalidate legitimate older promoted provenance once the corpus ran more than
    8 rounds. See oracle maintainability review EP-029 MUST-FIX #3.
    """
    state = load_output_candidates_state(root)
    results: list[dict[str, Any]] = []
    for candidate in state.get("candidates", []):
        if str(candidate.get("corpus_id") or "") != corpus_id:
            continue
        if str(candidate.get("candidate_state") or "") != "promoted":
            continue
        artifact_ref = str(candidate.get("artifact_ref") or "")
        promoted_to = str(candidate.get("promoted_to") or "")
        if promoted_to:
            results.append(
                {
                    "artifact_ref": artifact_ref,
                    "promoted_to": promoted_to,
                    "question": str(candidate.get("question") or ""),
                }
            )
    return results


_ELIXIR_SOURCE_PREFIXES: tuple[str, ...] = ("wiki/derived/", "wiki/judgments/")


def _validate_source_outputs(root: Path, refs: list[str], *, allowed: set[str]) -> None:
    if not refs:
        raise ValueError("source outputs cannot be empty")
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("source output must be a non-empty wiki/derived or wiki/judgments ref")
        if ref.startswith("wiki/derived/") or ref.startswith("wiki/judgments/"):
            if not (root / ref).is_file():
                raise ValueError(f"source output missing: {ref}")
            if ref not in allowed:
                raise ValueError(f"source output is not a promoted candidate for this corpus: {ref}")
            continue
        if ref.startswith("wiki/elixirs/"):
            path = root / ref
            if not path.is_file():
                raise ValueError(f"source output missing: {ref}")
            frontmatter = _parse_elixir_frontmatter(path)
            if str(frontmatter.get("elixir_state") or "") != "settled":
                raise ValueError(
                    f"引用金丹 {ref} 当前状态为 {frontmatter.get('elixir_state') or 'unknown'}，只能引用 settled 金丹"
                )
            continue
        raise ValueError(
            f"source output must be under wiki/derived/, wiki/judgments/, or wiki/elixirs/: {ref}"
        )


def _settled_path(root: Path, elixir_id: str) -> Path:
    return root / ELIXIR_DIR / f"{elixir_id}.md"


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"


def _resolve_elixir_id(root: Path, elixir_id: str) -> str:
    elixir_id = elixir_id.strip()
    if not elixir_id:
        raise ValueError("金丹 id 不能为空")
    if "/" in elixir_id or "\\" in elixir_id:
        raise ValueError(f"金丹 id 不允许包含路径分隔符: {elixir_id!r}")
    if elixir_id in {".", ".."}:
        raise ValueError(f"金丹 id 非法: {elixir_id!r}")
    elixir_root = root / ELIXIR_DIR
    candidate = elixir_root / f"{elixir_id}.md"
    if candidate.resolve().parent != elixir_root.resolve():
        raise ValueError(f"金丹 id 非法: {elixir_id!r}")
    return elixir_id


def _validate_state_for_path(root: Path, state: str, abs_path: Path) -> None:
    if state not in ELIXIR_STATE_VALUES:
        raise ValueError(f"invalid elixir_state: {state}")
    resolved = abs_path.resolve()
    settled_root = (root / ELIXIR_DIR).resolve()
    candidate_root = (root / CANDIDATE_ELIXIR_DIR).resolve()
    in_settled = resolved.parent == settled_root
    in_candidate = resolved.parent == candidate_root
    if not (in_settled or in_candidate):
        raise ValueError(f"elixir path must be under {ELIXIR_DIR} or {CANDIDATE_ELIXIR_DIR}: {abs_path}")
    if state == "settled" and not in_settled:
        raise ValueError(f"elixir_state settled must live under {ELIXIR_DIR}: {abs_path}")
    if state in {"draft", "distilling", "candidate", "superseded"} and not in_candidate:
        raise ValueError(f"elixir_state {state} must live under {CANDIDATE_ELIXIR_DIR}: {abs_path}")


def _read_elixir_anywhere(root: Path, elixir_id: str) -> tuple[Path, dict[str, Any]]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled = _settled_path(root, normalized_id)
    candidate = _candidate_path(root, normalized_id)
    # settled is source-of-truth; prefer it over stale candidate drafts.
    if settled.is_file():
        frontmatter = _parse_elixir_frontmatter(settled)
        _validate_state_for_path(root, str(frontmatter.get("elixir_state") or ""), settled)
        return settled, frontmatter
    if candidate.is_file():
        frontmatter = _parse_elixir_frontmatter(candidate)
        _validate_state_for_path(root, str(frontmatter.get("elixir_state") or ""), candidate)
        return candidate, frontmatter
    raise FileNotFoundError(f"elixir not found: {normalized_id}")


def _read_elixir_both_planes(
    root: Path, elixir_id: str
) -> tuple[tuple[dict[str, Any], str] | None, tuple[dict[str, Any], str] | None]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled = _settled_path(root, normalized_id)
    candidate = _candidate_path(root, normalized_id)

    def _read(path: Path) -> tuple[dict[str, Any], str] | None:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = _parse_elixir_frontmatter(path)
        body = text.split("---", 2)[-1].lstrip("\n")
        return frontmatter, body

    return _read(settled), _read(candidate)


def _collect_dependent_elixir_ids(root: Path, *, source_elixir_id: str) -> list[str]:
    """Return settled elixir ids whose derived_from references source elixir."""
    source_ref = f"wiki/elixirs/{source_elixir_id}.md"
    elixir_root = root / ELIXIR_DIR
    if not elixir_root.exists():
        return []

    dependent_ids: set[str] = set()
    for path in elixir_root.glob("*.md"):
        try:
            frontmatter = _parse_elixir_frontmatter(path)
        except (OSError, ValueError) as exc:
            logger.warning(
                "skip elixir during dependency scan: path=%s source_elixir_id=%s error=%s",
                path,
                source_elixir_id,
                exc,
            )
            continue

        if str(frontmatter.get("elixir_state") or "") != "settled":
            continue

        elixir_id = str(frontmatter.get("elixir_id") or "").strip()
        if not elixir_id or elixir_id == source_elixir_id:
            continue

        derived_from = frontmatter.get("derived_from")
        if not isinstance(derived_from, list):
            continue

        if any(isinstance(item, str) and item == source_ref for item in derived_from):
            dependent_ids.add(elixir_id)

    return sorted(dependent_ids)


def _detect_elixir_cycle(root: Path, new_elixir_path: str | Path, derived_from: list[str]) -> list[str] | None:
    def _norm(p: str | Path, root: Path = root) -> str:
        s = str(p).replace("\\", "/")
        if s.startswith("./"):
            s = s[2:]
        path = Path(s)
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                return str(path).replace("\\", "/")
        return path.as_posix()

    def _elixir_deps(abs_path: Path) -> list[str]:
        try:
            frontmatter = _parse_elixir_frontmatter(abs_path)
        except (OSError, ValueError) as e:
            raise ValueError(f"金丹文件无法解析: {abs_path} ({e})") from e
        deps = frontmatter.get("derived_from", [])
        if not isinstance(deps, list):
            return []
        return [_norm(item) for item in deps if isinstance(item, str) and _norm(item).startswith("wiki/elixirs/")]

    graph: dict[str, list[str]] = {}
    elixir_root = root / "wiki" / "elixirs"
    if elixir_root.exists():
        for f in elixir_root.rglob("*.md"):
            rel = _norm(f.relative_to(root))
            try:
                frontmatter = _parse_elixir_frontmatter(f)
            except (OSError, ValueError) as e:
                raise ValueError(f"金丹文件无法解析: {f} ({e})") from e
            if str(frontmatter.get("elixir_state") or "") != "settled":
                continue
            graph[rel] = _elixir_deps(f)

    start = _norm(new_elixir_path)
    graph[start] = [_norm(d) for d in derived_from if isinstance(d, str) and _norm(d).startswith("wiki/elixirs/")]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                i = stack.index(nxt)
                return stack[i:] + [nxt]
            if c == WHITE:
                cyc = dfs(nxt)
                if cyc:
                    return cyc
        stack.pop()
        color[node] = BLACK
        return None

    return dfs(start)


def _scaffold_elixir_markdown(
    *,
    elixir_id: str,
    protocol: str,
    topic: str,
    corpus_id: str,
    source_outputs: list[str],
    iteration: int,
    elixir_state: str,
    created_at: str,
    updated_at: str,
    distill_history: list[dict[str, Any]] | None = None,
    body: str | None = None,
) -> str:
    frontmatter = {
        "kind": "elixir",
        "elixir_id": elixir_id,
        "elixir_state": elixir_state,
        "protocol": protocol,
        "iteration": iteration,
        "provenance_corpus": corpus_id,
        "derived_from": source_outputs,
        "topic": topic,
        "confidence_level": "low",
        "created_at": created_at,
        "updated_at": updated_at,
        "distill_history_json": json.dumps(distill_history or [], ensure_ascii=False),
        "cssclasses": ["aiwiki-output"],
    }
    body = body or "\n".join(
        [
            "# Elixir",
            "",
            "## Thesis",
            "- Pending refinement.",
            "",
            "## Evidence",
            "- Pending refinement.",
            "",
            "## Open Questions",
            "- Pending refinement.",
            "",
        ]
    )
    return _render_inserted_frontmatter(frontmatter) + body.rstrip() + "\n"


def _elixir_body_has_pending_refinement(body: str) -> bool:
    return bool(_PENDING_REFINEMENT_RE.search(body))


def _first_section_lines(
    markdown: str, headings: tuple[str, ...], *, fallback: list[str], max_lines: int = 6
) -> list[str]:
    for heading in headings:
        match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown)
        if not match:
            continue
        lines: list[str] = []
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("```") or line.startswith("#"):
                continue
            if "_LLM:" in line or "机器记忆提示" in line or "查询入口：" in line:
                continue
            if not line.startswith(("-", "1.", "2.", "3.", "4.", "5.")):
                line = f"- {line}"
            lines.append(line)
            if len(lines) >= max_lines:
                break
        if lines:
            return lines
    return list(fallback)


def _seed_elixir_body_from_sources(root: Path, *, topic: str, source_outputs: list[str]) -> str:
    source_texts: list[str] = []
    existing_refs: list[str] = []
    for ref in source_outputs:
        path = root / ref
        if not path.is_file():
            continue
        existing_refs.append(ref)
        try:
            source_texts.append(strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    merged = "\n\n".join(source_texts)
    refs = existing_refs or source_outputs
    thesis = _first_section_lines(
        merged,
        ("结论", "Conclusion", "Investment Judgment", "Judgment", "Filed Content"),
        fallback=[f"- {topic} is seeded from {', '.join(refs[:3])}."],
        max_lines=3,
    )
    evidence = _first_section_lines(
        merged,
        ("关键证据", "Evidence", "Drivers And Catalysts", "Supporting Evidence"),
        fallback=[f"- Provenance source: `{ref}`." for ref in refs[:6]],
        max_lines=6,
    )
    questions = _meaningful_counter_evidence_items(
        _first_section_lines(
            merged,
            ("反证与不确定性", "Open Questions", "Next Signals", "下次观察信号", "Risks And Invalidation"),
            fallback=[],
            max_lines=5,
        )
    )
    if not questions:
        questions = [
            "Review counter evidence and refresh this elixir before relying on it for a stronger claim."
        ]
    return "\n".join(
        [
            "# Elixir",
            "",
            "## Thesis",
            *thesis,
            "",
            "## Evidence",
            *evidence,
            "",
            "## Open Questions",
            *[f"- {item}" if not item.startswith("-") else item for item in questions],
            "",
        ]
    )


def _render_inserted_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=True)}")
        else:
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=True)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _parse_elixir_frontmatter(path: Path) -> dict[str, Any]:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    raw_history = frontmatter.get("distill_history_json")
    if isinstance(raw_history, str):
        try:
            frontmatter["distill_history"] = json.loads(raw_history)
        except json.JSONDecodeError as e:
            raise ValueError(f"elixir {path} has corrupt distill_history_json") from e
    elif "distill_history_json" in frontmatter:
        frontmatter["distill_history"] = []
    return frontmatter


def _write_elixir_markdown(path: Path, *, frontmatter: dict[str, Any], body: str) -> None:
    # Preserve distill_history as JSON string so the lightweight YAML parser remains usable.
    serializable = dict(frontmatter)
    serializable["distill_history_json"] = json.dumps(serializable.pop("distill_history", []), ensure_ascii=False)
    content = _render_inserted_frontmatter(serializable) + body
    atomic_write_text(path, content)


def _render_elixir_document(frontmatter: dict[str, Any], body: str) -> str:
    serializable = dict(frontmatter)
    serializable["distill_history_json"] = json.dumps(serializable.pop("distill_history", []), ensure_ascii=False)
    return _render_inserted_frontmatter(serializable) + body


def _find_corpus(root: Path, corpus_id: str) -> dict[str, Any]:
    state = load_active_corpora_state(root)
    for corpus in state.get("corpora", []):
        if str(corpus.get("corpus_id") or "") == corpus_id:
            return corpus
    raise FileNotFoundError(f"corpus not found: {corpus_id}")


def _default_elixir_review_after(*, protocol: str) -> str:
    """Compute a default ISO date for a freshly finalized elixir's review_after.

    Returns YYYY-MM-DD (UTC). Falls back to the general window when the
    protocol is unknown.
    """
    days = PROTOCOL_ELIXIR_REVIEW_DAYS.get(protocol.strip(), PROTOCOL_ELIXIR_REVIEW_DAYS["general"])
    # Local import preserves the tests/acceptance/case_runner.py monkeypatch of
    # ``aiwiki.execution.alchemy.datetime``.
    from aiwiki.execution.alchemy import datetime
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


_CONFIDENCE_LEVELS = {"low", "medium", "high"}

_ELIXIR_COUNTER_EVIDENCE_HEADINGS = (
    "Counter Evidence",
    "Risks",
    "Risks And Invalidation",
    "反证与不确定性",
    "Open Questions",
)

_COUNTER_EVIDENCE_PLACEHOLDER_ITEMS = frozenset(
    {
        "NONE_FOUND",
        "NONE",
        "None",
        "None.",
        "Pending refinement.",
        "Pending refinement",
    }
)


def _meaningful_counter_evidence_items(items: list[str]) -> list[str]:
    meaningful: list[str] = []
    for item in items:
        stripped = re.sub(r"^-+\s*", "", str(item)).strip()
        if not stripped or stripped in _COUNTER_EVIDENCE_PLACEHOLDER_ITEMS:
            continue
        if _PENDING_REFINEMENT_RE.match(f"- {stripped}"):
            continue
        meaningful.append(stripped)
    return meaningful


def _elixir_counter_evidence_from_body(body: str) -> list[str]:
    lines = _first_section_lines(
        body,
        _ELIXIR_COUNTER_EVIDENCE_HEADINGS,
        fallback=[],
        max_lines=12,
    )
    return _meaningful_counter_evidence_items(lines)


def resolve_promote_counter_evidence(frontmatter: dict[str, Any], *, body: str | None = None) -> list[str]:
    """Resolve promote counter-evidence body-first, falling back to frontmatter."""
    body_items = _elixir_counter_evidence_from_body(body or "")
    if body_items:
        return body_items
    raw = frontmatter.get("counter_evidence")
    if not isinstance(raw, list):
        return []
    return _meaningful_counter_evidence_items([str(item) for item in raw])


def validate_promote_gate(frontmatter: dict[str, Any], *, body: str | None = None) -> None:
    """Validate promotion counter-evidence (body-first) and confidence frontmatter."""
    counter_evidence = resolve_promote_counter_evidence(frontmatter, body=body)
    if not counter_evidence:
        raise ValueError("counter_evidence_required: counter_evidence is required")
    for item in counter_evidence:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("counter_evidence_invalid_format: counter_evidence items must be non-empty strings")

    confidence_level = str(frontmatter.get("confidence_level") or "").strip()
    if confidence_level not in _CONFIDENCE_LEVELS:
        raise ValueError("confidence_level_required: confidence_level must be one of low/medium/high")


