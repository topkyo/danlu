from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.output_artifacts import collect_output_artifacts
from ..content.outputs import classify_recurring_output_kind
from ..protocol.runtime_config import AUTO_PROMOTION_MIN_OCCURRENCES
from ..protocol.scaffold import ensure_layout
from ..render.paths import append_wiki_log
from ..state.collections import normalize_versioned_record_list_state
from ..state.io import load_json_document, save_json_document
from ..state.paths import output_candidates_state_path
from ..utils.io import atomic_write_text, runtime_write_operation
from ..utils.markdown import write_frontmatter_string_list
from ..utils.time import utc_now


def default_output_candidates_state() -> dict[str, Any]:
    return {"version": 1, "candidates": []}


def load_output_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(output_candidates_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_output_candidates_state,
        list_key="candidates",
    )


def save_output_candidates_state(root: Path, state: dict[str, Any]) -> None:
    save_json_document(output_candidates_state_path(root), state)


def upsert_output_candidate(
    root: Path,
    *,
    artifact_ref: str,
    candidate_state: str,
    created_at: str,
    updated_at: str,
    format: str,
    protocol: str,
    corpus_id: str,
    question: str,
    promoted_to: str = "",
    promoted_at: str = "",
    demoted_at: str = "",
    promotion_origin: str = "manual",
) -> dict[str, Any]:
    state = load_output_candidates_state(root)
    candidates = list(state.get("candidates", []))
    target = None
    for candidate in candidates:
        if str(candidate.get("artifact_ref") or "") == artifact_ref:
            target = candidate
            break
    if target is None:
        target = {"artifact_ref": artifact_ref, "created_at": created_at}
        candidates.append(target)
    target.update(
        {
            "artifact_ref": artifact_ref,
            "candidate_state": candidate_state,
            "created_at": created_at,
            "updated_at": updated_at,
            "format": format,
            "protocol": protocol,
            "corpus_id": corpus_id,
            "question": question,
            "promoted_to": promoted_to,
            "promoted_at": promoted_at,
            "demoted_at": demoted_at,
            "promotion_origin": promotion_origin or "manual",
        }
    )
    state = {"version": 1, "candidates": candidates}
    save_output_candidates_state(root, state)
    return target


def remove_output_candidate(root: Path, artifact_ref: str) -> bool:
    state = load_output_candidates_state(root)
    candidates = [c for c in state.get("candidates", []) if str(c.get("artifact_ref") or "") != artifact_ref]
    removed = len(candidates) != len(state.get("candidates", []))
    save_output_candidates_state(root, {"version": 1, "candidates": candidates})
    return removed


def _find_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    state = load_output_candidates_state(root)
    for candidate in state.get("candidates", []):
        if str(candidate.get("artifact_ref") or "") == artifact_ref:
            return candidate
    raise FileNotFoundError(f"candidate not found: {artifact_ref}")


def write_candidate_frontmatter(
    path: Path,
    *,
    candidate_state: str,
    corpus_id: str = "",
) -> None:
    """Write/update ``candidate_state`` (and optional ``corpus_id``) into the artifact frontmatter.

    Single authoritative writer for candidate audit markers. Behavior:

    - If the file has an existing frontmatter block, update ``candidate_state`` in place
      (and upsert ``corpus_id`` when provided); do not round-trip the YAML (preserves raw
      literals like ``marp: true``).
    - If the file has no frontmatter, synthesize a minimal one rather than silently skip.
      Silent no-op would drop the audit marker and violate AGENTS.md "do not swallow
      errors" + "single writer, many readers".

    This helper is the only sanctioned path to stamp candidate markers onto artifacts;
    ``ask``, ``promote`` and ``demote`` all route through here.
    """
    if not path.exists():
        raise FileNotFoundError(f"candidate artifact not found: {path}")
    original = path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    if not has_frontmatter or close_idx is None:
        header = ["---", f'candidate_state: "{candidate_state}"']
        if corpus_id:
            header.append(f'corpus_id: "{corpus_id}"')
        header.append("---")
        synthesized = header + lines
        atomic_write_text(path, "\n".join(synthesized).rstrip() + "\n")
        return
    filtered = lines[:1] + [
        line
        for line in lines[1:close_idx]
        if not line.startswith("candidate_state:") and not (corpus_id and line.startswith("corpus_id:"))
    ]
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    insertions = [f'candidate_state: "{candidate_state}"']
    if corpus_id:
        insertions.append(f'corpus_id: "{corpus_id}"')
    for offset, line in enumerate(insertions):
        filtered.insert(new_close_idx + offset, line)
    atomic_write_text(path, "\n".join(filtered).rstrip() + "\n")


def write_graph_anchor_frontmatter(path: Path, *, anchors: list[str], force: bool = False) -> None:
    """Write Obsidian-native ``graph_anchor_node_ids`` (sources/judgments only)."""
    write_frontmatter_string_list(
        path,
        "graph_anchor_node_ids",
        anchors,
        force=force,
        require_exists=True,
    )


def write_machine_memory_anchor_frontmatter(path: Path, *, anchors: list[str]) -> None:
    """Write full machine-memory anchors (may include concepts) for HTML/subgraph."""
    write_frontmatter_string_list(
        path,
        "machine_memory_anchor_node_ids",
        anchors,
        require_exists=True,
    )


def demote_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    ensure_layout(root)
    _find_candidate(root, artifact_ref)
    artifact_path = root / artifact_ref
    write_candidate_frontmatter(artifact_path, candidate_state="demoted")
    remove_output_candidate(root, artifact_ref)
    return {"artifact_ref": artifact_ref, "status": "demoted"}


@runtime_write_operation
def promote_recurring_outputs(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for artifact in collect_output_artifacts(root):
        groups.setdefault((artifact["protocol"], artifact["query_signature"]), []).append(artifact)

    generated_at = utc_now()
    enqueued = 0
    promotions: list[dict[str, str]] = []
    for (protocol, query_signature), artifacts in sorted(groups.items()):
        if len(artifacts) < AUTO_PROMOTION_MIN_OCCURRENCES:
            continue
        query = artifacts[0]["query"]
        kind = classify_recurring_output_kind(query, protocol)
        if kind not in {"decision", "judgment"}:
            continue
        candidate = upsert_output_candidate(
            root,
            artifact_ref=artifacts[-1]["path"],
            candidate_state="pending",
            created_at=generated_at,
            updated_at=generated_at,
            format=artifacts[-1].get("format", ""),
            protocol=protocol,
            corpus_id=artifacts[-1].get("corpus_id", ""),
            question=query,
            promotion_origin="nightly-recurring",
        )
        candidate["recurring_kind"] = kind
        state = load_output_candidates_state(root)
        for item in state.get("candidates", []):
            if str(item.get("artifact_ref") or "") == artifacts[-1]["path"]:
                item["recurring_kind"] = kind
                break
        save_output_candidates_state(root, state)
        enqueued += 1
        promotions.append(
            {
                "kind": kind,
                "action": "enqueued",
                "path": candidate["artifact_ref"],
                "candidate_ref": candidate["artifact_ref"],
                "protocol": protocol,
                "query": query,
                "query_signature": query_signature,
                "occurrences": str(len(artifacts)),
                "latest_artifact": artifacts[-1]["path"],
            }
        )
        append_wiki_log(
            root,
            "enqueue",
            query,
            [
                f"kind: `{kind}`",
                f"protocol: `{protocol}`",
                "action: `enqueued`",
                f"occurrences: `{len(artifacts)}`",
                f"candidate_ref: `{candidate['artifact_ref']}`",
                f"latest_artifact: `{artifacts[-1]['path']}`",
            ],
        )

    return {
        "count": enqueued,
        "created": 0,
        "updated": 0,
        "pages": promotions,
    }
