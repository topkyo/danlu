from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_protocol import PROTOCOL_LIBRARY
from ..app_utils import next_available_stem, parse_frontmatter, sha256_bytes, slugify, utc_now

LEARNINGS_DIR = "wiki/protocol-learnings"


def _known_protocols() -> set[str]:
    return set(PROTOCOL_LIBRARY.keys())


def _validate_source_refs(root: Path, refs: list[str]) -> None:
    # Canonicalize allowed roots once so path-traversal via ".." cannot sneak past
    # the string prefix check and land outside wiki/derived|elixirs.
    allowed_roots = [(root / prefix).resolve() for prefix in ("wiki/derived", "wiki/elixirs")]
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("source ref must be non-empty string")
        if not (ref.startswith("wiki/derived/") or ref.startswith("wiki/elixirs/")):
            raise ValueError(f"source ref must be under wiki/derived/ or wiki/elixirs/: {ref}")
        candidate = (root / ref).resolve()
        if not any(candidate == base or base in candidate.parents for base in allowed_roots):
            raise ValueError(f"source ref escapes allowed roots: {ref}")
        if not candidate.is_file():
            raise ValueError(f"source ref missing: {ref}")


def _render_inserted_frontmatter(frontmatter: dict[str, Any]) -> str:
    import json

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


def _scaffold_learning_markdown(*, learning_id: str, protocol: str, title: str, source_refs: list[str], created_at: str, updated_at: str, lesson: str = "", when_to_apply: str = "", evidence: str = "") -> str:
    del lesson, when_to_apply, evidence
    frontmatter = {
        "learning_id": learning_id,
        "protocol": protocol,
        "title": title,
        "source_refs": source_refs,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    body = "\n".join([
        "# Protocol Learning",
        "",
        "## Lesson",
        "- Pending.",
        "",
        "## When to apply",
        "- Pending.",
        "",
        "## Evidence",
        "- Pending.",
        "",
    ])
    return _render_inserted_frontmatter(frontmatter) + body


def add_learning(root: Path, protocol: str, *, title: str, source_refs: list[str] | None = None) -> dict[str, Any]:
    if protocol not in _known_protocols():
        raise ValueError(f"unknown protocol: {protocol}; known: {sorted(_known_protocols())}")
    refs = list(source_refs or [])
    _validate_source_refs(root, refs)
    directory = root / LEARNINGS_DIR / protocol
    directory.mkdir(parents=True, exist_ok=True)
    seed = f"learn-{protocol}-{slugify(title)[:40]}-{sha256_bytes(title.encode())[:8]}"
    learning_id = next_available_stem(directory, seed)
    path = directory / f"{learning_id}.md"
    now = utc_now()
    path.write_text(
        _scaffold_learning_markdown(
            learning_id=learning_id,
            protocol=protocol,
            title=title,
            source_refs=refs,
            created_at=now,
            updated_at=now,
        ),
        encoding="utf-8",
    )
    return {"learning_id": learning_id, "path": f"{LEARNINGS_DIR}/{protocol}/{learning_id}.md", "protocol": protocol, "title": title, "source_refs": refs}


def list_learnings(root: Path, protocol: str | None = None) -> list[dict[str, Any]]:
    if protocol is not None and protocol not in _known_protocols():
        raise ValueError(f"unknown protocol: {protocol}; known: {sorted(_known_protocols())}")
    base = root / LEARNINGS_DIR
    if not base.is_dir():
        return []
    protocols = [protocol] if protocol else sorted([p.name for p in base.iterdir() if p.is_dir()])
    results: list[dict[str, Any]] = []
    for proto in protocols:
        pdir = base / proto
        if not pdir.is_dir():
            continue
        for md in sorted(pdir.glob("*.md")):
            fm = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            refs = fm.get("source_refs") or []
            results.append({
                "learning_id": str(fm.get("learning_id") or md.stem),
                "protocol": str(fm.get("protocol") or proto),
                "title": str(fm.get("title") or ""),
                "updated_at": str(fm.get("updated_at") or ""),
                "source_refs_count": len([r for r in refs if isinstance(r, str)]),
                "path": f"{LEARNINGS_DIR}/{proto}/{md.name}",
            })
    return results


def show_learning(root: Path, learning_id: str) -> dict[str, Any]:
    base = root / LEARNINGS_DIR
    if not base.is_dir():
        raise FileNotFoundError(f"learning not found: {learning_id}")
    for pdir in base.iterdir():
        if not pdir.is_dir():
            continue
        candidate = pdir / f"{learning_id}.md"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter(text)
            parts = text.split("---", 2)
            body = parts[-1].lstrip("\n") if len(parts) >= 3 else text
            return {"learning_id": learning_id, "protocol": pdir.name, "frontmatter": fm, "body": body, "path": f"{LEARNINGS_DIR}/{pdir.name}/{learning_id}.md"}
    raise FileNotFoundError(f"learning not found: {learning_id}")


def load_learnings_for_protocol(root: Path, protocol: str) -> list[dict[str, Any]]:
    base = root / LEARNINGS_DIR / protocol
    if not base.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for md in sorted(base.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        body = text.split("---", 2)[-1].lstrip("\n")
        lesson = ""
        if "## Lesson" in body:
            lesson_part = body.split("## Lesson", 1)[1]
            if "\n## " in lesson_part:
                lesson = lesson_part.split("\n## ", 1)[0].strip()
            else:
                lesson = lesson_part.strip()
            lesson = lesson.lstrip("\n").strip()
            if lesson.startswith("-"):
                lesson = lesson[1:].strip()
        results.append({"learning_id": str(fm.get("learning_id") or md.stem), "title": str(fm.get("title") or ""), "lesson": lesson})
    return results
