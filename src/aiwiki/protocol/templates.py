"""Static protocol/runtime scaffold templates extracted from app_protocol."""

from __future__ import annotations

LAYOUT_DIRS = (
    "raw/inbox",
    "raw/normalized",
    "raw/assets",
    "schema",
    "schema/policies",
    "schema/protocols",
    "wiki/sources",
    "wiki/concepts",
    "wiki/rewrite-proposals",
    "wiki/indexes",
    "wiki/derived",
    "output/reports",
    "output/slides",
    "output/figures",
    "output/graph",
    "output/control",
    "output/review",
    "prompts",
    ".aiwiki/lint",
    ".aiwiki/state",
    ".aiwiki/state/execution-receipts",
    ".aiwiki/state/execution-bundles",
    ".aiwiki/state/execution-batches",
    ".aiwiki/staging/elixirs",
    ".aiwiki/staging/proposals/prompt",
    ".aiwiki/staging/proposals/policy",
    ".aiwiki/staging/proposals/judge",
    ".aiwiki/derived/agents",
    ".aiwiki/derived/packs/review",
    ".aiwiki/derived/packs/decision-memos",
    ".aiwiki/derived/packs/sop-drafts",
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
            "- [协议规则](./protocols/index.md)",
            "- `schema/policies/` 是 L3 policy proposal 的唯一 policy 写回目标目录。",
            "",
            "## 边界",
            "",
            "- `AGENTS.md` 是仓库/开发侧 agent protocol SoT。",
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
            "- `review-queue.md` 和 `repair-backlog.md` 应把 overdue / escalation 候选项显式展示出来。",
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
    "wiki/indexes/protocols.md": "\n".join(
        [
            "# 协议总览",
            "",
            "这里是统一炼丹炉的协议入口页。",
            "",
            "- 当前 runtime 只有 `general` 协议。",
            "- 具体规则落在 `schema/protocols/general/`。",
            "- 这里展示的是单 runtime 入口，而不是多套 protocol slug 分叉。",
        ]
    )
    + "\n",
    "wiki/indexes/review-center.md": "\n".join(
        [
            "# 审阅中心",
            "",
            "这里是炼丹炉的人用审阅入口，负责把 pending review、aging、repair 和 concept rewrite 收拢到一个地方。",
            "",
            "## 先看哪里",
            "",
            "- [审阅队列](./review-queue.md)：处理 `decision / judgment` 的状态推进",
            "- [概念质量](./concept-quality.md)：看弱概念、冲突信号、证据缺口、重写优先级",
            "- [认知历史](./cognitive-history.md)：看 reviewed judgment 是否因证据变化需要拉回复审",
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
    "wiki/indexes/furnace-center.md": "\n".join(
        [
            "# 炉心面板",
            "",
            "这里是炼丹炉的人用统一入口，负责把今天最该处理的 review、repair、graph 和 output 收到一个地方。",
            "",
            "## 先看哪里",
            "",
            "- [审阅中心](./review-center.md)：看 pending review、aging、rewrite 和 ready action",
            "- [认知历史](./cognitive-history.md)：看旧判断是否被新证据挑战",
            "- [图谱视图](./graph-view.md)：看证据链与机器记忆邻接说明",
            "- [修复待办](./repair-backlog.md)：看 nightly 汇总出的优先级队列",
            "- [协议总览](./protocols.md)：看当前 active protocol",
            "",
            "## 怎么用",
            "",
            "1. 先看今天的 ready actions、apply-ready rewrites 和 overdue review。",
            "2. 再看最新 output 是否值得回流成 derived / decision / judgment。",
            "3. 需要深入时，再跳到 review-center、graph-view 或具体页面。",
            "",
            "## 边界",
            "",
            "- 这是统一入口，不替代各自的专业页面。",
            "- 高风险修复仍然停留在 proposal / review 层，不会从这里直接自动 apply。",
        ]
    )
    + "\n",
    "wiki/indexes/execution-audit.md": "\n".join(
        [
            "# 执行审计",
            "",
            "这里是炼丹炉的人用执行审计入口，负责把 execution receipt、revert 历史、policy 分级和协议分布收拢到一个地方。",
            "",
            "## 先看哪里",
            "",
            "- [机器记忆动作队列](./machine-memory-actions.md)：看 action lifecycle 和 ready actions",
            "- [审阅队列](./review-queue.md)：看 pending review 和 aging",
            "- [认知历史](./cognitive-history.md)：对照 judgment drift 和 review history 决定是否升级修复",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和页级 patch plan",
            "",
            "## 怎么用",
            "",
            "1. 先看最近 apply / revert 是否符合预期。",
            "2. 再看 policy bands 是否和当前动作状态一致。",
            "3. 最后看协议分布和 receipt history，确认执行层没有漂移。",
            "",
            "## 边界",
            "",
            "- 这里负责审计，不直接替代 review-queue 或 machine-memory 动作页。",
            "- receipt history 仍然是 file-based，本页展示的是当前快照。",
        ]
    )
    + "\n",
    "wiki/indexes/cognitive-history.md": "\n".join(
        [
            "# 认知历史",
            "",
            "占位索引：reviewed `decision / judgment` 的复审轨迹入口。",
            "",
            "- 动态汇总渲染已退役；以 Today / review-queue / 单页 review history 为准。",
            "- 这里优先看“哪些旧判断被新证据挑战”。",
            "- 这里不自动改状态。",
        ]
    )
    + "\n",
    "wiki/indexes/graph-view.md": "\n".join(
        [
            "# 证据链 / 机器记忆邻接",
            "",
            "炼丹炉有两种图谱视角，用途不同，不要混用。",
            "默认工作流仍然是先看报告和 Today；普通读报告不需要打开本页。",
            "",
            "## 证据关系图（Obsidian 原生 Graph，主路径）",
            "",
            "- **入口**：Obsidian 侧边栏 Graph；枢纽页 [证据关系总览](../evidence-graph.md)。",
            "- **节点**：`output/reports`、`wiki/sources`、`raw/inbox`；协议下可有 `wiki/judgments`。",
            "- **边**：报告 → 来源页 → 原料笔记；**不含** `wiki/concepts` / `wiki/elixirs` / `wiki/derived` / `wiki/indexes` / `raw/assets`。",
            "- **严谨默认**：隐藏未解析链接与孤儿节点，避免投料正文里的相对路径（如 `.nvmrc`）污染图谱。",
            "- **用途**：回答“这份报告引用了哪些证据”，而不是浏览概念网络。",
            "- **默认行为**：打开 Obsidian Graph 即是证据关系图，无需手动筛选；compile / 打开 vault 自动恢复配置。",
            "",
            "## 机器记忆邻接（JSON 导出，维护/调试）",
            "",
            "- **入口**：`.aiwiki/cache/machine-memory-graph.json`（compile 写入的全量邻接导出）。",
            "- **节点**：来源、概念、判断、金丹等机器记忆资产。",
            "- **关系**：材料提到概念、概念相关、因果关系等机器记忆关系。",
            "- **说明**：HTML 图谱页已停写；人读证据链优先 Obsidian Graph 与 Today，JSON 供维护、对账或外部工具读取。",
            "- **维护**：[概念质量](./concept-quality.md)、[机器记忆索引](./machine-memory.md)",
            "",
            "1. 先看报告和 Today。",
            "2. 查证据链 → Obsidian Graph 或 `wiki/evidence-graph.md`。",
            "3. 需要机器记忆邻接数据 → `.aiwiki/cache/machine-memory-graph.json`。",
            "",
            "## 边界",
            "",
            "- Obsidian 证据链 ≠ 机器记忆 JSON 导出。",
            "- 概念页是机器记忆索引，不是原料副本。",
        ]
    )
    + "\n",
}

# Dashboard files that are static templates at runtime and should be refreshed
# by compile. Dynamic owner pages (protocols, furnace/execution centers,
# cognitive history, packs, pilots, etc.) are intentionally excluded so compile
# accounting does not count transient template rewrites before owner renderers
# restore the same final content.
MANAGED_DASHBOARD_TEMPLATE_FILES = (
    "wiki/indexes/review-center.md",
    "wiki/indexes/graph-view.md",
)


CURATED_ASSET_SECTION_ORDER = (
    "Counter Evidence",
    "Invalidation",
    "Next Signals",
    "Review History",
)


PROTOCOL_SECTION_FILES = ("taxonomy", "decision", "judgment", "review", "nightly", "query")


PROTOCOL_SECTION_TITLES = {
    "taxonomy": "分类规则",
    "decision": "决策模板",
    "judgment": "判断模板",
    "review": "审阅策略",
    "nightly": "Nightly 策略",
    "query": "查询提示",
}


__all__ = [
    "CURATED_ASSET_SECTION_ORDER",
    "DEFAULT_DASHBOARD_FILES",
    "DEFAULT_SCHEMA_FILES",
    "LAYOUT_DIRS",
    "MANAGED_DASHBOARD_TEMPLATE_FILES",
    "PROTOCOL_SECTION_FILES",
    "PROTOCOL_SECTION_TITLES",
]
