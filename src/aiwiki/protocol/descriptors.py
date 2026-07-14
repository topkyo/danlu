"""Protocol metadata and scaffold render helpers."""

from __future__ import annotations

from .library import PROTOCOL_LIBRARY
from .templates import PROTOCOL_SECTION_FILES, PROTOCOL_SECTION_TITLES

AGENT_PACK_LIBRARY = (
    {
        "role": "ingest-agent",
        "title": "Ingest Agent",
        "mission": "整理新原料、补来源页和基础元数据，让证据层持续进炉。",
    },
    {
        "role": "concept-agent",
        "title": "Concept Agent",
        "mission": "维护 concept 层，处理弱概念、冲突信号、证据缺口和 rewrite proposal。",
    },
    {
        "role": "judgment-agent",
        "title": "Judgment Agent",
        "mission": "把高价值输出沉成 decision / judgment，并补齐判断资产缺口。",
    },
    {
        "role": "review-agent",
        "title": "Review Agent",
        "mission": "清理 pending review、aging 和 judgment drift，把旧判断拉回复审。",
    },
    {
        "role": "repair-planner",
        "title": "Repair Planner",
        "mission": "把 machine-memory action、patch plan 和 execution proposal 收敛成可执行修复队列。",
    },
    {
        "role": "execution-agent",
        "title": "Execution Agent",
        "mission": "只在安全边界内执行 bundle-driven 低风险动作，并保留 receipt / revert 链。",
    },
    {
        "role": "nightly-agent",
        "title": "Nightly Agent",
        "mission": "夜间巡检、复审、漂移检查和自动晋升，维持整炉持续收敛。",
    },
)


def protocol_title(slug: str) -> str:
    metadata = PROTOCOL_LIBRARY.get(slug, {})
    return str(metadata.get("title") or slug.replace("-", " ").title())


def protocol_summary(slug: str) -> str:
    metadata = PROTOCOL_LIBRARY.get(slug, {})
    return str(metadata.get("summary") or "")


def render_protocol_library_index() -> str:
    lines = [
        "# 协议规则索引",
        "",
        "这里存放统一炼丹炉的多协议规则层。",
        "",
        "- 炉子只有一个。",
        "- 领域协议可以有很多套。",
        f"- 当前 starter library 已提供 `{ ' / '.join(sorted(PROTOCOL_LIBRARY)) }` {len(PROTOCOL_LIBRARY)} 套协议。",
        "",
        "## 可用协议",
    ]
    for slug in sorted(PROTOCOL_LIBRARY):
        lines.append(f"- [{protocol_title(slug)}](./{slug}/index.md)：{protocol_summary(slug)}")
    lines.extend(
        [
            "",
            "## 约束",
            "",
            "- 协议层是统一 runtime 的覆盖层，不是新的 runtime 分叉。",
            "- 领域差异优先落到 `schema/protocols/`，而不是复制一套 `aiwiki`。",
            "",
            "## 当前已经生效的运行时差异",
            "",
            "- `decision / judgment` 的默认 review window 会按协议变化。",
            "- `file-back` 生成的 `decision / judgment` 页面模板会按协议变化。",
            "- recurring promotion 的标题前缀和分类提示会按协议变化。",
            "- `review / nightly / repair` 的优先级和焦点会按协议变化。",
            "- `query / output / execution proposal` 会按协议加入领域偏置。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_protocol_overview(slug: str) -> str:
    metadata = PROTOCOL_LIBRARY[slug]
    lines = [
        f"# {metadata['title']}",
        "",
        metadata["summary"],
        "",
        "## 规则文件",
    ]
    for section in PROTOCOL_SECTION_FILES:
        lines.append(f"- [{PROTOCOL_SECTION_TITLES[section]}](./{section}.md)")
    lines.extend(["", "## 关注点"])
    for line in metadata.get("focus", []):
        lines.append(f"- {line}")
    return "\n".join(lines) + "\n"


def render_protocol_section(slug: str, section: str) -> str:
    metadata = PROTOCOL_LIBRARY[slug]
    title = protocol_title(slug)
    section_title = PROTOCOL_SECTION_TITLES[section]
    body = metadata.get(section, [])
    lines = [
        f"# {title} · {section_title}",
        "",
        f"这页属于 `{slug}` 协议。",
        "",
    ]
    for line in body:
        lines.append(f"- {line}")
    return "\n".join(lines) + "\n"
