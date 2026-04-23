from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import app_compile as _app_compile
from ..app_compile import file_back
from ..app_protocol import ensure_layout
from ..app_state import load_output_candidates_state, remove_output_candidate, upsert_output_candidate
from ..app_utils import parse_frontmatter


def _find_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    state = load_output_candidates_state(root)
    for candidate in state.get("candidates", []):
        if str(candidate.get("artifact_ref") or "") == artifact_ref:
            return candidate
    raise FileNotFoundError(f"candidate not found: {artifact_ref}")


def _insert_candidate_state(path: Path, state_value: str) -> None:
    original = path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                replaced = list(lines)
                if any(line.startswith("candidate_state:") for line in replaced[1:idx]):
                    for j in range(1, idx):
                        if replaced[j].startswith("candidate_state:"):
                            replaced[j] = f'candidate_state: "{state_value}"'
                            break
                else:
                    replaced.insert(idx, f'candidate_state: "{state_value}"')
                path.write_text("\n".join(replaced).rstrip() + "\n", encoding="utf-8")
                return


def promote_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    ensure_layout(root)
    candidate = _find_candidate(root, artifact_ref)
    artifact_path = root / artifact_ref
    text = artifact_path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(text)
    title = str(candidate.get("question") or frontmatter.get("title") or artifact_path.stem)
    # 阶段 1：所有 promote 统一落到 wiki/derived/（contract SC4）。
    # nightly 登记的 recurring_kind（decision/judgment）只作为元数据保留在 candidate 里，
    # 真正分流到 wiki/decisions|judgments 是阶段 3 的 L2 协议沉淀能力。
    kind = "derived"
    _insert_candidate_state(artifact_path, "promoted")
    result = file_back(root, artifact_ref, title=title, kind=kind)
    promoted_path = result["path"]
    filed_at = _app_compile.utc_now()
    upsert_output_candidate(
        root,
        artifact_ref=artifact_ref,
        candidate_state="promoted",
        created_at=str(candidate.get("created_at") or filed_at),
        updated_at=filed_at,
        format=str(candidate.get("format") or ""),
        protocol=str(candidate.get("protocol") or result.get("protocol") or ""),
        corpus_id=str(candidate.get("corpus_id") or ""),
        question=str(candidate.get("question") or ""),
        promoted_to=promoted_path,
        promoted_at=filed_at,
        promotion_origin=str(candidate.get("promotion_origin") or "manual"),
    )
    return {"artifact_ref": artifact_ref, "promoted_path": promoted_path, "status": "promoted"}


def demote_candidate(root: Path, artifact_ref: str) -> dict[str, Any]:
    ensure_layout(root)
    _find_candidate(root, artifact_ref)
    artifact_path = root / artifact_ref
    _insert_candidate_state(artifact_path, "demoted")
    remove_output_candidate(root, artifact_ref)
    return {"artifact_ref": artifact_ref, "status": "demoted"}
