from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_state import load_active_corpora_state, load_output_candidates_state
from ..app_utils import next_available_stem, parse_frontmatter, sha256_bytes, slugify, utc_now

ELIXIR_DIR = "wiki/elixirs"
CANDIDATE_ELIXIR_DIR = "output/_candidates/elixirs"
ELIXIR_STATE_VALUES = {"draft", "distilling", "candidate", "settled", "superseded"}


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
    path.write_text(_render_inserted_frontmatter(serializable) + body, encoding="utf-8")


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
    if str(frontmatter.get("elixir_state") or "") == "settled":
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
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


def seal_elixir(root: Path, elixir_id: str) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    source_path, frontmatter = _read_elixir_anywhere(root, normalized_id)
    if str(frontmatter.get("elixir_state") or "") == "settled":
        raise ValueError(f"elixir already sealed: {elixir_id}")
    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    target_path = _settled_path(root, normalized_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if any(str(Path(ref)) == str(target_path.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {target_path.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, target_path, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    sealed_at = utc_now()
    frontmatter.update({"elixir_state": "settled", "sealed_at": sealed_at, "updated_at": utc_now()})
    original = source_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    _write_elixir_markdown(target_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "settled", target_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "settled",
        "sealed_at": sealed_at,
    }
