"""Protocol/runtime base extracted from aiwiki.app."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import LLMConfig

from .app_utils import (
    parse_iso_datetime,
    relative_path,
)

from .app_state import (
    DEFAULT_PROTOCOL,
    load_json_document,
    manifest_path,
)
from .app_types import ProtocolDescriptor, ProtocolState

LAYOUT_DIRS = (
    "raw/inbox",
    "raw/normalized",
    "raw/assets",
    "schema",
    "schema/protocols",
    "wiki/sources",
    "wiki/concepts",
    "wiki/rewrite-proposals",
    "wiki/decisions",
    "wiki/judgments",
    "wiki/indexes",
    "wiki/derived",
    "output/reports",
    "output/slides",
    "output/figures",
    "output/agents",
    "output/packs/review",
    "output/packs/decision-memos",
    "output/packs/sop-drafts",
    "output/pilots",
    "output/graph",
    "output/control",
    "output/review",
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
            "- [协议规则](./protocols/index.md)",
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
    "wiki/indexes/protocols.md": "\n".join(
        [
            "# 协议总览",
            "",
            "这里是统一炼丹炉的协议入口页。",
            "",
            "- 当前 active protocol 会在 `compile` 后写到这里。",
            "- 具体规则落在 `schema/protocols/`。",
            "- 这里展示的是“一个统一炉子，多种领域协议”的运行时入口，而不是新的 runtime 分叉。",
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
            "- [Aging 报告](./aging-report.md)：看 overdue 和 escalation",
            "- [概念质量](./concept-quality.md)：看弱概念、冲突信号、证据缺口、重写优先级",
            "- [认知历史](./cognitive-history.md)：看 reviewed judgment 是否因证据变化需要拉回复审",
            "- [机器记忆动作队列](./machine-memory-actions.md)：看 machine-memory action lifecycle",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和 execution proposal",
            "- [修复待办](./repair-backlog.md)：看 nightly 汇总出来的优先级队列",
            "- [本地审阅面板](../../output/review/review-center.html)：直接看审阅 cockpit",
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
            "- [图谱视图](./graph-view.md)：看 machine-memory 图层和 graph health",
            "- [修复待办](./repair-backlog.md)：看 nightly 汇总出的优先级队列",
            "- [协议总览](./protocols.md)：看当前 active protocol",
            "- [本地炉心面板](../../output/control/furnace-center.html)：直接看统一控制面板",
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
    "wiki/indexes/execution-center.md": "\n".join(
        [
            "# 执行中心",
            "",
            "这里是炼丹炉的人用执行入口，负责把 repair action、page-level patch plan 和 safe apply 候选收拢到一个地方。",
            "",
            "## 先看哪里",
            "",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch、proposal 和 patch plan",
            "- [机器记忆动作队列](./machine-memory-actions.md)：看 action lifecycle 和 ready actions",
            "- [审阅中心](./review-center.md)：看 aging、rewrite 和 pending review",
            "- [认知历史](./cognitive-history.md)：看哪些 judgment 已因证据漂移需要拉回复审",
            "- [执行审计](./execution-audit.md)：看 apply / revert 历史和策略分级",
            "- [炉心面板](./furnace-center.md)：看统一产品壳入口",
            "- [本地执行面板](../../output/control/execution-center.html)：直接看执行 cockpit",
            "",
            "## 怎么用",
            "",
            "1. 先看 accepted 的 safe apply action。",
            "2. 再看 execution proposal 和 page-level patch plan。",
            "3. 需要深入时，再跳到具体 proposal 页面或目标页面。",
            "",
            "## 边界",
            "",
            "- 这里优先展示 reviewable execution plan，不自动 apply 高风险修复。",
            "- safe apply 仍只覆盖 allowlist 内的低风险动作。",
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
            "- [执行中心](./execution-center.md)：看当前 ready action、proposal 和 patch plan",
            "- [认知历史](./cognitive-history.md)：对照 judgment drift 和 review history 决定是否升级修复",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和页级 patch plan",
            "- [机器记忆动作队列](./machine-memory-actions.md)：看 action lifecycle 和 policy",
            "- [本地执行审计面板](../../output/control/execution-audit.html)：直接看 execution audit cockpit",
            "",
            "## 怎么用",
            "",
            "1. 先看最近 apply / revert 是否符合预期。",
            "2. 再看 policy bands 是否和当前动作状态一致。",
            "3. 最后看协议分布和 receipt history，确认执行层没有漂移。",
            "",
            "## 边界",
            "",
            "- 这里负责审计，不直接替代 execution-center。",
            "- receipt history 仍然是 file-based，本页展示的是当前快照。",
        ]
    )
    + "\n",
    "wiki/indexes/cognitive-history.md": "\n".join(
        [
            "# 认知历史",
            "",
            "这里会汇总 reviewed `decision / judgment` 的复审轨迹、证据漂移和长历史页面。",
            "",
            "- compile 后会自动刷新。",
            "- 这里优先看“哪些旧判断被新证据挑战”。",
            "- 这里不自动改状态，只做检测、索引和提醒。",
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
    "wiki/indexes/agent-workbench.md": "\n".join(
        [
            "# Agent Workbench",
            "",
            "这里会汇总炼丹炉当前可生成的 agent packs。",
            "",
            "- compile 后会把 agent packs 写到 `output/agents/`。",
            "- 这些 pack 是给单人 owner + 多 agent 工作小组的工作单。",
            "- 这里先做人用总览，不直接执行 agent。",
        ]
    )
    + "\n",
    "wiki/indexes/output-packs.md": "\n".join(
        [
            "# 输出 Pack 总览",
            "",
            "这里会汇总 compile 生成的稳定 pack 产物。",
            "",
            "- `review packs` 会把待审 / 漂移 / aging 页面导出成可直接审阅的工作单。",
            "- `decision memos` 会把已审 decision / judgment 导出成稳定 memo。",
            "- `SOP drafts` 会把 ready action / execution proposal 导出成可执行草案。",
            "- 这些 pack 先保持 deterministic markdown 产物，不引入新的 runtime 执行器。",
        ]
    )
    + "\n",
    "wiki/indexes/domain-pilots.md": "\n".join(
        [
            "# 领域 Pilot 总览",
            "",
            "这里会汇总 compile 生成的协议 pilot scorecard。",
            "",
            "- `output/pilots/*.md` 会按协议生成高密度场景压实的 deterministic scorecard。",
            "- scorecard 负责回答：这个协议现在处于 seed / building / compounding 的哪一档。",
            "- 它们不会改变 runtime，只负责把协议运行密度、判断资产和执行信号收拢成可追踪入口。",
        ]
    )
    + "\n",
}


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


PROTOCOL_LIBRARY = {
    "general": {
        "title": "通用协议",
        "summary": "默认的跨域协议，适合把事实、综合、判断和复审保持分层。",
        "focus": [
            "保持 raw evidence、wiki synthesis 和 decision/judgment 分层。",
            "优先记录证据、冲突和下一次复审窗口。",
        ],
        "taxonomy": [
            "concept 以稳定主题、对象或机制命名。",
            "decision 用来记录明确动作，judgment 用来记录可复用判断。",
            "跨域内容默认先落在通用概念，再按需要引用到具体协议。",
        ],
        "decision": [
            "记录决定了什么、为什么、依据是什么、何时复审。",
            "明确失效条件和后续观察信号。",
        ],
        "judgment": [
            "记录判断、证据、反证、置信度和观察窗口。",
            "不把猜测伪装成事实；证据薄弱时直接写出来。",
        ],
        "review": [
            "优先清理 overdue / escalation 项，再审新产生的 decision/judgment。",
            "高风险结论默认保持 tentative / proposed，直到证据稳定。",
        ],
        "nightly": [
            "关注 pending review、aging、repair backlog、concept rewrite。",
            "把 recurring outputs 保守晋升到 decision/judgment。",
        ],
        "query": [
            "优先引用 `wiki/sources/*.md` 和稳定 concept page。",
            "把不确定性和冲突显式写入产物，不做静默补洞。",
        ],
    },
    "investing": {
        "title": "投资协议",
        "summary": "面向 thesis、risk、catalyst、invalidation 和 position decision 的协议。",
        "focus": [
            "围绕 company / thesis / catalyst / risk / invalidation 组织知识。",
            "把判断形成、证据变化和 thesis 失效条件记录清楚。",
        ],
        "taxonomy": [
            "concept 优先围绕 company、industry、moat、valuation、risk factor。",
            "decision 记录观察、建仓、加仓、减仓、否决等动作。",
            "judgment 记录 thesis、预期、概率、风险边界。",
        ],
        "decision": [
            "必须写清动作、仓位/范围、触发条件和失效条件。",
            "把关键证据、反证和下一次财报/事件复审时间写清楚。",
        ],
        "judgment": [
            "写清 thesis、drivers、catalysts、risks、invalidation、confidence。",
            "对定性结论保持时间标签，避免把旧判断当成常量。",
        ],
        "review": [
            "重点审 earnings、guidance、监管、估值和 thesis drift。",
            "高风险判断默认更短 review window。",
        ],
        "nightly": [
            "优先抬升 thesis drift、risk escalation、待复审 company judgment。",
            "对重复出现的投研输出保守晋升，不直接代替投资决策。",
        ],
        "query": [
            "默认要求结论回指 source page，并显式标记 bull / bear evidence。",
            "鼓励把 thesis 与 invalidation 并列呈现。",
        ],
    },
    "research": {
        "title": "研发协议",
        "summary": "面向 paper、repo、benchmark、experiment 和 architecture decision 的协议。",
        "focus": [
            "围绕 paper / repo / benchmark / experiment / architecture decision 组织知识。",
            "让实验结果、失败记录和设计取舍持续沉淀。",
        ],
        "taxonomy": [
            "concept 优先围绕机制、系统瓶颈、算法、benchmark、failure mode。",
            "decision 记录 adopt / reject / defer / rollback 这类工程动作。",
            "judgment 记录 tradeoff、hypothesis、risk、expected gain。",
        ],
        "decision": [
            "写清楚要不要采用、影响面、依赖、回滚路径和验证方式。",
            "把成功指标和回归风险显式写出来。",
        ],
        "judgment": [
            "写清对方法、架构或实验结果的判断及其置信度。",
            "显式列出 supporting evidence、counter evidence、open questions。",
        ],
        "review": [
            "重点审 regression、benchmark drift、过期实验结论和架构取舍。",
            "待确认实验结论保留更高 revisit 频率。",
        ],
        "nightly": [
            "优先抬升 weak concepts、failed experiments、regression signals。",
            "把 recurring outputs 晋升成 architecture decision 或 engineering judgment。",
        ],
        "query": [
            "优先对比 benchmark、experiment 和 architecture tradeoff。",
            "答案里要同时指出 evidence、regression risk 和 next experiment。",
        ],
    },
    "product": {
        "title": "产品协议",
        "summary": "面向 user problem、insight、bet、metric 和 launch judgment 的协议。",
        "focus": [
            "围绕 user problem / insight / bet / metric / launch judgment 组织知识。",
            "把用户信号、产品假设、验证结果和发布判断持续沉淀。",
        ],
        "taxonomy": [
            "concept 优先围绕 user problem、segment、funnel、feature、metric、launch risk。",
            "decision 记录 prioritize / launch / rollback / deprecate / resource bet 这类动作。",
            "judgment 记录 insight、bet、expected impact、validation gap、launch readiness。",
        ],
        "decision": [
            "写清动作、目标用户、影响指标、验证方式和回滚条件。",
            "把依赖、上线窗口和风险前提显式写出来。",
        ],
        "judgment": [
            "写清 user problem、insight、bet、evidence、counter evidence 和 confidence。",
            "把验证缺口和下一次 release / review 窗口一起记录。",
        ],
        "review": [
            "重点审 metric drift、launch readiness、核心 bet 变化和用户信号反转。",
            "对发布前判断保持更短的 revisit window。",
        ],
        "nightly": [
            "优先抬升 metric regression、launch blockers、未验证 bet 和待复查判断。",
            "把 recurring outputs 晋升成 product decision 或 product judgment。",
        ],
        "query": [
            "优先组织成 user problem / insight / bet / metric / launch risk。",
            "答案里要显式区分 evidence、assumption 和 next validation。",
        ],
    },
    "ops": {
        "title": "运维协议",
        "summary": "面向 incident、runbook、mitigation、escalation 和 follow-up 的协议。",
        "focus": [
            "围绕 incident / mitigation / escalation / runbook / follow-up 组织知识。",
            "把处置动作、根因判断、影响范围和复盘结论持续沉淀。",
        ],
        "taxonomy": [
            "concept 优先围绕 incident type、service、dependency、blast radius、runbook、failure mode。",
            "decision 记录 mitigate / rollback / failover / isolate / escalate / follow-up owner。",
            "judgment 记录 root cause hypothesis、capacity risk、recurrence risk、operational debt。",
        ],
        "decision": [
            "写清楚处置动作、影响范围、回滚条件、owner 和升级链路。",
            "把恢复目标、验证信号和 follow-up 时间窗口写清楚。",
        ],
        "judgment": [
            "写清根因判断、证据、反证、blast radius、residual risk 和 confidence。",
            "保留 incident 时间标签，避免旧结论跨事件复用。",
        ],
        "review": [
            "重点审 incident recurrence、SLO drift、runbook 老化和升级滞后。",
            "未确认根因的判断默认极短 revisit window。",
        ],
        "nightly": [
            "优先抬升 unresolved incident judgment、runbook drift、capacity risk 和 follow-up debt。",
            "把 recurring outputs 晋升成 incident decision 或 ops judgment。",
        ],
        "query": [
            "优先组织成 incident timeline / blast radius / mitigation / root cause / follow-up。",
            "答案里要同时指出当前缓解、残余风险和下一次复查点。",
        ],
    },
}


PROTOCOL_REVIEW_WINDOWS: dict[str, dict[tuple[str, str], tuple[int, int]]] = {
    "general": {},
    "investing": {
        ("decision", "proposed"): (3, 7),
        ("decision", "needs-revisit"): (2, 5),
        ("judgment", "tentative"): (3, 7),
        ("judgment", "tracking"): (7, 14),
    },
    "research": {
        ("decision", "proposed"): (5, 14),
        ("decision", "needs-revisit"): (2, 7),
        ("judgment", "tentative"): (4, 10),
        ("judgment", "tracking"): (7, 21),
    },
    "product": {
        ("decision", "proposed"): (4, 10),
        ("decision", "needs-revisit"): (2, 5),
        ("judgment", "tentative"): (3, 7),
        ("judgment", "tracking"): (7, 14),
    },
    "ops": {
        ("decision", "proposed"): (1, 3),
        ("decision", "needs-revisit"): (1, 2),
        ("judgment", "tentative"): (1, 3),
        ("judgment", "tracking"): (3, 7),
    },
}


PROTOCOL_CLASSIFICATION_MARKERS: dict[str, dict[str, tuple[str, ...]]] = {
    "general": {"decision": (), "judgment": ()},
    "investing": {
        "decision": (
            "underwrite",
            "position",
            "sizing",
            "allocate",
            "build",
            "trim",
            "exit",
            "buy",
            "sell",
            "hold",
            "建仓",
            "加仓",
            "减仓",
            "卖出",
            "持有",
            "仓位",
            "配置",
        ),
        "judgment": (
            "thesis",
            "catalyst",
            "invalidation",
            "valuation",
            "earnings",
            "guidance",
            "bull",
            "bear",
            "moat",
            "upside",
            "downside",
            "thesis drift",
            "护城河",
            "催化剂",
            "估值",
            "财报",
            "失效条件",
        ),
    },
    "research": {
        "decision": (
            "adopt",
            "reject",
            "rollback",
            "benchmark",
            "experiment",
            "architecture",
            "regression",
            "integrate",
            "migrate",
            "roll back",
            "采用",
            "回滚",
            "实验",
            "基准",
            "架构",
            "回归",
        ),
        "judgment": (
            "hypothesis",
            "latency",
            "throughput",
            "failure mode",
            "tradeoff",
            "expected gain",
            "bottleneck",
            "open question",
            "假设",
            "延迟",
            "吞吐",
            "瓶颈",
            "失败模式",
            "取舍",
            "开放问题",
        ),
    },
    "product": {
        "decision": (
            "launch",
            "ship",
            "rollout",
            "prioritize",
            "deprecate",
            "sunset",
            "scope",
            "bet",
            "go-to-market",
            "go no-go",
            "发布",
            "上线",
            "灰度",
            "优先级",
            "下线",
            "资源投入",
        ),
        "judgment": (
            "user problem",
            "insight",
            "metric",
            "activation",
            "retention",
            "churn",
            "adoption",
            "funnel",
            "launch readiness",
            "segment",
            "用户问题",
            "洞察",
            "指标",
            "转化",
            "留存",
            "流失",
            "发布准备度",
        ),
    },
    "ops": {
        "decision": (
            "incident",
            "mitigate",
            "rollback",
            "failover",
            "disable",
            "throttle",
            "isolate",
            "escalate",
            "hotfix",
            "containment",
            "事故",
            "缓解",
            "回滚",
            "切流",
            "降级",
            "隔离",
            "升级",
            "热修",
        ),
        "judgment": (
            "root cause",
            "blast radius",
            "recurrence",
            "capacity",
            "dependency",
            "runbook",
            "slo",
            "sla",
            "oncall",
            "operational debt",
            "根因",
            "影响范围",
            "复发",
            "容量",
            "依赖",
            "值班",
            "运行负债",
        ),
    },
}


PROTOCOL_PROMOTION_PREFIXES: dict[str, dict[str, str]] = {
    "general": {"decision": "决策沉淀", "judgment": "判断沉淀"},
    "investing": {"decision": "投资决策沉淀", "judgment": "投资判断沉淀"},
    "research": {"decision": "研发决策沉淀", "judgment": "研发判断沉淀"},
    "product": {"decision": "产品决策沉淀", "judgment": "产品判断沉淀"},
    "ops": {"decision": "运维决策沉淀", "judgment": "运维判断沉淀"},
}


PROTOCOL_FOCUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "general": (),
    "investing": (
        "company",
        "thesis",
        "catalyst",
        "risk",
        "invalidation",
        "valuation",
        "earnings",
        "guidance",
        "moat",
        "position",
        "仓位",
        "财报",
        "估值",
        "护城河",
        "催化剂",
        "失效条件",
    ),
    "research": (
        "paper",
        "repo",
        "benchmark",
        "experiment",
        "architecture",
        "regression",
        "latency",
        "throughput",
        "bottleneck",
        "failure mode",
        "tradeoff",
        "实验",
        "基准",
        "架构",
        "回归",
        "延迟",
        "吞吐",
        "瓶颈",
    ),
    "product": (
        "user problem",
        "insight",
        "bet",
        "metric",
        "launch",
        "rollout",
        "retention",
        "activation",
        "adoption",
        "funnel",
        "segment",
        "north star",
        "用户问题",
        "洞察",
        "指标",
        "发布",
        "灰度",
        "留存",
        "转化",
    ),
    "ops": (
        "incident",
        "mitigation",
        "rollback",
        "failover",
        "runbook",
        "root cause",
        "blast radius",
        "dependency",
        "capacity",
        "slo",
        "sla",
        "事故",
        "缓解",
        "回滚",
        "切流",
        "根因",
        "影响范围",
        "依赖",
        "容量",
    ),
}


PROTOCOL_ACTION_KIND_WEIGHTS: dict[str, dict[str, int]] = {
    "general": {},
    "investing": {
        "split-overloaded-concept": 2,
        "add-source-concept-link": 1,
        "monitor-bridge-concept": 1,
    },
    "research": {
        "expand-singleton-concept": 2,
        "connect-isolated-source": 2,
        "split-overloaded-concept": 1,
    },
    "product": {
        "split-overloaded-concept": 2,
        "expand-singleton-concept": 1,
        "monitor-bridge-concept": 1,
    },
    "ops": {
        "connect-isolated-source": 2,
        "add-source-concept-link": 2,
        "monitor-bridge-concept": 2,
        "split-overloaded-concept": 1,
    },
}


PROTOCOL_OUTPUT_GUIDANCE: dict[str, dict[str, tuple[str, ...]]] = {
    "general": {
        "report": (
            "先重述问题，再列证据、分歧、缺口和下一步问题。",
            "不要把猜测写成事实。",
        ),
        "decision-memo": (
            "优先组织成结论、证据、反证、失效条件和下一次复核信号。",
        ),
        "sop": (
            "优先组织成前置检查、步骤、风险控制、回滚和复盘记录。",
        ),
        "slides": (
            "每页都保留引用和关键不确定性。",
        ),
        "figure": (
            "图表应强调变量关系、假设和证据边界。",
        ),
    },
    "investing": {
        "report": (
            "优先组织成 thesis / bull-bear evidence / catalysts / risks / invalidation。",
            "把时间窗口和下一次财报或事件复审写清楚。",
        ),
        "decision-memo": (
            "优先突出 thesis、bull-bear evidence、position sizing guardrail、risk 和 invalidation。",
        ),
        "sop": (
            "优先突出检查仓位、催化剂窗口、风控阈值和复盘步骤。",
        ),
        "slides": (
            "优先呈现 thesis、估值/风险、催化剂和失效条件。",
        ),
        "figure": (
            "优先做 thesis、估值、风险或催化剂的对比图，而不是泛泛总结图。",
        ),
    },
    "research": {
        "report": (
            "优先组织成 benchmark / experiment / tradeoff / regression risk / next experiment。",
            "把 open questions 和验证条件写清楚。",
        ),
        "decision-memo": (
            "优先突出假设、实验信号、反例、回归风险和下一轮验证。",
        ),
        "sop": (
            "优先突出实验准备、执行步骤、度量口径、回滚和复现实验。",
        ),
        "slides": (
            "优先呈现 benchmark、架构取舍、回归风险和下一步实验。",
        ),
        "figure": (
            "优先做 benchmark、latency/throughput、tradeoff 或 regression signal 图。",
        ),
    },
    "product": {
        "report": (
            "优先组织成 user problem / insight / bet / metric / launch risk / next validation。",
            "把关键假设、受影响用户和下一次验证窗口写清楚。",
        ),
        "decision-memo": (
            "优先突出用户问题、核心 bet、指标、发布风险和验证窗口。",
        ),
        "sop": (
            "优先突出发布前检查、执行步骤、监控指标、回退和复盘。",
        ),
        "slides": (
            "优先呈现 user problem、关键 insight、核心 bet、metric 和 launch readiness。",
        ),
        "figure": (
            "优先做 funnel、retention、segment、metric delta 或 launch risk 图。",
        ),
    },
    "ops": {
        "report": (
            "优先组织成 incident timeline / blast radius / mitigation / root cause / follow-up。",
            "把当前缓解状态、残余风险和下一次复查窗口写清楚。",
        ),
        "decision-memo": (
            "优先突出影响范围、缓解方案、残余风险、失效条件和 follow-up owner。",
        ),
        "sop": (
            "优先突出告警前置检查、处置步骤、升级路径、回滚和复盘记录。",
        ),
        "slides": (
            "优先呈现事故时间线、影响范围、缓解动作、根因判断和 follow-up。",
        ),
        "figure": (
            "优先做 incident timeline、capacity、dependency 或 SLO drift 图。",
        ),
    },
}


PROTOCOL_EXECUTION_POLICY_RULES: dict[str, dict[str, dict[str, Any]]] = {
    "general": {
        "add-source-concept-link": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "低风险补链可直接走 safe apply，再让 compile 收敛页面链接。",
        },
        "refresh-citation-snapshots": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "只刷新 citation snapshot metadata，不改正文判断，可直接自动修复。",
        },
        "connect-isolated-source": {
            "decision": "review",
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "capabilities": ("manual-edit", "review", "history"),
            "policy_summary": "涉及概念接入判断，先 review 再人工修复。",
        },
        "expand-singleton-concept": {
            "decision": "review",
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "capabilities": ("manual-edit", "review", "history"),
            "policy_summary": "会改 concept synthesis，保留人工 review 边界。",
        },
        "split-overloaded-concept": {
            "decision": "review",
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "capabilities": ("manual-edit", "review", "history"),
            "policy_summary": "概念拆分属于高影响动作，只允许人工修复。",
        },
        "monitor-bridge-concept": {
            "decision": "review",
            "execution_policy": "manual-repair",
            "execution_band": "review-first",
            "capabilities": ("review", "history"),
            "policy_summary": "桥接概念只给观察与 review 建议，不直接自动执行。",
        },
    },
    "investing": {
        "add-source-concept-link": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "仅允许 provenance 明确的低风险补链自动执行，避免 thesis 页面静默漂移。",
        },
        "refresh-citation-snapshots": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "可自动刷新 citation snapshot，但不自动改变 thesis / risk 结论。",
        },
    },
    "research": {
        "add-source-concept-link": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "实验 provenance 明确时允许自动补链，加快 benchmark / concept 收敛。",
        },
        "refresh-citation-snapshots": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "可自动刷新实验引用快照，不直接改 benchmark judgment。",
        },
    },
    "product": {
        "add-source-concept-link": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "低风险补链可自动执行，但 launch / metric 判断仍停在 review。",
        },
        "refresh-citation-snapshots": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "可自动刷新用户信号 snapshot，不自动改发布判断。",
        },
    },
    "ops": {
        "add-source-concept-link": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "低风险补链可自动执行，但 incident judgment 与 runbook 结论仍需人工 review。",
        },
        "refresh-citation-snapshots": {
            "decision": "allow",
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ("dry-run", "bundle-apply", "revert-safe", "history"),
            "policy_summary": "可自动刷新 incident citation snapshot，避免 review 基线继续漂移。",
        },
    },
}


PROTOCOL_QUERY_ROUTE_CONFIG: dict[str, dict[str, Any]] = {
    "general": {
        "default_strategy": "concept-first",
        "strategy_order": ("concept-first", "graph-walk", "source-first"),
        "source_markers": ("source", "citation", "quote", "file", "raw", "证据", "引用", "来源", "原文"),
        "graph_markers": ("why", "how", "impact", "dependency", "relationship", "root cause", "为什么", "因果", "关系", "根因"),
    },
    "investing": {
        "default_strategy": "concept-first",
        "strategy_order": ("concept-first", "graph-walk", "source-first"),
        "source_markers": ("filing", "10-k", "earnings", "transcript", "财报", "电话会", "指引"),
        "graph_markers": ("catalyst", "driver", "risk", "invalidation", "催化剂", "驱动", "风险", "失效"),
    },
    "research": {
        "default_strategy": "source-first",
        "strategy_order": ("source-first", "graph-walk", "concept-first"),
        "source_markers": ("benchmark", "experiment", "latency", "throughput", "日志", "实验", "基准", "性能"),
        "graph_markers": ("tradeoff", "regression", "dependency", "bottleneck", "取舍", "回归", "瓶颈"),
    },
    "product": {
        "default_strategy": "concept-first",
        "strategy_order": ("concept-first", "source-first", "graph-walk"),
        "source_markers": ("interview", "ticket", "feedback", "session", "访谈", "反馈", "工单", "埋点"),
        "graph_markers": ("funnel", "retention", "segment", "metric", "漏斗", "留存", "分群", "指标"),
    },
    "ops": {
        "default_strategy": "graph-walk",
        "strategy_order": ("graph-walk", "source-first", "concept-first"),
        "source_markers": ("log", "trace", "incident", "alert", "日志", "告警", "事件", "trace"),
        "graph_markers": ("dependency", "blast radius", "rollback", "root cause", "依赖", "影响面", "回滚", "根因"),
    },
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


REWRITE_PROPOSAL_STATUSES = ("proposed", "accepted", "deferred", "applied", "rejected")


ACTIVE_CORPUS_STATUSES = ("active", "cooling", "expired")


ARCHIVE_CANDIDATE_STATUSES = ("suggested", "deferred", "ready", "reactivated")


PENDING_DECISION_REVIEW_STATUSES = {"proposed", "needs-revisit"}


PENDING_JUDGMENT_REVIEW_STATUSES = {"tentative", "tracking"}


PENDING_ACTION_STATUSES = {"proposed", "accepted", "deferred"}


PENDING_REWRITE_PROPOSAL_STATUSES = {"proposed", "accepted", "deferred"}


LOW_RISK_APPLYABLE_ACTION_KINDS = {"add-source-concept-link"}


ACTIVE_CORPUS_TTL = timedelta(days=3)


ARCHIVE_QUERY_STALE_AFTER = timedelta(days=14)


EXECUTION_BAND_LABELS = {
    "review-first": "先审后动",
    "manual-repair": "人工修复",
    "bundle-safe-apply": "bundle 安全执行",
    "deferred": "暂缓观察",
    "closed": "已关闭",
    "history-only": "历史归档",
}


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


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema(root)
    ensure_protocol_scaffold(root)
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


def protocol_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "protocol.json"


def default_protocol_state() -> ProtocolState:
    return {"version": 1, "active_protocol": DEFAULT_PROTOCOL}


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


def protocol_runtime_schema_path(root: Path, slug: str) -> Path:
    return root / "schema" / "protocols" / slug / "runtime.yaml"


def default_protocol_runtime_schema(slug: str) -> dict[str, Any]:
    metadata = PROTOCOL_LIBRARY[slug]
    review_windows = {
        f"{kind}:{status}": [window[0], window[1]]
        for (kind, status), window in PROTOCOL_REVIEW_WINDOWS.get(slug, {}).items()
    }
    execution_policy_rules = dict(PROTOCOL_EXECUTION_POLICY_RULES.get(DEFAULT_PROTOCOL, {}))
    execution_policy_rules.update(PROTOCOL_EXECUTION_POLICY_RULES.get(slug, {}))
    route_config = dict(PROTOCOL_QUERY_ROUTE_CONFIG.get(DEFAULT_PROTOCOL, {}))
    route_config.update(PROTOCOL_QUERY_ROUTE_CONFIG.get(slug, {}))
    return {
        "version": 1,
        "slug": slug,
        "title": metadata["title"],
        "summary": metadata["summary"],
        "review_windows": review_windows,
        "output_guidance": {
            output_format: list(lines)
            for output_format, lines in PROTOCOL_OUTPUT_GUIDANCE.get(slug, PROTOCOL_OUTPUT_GUIDANCE[DEFAULT_PROTOCOL]).items()
        },
        "execution_policy": {
            "accepted_rules": execution_policy_rules,
        },
        "query_routes": {
            "default_strategy": str(route_config.get("default_strategy") or "concept-first"),
            "strategy_order": list(route_config.get("strategy_order") or ["concept-first", "graph-walk", "source-first"]),
            "source_markers": list(route_config.get("source_markers") or []),
            "graph_markers": list(route_config.get("graph_markers") or []),
        },
    }


def load_protocol_runtime_schema(root: Path, slug: str) -> dict[str, Any]:
    path = protocol_runtime_schema_path(root, slug)
    default_schema = default_protocol_runtime_schema(slug)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return default_schema
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_schema
    if not isinstance(payload, dict):
        return default_schema
    merged = dict(default_schema)
    merged.update({key: value for key, value in payload.items() if key in merged})
    output_guidance = payload.get("output_guidance")
    if isinstance(output_guidance, dict):
        merged["output_guidance"] = {
            key: list(value)
            for key, value in output_guidance.items()
            if isinstance(key, str) and isinstance(value, list)
        }
    execution_policy = payload.get("execution_policy")
    if isinstance(execution_policy, dict):
        accepted_rules = execution_policy.get("accepted_rules")
        if isinstance(accepted_rules, dict):
            merged["execution_policy"] = {
                "accepted_rules": {
                    key: dict(value)
                    for key, value in accepted_rules.items()
                    if isinstance(key, str) and isinstance(value, dict)
                }
            }
    query_routes = payload.get("query_routes")
    if isinstance(query_routes, dict):
        merged["query_routes"] = {
            "default_strategy": str(query_routes.get("default_strategy") or merged["query_routes"]["default_strategy"]),
            "strategy_order": [
                str(item)
                for item in query_routes.get("strategy_order", merged["query_routes"]["strategy_order"])
                if isinstance(item, str) and item
            ],
            "source_markers": [
                str(item)
                for item in query_routes.get("source_markers", merged["query_routes"]["source_markers"])
                if isinstance(item, str) and item
            ],
            "graph_markers": [
                str(item)
                for item in query_routes.get("graph_markers", merged["query_routes"]["graph_markers"])
                if isinstance(item, str) and item
            ],
        }
    review_windows = payload.get("review_windows")
    if isinstance(review_windows, dict):
        merged["review_windows"] = {
            str(key): [int(value[0]), int(value[1])]
            for key, value in review_windows.items()
            if isinstance(key, str)
            and isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, int) for item in value)
        }
    return merged


def ensure_protocol_scaffold(root: Path) -> None:
    base = root / "schema" / "protocols"
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "index.md"
    if not index_path.exists():
        index_path.write_text(render_protocol_library_index(), encoding="utf-8")
    for slug in sorted(PROTOCOL_LIBRARY):
        runtime_schema = protocol_runtime_schema_path(root, slug)
        runtime_schema.parent.mkdir(parents=True, exist_ok=True)
        if not runtime_schema.exists():
            runtime_schema.write_text(
                json.dumps(default_protocol_runtime_schema(slug), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        overview = base / slug / "index.md"
        overview.parent.mkdir(parents=True, exist_ok=True)
        if not overview.exists():
            overview.write_text(render_protocol_overview(slug), encoding="utf-8")
        for section in PROTOCOL_SECTION_FILES:
            path = base / slug / f"{section}.md"
            if not path.exists():
                path.write_text(render_protocol_section(slug, section), encoding="utf-8")
    state = protocol_state_path(root)
    if not state.exists():
        state.write_text(json.dumps(default_protocol_state(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def available_protocols(root: Path) -> list[str]:
    ensure_protocol_scaffold(root)
    protocols: list[str] = []
    for path in sorted((root / "schema" / "protocols").glob("*/index.md")):
        protocols.append(path.parent.name)
    return protocols


def protocol_descriptor(root: Path, slug: str) -> ProtocolDescriptor:
    base = root / "schema" / "protocols" / slug
    return {
        "slug": slug,
        "title": protocol_title(slug),
        "summary": protocol_summary(slug),
        "paths": {
            "index": relative_path(root, base / "index.md"),
            **{section: relative_path(root, base / f"{section}.md") for section in PROTOCOL_SECTION_FILES},
        },
    }


def load_protocol_state(root: Path) -> ProtocolState:
    ensure_protocol_scaffold(root)
    path = protocol_state_path(root)
    state = load_json_document(path) if path.exists() else default_protocol_state()
    available = available_protocols(root)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active not in available:
        active = DEFAULT_PROTOCOL if DEFAULT_PROTOCOL in available else (available[0] if available else DEFAULT_PROTOCOL)
    normalized = {"version": 1, "active_protocol": active}
    if state != normalized:
        path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **normalized,
        "available_protocols": available,
        "protocols": [protocol_descriptor(root, slug) for slug in available],
        "state_path": relative_path(root, path),
    }


def resolve_protocol(root: Path, protocol: str | None = None) -> str:
    state = load_protocol_state(root)
    if protocol is None:
        return state["active_protocol"]
    candidate = protocol.strip().lower()
    if candidate not in state["available_protocols"]:
        available = ", ".join(state["available_protocols"])
        raise ValueError(f"Unknown protocol: {protocol}. Available protocols: {available}")
    return candidate


def protocol_runtime_summary(slug: str) -> list[str]:
    windows = PROTOCOL_REVIEW_WINDOWS.get(slug, {})
    lines = [f"- 默认协议：`{slug}` ({protocol_title(slug)})"]
    if not windows:
        lines.append("- Review window：沿通用默认窗口。")
    else:
        lines.append("- Review window overrides:")
        for (kind, status), (revisit_days, escalate_days) in sorted(windows.items()):
            lines.append(
                f"  - `{kind}:{status}` -> revisit `{revisit_days}`d / escalate `{escalate_days}`d"
            )
    prefixes = PROTOCOL_PROMOTION_PREFIXES.get(slug, PROTOCOL_PROMOTION_PREFIXES[DEFAULT_PROTOCOL])
    lines.append(
        f"- Auto-promotion 标题前缀：decision `{prefixes['decision']}` / judgment `{prefixes['judgment']}`"
    )
    review_focus = PROTOCOL_LIBRARY.get(slug, {}).get("review", [])
    nightly_focus = PROTOCOL_LIBRARY.get(slug, {}).get("nightly", [])
    if review_focus:
        lines.append(f"- Review focus：`{' / '.join(review_focus[:2])}`")
    if nightly_focus:
        lines.append(f"- Nightly focus：`{' / '.join(nightly_focus[:2])}`")
    return lines


def protocol_focus_score(protocol: str, text: str) -> int:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()))
    return sum(1 for marker in PROTOCOL_FOCUS_KEYWORDS.get(protocol, ()) if marker in normalized)


def page_focus_score(active_protocol: str, page: dict[str, str]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(page.get("title") or ""),
                str(page.get("path") or ""),
                str(page.get("status") or ""),
            ]
        ),
    )
    if str(page.get("protocol") or "") == active_protocol:
        score += 10
    return score


def action_focus_score(active_protocol: str, action: dict[str, Any]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(action.get("title") or ""),
                str(action.get("reason") or ""),
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            ]
        ),
    )
    score += PROTOCOL_ACTION_KIND_WEIGHTS.get(active_protocol, {}).get(str(action.get("kind") or ""), 0)
    return score


def entry_focus_score(active_protocol: str, entry: dict[str, Any], summary_or_preview: str) -> int:
    return protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(entry.get("title") or ""),
                str(entry.get("source_type") or ""),
                summary_or_preview,
            ]
        ),
    )


def concept_focus_score(active_protocol: str, title: str, content: str) -> int:
    return protocol_focus_score(active_protocol, f"{title}\n{content}")


def protocol_output_guidance(root: Path, protocol: str, output_format: str) -> tuple[str, ...]:
    default_guidance = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("output_guidance", {})
    protocol_guidance = load_protocol_runtime_schema(root, protocol).get("output_guidance", default_guidance)
    if not isinstance(default_guidance, dict):
        default_guidance = {}
    if not isinstance(protocol_guidance, dict):
        protocol_guidance = default_guidance
    return tuple(protocol_guidance.get(output_format, default_guidance.get(output_format, ())))


def protocol_execution_policy_rule(root: Path, protocol: str, action_kind: str) -> dict[str, Any]:
    default_rules = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("execution_policy", {}).get("accepted_rules", {})
    protocol_rules = load_protocol_runtime_schema(root, protocol).get("execution_policy", {}).get("accepted_rules", {})
    rule = protocol_rules.get(action_kind) or default_rules.get(action_kind) or {}
    if not isinstance(rule, dict):
        return {}
    return {
        "decision": str(rule.get("decision") or "review"),
        "execution_policy": str(rule.get("execution_policy") or "manual-repair"),
        "execution_band": str(rule.get("execution_band") or "manual-repair"),
        "capabilities": [str(item) for item in rule.get("capabilities", []) if isinstance(item, str) and item],
        "policy_summary": str(rule.get("policy_summary") or ""),
    }


def protocol_query_route_config(root: Path, protocol: str) -> dict[str, Any]:
    default_config = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("query_routes", {})
    protocol_config = load_protocol_runtime_schema(root, protocol).get("query_routes", default_config)
    if not isinstance(default_config, dict):
        default_config = {}
    if not isinstance(protocol_config, dict):
        protocol_config = default_config
    return {
        "default_strategy": str(protocol_config.get("default_strategy") or default_config.get("default_strategy") or "concept-first"),
        "strategy_order": [
            str(item)
            for item in protocol_config.get("strategy_order", default_config.get("strategy_order", []))
            if isinstance(item, str) and item
        ],
        "source_markers": [
            str(item)
            for item in protocol_config.get("source_markers", default_config.get("source_markers", []))
            if isinstance(item, str) and item
        ],
        "graph_markers": [
            str(item)
            for item in protocol_config.get("graph_markers", default_config.get("graph_markers", []))
            if isinstance(item, str) and item
        ],
    }


def protocol_paths(root: Path, protocol: str | None = None) -> list[str]:
    slug = resolve_protocol(root, protocol)
    base = root / "schema" / "protocols" / slug
    paths = [relative_path(root, base / "index.md")]
    paths.extend(relative_path(root, base / f"{section}.md") for section in PROTOCOL_SECTION_FILES)
    return paths


def schedule_review_windows(
    kind: str,
    status: str,
    base_timestamp: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
    root: Path | None = None,
) -> tuple[str, str]:
    windows = AGING_WINDOWS_DAYS.get((kind, status))
    if root is not None:
        runtime_schema = load_protocol_runtime_schema(root, protocol)
        review_windows = runtime_schema.get("review_windows", {}) if isinstance(runtime_schema, dict) else {}
        candidate = review_windows.get(f"{kind}:{status}") if isinstance(review_windows, dict) else None
        if isinstance(candidate, list) and len(candidate) == 2 and all(isinstance(item, int) for item in candidate):
            windows = (candidate[0], candidate[1])
    elif protocol in PROTOCOL_REVIEW_WINDOWS:
        windows = PROTOCOL_REVIEW_WINDOWS.get(protocol, {}).get((kind, status), windows)
    if not windows:
        return "", ""
    base = parse_iso_datetime(base_timestamp) or datetime.now(timezone.utc)
    revisit_days, escalate_days = windows
    revisit_after = (base + timedelta(days=revisit_days)).replace(microsecond=0).isoformat()
    escalate_after = (base + timedelta(days=escalate_days)).replace(microsecond=0).isoformat()
    return revisit_after, escalate_after


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    ensure_layout(root)
    path = manifest_path(root)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
