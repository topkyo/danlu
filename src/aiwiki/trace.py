"""P1 / M8.2 — Evidence chain trace resolver.

输入任一资产 ID（raw 路径 / source / judgment / decision / elixir / l3 proposal /
receipt action_id），输出 provenance 树。

设计：
- read-only，纯派生，每次重扫（vault 规模够小）
- ID 路由按前缀 / 形态识别 9 类
- 循环引用：visited set + 二次访问标记 (cycle)
- 默认向上（parents），`--children/--depth` 切换

不引入第三方依赖；只用 stdlib + 既有 helper：
- `aiwiki.utils.markdown.parse_frontmatter`
- `aiwiki.state.io.load_json_document` + `aiwiki.state.paths.l3_proposal_state_path`
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from aiwiki.execution.alchemy_helpers import CANDIDATE_ELIXIR_DIR
from aiwiki.state.paths import STAGING_PROPOSALS_DIR
from aiwiki.utils.markdown import parse_frontmatter

# 资产种类 — 用前缀 / 路径形态识别
AssetKind = str  # "raw" | "source" | "concept" | "derived" | "judgment" | "decision" | "elixir" | "proposal" | "receipt" | "unknown"

# 安全深度上限，避免病态数据导致深递归
_MAX_DEPTH = 10


@dataclass
class TraceNode:
    """一棵 provenance 树的节点。"""

    id: str
    kind: AssetKind
    label: str = ""
    path: str = ""  # 仓库相对路径（若适用）
    parents: list["TraceNode"] = field(default_factory=list)
    children: list["TraceNode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cycle: bool = False
    not_found: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "path": self.path,
        }
        if self.parents:
            out["parents"] = [n.to_dict() for n in self.parents]
        if self.children:
            out["children"] = [n.to_dict() for n in self.children]
        if self.metadata:
            out["metadata"] = self.metadata
        if self.cycle:
            out["cycle"] = True
        if self.not_found:
            out["not_found"] = True
        return out


def resolve_trace(
    root: Path,
    asset_id: str,
    *,
    direction: str = "up",
    max_depth: int = 5,
) -> TraceNode:
    """主入口：识别 asset 类型并递归组装 trace 树。

    direction:
        - "up"   : 只展开 parents
        - "down" : 只展开 children
        - "both" : 同时展开 parents + children
    """
    if direction not in {"up", "down", "both"}:
        raise ValueError(f"direction must be one of up/down/both: {direction!r}")
    depth = max(1, min(int(max_depth), _MAX_DEPTH))
    visited: set[str] = set()
    return _resolve_any(root, asset_id.strip(), direction=direction, depth=depth, visited=visited)


# --- ID router ---------------------------------------------------------------


def _classify(asset_id: str) -> AssetKind:
    text = asset_id.strip()
    if not text:
        return "unknown"
    if text.startswith("raw/") or text.startswith("./raw/"):
        return "raw"
    if text.startswith("wiki/sources/") or text.startswith("source-") or text.startswith("discovered-"):
        return "source"
    if text.startswith("wiki/concepts/") or text.startswith("concept-"):
        return "concept"
    if text.startswith("wiki/derived/") or text.startswith("./wiki/derived/") or text.startswith("derived-"):
        return "derived"
    if text.startswith("wiki/judgments/") or text.startswith("judgment-"):
        return "judgment"
    if text.startswith("wiki/decisions/") or text.startswith("decision-"):
        return "decision"
    if text.startswith("wiki/elixirs/") or text.startswith(f"{CANDIDATE_ELIXIR_DIR}/") or text.startswith("elixir-"):
        return "elixir"
    if text.startswith("proposal-") or text.startswith("L3-proposal-") or text.startswith(f"{STAGING_PROPOSALS_DIR}/"):
        return "proposal"
    # receipt action_id 通常是 UUID 风格；fallback
    if len(text) >= 8 and "-" in text and not text.endswith(".md") and "/" not in text:
        return "receipt"
    return "unknown"


def _resolve_any(
    root: Path,
    asset_id: str,
    *,
    direction: str,
    depth: int,
    visited: set[str],
) -> TraceNode:
    if depth <= 0 or not asset_id:
        return TraceNode(id=asset_id, kind=_classify(asset_id) if asset_id else "unknown", label="(depth limit)")

    if asset_id in visited:
        return TraceNode(id=asset_id, kind=_classify(asset_id), label=asset_id, cycle=True)
    visited = visited | {asset_id}

    kind = _classify(asset_id)
    if kind == "raw":
        return _resolve_raw(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "source":
        return _resolve_source(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "concept":
        return _resolve_concept(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "derived":
        return _resolve_derived(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "judgment":
        return _resolve_judgment(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "decision":
        return _resolve_decision(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "elixir":
        return _resolve_elixir(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "proposal":
        return _resolve_proposal(root, asset_id, direction=direction, depth=depth, visited=visited)
    if kind == "receipt":
        return _resolve_receipt(root, asset_id, direction=direction, depth=depth, visited=visited)
    # bare-slug fallback: classify returned "unknown" but a concept page exists with this slug.
    # Scoped to concept layer only (concept slug namespace 与 raw/source 时间戳 id 不重叠).
    if kind == "unknown" and "/" not in asset_id and not asset_id.endswith(".md"):
        bare = asset_id.removesuffix(".md")
        candidate = root / "wiki" / "concepts" / f"{bare}.md"
        if candidate.exists() and candidate.is_file():
            return _resolve_concept(root, asset_id, direction=direction, depth=depth, visited=visited)
    return TraceNode(id=asset_id, kind="unknown", label=asset_id, not_found=True)


# --- specialized resolvers --------------------------------------------------


def _resolve_raw(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    rel = asset_id.removeprefix("./").lstrip("/")
    abs_path = root / rel
    node = TraceNode(id=rel, kind="raw", label=Path(rel).name, path=rel)
    if not abs_path.exists():
        node.not_found = True
    if direction in {"down", "both"}:
        # 找哪些 wiki/sources 引用此 raw
        for src_path, fm in _iter_curated_pages(root, "wiki/sources"):
            sources = _as_str_list(fm.get("source_files"))
            if any(_path_matches_raw(s, rel) for s in sources):
                src_id = str(fm.get("id") or src_path.stem)
                child = _resolve_any(root, src_id, direction=direction, depth=depth - 1, visited=visited)
                node.children.append(child)
    return node


def _resolve_source(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    path, fm = _find_curated(root, "wiki/sources", asset_id)
    if path is None:
        return TraceNode(id=asset_id, kind="source", label=asset_id, not_found=True)
    rel = path.relative_to(root).as_posix()
    node = TraceNode(
        id=str(fm.get("id") or path.stem),
        kind="source",
        label=str(fm.get("title") or path.stem),
        path=rel,
        metadata={"sha256": str(fm.get("source_sha256") or "")[:12]} if fm.get("source_sha256") else {},
    )
    if direction in {"up", "both"}:
        for raw_ref in _as_str_list(fm.get("source_files")):
            raw_rel = _normalize_raw_ref(raw_ref)
            if not raw_rel:
                continue
            node.parents.append(_resolve_any(root, raw_rel, direction="up", depth=depth - 1, visited=visited))
    if direction in {"down", "both"}:
        # 哪些 judgments/decisions/elixirs 引用此 source
        node.children.extend(
            _find_referrers(
                root,
                source_rel=rel,
                source_id=node.id,
                direction=direction,
                depth=depth - 1,
                visited=visited,
            )
        )
        # source → concept derived edge: scan wiki/concepts/* whose source_pages references this source
        for c_path, c_fm in _iter_curated_pages(root, "wiki/concepts"):
            sp = _as_str_list(c_fm.get("source_pages"))
            if any(_concept_source_matches(entry, rel, node.id) for entry in sp):
                concept_id = str(c_fm.get("id") or c_path.stem)
                node.children.append(
                    _resolve_any(root, concept_id, direction=direction, depth=depth - 1, visited=visited)
                )
        # source → derived edge: scan wiki/derived/* whose citations reference this source
        seen_derived: set[str] = set()
        for d_path, d_fm in _iter_curated_pages(root, "wiki/derived"):
            citations = _as_str_list(d_fm.get("citations"))
            matched = False
            for entry in citations:
                target = entry.split("#", 1)[0].strip().strip('"').strip("'")
                if not target:
                    continue
                if target == rel or target.endswith("/" + Path(rel).name) or target == node.id:
                    matched = True
                    break
            if not matched:
                continue
            derived_id = str(d_fm.get("id") or d_path.stem)
            if derived_id in seen_derived:
                continue
            seen_derived.add(derived_id)
            node.children.append(_resolve_any(root, derived_id, direction=direction, depth=depth - 1, visited=visited))
    return node


def _resolve_concept(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    path, fm = _find_curated(root, "wiki/concepts", asset_id)
    if path is None:
        return TraceNode(id=asset_id, kind="concept", label=asset_id, not_found=True)
    rel = path.relative_to(root).as_posix()
    node = TraceNode(
        id=str(fm.get("id") or path.stem),
        kind="concept",
        label=str(fm.get("title") or path.stem),
        path=rel,
    )
    if direction in {"up", "both"}:
        for src_ref in _as_str_list(fm.get("source_pages")):
            ref = src_ref.strip()
            if not ref:
                continue
            node.parents.append(_resolve_any(root, ref, direction="up", depth=depth - 1, visited=visited))
    # concept 是叶子节点：source→concept 边由 source 侧 down 展开提供，避免双向重复
    return node


def _resolve_derived(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    path, fm = _find_curated(root, "wiki/derived", asset_id)
    if path is None:
        return TraceNode(id=asset_id, kind="derived", label=asset_id, not_found=True)
    rel = path.relative_to(root).as_posix()
    node = TraceNode(
        id=str(fm.get("id") or path.stem),
        kind="derived",
        label=str(fm.get("title") or path.stem),
        path=rel,
        metadata={"protocol": str(fm.get("protocol") or "")} if fm.get("protocol") else {},
    )
    if direction in {"up", "both"}:
        for cit in _as_str_list(fm.get("citations")):
            ref = cit.strip()
            if not ref:
                continue
            # strip anchor fragment if any (`wiki/sources/x.md#sha256`)
            target = ref.split("#", 1)[0] if "#" in ref else ref
            node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
    if direction in {"down", "both"}:
        # 哪些 elixir 引用此 derived 页面
        seen_elixir: set[str] = set()
        for elixir_subdir in ("wiki/elixirs", CANDIDATE_ELIXIR_DIR):
            for e_path, e_fm in _iter_curated_pages(root, elixir_subdir):
                refs = _as_str_list(e_fm.get("derived_from"))
                if not any(_derived_ref_matches(r, rel, node.id) for r in refs):
                    continue
                elixir_id = str(e_fm.get("id") or e_path.stem)
                if elixir_id in seen_elixir:
                    continue
                seen_elixir.add(elixir_id)
                node.children.append(
                    _resolve_any(root, elixir_id, direction=direction, depth=depth - 1, visited=visited)
                )
    return node


def _resolve_judgment(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    path, fm = _find_curated(root, "wiki/judgments", asset_id)
    if path is None:
        return TraceNode(id=asset_id, kind="judgment", label=asset_id, not_found=True)
    rel = path.relative_to(root).as_posix()
    node = TraceNode(
        id=str(fm.get("id") or path.stem),
        kind="judgment",
        label=str(fm.get("title") or path.stem),
        path=rel,
        metadata={"status": str(fm.get("status") or ""), "confidence": str(fm.get("confidence") or "")},
    )
    if direction in {"up", "both"}:
        for cit in _as_str_list(fm.get("citations")):
            citation = cit.strip()
            if not citation:
                continue
            node.parents.append(_resolve_any(root, citation, direction="up", depth=depth - 1, visited=visited))
    if direction in {"down", "both"}:
        # 找 decision.supports 反向 + elixir derived_from
        for dec_path, dec_fm in _iter_curated_pages(root, "wiki/decisions"):
            supports = _as_str_list(dec_fm.get("supports"))
            if any(_judgment_ref_matches(s, rel, node.id) for s in supports):
                node.children.append(
                    _resolve_any(
                        root,
                        str(dec_fm.get("id") or dec_path.stem),
                        direction=direction,
                        depth=depth - 1,
                        visited=visited,
                    )
                )
    return node


def _resolve_decision(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    path, fm = _find_curated(root, "wiki/decisions", asset_id)
    if path is None:
        return TraceNode(id=asset_id, kind="decision", label=asset_id, not_found=True)
    rel = path.relative_to(root).as_posix()
    node = TraceNode(
        id=str(fm.get("id") or path.stem),
        kind="decision",
        label=str(fm.get("title") or path.stem),
        path=rel,
        metadata={"status": str(fm.get("status") or ""), "protocol": str(fm.get("protocol") or "")},
    )
    if direction in {"up", "both"}:
        for support in _as_str_list(fm.get("supports")):
            target = support.strip()
            if not target:
                continue
            node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
        for cit in _as_str_list(fm.get("citations")):
            target = cit.strip()
            if not target:
                continue
            node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
    return node


def _resolve_elixir(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    # 先 settled (wiki/elixirs/) 后 candidate (.aiwiki/staging/elixirs/)
    candidate_dirs = [root / "wiki" / "elixirs", root / CANDIDATE_ELIXIR_DIR]
    elixir_id = asset_id
    if asset_id.startswith("wiki/elixirs/") or asset_id.startswith(f"{CANDIDATE_ELIXIR_DIR}/"):
        elixir_id = Path(asset_id).stem
    fm: dict[str, Any] = {}
    found_path: Path | None = None
    for d in candidate_dirs:
        if not d.exists():
            continue
        candidate = d / f"{elixir_id}.md"
        if candidate.exists():
            found_path = candidate
            fm = parse_frontmatter(candidate.read_text(encoding="utf-8", errors="replace"))
            break
    if found_path is None:
        return TraceNode(id=elixir_id, kind="elixir", label=elixir_id, not_found=True)
    rel = found_path.relative_to(root).as_posix()
    plane = "settled" if "wiki/elixirs/" in rel else "candidate"
    node = TraceNode(
        id=elixir_id,
        kind="elixir",
        label=str(fm.get("title") or elixir_id),
        path=rel,
        metadata={"plane": plane, "status": str(fm.get("status") or "")},
    )
    if direction in {"up", "both"}:
        for ref in _as_str_list(fm.get("derived_from")):
            target = ref.strip()
            if not target:
                continue
            node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
        for ref in _as_str_list(fm.get("evidence")):
            target = ref.strip()
            if not target:
                continue
            node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
    return node


def _resolve_proposal(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    from aiwiki.state.io import load_json_document
    from aiwiki.state.paths import l3_proposal_state_path

    state_path = l3_proposal_state_path(root)
    if not state_path.exists():
        return TraceNode(id=asset_id, kind="proposal", label=asset_id, not_found=True)
    state = load_json_document(state_path)
    proposals = state.get("proposals", []) if isinstance(state, dict) else []
    target_id = Path(asset_id).stem if "/" in asset_id else asset_id
    found: dict[str, Any] | None = None
    for p in proposals:
        if not isinstance(p, dict):
            continue
        if str(p.get("proposal_id") or "") == target_id:
            found = p
            break
    if found is None:
        return TraceNode(id=asset_id, kind="proposal", label=asset_id, not_found=True)
    proposal_id = str(found.get("proposal_id") or asset_id)
    node = TraceNode(
        id=proposal_id,
        kind="proposal",
        label=f"L3 proposal: {proposal_id}",
        path=str(found.get("proposal_path") or ""),
        metadata={
            "kind": str(found.get("kind") or ""),
            "state": str(found.get("state") or ""),
            "target_file": str(found.get("target_file") or ""),
        },
    )
    if direction in {"up", "both"}:
        evidence_refs = found.get("evidence_refs")
        if isinstance(evidence_refs, list):
            for ref in evidence_refs:
                target = str(ref or "").strip()
                if not target:
                    continue
                node.parents.append(_resolve_any(root, target, direction="up", depth=depth - 1, visited=visited))
    return node


def _resolve_receipt(root: Path, asset_id: str, *, direction: str, depth: int, visited: set[str]) -> TraceNode:
    """receipt action_id → 找到 receipt 的 subject_id，再 trace 主体。"""
    receipts_path = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
    if not receipts_path.exists():
        return TraceNode(id=asset_id, kind="receipt", label=asset_id, not_found=True)
    matched: dict[str, Any] | None = None
    try:
        text = receipts_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return TraceNode(id=asset_id, kind="receipt", label=asset_id, not_found=True)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if str(record.get("action_id") or "") == asset_id:
            matched = record
            break
    if matched is None:
        return TraceNode(id=asset_id, kind="receipt", label=asset_id, not_found=True)
    subject_id = str(matched.get("subject_id") or "")
    subject_kind = str(matched.get("subject_kind") or "")
    node = TraceNode(
        id=asset_id,
        kind="receipt",
        label=f"receipt: {subject_kind} {subject_id}",
        metadata={
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "operation": str(matched.get("operation") or ""),
        },
    )
    if direction in {"up", "both"} and subject_id:
        node.parents.append(_resolve_any(root, subject_id, direction="up", depth=depth - 1, visited=visited))
    return node


# --- helpers ----------------------------------------------------------------


def _find_curated(root: Path, subdir: str, asset_id: str) -> tuple[Path | None, dict[str, Any]]:
    """通过 id 或 path 查找 wiki/sources|judgments|decisions/*.md。"""
    base = root / subdir
    if not base.exists():
        return None, {}
    # 直接 path 匹配
    if asset_id.startswith(subdir + "/") or asset_id.startswith("./" + subdir + "/"):
        rel = asset_id.removeprefix("./")
        path = root / rel
        if path.exists() and path.is_file():
            return path, parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    # 文件名匹配（with or without .md）
    bare = asset_id.removesuffix(".md")
    direct = base / f"{bare}.md"
    if direct.exists():
        return direct, parse_frontmatter(direct.read_text(encoding="utf-8", errors="replace"))
    # frontmatter id 匹配（线性扫描）
    for path, fm in _iter_curated_pages(root, subdir):
        if str(fm.get("id") or "") == bare:
            return path, fm
    return None, {}


def _iter_curated_pages(root: Path, subdir: str) -> Iterable[tuple[Path, dict[str, Any]]]:
    base = root / subdir
    if not base.exists():
        return
    for path in sorted(base.glob("*.md")):
        if not path.is_file():
            continue
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        yield path, fm


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _path_matches_raw(source_file: str, raw_rel: str) -> bool:
    text = (source_file or "").strip()
    if not text:
        return False
    return text.endswith(raw_rel) or raw_rel in text


def _concept_source_matches(entry: str, source_rel: str, source_id: str) -> bool:
    """Concept frontmatter `source_pages` 项是否指向当前 source。"""
    text = (entry or "").strip().strip("'\"`")
    if not text:
        return False
    if text == source_rel:
        return True
    if text.endswith("/" + Path(source_rel).name):
        return True
    if source_id and source_id in text:
        return True
    return False


def _normalize_raw_ref(value: str) -> str:
    text = (value or "").strip().strip("'\"`")
    # 绝对路径 → 截到 raw/ 之后
    if "raw/" in text:
        idx = text.find("raw/")
        return text[idx:]
    return text


def _judgment_ref_matches(supports_value: str, judgment_rel: str, judgment_id: str) -> bool:
    text = supports_value.strip()
    if not text:
        return False
    return text == judgment_rel or text.endswith("/" + Path(judgment_rel).name) or judgment_id in text


def _derived_ref_matches(ref_value: str, derived_rel: str, derived_id: str) -> bool:
    text = (ref_value or "").strip().strip("'\"`")
    if not text:
        return False
    if "#" in text:
        text = text.split("#", 1)[0]
    if text == derived_rel:
        return True
    if text.endswith("/" + Path(derived_rel).name):
        return True
    if derived_id and derived_id in text:
        return True
    return False


def _find_referrers(
    root: Path,
    *,
    source_rel: str,
    source_id: str,
    direction: str,
    depth: int,
    visited: set[str],
) -> list[TraceNode]:
    """找哪些 judgment/decision 引用了某 source。"""
    referrers: list[TraceNode] = []
    for subdir in ("wiki/judgments", "wiki/decisions"):
        for path, fm in _iter_curated_pages(root, subdir):
            citations = _as_str_list(fm.get("citations"))
            if any(c.strip() == source_rel or source_id in c for c in citations):
                node_id = str(fm.get("id") or path.stem)
                referrers.append(_resolve_any(root, node_id, direction=direction, depth=depth, visited=visited))
    return referrers


# --- rendering --------------------------------------------------------------


def render_trace_text(node: TraceNode, *, direction: str = "up") -> str:
    """生成 ASCII 树。direction 决定显示 parents 还是 children。"""
    lines: list[str] = []
    _render_node(node, prefix="", is_last=True, lines=lines, direction=direction, is_root=True)
    return "\n".join(lines)


def _render_node(
    node: TraceNode,
    *,
    prefix: str,
    is_last: bool,
    lines: list[str],
    direction: str,
    is_root: bool,
) -> None:
    if is_root:
        lines.append(_format_node_line(node))
        next_prefix = ""
    else:
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + _format_node_line(node))
        next_prefix = prefix + ("    " if is_last else "│   ")

    children = list(node.parents) if direction == "up" else list(node.children)
    if direction == "both":
        children = list(node.parents) + list(node.children)
    for idx, child in enumerate(children):
        _render_node(
            child,
            prefix=next_prefix,
            is_last=idx == len(children) - 1,
            lines=lines,
            direction=direction,
            is_root=False,
        )


def _format_node_line(node: TraceNode) -> str:
    bits: list[str] = [f"[{node.kind}]", node.id]
    if node.label and node.label != node.id:
        bits.append(f"— {node.label}")
    if node.path and node.path != node.id:
        bits.append(f"({node.path})")
    if node.cycle:
        bits.append("(cycle)")
    if node.not_found:
        bits.append("(not found)")
    return " ".join(bits)
