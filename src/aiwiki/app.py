"""Core application logic for the aiwiki MVP."""

from __future__ import annotations

from collections import deque
import hashlib
import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LAYOUT_DIRS = (
    "raw/inbox",
    "raw/normalized",
    "raw/assets",
    "schema",
    "wiki/sources",
    "wiki/concepts",
    "wiki/decisions",
    "wiki/judgments",
    "wiki/indexes",
    "wiki/derived",
    "output/reports",
    "output/slides",
    "output/figures",
    "output/graph",
    "output/lint",
    "prompts",
    ".aiwiki/state",
    ".aiwiki/cache",
    ".aiwiki/logs",
)

DEFAULT_SCHEMA_FILES = {
    "schema/index.md": "\n".join(
        [
            "# 运行时规则",
            "",
            "这个目录存放 `aiwiki` 的运行时规则。",
            "",
            "它属于产品运行时约束，不属于开发治理说明。",
            "",
            "## 核心规则文件",
            "",
            "- [采集规则](./ingest.md)",
            "- [引用规则](./citations.md)",
            "- [冲突规则](./conflicts.md)",
            "- [审阅规则](./review.md)",
            "- [回流规则](./writeback.md)",
            "- [分类规则](./taxonomy.md)",
            "",
            "## 边界",
            "",
            "- `AGENTS.md` 和 `CLAUDE.md` 是仓库/开发侧文件。",
            "- 运行时行为应由这个目录和 `prompts/` 共同驱动。",
        ]
    )
    + "\n",
    "schema/ingest.md": "\n".join(
        [
            "# 采集规则",
            "",
            "- 能保留原始附件时，优先保留原始附件。",
            "- 在采集笔记里记录原始路径或 URL。",
            "- ingest 生成的笔记要留在 `raw/`，并回指到它们的证据来源。",
            "- URL stub 或不完整采集内容，不能在未声明的情况下当成强证据。",
        ]
    )
    + "\n",
    "schema/citations.md": "\n".join(
        [
            "# 引用规则",
            "",
            "- 在编译层和输出层里优先引用 `wiki/sources/*.md`。",
            "- 能保留回到 `raw/` 的文件路径溯源时，尽量保留。",
            "- 没有证据支撑的综合结论不能写成事实。",
            "- 如果证据薄弱、不完整或互相冲突，要明确写出来。",
        ]
    )
    + "\n",
    "schema/conflicts.md": "\n".join(
        [
            "# 冲突规则",
            "",
            "- 让冲突保持显式，不要把它们抹平。",
            "- 宁可保留不确定性，也不要编造一致解释。",
            "- 当来源互相矛盾时，要同时指出两边的 source page。",
            "- 在 lint 和后续修复循环里追踪重复出现的漂移和歧义。",
        ]
    )
    + "\n",
    "schema/review.md": "\n".join(
        [
            "# 审阅规则",
            "",
            "- decision 页面默认从 `proposed` 开始，并沿显式审阅状态推进。",
            "- judgment 页面默认从 `tentative` 开始，并始终保留明确的 confidence。",
            "- 用 review workflow 把 decision 和 judgment 页面从队列里推进出去。",
            "- review note 应记录状态为什么变化、接下来要看什么。",
            "- 进入 approved、rejected、superseded 或 revisit 等状态时，必须带 `reviewed_at`。",
            "- pending 的 decision / judgment 页面应带 `revisit_after` 和 `escalate_after`，让 nightly 能追踪 aging 信号。",
            "- `aging-report.md`、`review-queue.md` 和 `repair-backlog.md` 应把 overdue / escalation 候选项显式展示出来。",
        ]
    )
    + "\n",
    "schema/writeback.md": "\n".join(
        [
            "# 回流规则",
            "",
            "- 高价值输出可以回流到 `wiki/derived/`。",
            "- 稳定选择可以晋升到 `wiki/decisions/`。",
            "- 可复用的判断可以晋升到 `wiki/judgments/`。",
            "- decision 和 judgment 页面应该经过显式 review 状态，而不是一直停在隐式草稿。",
            "- 回流笔记不能覆盖 source page 或 raw evidence。",
            "- derived、decision、judgment 页面都应引用 source page 或 raw 证据。",
            "- 回流是知识复利，不是对事实的静默篡改。",
        ]
    )
    + "\n",
    "schema/taxonomy.md": "\n".join(
        [
            "# 分类规则",
            "",
            "- 让 concept 名称保持稳定且便于人读。",
            "- 能放进 concept page 的综合结论，优先不要散落在多个 source page 里重复写。",
            "- source、concept、decision、judgment、derived、output 各层要按职责分开。",
            "- 当重复模式稳定下来时，把它提升进 schema 或 decision page。",
        ]
    )
    + "\n",
}

DEFAULT_DASHBOARD_FILES = {
    "wiki/indexes/review-center.md": "\n".join(
        [
            "# 审阅中心",
            "",
            "这里是炼丹炉的人用审阅入口，负责把 pending review、aging、repair 和 concept rewrite 收拢到一个地方。",
            "",
            "## 先看哪里",
            "",
            "- [审阅队列](./review-queue.md)：处理 `decision / judgment` 的状态推进",
            "- [Aging 报告](./aging-report.md)：看 overdue 和 escalation",
            "- [概念质量](./concept-quality.md)：看弱概念、冲突信号、证据缺口、重写优先级",
            "- [机器记忆动作队列](./machine-memory-actions.md)：看 machine-memory action lifecycle",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和 execution proposal",
            "- [修复待办](./repair-backlog.md)：看 nightly 汇总出来的优先级队列",
            "",
            "## 推荐顺序",
            "",
            "1. 先处理升级项和已到期复审。",
            "2. 再处理 accepted 的 machine-memory 修复动作。",
            "3. 然后处理高优先级弱概念页和显式冲突信号。",
            "4. 最后处理 deferred / watch 类项目。",
            "",
            "## 边界",
            "",
            "- 这里是入口页，不直接替代 `review-queue.md` 或 `repair-backlog.md`。",
            "- 高风险修复仍然应通过 review 后执行，不要直接改写事实层。",
        ]
    )
    + "\n",
    "wiki/indexes/graph-view.md": "\n".join(
        [
            "# 图谱视图",
            "",
            "这里是炼丹炉的人用图谱入口，负责把 machine memory 的几类图相关页面收拢起来。",
            "",
            "## 先看哪里",
            "",
            "- [机器记忆](./machine-memory.md)：看 term index、digest、动作/提案数量",
            "- [机器记忆拓扑](./machine-memory-topology.md)：看 hub、Mermaid 拓扑切片",
            "- [图谱健康](./graph-health.md)：看 component、isolated/singleton/bridge 信号",
            "- [漂移报告](./drift-report.md)：看最近一次 machine-memory 结构变化",
            "- [概念质量](./concept-quality.md)：看图谱问题如何传导到 concept rewrite",
            "- [本地图谱 HTML](../../output/graph/machine-memory.html)：直接看可视化图谱产物",
            "",
            "## 怎么读",
            "",
            "1. 先看 component、hub 和 drift 是否稳定。",
            "2. 再看 link suggestion、action queue 和 repair proposal。",
            "3. 最后回到具体 `wiki/concepts/` 或 `wiki/sources/` 页面处理。",
            "",
            "## 边界",
            "",
            "- 这里展示的是 `aiwiki` 的 machine-memory 视角，不等于 Obsidian 自带的 Graph View。",
            "- Obsidian Graph 更适合看笔记链接；这里更适合看知识编译后的机读层状态。",
        ]
    )
    + "\n",
}

TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".markdown",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}

STOP_WORDS = {
    "about",
    "article",
    "articles",
    "after",
    "against",
    "brief",
    "browser",
    "compare",
    "compiled",
    "file",
    "files",
    "figure",
    "from",
    "image",
    "images",
    "into",
    "must",
    "note",
    "notes",
    "page",
    "pages",
    "question",
    "report",
    "rendered",
    "smoke",
    "source",
    "sources",
    "slides",
    "that",
    "their",
    "there",
    "these",
    "this",
    "with",
    "wiki",
}

CONFLICT_SIGNAL_PAIRS = (
    ("increase", "decrease", "increase-vs-decrease"),
    ("rise", "fall", "rise-vs-fall"),
    ("higher", "lower", "higher-vs-lower"),
    ("more", "less", "more-vs-less"),
    ("improve", "hurt", "improve-vs-hurt"),
    ("benefit", "risk", "benefit-vs-risk"),
    ("faster", "slower", "faster-vs-slower"),
    ("增加", "减少", "增加-vs-减少"),
    ("上升", "下降", "上升-vs-下降"),
    ("更高", "更低", "更高-vs-更低"),
    ("更多", "更少", "更多-vs-更少"),
    ("改善", "恶化", "改善-vs-恶化"),
    ("收益", "风险", "收益-vs-风险"),
    ("更快", "更慢", "更快-vs-更慢"),
)

EVIDENCE_GAP_MARKERS = (
    "unclear",
    "unknown",
    "missing",
    "partial",
    "truncated",
    "weak",
    "incomplete",
    "not enough",
    "insufficient",
    "todo",
    "tbd",
    "不确定",
    "未知",
    "缺失",
    "待补",
    "截断",
    "薄弱",
    "不完整",
    "证据不足",
)

DECISION_STATUSES = ("proposed", "approved", "needs-revisit", "superseded")
JUDGMENT_STATUSES = ("tentative", "tracking", "confirmed", "rejected")
ACTION_STATUSES = ("proposed", "accepted", "deferred", "resolved", "rejected")
PENDING_DECISION_REVIEW_STATUSES = {"proposed", "needs-revisit"}
PENDING_JUDGMENT_REVIEW_STATUSES = {"tentative", "tracking"}
PENDING_ACTION_STATUSES = {"proposed", "accepted", "deferred"}
AGING_WINDOWS_DAYS: dict[tuple[str, str], tuple[int, int]] = {
    ("decision", "proposed"): (7, 21),
    ("decision", "needs-revisit"): (3, 10),
    ("judgment", "tentative"): (7, 21),
    ("judgment", "tracking"): (14, 30),
    ("action", "proposed"): (3, 10),
    ("action", "accepted"): (7, 21),
    ("action", "deferred"): (14, 30),
}
AUTO_PROMOTION_MIN_OCCURRENCES = 2
AUTO_PROMOTION_FORMATS = {"report", "figure"}
DECISION_QUERY_MARKERS = (
    "should we",
    "which option",
    "which approach",
    "which should",
    "decision",
    "decide",
    "choose",
    "choice",
    "adopt",
    "select",
    "prioritize",
    "migrate",
    "replace",
    "switch",
    "deprecate",
    "approve",
    "reject",
    "是否应该",
    "该不该",
    "怎么选",
    "如何选",
    "选择",
    "决策",
    "采用",
    "迁移",
    "替换",
    "切换",
    "取舍",
    "批准",
    "否决",
)
JUDGMENT_QUERY_MARKERS = (
    "will ",
    "likely",
    "risk",
    "forecast",
    "outlook",
    "signal",
    "signals",
    "probability",
    "expect",
    "assessment",
    "assess",
    "judge",
    "trend",
    "confidence",
    "是否会",
    "会不会",
    "风险",
    "预判",
    "判断",
    "信号",
    "概率",
    "趋势",
    "置信",
    "走向",
    "可能性",
)


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema(root)
    ensure_runtime_dashboards(root)


def ensure_runtime_schema(root: Path) -> None:
    for relative, content in DEFAULT_SCHEMA_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def ensure_runtime_dashboards(root: Path) -> None:
    for relative, content in DEFAULT_DASHBOARD_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def schedule_review_windows(kind: str, status: str, base_timestamp: str) -> tuple[str, str]:
    if (kind, status) not in AGING_WINDOWS_DAYS:
        return "", ""
    base = parse_iso_datetime(base_timestamp) or datetime.now(timezone.utc)
    revisit_days, escalate_days = AGING_WINDOWS_DAYS[(kind, status)]
    revisit_after = (base + timedelta(days=revisit_days)).replace(microsecond=0).isoformat()
    escalate_after = (base + timedelta(days=escalate_days)).replace(microsecond=0).isoformat()
    return revisit_after, escalate_after


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "item"


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".rst"}:
        return "text"
    if suffix in {".json", ".yaml", ".yml", ".csv", ".tsv", ".toml"}:
        return "data"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if not suffix:
        return "file"
    return suffix.lstrip(".")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


def default_manifest() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    if not path.exists():
        return default_manifest()
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    ensure_layout(root)
    path = manifest_path(root)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def next_identifier(existing_ids: set[str], seed: str) -> str:
    candidate = seed
    index = 2
    while candidate in existing_ids:
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def next_available_stem(directory: Path, seed: str, suffix: str = ".md") -> str:
    candidate = seed
    index = 2
    while (directory / f"{candidate}{suffix}").exists():
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def read_text_preview(path: Path, limit_lines: int = 12, limit_chars: int = 1600) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return f"Preview unavailable for {path.suffix or 'unknown'} files."
    text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    preview = "\n".join(text.splitlines()[:limit_lines]).strip()
    if len(preview) > limit_chars:
        preview = preview[:limit_chars].rstrip() + "..."
    return preview or "(empty text file)"


def raw_note_metadata(path: Path) -> dict[str, str]:
    if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return {}
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    result: dict[str, str] = {}
    for key in ("title", "source_type", "original_path"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def render_scalar(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def render_frontmatter(mapping: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in mapping.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {render_scalar(item)}")
        else:
            lines.append(f"{key}: {render_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def parse_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - ") and current_key is not None:
            data.setdefault(current_key, []).append(parse_scalar(line[4:]))
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw:
            data[key] = parse_scalar(raw)
            current_key = None
        else:
            data[key] = []
            current_key = key
    return data


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip()
    return text


def upsert_markdown_section(markdown: str, heading: str, content: str) -> str:
    section = content.strip()
    block = f"## {heading}\n{section}\n"
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    if re.search(pattern, markdown):
        updated = re.sub(pattern, block + "\n", markdown).strip()
        return updated + "\n"
    base = markdown.rstrip()
    if base:
        return base + "\n\n" + block
    return block


def replace_first_markdown_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}"
            return "\n".join(lines).strip() + "\n"
    body = markdown.strip()
    if body:
        return f"# {title}\n\n{body}\n"
    return f"# {title}\n"


def first_markdown_heading(markdown: str) -> str:
    for line in strip_frontmatter(markdown).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
    path.write_text(content, encoding="utf-8")
    return True


def sync_manifest_with_raw(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = load_manifest(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    entry_by_path = {entry["stored_path"]: entry for entry in entries}
    known_paths = set(entry_by_path)
    existing_ids = {entry["id"] for entry in entries}
    changed = False

    for path in sorted((root / "raw" / "inbox").iterdir()):
        if not path.is_file():
            continue
        stored_path = relative_path(root, path)
        metadata = raw_note_metadata(path)
        if stored_path in known_paths:
            entry = entry_by_path[stored_path]
            current_sha = sha256_file(path)
            current_kind = detect_kind(path)
            current_title = metadata.get("title") or entry["title"]
            current_source_type = metadata.get("source_type") or entry["source_type"]
            current_original_path = metadata.get("original_path") or entry["original_path"]
            if (
                entry.get("sha256") != current_sha
                or entry.get("kind") != current_kind
                or entry.get("title") != current_title
                or entry.get("source_type") != current_source_type
                or entry.get("original_path") != current_original_path
            ):
                entry["sha256"] = current_sha
                entry["kind"] = current_kind
                entry["title"] = current_title
                entry["source_type"] = current_source_type
                entry["original_path"] = current_original_path
                entry["updated_at"] = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat()
                changed = True
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        seed_label = metadata.get("title") or path.stem
        seed = f"discovered-{stamp}-{slugify(seed_label)}"
        entry_id = next_identifier(existing_ids, seed)
        existing_ids.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "title": metadata.get("title") or path.stem,
                "source_type": metadata.get("source_type") or "raw-drop",
                "original_path": metadata.get("original_path") or stored_path,
                "stored_path": stored_path,
                "kind": detect_kind(path),
                "sha256": sha256_file(path),
                "imported_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat(),
                "updated_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat(),
            }
        )
        known_paths.add(stored_path)
        changed = True

    if changed:
        save_manifest(root, manifest)
    return manifest


def ingest_source(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    existing_ids = {entry["id"] for entry in manifest["entries"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    label = title or Path(source).stem or source
    display_title = title or label
    entry_id = next_identifier(existing_ids, f"{stamp}-{slugify(label)}")

    if source.startswith("http://") or source.startswith("https://"):
        destination = root / "raw" / "inbox" / f"{entry_id}.md"
        stub_title = title or source
        stub = "\n".join(
            [
                f"# {stub_title}",
                "",
                "## 来源 URL",
                f"- {source}",
                "",
                "## 采集状态",
                "- 这个 URL 目前只是一个占位 stub。",
                "- 在把它当作事实来源前，请先用剪藏 markdown 或本地附件替换成更完整材料。",
                "",
                "## 备注",
                "- 在补充更完整材料之前，编译器会把这个文件视为占位来源。",
            ]
        )
        destination.write_text(stub + "\n", encoding="utf-8")
        original_path = source
        source_type = "url"
    else:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source not found: {source}")
        destination = root / "raw" / "inbox" / f"{entry_id}{source_path.suffix.lower()}"
        shutil.copy2(source_path, destination)
        original_path = str(source_path)
        source_type = "file"

    entry = {
        "id": entry_id,
        "title": display_title,
        "source_type": source_type,
        "original_path": original_path,
        "stored_path": relative_path(root, destination),
        "kind": detect_kind(destination),
        "sha256": sha256_file(destination),
        "imported_at": utc_now(),
    }
    manifest["entries"].append(entry)
    save_manifest(root, manifest)
    append_wiki_log(
        root,
        "ingest",
        display_title,
        [
            f"source_type: `{source_type}`",
            f"stored_path: `{entry['stored_path']}`",
            f"original_path: `{original_path}`",
        ],
    )
    return entry


def render_source_page(entry: dict[str, Any], preview: str, compiled_at: str) -> str:
    return render_source_page_with_state(entry, preview, compiled_at, concepts=[], existing_page="")


def render_source_page_with_state(
    entry: dict[str, Any],
    preview: str,
    compiled_at: str,
    *,
    concepts: list[str],
    existing_page: str,
) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = compiled_source_sha(existing_page) not in ("", entry["sha256"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "low") if not source_changed else "low"
    if not isinstance(confidence, str) or not confidence:
        confidence = "low"
    summary = (
        preserved_section(existing_page, "Summary", "- Pending LLM summary.")
        if not source_changed
        else "- Pending LLM summary."
    )
    concept_links = ["- No concept links yet."] if not concepts else [
        f"- [{concept_label_to_title(label)}](../concepts/{concept_label_to_slug(label)}.md)"
        for label in concepts
    ]
    frontmatter = render_frontmatter(
        {
            "id": entry["id"],
            "kind": "source",
            "status": "compiled",
            "title": entry["title"],
            "source_files": [entry["stored_path"]],
            "source_sha256": entry["sha256"],
            "citations": citations,
            "concepts": concepts,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
            "confidence": confidence,
        }
    )
    body = "\n".join(
        [
            frontmatter,
            "",
            f"# {entry['title']}",
            "",
            "## Source Record",
            f"- Source type: `{entry['source_type']}`",
            f"- Original path: `{entry['original_path']}`",
            f"- Stored path: `{entry['stored_path']}`",
            f"- Imported at: `{entry['imported_at']}`",
            f"- SHA256: `{entry['sha256']}`",
            "",
            "## Summary",
            summary,
            "",
            "## Concept Links",
            *concept_links,
            "",
            "## Enrichment TODO",
            "- Refresh concept links when new sources shift the synthesis.",
            "- Add backlinks from derived outputs that cite this page.",
            "- Preserve provenance when replacing placeholder text.",
            "",
            "## Preview",
            "```text",
            preview,
            "```",
            "",
            "## Citation Anchor",
            f"- Cite this page as `wiki/sources/{entry['id']}.md`.",
        ]
    )
    return body + "\n"


def concept_candidates(entries: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in entries:
        for token in re.findall(r"[a-zA-Z0-9]{4,}", entry["title"].lower()):
            if token in STOP_WORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:10]]


def preserved_section(markdown: str, heading: str, fallback: str) -> str:
    if not markdown:
        return fallback
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, markdown)
    if not match:
        return fallback
    section = match.group(1).strip()
    return section or fallback


def compiled_source_sha(markdown: str) -> str:
    if not markdown:
        return ""
    frontmatter = parse_frontmatter(markdown)
    sha = frontmatter.get("source_sha256")
    if isinstance(sha, str) and sha:
        return sha
    match = re.search(r"(?m)^- SHA256: `([^`]+)`", markdown)
    if match:
        return match.group(1)
    return ""


def concept_label_to_slug(label: str) -> str:
    return slugify(label)[:64]


def concept_label_to_title(label: str) -> str:
    words = [word for word in label.split() if word]
    if not words:
        return "Concept"
    return " ".join(word.capitalize() for word in words)


def entry_concept_terms(entry: dict[str, Any], context: str, max_terms: int = 5) -> list[str]:
    scores: dict[str, int] = {}
    title_tokens = tokenize(entry["title"])
    phrase_tokens = title_tokens[:3]
    if len(phrase_tokens) >= 2:
        phrase = " ".join(phrase_tokens)
        scores[phrase] = scores.get(phrase, 0) + 8
    for token in title_tokens[:4]:
        scores[token] = scores.get(token, 0) + 5
    for token in tokenize(context):
        scores[token] = scores.get(token, 0) + 1
    ranked = sorted(scores.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    return [label for label, _score in ranked[:max_terms]]


def source_summary_or_preview(root: Path, entry: dict[str, Any], preview: str) -> str:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if page.exists():
        content = page.read_text(encoding="utf-8", errors="replace")
        summary = preserved_section(content, "Summary", "")
        if compiled_source_sha(content) in ("", entry["sha256"]) and summary and "Pending LLM summary." not in summary:
            return summary
    return preview


def build_concept_records(
    root: Path,
    entries: list[dict[str, Any]],
    previews: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    concept_map: dict[str, dict[str, Any]] = {}
    entry_terms: dict[str, list[str]] = {}
    for entry in entries:
        context = source_summary_or_preview(root, entry, previews[entry["id"]])
        terms = entry_concept_terms(entry, context)
        entry_terms[entry["id"]] = terms
        for label in terms:
            slug = concept_label_to_slug(label)
            record = concept_map.setdefault(
                slug,
                {
                    "slug": slug,
                    "label": label,
                    "title": concept_label_to_title(label),
                    "entries": [],
                    "score": 0,
                },
            )
            record["entries"].append(entry)
            record["score"] += 1

    ranked_records = sorted(concept_map.values(), key=lambda item: (-item["score"], item["title"].lower()))[:30]
    allowed = {record["slug"] for record in ranked_records}
    filtered_entry_terms: dict[str, list[str]] = {}
    for entry_id, labels in entry_terms.items():
        filtered = [label for label in labels if concept_label_to_slug(label) in allowed]
        filtered_entry_terms[entry_id] = filtered[:5]

    by_slug = {record["slug"]: record for record in ranked_records}
    for record in ranked_records:
        related_counts: dict[str, int] = {}
        for entry in record["entries"]:
            for label in filtered_entry_terms[entry["id"]]:
                other_slug = concept_label_to_slug(label)
                if other_slug == record["slug"] or other_slug not in by_slug:
                    continue
                related_counts[other_slug] = related_counts.get(other_slug, 0) + 1
        related = sorted(related_counts.items(), key=lambda item: (-item[1], by_slug[item[0]]["title"].lower()))
        record["related_slugs"] = [slug for slug, _count in related[:6]]
        record["entry_ids"] = [entry["id"] for entry in record["entries"]]
        record["source_signature"] = concept_source_signature(record)
    return ranked_records, filtered_entry_terms


def concept_source_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": record["slug"],
        "entry_ids": sorted(record["entry_ids"]),
        "entry_sources": sorted(f"{entry['id']}:{entry['sha256']}" for entry in record["entries"]),
        "related_slugs": sorted(record.get("related_slugs", [])),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
    summary_fallback = "\n".join(
        [
            f"- This concept currently appears in `{len(record['entries'])}` source page(s).",
            "- Use the linked source pages below to deepen or revise this synthesis.",
        ]
    )
    summary = preserved_section(existing_page, "Summary", summary_fallback) if not source_changed else summary_fallback
    related_source_lines = [
        f"- [{entry['title']}](../sources/{entry['id']}.md)"
        for entry in sorted(record["entries"], key=lambda item: item["title"].lower())
    ] or ["- No related source pages yet."]
    related_concepts = record.get("related_slugs", [])
    related_concept_lines = [
        f"- [{record_for_slug['title']}](./{record_for_slug['slug']}.md)"
        for record_for_slug in sorted(
            [record["record_lookup"][slug] for slug in related_concepts if slug in record["record_lookup"]],
            key=lambda item: item["title"].lower(),
        )
    ] or ["- No related concepts yet."]
    frontmatter = render_frontmatter(
        {
            "id": f"concept-{record['slug']}",
            "kind": "concept",
            "status": "compiled",
            "title": record["title"],
            "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
            "source_signature": record["source_signature"],
            "citations": citations,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
            "confidence": confidence,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {record['title']}",
        "",
        "## Summary",
        summary,
        "",
        "## Related Sources",
        *related_source_lines,
        "",
        "## Related Concepts",
        *related_concept_lines,
        "",
        "## Maintenance Notes",
        "- Promote stable findings here instead of repeating the same synthesis across source pages.",
        "- Keep contradictions and missing evidence explicit.",
    ]
    return "\n".join(lines) + "\n"


def render_sources_index(entries: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 来源索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源总数：`{len(entries)}`",
        "",
        "## 来源列表",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in entries:
            lines.append(
                f"- [{entry['title']}](../sources/{entry['id']}.md) "
                f"({entry['kind']}, {entry['source_type']})"
            )
    return "\n".join(lines) + "\n"


def render_concepts_index(concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 概念索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 概念页总数：`{len(concepts)}`",
        "",
        "## 概念列表",
    ]
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md) "
                f"({len(concept['entries'])} source(s))"
            )
    return "\n".join(lines) + "\n"


def default_curated_status(kind: str) -> str:
    if kind == "decision":
        return "proposed"
    if kind == "judgment":
        return "tentative"
    return "filed"


def valid_curated_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return DECISION_STATUSES
    if kind == "judgment":
        return JUDGMENT_STATUSES
    return ()


def page_needs_review(kind: str, status: str) -> bool:
    if kind == "decision":
        return status in PENDING_DECISION_REVIEW_STATUSES
    if kind == "judgment":
        return status in PENDING_JUDGMENT_REVIEW_STATUSES
    return False


def evaluate_page_aging(page: dict[str, str], now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    revisit_after = parse_iso_datetime(page.get("revisit_after", ""))
    escalate_after = parse_iso_datetime(page.get("escalate_after", ""))
    overdue = bool(revisit_after and revisit_after <= now)
    escalated = bool(escalate_after and escalate_after <= now)
    aging_state = ""
    if escalated:
        aging_state = "escalated"
    elif overdue:
        aging_state = "overdue"
    elif revisit_after:
        aging_state = "scheduled"
    return {
        "revisit_after": revisit_after.replace(microsecond=0).isoformat() if revisit_after else "",
        "escalate_after": escalate_after.replace(microsecond=0).isoformat() if escalate_after else "",
        "aging_state": aging_state,
        "overdue_review": "true" if overdue else "false",
        "escalation_candidate": "true" if escalated else "false",
    }


def collect_aging_signals(decisions: list[dict[str, str]], judgments: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    pages = decisions + judgments
    overdue = [page for page in pages if page.get("overdue_review") == "true"]
    escalated = [page for page in pages if page.get("escalation_candidate") == "true"]
    scheduled = [page for page in pages if page.get("aging_state") == "scheduled"]
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
    }


def display_curated_status(status: str) -> str:
    mapping = {
        "filed": "已归档",
        "proposed": "待决策",
        "approved": "已批准",
        "needs-revisit": "待复审",
        "superseded": "已替代",
        "tentative": "暂定判断",
        "tracking": "持续观察",
        "confirmed": "已确认",
        "rejected": "已否决",
    }
    return mapping.get(status, status or "unknown")


def action_needs_review(status: str) -> bool:
    return status in PENDING_ACTION_STATUSES


def display_action_status(status: str) -> str:
    mapping = {
        "proposed": "待处理",
        "accepted": "已接受",
        "deferred": "暂缓",
        "resolved": "已解决",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def sort_curated_pages(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(page: dict[str, str]) -> tuple[str, str]:
        return (page.get("reviewed_at", "") or page.get("updated_at", ""), page["title"].lower())

    return sorted(pages, key=sort_key, reverse=True)


def collect_curated_pages(root: Path, folder: str, expected_kind: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        status = str(frontmatter.get("status") or default_curated_status(expected_kind))
        reviewed_at = str(frontmatter.get("reviewed_at") or "")
        updated_at = str(frontmatter.get("last_compiled_at") or "")
        revisit_after = str(frontmatter.get("revisit_after") or "")
        escalate_after = str(frontmatter.get("escalate_after") or "")
        if not revisit_after and not escalate_after:
            base_timestamp = reviewed_at or updated_at or utc_now()
            revisit_after, escalate_after = schedule_review_windows(expected_kind, status, base_timestamp)
        pages.append(
            {
                "title": str(frontmatter.get("title") or path.stem),
                "path": relative_path(root, path),
                "kind": str(frontmatter.get("kind") or ""),
                "status": status,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "updated_at": updated_at,
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
                "matches_expected_kind": str(frontmatter.get("kind") or "") == expected_kind,
                "pending_review": "true" if page_needs_review(expected_kind, status) else "false",
            }
        )
    enriched: list[dict[str, str]] = []
    for page in pages:
        enriched_page = dict(page)
        enriched_page.update(evaluate_page_aging(enriched_page, now=now))
        enriched.append(enriched_page)
    return sort_curated_pages(enriched)


def review_queue(decisions: list[dict[str, str]], judgments: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    pending_decisions = [page for page in decisions if page.get("pending_review") == "true"]
    pending_judgments = [page for page in judgments if page.get("pending_review") == "true"]
    reviewed = [
        page
        for page in decisions + judgments
        if page.get("reviewed_at") and page.get("pending_review") != "true"
    ]
    reviewed = sorted(reviewed, key=lambda page: (page.get("reviewed_at", ""), page["title"].lower()), reverse=True)
    return {
        "pending_decisions": pending_decisions,
        "pending_judgments": pending_judgments,
        "recently_reviewed": reviewed,
    }


def collect_machine_memory_actions(root: Path) -> list[dict[str, Any]]:
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    now = datetime.now(timezone.utc)
    for action in actions:
        action.setdefault("status", "proposed")
        action.setdefault("active", True)
        action.setdefault("priority", "medium")
        action.setdefault("review_note", "")
        action.setdefault("first_seen_at", "")
        action.setdefault("last_seen_at", "")
        action.setdefault("inactive_since", "")
        action.setdefault("occurrences", 0)
        action.setdefault("pending_review", "true" if action_needs_review(str(action.get("status"))) else "false")
        action.update(evaluate_page_aging(action, now=now))
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}
    return sorted(
        actions,
        key=lambda item: (
            0 if item.get("active") else 1,
            status_order.get(str(item.get("status")), 9),
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("occurrences", 0)),
            str(item.get("title", "")).lower(),
        ),
    )


def collect_machine_memory_action_aging(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    active_actions = [action for action in actions if action.get("active")]
    overdue = [action for action in active_actions if action.get("overdue_review") == "true"]
    escalated = [action for action in active_actions if action.get("escalation_candidate") == "true"]
    scheduled = [action for action in active_actions if action.get("aging_state") == "scheduled"]
    inactive = [action for action in actions if not action.get("active")]
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
        "inactive": inactive,
    }


def action_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 9)


def action_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}.get(status, 9)


def describe_machine_memory_action(action: dict[str, Any]) -> dict[str, str]:
    action_id = str(action.get("id") or "")
    kind = str(action.get("kind") or "")
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    review_prefix = f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id}"
    kind_steps = {
        "add-source-concept-link": "检查来源页与概念页是否应补引用或反链。",
        "connect-isolated-source": "把孤立来源接入至少一个稳定概念。",
        "expand-singleton-concept": "扩展单节点概念的相关来源或相关概念。",
        "split-overloaded-concept": "把过载概念拆成更窄的概念页或子主题。",
        "monitor-bridge-concept": "确认桥接概念仍然必要，并记录观察结论。",
    }
    next_step = kind_steps.get(kind, "检查这个 machine-memory 动作对应的页面。")
    command_hint = ""
    execution_policy = "triage"
    if not active:
        execution_policy = "inactive-history"
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = f'{review_prefix} --status resolved --note "Signal disappeared after compile."'
    elif status == "proposed":
        execution_policy = "triage"
        command_hint = f'{review_prefix} --status accepted --note "Accepted for manual repair."'
    elif status == "accepted":
        execution_policy = "manual-repair"
        next_step = f"{next_step} 完成后将动作标为 resolved。"
        command_hint = f'{review_prefix} --status resolved --note "Repair completed."'
    elif status == "deferred":
        execution_policy = "parked"
        next_step = "已确认但暂缓处理；准备恢复时改回 accepted。"
        command_hint = f'{review_prefix} --status accepted --note "Resume deferred repair."'
    elif status == "resolved":
        execution_policy = "closed"
        next_step = "保持关闭，只有信号再次出现时才重开。"
    elif status == "rejected":
        execution_policy = "closed"
        next_step = "保持关闭，除非修复策略改变。"
    return {
        "execution_policy": execution_policy,
        "next_step": next_step,
        "command_hint": command_hint,
    }


def build_machine_memory_repair_plan(health: dict[str, Any]) -> dict[str, Any]:
    active_actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    for action in active_actions + inactive_actions:
        action.update(describe_machine_memory_action(action))
    ready_actions = [action for action in active_actions if action.get("status") == "accepted"]
    triage_actions = [action for action in active_actions if action.get("status") == "proposed"]
    deferred_actions = [action for action in active_actions if action.get("status") == "deferred"]
    escalated_ids = {action["id"] for action in health.get("escalated_actions", []) if action.get("id")}
    overdue_ids = {action["id"] for action in health.get("overdue_actions", []) if action.get("id")}

    batches: dict[str, dict[str, Any]] = {}
    for action in ready_actions:
        batch_key = str(action.get("component_id") or action.get("primary_path") or action.get("id"))
        label = (
            f"component `{action['component_id']}`" if action.get("component_id") else f"page `{action['primary_path']}`"
        )
        batch = batches.setdefault(
            batch_key,
            {
                "id": batch_key,
                "label": label,
                "component_id": action.get("component_id", ""),
                "primary_paths": set(),
                "secondary_paths": set(),
                "action_ids": [],
                "actions": [],
                "priority_rank": 9,
                "escalated": False,
                "overdue": False,
            },
        )
        batch["primary_paths"].add(str(action.get("primary_path") or ""))
        if action.get("secondary_path"):
            batch["secondary_paths"].add(str(action.get("secondary_path") or ""))
        batch["action_ids"].append(action["id"])
        batch["actions"].append(action)
        batch["priority_rank"] = min(batch["priority_rank"], action_priority_rank(str(action.get("priority") or "")))
        batch["escalated"] = batch["escalated"] or action["id"] in escalated_ids
        batch["overdue"] = batch["overdue"] or action["id"] in overdue_ids

    execution_batches = sorted(
        [
            {
                **batch,
                "primary_paths": sorted(path for path in batch["primary_paths"] if path),
                "secondary_paths": sorted(path for path in batch["secondary_paths"] if path),
                "actions": sorted(
                    batch["actions"],
                    key=lambda item: (
                        action_priority_rank(str(item.get("priority") or "")),
                        -int(item.get("occurrences", 0)),
                        str(item.get("title", "")).lower(),
                    ),
                ),
            }
            for batch in batches.values()
        ],
        key=lambda item: (
            0 if item["escalated"] else 1,
            0 if item["overdue"] else 1,
            item["priority_rank"],
            item["label"],
        ),
    )
    execution_proposals = repair_execution_proposals(ready_actions + triage_actions + deferred_actions)

    return {
        "ready_actions": ready_actions,
        "triage_actions": triage_actions,
        "deferred_actions": deferred_actions,
        "inactive_actions": inactive_actions[:12],
        "execution_batches": execution_batches[:10],
        "execution_proposals": execution_proposals,
        "counts": {
            "ready": len(ready_actions),
            "triage": len(triage_actions),
            "deferred": len(deferred_actions),
            "inactive": len(inactive_actions),
            "batches": len(execution_batches),
            "proposals": len(execution_proposals),
        },
    }


def normalize_query_signature(query: str) -> str:
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower())
    signature = "-".join(tokens).strip("-")
    return signature[:160] or "query"


def classify_recurring_output_kind(query: str) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower()))
    decision_score = sum(1 for marker in DECISION_QUERY_MARKERS if marker in normalized)
    judgment_score = sum(1 for marker in JUDGMENT_QUERY_MARKERS if marker in normalized)
    if decision_score <= 0 and judgment_score <= 0:
        return ""
    if decision_score >= judgment_score:
        return "decision"
    return "judgment"


def promotion_page_title(kind: str, query: str) -> str:
    prefix = "决策沉淀" if kind == "decision" else "判断沉淀"
    return f"{prefix}：{query}"


def collect_output_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            query = str(frontmatter.get("query") or "").strip()
            output_format = str(frontmatter.get("format") or "").strip()
            if not query or output_format not in AUTO_PROMOTION_FORMATS:
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": query,
                    "query_signature": normalize_query_signature(query),
                    "format": output_format,
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["query_signature"], item["created_at"], item["path"]))


def find_promoted_curated_page(root: Path, kind: str, query_signature: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != kind:
            continue
        if str(frontmatter.get("promotion_query_signature") or "") == query_signature:
            return path
    return None


def recurring_promotion_needs_refresh(page_path: Path, artifacts: list[dict[str, str]]) -> bool:
    frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8", errors="replace"))
    current_count = str(frontmatter.get("promotion_count") or "")
    current_last_artifact = str(frontmatter.get("promotion_last_artifact") or "")
    current_sources = {
        str(path)
        for path in frontmatter.get("source_files", [])
        if isinstance(path, str) and path.strip()
    }
    desired_count = str(len(artifacts))
    desired_last_artifact = artifacts[-1]["path"]
    desired_sources = {artifact["path"] for artifact in artifacts}
    if current_count != desired_count:
        return True
    if current_last_artifact != desired_last_artifact:
        return True
    if not desired_sources.issubset(current_sources):
        return True
    return False


def annotate_recurring_promotion(
    root: Path,
    page_path: Path,
    *,
    kind: str,
    query: str,
    query_signature: str,
    artifacts: list[dict[str, str]],
    generated_at: str,
) -> None:
    content = page_path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_files = [
        str(path)
        for path in frontmatter.get("source_files", [])
        if isinstance(path, str) and path.strip()
    ]
    for artifact in artifacts:
        artifact_path = artifact["path"]
        if artifact_path not in source_files:
            source_files.append(artifact_path)
    formats = sorted({artifact["format"] for artifact in artifacts})
    title = promotion_page_title(kind, query)
    frontmatter["title"] = title
    frontmatter["source_files"] = source_files
    frontmatter["promotion_origin"] = "nightly-recurring-output"
    frontmatter["promotion_query"] = query
    frontmatter["promotion_query_signature"] = query_signature
    frontmatter["promotion_count"] = str(len(artifacts))
    frontmatter["promotion_formats"] = formats
    frontmatter["promotion_last_artifact"] = artifacts[-1]["path"]
    frontmatter["last_compiled_at"] = generated_at
    body = replace_first_markdown_heading(strip_frontmatter(content).strip(), title).strip()
    auto_lines = [
        "- Rule: `nightly-recurring-output`",
        f"- Query: `{query}`",
        f"- Signature: `{query_signature}`",
        f"- Matching outputs: `{len(artifacts)}`",
        f"- Latest artifact: `{artifacts[-1]['path']}`",
        f"- Formats: `{', '.join(formats)}`",
    ]
    for artifact in artifacts[-5:]:
        auto_lines.append(f"- Supporting artifact: `{artifact['path']}`")
    updated_body = upsert_markdown_section(body, "Auto Promotion", "\n".join(auto_lines)).strip()
    page_path.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body}\n", encoding="utf-8")


def promote_recurring_outputs(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    groups: dict[str, list[dict[str, str]]] = {}
    for artifact in collect_output_artifacts(root):
        groups.setdefault(artifact["query_signature"], []).append(artifact)

    generated_at = utc_now()
    created = 0
    updated = 0
    promotions: list[dict[str, str]] = []
    for query_signature, artifacts in sorted(groups.items()):
        if len(artifacts) < AUTO_PROMOTION_MIN_OCCURRENCES:
            continue
        query = artifacts[0]["query"]
        kind = classify_recurring_output_kind(query)
        if kind not in {"decision", "judgment"}:
            continue
        existing = find_promoted_curated_page(root, kind, query_signature)
        if existing is None:
            result = file_back(
                root,
                artifacts[-1]["path"],
                title=f"{kind}-{query_signature}",
                kind=kind,
            )
            page_path = root / result["path"]
            action = "created"
            created += 1
        else:
            if not recurring_promotion_needs_refresh(existing, artifacts):
                continue
            page_path = existing
            action = "updated"
            updated += 1
        annotate_recurring_promotion(
            root,
            page_path,
            kind=kind,
            query=query,
            query_signature=query_signature,
            artifacts=artifacts,
            generated_at=generated_at,
        )
        promotions.append(
            {
                "kind": kind,
                "action": action,
                "path": relative_path(root, page_path),
                "query": query,
                "query_signature": query_signature,
                "occurrences": str(len(artifacts)),
                "latest_artifact": artifacts[-1]["path"],
            }
        )
        append_wiki_log(
            root,
            "promote",
            query,
            [
                f"kind: `{kind}`",
                f"action: `{action}`",
                f"occurrences: `{len(artifacts)}`",
                f"page: `{relative_path(root, page_path)}`",
                f"latest_artifact: `{artifacts[-1]['path']}`",
            ],
        )

    return {
        "count": len(promotions),
        "created": created,
        "updated": updated,
        "pages": promotions,
    }


def render_curated_page_summary(page: dict[str, str]) -> str:
    suffix_parts = [f"状态 `{display_curated_status(page.get('status', '') or 'unknown')}`"]
    confidence = page.get("confidence", "")
    if confidence:
        suffix_parts.append(f"置信度 `{confidence}`")
    reviewed_at = page.get("reviewed_at", "")
    if reviewed_at:
        suffix_parts.append(f"审阅时间 `{reviewed_at}`")
    revisit_after = page.get("revisit_after", "")
    if revisit_after:
        suffix_parts.append(f"复审截止 `{revisit_after}`")
    if page.get("overdue_review") == "true":
        suffix_parts.append("已到期待复审")
    if page.get("escalation_candidate") == "true":
        suffix_parts.append("需要升级处理")
    return f"- [{page['title']}](../../{page['path']}) | " + " | ".join(suffix_parts)


def render_curated_index(
    heading: str,
    section_name: str,
    pages: list[dict[str, str]],
    compiled_at: str,
) -> str:
    pending_review = sum(1 for page in pages if page.get("pending_review") == "true")
    overdue_review = sum(1 for page in pages if page.get("overdue_review") == "true")
    escalated = sum(1 for page in pages if page.get("escalation_candidate") == "true")
    status_counts: dict[str, int] = {}
    for page in pages:
        status = page.get("status", "") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [
        f"# {heading}",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 页面总数：`{len(pages)}`",
        f"- 待审阅数量：`{pending_review}`",
        f"- 已到期数量：`{overdue_review}`",
        f"- 需要升级：`{escalated}`",
        "",
        "## 状态统计",
    ]
    if not status_counts:
        lines.append("- 还没有相关页面。")
    else:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- `{display_curated_status(status)}`：`{count}`")
    lines.extend(
        [
            "",
        f"## {section_name}",
        ]
    )
    if not pages:
        lines.append(f"- 还没有{section_name}。")
    else:
        for page in pages:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_review_queue(decisions: list[dict[str, str]], judgments: list[dict[str, str]], compiled_at: str) -> str:
    queue = review_queue(decisions, judgments)
    aging = collect_aging_signals(decisions, judgments)
    lines = [
        "# 审阅队列",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 待审决策：`{len(queue['pending_decisions'])}`",
        f"- 待审判断：`{len(queue['pending_judgments'])}`",
        f"- 最近已审项目：`{len(queue['recently_reviewed'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        "",
        "## 待审决策",
    ]
    if not queue["pending_decisions"]:
        lines.append("- 当前没有待审决策。")
    else:
        for page in queue["pending_decisions"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 待审判断"])
    if not queue["pending_judgments"]:
        lines.append("- 当前没有待审判断。")
    else:
        for page in queue["pending_judgments"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期的决策或判断页面。")
    else:
        for page in aging["overdue"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 需要升级处理"])
    if not aging["escalated"]:
        lines.append("- 当前没有需要升级处理的页面。")
    else:
        for page in aging["escalated"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近已审"])
    if not queue["recently_reviewed"]:
        lines.append("- 还没有已审阅的决策或判断页面。")
    else:
        for page in queue["recently_reviewed"][:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_aging_report(decisions: list[dict[str, str]], judgments: list[dict[str, str]], compiled_at: str) -> str:
    aging = collect_aging_signals(decisions, judgments)
    pages = decisions + judgments
    lines = [
        "# Aging 报告",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 已排期复审：`{len(aging['scheduled'])}`",
        "",
        "## 需要升级处理",
    ]
    if not aging["escalated"]:
        lines.append("- 当前没有升级处理项。")
    else:
        for page in aging["escalated"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期页面。")
    else:
        for page in aging["overdue"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已排期复审"])
    if not aging["scheduled"]:
        lines.append("- 当前没有已排期的复审页面。")
    else:
        for page in aging["scheduled"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 建议动作"])
    if aging["escalated"]:
        lines.append("- 优先处理升级项，补证据、更新状态或明确下一次复审窗口。")
    if aging["overdue"] and not aging["escalated"]:
        lines.append("- 先清理已到期页面，避免 review queue 长期堆积。")
    if not aging["overdue"] and not aging["escalated"]:
        lines.append("- 当前 aging 状态健康，继续通过 nightly 跟踪。")
    stale_reviewed = [
        page
        for page in pages
        if page.get("pending_review") != "true" and page.get("revisit_after")
    ]
    if stale_reviewed:
        lines.append("- 已审页面如仍保留复审窗口，必要时在下一次 review 中收紧或清空。")
    return "\n".join(lines) + "\n"


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments)
    aging = collect_aging_signals(decisions, judgments)
    lines = [
        "# 编译状态",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级：`{len(aging['escalated'])}`",
        "- 总索引位于 `index.md`。",
        "- 运行时规则位于 `schema/`。",
        "- 操作日志位于 `log.md`。",
        "- 决策索引位于 `decisions.md`。",
        "- 判断索引位于 `judgments.md`。",
        "- 审阅队列位于 `review-queue.md`。",
        "- 审阅中心位于 `review-center.md`。",
        "- aging 报告位于 `aging-report.md`。",
        "- 机器记忆摘要位于 `machine-memory.md`。",
        "- 图谱视图位于 `graph-view.md`。",
        "- 机器记忆拓扑位于 `machine-memory-topology.md`。",
        "- 机器记忆动作队列位于 `machine-memory-actions.md`。",
        "- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。",
        "- 图谱健康页位于 `graph-health.md`。",
        "- 漂移报告位于 `drift-report.md`。",
        "- 修复待办位于 `repair-backlog.md`。",
        "- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。",
        "- lint 结果输出在 `output/lint/`。",
    ]
    return "\n".join(lines) + "\n"


def render_master_index(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments)
    aging = collect_aging_signals(decisions, judgments)
    lines = [
        "# 知识库总索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        "",
        "## 核心页面",
        "- [来源索引](./sources.md)",
        "- [概念索引](./concepts.md)",
        "- [概念质量](./concept-quality.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [审阅队列](./review-queue.md)",
        "- [审阅中心](./review-center.md)",
        "- [Aging 报告](./aging-report.md)",
        "- [编译状态](./compile-status.md)",
        "- [机器记忆](./machine-memory.md)",
        "- [图谱视图](./graph-view.md)",
        "- [机器记忆拓扑](./machine-memory-topology.md)",
        "- [机器记忆动作队列](./machine-memory-actions.md)",
        "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
        "- [图谱健康](./graph-health.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [操作日志](./log.md)",
        "- [运行时规则](../../schema/index.md)",
        "",
        "## 最近来源",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in sorted(entries, key=lambda item: item["imported_at"], reverse=True)[:8]:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md)")
    lines.extend(["", "## 重点概念"])
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts[:10]:
            lines.append(f"- [{concept['title']}](../concepts/{concept['slug']}.md)")
    lines.extend(["", "## 待审项目"])
    if not queue["pending_decisions"] and not queue["pending_judgments"]:
        lines.append("- 当前没有等待审阅的决策或判断页面。")
    else:
        for page in (queue["pending_decisions"] + queue["pending_judgments"])[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近决策"])
    if not decisions:
        lines.append("- 还没有回流的决策页面。")
    else:
        for page in decisions[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近判断"])
    if not judgments:
        lines.append("- 还没有回流的判断页面。")
    else:
        for page in judgments[:8]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def ensure_wiki_log(root: Path) -> Path:
    ensure_layout(root)
    path = root / "wiki" / "indexes" / "log.md"
    if not path.exists():
        path.write_text("# 知识库日志\n\n", encoding="utf-8")
    return path


def append_wiki_log(root: Path, category: str, title: str, details: list[str]) -> None:
    path = ensure_wiki_log(root)
    timestamp = utc_now()
    lines = [
        f"## [{timestamp}] {category} | {title}",
        "",
        *[f"- {detail}" for detail in details],
        "",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def remove_stale_generated_concept_pages(root: Path, active_slugs: set[str]) -> int:
    removed = 0
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != "concept":
            continue
        if frontmatter.get("generated_by") != "aiwiki-compile":
            continue
        concept_id = frontmatter.get("id", "")
        if not isinstance(concept_id, str) or not concept_id.startswith("concept-"):
            continue
        slug = concept_id[len("concept-") :]
        if slug in active_slugs:
            continue
        path.unlink()
        removed += 1
    return removed


def machine_memory_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory.json"


def machine_memory_graph_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache" / "machine-memory-graph.json"


def machine_memory_graph_html_path(root: Path) -> Path:
    return root / "output" / "graph" / "machine-memory.html"


def machine_memory_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-history.jsonl"


def machine_memory_drift_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "drift-report.md"


def graph_health_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "graph-health.md"


def machine_memory_topology_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-topology.md"


def machine_memory_actions_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-actions.md"


def machine_memory_repair_plan_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-repair-plan.md"


def concept_quality_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "concept-quality.md"


def machine_memory_action_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-actions.json"


def repair_backlog_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "repair-backlog.md"


def aging_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "aging-report.md"


def nightly_health_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "nightly-health.json"


def load_json_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def default_machine_memory_action_state() -> dict[str, Any]:
    return {"version": 1, "actions": []}


def load_machine_memory_action_state(root: Path) -> dict[str, Any]:
    document = load_json_document(machine_memory_action_state_path(root))
    if not isinstance(document, dict):
        return default_machine_memory_action_state()
    actions = document.get("actions")
    if not isinstance(actions, list):
        return default_machine_memory_action_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "actions": [action for action in actions if isinstance(action, dict)],
    }


def save_machine_memory_action_state(root: Path, document: dict[str, Any]) -> None:
    machine_memory_action_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_machine_memory(root: Path) -> dict[str, Any]:
    memory = load_json_document(machine_memory_state_path(root))
    return memory if isinstance(memory, dict) else {}


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    term_index: dict[str, dict[str, set[str]]] = {}
    source_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    source_to_concept: list[dict[str, str]] = []
    concept_to_concept: list[dict[str, str]] = []
    citation_map: list[dict[str, Any]] = []

    def index_term(term: str, *, source_id: str | None = None, concept_slug: str | None = None) -> None:
        bucket = term_index.setdefault(term, {"source_ids": set(), "concept_slugs": set()})
        if source_id:
            bucket["source_ids"].add(source_id)
        if concept_slug:
            bucket["concept_slugs"].add(concept_slug)

    for entry in entries:
        concept_slugs = [concept_label_to_slug(label) for label in entry_terms.get(entry["id"], [])]
        source_page = f"wiki/sources/{entry['id']}.md"
        summary = source_summary_or_preview(root, entry, previews[entry["id"]])
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "source_type": entry["source_type"],
                "kind": entry["kind"],
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
                "source_page": source_page,
                "concept_slugs": concept_slugs,
            }
        )
        citation_map.append(
            {
                "source_page": source_page,
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
            }
        )
        for slug in concept_slugs:
            source_to_concept.append({"source_id": entry["id"], "concept_slug": slug})
        for token in tokenize(f"{entry['title']}\n{summary}"):
            index_term(token, source_id=entry["id"])

    for record in concepts:
        concept_nodes.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
                "related_slugs": record.get("related_slugs", []),
                "source_signature": record["source_signature"],
            }
        )
        for related_slug in record.get("related_slugs", []):
            concept_to_concept.append({"from": record["slug"], "to": related_slug})
        for token in tokenize(record["title"]):
            index_term(token, concept_slug=record["slug"])

    drift = {
        "missing_raw_files": [
            entry["stored_path"] for entry in entries if not (root / entry["stored_path"]).exists()
        ],
        "missing_source_pages": [
            f"wiki/sources/{entry['id']}.md"
            for entry in entries
            if not (root / "wiki" / "sources" / f"{entry['id']}.md").exists()
        ],
        "missing_concept_pages": [
            f"wiki/concepts/{record['slug']}.md"
            for record in concepts
            if not (root / "wiki" / "concepts" / f"{record['slug']}.md").exists()
        ],
        "sources_without_concepts": [entry["id"] for entry in entries if not entry_terms.get(entry["id"])],
    }

    return {
        "version": 1,
        "compiled_at": compiled_at,
        "source_nodes": sorted(source_nodes, key=lambda item: item["id"]),
        "concept_nodes": sorted(concept_nodes, key=lambda item: item["slug"]),
        "edges": {
            "source_to_concept": sorted(source_to_concept, key=lambda item: (item["source_id"], item["concept_slug"])),
            "concept_to_concept": sorted(concept_to_concept, key=lambda item: (item["from"], item["to"])),
        },
        "citation_map": sorted(citation_map, key=lambda item: item["source_page"]),
        "term_index": {
            term: {
                "source_ids": sorted(payload["source_ids"]),
                "concept_slugs": sorted(payload["concept_slugs"]),
            }
            for term, payload in sorted(term_index.items())
        },
        "drift": drift,
    }


def build_machine_memory_health(memory: dict[str, Any]) -> dict[str, Any]:
    source_nodes = memory.get("source_nodes", [])
    concept_nodes = memory.get("concept_nodes", [])
    edges = memory.get("edges", {})
    drift = memory.get("drift", {})

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    concept_related: dict[str, set[str]] = {}
    source_node_by_id = {node["id"]: node for node in source_nodes}
    concept_node_by_slug = {node["slug"]: node for node in concept_nodes}

    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        concept_related.setdefault(left, set()).add(right)
        concept_related.setdefault(right, set()).add(left)

    isolated_source_ids = sorted(node["id"] for node in source_nodes if not source_to_concepts.get(node["id"]))
    singleton_concept_slugs = sorted(
        node["slug"]
        for node in concept_nodes
        if len(concept_to_sources.get(node["slug"], set())) <= 1 and not concept_related.get(node["slug"])
    )
    bridge_concept_slugs = [
        node["slug"]
        for node in sorted(
            concept_nodes,
            key=lambda item: (
                -len(concept_to_sources.get(item["slug"], set())),
                -len(concept_related.get(item["slug"], set())),
                item["title"].lower(),
            ),
        )
        if len(concept_to_sources.get(node["slug"], set())) >= 2 and concept_related.get(node["slug"])
    ]
    overloaded_concept_slugs = sorted(
        node["slug"] for node in concept_nodes if len(concept_to_sources.get(node["slug"], set())) >= 4
    )

    hub_concepts = [
        {
            "slug": node["slug"],
            "title": node["title"],
            "source_count": len(concept_to_sources.get(node["slug"], set())),
            "related_count": len(concept_related.get(node["slug"], set())),
            "component_id": "",
        }
        for node in concept_nodes
    ]
    hub_concepts.sort(
        key=lambda item: (-item["source_count"], -item["related_count"], item["title"].lower())
    )
    hub_sources = [
        {
            "id": node["id"],
            "title": node["title"],
            "concept_count": len(source_to_concepts.get(node["id"], set())),
            "source_page": node["source_page"],
            "component_id": "",
        }
        for node in source_nodes
    ]
    hub_sources.sort(key=lambda item: (-item["concept_count"], item["title"].lower()))

    adjacency = build_machine_memory_adjacency(memory)

    visited: set[str] = set()
    component_sizes: list[int] = []
    component_records: list[dict[str, Any]] = []
    for node_key in sorted(adjacency):
        if node_key in visited:
            continue
        stack = [node_key]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(set(adjacency.get(current, {})) - visited))
        component_sizes.append(len(members))
        source_ids = sorted(member.removeprefix("source:") for member in members if member.startswith("source:"))
        concept_slugs = sorted(member.removeprefix("concept:") for member in members if member.startswith("concept:"))
        component_records.append(
            {
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
                "size": len(members),
                "sort_key": (
                    -len(members),
                    source_ids[0] if source_ids else "~",
                    concept_slugs[0] if concept_slugs else "~",
                ),
            }
        )
    component_sizes.sort(reverse=True)
    component_records.sort(key=lambda item: item["sort_key"])
    components: list[dict[str, Any]] = []
    source_component_ids: dict[str, str] = {}
    concept_component_ids: dict[str, str] = {}
    for index, record in enumerate(component_records, start=1):
        component_id = f"component-{index}"
        components.append(
            {
                "id": component_id,
                "size": record["size"],
                "source_ids": record["source_ids"],
                "concept_slugs": record["concept_slugs"],
            }
        )
        for source_id in record["source_ids"]:
            source_component_ids[source_id] = component_id
        for concept_slug in record["concept_slugs"]:
            concept_component_ids[concept_slug] = component_id

    for item in hub_concepts:
        item["component_id"] = concept_component_ids.get(item["slug"], "")
    for item in hub_sources:
        item["component_id"] = source_component_ids.get(item["id"], "")

    term_index = memory.get("term_index", {})
    suggestion_scores: dict[tuple[str, str], set[str]] = {}
    for term, payload in term_index.items():
        source_ids = payload.get("source_ids", [])
        concept_slugs = payload.get("concept_slugs", [])
        if not source_ids or not concept_slugs:
            continue
        for source_id in source_ids:
            if source_id not in drift.get("sources_without_concepts", []) and source_id not in isolated_source_ids:
                continue
            for concept_slug in concept_slugs:
                suggestion_scores.setdefault((source_id, concept_slug), set()).add(term)

    link_suggestions: list[dict[str, Any]] = []
    for (source_id, concept_slug), shared_terms in suggestion_scores.items():
        source_node = source_node_by_id.get(source_id)
        concept_node = concept_node_by_slug.get(concept_slug)
        if not source_node or not concept_node:
            continue
        link_suggestions.append(
            {
                "source_id": source_id,
                "source_title": source_node["title"],
                "source_page": source_node["source_page"],
                "concept_slug": concept_slug,
                "concept_title": concept_node["title"],
                "concept_page": f"wiki/concepts/{concept_slug}.md",
                "shared_terms": sorted(shared_terms),
                "score": len(shared_terms),
                "component_id": concept_component_ids.get(concept_slug, ""),
            }
        )
    link_suggestions.sort(
        key=lambda item: (-item["score"], item["source_title"].lower(), item["concept_title"].lower())
    )

    actions: list[dict[str, Any]] = []
    for suggestion in link_suggestions[:12]:
        shared_terms = suggestion.get("shared_terms", [])
        actions.append(
            {
                "id": f"link-{suggestion['source_id']}-{suggestion['concept_slug']}",
                "kind": "add-source-concept-link",
                "priority": "high" if suggestion["score"] >= 3 else "medium",
                "title": f"补连 {suggestion['source_title']} -> {suggestion['concept_title']}",
                "primary_path": suggestion["source_page"],
                "secondary_path": suggestion["concept_page"],
                "component_id": suggestion.get("component_id", ""),
                "reason": f"共享词：{', '.join(shared_terms[:6]) or 'none'}",
                "score": suggestion["score"],
                "source_ids": [suggestion["source_id"]],
                "concept_slugs": [suggestion["concept_slug"]],
            }
        )

    suggested_source_ids = {action["source_ids"][0] for action in actions if action.get("source_ids")}
    for source_id in isolated_source_ids:
        if source_id in suggested_source_ids:
            continue
        source_node = source_node_by_id.get(source_id)
        if not source_node:
            continue
        actions.append(
            {
                "id": f"isolated-source-{source_id}",
                "kind": "connect-isolated-source",
                "priority": "medium",
                "title": f"连接孤立来源 {source_node['title']}",
                "primary_path": source_node["source_page"],
                "secondary_path": "",
                "component_id": source_component_ids.get(source_id, ""),
                "reason": "来源节点当前没有接入任何概念。",
                "score": 1,
                "source_ids": [source_id],
                "concept_slugs": [],
            }
        )

    for concept_slug in singleton_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"singleton-concept-{concept_slug}",
                "kind": "expand-singleton-concept",
                "priority": "medium",
                "title": f"扩展单节点概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前只关联 `{source_count}` 个来源，且没有概念间连接。",
                "score": max(1, source_count),
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in overloaded_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"overloaded-concept-{concept_slug}",
                "kind": "split-overloaded-concept",
                "priority": "high" if source_count >= 6 else "medium",
                "title": f"拆分过载概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前挂接 `{source_count}` 个来源，可能过宽。",
                "score": source_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in bridge_concept_slugs[:6]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        related_count = len(concept_related.get(concept_slug, set()))
        actions.append(
            {
                "id": f"bridge-concept-{concept_slug}",
                "kind": "monitor-bridge-concept",
                "priority": "low",
                "title": f"观察桥接概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"概念连接 `{related_count}` 个相关概念，属于图谱桥接点。",
                "score": related_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(
        key=lambda item: (
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
            str(item.get("id", "")),
        )
    )
    action_counts = {
        "total": len(actions),
        "by_priority": {
            priority: sum(1 for action in actions if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_kind": {
            kind: sum(1 for action in actions if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }

    return {
        "isolated_source_ids": isolated_source_ids,
        "singleton_concept_slugs": singleton_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs[:10],
        "overloaded_concept_slugs": overloaded_concept_slugs,
        "hub_concepts": hub_concepts[:10],
        "hub_sources": hub_sources[:10],
        "link_suggestions": link_suggestions[:12],
        "actions": actions[:20],
        "action_counts": action_counts,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "components": components,
        "source_component_ids": source_component_ids,
        "concept_component_ids": concept_component_ids,
    }


def reconcile_machine_memory_actions(
    root: Path,
    health: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    previous_state = load_machine_memory_action_state(root)
    previous_by_id = {
        str(action.get("id")): action for action in previous_state.get("actions", []) if action.get("id")
    }
    now = parse_iso_datetime(compiled_at) or datetime.now(timezone.utc)
    active_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for action in health.get("actions", []):
        action_id = str(action.get("id") or "").strip()
        if not action_id:
            continue
        previous = previous_by_id.get(action_id, {})
        previous_status = str(previous.get("status") or "proposed")
        status = previous_status if previous_status in ACTION_STATUSES else "proposed"
        reopened_count = int(previous.get("reopened_count") or 0)
        reopened_from = ""
        if previous and previous.get("active") is False and status in {"resolved", "rejected"}:
            reopened_from = status
            reopened_count += 1
            status = "proposed"
        first_seen_at = str(previous.get("first_seen_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0)
        if occurrences <= 0:
            occurrences = 1
        else:
            occurrences += 1
        status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
        if status != previous_status or not status_updated_at:
            status_updated_at = compiled_at
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        revisit_after = str(previous.get("revisit_after") or "")
        escalate_after = str(previous.get("escalate_after") or "")
        if status in PENDING_ACTION_STATUSES:
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows("action", status, base_timestamp)
        else:
            revisit_after, escalate_after = "", ""
        record = {
            **action,
            "status": status,
            "active": True,
            "first_seen_at": first_seen_at,
            "last_seen_at": compiled_at,
            "occurrences": occurrences,
            "status_updated_at": status_updated_at,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
            "reopened_count": reopened_count,
            "reopened_from": reopened_from,
            "inactive_since": "",
            "pending_review": "true" if action_needs_review(status) else "false",
        }
        record.update(evaluate_page_aging(record, now=now))
        active_records.append(record)
        seen_ids.add(action_id)

    inactive_records: list[dict[str, Any]] = []
    for action_id, previous in previous_by_id.items():
        if action_id in seen_ids:
            continue
        record = dict(previous)
        record["active"] = False
        record["inactive_since"] = str(previous.get("inactive_since") or compiled_at)
        record["pending_review"] = "false"
        record["aging_state"] = ""
        record["overdue_review"] = "false"
        record["escalation_candidate"] = "false"
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            action_status_rank(str(item.get("status"))),
            action_priority_rank(str(item.get("priority"))),
            -int(item.get("occurrences", 0)),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("inactive_since") or item.get("last_seen_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    overdue_actions = [record for record in active_records if record.get("overdue_review") == "true"]
    escalated_actions = [record for record in active_records if record.get("escalation_candidate") == "true"]
    active_records = [{**record, **describe_machine_memory_action(record)} for record in active_records]
    inactive_records = [{**record, **describe_machine_memory_action(record)} for record in inactive_records]
    overdue_actions = [{**record, **describe_machine_memory_action(record)} for record in overdue_actions]
    escalated_actions = [{**record, **describe_machine_memory_action(record)} for record in escalated_actions]
    counts = {
        "total": len(active_records),
        "inactive": len(inactive_records),
        "overdue": len(overdue_actions),
        "escalated": len(escalated_actions),
        "by_priority": {
            priority: sum(1 for action in active_records if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_status": {
            status: sum(1 for action in active_records if action.get("status") == status)
            for status in ACTION_STATUSES
        },
        "by_kind": {
            kind: sum(1 for action in active_records if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }
    state_document = {
        "version": 1,
        "compiled_at": compiled_at,
        "actions": active_records + inactive_records,
    }
    save_machine_memory_action_state(root, state_document)
    return {
        "actions": active_records[:20],
        "inactive_actions": inactive_records[:12],
        "overdue_actions": overdue_actions[:10],
        "escalated_actions": escalated_actions[:10],
        "action_counts": counts,
        "action_state_path": relative_path(root, machine_memory_action_state_path(root)),
    }


def machine_memory_digest(memory: dict[str, Any]) -> str:
    payload = {
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "edges": memory.get("edges", {}),
        "citation_map": memory.get("citation_map", []),
        "term_index": memory.get("term_index", {}),
        "drift": memory.get("drift", {}),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def build_machine_memory_graph(memory: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in memory.get("source_nodes", []):
        nodes.append(
            {
                "id": f"source:{node['id']}",
                "kind": "source",
                "title": node["title"],
                "source_type": node["source_type"],
                "source_page": node["source_page"],
                "stored_path": node["stored_path"],
            }
        )
    for node in memory.get("concept_nodes", []):
        nodes.append(
            {
                "id": f"concept:{node['slug']}",
                "kind": "concept",
                "title": node["title"],
                "source_pages": node["source_pages"],
            }
        )
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"concept:{edge['concept_slug']}",
                "type": "HAS_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": "RELATED_CONCEPT",
            }
        )
    graph = {
        "version": 1,
        "compiled_at": memory["compiled_at"],
        "nodes": sorted(nodes, key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["type"], item["source"], item["target"])),
    }
    graph["digest"] = sha256_bytes(json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, sort_keys=True).encode("utf-8"))
    return graph


def render_machine_memory_graph_html(memory: dict[str, Any], graph: dict[str, Any]) -> str:
    health = memory.get("health", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    components = health.get("components", [])
    if not components and (source_nodes or concept_nodes):
        components = [
            {
                "id": "component-1",
                "source_ids": sorted(source_nodes),
                "concept_slugs": sorted(concept_nodes),
                "size": len(source_nodes) + len(concept_nodes),
            }
        ]

    positions: dict[str, tuple[int, int]] = {}
    sections: list[dict[str, Any]] = []
    current_y = 36
    section_width = 980
    for component in components:
        source_ids = [source_id for source_id in component.get("source_ids", []) if source_id in source_nodes]
        concept_slugs = [slug for slug in component.get("concept_slugs", []) if slug in concept_nodes]
        if not source_ids and not concept_slugs:
            continue
        row_count = max(len(source_ids), len(concept_slugs), 1)
        row_gap = 68
        section_height = 96 + max(row_count - 1, 0) * row_gap
        row_top = current_y + 52
        for index, source_id in enumerate(source_ids):
            positions[f"source:{source_id}"] = (220, row_top + index * row_gap)
        for index, concept_slug in enumerate(concept_slugs):
            positions[f"concept:{concept_slug}"] = (820, row_top + index * row_gap)
        sections.append(
            {
                "id": component.get("id", "component"),
                "y": current_y,
                "height": section_height,
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
            }
        )
        current_y += section_height + 28

    view_height = max(current_y + 24, 320)

    def truncate_label(text: str, limit: int = 30) -> str:
        return text if len(text) <= limit else f"{text[: limit - 3]}..."

    edge_fragments: list[str] = []
    for edge in graph.get("edges", []):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        if str(edge.get("type") or "") == "RELATED_CONCEPT":
            stroke = "#f59e0b"
            dash = ' stroke-dasharray="8 6"'
        else:
            stroke = "#94a3b8"
            dash = ""
        edge_fragments.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="2"{dash} opacity="0.72" />'
        )

    node_fragments: list[str] = []
    for node in graph.get("nodes", []):
        node_id = str(node.get("id") or "")
        position = positions.get(node_id)
        if not position:
            continue
        x, y = position
        kind = str(node.get("kind") or "concept")
        title = str(node.get("title") or node_id)
        if kind == "source":
            fill = "#0f766e"
            stroke = "#115e59"
            href = f"../../{html.escape(str(node.get('source_page') or ''))}"
            subtitle = html.escape(str(node.get("source_type") or "source"))
        else:
            fill = "#1d4ed8"
            stroke = "#1e40af"
            href = f"../../wiki/concepts/{html.escape(node_id.removeprefix('concept:'))}.md"
            subtitle = "concept"
        safe_title = html.escape(title)
        label = html.escape(truncate_label(title))
        rx = x - 120
        ry = y - 22
        node_fragments.append(
            "\n".join(
                [
                    f'<a href="{href}">',
                    f'  <title>{safe_title}</title>',
                    f'  <rect x="{rx}" y="{ry}" width="240" height="44" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2" />',
                    f'  <text x="{x}" y="{y - 3}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">{label}</text>',
                    f'  <text x="{x}" y="{y + 14}" text-anchor="middle" fill="#dbeafe" font-size="11">{html.escape(subtitle)}</text>',
                    "</a>",
                ]
            )
        )

    section_fragments: list[str] = []
    for section in sections:
        section_fragments.append(
            f'<rect x="20" y="{section["y"]}" width="{section_width}" height="{section["height"]}" rx="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5" />'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 28}" fill="#0f172a" font-size="15" font-weight="700">{html.escape(section["id"])}</text>'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 48}" fill="#475569" font-size="12">sources {len(section["source_ids"])} | concepts {len(section["concept_slugs"])}</text>'
        )

    hub_concepts = health.get("hub_concepts", [])
    hub_sources = health.get("hub_sources", [])
    actions = health.get("action_counts", {})
    repair_counts = health.get("repair_plan", {}).get("counts", {})
    summary_items = [
        f"来源节点 {len(memory.get('source_nodes', []))}",
        f"概念节点 {len(memory.get('concept_nodes', []))}",
        f"分量 {health.get('component_count', 0)}",
        f"桥接概念 {len(health.get('bridge_concept_slugs', []))}",
        f"修复动作 {actions.get('total', 0)}",
        f"执行提案 {repair_counts.get('proposals', 0)}",
    ]

    hub_concept_items = "".join(
        f'<li><a href="../../wiki/concepts/{html.escape(item["slug"])}.md">{html.escape(item["title"])}</a> | sources {item.get("source_count", 0)} | related {item.get("related_count", 0)}</li>'
        for item in hub_concepts[:8]
    ) or "<li>当前没有 hub 概念。</li>"
    hub_source_items = "".join(
        f'<li><a href="../../wiki/sources/{html.escape(item["id"])}.md">{html.escape(item["title"])}</a> | concepts {item.get("concept_count", 0)}</li>'
        for item in hub_sources[:8]
    ) or "<li>当前没有 hub 来源。</li>"
    suggestion_items = "".join(
        f'<li><a href="../../wiki/sources/{html.escape(item["source_id"])}.md">{html.escape(item["source_title"])}</a> -> <a href="../../wiki/concepts/{html.escape(item["concept_slug"])}.md">{html.escape(item["concept_title"])}</a> | score {item.get("score", 0)} | shared {html.escape(", ".join(item.get("shared_terms", [])[:5]) or "none")}</li>'
        for item in health.get("link_suggestions", [])[:8]
    ) or "<li>当前没有修复候选。</li>"

    empty_state = ""
    if not graph.get("nodes"):
        empty_state = '<div class="empty">当前还没有 machine-memory 节点。先投料并运行 compile，再打开这个页面。</div>'

    svg_body = "\n".join(section_fragments + edge_fragments + node_fragments)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Machine Memory Graph</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: #ffffff; --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1120px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .meta, .cards, .lists { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin: 18px 0 24px; }",
            "    .card, .panel { background: rgba(255,255,255,0.92); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .canvas { overflow-x: auto; }",
            "    svg { width: 100%; min-width: 1020px; height: auto; display: block; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--muted); }",
            "    .legend span::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 999px; margin-right: 6px; vertical-align: -1px; }",
            "    .legend .source::before { background: #0f766e; }",
            "    .legend .concept::before { background: #1d4ed8; }",
            "    .legend .related::before { background: #f59e0b; }",
            "    .empty { padding: 16px; background: #fff7ed; border: 1px solid #fdba74; border-radius: 14px; color: #9a3412; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            "  <section class=\"panel\">",
            "    <h1>Machine Memory Graph</h1>",
            f"    <p>编译时间：<code>{html.escape(str(memory.get('compiled_at', '')))}</code> | 图谱摘要：<code>{html.escape(str(graph.get('digest', '')))}</code></p>",
            "    <p>这是炼丹炉 machine-memory 的本地图谱视图。来源节点与概念节点按连通分量分块展示，直接点击节点可跳回对应的 wiki 页面。</p>",
            "    <div class=\"meta\">",
            *[f'      <div class="card"><div class="metric">{html.escape(item.split()[-1])}</div><div class="metric-label">{html.escape(" ".join(item.split()[:-1]) or item)}</div></div>' for item in summary_items],
            "    </div>",
            "    <div class=\"legend\">",
            '      <span class="source">source</span>',
            '      <span class="concept">concept</span>',
            '      <span class="related">related edge</span>',
            "    </div>",
            "  </section>",
            f"  {empty_state}",
            "  <section class=\"panel canvas\">",
            f'    <svg viewBox="0 0 1020 {view_height}" role="img" aria-label="machine memory graph">',
            f"{svg_body}",
            "    </svg>",
            "  </section>",
            "  <section class=\"lists\">",
            '    <div class="panel"><h2>Hub 概念</h2><ul>',
            f"{hub_concept_items}",
            "    </ul></div>",
            '    <div class="panel"><h2>Hub 来源</h2><ul>',
            f"{hub_source_items}",
            "    </ul></div>",
            '    <div class="panel"><h2>修复候选</h2><ul>',
            f"{suggestion_items}",
            "    </ul></div>",
            "  </section>",
            '  <section class="panel"><h2>相关入口</h2><ul>',
            '    <li><a href="../../wiki/indexes/graph-view.md">Graph View Dashboard</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory.md">机器记忆</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-topology.md">机器记忆拓扑</a></li>',
            '    <li><a href="../../wiki/indexes/graph-health.md">图谱健康</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>',
            "  </ul></section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def build_machine_memory_adjacency(memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    adjacency: dict[str, dict[str, str]] = {}
    for node in memory.get("source_nodes", []):
        adjacency.setdefault(f"source:{node['id']}", {})
    for node in memory.get("concept_nodes", []):
        adjacency.setdefault(f"concept:{node['slug']}", {})
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_key = f"source:{edge['source_id']}"
        concept_key = f"concept:{edge['concept_slug']}"
        adjacency.setdefault(source_key, {})[concept_key] = "HAS_CONCEPT"
        adjacency.setdefault(concept_key, {})[source_key] = "HAS_CONCEPT"
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_key = f"concept:{edge['from']}"
        right_key = f"concept:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = "RELATED_CONCEPT"
        adjacency.setdefault(right_key, {})[left_key] = "RELATED_CONCEPT"
    return adjacency


def build_machine_memory_query(memory: dict[str, Any], question: str) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)

    direct_source_scores: dict[str, int] = {}
    direct_concept_scores: dict[str, int] = {}
    matched_terms: list[str] = []

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    related_concepts: dict[str, set[str]] = {}
    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        related_concepts.setdefault(left, set()).add(right)
        related_concepts.setdefault(right, set()).add(left)

    for token in question_tokens:
        payload = term_index.get(token)
        if not isinstance(payload, dict):
            continue
        matched_terms.append(token)
        for source_id in payload.get("source_ids", []):
            if source_id in source_nodes:
                direct_source_scores[source_id] = direct_source_scores.get(source_id, 0) + 3
        for concept_slug in payload.get("concept_slugs", []):
            if concept_slug in concept_nodes:
                direct_concept_scores[concept_slug] = direct_concept_scores.get(concept_slug, 0) + 4

    expanded_source_scores = dict(direct_source_scores)
    expanded_concept_scores = dict(direct_concept_scores)
    supporting_edges: set[tuple[str, str, str]] = set()

    for source_id in list(direct_source_scores):
        for concept_slug in sorted(source_to_concepts.get(source_id, set())):
            expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))

    for concept_slug in list(direct_concept_scores):
        for source_id in sorted(concept_to_sources.get(concept_slug, set())):
            expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))
        for related_slug in sorted(related_concepts.get(concept_slug, set())):
            expanded_concept_scores[related_slug] = expanded_concept_scores.get(related_slug, 0) + 1
            supporting_edges.add(("RELATED_CONCEPT", concept_slug, related_slug))
            for source_id in sorted(concept_to_sources.get(related_slug, set())):
                expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 1
                supporting_edges.add(("HAS_CONCEPT", source_id, related_slug))

    query_routes = build_machine_memory_query_routes(
        memory,
        adjacency,
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    for route in query_routes:
        for node in route["nodes"]:
            if node["kind"] == "source":
                expanded_source_scores[node["id"]] = expanded_source_scores.get(node["id"], 0) + 2
            else:
                expanded_concept_scores[node["slug"]] = expanded_concept_scores.get(node["slug"], 0) + 2
        for edge in route["edges"]:
            if edge["type"] == "HAS_CONCEPT":
                supporting_edges.add(("HAS_CONCEPT", edge["left"], edge["right"]))
            elif edge["type"] == "RELATED_CONCEPT":
                supporting_edges.add(("RELATED_CONCEPT", edge["left"], edge["right"]))

    ranked_source_ids = [
        source_id
        for source_id, _score in sorted(
            expanded_source_scores.items(),
            key=lambda item: (-item[1], source_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    ranked_concept_slugs = [
        concept_slug
        for concept_slug, _score in sorted(
            expanded_concept_scores.items(),
            key=lambda item: (-item[1], concept_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    bridge_concept_slugs = [
        slug for slug in ranked_concept_slugs if slug in set(health.get("bridge_concept_slugs", []))
    ]
    query_subgraph_sources = [
        {
            "id": source_id,
            "title": source_nodes[source_id]["title"],
            "path": source_nodes[source_id]["source_page"],
        }
        for source_id in ranked_source_ids
        if source_id in source_nodes
    ]
    query_subgraph_concepts = [
        {
            "slug": concept_slug,
            "title": concept_nodes[concept_slug]["title"],
            "path": f"wiki/concepts/{concept_slug}.md",
        }
        for concept_slug in ranked_concept_slugs
        if concept_slug in concept_nodes
    ]
    query_subgraph_edges = [
        {"type": edge_type, "left": left, "right": right}
        for edge_type, left, right in sorted(supporting_edges)
        if (edge_type == "HAS_CONCEPT" and left in ranked_source_ids and right in ranked_concept_slugs)
        or (edge_type == "RELATED_CONCEPT" and left in ranked_concept_slugs and right in ranked_concept_slugs)
    ]
    touched_component_ids = sorted(
        {
            component_id
            for component_id in (
                [health.get("source_component_ids", {}).get(source_id) for source_id in ranked_source_ids]
                + [health.get("concept_component_ids", {}).get(slug) for slug in ranked_concept_slugs]
            )
            if component_id
        }
    )
    touched_components = [
        component
        for component in health.get("components", [])
        if component.get("id") in touched_component_ids
    ]
    proposal_by_action_id = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in health.get("repair_plan", {}).get("execution_proposals", [])
        if proposal.get("action_id")
    }
    relevant_actions: list[dict[str, Any]] = []
    ranked_source_set = set(ranked_source_ids) | set(direct_source_scores)
    ranked_concept_set = set(ranked_concept_slugs) | set(direct_concept_scores)
    for action in health.get("actions", []):
        if action.get("status") not in PENDING_ACTION_STATUSES:
            continue
        source_hit = bool(ranked_source_set & set(action.get("source_ids", [])))
        concept_hit = bool(ranked_concept_set & set(action.get("concept_slugs", [])))
        component_hit = bool(action.get("component_id")) and action.get("component_id") in touched_component_ids
        if not (source_hit or concept_hit or component_hit):
            continue
        proposal = proposal_by_action_id.get(str(action.get("id") or ""), {})
        relevant_actions.append(
            {
                "id": action["id"],
                "kind": action["kind"],
                "priority": action["priority"],
                "status": action.get("status", "proposed"),
                "title": action["title"],
                "primary_path": action["primary_path"],
                "secondary_path": action.get("secondary_path", ""),
                "reason": action.get("reason", ""),
                "execution_policy": action.get("execution_policy", "triage"),
                "next_step": action.get("next_step", ""),
                "proposal_kind": proposal.get("proposal_kind", ""),
                "proposal_summary": proposal.get("summary", ""),
                "proposal_targets": proposal.get("target_paths", []),
            }
        )

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs,
        "supporting_edges": [
            {"type": edge_type, "left": left, "right": right}
            for edge_type, left, right in sorted(supporting_edges)
        ],
        "query_routes": query_routes,
        "touched_component_ids": touched_component_ids,
        "touched_components": touched_components,
        "relevant_actions": relevant_actions[:6],
        "query_subgraph": {
            "sources": query_subgraph_sources,
            "concepts": query_subgraph_concepts,
            "edges": query_subgraph_edges,
        },
    }


def build_machine_memory_query_routes(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[dict[str, Any]]:
    anchor_nodes = ranked_machine_memory_anchor_nodes(
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    routes: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, ...]] = set()
    for index, start in enumerate(anchor_nodes):
        for goal in anchor_nodes[index + 1 :]:
            path = shortest_machine_memory_path(adjacency, start, goal)
            if len(path) < 2:
                continue
            route_key = tuple(path)
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)
            routes.append(render_machine_memory_route(memory, adjacency, path))
            if len(routes) >= 4:
                return routes
    return routes


def ranked_machine_memory_anchor_nodes(
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[str]:
    anchors: list[str] = []
    for concept_slug, _score in sorted(direct_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
        anchors.append(f"concept:{concept_slug}")
    for source_id, _score in sorted(direct_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
        anchors.append(f"source:{source_id}")
    if len(anchors) < 2:
        for concept_slug, _score in sorted(expanded_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
            key = f"concept:{concept_slug}"
            if key not in anchors:
                anchors.append(key)
        for source_id, _score in sorted(expanded_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
            key = f"source:{source_id}"
            if key not in anchors:
                anchors.append(key)
    return anchors[:4]


def shortest_machine_memory_path(adjacency: dict[str, dict[str, str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    if start not in adjacency or goal not in adjacency:
        return []
    queue: deque[str] = deque([start])
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency.get(current, {})):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parents:
        return []
    path: list[str] = []
    current: str | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    return list(reversed(path))


def render_machine_memory_route(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    path: list[str],
) -> dict[str, Any]:
    nodes = [machine_memory_node_metadata(memory, node_key) for node_key in path]
    edges: list[dict[str, str]] = []
    for left, right in zip(path, path[1:]):
        edge_type = adjacency.get(left, {}).get(right, "")
        if edge_type == "HAS_CONCEPT":
            if left.startswith("source:"):
                edges.append(
                    {
                        "type": edge_type,
                        "left": left.removeprefix("source:"),
                        "right": right.removeprefix("concept:"),
                    }
                )
            else:
                edges.append(
                    {
                        "type": edge_type,
                        "left": right.removeprefix("source:"),
                        "right": left.removeprefix("concept:"),
                    }
                )
        else:
            edges.append(
                {
                    "type": "RELATED_CONCEPT",
                    "left": left.removeprefix("concept:"),
                    "right": right.removeprefix("concept:"),
                }
            )
    return {
        "start": nodes[0],
        "goal": nodes[-1],
        "length": max(0, len(path) - 1),
        "nodes": nodes,
        "edges": edges,
    }


def machine_memory_node_metadata(memory: dict[str, Any], node_key: str) -> dict[str, Any]:
    if node_key.startswith("source:"):
        source_id = node_key.removeprefix("source:")
        source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
        node = source_nodes.get(source_id, {})
        return {
            "kind": "source",
            "id": source_id,
            "title": node.get("title", source_id),
            "path": node.get("source_page", f"wiki/sources/{source_id}.md"),
        }
    concept_slug = node_key.removeprefix("concept:")
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    node = concept_nodes.get(concept_slug, {})
    return {
        "kind": "concept",
        "slug": concept_slug,
        "title": node.get("title", concept_slug),
        "path": f"wiki/concepts/{concept_slug}.md",
    }


def summarize_machine_memory_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_source_ids = {node["id"] for node in previous.get("source_nodes", [])}
    current_source_ids = {node["id"] for node in current.get("source_nodes", [])}
    previous_concept_slugs = {node["slug"] for node in previous.get("concept_nodes", [])}
    current_concept_slugs = {node["slug"] for node in current.get("concept_nodes", [])}
    previous_terms = set(previous.get("term_index", {}).keys())
    current_terms = set(current.get("term_index", {}).keys())
    previous_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in previous.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in previous.get("edges", {}).get("concept_to_concept", [])
    }
    current_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in current.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in current.get("edges", {}).get("concept_to_concept", [])
    }
    previous_digest = previous.get("digest", "")
    current_digest = current["digest"]
    return {
        "has_previous_snapshot": bool(previous_digest),
        "changed": previous_digest != current_digest,
        "previous_digest": previous_digest,
        "current_digest": current_digest,
        "added_source_ids": sorted(current_source_ids - previous_source_ids),
        "removed_source_ids": sorted(previous_source_ids - current_source_ids),
        "added_concept_slugs": sorted(current_concept_slugs - previous_concept_slugs),
        "removed_concept_slugs": sorted(previous_concept_slugs - current_concept_slugs),
        "added_terms": sorted(current_terms - previous_terms)[:25],
        "removed_terms": sorted(previous_terms - current_terms)[:25],
        "added_edges": len(current_edges - previous_edges),
        "removed_edges": len(previous_edges - current_edges),
    }


def append_machine_memory_history(root: Path, memory: dict[str, Any], transition: dict[str, Any]) -> None:
    path = machine_memory_history_path(root)
    if transition["has_previous_snapshot"] and not transition["changed"]:
        return
    entry = {
        "compiled_at": memory["compiled_at"],
        "digest": memory["digest"],
        "sources": len(memory.get("source_nodes", [])),
        "concepts": len(memory.get("concept_nodes", [])),
        "terms": len(memory.get("term_index", {})),
        "added_source_ids": transition["added_source_ids"],
        "removed_source_ids": transition["removed_source_ids"],
        "added_concept_slugs": transition["added_concept_slugs"],
        "removed_concept_slugs": transition["removed_concept_slugs"],
        "added_edges": transition["added_edges"],
        "removed_edges": transition["removed_edges"],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def render_drift_report(memory: dict[str, Any], transition: dict[str, Any]) -> str:
    drift = memory["drift"]
    lines = [
        "# 漂移报告",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 当前摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 变化摘要",
    ]
    if not transition["has_previous_snapshot"]:
        lines.append("- 目前没有可对比的上一版机器记忆快照。")
    elif not transition["changed"]:
        lines.append("- 相比上一版快照，没有检测到结构性漂移。")
    else:
        lines.extend(
            [
                f"- 上一版摘要：`{transition['previous_digest']}`",
                f"- 新增来源节点：`{len(transition['added_source_ids'])}`",
                f"- 移除来源节点：`{len(transition['removed_source_ids'])}`",
                f"- 新增概念节点：`{len(transition['added_concept_slugs'])}`",
                f"- 移除概念节点：`{len(transition['removed_concept_slugs'])}`",
                f"- 新增边：`{transition['added_edges']}`",
                f"- 移除边：`{transition['removed_edges']}`",
                f"- 新增索引词（样本）：`{', '.join(transition['added_terms']) or 'none'}`",
                f"- 移除索引词（样本）：`{', '.join(transition['removed_terms']) or 'none'}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 当前漂移检查",
            f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
            f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
            f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
            f"- 无概念覆盖的来源：`{len(drift['sources_without_concepts'])}`",
            "",
            "## 机器记忆产物",
            "- 状态文件：`.aiwiki/state/machine-memory.json`",
            "- 图谱导出：`.aiwiki/cache/machine-memory-graph.json`",
            "- 历史记录：`.aiwiki/state/machine-memory-history.jsonl`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_graph_health(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    lines = [
        "# 图谱健康",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 连通分量数：`{health.get('component_count', 0)}`",
        f"- 分量大小：`{', '.join(str(size) for size in health.get('component_sizes', [])) or 'none'}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        "",
        "## 修复信号",
        f"- 孤立来源：`{', '.join(health.get('isolated_source_ids', [])[:10]) or 'none'}`",
        f"- 单节点概念：`{', '.join(health.get('singleton_concept_slugs', [])[:10]) or 'none'}`",
        f"- 桥接概念：`{', '.join(health.get('bridge_concept_slugs', [])[:10]) or 'none'}`",
        f"- 过载概念：`{', '.join(health.get('overloaded_concept_slugs', [])[:10]) or 'none'}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        "",
        "## 最大分量",
    ]
    components = health.get("components", [])
    if not components:
        lines.append("- 暂无分量数据。")
    else:
        for component in components[:5]:
            lines.append(
                f"- `{component['id']}` size `{component['size']}`"
                f" | sources `{', '.join(component.get('source_ids', [])[:4]) or 'none'}`"
                f" | concepts `{', '.join(component.get('concept_slugs', [])[:4]) or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 相关链接",
        "- [机器记忆](./machine-memory.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [审阅队列](./review-queue.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_index(memory: dict[str, Any]) -> str:
    concept_nodes = memory["concept_nodes"]
    edges = memory["edges"]
    drift = memory["drift"]
    health = memory.get("health", {})
    lines = [
        "# 机器记忆",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        "- 运行时状态文件：`.aiwiki/state/machine-memory.json`",
        "- 图谱导出文件：`.aiwiki/cache/machine-memory-graph.json`",
        "- 漂移报告：`wiki/indexes/drift-report.md`",
        f"- 来源节点：`{len(memory['source_nodes'])}`",
        f"- 概念节点：`{len(concept_nodes)}`",
        f"- 来源到概念的边：`{len(edges['source_to_concept'])}`",
        f"- 概念到概念的边：`{len(edges['concept_to_concept'])}`",
        f"- 索引词数量：`{len(memory['term_index'])}`",
        f"- 机器摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 图谱健康",
        f"- 连通分量：`{health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 已索引分量：`{len(health.get('components', []))}`",
        f"- Hub 概念：`{len(health.get('hub_concepts', []))}`",
        f"- Hub 来源：`{len(health.get('hub_sources', []))}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        f"- 概念冲突信号：`{health.get('concept_quality', {}).get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念重写候选：`{health.get('concept_quality', {}).get('counts', {}).get('rewrite_candidates', 0)}`",
        "",
        "## 判断层",
        "- 决策索引：`wiki/indexes/decisions.md`",
        "- 判断索引：`wiki/indexes/judgments.md`",
        "- 审阅队列：`wiki/indexes/review-queue.md`",
        "",
        "## 漂移摘要",
        f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
        f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
        f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
        f"- 无概念覆盖来源：`{len(drift['sources_without_concepts'])}`",
        "",
        "## 相关链接",
        "- [图谱健康](./graph-health.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [概念质量](./concept-quality.md)",
        "",
        "## Action Workflow",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "- 通过 `review-action` 推进 action status。",
        "- nightly 会继续追踪 action 的 occurrences、aging 和 escalation。",
        "- repair 计划页：`wiki/indexes/machine-memory-repair-plan.md`",
        "",
        "## 查询加速",
        "- `ask` 和 `run-ask` 先用机器记忆 term index 做第一轮查询规划。",
        "- source-to-concept 和 concept-to-concept 边会在组装 prompt 前扩展候选范围。",
        "- 查询规划还会提取最短图路径和触达分量，支持更深的检索。",
        "- 图谱导出主要给 agent / tooling 使用，不建议直接人工修改。",
        "",
        "## 重点概念",
    ]
    if not concept_nodes:
        lines.append("- 还没有编译出概念节点。")
    else:
        for node in sorted(
            concept_nodes,
            key=lambda item: (-len(item["source_pages"]), item["title"].lower()),
        )[:10]:
            lines.append(
                f"- [{node['title']}](../concepts/{node['slug']}.md) "
                f"({len(node['source_pages'])} source(s), {len(node['related_slugs'])} related concept(s))"
            )
    lines.extend(
        [
            "",
            "## 运行时规则",
            "- [规则索引](../../schema/index.md)",
            "- [引用规则](../../schema/citations.md)",
            "- [冲突规则](../../schema/conflicts.md)",
            "- [审阅规则](../../schema/review.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_topology(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    hub_concepts = health.get("hub_concepts", [])
    hub_sources = health.get("hub_sources", [])
    link_suggestions = health.get("link_suggestions", [])
    lines = [
        "# 机器记忆拓扑",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 已索引分量：`{health.get('component_count', 0)}`",
        f"- Hub 概念：`{len(hub_concepts)}`",
        f"- Hub 来源：`{len(hub_sources)}`",
        f"- 修复候选：`{len(link_suggestions)}`",
        "",
        "## Hub 概念",
    ]
    if not hub_concepts:
        lines.append("- 当前没有可展示的 hub 概念。")
    else:
        for item in hub_concepts[:10]:
            lines.append(
                f"- [{item['title']}](../concepts/{item['slug']}.md)"
                f" | sources `{item['source_count']}`"
                f" | related `{item['related_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## Hub 来源"])
    if not hub_sources:
        lines.append("- 当前没有可展示的 hub 来源。")
    else:
        for item in hub_sources[:10]:
            lines.append(
                f"- [{item['title']}](../sources/{item['id']}.md)"
                f" | concepts `{item['concept_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## 修复候选"])
    if not link_suggestions:
        lines.append("- 当前没有机器记忆修复候选。")
    else:
        for suggestion in link_suggestions[:10]:
            lines.append(
                f"- [{suggestion['source_title']}](../sources/{suggestion['source_id']}.md)"
                f" -> [{suggestion['concept_title']}](../concepts/{suggestion['concept_slug']}.md)"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    lines.extend(["", "## Mermaid 拓扑切片", "```mermaid", "graph LR"])
    node_lines: list[str] = []
    edge_lines: list[str] = []
    added_nodes: set[str] = set()
    hub_concept_slugs = {item["slug"] for item in hub_concepts[:5]}
    hub_source_ids = {item["id"] for item in hub_sources[:5]}
    concept_by_slug = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    source_by_id = {node["id"]: node for node in memory.get("source_nodes", [])}
    for source_id in sorted(hub_source_ids):
        node = source_by_id.get(source_id)
        if not node:
            continue
        node_key = f"src_{slugify(source_id).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["S: {label}"]')
    for concept_slug in sorted(hub_concept_slugs):
        node = concept_by_slug.get(concept_slug)
        if not node:
            continue
        node_key = f"concept_{slugify(concept_slug).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["C: {label}"]')
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if source_id not in hub_source_ids or concept_slug not in hub_concept_slugs:
            continue
        left = f"src_{slugify(source_id).replace('-', '_')}"
        right = f"concept_{slugify(concept_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} --> {right}")
    seen_related_pairs: set[tuple[str, str]] = set()
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_slug = edge.get("from")
        right_slug = edge.get("to")
        if left_slug not in hub_concept_slugs or right_slug not in hub_concept_slugs:
            continue
        pair = tuple(sorted((str(left_slug), str(right_slug))))
        if pair in seen_related_pairs:
            continue
        seen_related_pairs.add(pair)
        left = f"concept_{slugify(left_slug).replace('-', '_')}"
        right = f"concept_{slugify(right_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} -.-> {right}")
    if not node_lines:
        lines.append('    placeholder["Not enough machine-memory nodes yet"]')
    else:
        lines.extend(node_lines)
        lines.extend(edge_lines[:18])
    lines.extend(
        [
            "```",
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [概念质量](./concept-quality.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_actions(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    actions = health.get("actions", [])
    inactive_actions = health.get("inactive_actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    counts = health.get("action_counts", {})
    by_priority = counts.get("by_priority", {})
    by_status = counts.get("by_status", {})
    kind_labels = {
        "add-source-concept-link": "补链动作",
        "connect-isolated-source": "孤立来源动作",
        "expand-singleton-concept": "单节点概念动作",
        "split-overloaded-concept": "过载概念动作",
        "monitor-bridge-concept": "桥接概念观察",
    }
    lines = [
        "# 机器记忆动作队列",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 动作总数：`{counts.get('total', 0)}`",
        f"- 高优先级：`{by_priority.get('high', 0)}`",
        f"- 中优先级：`{by_priority.get('medium', 0)}`",
        f"- 低优先级：`{by_priority.get('low', 0)}`",
        f"- 已到期：`{counts.get('overdue', 0)}`",
        f"- 已升级：`{counts.get('escalated', 0)}`",
        f"- 已清除：`{counts.get('inactive', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## 状态分布",
    ]
    for status in ACTION_STATUSES:
        lines.append(f"- `{display_action_status(status)}`：`{by_status.get(status, 0)}`")
    lines.extend(
        [
            "",
            "## 已升级动作",
        ]
    )
    if not escalated_actions:
        lines.append("- 当前没有需要升级处理的动作。")
    else:
        for action in escalated_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 已到期动作",
        ]
    )
    if not overdue_actions:
        lines.append("- 当前没有已到期待处理的动作。")
    else:
        for action in overdue_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 优先队列",
        ]
    )
    if not actions:
        lines.append("- 当前没有 machine-memory 动作。")
    else:
        for action in actions[:12]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
                f" | component `{action.get('component_id') or 'none'}`"
            )
    for kind, label in kind_labels.items():
        lines.extend(["", f"## {label}"])
        kind_actions = [action for action in actions if action.get("kind") == kind]
        if not kind_actions:
            lines.append("- 当前没有此类动作。")
            continue
        for action in kind_actions[:8]:
            paths = [f"primary `{action['primary_path']}`"]
            if action.get("secondary_path"):
                paths.append(f"secondary `{action['secondary_path']}`")
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | {' | '.join(paths)}"
                f" | first `{action.get('first_seen_at', '') or 'none'}`"
                f" | seen `{action.get('occurrences', 0)}`"
                f" | {action.get('reason', '') or 'no reason'}"
            )
    lines.extend(["", "## 最近清除"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除的动作。")
    else:
        for action in inactive_actions[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | last_seen `{action.get('last_seen_at', '') or 'none'}`"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [拓扑视图](./machine-memory-topology.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_repair_plan(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    counts = plan.get("counts", {})
    ready_actions = plan.get("ready_actions", [])
    triage_actions = plan.get("triage_actions", [])
    deferred_actions = plan.get("deferred_actions", [])
    inactive_actions = plan.get("inactive_actions", [])
    execution_batches = plan.get("execution_batches", [])
    execution_proposals = plan.get("execution_proposals", [])
    lines = [
        "# 机器记忆修复计划",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- Ready 动作：`{counts.get('ready', 0)}`",
        f"- 待分流动作：`{counts.get('triage', 0)}`",
        f"- 暂缓动作：`{counts.get('deferred', 0)}`",
        f"- 最近清除：`{counts.get('inactive', 0)}`",
        f"- 执行批次：`{counts.get('batches', 0)}`",
        f"- 执行提案：`{counts.get('proposals', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## Ready Now",
    ]
    if not ready_actions:
        lines.append("- 当前没有 ready action。")
    else:
        for action in ready_actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Need Triage"])
    if not triage_actions:
        lines.append("- 当前没有待分流动作。")
    else:
        for action in triage_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Deferred"])
    if not deferred_actions:
        lines.append("- 当前没有暂缓动作。")
    else:
        for action in deferred_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
                f"{command_part}"
            )
    lines.extend(["", "## Execution Batches"])
    if not execution_batches:
        lines.append("- 当前没有可执行批次。")
    else:
        for batch in execution_batches[:8]:
            lines.append(
                f"- {batch['label']}"
                f" | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
            for action in batch.get("actions", [])[:4]:
                command_hint = action.get("command_hint", "")
                command_part = f" | command `{command_hint}`" if command_hint else ""
                lines.append(
                    f"  action [{action['priority']}] {action['title']}"
                    f" | status `{display_action_status(str(action.get('status')))}`"
                    f" | next {action.get('next_step', 'n/a')}"
                    f"{command_part}"
                )
    lines.extend(["", "## Execution Proposals"])
    if not execution_proposals:
        lines.append("- 当前没有页级执行提案。")
    else:
        for proposal in execution_proposals[:10]:
            command_part = f" | command `{proposal['command_hint']}`" if proposal.get("command_hint") else ""
            lines.append(
                f"- [{proposal['priority']}] {proposal['title']}"
                f" | status `{display_action_status(str(proposal.get('status')))}`"
                f" | kind `{proposal.get('proposal_kind', 'manual-repair')}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f"{command_part}"
            )
            lines.append(f"  - strategy: {proposal.get('summary', 'n/a')}")
            for edit in proposal.get("suggested_edits", [])[:3]:
                lines.append(f"  - edit: {edit}")
    lines.extend(["", "## Recently Cleared"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除动作。")
    else:
        for action in inactive_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [动作队列](./machine-memory-actions.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_concept_quality(memory: dict[str, Any]) -> str:
    quality = memory.get("health", {}).get("concept_quality", {})
    counts = quality.get("counts", {})
    weak_concepts = quality.get("weak_concepts", [])
    stable_concepts = quality.get("stable_concepts", [])
    merge_candidates = quality.get("merge_candidates", [])
    rewrite_candidates = quality.get("rewrite_candidates", [])
    conflict_signals = quality.get("conflict_signals", [])
    gap_signals = quality.get("gap_signals", [])
    lines = [
        "# 概念质量",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 弱概念页：`{counts.get('weak', 0)}`",
        f"- 稳定概念页：`{counts.get('stable', 0)}`",
        f"- 占位概念页：`{counts.get('placeholders', 0)}`",
        f"- 合并候选：`{counts.get('merge_candidates', 0)}`",
        f"- 重写候选：`{counts.get('rewrite_candidates', 0)}`",
        f"- 冲突信号：`{counts.get('conflict_signals', 0)}`",
        f"- 证据缺口：`{counts.get('gap_signals', 0)}`",
        "",
        "## Rewrite Now",
    ]
    if not weak_concepts:
        lines.append("- 当前没有需要立即重写的概念页。")
    else:
        for concept in weak_concepts[:12]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
            )
    lines.extend(["", "## Rewrite Priority"])
    if not rewrite_candidates:
        lines.append("- 当前没有新的重写候选。")
    else:
        for candidate in rewrite_candidates[:10]:
            lines.append(
                f"- [{candidate['title']}](../concepts/{candidate['slug']}.md)"
                f" | priority `{candidate.get('priority', 'n/a')}`"
                f" | score `{candidate.get('score', 0)}`"
                f" | issues `{', '.join(candidate.get('issues', [])) or 'none'}`"
            )
            lines.append(f"  - strategy: {candidate.get('rewrite_strategy', 'n/a')}")
    lines.extend(["", "## Conflict Signals"])
    if not conflict_signals:
        lines.append("- 当前没有显式概念冲突信号。")
    else:
        for signal in conflict_signals[:10]:
            lines.append(
                f"- [{signal['title']}](../concepts/{signal['slug']}.md)"
                f" | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    lines.extend(["", "## Evidence Gaps"])
    if not gap_signals:
        lines.append("- 当前没有显式证据缺口。")
    else:
        for gap in gap_signals[:10]:
            lines.append(
                f"- [{gap['title']}](../concepts/{gap['slug']}.md)"
                f" | kind `{gap.get('kind', 'n/a')}`"
                f" | source `{gap.get('path', 'n/a')}`"
                f" | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
            )
    lines.extend(["", "## Merge Candidates"])
    if not merge_candidates:
        lines.append("- 当前没有明显的概念合并候选。")
    else:
        for candidate in merge_candidates[:10]:
            lines.append(
                f"- [{candidate['left_title']}](../concepts/{candidate['left_slug']}.md)"
                f" <-> [{candidate['right_title']}](../concepts/{candidate['right_slug']}.md)"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    lines.extend(["", "## Stable Concepts"])
    if not stable_concepts:
        lines.append("- 当前还没有稳定概念页。")
    else:
        for concept in stable_concepts[:10]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [概念索引](./concepts.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def compile_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    compiled_at = utc_now()
    previous_memory = load_json_document(machine_memory_state_path(root))
    changed_pages = 0
    previews: dict[str, str] = {}
    existing_pages: dict[str, str] = {}
    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file)
        previews[entry["id"]] = preview
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        existing_pages[entry["id"]] = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
    concepts, entry_terms = build_concept_records(root, entries, previews)
    for entry in entries:
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        content = render_source_page_with_state(
            entry,
            previews[entry["id"]],
            compiled_at,
            concepts=entry_terms.get(entry["id"], []),
            existing_page=existing_pages[entry["id"]],
        )
        changed_pages += int(write_if_changed(destination, content))

    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "sources.md", render_sources_index(entries, compiled_at))
    )
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "concepts.md", render_concepts_index(concepts, compiled_at))
    )
    decision_pages = collect_curated_pages(root, "decisions", "decision")
    judgment_pages = collect_curated_pages(root, "judgments", "judgment")
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "decisions.md",
            render_curated_index("决策索引", "决策列表", decision_pages, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "judgments.md",
            render_curated_index("判断索引", "判断列表", judgment_pages, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "review-queue.md",
            render_review_queue(decision_pages, judgment_pages, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(
            aging_report_path(root),
            render_aging_report(decision_pages, judgment_pages, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(entries, concepts, decision_pages, judgment_pages, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "index.md",
            render_master_index(entries, concepts, decision_pages, judgment_pages, compiled_at),
        )
    )
    ensure_wiki_log(root)

    concept_lookup = {record["slug"]: record for record in concepts}
    for record in concepts:
        record["record_lookup"] = concept_lookup
        destination = root / "wiki" / "concepts" / f"{record['slug']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        changed_pages += int(write_if_changed(destination, render_concept_page(record, compiled_at, existing_page)))

    removed_pages = remove_stale_generated_concept_pages(root, {record["slug"] for record in concepts})
    memory = build_machine_memory(root, entries, concepts, previews, entry_terms, compiled_at)
    memory["health"] = build_machine_memory_health(memory)
    memory["health"].update(reconcile_machine_memory_actions(root, memory["health"], compiled_at=compiled_at))
    memory["health"]["repair_plan"] = build_machine_memory_repair_plan(memory["health"])
    memory["health"]["concept_quality"] = build_concept_quality(root, memory)
    memory["digest"] = machine_memory_digest(memory)
    graph = build_machine_memory_graph(memory)
    memory["graph_digest"] = graph["digest"]
    memory["graph_path"] = relative_path(root, machine_memory_graph_path(root))
    memory["history_path"] = relative_path(root, machine_memory_history_path(root))
    transition = summarize_machine_memory_transition(previous_memory, memory)
    memory["transition"] = transition
    changed_pages += int(
        write_if_changed(machine_memory_state_path(root), json.dumps(memory, indent=2, sort_keys=True) + "\n")
    )
    changed_pages += int(write_if_changed(machine_memory_graph_path(root), json.dumps(graph, indent=2, sort_keys=True) + "\n"))
    changed_pages += int(
        write_if_changed(machine_memory_graph_html_path(root), render_machine_memory_graph_html(memory, graph))
    )
    append_machine_memory_history(root, memory, transition)
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "machine-memory.md", render_machine_memory_index(memory))
    )
    changed_pages += int(
        write_if_changed(machine_memory_topology_path(root), render_machine_memory_topology(memory))
    )
    changed_pages += int(
        write_if_changed(machine_memory_actions_path(root), render_machine_memory_actions(memory))
    )
    changed_pages += int(
        write_if_changed(machine_memory_repair_plan_path(root), render_machine_memory_repair_plan(memory))
    )
    changed_pages += int(write_if_changed(concept_quality_path(root), render_concept_quality(memory)))
    changed_pages += int(write_if_changed(graph_health_report_path(root), render_graph_health(memory)))
    changed_pages += int(write_if_changed(machine_memory_drift_report_path(root), render_drift_report(memory, transition)))
    append_wiki_log(
        root,
        "compile",
        "wiki refresh",
        [
            f"compiled_at: `{compiled_at}`",
            f"source_pages: `{len(entries)}`",
            f"concept_pages: `{len(concepts)}`",
            f"machine_memory_terms: `{len(memory['term_index'])}`",
            f"graph_components: `{memory['health']['component_count']}`",
            f"machine_memory_changed: `{transition['changed']}`",
            f"changed_pages: `{changed_pages}`",
            f"removed_concept_pages: `{removed_pages}`",
        ],
    )

    return {
        "compiled_at": compiled_at,
        "sources": len(entries),
        "concepts": len(concepts),
        "machine_memory_terms": len(memory["term_index"]),
        "machine_memory_changed": transition["changed"],
        "changed_pages": changed_pages,
    }


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def rank_concepts(root: Path, question: str, boost_concept_slugs: set[str] | None = None) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        title = frontmatter.get("title") or path.stem
        haystack = f"{title}\n{strip_frontmatter(content)}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        if path.stem in boost_concept_slugs:
            score += 5
        if score:
            ranked.append(
                (
                    score,
                    {
                        "slug": path.stem,
                        "title": str(title),
                        "path": relative_path(root, path),
                        "source_pages": frontmatter.get("source_pages", []),
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [item for _score, item in ranked[:5]]


def source_page_is_stale(root: Path, entry: dict[str, Any]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    return compiled_source_sha(page.read_text(encoding="utf-8", errors="replace")) != entry["sha256"]


def wiki_requires_compile(root: Path, entries: list[dict[str, Any]]) -> bool:
    if not entries:
        return False
    if not (root / "wiki" / "indexes" / "index.md").exists():
        return True
    if not (root / "wiki" / "indexes" / "review-queue.md").exists():
        return True
    if any(source_page_is_stale(root, entry) for entry in entries):
        return True
    concept_dir = root / "wiki" / "concepts"
    return not any(concept_dir.glob("*.md"))


def rank_sources(
    root: Path,
    entries: list[dict[str, Any]],
    question: str,
    boost_source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    boost_source_ids = boost_source_ids or set()
    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file, limit_lines=8)
        summary_or_preview = source_summary_or_preview(root, entry, preview)
        haystack = " ".join([entry["title"], summary_or_preview]).lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        for concept in entry_concept_terms(entry, summary_or_preview, max_terms=4):
            for token in question_tokens:
                score += concept.lower().count(token)
        if entry["id"] in boost_source_ids:
            score += 5
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [entry for _score, entry in scored[:5]]


def render_report(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "report",
            "query": question,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {question}",
        "",
        "## 回答约束",
        "- 所有重要结论都要落回 `wiki/sources/*.md`。",
        "- 有不确定性就直接写出来，不要补洞。",
        "- 优先使用文件路径引用，而不是模糊转述。",
        "",
        "## 推荐索引页",
        "- [知识库总索引](../../wiki/indexes/index.md)",
        "- [来源索引](../../wiki/indexes/sources.md)",
        "- [概念索引](../../wiki/indexes/concepts.md)",
        "- [决策索引](../../wiki/indexes/decisions.md)",
        "- [判断索引](../../wiki/indexes/judgments.md)",
        "- [审阅队列](../../wiki/indexes/review-queue.md)",
        "- [审阅中心](../../wiki/indexes/review-center.md)",
        "- [Aging 报告](../../wiki/indexes/aging-report.md)",
        "- [概念质量](../../wiki/indexes/concept-quality.md)",
        "- [机器记忆](../../wiki/indexes/machine-memory.md)",
        "- [图谱视图](../../wiki/indexes/graph-view.md)",
        "- [拓扑视图](../../wiki/indexes/machine-memory-topology.md)",
        "- [动作队列](../../wiki/indexes/machine-memory-actions.md)",
        "- [修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
        "- [图谱健康](../../wiki/indexes/graph-health.md)",
        "- [漂移报告](../../wiki/indexes/drift-report.md)",
        "- [修复待办](../../wiki/indexes/repair-backlog.md)",
        "- [运行时规则](../../schema/index.md)",
        "",
        "## 机器记忆查询计划",
    ]
    matched_terms = machine_query.get("matched_terms", [])
    if matched_terms:
        lines.append(f"- 命中词：`{', '.join(matched_terms)}`")
    else:
        lines.append("- 当前还没有直接命中的机器记忆词。")
    lines.append(
        f"- 提升权重的来源候选：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`"
    )
    lines.append(
        f"- 提升权重的概念候选：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`"
    )
    lines.append(
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`"
    )
    lines.append(
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`"
    )
    lines.append(f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`")
    lines.append(f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`")
    lines.append(f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`")
    lines.extend(
        [
            "",
        "## 推荐概念",
        ]
    )
    if not concepts:
        lines.append("- 还没有排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
        "## 推荐来源",
        ]
    )
    if not entries:
        lines.append("- 还没有排好序的来源。先在 ingest 后运行 `aiwiki compile`。")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
            "## 草稿提纲",
            "1. 重新表述研究问题。",
            "2. 对比最强相关来源。",
            "3. 写出分歧、证据缺口和下一步问题。",
            "",
            "## 引用要求",
            "- 在最终答案里加入 source-page 内联引用。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_slides(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    lines = [
        "---",
        "marp: true",
        f"title: {render_scalar(question)}",
        f"description: {render_scalar(f'Generated at {created_at}')}",
        "---",
        "",
        f"# {question}",
        "",
        "## 使用说明",
        "- 把排好序的来源页整理成 5 到 7 页幻灯片。",
        "- 每页正文都保留引用。",
        "",
        "## 相关索引",
        "- `wiki/indexes/index.md`",
        "- `wiki/indexes/sources.md`",
        "- `wiki/indexes/concepts.md`",
        "- `wiki/indexes/decisions.md`",
        "- `wiki/indexes/judgments.md`",
        "- `wiki/indexes/review-queue.md`",
        "- `wiki/indexes/review-center.md`",
        "- `wiki/indexes/aging-report.md`",
        "- `wiki/indexes/concept-quality.md`",
        "- `wiki/indexes/machine-memory.md`",
        "- `wiki/indexes/graph-view.md`",
        "- `wiki/indexes/machine-memory-topology.md`",
        "- `wiki/indexes/machine-memory-actions.md`",
        "- `wiki/indexes/machine-memory-repair-plan.md`",
        "- `wiki/indexes/graph-health.md`",
        "- `wiki/indexes/drift-report.md`",
        "- `wiki/indexes/repair-backlog.md`",
        "- `schema/index.md`",
        "",
        "## 机器记忆查询计划",
        f"- 命中词：`{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- 提升权重的来源：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- 提升权重的概念：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`",
        f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`",
        "",
        "## 相关概念",
    ]
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- `{concept['path']}`")
    lines.extend(
        [
            "",
        "## 相关来源",
        ]
    )
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        for entry in entries:
            lines.append(f"- `wiki/sources/{entry['id']}.md`")
    lines.extend(
        [
            "",
            "---",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
            "# 结论",
            "",
            "- 用有依据的内容替换这一页。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_figure_brief(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "figure",
            "query": question,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# 图表简报：{question}",
        "",
        "## 目标",
        "- 描述这张图应该表达什么。",
        "",
        "## 推荐索引页",
        "- [知识库总索引](../../wiki/indexes/index.md)",
        "- [来源索引](../../wiki/indexes/sources.md)",
        "- [概念索引](../../wiki/indexes/concepts.md)",
        "- [决策索引](../../wiki/indexes/decisions.md)",
        "- [判断索引](../../wiki/indexes/judgments.md)",
        "- [审阅队列](../../wiki/indexes/review-queue.md)",
        "- [审阅中心](../../wiki/indexes/review-center.md)",
        "- [Aging 报告](../../wiki/indexes/aging-report.md)",
        "- [概念质量](../../wiki/indexes/concept-quality.md)",
        "- [机器记忆](../../wiki/indexes/machine-memory.md)",
        "- [图谱视图](../../wiki/indexes/graph-view.md)",
        "- [拓扑视图](../../wiki/indexes/machine-memory-topology.md)",
        "- [动作队列](../../wiki/indexes/machine-memory-actions.md)",
        "- [修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
        "- [图谱健康](../../wiki/indexes/graph-health.md)",
        "- [漂移报告](../../wiki/indexes/drift-report.md)",
        "- [修复待办](../../wiki/indexes/repair-backlog.md)",
        "- [运行时规则](../../schema/index.md)",
        "",
        "## 机器记忆查询计划",
        f"- 命中词：`{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- 提升权重的来源：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- 提升权重的概念：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`",
        f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`",
        "",
        "## 推荐概念",
    ]
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
        "## 推荐来源",
        ]
    )
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
            "## 制图要求",
            "- 写明图表类型。",
            "- 列出变量或对比维度。",
            "- 在图注里包含 source-page 引用。",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
        ]
    )
    return "\n".join(lines) + "\n"


def ask_question(root: Path, question: str, output_format: str) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    machine_query = build_machine_memory_query(load_machine_memory(root), question)
    ranked_concepts = rank_concepts(root, question, boost_concept_slugs=set(machine_query["ranked_concept_slugs"]))
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_seed = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    elif output_format == "slides":
        directory = root / "output" / "slides"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_slides(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    elif output_format == "figure":
        directory = root / "output" / "figures"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_figure_brief(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.write_text(content, encoding="utf-8")
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{relative_path(root, destination)}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
        ],
    )
    return {
        "path": relative_path(root, destination),
        "format": output_format,
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/aging-report.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/machine-memory-topology.md",
            "wiki/indexes/machine-memory-actions.md",
            "wiki/indexes/machine-memory-repair-plan.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/log.md",
            "schema/index.md",
        ],
    }


def file_back(root: Path, artifact: str, title: str | None = None, kind: str = "derived") -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(artifact)
    artifact_path = candidate if candidate.is_absolute() else (root / candidate)
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")
    if kind not in {"derived", "decision", "judgment"}:
        raise ValueError(f"Unsupported filed-back kind: {kind}")

    filed_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    entry_seed = f"{kind}-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(kind, default_curated_status(kind), filed_at)
    frontmatter = render_frontmatter(
        {
            "id": entry_id,
            "kind": kind,
            "status": default_curated_status(kind),
            "title": title or artifact_path.stem,
            "source_files": [artifact_ref],
            "citations": [],
            "generated_by": "aiwiki-file-back",
            "last_compiled_at": filed_at,
            "confidence": "medium",
            "reviewed_at": "",
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
        }
    )
    stripped = strip_frontmatter(original).strip()
    if kind == "derived":
        body_lines = [
            f"# {title or artifact_path.stem}",
            "",
            "## Origin",
            f"- Filed from: `{artifact_ref}`",
            f"- Filed at: `{filed_at}`",
            "",
            "## Filed Content",
            stripped,
        ]
    elif kind == "decision":
        body_lines = [
            f"# {title or artifact_path.stem}",
            "",
            "## Origin",
            f"- Filed from: `{artifact_ref}`",
            f"- Filed at: `{filed_at}`",
            "",
            "## Decision",
            "- State the concrete decision here.",
            "",
            "## Why",
            "- Summarize the rationale and tradeoffs.",
            "",
            "## Evidence",
            f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
            "",
            "## Risks And Revisit",
            "- Record what could invalidate this decision and when to revisit it.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            "",
            "## Review Status",
            "- Current status: `proposed`",
            "- Review this page when the decision is approved, superseded, or needs revisit.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            "",
            "## Supporting Artifact",
            stripped,
        ]
    else:
        body_lines = [
            f"# {title or artifact_path.stem}",
            "",
            "## Origin",
            f"- Filed from: `{artifact_ref}`",
            f"- Filed at: `{filed_at}`",
            "",
            "## Judgment",
            "- State the judgment call here.",
            "",
            "## Signals",
            f"- Summarize the signals from `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence.",
            "",
            "## Counterevidence",
            "- Record what could make this judgment wrong.",
            "",
            "## Confidence And Follow-up",
            "- Keep confidence explicit and list what to watch next.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the judgment is confirmed, rejected, or moved to active tracking.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            "",
            "## Supporting Artifact",
            stripped,
        ]
    payload = "\n".join([frontmatter, "", *body_lines]).rstrip() + "\n"
    destination.write_text(payload, encoding="utf-8")
    append_wiki_log(
        root,
        "file-back",
        title or artifact_path.stem,
        [
            f"kind: `{kind}`",
            f"from: `{artifact_ref}`",
            f"destination: `{relative_path(root, destination)}`",
        ],
    )
    return {"path": relative_path(root, destination)}


def review_machine_memory_action(
    root: Path,
    action_id: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in ACTION_STATUSES:
        raise ValueError(f"Unsupported machine-memory action status: {status}")
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["status_updated_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if action_needs_review(status) else "false"
    if status in PENDING_ACTION_STATUSES:
        revisit_after, escalate_after = schedule_review_windows("action", status, reviewed_at)
    else:
        revisit_after, escalate_after = "", ""
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})
    append_wiki_log(
        root,
        "action-review",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"status: `{status}`",
            f"primary: `{target.get('primary_path', '')}`",
            f"priority: `{target.get('priority', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": status,
        "reviewed_at": reviewed_at,
        "active": bool(target.get("active", True)),
    }


def review_page(
    root: Path,
    page: str,
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(page)
    target = candidate if candidate.is_absolute() else (root / candidate)
    target = target.resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Review target not found: {page}")
    content = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        raise ValueError("Only decision or judgment pages can enter the review workflow.")
    valid_statuses = valid_curated_statuses(kind)
    if status not in valid_statuses:
        raise ValueError(f"Unsupported review status for {kind}: {status}")
    reviewed_at = utc_now()
    frontmatter["status"] = status
    frontmatter["reviewed_at"] = reviewed_at
    if kind == "judgment" and confidence:
        frontmatter["confidence"] = confidence
    revisit_after, escalate_after = schedule_review_windows(kind, status, reviewed_at)
    frontmatter["revisit_after"] = revisit_after
    frontmatter["escalate_after"] = escalate_after
    body = strip_frontmatter(content).strip()
    review_status_lines = [
        f"- Current status: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if confidence and kind == "judgment":
        review_status_lines.append(f"- Confidence: `{confidence}`")
    review_notes_lines = [
        f"- Outcome: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if note:
        review_notes_lines.append(f"- Note: {note}")
    else:
        review_notes_lines.append("- No additional review note recorded.")
    updated_body = upsert_markdown_section(body, "Review Status", "\n".join(review_status_lines))
    updated_body = upsert_markdown_section(updated_body, "Review Notes", "\n".join(review_notes_lines))
    updated_body = upsert_markdown_section(
        updated_body,
        "Aging",
        "\n".join(
            [
                f"- Revisit after: `{revisit_after or 'none'}`",
                f"- Escalate after: `{escalate_after or 'none'}`",
            ]
        ),
    )
    target.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n", encoding="utf-8")
    append_wiki_log(
        root,
        "review",
        str(frontmatter.get("title") or target.stem),
        [
            f"kind: `{kind}`",
            f"status: `{status}`",
            f"path: `{relative_path(root, target)}`",
            f"confidence: `{frontmatter.get('confidence', '') or 'n/a'}`",
        ],
    )
    compile_wiki(root)
    return {
        "path": relative_path(root, target),
        "kind": kind,
        "status": status,
        "reviewed_at": reviewed_at,
        "confidence": str(frontmatter.get("confidence") or ""),
    }


def pending_source_summary_ids(root: Path, entries: list[dict[str, Any]]) -> list[str]:
    pending: list[str] = []
    for entry in entries:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending.append(entry["id"])
    return pending


def placeholder_concept_slugs(root: Path) -> list[str]:
    slugs: list[str] = []
    for page in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if concept_summary_is_placeholder(content):
            slugs.append(page.stem)
    return slugs


def concept_summary_is_placeholder(markdown: str) -> bool:
    summary = preserved_section(markdown, "Summary", "")
    return summary.startswith("- This concept currently appears in `")


def concept_quality_tokens(label: str) -> set[str]:
    return {token for token in tokenize(label) if token not in STOP_WORDS}


def load_source_page_context(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    if not path.exists():
        return {"path": relative, "title": relative.rsplit("/", 1)[-1], "summary": "", "status": "missing"}
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    summary = preserved_section(content, "Summary", "").strip()
    status = "placeholder" if summary == "- Pending LLM summary." else "ready"
    return {
        "path": relative,
        "title": str(frontmatter.get("title") or path.stem),
        "summary": summary,
        "status": status,
    }


def detect_concept_conflict_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_path = {
        context["path"]: str(context.get("summary") or "").lower()
        for context in source_contexts
        if context.get("status") == "ready" and context.get("summary")
    }
    signals: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for positive, negative, label in CONFLICT_SIGNAL_PAIRS:
        positive_hits = sorted(path for path, summary in by_path.items() if positive in summary)
        negative_hits = sorted(path for path, summary in by_path.items() if negative in summary)
        if not positive_hits or not negative_hits:
            continue
        touched_paths = sorted(set(positive_hits) | set(negative_hits))
        if len(touched_paths) < 2 or label in seen_labels:
            continue
        seen_labels.add(label)
        signals.append(
            {
                "label": label,
                "positive": positive,
                "negative": negative,
                "source_pages": touched_paths,
                "source_titles": [
                    next(
                        (
                            str(context.get("title") or path)
                            for context in source_contexts
                            if context.get("path") == path
                        ),
                        path,
                    )
                    for path in touched_paths
                ],
            }
        )
    return signals


def detect_concept_gap_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for context in source_contexts:
        path = str(context.get("path") or "")
        title = str(context.get("title") or path)
        status = str(context.get("status") or "")
        summary = str(context.get("summary") or "").lower()
        if status == "missing":
            gaps.append({"kind": "missing-source-page", "path": path, "title": title, "markers": ["missing-source-page"]})
            continue
        if status == "placeholder":
            gaps.append({"kind": "pending-source-summary", "path": path, "title": title, "markers": ["pending-source-summary"]})
            continue
        markers = sorted({marker for marker in EVIDENCE_GAP_MARKERS if marker in summary})
        if markers:
            gaps.append({"kind": "evidence-gap", "path": path, "title": title, "markers": markers})
    return gaps


def concept_rewrite_priority(score: int, issues: list[str], conflicts: list[dict[str, Any]]) -> str:
    if score >= 6 or conflicts or "placeholder-summary" in issues:
        return "high"
    if score >= 3:
        return "medium"
    if score > 0:
        return "low"
    return ""


def concept_rewrite_strategy(record: dict[str, Any]) -> str:
    issues = set(record.get("issues", []))
    steps: list[str] = []
    if "placeholder-summary" in issues:
        steps.append("替换占位摘要，改成 grounded synthesis。")
    if "conflicting-source-signals" in issues:
        steps.append("并列呈现冲突来源，明确分歧和适用边界。")
    if "evidence-gap" in issues:
        steps.append("保留证据缺口和不确定性，避免过强结论。")
    if "single-source" in issues:
        steps.append("保持保守措辞，并指出还缺哪些来源。")
    if "no-related-concepts" in issues:
        steps.append("补充相关概念边界和反链。")
    if "merge-boundary" in issues:
        steps.append("检查是否需要合并或拆分概念边界。")
    return " ".join(steps[:3]) or "保持当前概念总结。"


def repair_execution_proposals(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strategy_map = {
        "add-source-concept-link": {
            "kind": "cross-link",
            "risk": "low",
            "summary": "补 source/concept 双向链接，并检查概念摘要是否需要吸收新证据。",
            "edits": [
                "在 source page 里补 concept 引用或相关链接。",
                "在 concept page 的 Related Sources 里加入该 source page。",
                "如果来源提供新证据，重写 concept 摘要并保持 provenance。",
            ],
        },
        "connect-isolated-source": {
            "kind": "connect-source",
            "risk": "medium",
            "summary": "把孤立来源接入至少一个稳定概念，并显式记录依据。",
            "edits": [
                "先从 source page 抽出候选概念。",
                "优先补到现有稳定概念；必要时再新建概念页。",
                "保持 source page 对 raw evidence 的回指。",
            ],
        },
        "expand-singleton-concept": {
            "kind": "expand-concept",
            "risk": "medium",
            "summary": "扩展单节点概念的来源覆盖或相关概念边界。",
            "edits": [
                "补更多来源或相关概念反链。",
                "重写摘要时强调当前证据仍然有限。",
                "如果概念过窄，考虑降级为 source-specific note。",
            ],
        },
        "split-overloaded-concept": {
            "kind": "split-concept",
            "risk": "high",
            "summary": "拆分过载概念，明确子概念边界和来源分流。",
            "edits": [
                "先定义更窄的子概念名称和边界。",
                "把 source pages 重新分流到更具体的概念页。",
                "在原概念页保留拆分说明和跳转链接。",
            ],
        },
        "monitor-bridge-concept": {
            "kind": "monitor-bridge",
            "risk": "low",
            "summary": "记录桥接概念仍然必要的原因，避免误删跨簇连接。",
            "edits": [
                "在 concept page 里补一段 bridge maintenance note。",
                "确认相关概念链接仍然成立。",
                "如果桥接已经失效，再把动作转成 merge 或 split。 ",
            ],
        },
    }
    proposals: list[dict[str, Any]] = []
    for action in actions:
        template = strategy_map.get(str(action.get("kind") or ""), {})
        target_paths = [
            path
            for path in (
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            )
            if path
        ]
        proposal = {
            "id": f"proposal-{action.get('id', '')}",
            "action_id": str(action.get("id") or ""),
            "title": str(action.get("title") or ""),
            "priority": str(action.get("priority") or "medium"),
            "status": str(action.get("status") or "proposed"),
            "execution_policy": str(action.get("execution_policy") or "triage"),
            "proposal_kind": str(template.get("kind") or "manual-repair"),
            "risk": str(template.get("risk") or "medium"),
            "summary": str(template.get("summary") or action.get("reason") or ""),
            "target_paths": target_paths,
            "suggested_edits": list(template.get("edits") or [str(action.get("reason") or "检查相关页面并补修复说明。")]),
            "command_hint": str(action.get("command_hint") or ""),
            "next_step": str(action.get("next_step") or ""),
        }
        proposals.append(proposal)
    proposals.sort(
        key=lambda item: (
            action_status_rank(item["status"]),
            action_priority_rank(item["priority"]),
            item["proposal_kind"],
            item["title"].lower(),
        )
    )
    return proposals[:16]


def build_concept_quality(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    placeholder_slugs = set(placeholder_concept_slugs(root))
    singleton_slugs = set(memory.get("health", {}).get("singleton_concept_slugs", []))
    concept_nodes = [dict(node) for node in memory.get("concept_nodes", []) if isinstance(node, dict)]
    concept_records: dict[str, dict[str, Any]] = {}

    merge_candidates: list[dict[str, Any]] = []
    for index, left in enumerate(concept_nodes):
        left_tokens = concept_quality_tokens(str(left.get("title") or left.get("slug") or ""))
        left_sources = set(left.get("source_pages", []))
        if not left_tokens or not left_sources:
            continue
        for right in concept_nodes[index + 1 :]:
            right_tokens = concept_quality_tokens(str(right.get("title") or right.get("slug") or ""))
            right_sources = set(right.get("source_pages", []))
            if not right_tokens or not right_sources:
                continue
            shared_sources = sorted(left_sources & right_sources)
            if not shared_sources:
                continue
            shared_tokens = sorted(left_tokens & right_tokens)
            left_slug = str(left.get("slug") or "")
            right_slug = str(right.get("slug") or "")
            subset_match = left_tokens <= right_tokens or right_tokens <= left_tokens or left_slug in right_slug or right_slug in left_slug
            if not subset_match and len(shared_tokens) < 2:
                continue
            merge_candidates.append(
                {
                    "left_slug": left_slug,
                    "left_title": str(left.get("title") or left_slug),
                    "right_slug": right_slug,
                    "right_title": str(right.get("title") or right_slug),
                    "shared_sources": shared_sources,
                    "shared_tokens": shared_tokens,
                    "score": len(shared_sources) * 2 + len(shared_tokens),
                }
            )

    merge_candidates.sort(
        key=lambda item: (-int(item.get("score", 0)), item["left_title"].lower(), item["right_title"].lower())
    )
    merge_candidate_slugs = {
        slug
        for candidate in merge_candidates
        for slug in (candidate.get("left_slug", ""), candidate.get("right_slug", ""))
        if slug
    }

    for node in concept_nodes:
        slug = str(node.get("slug") or "")
        title = str(node.get("title") or slug)
        source_pages = list(node.get("source_pages", []))
        related_slugs = list(node.get("related_slugs", []))
        source_contexts = [load_source_page_context(root, relative) for relative in source_pages]
        conflict_signals = detect_concept_conflict_signals(source_contexts)
        gap_signals = detect_concept_gap_signals(source_contexts)
        issues: list[str] = []
        score = 0
        if slug in placeholder_slugs:
            issues.append("placeholder-summary")
            score += 3
        if slug in singleton_slugs or len(source_pages) <= 1:
            issues.append("single-source")
            score += 2
        if not related_slugs:
            issues.append("no-related-concepts")
            score += 1
        if conflict_signals:
            issues.append("conflicting-source-signals")
            score += 3
        if gap_signals:
            issues.append("evidence-gap")
            score += 2
        if slug in merge_candidate_slugs:
            issues.append("merge-boundary")
            score += 1
        concept_records[slug] = {
            "slug": slug,
            "title": title,
            "path": f"wiki/concepts/{slug}.md",
            "source_pages": source_pages,
            "source_count": len(source_pages),
            "related_count": len(related_slugs),
            "issues": issues,
            "score": score,
            "conflict_signals": conflict_signals[:4],
            "gap_signals": gap_signals[:4],
            "quality_state": "stable" if score == 0 else ("rewrite-now" if score >= 3 else "watch"),
        }

    weak_concepts: list[dict[str, Any]] = []
    stable_concepts: list[dict[str, Any]] = []
    rewrite_candidates: list[dict[str, Any]] = []
    all_conflict_signals: list[dict[str, Any]] = []
    all_gap_signals: list[dict[str, Any]] = []
    for record in concept_records.values():
        record["rewrite_priority"] = concept_rewrite_priority(
            int(record.get("score", 0)),
            list(record.get("issues", [])),
            list(record.get("conflict_signals", [])),
        )
        record["rewrite_strategy"] = concept_rewrite_strategy(record)
        if record["conflict_signals"]:
            for signal in record["conflict_signals"]:
                all_conflict_signals.append({"slug": record["slug"], "title": record["title"], **signal})
        if record["gap_signals"]:
            for gap in record["gap_signals"]:
                all_gap_signals.append({"slug": record["slug"], "title": record["title"], **gap})
        if int(record.get("score", 0)) > 0:
            weak_concepts.append(record)
            rewrite_candidates.append(
                {
                    "slug": record["slug"],
                    "title": record["title"],
                    "path": record["path"],
                    "priority": record["rewrite_priority"],
                    "issues": list(record.get("issues", [])),
                    "score": int(record.get("score", 0)),
                    "rewrite_strategy": record["rewrite_strategy"],
                    "conflict_count": len(record.get("conflict_signals", [])),
                    "gap_count": len(record.get("gap_signals", [])),
                    "source_pages": list(record.get("source_pages", [])),
                }
            )
        else:
            stable_concepts.append(record)

    weak_concepts.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            -len(item.get("conflict_signals", [])),
            int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    stable_concepts.sort(key=lambda item: (-int(item.get("source_count", 0)), item.get("title", "").lower()))
    rewrite_candidates.sort(
        key=lambda item: (
            action_priority_rank(item.get("priority", "")),
            -int(item.get("score", 0)),
            -int(item.get("conflict_count", 0)),
            item.get("title", "").lower(),
        )
    )
    all_conflict_signals.sort(
        key=lambda item: (
            -len(item.get("source_pages", [])),
            item.get("title", "").lower(),
            item.get("label", ""),
        )
    )
    all_gap_signals.sort(
        key=lambda item: (
            item.get("kind", ""),
            item.get("title", "").lower(),
            item.get("path", ""),
        )
    )
    return {
        "weak_concepts": weak_concepts[:20],
        "stable_concepts": stable_concepts[:12],
        "merge_candidates": merge_candidates[:12],
        "rewrite_candidates": rewrite_candidates[:12],
        "conflict_signals": all_conflict_signals[:12],
        "gap_signals": all_gap_signals[:12],
        "placeholder_slugs": sorted(placeholder_slugs),
        "counts": {
            "weak": len(weak_concepts),
            "stable": len(stable_concepts),
            "merge_candidates": len(merge_candidates),
            "placeholders": len(placeholder_slugs),
            "rewrite_candidates": len(rewrite_candidates),
            "conflict_signals": len(all_conflict_signals),
            "gap_signals": len(all_gap_signals),
        },
    }


def lint_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    findings: list[Finding] = []

    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            findings.append(
                Finding("error", relative_path(root, page), f"Missing source page for manifest entry `{entry['id']}`.")
            )
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        for key in ("id", "kind", "source_files", "generated_by"):
            if key not in frontmatter or frontmatter[key] in ("", []):
                findings.append(
                    Finding("error", relative_path(root, page), f"Frontmatter is missing required key `{key}`.")
                )
        for source_file in frontmatter.get("source_files", []):
            candidate = root / source_file
            if not candidate.exists():
                findings.append(
                    Finding("error", relative_path(root, page), f"Referenced source file does not exist: `{source_file}`.")
                )
        if "Pending LLM summary." in content:
            findings.append(
                Finding("warn", relative_path(root, page), "Source page still contains the placeholder summary.")
            )
        if not frontmatter.get("concepts"):
            findings.append(
                Finding("warn", relative_path(root, page), "Source page has no compiled concept links.")
            )

    required_indexes = {
        "wiki/indexes/index.md": "Missing master wiki index page.",
        "wiki/indexes/sources.md": "Missing sources index page.",
        "wiki/indexes/concepts.md": "Missing concepts index page.",
        "wiki/indexes/decisions.md": "Missing decisions index page.",
        "wiki/indexes/judgments.md": "Missing judgments index page.",
        "wiki/indexes/review-queue.md": "Missing review queue page.",
        "wiki/indexes/review-center.md": "Missing review center page.",
        "wiki/indexes/aging-report.md": "Missing aging report page.",
        "wiki/indexes/concept-quality.md": "Missing concept quality page.",
        "wiki/indexes/compile-status.md": "Missing compile status page.",
        "wiki/indexes/machine-memory.md": "Missing machine memory index page.",
        "wiki/indexes/graph-view.md": "Missing graph view page.",
        "wiki/indexes/machine-memory-topology.md": "Missing machine memory topology page.",
        "wiki/indexes/machine-memory-actions.md": "Missing machine memory actions page.",
        "wiki/indexes/machine-memory-repair-plan.md": "Missing machine memory repair plan page.",
        "wiki/indexes/graph-health.md": "Missing machine memory graph health page.",
        "wiki/indexes/drift-report.md": "Missing machine memory drift report.",
        "wiki/indexes/log.md": "Missing wiki operation log.",
    }
    for relative, message in required_indexes.items():
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, message))

    required_schema = {
        "schema/index.md": "Missing runtime schema index.",
        "schema/ingest.md": "Missing runtime ingest rules.",
        "schema/citations.md": "Missing runtime citation rules.",
        "schema/conflicts.md": "Missing runtime conflict rules.",
        "schema/review.md": "Missing runtime review rules.",
        "schema/writeback.md": "Missing runtime writeback rules.",
    }
    for relative, message in required_schema.items():
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, message))

    memory_state = machine_memory_state_path(root)
    graph_html = machine_memory_graph_html_path(root)
    if manifest["entries"] and not memory_state.exists():
        findings.append(Finding("error", relative_path(root, memory_state), "Missing machine memory state file."))
    if manifest["entries"] and not graph_html.exists():
        findings.append(Finding("error", relative_path(root, graph_html), "Missing machine memory graph HTML view."))
    if memory_state.exists():
        try:
            memory = json.loads(memory_state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(Finding("error", relative_path(root, memory_state), "Machine memory state is not valid JSON."))
        else:
            if "source_nodes" not in memory or "concept_nodes" not in memory:
                findings.append(
                    Finding("error", relative_path(root, memory_state), "Machine memory state is missing required indexes.")
                )
            if "health" not in memory:
                findings.append(
                    Finding("warn", relative_path(root, memory_state), "Machine memory state is missing graph health data.")
                )
            if not memory.get("digest"):
                findings.append(
                    Finding("warn", relative_path(root, memory_state), "Machine memory state is missing a stable digest.")
                )

    graph_export = machine_memory_graph_path(root)
    if manifest["entries"] and not graph_export.exists():
        findings.append(Finding("error", relative_path(root, graph_export), "Missing machine memory graph export."))
    elif graph_export.exists():
        try:
            graph = json.loads(graph_export.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(Finding("error", relative_path(root, graph_export), "Machine memory graph export is not valid JSON."))
        else:
            if "nodes" not in graph or "edges" not in graph:
                findings.append(
                    Finding("error", relative_path(root, graph_export), "Machine memory graph export is missing nodes or edges.")
                )

    history_path = machine_memory_history_path(root)
    if manifest["entries"] and not history_path.exists():
        findings.append(Finding("warn", relative_path(root, history_path), "Machine memory history file has not been initialized."))

    action_state_path = machine_memory_action_state_path(root)
    if manifest["entries"] and not action_state_path.exists():
        findings.append(
            Finding("warn", relative_path(root, action_state_path), "Machine memory action state file has not been initialized.")
        )
    elif action_state_path.exists():
        action_state = load_json_document(action_state_path)
        if not isinstance(action_state, dict) or not isinstance(action_state.get("actions"), list):
            findings.append(
                Finding("error", relative_path(root, action_state_path), "Machine memory action state is not valid JSON.")
            )

    concept_pages = sorted((root / "wiki" / "concepts").glob("*.md"))
    if manifest["entries"] and not concept_pages:
        findings.append(Finding("warn", "wiki/concepts", "No concept pages have been compiled yet."))

    for page in concept_pages:
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "concept":
            findings.append(Finding("warn", relative_path(root, page), "Concept page kind is missing or incorrect."))
        if concept_summary_is_placeholder(content):
            findings.append(Finding("warn", relative_path(root, page), "Concept page still contains the fallback summary."))
        source_pages = frontmatter.get("source_pages", [])
        if not source_pages:
            findings.append(Finding("warn", relative_path(root, page), "Concept page has no source-page references."))
        for source_page in source_pages:
            candidate = root / source_page
            if not candidate.exists():
                findings.append(
                    Finding("error", relative_path(root, page), f"Concept page references missing source page: `{source_page}`.")
                )

    for group, expected_kind in (
        ("wiki/derived", "derived"),
        ("wiki/decisions", "decision"),
        ("wiki/judgments", "judgment"),
    ):
        for page in sorted((root / group).glob("*.md")):
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != expected_kind:
                findings.append(
                    Finding("warn", relative_path(root, page), f"{expected_kind.capitalize()} page kind is missing or incorrect.")
                )
            if "wiki/sources/" not in content and "raw/" not in content:
                findings.append(
                    Finding("warn", relative_path(root, page), f"{expected_kind.capitalize()} page has no explicit source-page reference.")
                )
            if expected_kind == "decision":
                if frontmatter.get("status") not in DECISION_STATUSES:
                    findings.append(
                        Finding(
                            "warn",
                            relative_path(root, page),
                            f"Decision page has unsupported status `{frontmatter.get('status', '')}`.",
                        )
                    )
                for section in ("## Decision", "## Evidence"):
                    if section not in content:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Decision page is missing section `{section}`.")
                        )
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Decision page is missing section `{section}`.")
                        )
                if frontmatter.get("status") in {"approved", "needs-revisit", "superseded"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    findings.append(
                        Finding("warn", relative_path(root, page), "Reviewed decision page is missing `reviewed_at`."),
                    )
            if expected_kind == "judgment":
                if frontmatter.get("status") not in JUDGMENT_STATUSES:
                    findings.append(
                        Finding(
                            "warn",
                            relative_path(root, page),
                            f"Judgment page has unsupported status `{frontmatter.get('status', '')}`.",
                        )
                    )
                for section in ("## Judgment", "## Signals"):
                    if section not in content:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Judgment page is missing section `{section}`.")
                        )
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Judgment page is missing section `{section}`.")
                        )
                if not frontmatter.get("confidence"):
                    findings.append(
                        Finding("warn", relative_path(root, page), "Judgment page is missing explicit confidence metadata.")
                    )
                if frontmatter.get("status") in {"tracking", "confirmed", "rejected"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    findings.append(
                        Finding("warn", relative_path(root, page), "Reviewed judgment page is missing `reviewed_at`."),
                    )

    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    report_path = root / "output" / "lint" / report_name
    error_count = sum(1 for finding in findings if finding.severity == "error")
    warn_count = sum(1 for finding in findings if finding.severity == "warn")
    lines = [
        "# Lint 报告",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 错误数：`{error_count}`",
        f"- 警告数：`{warn_count}`",
        "",
        "## 发现",
    ]
    if not findings:
        lines.append("- 没有发现问题。")
    else:
        for finding in findings:
            lines.append(f"- `{finding.severity}` {finding.path}: {finding.message}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_wiki_log(
        root,
        "lint",
        "wiki health check",
        [
            f"errors: `{error_count}`",
            f"warnings: `{warn_count}`",
            f"report: `{relative_path(root, report_path)}`",
        ],
    )
    return {
        "path": relative_path(root, report_path),
        "counts": {"errors": error_count, "warnings": warn_count},
        "findings": [
            {"severity": finding.severity, "path": finding.path, "message": finding.message}
            for finding in findings
        ],
    }


def render_repair_backlog(
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    memory: dict[str, Any],
    promotion_result: dict[str, Any],
    pending_sources: list[str],
    placeholder_concepts: list[str],
    pending_review_decisions: list[dict[str, str]],
    pending_review_judgments: list[dict[str, str]],
    overdue_pages: list[dict[str, str]],
    escalated_pages: list[dict[str, str]],
    semantic_report: str,
    generated_at: str,
) -> str:
    drift = memory.get("drift", {})
    health = memory.get("health", {})
    transition = memory.get("transition", {})
    findings = lint_result.get("findings", [])
    error_findings = [finding for finding in findings if finding["severity"] == "error"]
    warn_findings = [finding for finding in findings if finding["severity"] == "warn"]
    sources_without_concepts = drift.get("sources_without_concepts", [])
    isolated_sources = health.get("isolated_source_ids", [])
    singleton_concepts = health.get("singleton_concept_slugs", [])
    bridge_concepts = health.get("bridge_concept_slugs", [])
    overloaded_concepts = health.get("overloaded_concept_slugs", [])
    actions = health.get("actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    inactive_actions = health.get("inactive_actions", [])
    repair_plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    execution_proposals = repair_plan.get("execution_proposals", [])
    promotions = promotion_result.get("pages", [])
    lines = [
        "# 修复待办",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 本轮编译改动页数：`{compile_result.get('changed_pages', 0)}`",
        f"- 机器记忆是否变化：`{compile_result.get('machine_memory_changed', False)}`",
        f"- Lint 错误：`{lint_result['counts']['errors']}`",
        f"- Lint 警告：`{lint_result['counts']['warnings']}`",
        f"- 待补来源摘要：`{len(pending_sources)}`",
        f"- 占位概念摘要：`{len(placeholder_concepts)}`",
        f"- 待审决策：`{len(pending_review_decisions)}`",
        f"- 待审判断：`{len(pending_review_judgments)}`",
        f"- 已到期复审：`{len(overdue_pages)}`",
        f"- 升级处理项：`{len(escalated_pages)}`",
        f"- 自动晋升页面：`{promotion_result.get('count', 0)}`",
        f"- 图谱修复动作：`{len(actions)}`",
        f"- 动作已到期：`{len(overdue_actions)}`",
        f"- 动作需升级：`{len(escalated_actions)}`",
        f"- 最近清除动作：`{len(inactive_actions)}`",
        f"- Ready 动作：`{repair_plan.get('counts', {}).get('ready', 0)}`",
        f"- 待分流动作：`{repair_plan.get('counts', {}).get('triage', 0)}`",
        f"- 执行批次：`{repair_plan.get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{repair_plan.get('counts', {}).get('proposals', 0)}`",
        f"- 弱概念页：`{concept_quality.get('counts', {}).get('weak', 0)}`",
        f"- 概念合并候选：`{concept_quality.get('counts', {}).get('merge_candidates', 0)}`",
        f"- 概念冲突信号：`{concept_quality.get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念证据缺口：`{concept_quality.get('counts', {}).get('gap_signals', 0)}`",
        f"- 图谱修复候选：`{len(health.get('link_suggestions', []))}`",
        f"- 无概念覆盖来源：`{len(sources_without_concepts)}`",
        f"- 图谱分量数：`{health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(isolated_sources)}`",
        f"- 单节点概念：`{len(singleton_concepts)}`",
        f"- 桥接概念：`{len(bridge_concepts)}`",
        f"- 过载概念：`{len(overloaded_concepts)}`",
        "",
        "## 优先队列",
    ]
    if error_findings:
        lines.append(f"1. 先解决 `{len(error_findings)}` 个 lint 错误，再继续依赖下游输出。")
    if pending_sources:
        lines.append(f"2. 补齐 `{len(pending_sources)}` 个仍是占位摘要的来源页。")
    if placeholder_concepts:
        lines.append(f"3. 重写 `{len(placeholder_concepts)}` 个仍使用回退摘要的概念页。")
    if concept_quality.get("counts", {}).get("weak", 0):
        lines.append(f"3a. 按概念质量看板优先处理 `{concept_quality.get('counts', {}).get('weak', 0)}` 个弱概念页。")
    if pending_review_decisions:
        lines.append(f"4. 审阅 `{len(pending_review_decisions)}` 个等待批准或复审的决策页。")
    if pending_review_judgments:
        lines.append(f"5. 审阅 `{len(pending_review_judgments)}` 个仍处于暂定或跟踪状态的判断页。")
    if overdue_pages:
        lines.append(f"6. 先清理 `{len(overdue_pages)}` 个已到期但还没复审的页面。")
    if escalated_pages:
        lines.append(f"7. 提升 `{len(escalated_pages)}` 个已经超过升级阈值的页面优先级。")
    if promotions:
        lines.append(f"8. 检查本轮自动晋升的 `{len(promotions)}` 个页面，确认是否需要补证据和审阅。")
    if actions:
        lines.append(f"9. 按动作队列处理 `{len(actions)}` 个 machine-memory 修复动作。")
    if repair_plan.get("counts", {}).get("ready", 0):
        lines.append(
            f"9a. 先执行 `{repair_plan.get('counts', {}).get('ready', 0)}` 个已接受动作和 `{repair_plan.get('counts', {}).get('batches', 0)}` 个批次。"
        )
    if repair_plan.get("counts", {}).get("proposals", 0):
        lines.append(f"9b. 参考 `{repair_plan.get('counts', {}).get('proposals', 0)}` 个页级执行提案决定下一批修复。")
    if overdue_actions:
        lines.append(f"10. 优先清理 `{len(overdue_actions)}` 个已到期待处理的 machine-memory 动作。")
    if escalated_actions:
        lines.append(f"11. 先处理 `{len(escalated_actions)}` 个已升级的 machine-memory 动作。")
    if concept_quality.get("counts", {}).get("conflict_signals", 0):
        lines.append(f"11a. 先把 `{concept_quality.get('counts', {}).get('conflict_signals', 0)}` 个概念冲突信号显式写进相关概念页。")
    if health.get("link_suggestions", []):
        lines.append(f"12. 审阅 `{len(health.get('link_suggestions', []))}` 个机器记忆补链候选，决定是否补链接。")
    if sources_without_concepts:
        lines.append(f"13. 检查 `{len(sources_without_concepts)}` 个没有概念覆盖的来源。")
    if isolated_sources:
        lines.append(f"14. 把 `{len(isolated_sources)}` 个孤立来源节点接入概念图谱。")
    if singleton_concepts:
        lines.append(f"15. 复查 `{len(singleton_concepts)}` 个还没接入更大上下文的单节点概念。")
    if overloaded_concepts:
        lines.append(f"16. 考虑拆分 `{len(overloaded_concepts)}` 个过载概念。")
    if transition.get("changed"):
        lines.append("17. 在下一轮研究前先检查最新的机器记忆漂移。")
    if not any(
        (
            error_findings,
            pending_sources,
            placeholder_concepts,
            pending_review_decisions,
            pending_review_judgments,
            overdue_pages,
            escalated_pages,
            promotions,
            sources_without_concepts,
            isolated_sources,
            singleton_concepts,
            overloaded_concepts,
            transition.get("changed"),
        )
    ):
        lines.append("1. 当前没有紧急修复项，继续观察 nightly 漂移和 lint 输出。")
    lines.extend(
        [
            "",
            "## 可执行事项",
        ]
    )
    if error_findings:
        lines.append("### Lint 错误")
        for finding in error_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if warn_findings:
        lines.append("")
        lines.append("### Lint 警告")
        for finding in warn_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if pending_sources:
        lines.append("")
        lines.append("### 待补来源摘要")
        for source_id in pending_sources[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    if placeholder_concepts:
        lines.append("")
        lines.append("### 占位概念摘要")
        for slug in placeholder_concepts[:10]:
            lines.append(f"- `wiki/concepts/{slug}.md`")
    if pending_review_decisions or pending_review_judgments:
        lines.append("")
        lines.append("### 审阅队列")
        for page in pending_review_decisions[:10]:
            lines.append(f"- 决策：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
        for page in pending_review_judgments[:10]:
            lines.append(f"- 判断：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
    if overdue_pages or escalated_pages:
        lines.append("")
        lines.append("### Aging 信号")
        for page in escalated_pages[:10]:
            lines.append(f"- 升级：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
        for page in overdue_pages[:10]:
            if page in escalated_pages[:10]:
                continue
            lines.append(f"- 到期：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
    if promotions:
        lines.append("")
        lines.append("### 本轮自动晋升")
        for promotion in promotions[:10]:
            label = "决策" if promotion["kind"] == "decision" else "判断"
            lines.append(
                f"- {label}：`{promotion['path']}` | 动作 `{promotion['action']}` | 重复次数 `{promotion['occurrences']}`"
            )
    lines.append("")
    lines.append("### Machine Memory 动作")
    if actions:
        for action in actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] `{action['primary_path']}`"
                f"{detail}"
                f" | {action['title']}"
                f" | status `{action_status}`"
                f" | seen `{action.get('occurrences', 0)}`"
            )
    else:
        lines.append("- 当前没有 machine-memory 动作。")
    if escalated_actions or overdue_actions:
        lines.append("")
        lines.append("### Action Aging")
        for action in escalated_actions[:10]:
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- 升级：`{action['id']}` | {action['title']} | status `{action_status}`"
            )
        for action in overdue_actions[:10]:
            if any(action["id"] == escalated["id"] for escalated in escalated_actions[:10]):
                continue
            lines.append(
                f"- 到期：`{action['id']}` | {action['title']} | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    if inactive_actions:
        lines.append("")
        lines.append("### 最近清除动作")
        for action in inactive_actions[:10]:
            lines.append(
                f"- 清除：`{action['id']}` | {action['title']} | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    if concept_quality.get("weak_concepts"):
        lines.append("")
        lines.append("### 弱概念页")
        for concept in concept_quality.get("weak_concepts", [])[:10]:
            lines.append(
                f"- `{concept['path']}` | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
            )
    if concept_quality.get("rewrite_candidates"):
        lines.append("")
        lines.append("### 概念重写优先级")
        for candidate in concept_quality.get("rewrite_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['path']}` | priority `{candidate.get('priority', 'n/a')}`"
                f" | strategy `{candidate.get('rewrite_strategy', 'n/a')}`"
            )
    if concept_quality.get("conflict_signals"):
        lines.append("")
        lines.append("### 概念冲突信号")
        for signal in concept_quality.get("conflict_signals", [])[:8]:
            lines.append(
                f"- `{signal['slug']}` | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    if concept_quality.get("merge_candidates"):
        lines.append("")
        lines.append("### 概念合并候选")
        for candidate in concept_quality.get("merge_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['left_slug']}` <-> `{candidate['right_slug']}`"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    if repair_plan.get("execution_batches"):
        lines.append("")
        lines.append("### 执行批次")
        for batch in repair_plan.get("execution_batches", [])[:8]:
            lines.append(
                f"- {batch['label']} | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Repair Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | strategy `{proposal.get('summary', 'n/a')}`"
            )
    if health.get("link_suggestions", []):
        lines.append("")
        lines.append("### 图谱修复候选")
        for suggestion in health.get("link_suggestions", [])[:10]:
            lines.append(
                f"- `{suggestion['source_page']}` -> `{suggestion['concept_page']}`"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    if sources_without_concepts:
        lines.append("")
        lines.append("### 无概念覆盖来源")
        for source_id in sources_without_concepts[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    lines.append("")
    lines.append("### 图谱修复建议")
    if isolated_sources:
        for source_id in isolated_sources[:10]:
            lines.append(f"- 将孤立来源 `wiki/sources/{source_id}.md` 至少连接到一个稳定概念。")
    if singleton_concepts:
        for slug in singleton_concepts[:10]:
            lines.append(f"- 检查单节点概念 `wiki/concepts/{slug}.md` 是否缺少相关概念或来源链接。")
    if overloaded_concepts:
        for slug in overloaded_concepts[:10]:
            lines.append(f"- 考虑把过宽的概念 `wiki/concepts/{slug}.md` 拆成更窄的页面。")
    if bridge_concepts:
        lines.append(f"- 保留桥接概念：`{', '.join(bridge_concepts[:10])}`，因为它们连接了多个簇。")
    if not any((isolated_sources, singleton_concepts, overloaded_concepts, bridge_concepts)):
        lines.append("- 当前没有图谱专项修复项。")
    if transition.get("changed"):
        lines.append("")
        lines.append("### 结构漂移")
        lines.append(f"- 上一版摘要：`{transition.get('previous_digest', '') or 'none'}`")
        lines.append(f"- 当前摘要：`{transition.get('current_digest', '') or 'none'}`")
        lines.append(f"- 新增来源节点：`{len(transition.get('added_source_ids', []))}`")
        lines.append(f"- 新增概念节点：`{len(transition.get('added_concept_slugs', []))}`")
        lines.append(f"- 新增边：`{transition.get('added_edges', 0)}`")
        lines.append(f"- 移除边：`{transition.get('removed_edges', 0)}`")
    lines.extend(
        [
            "",
            "## 相关产物",
            f"- Lint 报告：`{lint_result['path']}`",
            "- Aging 报告：`wiki/indexes/aging-report.md`",
            "- 机器记忆：`wiki/indexes/machine-memory.md`",
            "- 拓扑视图：`wiki/indexes/machine-memory-topology.md`",
            "- 动作队列：`wiki/indexes/machine-memory-actions.md`",
            "- 修复计划：`wiki/indexes/machine-memory-repair-plan.md`",
            "- 图谱健康：`wiki/indexes/graph-health.md`",
            "- 漂移报告：`wiki/indexes/drift-report.md`",
            "- 审阅队列：`wiki/indexes/review-queue.md`",
            "- 规则索引：`schema/index.md`",
        ]
    )
    if semantic_report:
        lines.append(f"- 语义 lint：`{semantic_report}`")
    return "\n".join(lines) + "\n"


def write_nightly_health(
    root: Path,
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    *,
    promotion_result: dict[str, Any] | None = None,
    semantic_report: str = "",
    llm_used: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    promotion_result = promotion_result or {"count": 0, "created": 0, "updated": 0, "pages": []}
    manifest = load_manifest(root)
    memory = load_machine_memory(root)
    pending_sources = pending_source_summary_ids(root, manifest["entries"])
    placeholder_concepts = placeholder_concept_slugs(root)
    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    queue = review_queue(decisions, judgments)
    aging = collect_aging_signals(decisions, judgments)
    generated_at = utc_now()
    state = {
        "generated_at": generated_at,
        "llm_used": llm_used,
        "compile": compile_result,
        "lint": {
            "path": lint_result["path"],
            "counts": lint_result["counts"],
        },
        "semantic_report": semantic_report,
        "promotions": promotion_result,
        "aging": {
            "overdue_pages": [page["path"] for page in aging["overdue"]],
            "escalated_pages": [page["path"] for page in aging["escalated"]],
            "scheduled_pages": [page["path"] for page in aging["scheduled"]],
        },
        "concept_quality": {
            "path": relative_path(root, concept_quality_path(root)),
            "weak_concept_slugs": [
                concept["slug"] for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
            ],
            "rewrite_candidate_slugs": [
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("rewrite_candidates", [])
            ],
            "merge_candidates": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("merge_candidates", 0),
            "conflict_signals": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("conflict_signals", 0),
            "gap_signals": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("gap_signals", 0),
        },
        "machine_memory": {
            "digest": memory.get("digest", ""),
            "graph_digest": memory.get("graph_digest", ""),
            "transition": memory.get("transition", {}),
            "drift": memory.get("drift", {}),
            "health": memory.get("health", {}),
            "topology_path": relative_path(root, machine_memory_topology_path(root)),
            "actions_path": relative_path(root, machine_memory_actions_path(root)),
            "repair_plan_path": relative_path(root, machine_memory_repair_plan_path(root)),
            "action_counts": memory.get("health", {}).get("action_counts", {}),
            "repair_plan_counts": memory.get("health", {}).get("repair_plan", {}).get("counts", {}),
            "overdue_action_ids": [action["id"] for action in memory.get("health", {}).get("overdue_actions", [])],
            "escalated_action_ids": [action["id"] for action in memory.get("health", {}).get("escalated_actions", [])],
            "ready_action_ids": [
                action["id"] for action in memory.get("health", {}).get("repair_plan", {}).get("ready_actions", [])
            ],
            "proposal_action_ids": [
                proposal["action_id"]
                for proposal in memory.get("health", {}).get("repair_plan", {}).get("execution_proposals", [])
            ],
        },
        "repair_backlog": {
            "path": relative_path(root, repair_backlog_path(root)),
            "pending_source_summaries": pending_sources,
            "placeholder_concepts": placeholder_concepts,
            "pending_review_decisions": [page["path"] for page in queue["pending_decisions"]],
            "pending_review_judgments": [page["path"] for page in queue["pending_judgments"]],
            "overdue_pages": [page["path"] for page in aging["overdue"]],
            "escalated_pages": [page["path"] for page in aging["escalated"]],
            "auto_promotions": [page["path"] for page in promotion_result.get("pages", [])],
            "weak_concept_slugs": [
                concept["slug"] for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
            ],
            "rewrite_candidate_slugs": [
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("rewrite_candidates", [])
            ],
            "machine_memory_actions": [action["id"] for action in memory.get("health", {}).get("actions", [])],
            "overdue_action_ids": [action["id"] for action in memory.get("health", {}).get("overdue_actions", [])],
            "escalated_action_ids": [action["id"] for action in memory.get("health", {}).get("escalated_actions", [])],
            "repair_plan_path": relative_path(root, machine_memory_repair_plan_path(root)),
            "ready_action_ids": [
                action["id"] for action in memory.get("health", {}).get("repair_plan", {}).get("ready_actions", [])
            ],
            "proposal_action_ids": [
                proposal["action_id"]
                for proposal in memory.get("health", {}).get("repair_plan", {}).get("execution_proposals", [])
            ],
        },
    }
    repair_backlog = render_repair_backlog(
        compile_result,
        lint_result,
        memory,
        promotion_result,
        pending_sources,
        placeholder_concepts,
        queue["pending_decisions"],
        queue["pending_judgments"],
        aging["overdue"],
        aging["escalated"],
        semantic_report,
        generated_at,
    )
    repair_backlog_path(root).write_text(repair_backlog, encoding="utf-8")
    nightly_health_state_path(root).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_wiki_log(
        root,
        "nightly",
        "health and repair pass",
        [
            f"llm_used: `{llm_used}`",
            f"lint_errors: `{lint_result['counts']['errors']}`",
            f"lint_warnings: `{lint_result['counts']['warnings']}`",
            f"pending_source_summaries: `{len(pending_sources)}`",
            f"placeholder_concepts: `{len(placeholder_concepts)}`",
            f"pending_decision_reviews: `{len(queue['pending_decisions'])}`",
            f"pending_judgment_reviews: `{len(queue['pending_judgments'])}`",
            f"overdue_reviews: `{len(aging['overdue'])}`",
            f"escalation_candidates: `{len(aging['escalated'])}`",
            f"auto_promotions: `{promotion_result.get('count', 0)}`",
            f"weak_concepts: `{memory.get('health', {}).get('concept_quality', {}).get('counts', {}).get('weak', 0)}`",
            f"machine_memory_actions: `{memory.get('health', {}).get('action_counts', {}).get('total', 0)}`",
            f"ready_machine_memory_actions: `{memory.get('health', {}).get('repair_plan', {}).get('counts', {}).get('ready', 0)}`",
            f"repair_backlog: `{relative_path(root, repair_backlog_path(root))}`",
        ],
    )
    return state


def nightly_health(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    promotion_result = promote_recurring_outputs(root)
    if promotion_result["count"]:
        compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)
    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        promotion_result=promotion_result,
        semantic_report="",
        llm_used=False,
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }
