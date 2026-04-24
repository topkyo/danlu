from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_state import load_active_corpora_state, load_output_candidates_state
from ..app_utils import next_available_stem, parse_frontmatter, sha256_bytes, slugify, utc_now

ELIXIR_DIR = "wiki/elixirs"


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
        if not ref.startswith("wiki/derived/"):
            raise ValueError(f"source output must be under wiki/derived/: {ref}")
        if not (root / ref).is_file():
            raise ValueError(f"source output missing: {ref}")
        if ref not in allowed:
            raise ValueError(f"source output is not a promoted candidate for this corpus: {ref}")


def _scaffold_elixir_markdown(*, elixir_id: str, topic: str, corpus_id: str, source_outputs: list[str], iteration: int, elixir_state: str, created_at: str, updated_at: str, distill_history: list[dict[str, Any]] | None = None) -> str:
    frontmatter = {
        "elixir_id": elixir_id,
        "elixir_state": elixir_state,
        "iteration": iteration,
        "source_corpus": corpus_id,
        "source_outputs": source_outputs,
        "topic": topic,
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


def start_elixir(root: Path, corpus_id: str, *, topic: str) -> dict[str, Any]:
    _find_corpus(root, corpus_id)  # validate corpus exists
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    if not promoted:
        raise ValueError(f"no promoted outputs for corpus {corpus_id}")
    source_outputs = [item["promoted_to"] for item in promoted if item.get("promoted_to")]
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    path = root / ELIXIR_DIR
    path.mkdir(parents=True, exist_ok=True)
    seed = f"elixir-{slugify(topic)[:40]}-{sha256_bytes(topic.encode())[:8]}"
    elixir_id = next_available_stem(path, seed)
    path = path / f"{elixir_id}.md"
    now = utc_now()
    path.write_text(_scaffold_elixir_markdown(elixir_id=elixir_id, topic=topic, corpus_id=corpus_id, source_outputs=source_outputs, iteration=0, elixir_state="forming", created_at=now, updated_at=now), encoding="utf-8")
    return {"elixir_id": elixir_id, "path": f"{ELIXIR_DIR}/{elixir_id}.md", "source_outputs": source_outputs, "iteration": 0, "elixir_state": "forming"}


def distill_elixir(root: Path, elixir_id: str, *, question: str) -> dict[str, Any]:
    path = root / ELIXIR_DIR / f"{elixir_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"elixir not found: {elixir_id}")
    frontmatter = _parse_elixir_frontmatter(path)
    if str(frontmatter.get("elixir_state") or "") == "sealed":
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    corpus_id = str(frontmatter.get("source_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    existing = [str(item) for item in frontmatter.get("source_outputs", []) if isinstance(item, str)]
    # Defense-in-depth: refuse to distill an elixir whose existing provenance was
    # tampered empty or points outside the current corpus allowlist. Prevents
    # silent provenance loss via frontmatter edits.
    if not existing:
        raise ValueError(f"elixir has empty source_outputs, refusing to distill: {elixir_id}")
    _validate_source_outputs(root, existing, allowed=allowed)
    merged = list(dict.fromkeys([*existing, *allowed]))
    _validate_source_outputs(root, merged, allowed=allowed)
    iteration = int(frontmatter.get("iteration", 0) or 0) + 1
    history = frontmatter.get("distill_history") if isinstance(frontmatter.get("distill_history"), list) else []
    history = list(history)
    history.append({"iteration": iteration, "question": question, "at": utc_now()})
    frontmatter.update({"iteration": iteration, "source_outputs": merged, "elixir_state": "forming", "updated_at": utc_now(), "distill_history": history})
    original = path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1]
    body = body.lstrip("\n")
    _write_elixir_markdown(path, frontmatter=frontmatter, body=body)
    return {"elixir_id": elixir_id, "path": f"{ELIXIR_DIR}/{elixir_id}.md", "iteration": iteration, "source_outputs": merged, "elixir_state": "forming"}


def seal_elixir(root: Path, elixir_id: str) -> dict[str, Any]:
    path = root / ELIXIR_DIR / f"{elixir_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"elixir not found: {elixir_id}")
    frontmatter = _parse_elixir_frontmatter(path)
    if str(frontmatter.get("elixir_state") or "") == "sealed":
        raise ValueError(f"elixir already sealed: {elixir_id}")
    corpus_id = str(frontmatter.get("source_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("source_outputs", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    sealed_at = utc_now()
    frontmatter.update({"elixir_state": "sealed", "sealed_at": sealed_at, "updated_at": utc_now()})
    original = path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    _write_elixir_markdown(path, frontmatter=frontmatter, body=body)
    return {"elixir_id": elixir_id, "path": f"{ELIXIR_DIR}/{elixir_id}.md", "elixir_state": "sealed", "sealed_at": sealed_at}
