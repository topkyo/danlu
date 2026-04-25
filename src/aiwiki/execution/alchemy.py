from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_execution import (
    append_execution_receipt_history,
    build_elixir_demotion_receipt,
    build_elixir_promotion_receipt,
    build_elixir_revert_receipt,
    compute_file_sha256,
    find_latest_elixir_promotion_receipt,
)
from ..app_state import load_active_corpora_state, load_output_candidates_state
from ..app_utils import next_available_stem, parse_frontmatter, sha256_bytes, slugify, utc_now

ELIXIR_DIR = "wiki/elixirs"
CANDIDATE_ELIXIR_DIR = "output/_candidates/elixirs"
ELIXIR_STATE_VALUES = {"draft", "distilling", "candidate", "settled", "superseded"}
_ACTIVE_ELIXIR_STATES = {"draft", "distilling", "candidate"}
_CONFIDENCE_LEVELS = {"low", "medium", "high"}
_PROMOTION_TS_FIELD = "promoted_at"
logger = logging.getLogger("aiwiki")


class PromoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path) -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        super().__init__(
            "promote_half_write_error: failed to rollback settled after tombstone write failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class RevertHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path) -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        super().__init__(
            "revert_half_write_error: failed to rollback candidate after settled delete failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class DemoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path) -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        super().__init__(
            "demote_half_write_error: failed to rollback candidate after settled delete failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


# distill_history is stored as a JSON string in frontmatter because the simple YAML
# helpers in app_utils do not round-trip nested list-of-maps structures reliably.


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
            results.append({"artifact_ref": artifact_ref, "promoted_to": promoted_to, "question": str(candidate.get("question") or "")})
    return results


def _validate_source_outputs(root: Path, refs: list[str], *, allowed: set[str]) -> None:
    if not refs:
        raise ValueError("source outputs cannot be empty")
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("source output must be a non-empty wiki/derived ref")
        if ref.startswith("wiki/derived/"):
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
                raise ValueError(f"引用金丹 {ref} 当前状态为 {frontmatter.get('elixir_state') or 'unknown'}，只能引用 settled 金丹")
            continue
        raise ValueError(f"source output must be under wiki/derived/ or wiki/elixirs/: {ref}")


def _settled_path(root: Path, elixir_id: str) -> Path:
    return (root / ELIXIR_DIR / f"{elixir_id}.md")


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return (root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md")


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
        "counter_evidence": ["NONE_FOUND"],
        "confidence_level": "low",
        "created_at": created_at,
        "updated_at": updated_at,
        "distill_history_json": json.dumps(distill_history or [], ensure_ascii=False),
    }
    body = "\n".join([
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
    ])
    return _render_inserted_frontmatter(frontmatter) + body


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
    _write_atomic_text(path, content)


def _write_atomic_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _render_elixir_document(frontmatter: dict[str, Any], body: str) -> str:
    serializable = dict(frontmatter)
    serializable["distill_history_json"] = json.dumps(serializable.pop("distill_history", []), ensure_ascii=False)
    return _render_inserted_frontmatter(serializable) + body


def _validate_promote_gate(frontmatter: dict[str, Any]) -> None:
    if "counter_evidence" not in frontmatter:
        raise ValueError("counter_evidence_required: counter_evidence is required")
    counter_evidence = frontmatter.get("counter_evidence")
    if not isinstance(counter_evidence, list):
        raise ValueError("counter_evidence_invalid_format: counter_evidence must be a list")
    if not counter_evidence:
        raise ValueError("counter_evidence_required: counter_evidence cannot be empty")
    for item in counter_evidence:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("counter_evidence_invalid_format: counter_evidence items must be non-empty strings")

    confidence_level = str(frontmatter.get("confidence_level") or "").strip()
    has_none_found = any(item.strip() == "NONE_FOUND" for item in counter_evidence)
    if has_none_found:
        if len(counter_evidence) > 1:
            raise ValueError("counter_evidence_invalid_format: NONE_FOUND must be the only counter_evidence item")
        if counter_evidence[0].strip() != "NONE_FOUND":
            raise ValueError("counter_evidence_invalid_format: NONE_FOUND must be the only counter_evidence item")
        if confidence_level != "low":
            raise ValueError("none_found_requires_low_confidence: [NONE_FOUND] requires confidence_level=low")
        return
    if confidence_level not in _CONFIDENCE_LEVELS:
        raise ValueError("confidence_level_required: confidence_level must be one of low/medium/high")


def _find_corpus(root: Path, corpus_id: str) -> dict[str, Any]:
    state = load_active_corpora_state(root)
    for corpus in state.get("corpora", []):
        if str(corpus.get("corpus_id") or "") == corpus_id:
            return corpus
    raise FileNotFoundError(f"corpus not found: {corpus_id}")


def start_elixir(
    root: Path,
    corpus_id: str,
    *,
    topic: str,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    corpus = _find_corpus(root, corpus_id)  # validate corpus exists
    protocol_name = str(protocol or corpus.get("protocol") or "").strip()
    if not protocol_name:
        raise ValueError("protocol 不能为空")
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    if not promoted:
        raise ValueError(f"no promoted outputs for corpus {corpus_id}")
    source_outputs = [item["promoted_to"] for item in promoted if item.get("promoted_to")]
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for elixir_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, elixir_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{elixir_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {elixir_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    source_outputs = list(dict.fromkeys([*source_outputs, *include_paths]))
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    candidate_dir = root / CANDIDATE_ELIXIR_DIR
    candidate_dir.mkdir(parents=True, exist_ok=True)
    seed = f"elixir-{slugify(topic)[:40]}-{sha256_bytes(topic.encode())[:8]}"
    elixir_id = next_available_stem(candidate_dir, seed)
    settled_path = _settled_path(root, elixir_id)
    candidate_path = _candidate_path(root, elixir_id)
    _norm = str(settled_path.relative_to(root))
    if _norm in {str(Path(ref)) for ref in source_outputs}:
        raise ValueError(f"cannot reference self: {_norm}")
    cycle = _detect_elixir_cycle(root, settled_path, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    if settled_path.exists() or candidate_path.exists():
        raise FileExistsError(f"elixir already exists: {elixir_id}")
    now = utc_now()
    candidate_path.write_text(
        _scaffold_elixir_markdown(
            elixir_id=elixir_id,
            protocol=protocol_name,
            topic=topic,
            corpus_id=corpus_id,
            source_outputs=source_outputs,
            iteration=0,
            elixir_state="draft",
            created_at=now,
            updated_at=now,
        ),
        encoding="utf-8",
    )
    _validate_state_for_path(root, "draft", candidate_path)
    return {
        "elixir_id": elixir_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{elixir_id}.md",
        "derived_from": source_outputs,
        "iteration": 0,
        "elixir_state": "draft",
        "protocol": protocol_name,
    }


def distill_elixir(root: Path, elixir_id: str, *, question: str, include_elixir_ids: list[str] | None = None) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    source_path, frontmatter = _read_elixir_anywhere(root, normalized_id)
    if source_path.resolve().parent == (root / ELIXIR_DIR).resolve():
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    source_state = str(frontmatter.get("elixir_state") or "")
    if source_state == "settled":
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    if source_state not in _ACTIVE_ELIXIR_STATES:
        raise ValueError(f"unsupported_source_state: cannot distill elixir from state={source_state or 'unknown'}")
    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    existing = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    # Defense-in-depth: refuse to distill an elixir whose existing provenance was
    # tampered empty or points outside the current corpus allowlist. Prevents
    # silent provenance loss via frontmatter edits.
    if not existing:
        raise ValueError(f"elixir has empty derived_from, refusing to distill: {elixir_id}")
    _validate_source_outputs(root, existing, allowed=allowed)
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for include_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, include_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{include_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {include_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    merged = list(dict.fromkeys([*existing, *allowed, *include_paths]))
    _validate_source_outputs(root, merged, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in merged):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in merged if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, merged)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    target_path = _candidate_path(root, normalized_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    iteration = int(frontmatter.get("iteration", 0) or 0) + 1
    history = frontmatter.get("distill_history") if isinstance(frontmatter.get("distill_history"), list) else []
    history = list(history)
    history.append({"iteration": iteration, "question": question, "at": utc_now()})
    frontmatter.update({"iteration": iteration, "derived_from": merged, "elixir_state": "distilling", "updated_at": utc_now(), "distill_history": history})
    original = source_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1]
    body = body.lstrip("\n")
    _write_elixir_markdown(target_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "distilling", target_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "iteration": iteration,
        "derived_from": merged,
        "elixir_state": "distilling",
    }


def finalize_elixir(root: Path, *, elixir_id: str) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("unsupported_source_state: cannot finalize settled elixir")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)

    if source_state == "candidate":
        raise ValueError("already_candidate: elixir already finalized")
    if source_state not in {"draft", "distilling"}:
        raise ValueError(f"unsupported_source_state: cannot finalize elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    frontmatter.update({"elixir_state": "candidate", "updated_at": utc_now()})
    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "candidate", candidate_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "candidate",
    }


def promote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("already_promoted: settled elixir already exists")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)
    if source_state != "candidate":
        raise ValueError(f"unsupported_source_state: cannot promote elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    _validate_promote_gate(frontmatter)

    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    applied_at_dt = datetime.now(timezone.utc)
    applied_at = applied_at_dt.isoformat()

    settled_frontmatter = dict(frontmatter)
    settled_frontmatter.pop("sealed_at", None)
    settled_frontmatter.update({"elixir_state": "settled", "promoted_at": applied_at})
    tombstone_frontmatter = dict(frontmatter)
    tombstone_frontmatter.pop("sealed_at", None)
    tombstone_frontmatter.update(
        {
            "elixir_state": "superseded",
            "superseded_by": f"{ELIXIR_DIR}/{normalized_id}.md",
            "promoted_at": applied_at,
        }
    )

    settled_text = _render_elixir_document(settled_frontmatter, body)
    tombstone_text = _render_elixir_document(tombstone_frontmatter, body)
    protocol = str(frontmatter.get("protocol") or "")

    settled_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic_text(settled_path, settled_text)
    try:
        _write_atomic_text(candidate_path, tombstone_text)
    except Exception as exc:
        try:
            settled_path.unlink(missing_ok=True)
        except Exception as rollback_exc:
            raise PromoteHalfWriteError(settled_path=settled_path, candidate_path=candidate_path) from rollback_exc
        raise exc

    _validate_state_for_path(root, "settled", settled_path)
    _validate_state_for_path(root, "superseded", candidate_path)

    receipt_result_path = ""
    try:
        primary_hash = compute_file_sha256(settled_path)
        secondary_hash = compute_file_sha256(candidate_path)
        receipt = build_elixir_promotion_receipt(
            root,
            elixir_id=normalized_id,
            slug=slugify(normalized_id),
            settled_path=settled_path,
            candidate_path=candidate_path,
            protocol=protocol,
            applied_at=applied_at_dt,
            note=note,
            primary_path_sha256=primary_hash,
            secondary_path_sha256=secondary_hash,
        )
        receipt_result_path = str(receipt.get("receipt_path") or "")
        receipt_path = root / receipt_result_path
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_execution_receipt_history(root, receipt)
    except FileNotFoundError:
        logging.getLogger("aiwiki").exception("failed to compute elixir promotion receipt hash anchors: %s", normalized_id)
    except Exception:
        logging.getLogger("aiwiki").exception("failed to persist elixir promotion receipt: %s", normalized_id)

    return {
        "elixir_id": normalized_id,
        "path": f"{ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "settled",
        "promoted_at": applied_at,
        "receipt_path": receipt_result_path,
    }


def revert_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, _settled_body = settled_data

    latest_promotion = find_latest_elixir_promotion_receipt(root, elixir_id=normalized_id)
    if latest_promotion is None:
        raise ValueError("promotion_receipt_missing: latest promotion receipt not found")

    source_applied_at = str(latest_promotion.get("applied_at") or "")
    source_action_id = str(latest_promotion.get("action_id") or "")
    bundle = latest_promotion.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")
    expected_settled_hash = bundle.get("primary_path_sha256")
    expected_tombstone_hash = bundle.get("secondary_path_sha256")
    if (
        not isinstance(expected_settled_hash, str)
        or not expected_settled_hash.strip()
        or not isinstance(expected_tombstone_hash, str)
        or not expected_tombstone_hash.strip()
    ):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")

    actual_settled_hash = compute_file_sha256(settled_path)
    if actual_settled_hash != expected_settled_hash:
        raise ValueError("revert_conflict_settled_modified: settled elixir was modified after promotion")

    if candidate_data is None:
        raise ValueError("revert_tombstone_missing: superseded tombstone is required")
    tombstone_frontmatter, tombstone_body = candidate_data
    tombstone_state = str(tombstone_frontmatter.get("elixir_state") or "")
    if tombstone_state != "superseded":
        raise ValueError(f"unsupported_source_state: cannot revert elixir from state={tombstone_state or 'unknown'}")

    actual_tombstone_hash = compute_file_sha256(candidate_path)
    if actual_tombstone_hash != expected_tombstone_hash:
        raise ValueError("revert_conflict_candidate_modified: candidate tombstone no longer matches promotion receipt")

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_reverted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for revert: %s",
            normalized_id,
        )
        dependency_breaks = []

    tombstone_original_text = candidate_path.read_text(encoding="utf-8", errors="replace")
    candidate_frontmatter = dict(tombstone_frontmatter)
    candidate_frontmatter["elixir_state"] = "candidate"
    candidate_frontmatter.pop("superseded_by", None)
    candidate_frontmatter.pop(_PROMOTION_TS_FIELD, None)
    candidate_text = _render_elixir_document(candidate_frontmatter, tombstone_body)

    _write_atomic_text(candidate_path, candidate_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            _write_atomic_text(candidate_path, tombstone_original_text)
        except Exception as rollback_exc:
            raise RevertHalfWriteError(settled_path=settled_path, candidate_path=candidate_path) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or tombstone_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_revert_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        source_receipt_applied_at=source_applied_at,
        source_receipt_action_id=source_action_id,
        dependency_breaks=dependency_breaks,
    )
    receipt_path = root / str(receipt.get("receipt_path") or "")
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_execution_receipt_history(root, receipt)
    except Exception:
        logging.getLogger("aiwiki").exception("failed to persist elixir revert receipt: %s", normalized_id)

    return candidate_path


def demote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, settled_body = settled_data
    settled_state = str(settled_frontmatter.get("elixir_state") or "")
    if settled_state != "settled":
        raise ValueError(f"unsupported_source_state: cannot demote elixir from state={settled_state or 'unknown'}")

    had_candidate_before = candidate_data is not None
    candidate_original_text = candidate_path.read_text(encoding="utf-8", errors="replace") if had_candidate_before else ""
    if candidate_data is not None:
        candidate_frontmatter, _candidate_body = candidate_data
        candidate_state = str(candidate_frontmatter.get("elixir_state") or "")
        if candidate_state != "superseded":
            raise ValueError("demote_conflict_candidate_exists: candidate plane has conflicting non-superseded state")

    demoted_frontmatter = dict(settled_frontmatter)
    demoted_frontmatter["elixir_state"] = "candidate"
    demoted_frontmatter.pop("promoted_at", None)
    demoted_frontmatter.pop("sealed_at", None)
    demoted_frontmatter.pop("superseded_by", None)
    demoted_text = _render_elixir_document(demoted_frontmatter, settled_body)

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_demoted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for demote: %s",
            normalized_id,
        )
        dependency_breaks = []

    _write_atomic_text(candidate_path, demoted_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            if had_candidate_before:
                _write_atomic_text(candidate_path, candidate_original_text)
            else:
                candidate_path.unlink(missing_ok=True)
        except Exception as rollback_exc:
            raise DemoteHalfWriteError(settled_path=settled_path, candidate_path=candidate_path) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_demotion_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        dependency_breaks=dependency_breaks,
    )
    receipt_path = root / str(receipt.get("receipt_path") or "")
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_execution_receipt_history(root, receipt)
    except Exception:
        logging.getLogger("aiwiki").exception("failed to persist elixir demotion receipt: %s", normalized_id)

    return candidate_path
