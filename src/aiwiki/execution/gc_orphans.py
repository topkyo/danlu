"""Explicit GC for broken file-backs, noise concepts, and misdrops."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lifecycle.provenance_scrub import iter_curated_pages, path_exists_in_root
from ..memory.state import load_machine_memory
from ..utils.io import runtime_write_operation
from ..utils.markdown import frontmatter_string_list, parse_frontmatter
from ..utils.path import relative_path
from .receipts import write_execution_receipt

NOISE_SLUGS = frozenset(
    {
        "because",
        "aio",
        "api",
        "brain",
        "autonomous",
        "environment",
        "history-ethos-garden",
    }
)
HUB_WHITELIST = frozenset(
    {
        "llm",
        "knowledge",
        "memory",
        "obsidian",
        "agent",
        "judgment",
        "evidence",
        "concept",
    }
)
MISDROP_MARKERS = ("vphone-aio", "34306/vphone")


def _page_kind(rel: str) -> str:
    if rel.startswith("wiki/judgments/"):
        return "judgment"
    if rel.startswith("wiki/derived/"):
        return "derived"
    if rel.startswith("wiki/elixirs/"):
        return "elixir"
    if rel.startswith("wiki/concepts/"):
        return "concept"
    if rel.startswith("wiki/sources/"):
        return "source"
    if rel.startswith("raw/"):
        return "raw"
    return "page"


def _collect_broken_candidates(
    root: Path,
    *,
    include_judgments: bool,
    include_derived: bool,
    include_elixirs: bool,
    force_degraded: bool,
) -> list[dict[str, Any]]:
    allowed: set[str] = set()
    if include_judgments:
        allowed.add("wiki/judgments")
    if include_derived:
        allowed.add("wiki/derived")
    if include_elixirs:
        allowed.add("wiki/elixirs")
    if not allowed:
        return []

    deleting: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for path in iter_curated_pages(root):
        rel = relative_path(root, path)
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent not in allowed:
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        status = str(fm.get("provenance_status") or "").strip()
        if status == "broken" or (force_degraded and status == "degraded"):
            candidates.append(
                {
                    "path": rel,
                    "kind": _page_kind(rel),
                    "reason": f"provenance_status={status}",
                    "status": status,
                }
            )
            deleting.add(rel)

    # Elixir: also GC when all derived_from anchors missing or already deleting.
    if include_elixirs:
        elixirs_dir = root / "wiki" / "elixirs"
        if elixirs_dir.is_dir():
            for path in sorted(elixirs_dir.glob("*.md")):
                rel = relative_path(root, path)
                if any(c["path"] == rel for c in candidates):
                    continue
                fm = parse_frontmatter(path.read_text(encoding="utf-8"))
                anchors = frontmatter_string_list(fm, "derived_from")
                if not anchors:
                    continue
                live = [
                    a
                    for a in anchors
                    if a not in deleting and path_exists_in_root(root, a)
                ]
                if not live:
                    candidates.append(
                        {
                            "path": rel,
                            "kind": "elixir",
                            "reason": "elixir_anchors_missing_or_gc",
                            "status": str(fm.get("provenance_status") or ""),
                        }
                    )
    return candidates


def _collect_noise_concepts(root: Path) -> list[dict[str, Any]]:
    concepts_dir = root / "wiki" / "concepts"
    if not concepts_dir.is_dir():
        return []
    memory = load_machine_memory(root)
    health = memory.get("health") if isinstance(memory, dict) else {}
    singletons = set()
    if isinstance(health, dict):
        raw = health.get("singleton_concept_slugs") or []
        if isinstance(raw, list):
            singletons = {str(item).strip() for item in raw if str(item).strip()}

    candidates: list[dict[str, Any]] = []
    for path in sorted(concepts_dir.glob("*.md")):
        slug = path.stem
        if slug in HUB_WHITELIST:
            continue
        reasons: list[str] = []
        if slug in NOISE_SLUGS:
            reasons.append("noise_vocab")
        if slug in singletons:
            reasons.append("singleton")
        if not reasons:
            continue
        candidates.append(
            {
                "path": relative_path(root, path),
                "kind": "concept",
                "reason": "+".join(reasons),
                "status": "",
            }
        )
    return candidates


def _text_blob(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").lower()
    except OSError:
        return ""


def _looks_like_misdrop(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in MISDROP_MARKERS)


def _judgment_refs_source(root: Path, source_rel: str) -> bool:
    needle = source_rel.replace("\\", "/")
    for path in iter_curated_pages(root):
        if not str(path).replace("\\", "/").endswith((".md",)):
            continue
        rel = relative_path(root, path)
        if not rel.startswith("wiki/judgments/"):
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        refs = [
            *frontmatter_string_list(fm, "source_files"),
            *frontmatter_string_list(fm, "derived_from"),
            *[c for c in (fm.get("citations") or []) if isinstance(c, str)],
        ]
        if needle in refs:
            return True
    return False


def _collect_misdrops(root: Path, *, force: bool) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for directory, kind in (
        (root / "raw" / "inbox", "raw"),
        (root / "wiki" / "sources", "source"),
    ):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt", ".html", ".json"} and kind == "raw":
                # Still check markdown notes primarily; include common note types.
                if path.suffix.lower() not in {".md", ".txt"}:
                    continue
            blob = _text_blob(path) + " " + path.name.lower()
            if not _looks_like_misdrop(blob):
                continue
            rel = relative_path(root, path)
            if kind == "source" and _judgment_refs_source(root, rel) and not force:
                candidates.append(
                    {
                        "path": rel,
                        "kind": kind,
                        "reason": "misdrop_blocked_by_judgment_ref",
                        "status": "blocked",
                    }
                )
                continue
            candidates.append(
                {
                    "path": rel,
                    "kind": kind,
                    "reason": "misdrop_fingerprint",
                    "status": "",
                }
            )
    return candidates


def plan_gc_orphans(
    root: Path,
    *,
    judgments: bool = False,
    derived: bool = False,
    elixirs: bool = False,
    force_degraded: bool = False,
    noise_concepts: bool = False,
    misdrops: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if not any([judgments, derived, elixirs, noise_concepts, misdrops]):
        raise ValueError(
            "Select at least one target: --judgments/--derived/--elixirs/--noise-concepts/--misdrops"
        )
    candidates: list[dict[str, Any]] = []
    candidates.extend(
        _collect_broken_candidates(
            root,
            include_judgments=judgments,
            include_derived=derived,
            include_elixirs=elixirs,
            force_degraded=force_degraded,
        )
    )
    if noise_concepts:
        candidates.extend(_collect_noise_concepts(root))
    if misdrops:
        candidates.extend(_collect_misdrops(root, force=force))

    # Deduplicate by path, keep first reason.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in candidates:
        path = str(item.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        unique.append(item)

    deletable = [c for c in unique if c.get("status") != "blocked"]
    blocked = [c for c in unique if c.get("status") == "blocked"]
    return {
        "dry_run": True,
        "candidate_count": len(deletable),
        "blocked_count": len(blocked),
        "candidates": deletable,
        "blocked": blocked,
        "flags": {
            "judgments": judgments,
            "derived": derived,
            "elixirs": elixirs,
            "force_degraded": force_degraded,
            "noise_concepts": noise_concepts,
            "misdrops": misdrops,
            "force": force,
        },
    }


@runtime_write_operation
def apply_gc_orphans(root: Path, plan: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    planned = plan or plan_gc_orphans(root, **kwargs)
    root_resolved = root.resolve()
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    for item in planned.get("candidates") or []:
        rel = str(item.get("path") or "").strip().replace("\\", "/")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            errors.append({"path": rel, "error": "path_outside_root_or_invalid"})
            continue
        target = (root / rel).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError:
            errors.append({"path": rel, "error": "path_outside_root"})
            continue
        try:
            if target.is_file():
                target.unlink()
                deleted.append(rel)
        except OSError as exc:
            errors.append({"path": rel, "error": str(exc)})

    receipt = write_execution_receipt(
        root,
        operation="gc-orphans",
        generated_by="aiwiki-gc-orphans",
        subject_kind="maintenance",
        subject_id="gc-orphans",
        target_file=deleted[0] if deleted else ".aiwiki/state/execution-receipts",
        status="success" if not errors else "partial",
        revert_supported=False,
        extra={
            "deleted_paths": deleted,
            "blocked": list(planned.get("blocked") or []),
            "errors": errors,
            "flags": dict(planned.get("flags") or {}),
            "candidate_count": int(planned.get("candidate_count") or 0),
        },
    )
    return {
        "dry_run": False,
        "deleted_count": len(deleted),
        "deleted_paths": deleted,
        "blocked": list(planned.get("blocked") or []),
        "errors": errors,
        "receipt_path": receipt.get("receipt_path"),
        "flags": dict(planned.get("flags") or {}),
    }


def run_gc_orphans(root: Path, *, apply: bool = False, **kwargs: Any) -> dict[str, Any]:
    planned = plan_gc_orphans(root, **kwargs)
    if not apply:
        return planned
    return apply_gc_orphans(root, plan=planned)


__all__ = [
    "HUB_WHITELIST",
    "MISDROP_MARKERS",
    "NOISE_SLUGS",
    "apply_gc_orphans",
    "plan_gc_orphans",
    "run_gc_orphans",
]
