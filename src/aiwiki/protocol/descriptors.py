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
        "这里存放统一炼丹炉的单 runtime 协议规则层。",
        "",
        "- 炉子只有一个 runtime：`general`。",
        "- 领域差异通过概念、判断和 schema 扩展表达，不再拆多套 protocol slug。",
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
            "- 协议层是统一 runtime 的规则覆盖，不是新的 runtime 分叉。",
            "- 非 `general` 的旧 protocol slug 会在 state 加载时一次性迁移到 `general`。",
            "",
            "## 运行时行为",
            "",
            "- `decision / judgment` 默认 review window 沿通用协议执行。",
            "- `file-back` 生成的页面模板沿通用协议执行。",
            "- recurring promotion、review / nightly / repair 沿通用协议焦点执行。",
            "- `query / output / execution proposal` 沿通用协议偏置执行。",
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
