from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_protocol import ensure_layout
from ..app_state import load_output_candidates_state, remove_output_candidate


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
        path.write_text("\n".join(synthesized).rstrip() + "\n", encoding="utf-8")
        return
    filtered = lines[:1] + [
        line
        for line in lines[1:close_idx]
        if not line.startswith("candidate_state:")
        and not (corpus_id and line.startswith("corpus_id:"))
    ]
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    insertions = [f'candidate_state: "{candidate_state}"']
    if corpus_id:
        insertions.append(f'corpus_id: "{corpus_id}"')
    for offset, line in enumerate(insertions):
        filtered.insert(new_close_idx + offset, line)
    path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")


def _write_frontmatter_string_list(
    path: Path,
    key: str,
    anchors: list[str],
    *,
    force: bool = False,
) -> None:
    if not path.exists():
        raise FileNotFoundError(f"frontmatter target not found: {path}")
    cleaned = [str(item).strip() for item in anchors if str(item).strip()]
    if not cleaned and not force:
        return
    block = [f"{key}:"]
    if cleaned:
        block.extend([f'  - "{item}"' for item in cleaned])
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
        header = ["---", *block, "---"]
        synthesized = header + lines
        path.write_text("\n".join(synthesized).rstrip() + "\n", encoding="utf-8")
        return
    filtered: list[str] = lines[:1]
    skip_list_items = False
    for item in lines[1:close_idx]:
        if item.startswith(f"{key}:"):
            skip_list_items = True
            continue
        if skip_list_items and item.startswith("  - "):
            continue
        skip_list_items = False
        filtered.append(item)
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    for offset, line in enumerate(block):
        filtered.insert(new_close_idx + offset, line)
    path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")


def write_graph_anchor_frontmatter(path: Path, *, anchors: list[str], force: bool = False) -> None:
    """Write Obsidian-native ``graph_anchor_node_ids`` (sources/judgments only)."""
    _write_frontmatter_string_list(path, "graph_anchor_node_ids", anchors, force=force)


def write_machine_memory_anchor_frontmatter(path: Path, *, anchors: list[str]) -> None:
    """Write full machine-memory anchors (may include concepts) for HTML/subgraph."""
    _write_frontmatter_string_list(path, "machine_memory_anchor_node_ids", anchors)


def promote_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    """Legacy candidate promote path removed (W8): use judgment-only file-back instead."""
    _ = (root, artifact_ref)
    raise ValueError(
        "promote_candidate via wiki/derived file-back was removed; use aiwiki file-back <artifact> (judgment-only)."
    )


def demote_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    ensure_layout(root)
    _find_candidate(root, artifact_ref)
    artifact_path = root / artifact_ref
    write_candidate_frontmatter(artifact_path, candidate_state="demoted")
    remove_output_candidate(root, artifact_ref)
    return {"artifact_ref": artifact_ref, "status": "demoted"}
