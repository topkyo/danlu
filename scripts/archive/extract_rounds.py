#!/usr/bin/env python3
"""Extract historical round entries from PROGRESS.md into archive files.

This is a one-off dev tool for Round 68.  It intentionally keeps parsing
simple and stdlib-only: top-level round bullets are split from PROGRESS.md,
written to archive/rounds/round-*.md, and indexed in archive/rounds/index.json.
Existing manual round files in archive/rounds are merged into the index.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROUND_RE = re.compile(
    r"^- \*\*(Round \S+|P4-\S+(?:\s+系列)?) — (.+?) — (完成|进行中)(.*?)\*\*$"
)
COMMIT_RE = re.compile(r"\bcommit\s+[`'\"]?([0-9a-fA-F]{7,40})\b", re.IGNORECASE)
STATUS_MAP = {"完成": "done", "进行中": "in_progress", "done": "done", "in_progress": "in_progress"}


@dataclass(frozen=True)
class RoundEntry:
    display_id: str
    round_id: str
    title: str
    status_raw: str
    status: str
    commit: str | None
    slug: str
    body: str
    archived_path: str


def _slugify(value: str) -> str:
    value = value.lower().replace(".", "-")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9-]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def _round_id(display_id: str) -> str:
    if display_id.startswith("Round "):
        return _slugify(display_id.removeprefix("Round "))
    return _slugify(display_id)


def _file_stem(display_id: str, round_id: str) -> str:
    if display_id.startswith("Round "):
        return f"round-{round_id}"
    return round_id


def _strip_bullet_marker(line: str) -> str:
    text = line.strip()
    if text.startswith("- **") and text.endswith("**"):
        return text[4:-2]
    return text.removeprefix("- ")


def _normalize_block(block: list[str]) -> str:
    if not block:
        return ""
    out = [_strip_bullet_marker(block[0])]
    for line in block[1:]:
        if line.startswith("  "):
            out.append(line[2:])
        else:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _extract_commit(text: str) -> str | None:
    match = COMMIT_RE.search(text)
    return match.group(1).lower() if match else None


def parse_progress(progress_path: Path, archive_dir: Path) -> list[RoundEntry]:
    lines = progress_path.read_text(encoding="utf-8").splitlines()
    starts: list[tuple[int, re.Match[str]]] = []
    for idx, line in enumerate(lines):
        match = ROUND_RE.match(line)
        if match:
            starts.append((idx, match))

    entries: list[RoundEntry] = []
    for pos, (start, match) in enumerate(starts):
        end = len(lines)
        for next_idx in range(start + 1, len(lines)):
            if next_idx in {s for s, _m in starts[pos + 1 : pos + 2]}:
                end = next_idx
                break
            if lines[next_idx].startswith("## "):
                end = next_idx
                break
        if pos + 1 < len(starts):
            end = min(end, starts[pos + 1][0])

        display_id, title, status_raw, _suffix = match.groups()
        rid = _round_id(display_id)
        slug = _file_stem(display_id, rid)
        body = _normalize_block(lines[start:end])
        commit = _extract_commit("\n".join(lines[start:end]))
        rel_path = archive_dir / f"{slug}.md"
        entries.append(
            RoundEntry(
                display_id=display_id,
                round_id=rid,
                title=title,
                status_raw=status_raw,
                status=STATUS_MAP[status_raw],
                commit=commit,
                slug=slug,
                body=body,
                archived_path=str(rel_path.as_posix()),
            )
        )
    return entries


def _archive_text(entry: RoundEntry) -> str:
    commit = entry.commit or ""
    return (
        f"# {entry.display_id} — {entry.title}\n\n"
        f"status: {entry.status_raw}\n"
        f"commit: {commit}\n\n"
        f"{entry.body}"
    )


def write_round_files(entries: list[RoundEntry], root: Path, *, force: bool = False) -> int:
    written = 0
    for entry in entries:
        path = root / entry.archived_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            # Skip files already on disk to keep the dev tool idempotent across
            # reruns; manually-edited round files (R67/R67.5/R68) must not be
            # clobbered. Use --force to opt in to overwriting.
            continue
        path.write_text(_archive_text(entry), encoding="utf-8")
        written += 1
    return written


def _parse_manual_file(path: Path, root: Path) -> dict[str, object] | None:
    if path.suffix != ".md":
        return None
    text = path.read_text(encoding="utf-8")
    heading = next((line for line in text.splitlines() if line.startswith("# ")), "")
    if not heading:
        return None
    heading_text = heading[2:].strip()
    if " — " in heading_text:
        display_id, title = heading_text.split(" — ", 1)
    else:
        display_id, title = path.stem, heading_text
    if display_id.startswith("Round ") or display_id.startswith("P4-"):
        rid = _round_id(display_id)
    else:
        rid = path.stem.removeprefix("round-")

    status_match = re.search(r"^status:[ \t]*(\S+)", text, flags=re.MULTILINE)
    status_token = status_match.group(1) if status_match else ""
    status = STATUS_MAP.get(status_token, STATUS_MAP.get(status_token.lower(), "done"))
    commit_match = re.search(r"^commit:[ \t]*([^\n]*)$", text, flags=re.MULTILINE)
    if commit_match is not None:
        # Honour the explicit `commit:` line verbatim. An empty value means
        # "no commit recorded yet"; do NOT fallback to scanning the body,
        # because cross-reference paragraphs may mention unrelated commits
        # (e.g., p4-3.md referencing the P4-1 commit chain).
        commit_value = commit_match.group(1).strip()
        commit = commit_value if commit_value and commit_value.lower() != "null" else None
    else:
        # No frontmatter `commit:` field at all -> legacy file, scan body.
        commit = _extract_commit(text)

    tags: list[str] = []
    if rid.startswith("p4-inv"):
        tags = ["P4-INV"]
    elif rid.startswith("p4-"):
        tags = ["P4"]

    return {
        "round_id": rid,
        "title": title.strip(),
        "status": status,
        "commit": commit,
        "archived_path": str(path.relative_to(root).as_posix()),
        "tags": tags,
    }


def _sort_key(item: dict[str, object]) -> tuple:
    rid = str(item["round_id"])
    if rid.startswith("p4-"):
        # Numeric sort within P4 family so p4-3 < p4-11. P4-INV-N goes after
        # plain P4 milestones. Strip the `p4-`/`p4-inv-` prefix before
        # extracting the milestone number, otherwise `4` from `p4` collides.
        family = 1 if rid.startswith("p4-inv") else 0
        suffix = rid[len("p4-inv-"):] if family else rid[len("p4-"):]
        nums = [int(part) for part in re.findall(r"\d+", suffix)]
        primary = nums[0] if nums else 0
        return (1, (family, primary, rid))
    nums = [int(part) for part in re.findall(r"\d+", rid)]
    if not nums:
        return (2, rid)
    if len(nums) >= 2 and nums[0] == 67 and nums[1] == 5:
        value = 67.5
    elif len(nums) >= 2 and "-" in rid and rid.replace("-", "").isdigit():
        value = float(max(nums))
    elif len(nums) >= 2 and re.search(r"r\d+", rid):
        value = nums[0] + nums[1] / 10.0
    else:
        value = float(nums[0])
    return (0, -value)


def write_index(root: Path, archive_dir: Path) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for path in sorted((root / archive_dir).glob("*.md")):
        item = _parse_manual_file(path, root)
        if item:
            merged[str(item["round_id"])] = item
    rounds = sorted(merged.values(), key=_sort_key)
    payload = {
        "schema_version": 1,
        "rounds": rounds,
    }
    (root / archive_dir / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rounds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("progress", type=Path, help="Path to PROGRESS.md")
    parser.add_argument("--archive-dir", default="archive/rounds")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing round-*.md files; default is idempotent (skip-existing).",
    )
    args = parser.parse_args()

    progress_path = args.progress.resolve()
    root = progress_path.parent
    archive_dir = Path(args.archive_dir)
    entries = parse_progress(progress_path, archive_dir)
    written = write_round_files(entries, root, force=args.force)
    rounds = write_index(root, archive_dir)
    print(
        f"extracted={len(entries)} written={written} indexed={len(rounds)} "
        f"archive_dir={archive_dir} force={args.force}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
