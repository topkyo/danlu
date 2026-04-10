"""Core application logic for the aiwiki MVP."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import hashlib
import html
import json
import os
import re
import shutil
import threading
import functools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import fcntl

from .config import LLMConfig


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

_RUNTIME_LOCK_GUARD = threading.RLock()
_RUNTIME_LOCKS: dict[str, dict[str, Any]] = {}


def runtime_lock_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime.lock"


@contextmanager
def runtime_write_lock(root: Path):
    resolved_root = str(root.resolve())
    with _RUNTIME_LOCK_GUARD:
        state = _RUNTIME_LOCKS.get(resolved_root)
        if state is not None:
            state["depth"] = int(state.get("depth", 0)) + 1
            handle = state["handle"]
        else:
            lock_path = runtime_lock_path(root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = lock_path.open("a+", encoding="utf-8")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "root": resolved_root,
                        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            _RUNTIME_LOCKS[resolved_root] = {"handle": handle, "depth": 1}
    try:
        yield
    finally:
        with _RUNTIME_LOCK_GUARD:
            state = _RUNTIME_LOCKS.get(resolved_root)
            if state is None:
                return
            state["depth"] = int(state.get("depth", 0)) - 1
            if state["depth"] > 0:
                return
            handle = state["handle"]
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
                _RUNTIME_LOCKS.pop(resolved_root, None)


def runtime_write_operation(func):
    @functools.wraps(func)
    def wrapper(root: Path, *args, **kwargs):
        with runtime_write_lock(root):
            return func(root, *args, **kwargs)

    return wrapper

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

DEFAULT_PROTOCOL = "general"
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
        "slides": (
            "优先呈现事故时间线、影响范围、缓解动作、根因判断和 follow-up。",
        ),
        "figure": (
            "优先做 incident timeline、capacity、dependency 或 SLO drift 图。",
        ),
    },
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
REWRITE_PROPOSAL_STATUSES = ("proposed", "accepted", "deferred", "applied", "rejected")
ACTIVE_CORPUS_STATUSES = ("active", "cooling", "expired")
ARCHIVE_CANDIDATE_STATUSES = ("suggested", "deferred", "ready", "reactivated")
KNOWLEDGE_LIFECYCLE_STATES = ("active", "review", "deferred", "retired", "revisit")
KNOWLEDGE_LIFECYCLE_KINDS = ("concept", "decision", "judgment")
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


@dataclass
class Finding:
    severity: str
    path: str
    message: str


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


def default_protocol_state() -> dict[str, Any]:
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


def ensure_protocol_scaffold(root: Path) -> None:
    base = root / "schema" / "protocols"
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "index.md"
    if not index_path.exists():
        index_path.write_text(render_protocol_library_index(), encoding="utf-8")
    for slug in sorted(PROTOCOL_LIBRARY):
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


def protocol_descriptor(root: Path, slug: str) -> dict[str, Any]:
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


def load_protocol_state(root: Path) -> dict[str, Any]:
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


def protocol_output_guidance(protocol: str, output_format: str) -> tuple[str, ...]:
    default_guidance = PROTOCOL_OUTPUT_GUIDANCE.get(DEFAULT_PROTOCOL, {})
    protocol_guidance = PROTOCOL_OUTPUT_GUIDANCE.get(protocol, default_guidance)
    return tuple(protocol_guidance.get(output_format, default_guidance.get(output_format, ())))


@runtime_write_operation
def set_active_protocol(root: Path, protocol: str) -> dict[str, Any]:
    active = resolve_protocol(root, protocol)
    path = protocol_state_path(root)
    path.write_text(json.dumps({"version": 1, "active_protocol": active}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state = load_protocol_state(root)
    write_if_changed(
        root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            root,
            utc_now(),
            knowledge_lifecycle=load_knowledge_lifecycle_state(root),
        ),
    )
    append_wiki_log(
        root,
        "protocol",
        "switch active protocol",
        [
            f"active_protocol: `{active}`",
            f"state_path: `{state['state_path']}`",
        ],
    )
    return state


def protocol_paths(root: Path, protocol: str | None = None) -> list[str]:
    slug = resolve_protocol(root, protocol)
    base = root / "schema" / "protocols" / slug
    paths = [relative_path(root, base / "index.md")]
    paths.extend(relative_path(root, base / f"{section}.md") for section in PROTOCOL_SECTION_FILES)
    return paths


def render_protocols_dashboard(
    root: Path,
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    state = load_protocol_state(root)
    active = state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle or load_knowledge_lifecycle_state(root),
        active_protocol=active,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lines = [
        "# 协议总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前 active protocol：`{active}` ({protocol_title(active)})",
        f"- 协议总数：`{len(state['available_protocols'])}`",
        f"- 状态文件：`{state['state_path']}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "- 切换命令：`PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set <slug>`",
        "",
        "## 当前协议入口",
    ]
    for relative in protocol_paths(root, active):
        label = Path(relative).stem
        if label == "index":
            label = "overview"
        lines.append(f"- [{relative}](../../{relative})")
    lines.extend(["", "## 可用协议"])
    for descriptor in state["protocols"]:
        lines.append(
            f"- [{descriptor['title']}](../../{descriptor['paths']['index']})"
            f" | slug `{descriptor['slug']}` | {descriptor['summary']}"
        )
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            "- 以下 lifecycle backlog 是全局 knowledge plane 工作面，按当前 active protocol 排序，不伪装成 protocol-specific 指标。",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Concept Backlog",
        ]
    )
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
            "## 运行原则",
            "- 统一 runtime，不复制多个炉子。",
            "- 领域差异优先落在 `schema/protocols/`。",
            "- 查询、回流和审阅默认沿当前 active protocol 执行，但 page frontmatter 会保留显式 protocol 字段。",
            "",
            "## 当前协议语义",
            *protocol_runtime_summary(active),
        ]
    )
    return "\n".join(lines) + "\n"


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


def schedule_review_windows(
    kind: str,
    status: str,
    base_timestamp: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> tuple[str, str]:
    windows = PROTOCOL_REVIEW_WINDOWS.get(protocol, {}).get((kind, status), AGING_WINDOWS_DAYS.get((kind, status)))
    if not windows:
        return "", ""
    base = parse_iso_datetime(base_timestamp) or datetime.now(timezone.utc)
    revisit_days, escalate_days = windows
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


PROVENANCE_PATH_PATTERN = re.compile(r"(?:\.\./)*(wiki/sources/[^\s`)\]]+\.md|raw/[^\s`)\]]+)")


def normalize_workspace_path(value: str) -> str:
    normalized = value.strip().strip("'\"`")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip(".,;:")


def extract_provenance_paths(root: Path, markdown: str) -> list[str]:
    frontmatter = parse_frontmatter(markdown)
    candidates: list[str] = []
    for key in ("citations", "source_files"):
        value = frontmatter.get(key, [])
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if isinstance(item, str))
    candidates.extend(match.group(1) for match in PROVENANCE_PATH_PATTERN.finditer(markdown))

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        path = normalize_workspace_path(candidate)
        if not path.startswith(("wiki/sources/", "raw/")):
            continue
        if not (root / path).exists():
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized_paths.append(path)
    return normalized_paths


def evidence_path_digest(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists():
        return ""
    if relative.startswith("wiki/sources/"):
        return compiled_source_sha(path.read_text(encoding="utf-8", errors="replace"))
    if path.is_file():
        return sha256_file(path)
    return ""


def build_citation_snapshots(root: Path, citations: list[str]) -> list[str]:
    snapshots: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        normalized = normalize_workspace_path(str(citation))
        if not normalized or normalized in seen:
            continue
        digest = evidence_path_digest(root, normalized)
        if not digest:
            continue
        seen.add(normalized)
        snapshots.append(f"{normalized}#{digest}")
    return snapshots


def parse_citation_snapshots(frontmatter: dict[str, Any]) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    raw_value = frontmatter.get("citation_snapshots", [])
    if not isinstance(raw_value, list):
        return snapshots
    for item in raw_value:
        if not isinstance(item, str) or "#" not in item:
            continue
        relative, digest = item.rsplit("#", 1)
        relative = normalize_workspace_path(relative)
        if not relative or not digest:
            continue
        snapshots[relative] = digest
    return snapshots


def analyze_citation_snapshots(
    root: Path,
    citations: list[str],
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    current = {
        snapshot.rsplit("#", 1)[0]: snapshot.rsplit("#", 1)[1]
        for snapshot in build_citation_snapshots(root, citations)
        if "#" in snapshot
    }
    recorded = parse_citation_snapshots(frontmatter)
    drifted = sorted(path for path, digest in current.items() if recorded.get(path) and recorded[path] != digest)
    missing = sorted(path for path in current if path not in recorded)
    stale = sorted(path for path in recorded if path not in current)
    return {
        "current": current,
        "recorded": recorded,
        "drifted": drifted,
        "missing": missing,
        "stale": stale,
        "has_drift": bool(drifted or missing or stale),
    }


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


ISO_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)")


def normalize_generated_artifact_content(content: str) -> str:
    return ISO_DATETIME_PATTERN.sub("<ISO_DATETIME>", content)


def write_if_changed_ignoring_timestamps(path: Path, content: str) -> tuple[bool, bool]:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False, False
        if normalize_generated_artifact_content(current) == normalize_generated_artifact_content(content):
            return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, True


def render_json_document(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def normalize_generated_state_document(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"generated_at", "computed_at"} and isinstance(value, str) and ISO_DATETIME_PATTERN.fullmatch(value):
                normalized[key] = "<ISO_DATETIME>"
            else:
                normalized[key] = normalize_generated_state_document(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_generated_state_document(item) for item in payload]
    return payload


def write_json_document_if_changed_ignoring_generated_timestamps(path: Path, document: dict[str, Any]) -> tuple[bool, bool]:
    rendered = render_json_document(document)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False, False
        try:
            current_document = json.loads(current)
        except json.JSONDecodeError:
            current_document = None
        if isinstance(current_document, dict):
            if normalize_generated_state_document(current_document) == normalize_generated_state_document(document):
                return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True, True


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


@runtime_write_operation
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


def normalized_markdown_section_lines(markdown: str, heading: str) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return []
    return [line.strip() for line in section.splitlines() if line.strip()]


def curated_asset_placeholder_lines(
    heading: str,
    *,
    revisit_after: str = "",
    escalate_after: str = "",
) -> list[str]:
    placeholders = {
        "Counter Evidence": ["- Pending counter evidence."],
        "Invalidation": ["- Pending invalidation conditions."],
        "Next Signals": [
            "- Pending next signals.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
        ],
        "Review History": ["- No review history yet."],
    }
    return placeholders.get(heading, [])


def render_curated_asset_sections(
    *,
    revisit_after: str,
    escalate_after: str,
) -> list[str]:
    sections: list[str] = []
    for heading in CURATED_ASSET_SECTION_ORDER:
        if heading == "Review History":
            continue
        sections.extend(
            [
                "",
                f"## {heading}",
                *curated_asset_placeholder_lines(
                    heading,
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
            ]
        )
    return sections


def render_review_history_section() -> list[str]:
    return [
        "",
        "## Review History",
        *curated_asset_placeholder_lines("Review History"),
    ]


def curated_asset_section_snapshot(
    markdown: str,
    heading: str,
    *,
    revisit_after: str = "",
    escalate_after: str = "",
) -> dict[str, Any]:
    lines = normalized_markdown_section_lines(markdown, heading)
    placeholders = curated_asset_placeholder_lines(
        heading,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
    )
    meaningful_lines = [line for line in lines if line not in placeholders]
    review_history_entries = 0
    if heading == "Review History":
        review_history_entries = sum(1 for line in meaningful_lines if line.startswith("- `"))
    return {
        "present": bool(lines),
        "meaningful": bool(meaningful_lines),
        "placeholder_only": bool(lines) and not meaningful_lines,
        "review_history_entries": review_history_entries,
    }


def append_review_history_entry(
    markdown: str,
    *,
    reviewed_at: str,
    status: str,
    note: str | None = None,
    confidence: str | None = None,
) -> str:
    existing_lines = normalized_markdown_section_lines(markdown, "Review History")
    history_lines = [line for line in existing_lines if line != "- No review history yet."]
    entry_parts = [f"- `{reviewed_at}` | status `{status}`"]
    if confidence:
        entry_parts.append(f"confidence `{confidence}`")
    if note:
        entry_parts.append(f"note {note}")
    else:
        entry_parts.append("note none")
    history_lines.insert(0, " | ".join(entry_parts))
    return upsert_markdown_section(markdown, "Review History", "\n".join(history_lines))


def review_history_entries(markdown: str) -> list[str]:
    return [
        line
        for line in normalized_markdown_section_lines(markdown, "Review History")
        if line != "- No review history yet."
    ]


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


def active_manual_source_concept_links(root: Path) -> dict[str, set[str]]:
    state = load_manual_link_state(root)
    mapping: dict[str, set[str]] = {}
    for item in state.get("source_to_concept", []):
        source_id = str(item.get("source_id") or "").strip()
        concept_slug = str(item.get("concept_slug") or "").strip()
        active = bool(item.get("active", True))
        if not source_id or not concept_slug or not active:
            continue
        mapping.setdefault(source_id, set()).add(concept_slug)
    return mapping


def concept_source_input_signature(entry: dict[str, Any], context: str, manual_slugs: list[str]) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_sha256": str(entry.get("sha256") or ""),
        "context": context,
        "manual_slugs": sorted(str(slug) for slug in manual_slugs if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_concept_records(
    root: Path,
    entries: list[dict[str, Any]],
    previews: dict[str, str],
    *,
    generated_at: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    concept_map: dict[str, dict[str, Any]] = {}
    entry_terms: dict[str, list[str]] = {}
    previous_state = load_concept_build_state(root)
    previous_records = previous_state.get("entry_records", {})
    if not isinstance(previous_records, dict):
        previous_records = {}
    manual_links = active_manual_source_concept_links(root)
    dirty_concept_source_ids: list[str] = []
    clean_concept_source_ids: list[str] = []
    entry_records: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry["id"])
        context = source_summary_or_preview(root, entry, previews[entry["id"]])
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = concept_source_input_signature(entry, context, manual_slugs)
        previous_record = previous_records.get(entry_id, {})
        cached_terms = previous_record.get("terms", []) if isinstance(previous_record, dict) else []
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
            and isinstance(cached_terms, list)
        ):
            terms = [str(label) for label in cached_terms if str(label)]
            clean_concept_source_ids.append(entry_id)
        else:
            terms = entry_concept_terms(entry, context)
            dirty_concept_source_ids.append(entry_id)
        for manual_slug in manual_slugs:
            manual_label = manual_slug.replace("-", " ")
            if manual_label not in terms:
                terms.append(manual_label)
        entry_terms[entry_id] = terms
        entry_records[entry_id] = {
            "input_signature": input_signature,
            "terms": list(terms),
        }
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
                    "manual_source_ids": set(),
                },
            )
            record["entries"].append(entry)
            record["score"] += 1
            if slug in manual_links.get(entry_id, set()):
                record["manual_source_ids"].add(entry_id)

    ranked_records = sorted(concept_map.values(), key=lambda item: (-item["score"], item["title"].lower()))[:30]
    allowed = {record["slug"] for record in ranked_records}
    filtered_entry_terms: dict[str, list[str]] = {}
    for entry_id, labels in entry_terms.items():
        filtered = [label for label in labels if concept_label_to_slug(label) in allowed]
        filtered_entry_terms[entry_id] = filtered[:5]

    by_slug = {record["slug"]: record for record in ranked_records}
    for record in ranked_records:
        record["manual_source_ids"] = sorted(record.get("manual_source_ids", set()))
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
    state_document = {
        "version": 2,
        "generated_at": generated_at,
        "entry_records": entry_records,
    }
    return ranked_records, filtered_entry_terms, {
        "state_document": state_document,
        "dirty_concept_source_ids": dirty_concept_source_ids,
        "clean_concept_source_ids": clean_concept_source_ids,
    }


def concept_source_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": record["slug"],
        "entry_ids": sorted(record["entry_ids"]),
        "entry_sources": sorted(f"{entry['id']}:{entry['sha256']}" for entry in record["entries"]),
        "related_slugs": sorted(record.get("related_slugs", [])),
        "manual_source_ids": sorted(record.get("manual_source_ids", [])),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def concept_source_pages(record: dict[str, Any]) -> list[str]:
    return [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]]


def concept_render_signature(root: Path, record: dict[str, Any]) -> str:
    source_contexts = [
        load_source_page_context(root, relative)
        for relative in concept_source_pages(record)
    ]
    payload = {
        "title": record["title"],
        "source_signature": record["source_signature"],
        "source_pages": concept_source_pages(record),
        "source_contexts": [
            {
                "path": context.get("path", ""),
                "title": context.get("title", ""),
                "status": context.get("status", ""),
                "summary": context.get("summary", ""),
            }
            for context in source_contexts
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def render_concept_conflict_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    signals = detect_concept_conflict_signals(source_contexts)
    if not signals:
        return ["- 当前没有显式冲突信号。"]
    lines: list[str] = []
    for signal in signals[:6]:
        lines.append(f"- `{signal['label']}` | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`")
    return lines


def render_concept_gap_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    gaps = detect_concept_gap_signals(source_contexts)
    if not gaps:
        return ["- 当前没有显式证据缺口。"]
    lines: list[str] = []
    for gap in gaps[:6]:
        lines.append(
            f"- `{gap.get('kind', 'unknown')}` | source `{gap.get('path', 'n/a')}` | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
        )
    return lines


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
    source_pages = concept_source_pages(record)
    render_signature = str(record.get("render_signature") or concept_render_signature(record["root"], record))
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
    source_contexts = [
        load_source_page_context(record["root"], f"wiki/sources/{entry_id}.md")
        for entry_id in record["entry_ids"]
    ]
    frontmatter = render_frontmatter(
        {
            "id": f"concept-{record['slug']}",
            "kind": "concept",
            "status": "compiled",
            "title": record["title"],
            "source_pages": source_pages,
            "source_signature": record["source_signature"],
            "render_signature": render_signature,
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
        "## Conflict Signals",
        *render_concept_conflict_lines(source_contexts),
        "",
        "## Evidence Gaps",
        *render_concept_gap_lines(source_contexts),
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


def collect_aging_signals(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pages = decisions + judgments
    overdue = sorted(
        [page for page in pages if page.get("overdue_review") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
    escalated = sorted(
        [page for page in pages if page.get("escalation_candidate") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("escalate_after", "") or "9999", page["title"].lower()),
    )
    scheduled = sorted(
        [page for page in pages if page.get("aging_state") == "scheduled"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
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


def curated_page_template(
    *,
    kind: str,
    protocol: str,
    title: str,
    artifact_ref: str,
    filed_at: str,
    revisit_after: str,
    escalate_after: str,
    supporting_body: str,
) -> list[str]:
    origin_block = [
        "## Origin",
        f"- Filed from: `{artifact_ref}`",
        f"- Filed at: `{filed_at}`",
        f"- Protocol: `{protocol}`",
        "",
    ]
    if kind == "derived":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Filed Content",
            supporting_body,
        ]
    if kind == "decision":
        if protocol == "investing":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Position Decision",
                "- State the action: observe, build, add, trim, exit, or reject.",
                "",
                "## Scope And Sizing",
                "- Record the position scope, sizing guardrails, or watchlist boundary.",
                "",
                "## Thesis",
                "- Summarize the thesis and the supporting evidence.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Bear Case And Invalidation",
                "- Record the counter-thesis, invalidation triggers, and stop conditions.",
                "",
                "## Catalysts And Revisit",
                "- Record the next earnings/event/catalyst and what to monitor before revisiting.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the action is approved, resized, exited, or invalidated.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "research":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Architecture Decision",
                "- State the action: adopt, reject, defer, migrate, or rollback.",
                "",
                "## Affected Surface",
                "- Record the systems, components, teams, or experiments affected.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Validation Plan",
                "- Define the benchmark, test, or rollout signal that would validate this decision.",
                "",
                "## Rollback And Risks",
                "- Record regression risks, rollback path, and explicit failure conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the rollout result, benchmark, or regression signal changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "product":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Product Decision",
                "- State the action: prioritize, launch, roll out, deprecate, or pause.",
                "",
                "## User Problem And Bet",
                "- Record the target user problem, the product bet, and the expected behavior change.",
                "",
                "## Metric And Validation",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the primary metric, rollout checkpoint, or validation signal.",
                "",
                "## Launch Risks And Rollback",
                "- Record launch blockers, segment risk, and rollback/containment conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when launch readiness, metric movement, or the product bet changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "ops":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Incident Decision",
                "- State the action: mitigate, roll back, fail over, isolate, escalate, or follow up.",
                "",
                "## Incident Scope",
                "- Record the impacted service, blast radius, owner, and current operational state.",
                "",
                "## Mitigation Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the signal that shows mitigation is working.",
                "",
                "## Residual Risk And Follow-up",
                "- Record rollback/failover paths, residual risk, and follow-up owner.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the incident state, blast radius, or owner changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        return [
            f"# {title}",
            "",
            *origin_block,
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
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `proposed`",
            "- Review this page when the decision is approved, superseded, or needs revisit.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "investing":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Investment Judgment",
            "- State the thesis or judgment call here.",
            "",
            "## Drivers And Catalysts",
            f"- Summarize the key drivers and catalysts from `{artifact_ref}` and supporting sources.",
            "",
            "## Risks And Invalidation",
            "- Record the main risks, disconfirming signals, and invalidation conditions.",
            "",
            "## Confidence And Watchlist",
            "- Keep confidence explicit and list the next datapoints to watch.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the thesis strengthens, weakens, or is invalidated.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "research":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Research Judgment",
            "- State the hypothesis, expected gain, or architecture judgment here.",
            "",
            "## Supporting Evidence",
            f"- Summarize benchmark, experiment, or source evidence from `{artifact_ref}` and `wiki/sources/*.md`.",
            "",
            "## Counter Evidence",
            "- Record the regression risks, weak signals, or conflicting results.",
            "",
            "## Open Questions",
            "- List what remains uncertain and what experiment should resolve it.",
            "",
            "## Confidence And Next Experiment",
            "- Keep confidence explicit and name the next benchmark or follow-up check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new benchmark, regression, or experiment evidence arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "product":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Product Judgment",
            "- State the insight, product bet, or launch-readiness judgment here.",
            "",
            "## User Signal And Evidence",
            f"- Summarize user signal, metric evidence, or rollout data from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Signals",
            "- Record what user, metric, or launch evidence could invalidate this judgment.",
            "",
            "## Confidence And Next Validation",
            "- Keep confidence explicit and name the next validation checkpoint, release, or metric review.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the signal strengthens, weakens, or the launch plan changes.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "ops":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Ops Judgment",
            "- State the root-cause, blast-radius, or operational-risk judgment here.",
            "",
            "## Incident Evidence",
            f"- Summarize incident timeline, logs, or runbook evidence from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Evidence",
            "- Record what would falsify this root-cause or operational-risk judgment.",
            "",
            "## Confidence And Follow-up",
            "- Keep confidence explicit and name the next incident review, runbook update, or mitigation check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new incident evidence, residual risk, or follow-up status arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    return [
        f"# {title}",
        "",
        *origin_block,
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
        *render_curated_asset_sections(
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        ),
        "",
        "## Review Status",
        "- Current status: `tentative`",
        "- Review this page when the judgment is confirmed, rejected, or moved to active tracking.",
        "",
        "## Review Notes",
        "- No review has been recorded yet.",
        *render_review_history_section(),
        "",
        "## Supporting Artifact",
        supporting_body,
    ]


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


def rewrite_proposal_needs_review(status: str) -> bool:
    return status in PENDING_REWRITE_PROPOSAL_STATUSES


def display_rewrite_proposal_status(status: str) -> str:
    mapping = {
        "proposed": "待审提案",
        "accepted": "已接受提案",
        "deferred": "暂缓提案",
        "applied": "已应用",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "applied": 3, "rejected": 4}.get(status, 9)


def transition_profile(
    allowed_transitions: list[str],
    *,
    preferred_transitions: list[str] | None = None,
    default_transition: str = "",
) -> dict[str, Any]:
    allowed = [str(item).strip() for item in allowed_transitions if str(item).strip()]
    preferred = [str(item).strip() for item in (preferred_transitions or []) if str(item).strip() in allowed]
    default_value = str(default_transition or "").strip()
    if default_value not in allowed:
        default_value = preferred[0] if preferred else (allowed[0] if allowed else "")
    return {
        "allowed_transitions": allowed,
        "preferred_transitions": preferred,
        "default_transition": default_value,
    }


def curated_page_transition_profile(kind: str, status: str) -> dict[str, Any]:
    if kind == "decision":
        if status == "proposed":
            return transition_profile(
                ["approved", "needs-revisit", "superseded"],
                preferred_transitions=["approved", "needs-revisit"],
                default_transition="approved",
            )
        if status == "approved":
            return transition_profile(
                ["needs-revisit", "superseded"],
                preferred_transitions=["needs-revisit"],
                default_transition="needs-revisit",
            )
        if status == "needs-revisit":
            return transition_profile(
                ["approved", "superseded"],
                preferred_transitions=["approved"],
                default_transition="approved",
            )
        return transition_profile([])
    if kind == "judgment":
        if status == "tentative":
            return transition_profile(
                ["tracking", "confirmed", "rejected"],
                preferred_transitions=["tracking", "confirmed"],
                default_transition="tracking",
            )
        if status == "tracking":
            return transition_profile(
                ["confirmed", "rejected"],
                preferred_transitions=["confirmed"],
                default_transition="confirmed",
            )
        if status == "confirmed":
            return transition_profile(
                ["tracking", "rejected"],
                preferred_transitions=["tracking"],
                default_transition="tracking",
            )
        return transition_profile([])
    return transition_profile([])


def rewrite_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["deferred", "rejected"],
            preferred_transitions=["deferred"],
            default_transition="deferred",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "rejected"],
            preferred_transitions=["accepted"],
            default_transition="accepted",
        )
    return transition_profile([])


def action_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["resolved", "deferred", "rejected"],
            preferred_transitions=["resolved", "deferred"],
            default_transition="resolved",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "resolved", "rejected"],
            preferred_transitions=["accepted", "resolved"],
            default_transition="accepted",
        )
    return transition_profile([])


def archive_transition_profile(*, can_apply: bool, can_revert: bool) -> dict[str, Any]:
    if can_apply:
        return transition_profile(["apply"], preferred_transitions=["apply"], default_transition="apply")
    if can_revert:
        return transition_profile(["revert"], preferred_transitions=["revert"], default_transition="revert")
    return transition_profile([])


def html_safe_json_literal(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


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
        protocol = str(frontmatter.get("protocol") or DEFAULT_PROTOCOL)
        revisit_after = str(frontmatter.get("revisit_after") or "")
        escalate_after = str(frontmatter.get("escalate_after") or "")
        if not revisit_after and not escalate_after:
            base_timestamp = reviewed_at or updated_at or utc_now()
            revisit_after, escalate_after = schedule_review_windows(
                expected_kind,
                status,
                base_timestamp,
                protocol=protocol,
            )
        asset_snapshots = {
            heading: curated_asset_section_snapshot(
                content,
                heading,
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            )
            for heading in CURATED_ASSET_SECTION_ORDER
        }
        citations = [
            str(path)
            for path in frontmatter.get("citations", [])
            if isinstance(path, str) and path.strip()
        ]
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        review_entries = review_history_entries(content)
        asset_score = sum(1 for snapshot in asset_snapshots.values() if snapshot.get("meaningful"))
        pages.append(
            {
                "page_id": str(frontmatter.get("id") or path.stem),
                "title": str(frontmatter.get("title") or path.stem),
                "path": relative_path(root, path),
                "kind": str(frontmatter.get("kind") or ""),
                "status": status,
                "protocol": protocol,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "updated_at": updated_at,
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
                "matches_expected_kind": str(frontmatter.get("kind") or "") == expected_kind,
                "pending_review": "true" if page_needs_review(expected_kind, status) else "false",
                "asset_score": str(asset_score),
                "has_counter_evidence": "true" if asset_snapshots["Counter Evidence"]["meaningful"] else "false",
                "has_invalidation": "true" if asset_snapshots["Invalidation"]["meaningful"] else "false",
                "has_next_signals": "true" if asset_snapshots["Next Signals"]["meaningful"] else "false",
                "has_review_history": "true" if asset_snapshots["Review History"]["meaningful"] else "false",
                "review_history_entries": str(asset_snapshots["Review History"]["review_history_entries"]),
                "latest_review_history_entry": review_entries[0] if review_entries else "",
                "citation_count": str(len(citations)),
                "citation_snapshot_count": str(len(citation_snapshot_state["recorded"])),
                "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
                "citation_drift_count": str(len(citation_snapshot_state["drifted"])),
                "citation_snapshot_gap_count": str(
                    len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
                ),
            }
        )
    enriched: list[dict[str, str]] = []
    for page in pages:
        enriched_page = dict(page)
        enriched_page.update(evaluate_page_aging(enriched_page, now=now))
        enriched.append(enriched_page)
    return sort_curated_pages(enriched)


def review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pending_decisions = sorted(
        [page for page in decisions if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    pending_judgments = sorted(
        [page for page in judgments if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
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


def knowledge_lifecycle_invalidation_signals(page: dict[str, str]) -> list[str]:
    signals: list[str] = []
    if str(page.get("status") or "") == "needs-revisit":
        signals.append("explicit-needs-revisit")
    if page.get("citation_drift") == "true":
        signals.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        signals.append("citation-snapshot-gap")
    if page.get("overdue_review") == "true":
        signals.append("overdue-review")
    if page.get("escalation_candidate") == "true":
        signals.append("escalation-candidate")
    return signals


def knowledge_lifecycle_active_corpus_ids(
    source_ids: list[str],
    active_corpora: list[dict[str, Any]],
    *,
    concept_slug: str = "",
) -> list[str]:
    source_id_set = {source_id for source_id in source_ids if source_id}
    active_ids: list[str] = []
    for corpus in active_corpora:
        if str(corpus.get("status") or "") not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        if concept_slug:
            concept_slugs = {str(item) for item in corpus.get("concept_slugs", []) if isinstance(item, str)}
            if concept_slug in concept_slugs and corpus_id not in active_ids:
                active_ids.append(corpus_id)
                continue
        if not source_id_set:
            continue
        corpus_source_ids = {
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        }
        if source_id_set & corpus_source_ids:
            active_ids.append(corpus_id)
    return sorted(active_ids)


def knowledge_lifecycle_classification(
    *,
    status: str,
    pending_review: bool,
    invalidation_signals: list[str],
    active_corpus_ids: list[str],
) -> tuple[str, list[str]]:
    if status in {"superseded", "rejected"}:
        return "retired", ["terminal-status"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if pending_review:
        return "review", ["pending-review-status"]
    if active_corpus_ids and status in {"approved", "confirmed"}:
        return "active", ["active-corpus-linked"]
    return "deferred", ["reviewed-idle"]


def concept_lifecycle_invalidation_signals(quality_record: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if quality_record.get("conflict_signals"):
        signals.append("concept-conflict")
    if quality_record.get("gap_signals"):
        signals.append("concept-evidence-gap")
    return signals


def concept_lifecycle_review_signals(
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
    *,
    active_corpus_ids: list[str],
) -> list[str]:
    signals: list[str] = []
    proposal_status = str(rewrite_proposal.get("status") or "")
    if rewrite_proposal.get("active") and rewrite_proposal.get("pending_review") == "true":
        if proposal_status == "accepted":
            signals.append("rewrite-proposal-accepted")
        elif proposal_status == "deferred":
            signals.append("rewrite-proposal-deferred")
        else:
            signals.append("rewrite-proposal-proposed")
    if rewrite_proposal.get("apply_ready"):
        signals.append("rewrite-apply-ready")
    if active_corpus_ids and str(quality_record.get("quality_state") or "") != "stable":
        signals.append("active-quality-pressure")
    return signals


def concept_lifecycle_classification(
    *,
    source_ids: list[str],
    active_corpus_ids: list[str],
    invalidation_signals: list[str],
    review_signals: list[str],
) -> tuple[str, list[str]]:
    if not source_ids:
        return "retired", ["no-source-pages"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if review_signals:
        return "review", ["quality-review", *review_signals]
    if active_corpus_ids:
        return "active", ["active-corpus-linked"]
    return "deferred", ["compiled-idle"]


def build_knowledge_lifecycle_entry(
    root: Path,
    page: dict[str, str],
    *,
    expected_kind: str,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [
        str(item)
        for item in frontmatter.get("citations", [])
        if isinstance(item, str) and item.strip()
    ]
    if not citations and content:
        citations = extract_provenance_paths(root, content)
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(source_ids, active_corpora)
    invalidation_signals = knowledge_lifecycle_invalidation_signals(page)
    lifecycle_state, reason_codes = knowledge_lifecycle_classification(
        status=str(page.get("status") or ""),
        pending_review=page.get("pending_review") == "true",
        invalidation_signals=invalidation_signals,
        active_corpus_ids=active_corpus_ids,
    )
    return {
        "page_id": str(frontmatter.get("id") or Path(str(page.get("path") or "")).stem),
        "title": str(page.get("title") or frontmatter.get("title") or Path(str(page.get("path") or "")).stem),
        "path": str(page.get("path") or ""),
        "kind": expected_kind,
        "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        "status": str(page.get("status") or ""),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": page.get("pending_review") == "true",
        "overdue_review": page.get("overdue_review") == "true",
        "escalation_candidate": page.get("escalation_candidate") == "true",
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": int(page.get("citation_count", "0") or "0"),
        "citation_drift": page.get("citation_drift") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "confidence": str(page.get("confidence") or ""),
    }


def build_concept_lifecycle_entry(
    root: Path,
    path: Path,
    *,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    slug = path.stem
    source_pages = [
        str(item)
        for item in frontmatter.get("source_pages", [])
        if isinstance(item, str) and item.strip()
    ]
    source_ids = entry_ids_from_paths(path_to_entry_id, source_pages)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(
        source_ids,
        active_corpora,
        concept_slug=slug,
    )
    invalidation_signals = concept_lifecycle_invalidation_signals(quality_record)
    review_signals = concept_lifecycle_review_signals(
        quality_record,
        rewrite_proposal,
        active_corpus_ids=active_corpus_ids,
    )
    lifecycle_state, reason_codes = concept_lifecycle_classification(
        source_ids=source_ids,
        active_corpus_ids=active_corpus_ids,
        invalidation_signals=invalidation_signals,
        review_signals=review_signals,
    )
    return {
        "page_id": str(frontmatter.get("id") or f"concept-{slug}"),
        "title": str(frontmatter.get("title") or path.stem),
        "path": relative_path(root, path),
        "kind": "concept",
        "protocol": "",
        "status": str(frontmatter.get("status") or "compiled"),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": "",
        "revisit_after": "",
        "escalate_after": "",
        "aging_state": "",
        "pending_review": bool(review_signals),
        "overdue_review": False,
        "escalation_candidate": False,
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": 0,
        "citation_drift": False,
        "citation_drift_count": 0,
        "citation_snapshot_gap_count": 0,
        "review_history_entries": 0,
        "asset_score": 0,
        "confidence": str(frontmatter.get("confidence") or ""),
        "source_pages": source_pages,
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "quality_state": str(quality_record.get("quality_state") or "stable"),
        "issues": list(quality_record.get("issues") or []),
        "rewrite_priority": str(quality_record.get("rewrite_priority") or "low"),
        "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
        "review_signal_codes": review_signals,
        "rewrite_proposal_status": str(rewrite_proposal.get("status") or ""),
        "rewrite_pending_review": rewrite_proposal.get("pending_review") == "true",
        "rewrite_apply_ready": bool(rewrite_proposal.get("apply_ready")),
        "source_count": int(quality_record.get("source_count") or len(source_pages)),
        "related_count": int(quality_record.get("related_count") or 0),
        "override_active": False,
        "override_state": "",
        "override_reason_codes": [],
        "override_note": "",
        "override_updated_at": "",
        "override_source": "",
    }


def apply_knowledge_lifecycle_override(
    entry: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(entry)
    if not override or not bool(override.get("active")):
        return normalized
    override_state = str(override.get("lifecycle_state") or "")
    if override_state not in KNOWLEDGE_LIFECYCLE_STATES:
        return normalized
    override_reason_codes = [
        str(reason)
        for reason in override.get("reason_codes", [])
        if isinstance(reason, str) and reason.strip()
    ]
    normalized["derived_lifecycle_state"] = str(entry.get("lifecycle_state") or "")
    normalized["derived_reason_codes"] = list(entry.get("reason_codes") or [])
    normalized["override_active"] = True
    normalized["override_state"] = override_state
    normalized["override_reason_codes"] = override_reason_codes
    normalized["override_note"] = str(override.get("note") or "")
    normalized["override_updated_at"] = str(override.get("updated_at") or override.get("applied_at") or "")
    normalized["override_source"] = str(override.get("operation") or "manual-runtime")
    normalized["lifecycle_state"] = override_state
    normalized["reason_codes"] = ["manual-override", *(override_reason_codes or [f"manual-{override_state}"])]
    if override_state == "retired":
        normalized["pending_review"] = False
        normalized["overdue_review"] = False
        normalized["escalation_candidate"] = False
    return normalized


def knowledge_lifecycle_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    by_kind = {kind: {"total": 0, "by_state": {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}} for kind in KNOWLEDGE_LIFECYCLE_KINDS}
    invalidated = 0
    active_corpus_linked = 0
    for entry in entries:
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        kind = str(entry.get("kind") or "")
        if lifecycle_state in by_state:
            by_state[lifecycle_state] += 1
        if kind in by_kind:
            by_kind[kind]["total"] += 1
            if lifecycle_state in by_kind[kind]["by_state"]:
                by_kind[kind]["by_state"][lifecycle_state] += 1
        if entry.get("invalidation_signals"):
            invalidated += 1
        if entry.get("active_corpus_ids"):
            active_corpus_linked += 1
    return {
        "total": len(entries),
        "by_state": by_state,
        "by_kind": by_kind,
        "invalidated": invalidated,
        "active_corpus_linked": active_corpus_linked,
    }


def display_knowledge_lifecycle_state(state: str) -> str:
    mapping = {
        "active": "活跃",
        "review": "待审",
        "deferred": "暂挂",
        "retired": "已退役",
        "revisit": "待回看",
    }
    return mapping.get(state, state or "unknown")


def display_protocol_relevance_mode(mode: str) -> str:
    mapping = {
        "source-top1": "top1",
        "strong-top2": "strong-top2",
        "cross-protocol-bridge": "bridge-top2",
    }
    return mapping.get(mode, mode or "unknown")


def display_protocol_relevance_ambiguity(state: str) -> str:
    mapping = {
        "dominant": "dominant",
        "mixed": "mixed",
        "bridge": "bridge",
    }
    return mapping.get(state, state or "unknown")


def select_knowledge_lifecycle_entries(
    knowledge_lifecycle: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    states: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        if kinds is not None and kind not in kinds:
            continue
        if states is not None and lifecycle_state not in states:
            continue
        selected.append(dict(entry))
    return selected


def sort_knowledge_lifecycle_entries(
    entries: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    state_rank = {"revisit": 0, "review": 1, "active": 2, "deferred": 3, "retired": 4}
    return sorted(
        entries,
        key=lambda entry: (
            state_rank.get(str(entry.get("lifecycle_state") or ""), 9),
            0 if str(entry.get("protocol") or "") == active_protocol and active_protocol else 1,
            0 if bool(entry.get("override_active")) else 1,
            -len(entry.get("invalidation_signals", []) if isinstance(entry.get("invalidation_signals"), list) else []),
            -len(entry.get("active_corpus_ids", []) if isinstance(entry.get("active_corpus_ids"), list) else []),
            str(entry.get("title") or "").lower(),
        ),
    )


def render_knowledge_lifecycle_entry_summary(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("page_id") or "unknown")
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "knowledge")
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    parts = [
        f"kind `{kind}`",
        f"state `{display_knowledge_lifecycle_state(lifecycle_state)}`",
    ]
    if bool(entry.get("override_active")):
        parts.append(f"override `{str(entry.get('override_state') or lifecycle_state or 'unknown')}`")
    invalidation_signals = entry.get("invalidation_signals", [])
    if isinstance(invalidation_signals, list) and invalidation_signals:
        parts.append(f"invalidation `{','.join(str(item) for item in invalidation_signals[:3])}`")
    active_corpus_ids = entry.get("active_corpus_ids", [])
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        parts.append(f"active_corpora `{len(active_corpus_ids)}`")
    review_signal_codes = entry.get("review_signal_codes", [])
    if isinstance(review_signal_codes, list) and review_signal_codes:
        parts.append(f"review_signals `{','.join(str(item) for item in review_signal_codes[:3])}`")
    reason_codes = entry.get("reason_codes", [])
    if isinstance(reason_codes, list) and reason_codes:
        parts.append(f"reasons `{','.join(str(item) for item in reason_codes[:3])}`")
    protocol_relevance_mode = str(entry.get("protocol_relevance_primary_mode") or "")
    if protocol_relevance_mode:
        parts.append(f"protocol_relevance `{display_protocol_relevance_mode(protocol_relevance_mode)}`")
    protocol_relevance_ambiguity = str(entry.get("protocol_relevance_ambiguity") or "")
    if protocol_relevance_ambiguity:
        parts.append(f"protocol_ambiguity `{display_protocol_relevance_ambiguity(protocol_relevance_ambiguity)}`")
    return f"- [{title}](../../{path}) | " + " | ".join(parts)


def knowledge_lifecycle_governance_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    concept_counts = (
        knowledge_lifecycle.get("counts", {})
        .get("by_kind", {})
        .get("concept", {})
        .get("by_state", {})
    )
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "counts": {
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": int(concept_counts.get("active", 0) or 0),
            "deferred_concepts": int(concept_counts.get("deferred", 0) or 0),
        },
    }


def concept_protocol_relevance_for_source(
    source_id: str,
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    routing_entry = routing_by_entry_id.get(source_id, {})
    if not isinstance(routing_entry, dict):
        return {}
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if protocol not in top_protocols[:2]:
        return {}
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    if not routing_snapshot:
        return {}
    selected_as = str(routing_snapshot.get("selected_as") or "")
    if top_protocols[:1] == [protocol]:
        mode = "source-top1"
    elif bool(routing_entry.get("cross_protocol_bridge")) and selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "cross-protocol-bridge"
    elif selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "strong-top2"
    else:
        return {}
    return {
        "source_id": source_id,
        "mode": mode,
        "selected_as": selected_as,
        "total_score": float(routing_snapshot.get("total_score", 0.0) or 0.0),
    }


def concept_protocol_relevance(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_ids = [str(item) for item in entry.get("source_ids", []) if isinstance(item, str) and item]
    if not source_ids:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    mode_rank = {"source-top1": 0, "cross-protocol-bridge": 1, "strong-top2": 2}
    matched_sources = [
        match
        for match in (
            concept_protocol_relevance_for_source(
                source_id,
                protocol=protocol,
                routing_by_entry_id=routing_by_entry_id,
            )
            for source_id in source_ids
        )
        if match
    ]
    if not matched_sources:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    matched_sources.sort(
        key=lambda item: (
            mode_rank.get(str(item.get("mode") or ""), 9),
            -float(item.get("total_score", 0.0) or 0.0),
            str(item.get("source_id") or ""),
        )
    )
    modes: list[str] = []
    matched_source_ids: list[str] = []
    for item in matched_sources:
        mode = str(item.get("mode") or "")
        source_id = str(item.get("source_id") or "")
        if mode and mode not in modes:
            modes.append(mode)
        if source_id and source_id not in matched_source_ids:
            matched_source_ids.append(source_id)
    return {
        "related": True,
        "primary_mode": modes[0] if modes else "",
        "modes": modes,
        "source_ids": matched_source_ids,
    }


def concept_protocol_ambiguity_state(modes: list[str]) -> str:
    normalized = [str(item) for item in modes if isinstance(item, str) and item]
    if "cross-protocol-bridge" in normalized:
        return "bridge"
    if normalized == ["source-top1"]:
        return "dominant"
    return "mixed"


def concept_lifecycle_matches_protocol(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> bool:
    return bool(
        concept_protocol_relevance(
            entry,
            protocol=protocol,
            routing_by_entry_id=routing_by_entry_id,
        ).get("related")
    )


def protocol_related_concept_lifecycle_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    material_routing: dict[str, Any] | None,
    *,
    protocol: str,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    material_routing = material_routing or default_material_routing_state()
    routing_by_entry_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_routing.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    mode_counts = {
        "source-top1": 0,
        "strong-top2": 0,
        "cross-protocol-bridge": 0,
    }
    ambiguity_counts = {
        "dominant": 0,
        "mixed": 0,
        "bridge": 0,
    }
    related_entries: list[dict[str, Any]] = []
    for entry in select_knowledge_lifecycle_entries(knowledge_lifecycle, kinds={"concept"}):
        relevance = concept_protocol_relevance(entry, protocol=protocol, routing_by_entry_id=routing_by_entry_id)
        if not relevance.get("related"):
            continue
        primary_mode = str(relevance.get("primary_mode") or "")
        ambiguity = concept_protocol_ambiguity_state(list(relevance.get("modes", [])))
        if primary_mode in mode_counts:
            mode_counts[primary_mode] += 1
        if ambiguity in ambiguity_counts:
            ambiguity_counts[ambiguity] += 1
        related_entries.append(
            {
                **entry,
                "protocol_relevance_primary_mode": primary_mode,
                "protocol_relevance_modes": list(relevance.get("modes", [])),
                "protocol_relevance_source_ids": list(relevance.get("source_ids", [])),
                "protocol_relevance_ambiguity": ambiguity,
            }
        )
    related_concepts = sort_knowledge_lifecycle_entries(related_entries, active_protocol=protocol)
    concept_backlog = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") in {"review", "revisit"}
    ]
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "retired"
    ]
    ambiguity_watchlist = [
        entry
        for entry in related_concepts
        if str(entry.get("protocol_relevance_ambiguity") or "") in {"mixed", "bridge"}
    ]
    mixed_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "mixed"
    ]
    bridge_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "bridge"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "ambiguity_watchlist": ambiguity_watchlist,
        "mixed_concepts": mixed_concepts,
        "bridge_concepts": bridge_concepts,
        "counts": {
            "related_concepts": len(related_concepts),
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": sum(
                1 for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "active"
            ),
            "direct_related_concepts": mode_counts["source-top1"],
            "secondary_related_concepts": mode_counts["strong-top2"],
            "bridge_related_concepts": mode_counts["cross-protocol-bridge"],
            "dominant_related_concepts": ambiguity_counts["dominant"],
            "mixed_related_concepts": ambiguity_counts["mixed"],
            "ambiguity_bridge_concepts": ambiguity_counts["bridge"],
        },
        "inference_mode": "source-top1-plus-strong-top2-plus-cross-protocol-bridge",
        "ambiguity_mode": "dominant-vs-mixed-vs-bridge",
    }


def refresh_knowledge_lifecycle_state(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = build_knowledge_lifecycle_document(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=entries,
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    save_knowledge_lifecycle_state(root, document)
    return document


def build_knowledge_lifecycle_document(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    override_state = ensure_knowledge_lifecycle_override_state(root)
    active_overrides = active_knowledge_lifecycle_overrides(override_state)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    _entry_by_id, path_to_entry_id = entry_lookup_maps(manifest_entries)
    decision_pages = decisions if decisions is not None else collect_curated_pages(root, "decisions", "decision")
    judgment_pages = judgments if judgments is not None else collect_curated_pages(root, "judgments", "judgment")
    concept_memory = memory if memory is not None else load_machine_memory(root)
    concept_quality = build_concept_quality(root, concept_memory) if concept_memory else {
        "weak_concepts": [],
        "stable_concepts": [],
    }
    concept_quality_by_slug = {
        str(record.get("slug") or ""): dict(record)
        for record in (concept_quality.get("all_concepts", []) or [])
        if isinstance(record, dict) and record.get("slug")
    }
    concept_rewrite_by_slug = {
        str(proposal.get("slug") or ""): dict(proposal)
        for proposal in load_concept_rewrite_state(root).get("proposals", [])
        if isinstance(proposal, dict) and proposal.get("slug")
    }
    active_corpora = [
        dict(corpus)
        for corpus in (active_corpora_state or load_active_corpora_state(root)).get("corpora", [])
        if isinstance(corpus, dict)
    ]
    lifecycle_entries = [
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="decision",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in decision_pages
        ],
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="judgment",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in judgment_pages
        ],
        *[
            build_concept_lifecycle_entry(
                root,
                path,
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
                quality_record=concept_quality_by_slug.get(
                    path.stem,
                    {
                        "slug": path.stem,
                        "quality_state": "stable",
                        "issues": [],
                        "rewrite_priority": "low",
                        "rewrite_strategy": "",
                        "source_count": 0,
                        "related_count": 0,
                    },
                ),
                rewrite_proposal=concept_rewrite_by_slug.get(path.stem, {}),
            )
            for path in sorted((root / "wiki" / "concepts").glob("*.md"))
        ],
    ]
    lifecycle_entries = [
        apply_knowledge_lifecycle_override(entry, active_overrides.get(str(entry.get("path") or "")))
        if str(entry.get("kind") or "") == "concept"
        else entry
        for entry in lifecycle_entries
    ]
    document = {
        "version": 1,
        "generated_at": generated_at,
        "entries": lifecycle_entries,
        "counts": knowledge_lifecycle_counts(lifecycle_entries),
    }
    return document


def collect_machine_memory_actions(root: Path) -> list[dict[str, Any]]:
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    now = datetime.now(timezone.utc)
    active_protocol = load_protocol_state(root)["active_protocol"]
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
        action["focus_score"] = action_focus_score(active_protocol, action)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}
    return sorted(
        actions,
        key=lambda item: (
            0 if item.get("active") else 1,
            status_order.get(str(item.get("status")), 9),
            0 if item.get("escalation_candidate") == "true" else 1,
            0 if item.get("overdue_review") == "true" else 1,
            -int(item.get("focus_score", 0)),
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


def action_supports_low_risk_apply(action: dict[str, Any]) -> bool:
    return (
        bool(action.get("active", True))
        and str(action.get("status") or "") == "accepted"
        and str(action.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
    )


def execution_policy_profile(action: dict[str, Any]) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    if not active:
        return {
            "execution_policy": "inactive-history",
            "execution_band": "history-only",
            "capabilities": ["history"],
            "policy_summary": "信号已消失，只保留历史与审计价值。",
        }
    if status == "proposed":
        return {
            "execution_policy": "triage",
            "execution_band": "review-first",
            "capabilities": ["review"],
            "policy_summary": "先 review / triage，再决定是否进入 accepted。",
        }
    if status == "accepted" and action_supports_low_risk_apply(action):
        return {
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ["dry-run", "bundle-apply", "revert-safe", "history"],
            "policy_summary": "支持 dry-run、bundle-driven apply 和 receipt 驱动回滚。",
        }
    if status == "accepted":
        return {
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "capabilities": ["manual-edit", "review"],
            "policy_summary": "只能走人工修复与 review，不开放 safe apply。",
        }
    if status == "deferred":
        return {
            "execution_policy": "parked",
            "execution_band": "deferred",
            "capabilities": ["resume-review", "history"],
            "policy_summary": "动作已暂缓，保留复查与恢复入口。",
        }
    return {
        "execution_policy": "closed",
        "execution_band": "closed",
        "capabilities": ["history"],
        "policy_summary": "动作已关闭，仅保留审计与历史记录。",
    }


def execution_band_label(band: str) -> str:
    return EXECUTION_BAND_LABELS.get(band, band or "unknown")


PATCH_ROLE_LABELS = {
    "source": "来源页",
    "concept": "概念页",
    "index": "索引页",
    "state": "状态文件",
    "output": "输出页",
    "other": "页面",
}

PATCH_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "add-source-concept-link": {
        "summary": "补 source/concept 双向链接，并把新证据吸收到概念页摘要里。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Related Concepts", "Summary", "Citations"),
                "summary": "在来源页补 concept 引用，并保留 raw/source provenance。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary", "Related Concepts"),
                "summary": "把来源页纳入概念页，并更新 grounded synthesis。",
            },
            "state": {
                "mode": "semi-auto-apply",
                "sections": ("source_to_concept",),
                "summary": "通过 manual-link state 注入低风险补链，让 compile 收敛页面链接。",
            },
        },
    },
    "connect-isolated-source": {
        "summary": "把孤立来源接回稳定概念层，并明确为什么要接入。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Summary", "Related Concepts", "Citations"),
                "summary": "从来源页抽出候选概念并补引用。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary"),
                "summary": "优先把来源接到已有稳定概念，而不是盲目新建概念。",
            },
            "index": {
                "mode": "review",
                "sections": ("Concept Coverage", "Open Questions"),
                "summary": "在索引层确认是否还缺概念覆盖或需要新概念。",
            },
        },
    },
    "expand-singleton-concept": {
        "summary": "扩展单节点概念的来源覆盖，并收紧其适用边界。",
        "roles": {
            "concept": {
                "mode": "update",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "补来源覆盖、显式有限证据，并更新相关概念边界。",
            },
            "index": {
                "mode": "review",
                "sections": ("Rewrite Priority", "Open Questions"),
                "summary": "在概念质量和索引层确认是否需要持续重写或补料。",
            },
        },
    },
    "split-overloaded-concept": {
        "summary": "把过载概念拆成更窄的主题，并把来源重新分流。",
        "roles": {
            "concept": {
                "mode": "rewrite",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "缩窄概念边界、保留拆分说明，并给出后续子概念方向。",
            },
            "index": {
                "mode": "review",
                "sections": ("Merge Candidates", "Rewrite Priority"),
                "summary": "在概念质量层复核拆分理由和后续子概念候选。",
            },
        },
    },
    "monitor-bridge-concept": {
        "summary": "确认桥接概念仍有必要，并记录跨簇连接的理由。",
        "roles": {
            "concept": {
                "mode": "review",
                "sections": ("Summary", "Related Concepts", "Related Sources"),
                "summary": "补 bridge maintenance note，明确为什么这个桥接概念还成立。",
            },
            "index": {
                "mode": "review",
                "sections": ("Bridge Concepts", "Repair Signals"),
                "summary": "在图谱健康层确认桥接信号是否稳定，避免误删关键连接。",
            },
        },
    },
}

PATCH_PLAN_AUXILIARY_PATHS: dict[str, tuple[str, ...]] = {
    "connect-isolated-source": ("wiki/indexes/concepts.md",),
    "expand-singleton-concept": ("wiki/indexes/concept-quality.md",),
    "split-overloaded-concept": ("wiki/indexes/concept-quality.md", "wiki/indexes/rewrite-proposals.md"),
    "monitor-bridge-concept": ("wiki/indexes/graph-health.md",),
}

PROTOCOL_PATCH_HINTS: dict[str, tuple[str, ...]] = {
    "general": (),
    "investing": (
        "同步检查 thesis、risk、catalyst 和 invalidation 页面是否要一起更新。",
    ),
    "research": (
        "同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。",
    ),
    "product": (
        "同步检查 user problem、metric、launch risk 和 validation gap 是否要一起更新。",
    ),
    "ops": (
        "同步检查 incident timeline、blast radius、mitigation 和 follow-up 是否要一起更新。",
    ),
}


def patch_role_for_path(path: str) -> str:
    if path.startswith("wiki/sources/"):
        return "source"
    if path.startswith("wiki/concepts/"):
        return "concept"
    if path.startswith("wiki/indexes/"):
        return "index"
    if path.startswith(".aiwiki/state/"):
        return "state"
    if path.startswith("output/"):
        return "output"
    return "other"


def patch_sections_for_action(kind: str, role: str) -> tuple[str, ...]:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return tuple(roles[role].get("sections", ()))
    fallback = {
        "source": ("Summary", "Citations"),
        "concept": ("Summary", "Related Sources", "Related Concepts"),
        "index": ("Status", "Open Questions"),
        "state": ("state",),
        "output": ("Summary",),
        "other": ("Summary",),
    }
    return fallback.get(role, ("Summary",))


def patch_summary_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("summary") or "")
    return str(template.get("summary") or "检查相关页面并补充修复说明。")


def patch_mode_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("mode") or "update")
    return "update"


def build_page_patch_plan(root: Path, action: dict[str, Any], *, active_protocol: str = DEFAULT_PROTOCOL) -> list[dict[str, Any]]:
    kind = str(action.get("kind") or "")
    seen_paths: set[str] = set()
    ordered_paths: list[str] = []
    for raw_path in (
        str(action.get("primary_path") or ""),
        str(action.get("secondary_path") or ""),
        *PATCH_PLAN_AUXILIARY_PATHS.get(kind, ()),
    ):
        path = raw_path.strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        ordered_paths.append(path)
    if action_supports_low_risk_apply(action):
        ordered_paths.append(".aiwiki/state/manual-links.json")

    plan: list[dict[str, Any]] = []
    for path in ordered_paths:
        role = patch_role_for_path(path)
        absolute = root / path
        title = absolute.stem
        if absolute.is_file() and role != "state":
            frontmatter = parse_frontmatter(absolute.read_text(encoding="utf-8", errors="replace"))
            title = str(frontmatter.get("title") or title)
        summary = patch_summary_for_action(kind, role)
        protocol_hints = PROTOCOL_PATCH_HINTS.get(active_protocol, ())
        if protocol_hints and role in {"source", "concept", "index"}:
            summary = f"{summary} {protocol_hints[0]}".strip()
        plan.append(
            {
                "path": path,
                "title": title,
                "role": role,
                "role_label": PATCH_ROLE_LABELS.get(role, role),
                "exists": absolute.is_file(),
                "mode": patch_mode_for_action(kind, role),
                "sections": list(patch_sections_for_action(kind, role)),
                "summary": summary,
                "command_hint": str(action.get("command_hint") or ""),
            }
        )
    return plan


def safe_apply_preview(root: Path, action: dict[str, Any]) -> dict[str, Any] | None:
    if str(action.get("kind") or "") not in LOW_RISK_APPLYABLE_ACTION_KINDS:
        return None
    try:
        source_id, concept_slug = validate_low_risk_action_targets(root, action)
    except RuntimeError:
        return None
    primary_path = str(action.get("primary_path") or "")
    secondary_path = str(action.get("secondary_path") or "")
    return {
        "apply_mode": "manual-link-state",
        "state_path": relative_path(root, manual_link_state_path(root)),
        "entry": {
            "source_id": source_id,
            "concept_slug": concept_slug,
            "origin_action_id": str(action.get("id") or ""),
            "active": True,
        },
        "affected_paths": [
            path for path in (primary_path, secondary_path, "wiki/indexes/machine-memory-repair-plan.md") if path
        ],
        "follow_up": "执行后会重跑 compile，让 source/concept/index 层按 manual link state 收敛。",
    }


def build_execution_bundle(
    root: Path,
    proposal: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    patch_steps: list[dict[str, Any]] = []
    for index, patch in enumerate(proposal.get("page_patch_plan", []), start=1):
        patch_steps.append(
            {
                "step": index,
                "path": str(patch.get("path") or ""),
                "role": str(patch.get("role") or ""),
                "role_label": str(patch.get("role_label") or patch.get("role") or "page"),
                "mode": str(patch.get("mode") or "update"),
                "sections": list(patch.get("sections") or []),
                "summary": str(patch.get("summary") or ""),
                "exists": bool(patch.get("exists", False)),
                "command_hint": str(patch.get("command_hint") or ""),
            }
        )
    bundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-compile",
        "compiled_at": compiled_at,
        "action_id": str(proposal.get("action_id") or ""),
        "title": str(proposal.get("title") or ""),
        "status": str(proposal.get("status") or "proposed"),
        "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
        "risk": str(proposal.get("risk") or "medium"),
        "priority": str(proposal.get("priority") or "medium"),
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "summary": str(proposal.get("summary") or ""),
        "target_paths": list(proposal.get("target_paths") or []),
        "suggested_edits": list(proposal.get("suggested_edits") or []),
        "proposal_path": str(proposal.get("proposal_path") or ""),
        "bundle_path": str(proposal.get("bundle_path") or ""),
        "page_patch_plan": patch_steps,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
        "command_hint": str(proposal.get("command_hint") or ""),
        "next_step": str(proposal.get("next_step") or ""),
        "dry_run_supported": bool(proposal.get("safe_apply_preview")),
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def execution_bundle_digest(bundle: dict[str, Any]) -> str:
    payload = {
        "action_id": str(bundle.get("action_id") or ""),
        "title": str(bundle.get("title") or ""),
        "status": str(bundle.get("status") or ""),
        "proposal_kind": str(bundle.get("proposal_kind") or ""),
        "risk": str(bundle.get("risk") or ""),
        "priority": str(bundle.get("priority") or ""),
        "protocol": str(bundle.get("protocol") or DEFAULT_PROTOCOL),
        "summary": str(bundle.get("summary") or ""),
        "target_paths": list(bundle.get("target_paths") or []),
        "suggested_edits": list(bundle.get("suggested_edits") or []),
        "page_patch_plan": list(bundle.get("page_patch_plan") or []),
        "safe_apply_preview": bundle.get("safe_apply_preview"),
        "command_hint": str(bundle.get("command_hint") or ""),
        "next_step": str(bundle.get("next_step") or ""),
        "dry_run_supported": bool(bundle.get("dry_run_supported")),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def load_execution_bundle(path: Path) -> dict[str, Any]:
    document = load_json_document(path)
    if not isinstance(document, dict) or str(document.get("kind") or "") != "execution-bundle":
        raise RuntimeError(f"Invalid execution bundle: {path}")
    return document


def build_execution_receipt(
    root: Path,
    action: dict[str, Any],
    *,
    applied_at: str,
    note: str | None,
    proposal: dict[str, Any],
    operation: str = "apply",
    resulting_status: str = "resolved",
) -> dict[str, Any]:
    bundle = build_execution_bundle(root, proposal, compiled_at=applied_at)
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-apply-action",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or ""),
        "status": resulting_status,
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "apply_mode": "manual-link-state" if operation == "apply" else "manual-link-state-revert",
        "note": note or "",
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "receipt_path": relative_path(root, execution_receipt_path(root, str(action.get("id") or ""))),
        "bundle": bundle,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
    }


def build_material_archive_bundle(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> dict[str, Any]:
    command_hint = (
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . revert-archive {entry_id}"
        if operation == "apply"
        else f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-archive {entry_id}"
    )
    action_id = material_archive_action_id(entry_id)
    bundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-material-archive",
        "compiled_at": applied_at,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "proposal_kind": "material-archive",
        "risk": "low",
        "priority": "low",
        "protocol": protocol,
        "summary": f"{operation} material archive override for `{entry_id}`.",
        "target_paths": [
            path
            for path in (
                source_path,
                relative_path(root, material_archive_state_path(root)),
                relative_path(root, material_state_path(root)),
            )
            if path
        ],
        "suggested_edits": [f"temperature `{current_temperature}` -> `{resulting_temperature}`"],
        "proposal_path": "",
        "bundle_path": "",
        "page_patch_plan": [],
        "safe_apply_preview": {
            "apply_mode": (
                "material-temperature-archive"
                if operation == "apply"
                else "material-temperature-archive-revert"
            ),
            "state_path": relative_path(root, material_archive_state_path(root)),
            "entry": {
                "entry_id": entry_id,
                "active": operation == "apply",
                "temperature": resulting_temperature,
            },
            "affected_paths": [
                path
                for path in (
                    source_path,
                    relative_path(root, material_archive_state_path(root)),
                    relative_path(root, material_state_path(root)),
                )
                if path
            ],
            "follow_up": "执行后会重跑 compile，让 material-state / archive-candidates / ask 排序同步收敛。",
        },
        "command_hint": command_hint,
        "next_step": "如需恢复材料，再执行对应的 revert-archive。",
        "dry_run_supported": False,
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def build_material_archive_receipt(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    note: str | None,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> dict[str, Any]:
    action_id = material_archive_action_id(entry_id)
    receipt_path = execution_receipt_path(root, action_id)
    bundle = build_material_archive_bundle(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        operation=operation,
        current_temperature=current_temperature,
        resulting_temperature=resulting_temperature,
    )
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-material-archive",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "protocol": protocol,
        "subject_kind": "material-archive",
        "subject_id": entry_id,
        "apply_mode": "material-temperature-archive" if operation == "apply" else "material-temperature-archive-revert",
        "note": note or "",
        "primary_path": source_path,
        "secondary_path": "",
        "current_temperature": current_temperature,
        "resulting_temperature": resulting_temperature,
        "receipt_path": relative_path(root, receipt_path),
        "bundle": bundle,
        "safe_apply_preview": bundle.get("safe_apply_preview"),
    }


def append_execution_receipt_history(root: Path, receipt: dict[str, Any]) -> None:
    path = execution_receipt_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")


def load_execution_receipt_history(root: Path) -> list[dict[str, Any]]:
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("kind") or "") == "execution-receipt":
            records.append(payload)
    return list(reversed(records))


def remove_stale_generated_execution_proposal_pages(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_proposals_dir(root)
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if str(frontmatter.get("kind") or "") != "execution-proposal":
            continue
        action_id = str(frontmatter.get("action_id") or "")
        if action_id and action_id in active_action_ids:
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_execution_bundle_files(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_bundles_dir(root)
    if not directory.exists():
        return 0
    active_slugs = {slugify(action_id) for action_id in active_action_ids if action_id}
    for path in sorted(directory.glob("*.json")):
        if path.stem in active_slugs:
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_markdown_files(directory: Path, active_stems: set[str]) -> int:
    removed = 0
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        if path.stem in active_stems:
            continue
        path.unlink()
        removed += 1
    return removed


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
    profile = execution_policy_profile(action)
    execution_policy = str(profile.get("execution_policy") or "triage")
    execution_band = str(profile.get("execution_band") or "review-first")
    capabilities = [str(item) for item in profile.get("capabilities", []) if isinstance(item, str) and item]
    if not active:
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = f'{review_prefix} --status resolved --note "Signal disappeared after compile."'
    elif status == "proposed":
        command_hint = f'{review_prefix} --status accepted --note "Accepted for manual repair."'
    elif status == "accepted":
        if action_supports_low_risk_apply(action):
            next_step = "这是低风险动作；可以直接通过 safe execution layer 应用，再让 compile 收敛状态。"
            command_hint = (
                f'PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id}'
                ' --note "Applied accepted low-risk repair."'
            )
        else:
            next_step = f"{next_step} 完成后将动作标为 resolved。"
            command_hint = f'{review_prefix} --status resolved --note "Repair completed."'
    elif status == "deferred":
        next_step = "已确认但暂缓处理；准备恢复时改回 accepted。"
        command_hint = f'{review_prefix} --status accepted --note "Resume deferred repair."'
    elif status in {"resolved", "rejected"}:
        next_step = "保持关闭，除非修复策略改变。"
    return {
        "execution_policy": execution_policy,
        "execution_band": execution_band,
        "execution_capabilities": ", ".join(capabilities) if capabilities else "none",
        "execution_capability_list": capabilities,
        "policy_summary": str(profile.get("policy_summary") or ""),
        "next_step": next_step,
        "command_hint": command_hint,
        "apply_ready": "true" if action_supports_low_risk_apply(action) else "false",
    }


def build_machine_memory_repair_plan(
    root: Path,
    health: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    active_actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    for action in active_actions + inactive_actions:
        action["focus_score"] = action_focus_score(active_protocol, action)
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
                        -int(item.get("focus_score", 0)),
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
            -max((int(action.get("focus_score", 0)) for action in item["actions"]), default=0),
            item["priority_rank"],
            item["label"],
        ),
    )
    execution_proposals = repair_execution_proposals(
        root,
        ready_actions + triage_actions + deferred_actions,
        active_protocol=active_protocol,
    )

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
            "patch_steps": sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals),
        },
    }


def normalize_query_signature(query: str) -> str:
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower())
    signature = "-".join(tokens).strip("-")
    return signature[:160] or "query"


def classify_recurring_output_kind(query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower()))
    protocol_markers = PROTOCOL_CLASSIFICATION_MARKERS.get(protocol, PROTOCOL_CLASSIFICATION_MARKERS[DEFAULT_PROTOCOL])
    decision_markers = DECISION_QUERY_MARKERS + tuple(protocol_markers.get("decision", ()))
    judgment_markers = JUDGMENT_QUERY_MARKERS + tuple(protocol_markers.get("judgment", ()))
    decision_score = sum(1 for marker in decision_markers if marker in normalized)
    judgment_score = sum(1 for marker in judgment_markers if marker in normalized)
    if decision_score <= 0 and judgment_score <= 0:
        return ""
    if decision_score >= judgment_score:
        return "decision"
    return "judgment"


def promotion_page_title(kind: str, query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    prefix = PROTOCOL_PROMOTION_PREFIXES.get(protocol, PROTOCOL_PROMOTION_PREFIXES[DEFAULT_PROTOCOL]).get(
        kind,
        "决策沉淀" if kind == "decision" else "判断沉淀",
    )
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
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "format": output_format,
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["query_signature"], item["created_at"], item["path"]))


def collect_output_density_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": str(frontmatter.get("query") or "").strip(),
                    "format": str(frontmatter.get("format") or "").strip(),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]))


def collect_recent_output_artifacts(root: Path, *, limit: int = 12) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": str(frontmatter.get("query") or "").strip(),
                    "format": str(frontmatter.get("format") or "").strip(),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]), reverse=True)[:limit]


def find_promoted_curated_page(root: Path, kind: str, query_signature: str, protocol: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != kind:
            continue
        if str(frontmatter.get("promotion_query_signature") or "") == query_signature:
            page_protocol = str(frontmatter.get("protocol") or "")
            if page_protocol == protocol or (not page_protocol and protocol == DEFAULT_PROTOCOL):
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
    protocol: str,
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
    citations = [
        str(path)
        for path in frontmatter.get("citations", [])
        if isinstance(path, str) and path.strip()
    ]
    seen_citations = {path for path in citations}
    for artifact in artifacts:
        artifact_path = root / artifact["path"]
        if not artifact_path.exists():
            continue
        for citation in extract_provenance_paths(root, artifact_path.read_text(encoding="utf-8", errors="replace")):
            if citation in seen_citations:
                continue
            seen_citations.add(citation)
            citations.append(citation)
    formats = sorted({artifact["format"] for artifact in artifacts})
    title = promotion_page_title(kind, query, protocol)
    citation_snapshots = build_citation_snapshots(root, citations)
    frontmatter["title"] = title
    frontmatter["protocol"] = protocol
    frontmatter["source_files"] = source_files
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = citation_snapshots
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
        f"- Protocol: `{protocol}`",
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


@runtime_write_operation
def promote_recurring_outputs(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for artifact in collect_output_artifacts(root):
        groups.setdefault((artifact["protocol"], artifact["query_signature"]), []).append(artifact)

    generated_at = utc_now()
    created = 0
    updated = 0
    promotions: list[dict[str, str]] = []
    for (protocol, query_signature), artifacts in sorted(groups.items()):
        if len(artifacts) < AUTO_PROMOTION_MIN_OCCURRENCES:
            continue
        query = artifacts[0]["query"]
        kind = classify_recurring_output_kind(query, protocol)
        if kind not in {"decision", "judgment"}:
            continue
        existing = find_promoted_curated_page(root, kind, query_signature, protocol)
        if existing is None:
            result = file_back(
                root,
                artifacts[-1]["path"],
                title=f"{kind}-{query_signature}",
                kind=kind,
                protocol=protocol,
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
            protocol=protocol,
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
                "protocol": protocol,
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
                f"protocol: `{protocol}`",
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
    protocol = page.get("protocol", "")
    if protocol:
        suffix_parts.append(f"协议 `{protocol}`")
    confidence = page.get("confidence", "")
    if confidence:
        suffix_parts.append(f"置信度 `{confidence}`")
    reviewed_at = page.get("reviewed_at", "")
    if reviewed_at:
        suffix_parts.append(f"审阅时间 `{reviewed_at}`")
    revisit_after = page.get("revisit_after", "")
    if revisit_after:
        suffix_parts.append(f"复审截止 `{revisit_after}`")
    if page.get("asset_score"):
        suffix_parts.append(f"资产 `{page.get('asset_score')}/4`")
    review_history_entries = int(page.get("review_history_entries", "0") or "0")
    if review_history_entries:
        suffix_parts.append(f"复审历史 `{review_history_entries}`")
    citation_drift_count = int(page.get("citation_drift_count", "0") or "0")
    citation_snapshot_gap_count = int(page.get("citation_snapshot_gap_count", "0") or "0")
    if page.get("citation_drift") == "true":
        suffix_parts.append(f"证据漂移 `{citation_drift_count or 1}`")
    if citation_snapshot_gap_count:
        suffix_parts.append(f"快照缺口 `{citation_snapshot_gap_count}`")
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
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
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
        f"- 证据漂移：`{len(drifted)}`",
        f"- 快照缺口：`{len(snapshot_gaps)}`",
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
    lines.extend(["", "## 证据漂移"])
    if not drifted:
        lines.append("- 当前没有检测到 citation drift。")
    else:
        for page in drifted[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gaps:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gaps[:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_judgment_assets(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> str:
    pages = sorted(
        decisions + judgments,
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            -(int(page.get("asset_score", "0") or "0")),
            page.get("title", "").lower(),
        ),
    )
    strong_assets = [page for page in pages if int(page.get("asset_score", "0") or "0") >= 3]
    missing_counter = [page for page in pages if page.get("has_counter_evidence") != "true"]
    missing_invalidation = [page for page in pages if page.get("has_invalidation") != "true"]
    missing_next_signals = [page for page in pages if page.get("has_next_signals") != "true"]
    missing_history = [page for page in pages if page.get("has_review_history") != "true"]
    lines = [
        "# 判断资产",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 资产完整（>= 3/4）：`{len(strong_assets)}`",
        f"- 缺反证：`{len(missing_counter)}`",
        f"- 缺失效条件：`{len(missing_invalidation)}`",
        f"- 缺下一信号：`{len(missing_next_signals)}`",
        f"- 缺复审历史：`{len(missing_history)}`",
        "",
        "## 强判断资产",
    ]
    if not strong_assets:
        lines.append("- 当前还没有资产完整度较高的 decision / judgment 页面。")
    else:
        for page in strong_assets[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Counter Evidence"])
    if not missing_counter:
        lines.append("- 当前所有判断资产都包含显式 counter evidence。")
    else:
        for page in missing_counter[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Invalidation"])
    if not missing_invalidation:
        lines.append("- 当前所有判断资产都包含显式 invalidation 条件。")
    else:
        for page in missing_invalidation[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Next Signals"])
    if not missing_next_signals:
        lines.append("- 当前所有判断资产都包含下一次观察信号。")
    else:
        for page in missing_next_signals[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Review History"])
    if not missing_history:
        lines.append("- 当前所有判断资产都已经积累复审历史。")
    else:
        for page in missing_history[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_cognitive_history(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    pages = sort_curated_pages(decisions + judgments)
    drifted_pages = sorted(
        [page for page in pages if page.get("citation_drift") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -int(page.get("citation_drift_count", "0") or "0"),
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )
    snapshot_gap_pages = sorted(
        [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("citation_snapshot_gap_count", "0") or "0"),
            0 if page.get("pending_review") == "true" else 1,
            page.get("title", "").lower(),
        ),
    )
    long_history_pages = sorted(
        [page for page in pages if int(page.get("review_history_entries", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("review_history_entries", "0") or "0"),
            page.get("reviewed_at", "") or "",
            page.get("title", "").lower(),
        ),
        reverse=True,
    )
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    lifecycle_entry_titles = {
        str(entry.get("path") or ""): str(entry.get("title") or entry.get("page_id") or "")
        for entry in knowledge_lifecycle.get("entries", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    concept_override_events: list[tuple[str, str, str, str]] = []
    for event in load_runtime_history(root):
        if str(event.get("event_type") or "") != "knowledge-lifecycle-override":
            continue
        if str(event.get("kind") or "") != "concept":
            continue
        occurred_at = str(event.get("occurred_at") or "")
        path = str(event.get("path") or "")
        title = lifecycle_entry_titles.get(path) or str(event.get("slug") or path or "unknown concept")
        operation = str(event.get("operation") or "override")
        lifecycle_state = str(event.get("lifecycle_state") or "")
        concept_override_events.append((occurred_at, title, path, f"{operation} -> {lifecycle_state or 'unknown'}"))
    concept_override_events.sort(key=lambda item: item[0], reverse=True)
    recent_events: list[tuple[str, str, str, str]] = []
    for page in pages:
        page_path = root / page["path"]
        if not page_path.exists():
            continue
        content = page_path.read_text(encoding="utf-8", errors="replace")
        for entry in review_history_entries(content)[:3]:
            match = re.match(r"- `([^`]+)`", entry)
            reviewed_at = match.group(1) if match else ""
            recent_events.append((reviewed_at, page["title"], page["path"], entry))
    recent_events.sort(key=lambda item: item[0], reverse=True)
    lines = [
        "# 认知历史",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- decision / judgment 页面：`{len(pages)}`",
        f"- 证据漂移页面：`{len(drifted_pages)}`",
        f"- snapshot 缺口页面：`{len(snapshot_gap_pages)}`",
        f"- 有复审历史的页面：`{len(long_history_pages)}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- concept lifecycle 事件：`{len(concept_override_events)}`",
        "",
        "## 证据漂移",
    ]
    if not drifted_pages:
        lines.append("- 当前没有 reviewed judgment / decision 因 citation drift 被标记。")
    else:
        for page in drifted_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gap_pages:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gap_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:16]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 概念生命周期事件"])
    if not concept_override_events:
        lines.append("- 当前还没有 concept lifecycle override 事件。")
    else:
        for occurred_at, title, path, detail in concept_override_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}"
            )
    lines.extend(["", "## 最近认知事件"])
    if not recent_events:
        lines.append("- 当前还没有 review history 事件。")
    else:
        for reviewed_at, title, path, entry in recent_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | reviewed `{reviewed_at or 'unknown'}` | {entry.replace(f'- `{reviewed_at}` | ', '') if reviewed_at else entry}"
            )
    lines.extend(["", "## 长历史页面"])
    if not long_history_pages:
        lines.append("- 当前还没有积累多轮复审历史的页面。")
    else:
        for page in long_history_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 建议动作",
        ]
    )
    if drifted_pages:
        lines.append(f"- 先复查 `{len(drifted_pages)}` 个被新证据挑战的 decision / judgment。")
    if snapshot_gap_pages:
        lines.append(f"- 补齐 `{len(snapshot_gap_pages)}` 个缺少 citation snapshot 的页面，避免 drift 失真。")
    if long_history_pages:
        lines.append(f"- 从 `{min(len(long_history_pages), 5)}` 个长历史页面里提炼更稳定的 judgment pattern。")
    if not any((drifted_pages, snapshot_gap_pages, long_history_pages)):
        lines.append("- 当前认知历史层比较干净，继续靠 nightly 累积 review history。")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def compact_section_lines(markdown: str, heading: str, *, fallback: str, limit: int = 5) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return [fallback]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return [fallback]
    if len(lines) > limit:
        return [*lines[:limit], "- ..."]
    return lines


def workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../{target})"


def pack_workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../../{target})"


def load_workspace_markdown(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = root / relative
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_frontmatter(content), content


def build_output_packs(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    pages = decisions + judgments
    review_candidates = sorted(
        [
            page
            for page in pages
            if page.get("pending_review") == "true"
            or page.get("citation_drift") == "true"
            or page.get("overdue_review") == "true"
            or page.get("escalation_candidate") == "true"
        ],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            0 if page.get("citation_drift") == "true" else 1,
            0 if page.get("pending_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )
    reviewed_candidates = sort_curated_pages(
        [page for page in pages if page.get("reviewed_at") and page.get("pending_review") != "true"]
    )
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action for action in repair_plan.get("ready_actions", []) if isinstance(action, dict) and action.get("active")
    ]
    execution_proposals = [
        proposal for proposal in repair_plan.get("execution_proposals", []) if isinstance(proposal, dict)
    ]
    proposal_by_action = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in execution_proposals
        if proposal.get("action_id")
    }
    review_packs: list[dict[str, str]] = []
    decision_memos: list[dict[str, str]] = []
    sop_drafts: list[dict[str, str]] = []

    for page in review_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        reasons: list[str] = []
        if page.get("pending_review") == "true":
            reasons.append("pending review")
        if page.get("overdue_review") == "true":
            reasons.append("overdue review")
        if page.get("escalation_candidate") == "true":
            reasons.append("escalation candidate")
        if page.get("citation_drift") == "true":
            reasons.append("citation drift")
        if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
            reasons.append("citation snapshot gap")
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = review_pack_path(root, page["path"])
        frontmatter_text = render_frontmatter(
            {
                "id": f"review-pack-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "review-pack",
                "title": f"Review Pack · {page['title']}",
                "protocol": str(frontmatter.get("protocol") or active_protocol),
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# Review Pack · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Kind: `{kind}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{frontmatter.get('protocol') or active_protocol}` ({protocol_title(str(frontmatter.get('protocol') or active_protocol))})",
            f"- Review reasons: `{', '.join(reasons) or 'manual review'}`",
            f"- Revisit / Escalate: `{page.get('revisit_after', '') or 'none'}` / `{page.get('escalate_after', '') or 'none'}`",
            "",
            f"## Current {section_name}",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。"),
            "",
            f"## {evidence_section} Snapshot",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据快照。"),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence."),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions."),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet."),
            "",
            "## Review Checklist",
            *[f"- {line}" for line in PROTOCOL_LIBRARY.get(str(frontmatter.get("protocol") or active_protocol), {}).get("review", [])],
            "",
            "## Commands",
            f"- `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page['path']} --status "
            f"{'approved' if kind == 'decision' else 'confirmed'} --note \"Review pack follow-up.\"`",
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [审阅队列](../../../wiki/indexes/review-queue.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
            ]
        )
        review_packs.append(
            {
                "title": f"Review Pack · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": str(frontmatter.get("protocol") or active_protocol),
                "reasons": ", ".join(reasons) or "manual review",
            }
        )

    for page in reviewed_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        memo_label = "Decision Memo" if kind == "decision" else "Judgment Memo"
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = decision_memo_path(root, page["path"])
        frontmatter_text = render_frontmatter(
            {
                "id": f"decision-memo-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "decision-memo",
                "title": f"{memo_label} · {page['title']}",
                "protocol": str(frontmatter.get("protocol") or active_protocol),
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# {memo_label} · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{frontmatter.get('protocol') or active_protocol}` ({protocol_title(str(frontmatter.get('protocol') or active_protocol))})",
            f"- Reviewed at: `{page.get('reviewed_at', '') or 'unknown'}`",
            f"- Confidence: `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            "",
            "## Executive Summary",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。", limit=6),
            "",
            f"## {evidence_section}",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据。", limit=6),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence.", limit=5),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions.", limit=5),
            "",
            "## Next Signals",
            *compact_section_lines(content, "Next Signals", fallback="- Pending next signals.", limit=5),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet.", limit=6),
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        if recent_outputs:
            lines.extend(["", "## Nearby Recent Outputs"])
            for artifact in recent_outputs[:5]:
                lines.append(
                    f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                    f" | format `{artifact['format'] or 'unknown'}`"
                    f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                )
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [判断资产](../../../wiki/indexes/judgment-assets.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
            ]
        )
        decision_memos.append(
            {
                "title": f"{memo_label} · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": str(frontmatter.get("protocol") or active_protocol),
                "reviewed_at": page.get("reviewed_at", "") or "",
            }
        )

    proposal_count = 0
    for proposal in execution_proposals:
        action_id = str(proposal.get("action_id") or "").strip()
        if not action_id:
            continue
        destination = sop_draft_path(root, action_id)
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "protocol": str(proposal.get("protocol") or active_protocol),
                "action_id": action_id,
                "source_files": [str(proposal.get("proposal_path") or "")],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        patch_plan = proposal.get("page_patch_plan", [])
        bundle_path = str(proposal.get("bundle_path") or "")
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {proposal.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Risk: `{proposal.get('risk', 'medium')}`",
            f"- Proposal kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
            f"- Protocol: `{proposal.get('protocol') or active_protocol}` ({protocol_title(str(proposal.get('protocol') or active_protocol))})",
            f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
            f"- Bundle: `{bundle_path or 'none'}`",
            "",
            "## Strategy",
            f"- {proposal.get('summary', '检查目标页面并确认是否执行。')}",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.append(
                f"2. 如果 dry-run 结果符合预期，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。"
            )
        else:
            lines.append("2. 当前没有 bundle，先回到 execution proposal 页面确认执行边界。")
        lines.append(
            f"3. 如需回滚，执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}`。"
        )
        lines.extend(["", "## Page-Level Patch Plan"])
        if not patch_plan:
            lines.append("- 当前没有页级 patch step。")
        else:
            for patch in patch_plan:
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
        lines.extend(
            [
                "",
                "## Suggested Edits",
            ]
        )
        edits = proposal.get("suggested_edits", [])
        if not edits:
            lines.append("- 当前没有额外建议。")
        else:
            lines.extend(f"- {edit}" for edit in edits[:8])
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(str(proposal.get('proposal_path') or ''), 'Execution Proposal')}" if proposal.get("proposal_path") else "- Execution Proposal: none",
                f"- {pack_workspace_link(bundle_path, 'Execution Bundle')}" if bundle_path else "- Execution Bundle: none",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆修复计划](../../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": str(proposal.get("protocol") or active_protocol),
                "risk": str(proposal.get("risk") or "medium"),
            }
        )
        proposal_count += 1

    for action in ready_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in proposal_by_action:
            continue
        destination = sop_draft_path(root, action_id)
        band = str(action.get("execution_band") or "review-first")
        action_protocol = str(action.get("protocol") or active_protocol)
        bundle_absolute = execution_bundle_path(root, action_id)
        bundle_relative = relative_path(root, bundle_absolute)
        bundle_path = bundle_relative if bundle_absolute.exists() else ""
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "protocol": action_protocol,
                "action_id": action_id,
                "source_files": [str(action.get("primary_path") or "")],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {action.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Status: `{display_action_status(str(action.get('status') or 'proposed'))}`",
            f"- Priority: `{action.get('priority', 'medium')}`",
            f"- Protocol: `{action_protocol}` ({protocol_title(action_protocol)})",
            f"- Execution band: `{band}` ({execution_band_label(band)})",
            f"- Primary / Secondary: `{action.get('primary_path', '')}` / `{action.get('secondary_path', '') or 'none'}`",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.extend(
                [
                    f"2. 如果执行 band 仍允许，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。",
                    f"3. 必要时用 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}` 回滚。",
                ]
            )
            bundle_link = f"- [Execution Bundle](../../../{bundle_path})"
        else:
            lines.extend(
                [
                    "2. 当前还没有稳定 bundle；先停在 dry-run，或回到 execution proposal 层生成 bundle。",
                    "3. 生成 bundle 后再执行真实 apply。",
                ]
            )
            bundle_link = "- Execution Bundle: none"
        lines.extend(
            [
                "",
                "## Action Notes",
                f"- Reason: {action.get('reason', 'n/a')}",
                f"- Next step: {action.get('next_step', 'n/a')}",
                f"- Command hint: `{action.get('command_hint', '') or 'none'}`",
                "",
                "## Related Links",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆动作队列](../../../wiki/indexes/machine-memory-actions.md)",
                bundle_link,
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": action_protocol,
                "risk": "low" if action_supports_low_risk_apply(action) else "medium",
            }
        )

    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }


def render_output_packs_index(output_packs: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    review_packs = output_packs.get("review_packs", [])
    decision_memos = output_packs.get("decision_memos", [])
    sop_drafts = output_packs.get("sop_drafts", [])
    lifecycle_summary = output_packs.get("lifecycle_summary", {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    counts = output_packs.get("counts", {})
    lines = [
        "# 输出 Pack 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Review packs：`{counts.get('review_packs', len(review_packs))}`",
        f"- Decision memos：`{counts.get('decision_memos', len(decision_memos))}`",
        f"- SOP drafts：`{counts.get('sop_drafts', len(sop_drafts))}`",
        f"- lifecycle concept backlog：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## Pack 目录",
        "- `output/packs/review/`：待审 / 漂移 / aging 页面",
        "- `output/packs/decision-memos/`：已审 decision / judgment",
        "- `output/packs/sop-drafts/`：ready action / execution proposal",
        "",
        "## Lifecycle Governance Summary",
        f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
        "",
        "## Lifecycle Concept Backlog",
    ]
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
        "## Review Packs",
        ]
    )
    if not review_packs:
        lines.append("- 当前没有 review packs。")
    else:
        for pack in review_packs[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reasons `{pack.get('reasons', 'manual review')}`"
            )
    lines.extend(["", "## Decision Memos"])
    if not decision_memos:
        lines.append("- 当前没有 decision memos。")
    else:
        for pack in decision_memos[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reviewed `{pack.get('reviewed_at', '') or 'unknown'}`"
            )
    lines.extend(["", "## SOP Drafts"])
    if not sop_drafts:
        lines.append("- 当前没有 SOP drafts。")
    else:
        for pack in sop_drafts[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | action `{pack.get('action_id', '')}`"
                f" | risk `{pack.get('risk', 'medium')}`"
            )
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [判断资产](./judgment-assets.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def domain_pilots_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def pilot_scorecards_dir(root: Path) -> Path:
    return root / "output" / "pilots"


def pilot_scorecard_path(root: Path, protocol: str) -> Path:
    return pilot_scorecards_dir(root) / f"{slugify(protocol)}.md"


def pilot_stage(metrics: dict[str, int]) -> tuple[str, str]:
    curated = metrics["decisions"] + metrics["judgments"]
    reviewed = metrics["reviewed"]
    outputs = metrics["outputs"]
    receipts = metrics["receipts"]
    packs = metrics["review_packs"] + metrics["decision_memos"] + metrics["sop_drafts"]
    if curated == 0 and outputs == 0:
        return ("seed", "尚未形成该协议的稳定判断资产。")
    if curated < 2 or reviewed == 0:
        return ("warming-up", "已经开始沉淀，但 reviewed judgment / decision 还偏少。")
    if reviewed < 3 or outputs < 3:
        return ("building", "协议已经起量，但还没进入明显复利。")
    if packs < 2 or receipts == 0:
        return ("active", "判断和 pack 已形成，但执行闭环还不够密。")
    return ("compounding", "已经出现判断、pack、执行和复审的复利迹象。")


def build_domain_pilots(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    material_routing = material_routing or load_material_routing_state(root)
    review_pack_counts: dict[str, int] = {}
    decision_memo_counts: dict[str, int] = {}
    sop_draft_counts: dict[str, int] = {}
    for pack in output_packs.get("review_packs", []):
        protocol = str(pack.get("protocol") or DEFAULT_PROTOCOL)
        review_pack_counts[protocol] = review_pack_counts.get(protocol, 0) + 1
    for pack in output_packs.get("decision_memos", []):
        protocol = str(pack.get("protocol") or DEFAULT_PROTOCOL)
        decision_memo_counts[protocol] = decision_memo_counts.get(protocol, 0) + 1
    for pack in output_packs.get("sop_drafts", []):
        protocol = str(pack.get("protocol") or DEFAULT_PROTOCOL)
        sop_draft_counts[protocol] = sop_draft_counts.get(protocol, 0) + 1
    receipt_counts = {
        str(row.get("protocol") or DEFAULT_PROTOCOL): int(row.get("count") or 0)
        for row in execution_audit.get("protocols", [])
        if isinstance(row, dict)
    }
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    proposal_counts: dict[str, int] = {}
    for proposal in repair_plan.get("execution_proposals", []):
        if not isinstance(proposal, dict):
            continue
        protocol = str(proposal.get("protocol") or DEFAULT_PROTOCOL)
        proposal_counts[protocol] = proposal_counts.get(protocol, 0) + 1

    scorecards: list[dict[str, Any]] = []
    for protocol in sorted(PROTOCOL_LIBRARY):
        protocol_decisions = [page for page in decisions if page.get("protocol") == protocol]
        protocol_judgments = [page for page in judgments if page.get("protocol") == protocol]
        protocol_outputs = [artifact for artifact in all_outputs if artifact.get("protocol") == protocol]
        protocol_recent_outputs = [artifact for artifact in recent_outputs if artifact.get("protocol") == protocol][:5]
        lifecycle_summary = protocol_related_concept_lifecycle_summary(
            knowledge_lifecycle,
            material_routing,
            protocol=protocol,
        )
        lifecycle_counts = lifecycle_summary.get("counts", {})
        pending = sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("pending_review") == "true")
        reviewed = sum(
            1
            for page in [*protocol_decisions, *protocol_judgments]
            if page.get("reviewed_at") and page.get("pending_review") != "true"
        )
        overdue = sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("overdue_review") == "true")
        escalation = sum(
            1 for page in [*protocol_decisions, *protocol_judgments] if page.get("escalation_candidate") == "true"
        )
        metrics = {
            "decisions": len(protocol_decisions),
            "judgments": len(protocol_judgments),
            "reviewed": reviewed,
            "pending": pending,
            "overdue": overdue,
            "escalation": escalation,
            "outputs": len(protocol_outputs),
            "review_packs": review_pack_counts.get(protocol, 0),
            "decision_memos": decision_memo_counts.get(protocol, 0),
            "sop_drafts": sop_draft_counts.get(protocol, 0),
            "receipts": receipt_counts.get(protocol, 0),
            "execution_proposals": proposal_counts.get(protocol, 0),
            "lifecycle_concept_backlog": lifecycle_counts.get("concept_backlog", 0),
            "lifecycle_retired_concepts": lifecycle_counts.get("retired_concepts", 0),
            "lifecycle_dominant_concepts": lifecycle_counts.get("dominant_related_concepts", 0),
            "lifecycle_mixed_concepts": lifecycle_counts.get("mixed_related_concepts", 0),
            "lifecycle_bridge_concepts": lifecycle_counts.get("ambiguity_bridge_concepts", 0),
        }
        stage, stage_summary = pilot_stage(metrics)
        gaps: list[str] = []
        if lifecycle_counts.get("concept_backlog", 0):
            gaps.append(
                f"有 `{lifecycle_counts.get('concept_backlog', 0)}` 个 protocol-related lifecycle concept backlog 尚未收敛。"
            )
        ambiguity_count = int(lifecycle_counts.get("mixed_related_concepts", 0)) + int(
            lifecycle_counts.get("ambiguity_bridge_concepts", 0)
        )
        if ambiguity_count:
            gaps.append(f"有 `{ambiguity_count}` 个 protocol-related concept 仍处于 mixed / bridge ambiguity，需要人工校准归属。")
        if metrics["decisions"] + metrics["judgments"] == 0:
            gaps.append("还没有该协议的 `decision / judgment` 资产。")
        if metrics["reviewed"] == 0:
            gaps.append("还没有 reviewed judgment / decision。")
        if metrics["outputs"] < 2:
            gaps.append("可回流 outputs 还不够密。")
        if metrics["pending"] > metrics["reviewed"]:
            gaps.append("待审页面多于已审资产。")
        if metrics["review_packs"] == 0 and metrics["pending"] > 0:
            gaps.append("需要先把 pending review 炼成 review packs。")
        if metrics["decision_memos"] == 0 and metrics["reviewed"] > 0:
            gaps.append("已审判断还没有形成 decision memos。")
        if metrics["sop_drafts"] == 0 and metrics["execution_proposals"] > 0:
            gaps.append("执行提案还没有形成 SOP drafts。")
        if metrics["receipts"] == 0 and metrics["sop_drafts"] > 0:
            gaps.append("还没有 execution receipt，可先从 dry-run / low-risk apply 开始。")
        next_moves = [
            PROTOCOL_LIBRARY[protocol]["focus"][0],
            PROTOCOL_LIBRARY[protocol]["review"][0],
            PROTOCOL_LIBRARY[protocol]["nightly"][0],
        ]
        if gaps:
            next_moves.insert(0, gaps[0])
        destination = pilot_scorecard_path(root, protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"pilot-scorecard-{slugify(protocol)}",
                "kind": "pilot-scorecard",
                "title": f"{protocol_title(protocol)} Pilot Scorecard",
                "protocol": protocol,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# {protocol_title(protocol)} Pilot Scorecard",
            "",
            "## Overview",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Stage: `{stage}`",
            f"- Summary: {stage_summary}",
            f"- 当前协议是否 active：`{'yes' if protocol == active_protocol else 'no'}`",
            "",
            "## Density Snapshot",
            f"- Decisions / Judgments: `{metrics['decisions']}` / `{metrics['judgments']}`",
            f"- Reviewed / Pending: `{metrics['reviewed']}` / `{metrics['pending']}`",
            f"- Overdue / Escalation: `{metrics['overdue']}` / `{metrics['escalation']}`",
            f"- Outputs: `{metrics['outputs']}`",
            f"- Review packs / Decision memos / SOP drafts: `{metrics['review_packs']}` / `{metrics['decision_memos']}` / `{metrics['sop_drafts']}`",
            f"- Execution proposals / Receipts: `{metrics['execution_proposals']}` / `{metrics['receipts']}`",
            f"- Protocol-related lifecycle backlog / retired concepts: `{metrics['lifecycle_concept_backlog']}` / `{metrics['lifecycle_retired_concepts']}`",
            "",
            "## Protocol Focus",
            *[f"- {line}" for line in PROTOCOL_LIBRARY[protocol]["focus"]],
            "",
            "## Gaps",
        ]
        if not gaps:
            lines.append("- 当前没有明显结构性缺口。")
        else:
            lines.extend(f"- {gap}" for gap in gaps)
        lines.extend(
            [
                "",
                "## Lifecycle Governance",
                "- 以下 concept lifecycle 摘要优先统计 supporting sources 的 `material-routing top_protocols` 首位命中；若来源在当前协议仍是 `warm/hot evidence`，或属于 `cross_protocol_bridge` 且当前协议仍位于 top2，也会保守纳入。",
                f"- Inference mode: `{lifecycle_summary.get('inference_mode', 'unknown')}`",
                f"- Ambiguity mode: `{lifecycle_summary.get('ambiguity_mode', 'unknown')}`",
                f"- Related direct / secondary / bridge concepts: `{lifecycle_counts.get('direct_related_concepts', 0)}` / `{lifecycle_counts.get('secondary_related_concepts', 0)}` / `{lifecycle_counts.get('bridge_related_concepts', 0)}`",
                f"- Related dominant / mixed / bridge concepts: `{lifecycle_counts.get('dominant_related_concepts', 0)}` / `{lifecycle_counts.get('mixed_related_concepts', 0)}` / `{lifecycle_counts.get('ambiguity_bridge_concepts', 0)}`",
                f"- Related review concepts: `{lifecycle_counts.get('review_concepts', 0)}`",
                f"- Related revisit concepts: `{lifecycle_counts.get('revisit_concepts', 0)}`",
                f"- Related retired concepts: `{lifecycle_counts.get('retired_concepts', 0)}`",
                f"- Related active concepts: `{lifecycle_counts.get('active_concepts', 0)}`",
                "",
                "## Protocol Ambiguity Watchlist",
            ]
        )
        if not lifecycle_summary.get("ambiguity_watchlist"):
            lines.append("- 当前没有 mixed / bridge ambiguity concept。")
        else:
            lines.append("- 以下概念仍需要人工判断是当前协议主归属、混合归属，还是桥接归属。")
            for entry in lifecycle_summary.get("ambiguity_watchlist", [])[:10]:
                lines.append(render_knowledge_lifecycle_entry_summary(entry))
        lines.extend(
            [
                "",
                "## Protocol-Related Lifecycle Concept Backlog",
            ]
        )
        if not lifecycle_summary.get("concept_backlog"):
            lines.append("- 当前没有 protocol-related lifecycle concept backlog。")
        else:
            for entry in lifecycle_summary.get("concept_backlog", [])[:10]:
                lines.append(render_knowledge_lifecycle_entry_summary(entry))
        lines.extend(["", "## Protocol-Related Retired Concepts"])
        if not lifecycle_summary.get("retired_concepts"):
            lines.append("- 当前没有 protocol-related retired concept。")
        else:
            for entry in lifecycle_summary.get("retired_concepts", [])[:10]:
                lines.append(render_knowledge_lifecycle_entry_summary(entry))
        lines.extend(["", "## Next Moves"])
        lines.extend(f"- {item}" for item in next_moves[:5])
        lines.extend(["", "## Recent Outputs"])
        if not protocol_recent_outputs:
            lines.append("- 当前没有最近 output。")
        else:
            for artifact in protocol_recent_outputs:
                lines.append(
                    f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                    f" | format `{artifact['format'] or 'unknown'}`"
                    f" | created `{artifact['created_at'] or 'unknown'}`"
                )
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(f'schema/protocols/{protocol}/index.md', f'{protocol_title(protocol)} 协议规则')}",
                f"- {pack_workspace_link('wiki/indexes/protocols.md', '协议总览')}",
                f"- {pack_workspace_link('wiki/indexes/output-packs.md', '输出 Pack 总览')}",
                f"- {pack_workspace_link('wiki/indexes/review-center.md', '审阅中心')}",
                f"- {pack_workspace_link('wiki/indexes/execution-center.md', '执行中心')}",
            ]
        )
        scorecards.append(
            {
                "protocol": protocol,
                "title": f"{protocol_title(protocol)} Pilot Scorecard",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "stage": stage,
                "summary": stage_summary,
                "metrics": metrics,
                "lifecycle_summary": lifecycle_summary,
            }
        )
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "scorecards": scorecards,
    }


def render_domain_pilots_index(domain_pilots: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    lines = [
        "# 领域 Pilot 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 协议总数：`{len(domain_pilots.get('scorecards', []))}`",
        "",
        "## 协议 Scorecards",
    ]
    for scorecard in domain_pilots.get("scorecards", []):
        metrics = scorecard.get("metrics", {})
        lines.append(
            f"- {workspace_link(scorecard['path'], scorecard['title'])}"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | curated `{int(metrics.get('decisions', 0)) + int(metrics.get('judgments', 0))}`"
            f" | outputs `{metrics.get('outputs', 0)}`"
            f" | receipts `{metrics.get('receipts', 0)}`"
            f" | lifecycle backlog `{metrics.get('lifecycle_concept_backlog', 0)}`"
            f" | retired `{metrics.get('lifecycle_retired_concepts', 0)}`"
            f" | dominant/mixed/bridge `{metrics.get('lifecycle_dominant_concepts', 0)}/{metrics.get('lifecycle_mixed_concepts', 0)}/{metrics.get('lifecycle_bridge_concepts', 0)}`"
        )
        lines.append(f"  - {scorecard.get('summary', '')}")
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [协议总览](./protocols.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_agent_pack(
    role: str,
    title: str,
    mission: str,
    protocol: str,
    compiled_at: str,
    focus: list[str],
    actions: list[str],
    links: list[str],
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": slugify(role),
            "kind": "agent-pack",
            "agent_role": role,
            "title": title,
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"- Agent role: `{role}`",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Compiled at: `{compiled_at}`",
        "",
        "## Mission",
        f"- {mission}",
        "",
        "## Current Focus",
    ]
    if not focus:
        lines.append("- 当前没有额外焦点。")
    else:
        lines.extend(f"- {item}" for item in focus)
    lines.extend(["", "## Suggested Actions"])
    if not actions:
        lines.append("- 当前没有新的建议动作。")
    else:
        lines.extend(f"- {item}" for item in actions)
    lines.extend(["", "## Related Links"])
    if not links:
        lines.append("- 当前没有相关链接。")
    else:
        lines.extend(f"- {item}" for item in links)
    return "\n".join(lines) + "\n"


def build_agent_packs(
    root: Path,
    entries: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    health = memory.get("health", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    repair_plan = health.get("repair_plan", {})
    pending_sources = pending_source_summary_ids(root, entries)
    drifted_pages = [page for page in decisions + judgments if page.get("citation_drift") == "true"]
    snapshot_gap_pages = [
        page for page in decisions + judgments if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0
    ]
    missing_asset_pages = [
        page
        for page in decisions + judgments
        if page.get("has_counter_evidence") != "true"
        or page.get("has_invalidation") != "true"
        or page.get("has_next_signals") != "true"
    ]
    ready_actions = repair_plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    all_actions = [*health.get("actions", []), *health.get("inactive_actions", [])]
    revert_ready_actions = [
        action for action in all_actions if str(action.get("status") or "") == "resolved" and action.get("last_receipt_path")
    ]
    execution_audit = build_execution_audit_snapshot(root, memory, active_protocol=active_protocol)
    packs: list[dict[str, str]] = []
    for spec in AGENT_PACK_LIBRARY:
        role = str(spec["role"])
        title = str(spec["title"])
        mission = str(spec["mission"])
        focus: list[str]
        actions: list[str]
        links: list[str]
        if role == "ingest-agent":
            focus = [
                f"待补来源摘要 `{len(pending_sources)}`",
                f"来源页 `{len(entries)}`",
                f"最近输出 `{len(recent_outputs)}`",
            ]
            actions = [f"补齐 `wiki/sources/{source_id}.md` 的来源摘要。" for source_id in pending_sources[:6]]
            if not actions:
                actions = ["继续观察新投料，并保持 source page 和 raw evidence 对齐。"]
            links = [
                "[来源索引](../../wiki/indexes/sources.md)",
                "[原料收件箱](../../wiki/indexes/Raw Inbox.md)",
                "[采集规则](../../schema/ingest.md)",
            ]
        elif role == "concept-agent":
            focus = [
                f"弱概念页 `{concept_quality.get('counts', {}).get('weak', 0)}`",
                f"冲突信号 `{concept_quality.get('counts', {}).get('conflict_signals', 0)}`",
                f"Rewrite 提案 `{rewrite_state.get('counts', {}).get('active', 0)}`",
            ]
            actions = [
                f"优先重写 `{candidate['path']}`，策略 `{candidate.get('rewrite_strategy', 'n/a')}`。"
                for candidate in concept_quality.get("rewrite_candidates", [])[:5]
            ]
            if not actions:
                actions = ["继续维护 concept 稳定性，确保冲突和证据缺口保持显式。"]
            links = [
                "[概念质量](../../wiki/indexes/concept-quality.md)",
                "[Rewrite 提案](../../wiki/indexes/rewrite-proposals.md)",
                "[概念索引](../../wiki/indexes/concepts.md)",
                "[机器记忆拓扑](../../wiki/indexes/machine-memory-topology.md)",
            ]
        elif role == "judgment-agent":
            focus = [
                f"最近输出 `{len(recent_outputs)}`",
                f"待补判断资产 `{len(missing_asset_pages)}`",
                f"证据漂移页面 `{len(drifted_pages)}`",
            ]
            actions = [
                f"补齐 `{page['path']}` 的反证 / 失效条件 / 下一信号。"
                for page in missing_asset_pages[:5]
            ]
            if recent_outputs:
                actions.append(f"检查最近输出 `{recent_outputs[0]['path']}` 是否值得晋升成 decision / judgment。")
            links = [
                "[判断资产](../../wiki/indexes/judgment-assets.md)",
                "[决策索引](../../wiki/indexes/decisions.md)",
                "[判断索引](../../wiki/indexes/judgments.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
            ]
        elif role == "review-agent":
            focus = [
                f"待审项目 `{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
                f"已到期 / 升级 `{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
                f"证据漂移 / snapshot gap `{len(drifted_pages)}` / `{len(snapshot_gap_pages)}`",
                f"生命周期概念待审 `{len(concept_backlog)}`",
                f"已退役概念 `{len(retired_concepts)}`",
            ]
            actions = [
                f"推进 lifecycle concept `{entry.get('title') or entry.get('page_id') or 'unknown'}`，状态 `{display_knowledge_lifecycle_state(str(entry.get('lifecycle_state') or 'unknown'))}`。"
                for entry in concept_backlog[:3]
            ]
            actions.extend(
                f"复查 `{page['path']}`，因为它已被新证据挑战。"
                for page in drifted_pages[:3]
            )
            if retired_concepts:
                retired = retired_concepts[0]
                actions.append(
                    f"确认 retired concept `{retired.get('title') or retired.get('page_id') or 'unknown'}` 是否需要 re-activate。"
                )
            if not actions:
                actions = [
                    f"推进 `{page['path']}` 的 review 状态。"
                    for page in (queue.get("pending_decisions", []) + queue.get("pending_judgments", []))[:5]
                ]
            actions = actions[:6]
            links = [
                "[审阅队列](../../wiki/indexes/review-queue.md)",
                "[审阅中心](../../wiki/indexes/review-center.md)",
                "[Aging 报告](../../wiki/indexes/aging-report.md)",
                "[概念索引](../../wiki/indexes/concepts.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
            ]
        elif role == "repair-planner":
            focus = [
                f"动作队列 `{len(health.get('actions', []))}`",
                f"Ready 动作 `{repair_plan.get('counts', {}).get('ready', 0)}`",
                f"执行提案 `{repair_plan.get('counts', {}).get('proposals', 0)}`",
            ]
            actions = [
                f"审阅 `{proposal.get('proposal_path', '')}`，确认 patch step `{len(proposal.get('page_patch_plan', []))}`。"
                for proposal in repair_plan.get("execution_proposals", [])[:5]
            ]
            if not actions:
                actions = ["当前没有新的 execution proposal，继续跟踪 machine-memory actions。"]
            links = [
                "[机器记忆动作队列](../../wiki/indexes/machine-memory-actions.md)",
                "[机器记忆修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
                "[修复待办](../../wiki/indexes/repair-backlog.md)",
                "[图谱健康](../../wiki/indexes/graph-health.md)",
            ]
        elif role == "execution-agent":
            focus = [
                f"可 apply 动作 `{len(apply_ready_actions)}`",
                f"可 revert 动作 `{len(revert_ready_actions)}`",
                f"执行 receipt `{execution_audit.get('counts', {}).get('receipts', 0)}`",
            ]
            actions = [
                f"对 `{action.get('id', '')}` 先做 `apply-action --dry-run`，再决定是否执行。"
                for action in apply_ready_actions[:5]
            ]
            if revert_ready_actions:
                actions.append(
                    f"必要时回滚 `{revert_ready_actions[0].get('id', '')}`，保持 low-risk execution 可逆。"
                )
            if not actions:
                actions = ["当前没有可执行动作，继续监控 execution audit 和 consistency signals。"]
            links = [
                "[执行中心](../../wiki/indexes/execution-center.md)",
                "[执行审计](../../wiki/indexes/execution-audit.md)",
                "[机器记忆修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        else:
            focus = [
                f"待补来源摘要 `{len(pending_sources)}`",
                f"已到期页面 `{len(aging.get('overdue', []))}`",
                f"证据漂移页面 `{len(drifted_pages)}`",
            ]
            actions = [
                "夜间优先刷新 compile / lint / review queue / cognitive history。",
                "把 recurring outputs 继续晋升成 decision / judgment。",
                "追踪 drift、aging 和 repair backlog，避免知识层长期漂移。",
            ]
            links = [
                "[炉心面板](../../wiki/indexes/furnace-center.md)",
                "[修复待办](../../wiki/indexes/repair-backlog.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
                "[编译状态](../../wiki/indexes/compile-status.md)",
            ]
        packs.append(
            {
                "role": role,
                "title": title,
                "mission": mission,
                "path": relative_path(root, agent_pack_path(root, role)),
                "content": render_agent_pack(
                    role,
                    title,
                    mission,
                    active_protocol,
                    compiled_at,
                    focus,
                    actions,
                    links,
                ),
            }
        )
    return packs


def render_agent_workbench(
    packs: list[dict[str, str]],
    compiled_at: str,
    active_protocol: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    dispatch_hints: list[str] = []
    if concept_backlog:
        dispatch_hints.append(
            f"先调 [Review Agent](../../output/agents/review-agent.md)，处理 `{len(concept_backlog)}` 个 lifecycle concept backlog。"
        )
    if lifecycle_counts.get("review_concepts", 0) or lifecycle_counts.get("revisit_concepts", 0):
        dispatch_hints.append(
            f"需要概念整理时，再调 [Concept Agent](../../output/agents/concept-agent.md)，消化 `{lifecycle_counts.get('review_concepts', 0) + lifecycle_counts.get('revisit_concepts', 0)}` 个 review / revisit concept。"
        )
    if retired_concepts:
        dispatch_hints.append(
            f"确认 `{min(len(retired_concepts), 3)}` 个 retired concept 是否要恢复进入工作面，优先走 [Review Agent](../../output/agents/review-agent.md)。"
        )
    if not dispatch_hints:
        dispatch_hints.append("当前 lifecycle governance 较干净，按输出、执行或 ingest 压力决定要调度哪个角色。")
    lines = [
        "# Agent Workbench",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Agent packs：`{len(packs)}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## 角色总览",
    ]
    if not packs:
        lines.append("- 当前还没有 agent packs。")
    else:
        for pack in packs:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | role `{pack['role']}`"
                f" | {pack['mission']}"
            )
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Dispatch Hints",
        ]
    )
    lines.extend(f"- {hint}" for hint in dispatch_hints)
    lines.extend(["", "## Lifecycle Concept Backlog"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
            "## 如何使用",
            "1. Human Owner 先在炉心面板里决定今天要调度哪个角色。",
            "2. 进入对应 agent pack，看当前焦点、建议动作和相关链接。",
            "3. 角色之间共享同一个 `raw / wiki / machine memory / decision / judgment`，不维护私有真相。",
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [图谱视图](./graph-view.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# 审阅队列",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 待审决策：`{len(queue['pending_decisions'])}`",
        f"- 待审判断：`{len(queue['pending_judgments'])}`",
        f"- 最近已审项目：`{len(queue['recently_reviewed'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- lifecycle concept backlog：`{len(concept_backlog)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 协议审阅焦点",
        *[f"- {line}" for line in PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])],
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
    lines.extend(["", "## 生命周期概念待审"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle state 标记为 `review` / `revisit` 的 concept。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 最近已审"])
    if not queue["recently_reviewed"]:
        lines.append("- 还没有已审阅的决策或判断页面。")
    else:
        for page in queue["recently_reviewed"][:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_aging_report(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    pages = decisions + judgments
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# Aging 报告",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 已排期复审：`{len(aging['scheduled'])}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
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
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 建议动作"])
    if aging["escalated"]:
        lines.append("- 优先处理升级项，补证据、更新状态或明确下一次复审窗口。")
    if aging["overdue"] and not aging["escalated"]:
        lines.append("- 先清理已到期页面，避免 review queue 长期堆积。")
    if lifecycle_revisit_entries:
        lines.append("- 把 lifecycle `revisit` 项和时间窗口型 overdue 项一起看，避免只盯 review date 而忽略证据失效。")
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


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_candidates = concept_quality.get("rewrite_candidates", [])
    conflict_signals = concept_quality.get("conflict_signals", [])
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]

    def render_page_item(page: dict[str, str]) -> str:
        path = html.escape(f"../../{page['path']}")
        status = html.escape(display_curated_status(page.get("status", "") or "unknown"))
        revisit = html.escape(page.get("revisit_after", "") or "none")
        return (
            f'<li><a href="{path}">{html.escape(page["title"])}</a>'
            f" | status {status}"
            f" | revisit {revisit}</li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        primary = html.escape(str(action.get("primary_path") or ""))
        status = html.escape(display_action_status(str(action.get("status") or "proposed")))
        priority = html.escape(str(action.get("priority") or "medium"))
        detail = ""
        if action.get("secondary_path"):
            detail = f" | secondary <code>{html.escape(str(action['secondary_path']))}</code>"
        command = ""
        if action.get("command_hint"):
            command = f" | command <code>{html.escape(str(action['command_hint']))}</code>"
        return (
            f"<li>{html.escape(str(action.get('title') or 'unnamed action'))}"
            f" | priority {priority}"
            f" | status {status}"
            f" | primary <code>{primary}</code>{detail}{command}</li>"
        )

    def render_concept_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        issues = html.escape(", ".join(item.get("issues", [])) or "none")
        return (
            f'<li><a href="../../wiki/concepts/{slug}.md">{title}</a>'
            f" | issues {issues}"
            f" | sources {int(item.get('source_count', 0))}</li>"
        )

    def render_rewrite_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        status = html.escape(display_rewrite_proposal_status(str(item.get("status") or "proposed")))
        return (
            f'<li><a href="../../wiki/rewrite-proposals/{slug}.md">{title}</a>'
            f" | status {status}"
            f" | apply_ready {html.escape(str(bool(item.get('apply_ready'))).lower())}</li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{override}{invalidation}{active_corpora}</li>"

    pending_list = "".join(render_page_item(page) for page in pending_items[:12]) or "<li>当前没有待审项目。</li>"
    overdue_list = "".join(render_page_item(page) for page in aging.get("overdue", [])[:10]) or "<li>当前没有已到期待复审页面。</li>"
    escalated_list = "".join(render_page_item(page) for page in aging.get("escalated", [])[:10]) or "<li>当前没有需要升级处理的页面。</li>"
    lifecycle_backlog_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    ready_action_list = "".join(render_action_item(action) for action in ready_actions[:10]) or "<li>当前没有 ready repair action。</li>"
    apply_ready_action_list = (
        "".join(render_action_item(action) for action in apply_ready_actions[:8])
        or "<li>当前没有可直接 semi-auto apply 的低风险动作。</li>"
    )
    rewrite_list = "".join(render_concept_item(item) for item in rewrite_candidates[:10]) or "<li>当前没有高优先级弱概念页。</li>"
    conflict_list = "".join(render_concept_item(item) for item in conflict_signals[:10]) or "<li>当前没有显式概念冲突信号。</li>"
    rewrite_proposal_list = "".join(render_rewrite_item(item) for item in rewrite_proposals[:10]) or "<li>当前没有 rewrite proposal。</li>"

    summary_cards = [
        ("待审项目", str(len(pending_items))),
        ("已到期复审", str(len(aging.get("overdue", [])))),
        ("升级项", str(len(aging.get("escalated", [])))),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("ready actions", str(plan.get("counts", {}).get("ready", 0))),
        ("重写候选", str(concept_quality.get("counts", {}).get("rewrite_candidates", 0))),
        ("冲突信号", str(concept_quality.get("counts", {}).get("conflict_signals", 0))),
        ("rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可应用 rewrite", str(len(apply_ready_rewrites))),
        ("可应用动作", str(len(apply_ready_actions))),
    ]

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Review Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #fffaf0; --ink: #1f2937; --muted: #6b7280; --panel: #ffffff; --line: #e5e7eb; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #fffaf0 0%, #f3f4f6 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1120px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: rgba(255,255,255,0.94); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .lists { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin: 18px 0 24px; }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #b45309; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #92400e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    code { background: #f3f4f6; padding: 1px 5px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Review Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议焦点：<code>{html.escape(active_protocol)}</code>。这是炼丹炉的人用审阅 cockpit：把 review、aging、repair 和 concept rewrite 收在一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="lists">',
            '    <div class="panel"><h2>待审项目</h2><ul>',
            f"{pending_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已到期 / 需升级</h2><ul>',
            f"{overdue_list}",
            f"{escalated_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>生命周期概念待审</h2><ul>',
            f"{lifecycle_backlog_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已退役概念</h2><ul>',
            f"{retired_concept_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Ready Repair Actions</h2><ul>',
            f"{ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Safe Apply Actions</h2><ul>',
            f"{apply_ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念重写优先级</h2><ul>',
            f"{rewrite_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念冲突信号</h2><ul>',
            f"{conflict_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Rewrite Proposals</h2><ul>',
            f"{rewrite_proposal_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>相关入口</h2><ul>',
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '      <li><a href="../../wiki/indexes/review-center.md">Review Center Dashboard</a></li>',
            '      <li><a href="../../wiki/indexes/review-queue.md">审阅队列</a></li>',
            '      <li><a href="../../wiki/indexes/aging-report.md">Aging 报告</a></li>',
            '      <li><a href="../../wiki/indexes/cognitive-history.md">认知历史</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">机器记忆动作队列</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">机器记忆修复计划</a></li>',
            '      <li><a href="../../wiki/indexes/judgment-assets.md">判断资产</a></li>',
            '      <li><a href="../../wiki/indexes/execution-center.md">执行中心</a></li>',
            '      <li><a href="../../wiki/indexes/concept-quality.md">概念质量</a></li>',
            '      <li><a href="../../wiki/indexes/rewrite-proposals.md">Rewrite Proposals</a></li>',
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def protocol_scorecard(domain_pilots: dict[str, Any], protocol: str) -> dict[str, Any]:
    for scorecard in domain_pilots.get("scorecards", []):
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "") == protocol:
            return scorecard
    return {}


def protocol_output_pack_rows(output_packs: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pack in output_packs.get("review_packs", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Review Pack",
                "title": str(pack.get("title") or "Review Pack"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reasons") or "manual review"),
            }
        )
    for pack in output_packs.get("decision_memos", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Decision Memo",
                "title": str(pack.get("title") or "Decision Memo"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reviewed_at") or "reviewed"),
            }
        )
    for pack in output_packs.get("sop_drafts", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "SOP Draft",
                "title": str(pack.get("title") or "SOP Draft"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("risk") or "medium"),
            }
        )
    rows.sort(key=lambda item: (item["kind"], item["title"].lower()))
    return rows[:limit]


def protocol_execution_receipts(execution_audit: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    protocol_buckets = execution_audit.get("recent_by_protocol", {})
    for bucket_name, label in (("recent_apply", "apply"), ("recent_revert", "revert")):
        bucket_rows = []
        if isinstance(protocol_buckets, dict):
            scoped = protocol_buckets.get(bucket_name, {})
            if isinstance(scoped, dict):
                protocol_rows = scoped.get(protocol, [])
                if isinstance(protocol_rows, list):
                    bucket_rows = protocol_rows
        if not bucket_rows:
            bucket_rows = execution_audit.get(bucket_name, [])
        for record in bucket_rows:
            if str(record.get("protocol") or DEFAULT_PROTOCOL) != protocol:
                continue
            rows.append(
                {
                    "kind": label,
                    "title": str(record.get("title") or record.get("action_id") or "receipt"),
                    "action_id": str(record.get("action_id") or ""),
                    "receipt_path": str(record.get("receipt_path") or ""),
                    "applied_at": str(record.get("applied_at") or ""),
                }
            )
    rows.sort(key=lambda item: (item["applied_at"], item["title"].lower()), reverse=True)
    return rows[:limit]


def furnace_quick_commands(
    active_protocol: str,
    apply_ready_actions: list[dict[str, Any]],
    apply_ready_rewrites: list[dict[str, Any]],
) -> list[str]:
    commands = [
        "PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status",
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . ask \"对当前主题做协议化总结\" --format report --protocol {active_protocol}",
        "PYTHONPATH=src python3 -m aiwiki.cli --root . nightly",
    ]
    if apply_ready_actions:
        first_action = apply_ready_actions[0]
        action_id = str(first_action.get("id") or "")
        bundle_hint = str(first_action.get("bundle_path") or "")
        if action_id:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"
            )
            if bundle_hint:
                commands.append(
                    f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_hint}"
                )
    if apply_ready_rewrites:
        first_rewrite = apply_ready_rewrites[0]
        slug = str(first_rewrite.get("slug") or "")
        if slug:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
            )
    return commands[:6]


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lifecycle_counts = lifecycle_summary.get("counts", {})
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    citation_drift_count = sum(1 for page in decisions + judgments if page.get("citation_drift") == "true")
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:6]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)
    next_steps: list[str] = []
    if concept_backlog:
        next_steps.append(f"先处理 `{min(len(concept_backlog), 5)}` 个 lifecycle concept backlog。")
    if apply_ready_actions:
        next_steps.append(f"先处理 `{len(apply_ready_actions)}` 个可直接 `apply-action` 的低风险动作。")
    if apply_ready_rewrites:
        next_steps.append(f"应用 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal。")
    if aging.get("escalated"):
        next_steps.append(f"优先复查 `{len(aging.get('escalated', []))}` 个升级项。")
    if pending_items:
        next_steps.append(f"继续审 `{len(pending_items)}` 个 decision / judgment 页面。")
    if retired_concepts and not concept_backlog:
        next_steps.append(f"检查 `{min(len(retired_concepts), 3)}` 个 retired concept 是否需要重新激活。")
    if not next_steps:
        next_steps.append("当前没有紧急执行项，优先看最新输出和图谱漂移。")

    lines = [
        "# 炉心面板",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 来源节点：`{len(memory.get('source_nodes', []))}`",
        f"- 概念节点：`{len(memory.get('concept_nodes', []))}`",
        f"- 待审项目：`{len(pending_items)}`",
        f"- 已到期 / 升级：`{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
        f"- 生命周期概念待审 / 已退役：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- 证据漂移：`{citation_drift_count}`",
        f"- Ready repair actions：`{len(ready_actions)}`",
        f"- 可直接 apply 的动作：`{len(apply_ready_actions)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 可直接 apply 的 rewrite：`{len(apply_ready_rewrites)}`",
        f"- 页级 patch step：`{page_patch_steps}`",
        f"- 当前协议 stage：`{scorecard.get('stage', 'seed') if scorecard else 'unknown'}`",
        f"- 当前协议 outputs / receipts：`{scorecard_metrics.get('outputs', 0)}` / `{scorecard_metrics.get('receipts', 0)}`",
        f"- 当前协议 review packs / memos / SOP：`{scorecard_metrics.get('review_packs', 0)}` / `{scorecard_metrics.get('decision_memos', 0)}` / `{scorecard_metrics.get('sop_drafts', 0)}`",
        f"- 最近输出：`{len(recent_outputs)}`",
        "- 本地控制面板：`output/control/furnace-center.html`",
        "",
        "## 今天先做什么",
    ]
    for index, step in enumerate(next_steps, start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "## 即刻可执行",
        ]
    )
    if apply_ready_actions:
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['title']}` | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if apply_ready_rewrites:
        lines.append("")
        lines.append("### Apply-Ready Rewrites")
        for proposal in apply_ready_rewrites[:8]:
            lines.append(
                f"- `{proposal['target_path']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Page-Level Patch Plan")
        for proposal in execution_proposals[:4]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(f"- `{proposal['action_id']}` | patch step `{len(patch_plan)}`")
            for patch in patch_plan[:3]:
                lines.append(
                    f"  - `{patch.get('path', '')}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
    if not any((apply_ready_actions, apply_ready_rewrites, execution_proposals)):
        lines.append("- 当前没有即刻可执行项。")

    lines.extend(
        [
            "",
            "## 最近输出",
        ]
    )
    if not recent_outputs:
        lines.append("- 当前还没有 recent outputs。")
    else:
        for artifact in recent_outputs:
            lines.append(
                f"- [{artifact['title']}](../../{artifact['path']})"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )

    lines.extend(["", "## 当前协议 Pilot"])
    if not scorecard:
        lines.append("- 当前协议还没有 pilot scorecard。")
    else:
        lines.append(
            f"- [{scorecard['title']}](../../{scorecard['path']})"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | {scorecard.get('summary', '')}"
        )
        gaps = compact_section_lines(scorecard.get("content", ""), "Gaps", fallback="- 当前没有明显结构性缺口。", limit=4)
        lines.append("")
        lines.append("### 当前缺口")
        lines.extend(gaps)
        next_moves_lines = compact_section_lines(scorecard.get("content", ""), "Next Moves", fallback="- 当前没有额外 next moves。", limit=4)
        lines.append("")
        lines.append("### 下一动作")
        lines.extend(next_moves_lines)

    lines.extend(["", "## Lifecycle 治理摘要"])
    lines.extend(
        [
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "### Lifecycle Concept Backlog",
        ]
    )
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))

    lines.extend(["", "## 最新输出 Packs"])
    if not pack_rows:
        lines.append("- 当前协议还没有 review pack / decision memo / SOP draft。")
    else:
        for pack in pack_rows:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | kind `{pack['kind']}`"
                f" | meta `{pack['meta'] or 'n/a'}`"
            )

    lines.extend(["", "## 最近执行回执"])
    if not receipt_rows:
        lines.append("- 当前协议还没有 execution receipt。")
    else:
        for receipt in receipt_rows:
            receipt_path = receipt["receipt_path"] or ".aiwiki/state/execution-receipts.jsonl"
            lines.append(
                f"- `{receipt['title']}`"
                f" | kind `{receipt['kind']}`"
                f" | action `{receipt['action_id']}`"
                f" | receipt `{receipt_path}`"
                f" | at `{receipt['applied_at'] or 'unknown'}`"
            )

    lines.extend(
        [
            "",
            "## 最近已审 / 已沉淀",
        ]
    )
    if recent_reviewed:
        for page in recent_reviewed:
            lines.append(
                f"- [{page['title']}](../../{page['path']})"
                f" | status `{display_curated_status(page.get('status', 'unknown'))}`"
                f" | reviewed `{page.get('reviewed_at', '') or 'unknown'}`"
            )
    else:
        lines.append("- 当前还没有最近已审项目。")

    lines.extend(["", "## 快速命令"])
    for command in quick_commands:
        lines.append(f"- `{command}`")

    lines.extend(
        [
            "",
            "## 快速跳转",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [Agent Workbench](./agent-workbench.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [领域 Pilot 总览](./domain-pilots.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [图谱视图](./graph-view.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [协议总览](./protocols.md)",
            "- [输出面板](./Outputs.md)",
            "- [本地审阅面板](../../output/review/review-center.html)",
            "- [本地图谱视图](../../output/graph/machine-memory.html)",
            "- [本地炉心面板](../../output/control/furnace-center.html)",
            "- [本地执行面板](../../output/control/execution-center.html)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_furnace_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:8]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)

    def render_page_item(page: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(page["path"])}">{html.escape(page["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(display_curated_status(page.get('status', 'unknown')))}</span></li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        command = html.escape(str(action.get("command_hint") or ""))
        return (
            f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
            f" <span class=\"item-meta\">{html.escape(str(action.get('priority') or 'medium'))} / {html.escape(display_action_status(str(action.get('status') or 'proposed')))}</span>"
            f"<div><code>{html.escape(str(action.get('primary_path') or ''))}</code></div>"
            f"{f'<div><code>{command}</code></div>' if command else ''}</li>"
        )

    def render_rewrite_item(proposal: dict[str, Any]) -> str:
        slug = html.escape(str(proposal.get("slug") or ""))
        target = html.escape(str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"))
        command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
        return (
            f"<li><strong><a href=\"../../wiki/rewrite-proposals/{slug}.md\">{html.escape(str(proposal.get('title') or slug))}</a></strong>"
            f" <span class=\"item-meta\">{html.escape(display_rewrite_proposal_status(str(proposal.get('status') or 'proposed')))}</span>"
            f"<div><code>{target}</code></div><div><code>{html.escape(command)}</code></div></li>"
        )

    def render_output_item(artifact: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(artifact["path"])}">{html.escape(artifact["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(artifact['format'] or 'unknown')} / {html.escape(artifact['protocol'] or DEFAULT_PROTOCOL)} / {html.escape(artifact['created_at'] or 'unknown')}</span></li>"
        )

    def render_proposal_item(proposal: dict[str, Any]) -> str:
        patch_count = len(proposal.get("page_patch_plan", []))
        return (
            f"<li><strong>{html.escape(str(proposal.get('action_id') or 'proposal'))}</strong>"
            f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))}</span>"
            f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
            f"<div><code>{html.escape(', '.join(proposal.get('target_paths', [])) or 'none')}</code></div>"
            f"<div class=\"item-meta\">patch steps {patch_count}</div></li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{override}{invalidation}{active_corpora}</li>"

    summary_cards = [
        ("来源", str(len(memory.get("source_nodes", [])))),
        ("概念", str(len(memory.get("concept_nodes", [])))),
        ("待审", str(len(pending_items))),
        ("到期/升级", f"{len(aging.get('overdue', []))}/{len(aging.get('escalated', []))}"),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("Ready 动作", str(plan.get("counts", {}).get("ready", 0))),
        ("可 apply 动作", str(len(apply_ready_actions))),
        ("Rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可 apply rewrite", str(len(apply_ready_rewrites))),
        ("Patch Steps", str(page_patch_steps)),
        ("最近输出", str(len(recent_outputs))),
        ("Pilot Stage", str(scorecard.get("stage", "unknown") if scorecard else "unknown")),
        ("Review Packs", str(scorecard_metrics.get("review_packs", 0))),
        ("Decision Memos", str(scorecard_metrics.get("decision_memos", 0))),
        ("SOP Drafts", str(scorecard_metrics.get("sop_drafts", 0))),
        ("Receipts", str(scorecard_metrics.get("receipts", 0))),
    ]

    protocol_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])[:3]
    nightly_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly", [])[:3]
    pending_markup = "".join(render_page_item(page) for page in pending_items[:8]) or "<li>当前没有待审项目。</li>"
    aging_markup = "".join(render_page_item(page) for page in (aging.get("escalated", []) + aging.get("overdue", []))[:8]) or "<li>当前没有已到期或升级项目。</li>"
    apply_action_markup = "".join(render_action_item(action) for action in apply_ready_actions[:8]) or "<li>当前没有可直接 apply 的低风险动作。</li>"
    rewrite_markup = "".join(render_rewrite_item(proposal) for proposal in apply_ready_rewrites[:8]) or "<li>当前没有可直接 apply 的 rewrite proposal。</li>"
    proposal_markup = "".join(render_proposal_item(proposal) for proposal in execution_proposals[:8]) or "<li>当前没有 execution proposal。</li>"
    output_markup = "".join(render_output_item(artifact) for artifact in recent_outputs[:10]) or "<li>当前还没有 recent outputs。</li>"
    reviewed_markup = "".join(render_page_item(page) for page in recent_reviewed) or "<li>当前还没有最近已审项目。</li>"
    focus_markup = "".join(f"<li>{html.escape(item)}</li>" for item in protocol_focus + nightly_focus) or "<li>当前协议没有额外焦点。</li>"
    lifecycle_backlog_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    pack_markup = "".join(
        f"<li><strong><a href=\"../../{html.escape(row['path'])}\">{html.escape(row['title'])}</a></strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['meta'] or 'n/a')}</span></li>"
        for row in pack_rows[:10]
    ) or "<li>当前协议还没有 review pack / decision memo / SOP draft。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(row['title'])}</strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['action_id'])}</span>"
        f"<div><code>{html.escape(row['receipt_path'] or '.aiwiki/state/execution-receipts.jsonl')}</code></div>"
        f"<div class=\"item-meta\">{html.escape(row['applied_at'] or 'unknown')}</div></li>"
        for row in receipt_rows[:10]
    ) or "<li>当前协议还没有 execution receipt。</li>"
    quick_command_markup = "".join(
        f"<li><code>{html.escape(command)}</code></li>" for command in quick_commands
    ) or "<li>当前没有额外快速命令。</li>"
    scorecard_markup = (
        "\n".join(
            [
                f'<p><strong><a href="../../{html.escape(str(scorecard.get("path") or ""))}">{html.escape(str(scorecard.get("title") or "Pilot Scorecard"))}</a></strong></p>',
                f'<p class="item-meta">stage {html.escape(str(scorecard.get("stage") or "seed"))} · {html.escape(str(scorecard.get("summary") or ""))}</p>',
                '<ul>'
                + "".join(
                    f"<li>{html.escape(line.lstrip('- ').strip())}</li>"
                    for line in compact_section_lines(
                        str(scorecard.get("content") or ""),
                        "Next Moves",
                        fallback="- 当前没有额外 next moves。",
                        limit=4,
                    )
                )
                + "</ul>",
            ]
        )
        if scorecard
        else "<p>当前协议还没有 pilot scorecard。</p>"
    )

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Furnace Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: radial-gradient(circle at top right, #dbeafe 0%, #f8fafc 40%, #fefce8 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1180px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; }",
            "    .hero { margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "    .quick-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }",
            "    .quick-links a { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; background: #ffffff; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel hero">',
            "    <h1>Furnace Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code> ({html.escape(protocol_title(active_protocol))})。这是炼丹炉的统一入口：把 review、graph、execution 和 recent outputs 收到一个地方。</p>",
            '    <div class="quick-links">',
            '      <a href="../../wiki/indexes/furnace-center.md">Markdown 面板</a>',
            '      <a href="../../wiki/indexes/review-center.md">审阅中心</a>',
            '      <a href="../../wiki/indexes/execution-center.md">执行中心</a>',
            '      <a href="../../wiki/indexes/execution-audit.md">执行审计</a>',
            '      <a href="../../wiki/indexes/agent-workbench.md">Agent Workbench</a>',
            '      <a href="../../wiki/indexes/cognitive-history.md">认知历史</a>',
            '      <a href="../../wiki/indexes/output-packs.md">输出 Packs</a>',
            '      <a href="../../wiki/indexes/domain-pilots.md">领域 Pilots</a>',
            '      <a href="../../wiki/indexes/judgment-assets.md">判断资产</a>',
            '      <a href="../../wiki/indexes/graph-view.md">图谱视图</a>',
            '      <a href="../../wiki/indexes/repair-backlog.md">修复待办</a>',
            '      <a href="../../wiki/indexes/protocols.md">协议总览</a>',
            '      <a href="../../output/review/review-center.html">审阅 HTML</a>',
            '      <a href="../../output/graph/machine-memory.html">图谱 HTML</a>',
            '      <a href="../../output/control/execution-center.html">执行 HTML</a>',
            '      <a href="../../output/control/execution-audit.html">审计 HTML</a>',
            "    </div>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>待审 / 已到期</h2><ul>{pending_markup}{aging_markup}</ul></div>',
            '    <div class="panel"><h2>生命周期治理</h2>'
            f'<p class="item-meta">review {html.escape(str(lifecycle_summary.get("counts", {}).get("review_concepts", 0)))}'
            f' · revisit {html.escape(str(lifecycle_summary.get("counts", {}).get("revisit_concepts", 0)))}'
            f' · active {html.escape(str(lifecycle_summary.get("counts", {}).get("active_concepts", 0)))}</p>'
            f"<ul>{lifecycle_backlog_markup}</ul></div>",
            f'    <div class="panel"><h2>已退役概念</h2><ul>{retired_concept_markup}</ul></div>',
            f'    <div class="panel"><h2>Safe Apply</h2><ul>{apply_action_markup}</ul></div>',
            f'    <div class="panel"><h2>Apply-Ready Rewrites</h2><ul>{rewrite_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>最近输出</h2><ul>{output_markup}</ul></div>',
            f'    <div class="panel"><h2>协议焦点</h2><ul>{focus_markup}</ul></div>',
            f'    <div class="panel"><h2>最近已审 / 已沉淀</h2><ul>{reviewed_markup}</ul></div>',
            f'    <div class="panel"><h2>当前协议 Pilot</h2>{scorecard_markup}</div>',
            f'    <div class="panel"><h2>最新输出 Packs</h2><ul>{pack_markup}</ul></div>',
            f'    <div class="panel"><h2>最近执行回执</h2><ul>{receipt_markup}</ul></div>',
            f'    <div class="panel"><h2>快速命令</h2><ul>{quick_command_markup}</ul></div>',
            '    <div class="panel"><h2>系统状态</h2><ul>'
            f'<li>graph components <code>{html.escape(str(health.get("component_count", 0)))}</code></li>'
            f'<li>bridge concepts <code>{html.escape(str(len(health.get("bridge_concept_slugs", []))))}</code></li>'
            f'<li>conflict signals <code>{html.escape(str(concept_quality.get("counts", {}).get("conflict_signals", 0)))}</code></li>'
            f'<li>gap signals <code>{html.escape(str(concept_quality.get("counts", {}).get("gap_signals", 0)))}</code></li>'
            f'<li>rewrite candidates <code>{html.escape(str(concept_quality.get("counts", {}).get("rewrite_candidates", 0)))}</code></li>'
            f'<li>ready batches <code>{html.escape(str(plan.get("counts", {}).get("batches", 0)))}</code></li>'
            "</ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
    *,
    compile_state: dict[str, Any] | None = None,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    compile_state = compile_state or default_compile_state()
    phase_summary = [
        phase
        for phase in compile_state.get("phase_summary", [])
        if isinstance(phase, dict) and str(phase.get("name") or "")
    ]
    dirty_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_source_ids", [])
        if str(entry_id)
    ]
    clean_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_concept_source_ids", [])
        if str(entry_id)
    ]
    clean_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_concept_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_concept_slugs", [])
        if str(slug)
    ]
    clean_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_concept_slugs", [])
        if str(slug)
    ]
    dirty_index_artifacts = [
        str(path)
        for path in compile_state.get("dirty_index_artifacts", [])
        if str(path)
    ]
    clean_index_artifacts = [
        str(path)
        for path in compile_state.get("clean_index_artifacts", [])
        if str(path)
    ]
    dirty_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("dirty_maintenance_artifacts", [])
        if str(path)
    ]
    clean_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("clean_maintenance_artifacts", [])
        if str(path)
    ]
    entry_by_id = {
        str(entry.get("id") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    concept_by_slug = {
        str(record.get("slug") or ""): record
        for record in concepts
        if isinstance(record, dict) and str(record.get("slug") or "")
    }
    detail_labels = {
        "manifest_entries": "entries",
        "changed_entries": "changed",
        "added_entries": "added",
        "updated_entries": "updated",
        "removed_entries": "removed",
        "source_pages": "sources",
        "dirty_sources": "dirty",
        "clean_sources": "clean",
        "updated_pages": "updated_pages",
        "skipped_pages": "skipped_pages",
        "concept_sources": "concept_sources",
        "dirty_concept_sources": "dirty_concept_sources",
        "clean_concept_sources": "clean_concept_sources",
        "concept_pages": "concepts",
        "dirty_concepts": "dirty_concepts",
        "clean_concepts": "clean_concepts",
        "tracked_artifacts": "tracked_artifacts",
        "dirty_artifacts": "dirty_artifacts",
        "clean_artifacts": "clean_artifacts",
        "updated_artifacts": "updated_artifacts",
        "skipped_artifacts": "skipped_artifacts",
        "removed_generated_pages": "removed_generated_pages",
        "material_state_entries": "material_state_entries",
        "archive_candidates": "archive_candidates",
        "active_corpora": "active_corpora",
        "knowledge_lifecycle_entries": "knowledge_lifecycle_entries",
    }
    lines = [
        "# 编译状态",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "- Compile state：`.aiwiki/state/compile-state.json`",
        "- Concept build state：`.aiwiki/state/concept-build-state.json`",
        f"- Dirty source：`{len(dirty_source_ids)}`",
        f"- Clean source：`{len(clean_source_ids)}`",
        f"- Dirty concept source：`{len(dirty_concept_source_ids)}`",
        f"- Clean concept source：`{len(clean_concept_source_ids)}`",
        f"- Dirty concept：`{len(dirty_concept_slugs)}`",
        f"- Clean concept：`{len(clean_concept_slugs)}`",
        f"- Dirty index artifact：`{len(dirty_index_artifacts)}`",
        f"- Clean index artifact：`{len(clean_index_artifacts)}`",
        f"- Dirty maintenance artifact：`{len(dirty_maintenance_artifacts)}`",
        f"- Clean maintenance artifact：`{len(clean_maintenance_artifacts)}`",
        "- 总索引位于 `index.md`。",
        "- 运行时规则位于 `schema/`。",
        "- 协议规则位于 `schema/protocols/`。",
        "- 协议总览位于 `protocols.md`。",
        "- 炉心面板位于 `furnace-center.md`。",
        "- 执行中心位于 `execution-center.md`。",
        "- 输出 Pack 总览位于 `output-packs.md`。",
        "- 领域 Pilot 总览位于 `domain-pilots.md`。",
        "- 操作日志位于 `log.md`。",
        "- Agent Workbench 位于 `agent-workbench.md`。",
        "- 决策索引位于 `decisions.md`。",
        "- 判断索引位于 `judgments.md`。",
        "- 判断资产盘点位于 `judgment-assets.md`。",
        "- 认知历史位于 `cognitive-history.md`。",
        "- 审阅队列位于 `review-queue.md`。",
        "- 审阅中心位于 `review-center.md`。",
        "- aging 报告位于 `aging-report.md`。",
        "- 机器记忆摘要位于 `machine-memory.md`。",
        "- 图谱视图位于 `graph-view.md`。",
        "- 机器记忆拓扑位于 `machine-memory-topology.md`。",
        "- 机器记忆动作队列位于 `machine-memory-actions.md`。",
        "- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。",
        "- Rewrite 提案队列位于 `rewrite-proposals.md`。",
        "- 图谱健康页位于 `graph-health.md`。",
        "- 漂移报告位于 `drift-report.md`。",
        "- 修复待办位于 `repair-backlog.md`。",
        "- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。",
        "- lint 结果输出在 `output/lint/`。",
    ]
    lines.extend(["", "## Compile Phases"])
    if not phase_summary:
        lines.append("- 当前还没有 compile phase summary。")
    else:
        for phase in phase_summary:
            details = phase.get("details", {})
            detail_chunks = []
            if isinstance(details, dict):
                for key, value in details.items():
                    if key not in detail_labels:
                        continue
                    detail_chunks.append(f"{detail_labels[key]}={value}")
            label = str(phase.get("label") or phase.get("name") or "")
            mode = str(phase.get("mode") or "full")
            status = str(phase.get("status") or "completed")
            detail_suffix = f" | {', '.join(detail_chunks)}" if detail_chunks else ""
            lines.append(f"- `{phase['name']}` `{label}` [{mode}/{status}]{detail_suffix}")
    lines.extend(["", "## Dirty Sources"])
    if not dirty_source_ids:
        lines.append("- 当前没有 dirty source page。")
    else:
        for entry_id in dirty_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_source_ids) > 8:
            lines.append(f"- 其余 dirty source：`{len(dirty_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concept Sources"])
    if not dirty_concept_source_ids:
        lines.append("- 当前没有 dirty concept source。")
    else:
        for entry_id in dirty_concept_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_concept_source_ids) > 8:
            lines.append(f"- 其余 dirty concept source：`{len(dirty_concept_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concepts"])
    if not dirty_concept_slugs:
        lines.append("- 当前没有 dirty concept page。")
    else:
        for slug in dirty_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_concept_slugs) > 8:
            lines.append(f"- 其余 dirty concept：`{len(dirty_concept_slugs) - 8}`")
    lines.extend(["", "## Dirty Index Artifacts"])
    if not dirty_index_artifacts:
        lines.append("- 当前没有 dirty index artifact。")
    else:
        for relative in dirty_index_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_index_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_index_artifacts) - 12}`")
    lines.extend(["", "## Dirty Maintenance Artifacts"])
    if not dirty_maintenance_artifacts:
        lines.append("- 当前没有 dirty maintenance artifact。")
    else:
        for relative in dirty_maintenance_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_maintenance_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_maintenance_artifacts) - 12}`")
    return "\n".join(lines) + "\n"


def render_master_index(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    lines = [
        "# 知识库总索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "",
        "## 核心页面",
        "- [来源索引](./sources.md)",
        "- [概念索引](./concepts.md)",
        "- [概念质量](./concept-quality.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [判断资产](./judgment-assets.md)",
        "- [Agent Workbench](./agent-workbench.md)",
        "- [认知历史](./cognitive-history.md)",
        "- [协议总览](./protocols.md)",
        "- [炉心面板](./furnace-center.md)",
        "- [执行中心](./execution-center.md)",
        "- [输出 Pack 总览](./output-packs.md)",
        "- [领域 Pilot 总览](./domain-pilots.md)",
        "- [审阅队列](./review-queue.md)",
        "- [审阅中心](./review-center.md)",
        "- [Aging 报告](./aging-report.md)",
        "- [编译状态](./compile-status.md)",
        "- [机器记忆](./machine-memory.md)",
        "- [图谱视图](./graph-view.md)",
        "- [机器记忆拓扑](./machine-memory-topology.md)",
        "- [机器记忆动作队列](./machine-memory-actions.md)",
        "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "- [图谱健康](./graph-health.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [操作日志](./log.md)",
        "- [运行时规则](../../schema/index.md)",
        "- [协议规则](../../schema/protocols/index.md)",
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


def review_center_html_path(root: Path) -> Path:
    return root / "output" / "review" / "review-center.html"


def furnace_center_html_path(root: Path) -> Path:
    return root / "output" / "control" / "furnace-center.html"


def shell_summary_path(root: Path) -> Path:
    return root / "output" / "control" / "shell-summary.json"


def execution_center_html_path(root: Path) -> Path:
    return root / "output" / "control" / "execution-center.html"


def execution_audit_html_path(root: Path) -> Path:
    return root / "output" / "control" / "execution-audit.html"


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


def execution_center_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "execution-center.md"


def execution_audit_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "execution-audit.md"


def agent_workbench_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "agent-workbench.md"


def agent_pack_path(root: Path, role: str) -> Path:
    return root / "output" / "agents" / f"{slugify(role)}.md"


def output_packs_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "output-packs.md"


def domain_pilots_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def review_packs_dir(root: Path) -> Path:
    return root / "output" / "packs" / "review"


def decision_memos_dir(root: Path) -> Path:
    return root / "output" / "packs" / "decision-memos"


def sop_drafts_dir(root: Path) -> Path:
    return root / "output" / "packs" / "sop-drafts"


def pack_stem(seed: str) -> str:
    cleaned = seed.replace("/", "-").replace("\\", "-").replace(".md", "")
    return slugify(cleaned)[:96] or "pack"


def review_pack_path(root: Path, target_path: str) -> Path:
    return review_packs_dir(root) / f"{pack_stem(target_path)}.md"


def decision_memo_path(root: Path, target_path: str) -> Path:
    return decision_memos_dir(root) / f"{pack_stem(target_path)}.md"


def sop_draft_path(root: Path, action_id: str) -> Path:
    return sop_drafts_dir(root) / f"{pack_stem(action_id)}.md"


def execution_proposals_dir(root: Path) -> Path:
    return root / "wiki" / "execution-proposals"


def execution_proposal_path(root: Path, action_id: str) -> Path:
    return execution_proposals_dir(root) / f"{slugify(action_id)}.md"


def execution_bundles_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-bundles"


def execution_bundle_path(root: Path, action_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(action_id)}.json"


def execution_receipts_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-receipts"


def execution_receipt_path(root: Path, action_id: str) -> Path:
    return execution_receipts_dir(root) / f"{slugify(action_id)}.json"


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def concept_quality_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "concept-quality.md"


def concept_rewrite_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "rewrite-proposals.md"


def concept_rewrite_proposal_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "rewrite-proposals" / f"{slug}.md"


def machine_memory_action_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-actions.json"


def concept_rewrite_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-rewrite-proposals.json"


def manual_link_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manual-links.json"


def repair_backlog_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "repair-backlog.md"


def judgment_assets_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "judgment-assets.md"


def cognitive_history_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "cognitive-history.md"


def aging_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "aging-report.md"


def nightly_health_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "nightly-health.json"


def compile_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "compile-state.json"


def concept_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-build-state.json"


def material_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-state.json"


def active_corpora_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "active-corpora.json"


def runtime_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime-history.jsonl"


def material_routing_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-routing.json"


def archive_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "archive-candidates.json"


def knowledge_lifecycle_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle.json"


def knowledge_lifecycle_override_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"


def material_archive_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-archives.json"


def load_json_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_json_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_document(document), encoding="utf-8")


def load_jsonl_documents(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                documents.append(document)
    return documents


def default_compile_state() -> dict[str, Any]:
    return {
        "version": 1,
        "compiled_at": "",
        "manifest_entry_count": 0,
        "dirty_source_ids": [],
        "clean_source_ids": [],
        "dirty_concept_source_ids": [],
        "clean_concept_source_ids": [],
        "dirty_concept_slugs": [],
        "clean_concept_slugs": [],
        "dirty_index_artifacts": [],
        "clean_index_artifacts": [],
        "dirty_maintenance_artifacts": [],
        "clean_maintenance_artifacts": [],
        "phase_summary": [],
    }


def load_compile_state(root: Path) -> dict[str, Any]:
    document = load_json_document(compile_state_path(root))
    if not isinstance(document, dict):
        return default_compile_state()
    dirty_source_ids = document.get("dirty_source_ids", [])
    clean_source_ids = document.get("clean_source_ids", [])
    dirty_concept_source_ids = document.get("dirty_concept_source_ids", [])
    clean_concept_source_ids = document.get("clean_concept_source_ids", [])
    dirty_concept_slugs = document.get("dirty_concept_slugs", [])
    clean_concept_slugs = document.get("clean_concept_slugs", [])
    dirty_index_artifacts = document.get("dirty_index_artifacts", [])
    clean_index_artifacts = document.get("clean_index_artifacts", [])
    dirty_maintenance_artifacts = document.get("dirty_maintenance_artifacts", [])
    clean_maintenance_artifacts = document.get("clean_maintenance_artifacts", [])
    phase_summary = document.get("phase_summary")
    if (
        not isinstance(dirty_source_ids, list)
        or not isinstance(clean_source_ids, list)
        or not isinstance(dirty_concept_source_ids, list)
        or not isinstance(clean_concept_source_ids, list)
        or not isinstance(dirty_concept_slugs, list)
        or not isinstance(clean_concept_slugs, list)
        or not isinstance(dirty_index_artifacts, list)
        or not isinstance(clean_index_artifacts, list)
        or not isinstance(dirty_maintenance_artifacts, list)
        or not isinstance(clean_maintenance_artifacts, list)
        or not isinstance(phase_summary, list)
    ):
        return default_compile_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "compiled_at": str(document.get("compiled_at") or ""),
        "manifest_entry_count": int(document.get("manifest_entry_count", 0) or 0),
        "dirty_source_ids": [str(entry_id) for entry_id in dirty_source_ids if str(entry_id)],
        "clean_source_ids": [str(entry_id) for entry_id in clean_source_ids if str(entry_id)],
        "dirty_concept_source_ids": [str(entry_id) for entry_id in dirty_concept_source_ids if str(entry_id)],
        "clean_concept_source_ids": [str(entry_id) for entry_id in clean_concept_source_ids if str(entry_id)],
        "dirty_concept_slugs": [str(slug) for slug in dirty_concept_slugs if str(slug)],
        "clean_concept_slugs": [str(slug) for slug in clean_concept_slugs if str(slug)],
        "dirty_index_artifacts": [str(path) for path in dirty_index_artifacts if str(path)],
        "clean_index_artifacts": [str(path) for path in clean_index_artifacts if str(path)],
        "dirty_maintenance_artifacts": [str(path) for path in dirty_maintenance_artifacts if str(path)],
        "clean_maintenance_artifacts": [str(path) for path in clean_maintenance_artifacts if str(path)],
        "phase_summary": [phase for phase in phase_summary if isinstance(phase, dict)],
    }


def save_compile_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(compile_state_path(root), document)


def default_concept_build_state() -> dict[str, Any]:
    return {"version": 2, "generated_at": "", "entry_records": {}}


def load_concept_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_build_state_path(root))
    if not isinstance(document, dict):
        return default_concept_build_state()
    version = int(document.get("version", 1) or 1)
    if version < 2:
        return default_concept_build_state()
    entry_records = document.get("entry_records")
    if not isinstance(entry_records, dict):
        return default_concept_build_state()
    normalized_records: dict[str, dict[str, Any]] = {}
    for entry_id, record in entry_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        terms = record.get("terms", [])
        if not isinstance(terms, list):
            continue
        normalized_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
            "terms": [str(label) for label in terms if str(label)],
        }
    return {
        "version": version,
        "generated_at": str(document.get("generated_at") or ""),
        "entry_records": normalized_records,
    }


def save_concept_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(concept_build_state_path(root), document)


def manifest_change_summary(previous_entries: list[dict[str, Any]], current_entries: list[dict[str, Any]]) -> dict[str, int]:
    previous_by_path = {
        str(entry.get("stored_path") or ""): entry
        for entry in previous_entries
        if isinstance(entry, dict) and str(entry.get("stored_path") or "")
    }
    current_by_path = {
        str(entry.get("stored_path") or ""): entry
        for entry in current_entries
        if isinstance(entry, dict) and str(entry.get("stored_path") or "")
    }
    previous_paths = set(previous_by_path)
    current_paths = set(current_by_path)
    added_paths = current_paths - previous_paths
    removed_paths = previous_paths - current_paths
    updated_paths = 0
    for stored_path in current_paths & previous_paths:
        previous = previous_by_path[stored_path]
        current = current_by_path[stored_path]
        if any(
            previous.get(field) != current.get(field)
            for field in ("sha256", "title", "kind", "source_type", "original_path")
        ):
            updated_paths += 1
    return {
        "manifest_entries": len(current_entries),
        "added_entries": len(added_paths),
        "updated_entries": updated_paths,
        "removed_entries": len(removed_paths),
        "changed_entries": len(added_paths) + updated_paths + len(removed_paths),
    }


def default_material_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_material_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_state_path(root))
    if not isinstance(document, dict):
        return default_material_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_state_path(root), document)


def default_active_corpora_state() -> dict[str, Any]:
    return {"version": 1, "corpora": []}


def load_active_corpora_state(root: Path) -> dict[str, Any]:
    document = load_json_document(active_corpora_state_path(root))
    if not isinstance(document, dict):
        return default_active_corpora_state()
    corpora = document.get("corpora")
    if not isinstance(corpora, list):
        return default_active_corpora_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "corpora": [corpus for corpus in corpora if isinstance(corpus, dict)],
    }


def save_active_corpora_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(active_corpora_state_path(root), document)


def load_runtime_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(runtime_history_path(root))


def append_runtime_history(root: Path, event: dict[str, Any]) -> None:
    path = runtime_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def summarize_runtime_event_for_shell(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    summary = {
        "event_type": event_type,
        "occurred_at": str(event.get("occurred_at") or ""),
        "protocol": str(event.get("protocol") or ""),
        "title": "",
    }
    if event_type == "query":
        summary["title"] = str(event.get("focus_ref") or "Query")
        summary["output_path"] = str(event.get("output_ref") or "")
        summary["corpus_id"] = str(event.get("corpus_id") or "")
        summary["output_format"] = str(event.get("output_format") or "")
    elif event_type == "review":
        summary["title"] = str(event.get("page_path") or "Review")
        summary["page_path"] = str(event.get("page_path") or "")
        summary["status"] = str(event.get("status") or "")
        summary["page_kind"] = str(event.get("page_kind") or "")
    elif event_type == "knowledge-lifecycle-override":
        summary["title"] = str(event.get("slug") or event.get("page_id") or "Lifecycle override")
        summary["operation"] = str(event.get("operation") or "")
        summary["path"] = str(event.get("path") or "")
        summary["lifecycle_state"] = str(event.get("lifecycle_state") or "")
    elif event_type in {"archive-apply", "archive-revert"}:
        entry_id = str(event.get("source_ids", ["archive"])[0] if event.get("source_ids") else "Archive")
        summary["title"] = entry_id
        summary["entry_id"] = entry_id
        summary["receipt_path"] = str(event.get("receipt_path") or "")
        summary["source_ids"] = [str(item) for item in event.get("source_ids", []) if item]
    elif event_type == "nightly":
        summary["title"] = "Nightly health"
        summary["active_corpus_ids"] = [str(item) for item in event.get("active_corpus_ids", []) if item]
        summary["cooled_corpus_ids"] = [str(item) for item in event.get("cooled_corpus_ids", []) if item]
        summary["expired_corpus_ids"] = [str(item) for item in event.get("expired_corpus_ids", []) if item]
    else:
        summary["title"] = event_type or "runtime-event"
    return summary


def shell_recent_runs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    history = load_runtime_history(root)
    return [summarize_runtime_event_for_shell(event) for event in list(reversed(history))[:limit]]


def shell_recent_receipts(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    receipts = load_execution_receipt_history(root)
    return [
        {
            "action_id": str(receipt.get("action_id") or ""),
            "applied_at": str(receipt.get("applied_at") or ""),
            "operation": str(receipt.get("operation") or ""),
            "protocol": str(receipt.get("protocol") or ""),
            "receipt_path": str(receipt.get("receipt_path") or ""),
            "status": str(receipt.get("status") or ""),
            "subject_id": str(receipt.get("subject_id") or ""),
            "subject_kind": str(receipt.get("subject_kind") or ""),
            "title": str(receipt.get("title") or ""),
        }
        for receipt in receipts[:limit]
    ]


def shell_review_controls(
    root: Path,
    *,
    queue: dict[str, list[dict[str, str]]],
    aging: dict[str, list[dict[str, str]]],
) -> dict[str, list[dict[str, Any]]]:
    page_by_path: dict[str, dict[str, Any]] = {}

    def add_page(page: dict[str, str], reason_code: str) -> None:
        page_path = str(page.get("path") or "")
        if not page_path:
            return
        current = page_by_path.get(page_path)
        if current is None:
            current = {
                "page_id": str(page.get("page_id") or Path(page_path).stem),
                "title": str(page.get("title") or page_path),
                "path": page_path,
                "kind": str(page.get("kind") or ""),
                "status": str(page.get("status") or ""),
                "current_status": str(page.get("status") or ""),
                "protocol": str(page.get("protocol") or ""),
                "confidence": str(page.get("confidence") or ""),
                "pending_review": str(page.get("pending_review") or "") == "true",
                "overdue_review": str(page.get("overdue_review") or "") == "true",
                "escalation_candidate": str(page.get("escalation_candidate") or "") == "true",
                "aging_state": str(page.get("aging_state") or ""),
                "revisit_after": str(page.get("revisit_after") or ""),
                "escalate_after": str(page.get("escalate_after") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
                "updated_at": str(page.get("updated_at") or ""),
                "can_review": False,
                "can_refresh_review": False,
                "reasons": [],
            }
            page_by_path[page_path] = current
        reasons = current.setdefault("reasons", [])
        if reason_code and reason_code not in reasons:
            reasons.append(reason_code)
        profile = curated_page_transition_profile(
            str(current.get("kind") or ""),
            str(current.get("status") or ""),
        )
        current.update(profile)
        current["can_review"] = bool(profile.get("allowed_transitions"))
        current["can_refresh_review"] = bool(valid_curated_statuses(str(current.get("kind") or "")))

    for page in queue.get("pending_decisions", []) + queue.get("pending_judgments", []):
        add_page(page, "pending-review")
    for page in aging.get("escalated", []):
        add_page(page, "escalation-candidate")
    for page in aging.get("overdue", []):
        add_page(page, "overdue-review")
    for page in aging.get("scheduled", []):
        add_page(page, "scheduled-review")

    review_pages = sorted(
        page_by_path.values(),
        key=lambda item: (
            0 if item.get("escalation_candidate") else 1,
            0 if item.get("overdue_review") else 1,
            0 if item.get("pending_review") else 1,
            str(item.get("revisit_after") or "9999"),
            str(item.get("title") or "").lower(),
        ),
    )

    rewrite_state = load_concept_rewrite_state(root)
    rewrite_controls: list[dict[str, Any]] = []
    for proposal in rewrite_state.get("proposals", []):
        if not isinstance(proposal, dict):
            continue
        slug = str(proposal.get("slug") or "").strip()
        if not slug or not bool(proposal.get("active", True)):
            continue
        status = str(proposal.get("status") or "proposed")
        profile = rewrite_transition_profile(status)
        rewrite_controls.append(
            {
                "slug": slug,
                "title": str(proposal.get("title") or slug),
                "status": status,
                "current_status": status,
                "priority": str(proposal.get("priority") or "medium"),
                "score": int(proposal.get("score") or 0),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "target_path": str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"),
                "pending_review": str(proposal.get("pending_review") or "") == "true",
                "apply_ready": bool(proposal.get("apply_ready", False)),
                "can_review": bool(profile.get("allowed_transitions")),
                "can_refresh_review": status in REWRITE_PROPOSAL_STATUSES,
                "can_apply": bool(proposal.get("apply_ready", False)),
                "first_proposed_at": str(proposal.get("first_proposed_at") or ""),
                "last_proposed_at": str(proposal.get("last_proposed_at") or ""),
                "reviewed_at": str(proposal.get("reviewed_at") or ""),
                "issue_count": len(proposal.get("issues", [])) if isinstance(proposal.get("issues"), list) else 0,
                "source_count": len(proposal.get("source_pages", [])) if isinstance(proposal.get("source_pages"), list) else 0,
                **profile,
            }
        )
    rewrite_controls.sort(
        key=lambda item: (
            0 if item.get("can_review") else 1,
            0 if item.get("apply_ready") else 1,
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            -int(item.get("score", 0)),
            str(item.get("title") or "").lower(),
        )
    )
    return {
        "pages": review_pages,
        "rewrite_proposals": rewrite_controls,
    }


def shell_action_control_objects(
    root: Path,
    memory: dict[str, Any],
    *,
    apply_ready_action_ids: set[str],
    revert_ready_action_ids: set[str],
) -> list[dict[str, Any]]:
    health = memory.get("health", {})
    repair_plan = health.get("repair_plan", {})
    all_actions = [
        action
        for action in [
            *health.get("actions", []),
            *health.get("inactive_actions", []),
            *repair_plan.get("ready_actions", []),
            *repair_plan.get("triage_actions", []),
            *repair_plan.get("deferred_actions", []),
        ]
        if isinstance(action, dict)
    ]
    controls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for action in all_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in seen_ids:
            continue
        seen_ids.add(action_id)
        status = str(action.get("status") or "proposed")
        profile = action_transition_profile(status) if bool(action.get("active", True)) else transition_profile([])
        can_review = bool(profile.get("allowed_transitions"))
        can_apply = action_id in apply_ready_action_ids
        can_revert = action_id in revert_ready_action_ids
        proposal_path = execution_proposal_path(root, action_id)
        bundle_path = execution_bundle_path(root, action_id)
        controls.append(
            {
                "action_id": action_id,
                "title": str(action.get("title") or action_id),
                "status": status,
                "current_status": status,
                "kind": str(action.get("kind") or ""),
                "priority": str(action.get("priority") or "medium"),
                "protocol": str(action.get("protocol") or DEFAULT_PROTOCOL),
                "primary_path": str(action.get("primary_path") or ""),
                "secondary_path": str(action.get("secondary_path") or ""),
                "component_id": str(action.get("component_id") or ""),
                "execution_policy": str(action.get("execution_policy") or ""),
                "execution_band": str(action.get("execution_band") or ""),
                "policy_summary": str(action.get("policy_summary") or ""),
                "pending_review": str(action.get("pending_review") or "") == "true",
                "overdue_review": str(action.get("overdue_review") or "") == "true",
                "escalation_candidate": str(action.get("escalation_candidate") or "") == "true",
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "proposal_path": relative_path(root, proposal_path) if proposal_path.exists() else "",
                "bundle_path": relative_path(root, bundle_path) if bundle_path.exists() else "",
                "can_review": can_review,
                "can_refresh_review": bool(action.get("active", True)) and status in ACTION_STATUSES,
                "can_apply": can_apply,
                "can_revert": can_revert,
                **profile,
            }
        )
    controls.sort(
        key=lambda item: (
            0 if item.get("can_apply") else 1,
            0 if item.get("can_review") else 1,
            0 if item.get("can_revert") else 1,
            0 if item.get("escalation_candidate") else 1,
            0 if item.get("overdue_review") else 1,
            action_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )
    return controls


def shell_archive_control_objects(
    root: Path,
    *,
    apply_ready_archive_entry_ids: set[str],
    revert_ready_archive_entry_ids: set[str],
) -> list[dict[str, Any]]:
    manifest = load_manifest(root)
    manifest_by_id = {
        str(entry.get("id") or ""): entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("id")
    }
    archive_candidates = load_archive_candidates_state(root)
    archive_candidate_by_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    active_archives = active_material_archive_entries(load_material_archive_state(root))
    entry_ids = sorted(
        {
            *archive_candidate_by_id.keys(),
            *active_archives.keys(),
            *apply_ready_archive_entry_ids,
            *revert_ready_archive_entry_ids,
        }
    )
    controls: list[dict[str, Any]] = []
    for entry_id in entry_ids:
        candidate = archive_candidate_by_id.get(entry_id, {})
        archived = active_archives.get(entry_id, {})
        manifest_entry = manifest_by_id.get(entry_id, {})
        title = str(manifest_entry.get("title") or archived.get("title") or entry_id)
        source_path = str(archived.get("source_path") or f"wiki/sources/{entry_id}.md")
        can_apply = entry_id in apply_ready_archive_entry_ids
        can_revert = entry_id in revert_ready_archive_entry_ids
        profile = archive_transition_profile(can_apply=can_apply, can_revert=can_revert)
        controls.append(
            {
                "entry_id": entry_id,
                "title": title,
                "source_path": source_path,
                "candidate_status": str(candidate.get("status") or ""),
                "current_temperature": str(candidate.get("current_temperature") or ("archived" if archived else "")),
                "recommended_temperature": str(candidate.get("recommended_temperature") or archived.get("recommended_temperature") or ""),
                "reason_codes": list(candidate.get("reason_codes", [])) if isinstance(candidate.get("reason_codes"), list) else [],
                "blocked_by_judgment_ids": list(candidate.get("blocked_by_judgment_ids", []))
                if isinstance(candidate.get("blocked_by_judgment_ids"), list)
                else [],
                "reactivation_signals": list(candidate.get("reactivation_signals", []))
                if isinstance(candidate.get("reactivation_signals"), list)
                else [],
                "archived": bool(archived.get("active", False)),
                "archived_at": str(archived.get("archived_at") or ""),
                "last_receipt_path": str(archived.get("last_receipt_path") or ""),
                "can_apply": can_apply,
                "can_revert": can_revert,
                **profile,
            }
        )
    controls.sort(
        key=lambda item: (
            0 if item.get("can_apply") else 1,
            0 if item.get("can_revert") else 1,
            0 if item.get("archived") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    return controls


def shell_execution_controls(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action
        for action in repair_plan.get("ready_actions", [])
        if isinstance(action, dict)
    ]
    apply_ready_action_ids = [
        str(action.get("id") or "")
        for action in ready_actions
        if action_supports_low_risk_apply(action) and action.get("id")
    ]
    all_actions = [
        action
        for action in [
            *memory.get("health", {}).get("actions", []),
            *memory.get("health", {}).get("inactive_actions", []),
        ]
        if isinstance(action, dict)
    ]
    revert_ready_action_ids = [
        str(action.get("id") or "")
        for action in all_actions
        if action.get("id")
        and action.get("last_receipt_path")
        and str(action.get("status") or "") == "resolved"
    ]
    archive_candidates = load_archive_candidates_state(root)
    apply_ready_archive_entry_ids = [
        str(entry.get("entry_id") or "")
        for entry in archive_candidates.get("entries", [])
        if (
            isinstance(entry, dict)
            and entry.get("entry_id")
            and str(entry.get("status") or "") == "ready"
            and str(entry.get("recommended_temperature") or "") == "archived"
        )
    ]
    revert_ready_archive_entry_ids = sorted(active_material_archive_entries(load_material_archive_state(root)).keys())
    apply_ready_action_id_set = {item for item in apply_ready_action_ids if item}
    revert_ready_action_id_set = {item for item in revert_ready_action_ids if item}
    apply_ready_archive_entry_id_set = {item for item in apply_ready_archive_entry_ids if item}
    revert_ready_archive_entry_id_set = set(revert_ready_archive_entry_ids)
    return {
        "apply_ready_action_ids": sorted(apply_ready_action_id_set),
        "revert_ready_action_ids": sorted(revert_ready_action_id_set),
        "apply_ready_archive_entry_ids": sorted(apply_ready_archive_entry_id_set),
        "revert_ready_archive_entry_ids": revert_ready_archive_entry_ids,
        "actions": shell_action_control_objects(
            root,
            memory,
            apply_ready_action_ids=apply_ready_action_id_set,
            revert_ready_action_ids=revert_ready_action_id_set,
        ),
        "archives": shell_archive_control_objects(
            root,
            apply_ready_archive_entry_ids=apply_ready_archive_entry_id_set,
            revert_ready_archive_entry_ids=revert_ready_archive_entry_id_set,
        ),
    }


def shell_links(root: Path) -> dict[str, str]:
    return {
        "summary_path": relative_path(root, shell_summary_path(root)),
        "furnace_center_markdown": "wiki/indexes/furnace-center.md",
        "review_center_markdown": "wiki/indexes/review-center.md",
        "execution_center_markdown": "wiki/indexes/execution-center.md",
        "execution_audit_markdown": "wiki/indexes/execution-audit.md",
        "graph_view_markdown": "wiki/indexes/graph-view.md",
        "protocols_markdown": "wiki/indexes/protocols.md",
        "domain_pilots_markdown": "wiki/indexes/domain-pilots.md",
        "output_packs_markdown": "wiki/indexes/output-packs.md",
        "agent_workbench_markdown": "wiki/indexes/agent-workbench.md",
        "furnace_center_html": relative_path(root, furnace_center_html_path(root)),
        "review_center_html": relative_path(root, review_center_html_path(root)),
        "execution_center_html": relative_path(root, execution_center_html_path(root)),
        "execution_audit_html": relative_path(root, execution_audit_html_path(root)),
        "graph_html": relative_path(root, machine_memory_graph_html_path(root)),
        "product_shell_design": "wiki/indexes/Furnace Product Shell Plugin.md",
        "product_shell_runtime_plan": "wiki/indexes/Furnace Product Shell Runtime Plan.md",
    }


def shell_capabilities(root: Path) -> dict[str, Any]:
    return {
        "launcher_mode": "repo-local",
        "supports_hidden_state_read": False,
        "commands": {
            "p0": [
                "shell-status",
                "compile",
                "ask",
                "run-ask",
                "nightly",
                "protocol-status",
                "protocol-set",
                "llm-check",
            ],
            "p1": [
                "run-compile",
                "run-nightly",
                "file-back",
                "review-page",
                "review-rewrite",
                "apply-rewrite",
                "retire-concept",
                "reactivate-concept",
                "apply-archive",
                "revert-archive",
            ],
            "p2": ["review-action", "apply-action", "revert-action", "watch", "auto-once"],
        },
        "views": {
            "furnace_center_markdown": (root / "wiki" / "indexes" / "furnace-center.md").exists(),
            "review_center_markdown": (root / "wiki" / "indexes" / "review-center.md").exists(),
            "execution_center_markdown": execution_center_path(root).exists(),
            "execution_audit_markdown": execution_audit_path(root).exists(),
            "domain_pilots_markdown": domain_pilots_path(root).exists(),
            "output_packs_markdown": output_packs_index_path(root).exists(),
            "agent_workbench_markdown": agent_workbench_path(root).exists(),
            "furnace_center_html": furnace_center_html_path(root).exists(),
            "review_center_html": review_center_html_path(root).exists(),
            "execution_center_html": execution_center_html_path(root).exists(),
            "execution_audit_html": execution_audit_html_path(root).exists(),
            "graph_html": machine_memory_graph_html_path(root).exists(),
        },
    }


def shell_protocol_state(root: Path) -> dict[str, Any]:
    state = load_json_document(protocol_state_path(root))
    available = sorted(PROTOCOL_LIBRARY)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active not in available:
        active = DEFAULT_PROTOCOL if DEFAULT_PROTOCOL in available else (available[0] if available else DEFAULT_PROTOCOL)
    return {
        "active_protocol": active,
        "available_protocols": available,
        "state_path": relative_path(root, protocol_state_path(root)),
    }


def build_shell_summary(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    generated_at = generated_at or utc_now()
    protocol_state = shell_protocol_state(root)
    llm_status = LLMConfig.status_from_env()
    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    knowledge_lifecycle = load_knowledge_lifecycle_state(root)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=protocol_state["active_protocol"],
    )
    memory = load_machine_memory(root)
    nightly_state = load_json_document(nightly_health_state_path(root))
    review_backlog_counts = {
        "pending_decisions": len(queue["pending_decisions"]),
        "pending_judgments": len(queue["pending_judgments"]),
        "overdue_reviews": len(aging["overdue"]),
        "escalation_candidates": len(aging["escalated"]),
        "concept_backlog": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
        "review_concepts": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
        "revisit_concepts": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
        "retired_concepts": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
        "machine_memory_actions": memory.get("health", {}).get("action_counts", {}).get("total", 0),
        "ready_actions": memory.get("health", {}).get("repair_plan", {}).get("counts", {}).get("ready", 0),
        "overdue_actions": len(memory.get("health", {}).get("overdue_actions", [])),
        "escalated_actions": len(memory.get("health", {}).get("escalated_actions", [])),
    }
    review_controls = shell_review_controls(root, queue=queue, aging=aging)
    return {
        "kind": "product-shell-summary",
        "contract_version": 1,
        "generated_at": generated_at,
        "generated_by": "aiwiki-shell-status",
        "summary_path": relative_path(root, shell_summary_path(root)),
        "active_protocol": protocol_state["active_protocol"],
        "available_protocols": list(protocol_state.get("available_protocols", [])),
        "llm_status": {
            "configured": bool(llm_status.get("configured")),
            "backend": str(llm_status.get("backend") or ""),
            "backend_requested": str(llm_status.get("backend_requested") or ""),
            "model": str(llm_status.get("model") or ""),
            "available_backends": list(llm_status.get("available_backends", [])),
            "image_analysis_supported": bool(llm_status.get("image_analysis_supported")),
            "message": str(llm_status.get("message") or ""),
        },
        "review_backlog_counts": review_backlog_counts,
        "aging_summary": {
            "overdue_count": len(aging["overdue"]),
            "escalated_count": len(aging["escalated"]),
            "scheduled_count": len(aging["scheduled"]),
            "overdue_pages": [page["path"] for page in aging["overdue"][:8]],
            "escalated_pages": [page["path"] for page in aging["escalated"][:8]],
            "scheduled_pages": [page["path"] for page in aging["scheduled"][:8]],
        },
        "review_controls": review_controls,
        "execution_controls": shell_execution_controls(root, memory),
        "recent_outputs": collect_recent_output_artifacts(root, limit=8),
        "recent_receipts": shell_recent_receipts(root, limit=8),
        "recent_runs": shell_recent_runs(root, limit=8),
        "nightly": {
            "available": nightly_health_state_path(root).exists(),
            "generated_at": str(nightly_state.get("generated_at") or ""),
            "state_path": relative_path(root, nightly_health_state_path(root)),
            "llm_used": bool(nightly_state.get("llm_used", False)),
            "lint_counts": dict(nightly_state.get("lint", {}).get("counts", {})),
        },
        "links": shell_links(root),
        "capabilities": shell_capabilities(root),
    }


def write_shell_summary(root: Path, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or build_shell_summary(root)
    write_if_changed(shell_summary_path(root), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def default_material_routing_state() -> dict[str, Any]:
    return {"version": 1, "computed_at": "", "active_protocol": DEFAULT_PROTOCOL, "entries": []}


def load_material_routing_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_routing_state_path(root))
    if not isinstance(document, dict):
        return default_material_routing_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_routing_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "computed_at": str(document.get("computed_at") or ""),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_routing_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_routing_state_path(root), document)


def default_archive_candidates_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_archive_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(archive_candidates_state_path(root))
    if not isinstance(document, dict):
        return default_archive_candidates_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_archive_candidates_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_archive_candidates_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(archive_candidates_state_path(root), document)


def default_knowledge_lifecycle_state() -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    return {
        "version": 1,
        "generated_at": "",
        "entries": [],
        "counts": {
            "total": 0,
            "by_state": dict(by_state),
            "by_kind": {kind: {"total": 0, "by_state": dict(by_state)} for kind in KNOWLEDGE_LIFECYCLE_KINDS},
            "invalidated": 0,
            "active_corpus_linked": 0,
        },
    }


def load_knowledge_lifecycle_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_state_path(root))
    if not isinstance(document, dict):
        return default_knowledge_lifecycle_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_knowledge_lifecycle_state()
    counts = document.get("counts")
    if not isinstance(counts, dict):
        counts = default_knowledge_lifecycle_state()["counts"]
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
        "counts": counts,
    }


def save_knowledge_lifecycle_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_state_path(root), document)


def default_knowledge_lifecycle_override_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_override_state_path(root))
    if not isinstance(document, dict):
        return default_knowledge_lifecycle_override_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_knowledge_lifecycle_override_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_knowledge_lifecycle_override_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_override_state_path(root), document)


def ensure_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    state = load_knowledge_lifecycle_override_state(root)
    path = knowledge_lifecycle_override_state_path(root)
    if not path.exists():
        save_knowledge_lifecycle_override_state(root, state)
    return state


def active_knowledge_lifecycle_overrides(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("path") or ""): entry
        for entry in document.get("entries", [])
        if isinstance(entry, dict) and bool(entry.get("active")) and str(entry.get("path") or "")
    }


def default_material_archive_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_material_archive_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_archive_state_path(root))
    if not isinstance(document, dict):
        return default_material_archive_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_archive_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_archive_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_archive_state_path(root), document)


def active_material_archive_entries(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id") or ""): entry
        for entry in document.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id") and bool(entry.get("active", False))
    }


def active_archived_material_ids(root: Path) -> set[str]:
    return set(active_material_archive_entries(load_material_archive_state(root)))


def material_archive_action_id(entry_id: str) -> str:
    return f"archive-{entry_id}"


def concept_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "concepts" / f"{slug}.md"


def concept_lifecycle_entry(lifecycle_state: dict[str, Any], slug: str) -> dict[str, Any]:
    target_path = f"wiki/concepts/{slug}.md"
    return next(
        (
            dict(entry)
            for entry in lifecycle_state.get("entries", [])
            if isinstance(entry, dict)
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == target_path
        ),
        {},
    )


def routing_snapshot_for_protocol(routing_entry: dict[str, Any], protocol: str) -> dict[str, Any]:
    if not isinstance(routing_entry, dict):
        return {}
    if str(routing_entry.get("protocol") or "") == protocol:
        return routing_entry
    for snapshot in routing_entry.get("protocol_snapshots", []):
        if isinstance(snapshot, dict) and str(snapshot.get("protocol") or "") == protocol:
            return snapshot
    return {}


def question_signature(question: str) -> str:
    normalized = " ".join(question.lower().split())
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"


def timestamp_is_newer(candidate: str, current: str) -> bool:
    candidate_dt = parse_iso_datetime(candidate)
    current_dt = parse_iso_datetime(current)
    if candidate_dt is None:
        return False
    if current_dt is None:
        return True
    return candidate_dt > current_dt


def update_latest_timestamp(mapping: dict[str, str], key: str, timestamp: str) -> None:
    if not key or not timestamp:
        return
    if timestamp_is_newer(timestamp, mapping.get(key, "")):
        mapping[key] = timestamp


def protocol_hints_for_material(entry: dict[str, Any], preview: str) -> list[str]:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    scored: list[tuple[int, str]] = []
    for protocol in sorted(PROTOCOL_LIBRARY):
        if protocol == DEFAULT_PROTOCOL:
            continue
        score = protocol_focus_score(protocol, text)
        if score > 0:
            scored.append((score, protocol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    hints = [protocol for _score, protocol in scored[:2]]
    return hints or [DEFAULT_PROTOCOL]


def recency_score_for_timestamp(timestamp: str) -> float:
    parsed = parse_iso_datetime(timestamp)
    if parsed is None:
        return 0.0
    now = datetime.now(timezone.utc)
    age = now - parsed
    if age <= timedelta(days=3):
        return 1.0
    if age <= timedelta(days=7):
        return 0.7
    if age <= timedelta(days=30):
        return 0.4
    return 0.1


QUERY_TIME_FOCUS_MARKERS: dict[str, tuple[str, ...]] = {
    "recent": ("latest", "recent", "current", "new", "newest", "updated", "today", "fresh"),
    "historical": ("history", "historical", "legacy", "old", "older", "previous", "prior", "archive", "archived"),
}


def machine_memory_query_time_focus(question: str) -> dict[str, Any]:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", question.lower()))
    recent_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["recent"] if marker in normalized]
    historical_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["historical"] if marker in normalized]
    if historical_hits and len(historical_hits) >= len(recent_hits):
        return {"focus": "historical", "markers": historical_hits[:4]}
    if recent_hits:
        return {"focus": "recent", "markers": recent_hits[:4]}
    return {"focus": "", "markers": []}


def machine_memory_source_runtime_record(
    source_id: str,
    *,
    base_score: float,
    source_nodes: dict[str, dict[str, Any]],
    material_by_entry: dict[str, dict[str, Any]],
    routing_by_entry: dict[str, dict[str, Any]],
    archive_candidates_by_entry: dict[str, dict[str, Any]],
    protocol: str,
    time_focus: str,
) -> dict[str, Any]:
    material_entry = material_by_entry.get(source_id, {})
    routing_entry = routing_by_entry.get(source_id, {})
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    archive_candidate = archive_candidates_by_entry.get(source_id, {})
    temperature = str(material_entry.get("temperature") or "")

    protocol_bonus = 0.0
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    protocol_is_top = top_protocols[:1] == [protocol]
    protocol_in_top2 = protocol in top_protocols[:2]
    selected_as = str(routing_snapshot.get("selected_as") or "")
    selected_bonus = 0.0
    if selected_as == "hot-evidence":
        selected_bonus = 0.9
    elif selected_as == "warm-evidence":
        selected_bonus = 0.6
    elif selected_as == "cold-evidence":
        selected_bonus = 0.3
    total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
    if protocol_is_top:
        protocol_bonus += 2.5 + selected_bonus + min(1.0, total_score * 0.25)
    elif protocol_in_top2:
        protocol_bonus += 1.2 + min(0.25, selected_bonus * 0.4) + min(0.4, total_score * 0.1)

    activity_score = max(
        recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_query_hit_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_review_reference_at") or "")),
    )
    time_bonus = 0.0
    if time_focus == "recent":
        time_bonus += activity_score * 4.0
        if temperature == "hot":
            time_bonus += 0.4
        elif temperature == "warm":
            time_bonus += 0.2
        elif temperature == "cold":
            time_bonus -= 0.35
        elif temperature == "archived":
            time_bonus -= 1.0
    elif time_focus == "historical":
        time_bonus += (1.0 - activity_score) * 4.0
        if temperature == "cold":
            time_bonus += 0.8
        elif temperature == "archived":
            time_bonus += 1.4
        elif temperature == "hot":
            time_bonus -= 0.25
        if archive_candidate:
            time_bonus += 0.6

    protocol_shard = protocol_is_top or (protocol_in_top2 and selected_as in {"hot-evidence", "warm-evidence"})
    time_shard = bool(time_focus) and time_bonus > 1.0
    archive_status = "archived" if temperature == "archived" else str(archive_candidate.get("status") or "")
    archive_hint = bool(
        temperature == "archived"
        or (time_focus == "historical" and (temperature == "cold" or bool(archive_candidate)))
        or (
            archive_candidate
            and str(archive_candidate.get("recommended_temperature") or "") == "archived"
        )
    )
    archive_hint_score = base_score + protocol_bonus + max(0.0, time_bonus)
    if temperature == "archived":
        archive_hint_score += 1.0
    elif archive_candidate:
        archive_hint_score += 0.6
    elif temperature == "cold":
        archive_hint_score += 0.3

    return {
        "entry_id": source_id,
        "title": str(source_nodes.get(source_id, {}).get("title") or source_id),
        "path": str(source_nodes.get(source_id, {}).get("source_page") or f"wiki/sources/{source_id}.md"),
        "base_score": float(base_score),
        "protocol_bonus": round(protocol_bonus, 3),
        "time_bonus": round(time_bonus, 3),
        "combined_score": round(float(base_score) + protocol_bonus + time_bonus, 3),
        "protocol_shard": protocol_shard,
        "time_shard": time_shard,
        "temperature": temperature,
        "archive_status": archive_status,
        "archive_hint": archive_hint,
        "archive_hint_score": round(archive_hint_score, 3),
        "recommended_temperature": str(archive_candidate.get("recommended_temperature") or ""),
        "reason_codes": [
            str(reason)
            for reason in archive_candidate.get("reason_codes", [])
            if isinstance(reason, str) and reason
        ],
    }


def material_protocol_score(
    active_protocol: str,
    *,
    protocol_hints: list[str],
    entry: dict[str, Any],
    preview: str,
) -> float:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    focus_score = protocol_focus_score(active_protocol, text)
    non_default_hints = [hint for hint in protocol_hints if hint and hint != DEFAULT_PROTOCOL]
    if active_protocol == DEFAULT_PROTOCOL:
        base = 0.4 if not non_default_hints else 0.25
    elif active_protocol in protocol_hints:
        base = 0.75
    else:
        base = 0.2
    return round(min(1.0, base + min(0.25, focus_score * 0.05)), 3)


def material_graph_context(memory: dict[str, Any]) -> dict[str, Any]:
    health = memory.get("health", {})
    bridge_concepts = set(health.get("bridge_concept_slugs", []))
    concept_count_by_entry: dict[str, int] = {}
    bridge_source_ids: set[str] = set()
    source_component_ids = {
        str(source_id): str(component_id)
        for source_id, component_id in health.get("source_component_ids", {}).items()
        if isinstance(source_id, str) and isinstance(component_id, str)
    }
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = str(edge.get("source_id") or "")
        concept_slug = str(edge.get("concept_slug") or "")
        if not source_id or not concept_slug:
            continue
        concept_count_by_entry[source_id] = concept_count_by_entry.get(source_id, 0) + 1
        if concept_slug in bridge_concepts:
            bridge_source_ids.add(source_id)
    action_pressure_by_entry: dict[str, float] = {}
    for action in health.get("actions", []):
        if not isinstance(action, dict):
            continue
        weight = 0.2
        if str(action.get("priority") or "") == "high":
            weight += 0.15
        if str(action.get("status") or "") in {"accepted", "proposed"}:
            weight += 0.1
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + weight
    for action in health.get("overdue_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.2
    for action in health.get("escalated_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.25
    return {
        "concept_count_by_entry": concept_count_by_entry,
        "bridge_source_ids": bridge_source_ids,
        "action_pressure_by_entry": action_pressure_by_entry,
        "sources_without_concepts": set(memory.get("drift", {}).get("sources_without_concepts", [])),
        "source_component_ids": source_component_ids,
    }


def material_routing_selected_as(total_score: float, *, active_corpus_ids: list[str]) -> str:
    if active_corpus_ids or total_score >= 3.2:
        return "hot-evidence"
    if total_score >= 2.2:
        return "warm-evidence"
    if total_score >= 1.2:
        return "cold-evidence"
    return "archive-candidate"


def temperature_from_routing(selected_as: str, *, supports_judgment_ids: list[str]) -> str:
    if selected_as == "hot-evidence":
        return "hot"
    if selected_as == "warm-evidence":
        return "warm"
    if supports_judgment_ids:
        return "warm"
    return "cold"


def entry_lookup_maps(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id: dict[str, dict[str, Any]] = {}
    path_to_entry_id: dict[str, str] = {}
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        by_id[entry_id] = entry
        stored_path = normalize_workspace_path(str(entry.get("stored_path") or ""))
        if stored_path:
            path_to_entry_id[stored_path] = entry_id
        source_path = f"wiki/sources/{entry_id}.md"
        path_to_entry_id[source_path] = entry_id
    return by_id, path_to_entry_id


def entry_ids_from_paths(path_to_entry_id: dict[str, str], paths: list[str]) -> list[str]:
    entry_ids: list[str] = []
    seen: set[str] = set()
    for candidate in paths:
        normalized = normalize_workspace_path(candidate)
        entry_id = path_to_entry_id.get(normalized, "")
        if not entry_id and normalized.startswith("wiki/sources/") and normalized.endswith(".md"):
            entry_id = Path(normalized).stem
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        entry_ids.append(entry_id)
    return entry_ids


def source_ids_for_citations(root: Path, entries: list[dict[str, Any]], markdown: str) -> list[str]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    return entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, markdown))


def scan_material_reference_state(
    root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    citation_count_by_entry: dict[str, int] = {}
    supports_judgment_ids: dict[str, set[str]] = {}
    active_judgment_ids: set[str] = set()

    for relative in ("wiki/derived", "wiki/decisions", "wiki/judgments"):
        directory = root / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            cited_entry_ids = entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, content))
            for entry_id in cited_entry_ids:
                citation_count_by_entry[entry_id] = citation_count_by_entry.get(entry_id, 0) + 1
            if relative != "wiki/judgments":
                continue
            frontmatter = parse_frontmatter(content)
            judgment_id = str(frontmatter.get("id") or path.stem)
            if str(frontmatter.get("status") or "") != "rejected":
                active_judgment_ids.add(judgment_id)
            for entry_id in cited_entry_ids:
                supports_judgment_ids.setdefault(entry_id, set()).add(judgment_id)

    return {
        "citation_count_by_entry": citation_count_by_entry,
        "supports_judgment_ids": {entry_id: sorted(ids) for entry_id, ids in supports_judgment_ids.items()},
        "active_judgment_ids": sorted(active_judgment_ids),
    }


def build_material_routing_snapshot(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "")
    concept_count = int(graph_context.get("concept_count_by_entry", {}).get(entry_id, 0))
    is_bridge = entry_id in graph_context.get("bridge_source_ids", set())
    graph_score = 0.0
    graph_score += min(0.55, concept_count * 0.18)
    if active_corpus_ids:
        graph_score += 0.25
    if is_bridge:
        graph_score += 0.2
    graph_score = round(min(1.0, graph_score), 3)

    judgment_score = round(min(1.0, len(supports_judgment_ids) * 0.35), 3)
    recency_score = round(
        min(
            1.0,
            max(
                recency_score_for_timestamp(str(entry.get("updated_at") or entry.get("imported_at") or "")),
                recency_score_for_timestamp(last_query_hit_at),
                recency_score_for_timestamp(last_review_reference_at),
            ),
        ),
        3,
    )

    drift_score = 0.0
    if entry_id in graph_context.get("sources_without_concepts", set()):
        drift_score += 0.4
    drift_score += float(graph_context.get("action_pressure_by_entry", {}).get(entry_id, 0.0))
    drift_score = round(min(1.0, drift_score), 3)

    protocol_score = material_protocol_score(
        active_protocol,
        protocol_hints=protocol_hints,
        entry=entry,
        preview=preview,
    )
    total_score = round(protocol_score + graph_score + judgment_score + recency_score + drift_score, 3)
    selected_as = material_routing_selected_as(total_score, active_corpus_ids=active_corpus_ids)
    return {
        "entry_id": entry_id,
        "protocol": active_protocol,
        "component_id": str(graph_context.get("source_component_ids", {}).get(entry_id, "") or ""),
        "scores": {
            "protocol_score": protocol_score,
            "graph_score": graph_score,
            "judgment_score": judgment_score,
            "recency_score": recency_score,
            "drift_score": drift_score,
        },
        "total_score": total_score,
        "selected_as": selected_as,
        "is_bridge": is_bridge,
        "computed_at": computed_at,
    }


def material_top_protocols(protocol_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        [snapshot for snapshot in protocol_snapshots if isinstance(snapshot, dict)],
        key=lambda item: (-float(item.get("total_score", 0.0) or 0.0), str(item.get("protocol") or "")),
    )
    return [
        {
            "protocol": str(snapshot.get("protocol") or ""),
            "total_score": float(snapshot.get("total_score", 0.0) or 0.0),
            "selected_as": str(snapshot.get("selected_as") or ""),
        }
        for snapshot in ranked[:3]
    ]


def cross_protocol_bridge_entry(protocol_snapshots: list[dict[str, Any]], active_protocol: str) -> bool:
    for snapshot in protocol_snapshots:
        if not isinstance(snapshot, dict):
            continue
        if str(snapshot.get("protocol") or "") == active_protocol:
            continue
        if bool(snapshot.get("is_bridge")) and float(snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
            return True
    return False


def build_material_routing_entry(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    protocol_snapshots = [
        build_material_routing_snapshot(
            active_protocol=protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=last_query_hit_at,
            last_review_reference_at=last_review_reference_at,
            graph_context=graph_context,
            computed_at=computed_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    active_snapshot = next(
        (snapshot for snapshot in protocol_snapshots if str(snapshot.get("protocol") or "") == active_protocol),
        protocol_snapshots[0],
    )
    return {
        **active_snapshot,
        "protocol_snapshots": protocol_snapshots,
        "top_protocols": material_top_protocols(protocol_snapshots),
        "cross_protocol_bridge": cross_protocol_bridge_entry(protocol_snapshots, active_protocol),
    }


def archive_candidate_reactivation_signals(
    material_entry: dict[str, Any],
    routing_snapshot: dict[str, Any],
    previous_candidate: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[str]:
    signals: list[str] = []
    previous_flagged_at = str(previous_candidate.get("last_flagged_at") or "")
    if material_entry.get("active_corpus_ids"):
        signals.append("active-corpus")
    if str(material_entry.get("last_query_hit_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_query_hit_at") or ""),
        previous_flagged_at,
    ):
        signals.append("query-hit")
    if str(material_entry.get("last_review_reference_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_review_reference_at") or ""),
        previous_flagged_at,
    ):
        signals.append("review-reference")
    if bool(routing_snapshot.get("is_bridge")):
        signals.append("bridge-evidence")
    if float(routing_snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
        signals.append("routing-score-recovered")
    if bool(routing_snapshot.get("cross_protocol_bridge")):
        signals.append("cross-protocol-bridge")
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_snapshot.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if any(protocol != active_protocol for protocol in top_protocols[:2]):
        signals.append("cross-protocol-top-rank")
    return signals


def build_archive_candidate_state(
    *,
    material_entries: list[dict[str, Any]],
    routing_entries: list[dict[str, Any]],
    active_judgment_ids: set[str],
    generated_at: str,
    previous_state: dict[str, Any],
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in previous_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_entries
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    entries: list[dict[str, Any]] = []
    for material_entry in material_entries:
        entry_id = str(material_entry.get("entry_id") or "")
        if not entry_id:
            continue
        routing_snapshot = routing_by_entry.get(entry_id, {})
        previous_candidate = previous_by_entry.get(entry_id, {})
        blocked_by_judgment_ids = sorted(set(material_entry.get("supports_judgment_ids", [])) & active_judgment_ids)
        last_query_hit_at = parse_iso_datetime(str(material_entry.get("last_query_hit_at") or ""))
        query_stale = last_query_hit_at is None or (datetime.now(timezone.utc) - last_query_hit_at) > ARCHIVE_QUERY_STALE_AFTER
        touch_stale = recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")) <= 0.4
        total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
        is_bridge = bool(routing_snapshot.get("is_bridge"))
        cross_protocol_bridge = bool(routing_snapshot.get("cross_protocol_bridge"))
        no_active_corpus = not material_entry.get("active_corpus_ids")
        candidate = (
            no_active_corpus
            and query_stale
            and touch_stale
            and not is_bridge
            and not cross_protocol_bridge
            and str(material_entry.get("temperature") or "") in {"warm", "cold"}
            and str(routing_snapshot.get("selected_as") or "") in {"cold-evidence", "archive-candidate"}
        )
        if candidate:
            reason_codes: list[str] = []
            if no_active_corpus:
                reason_codes.append("no-active-corpus")
            if query_stale:
                reason_codes.append("stale-no-query-hit")
            if touch_stale:
                reason_codes.append("stale-no-touch")
            if total_score < 2.0:
                reason_codes.append("low-routing-score")
            if str(material_entry.get("temperature") or "") == "cold":
                reason_codes.append("already-cold")
            recommended_temperature = "archived" if str(material_entry.get("temperature") or "") == "cold" and total_score < 1.2 else "cold"
            status = "suggested"
            if blocked_by_judgment_ids:
                status = "deferred"
            # Deferred means the candidate already crossed the archive bar once.
            # When the blocking judgments clear, it should resume at ready.
            elif previous_candidate and str(previous_candidate.get("status") or "") in {"suggested", "ready", "deferred"}:
                status = "ready"
            entries.append(
                {
                    "entry_id": entry_id,
                    "current_temperature": str(material_entry.get("temperature") or ""),
                    "recommended_temperature": recommended_temperature,
                    "reason_codes": reason_codes,
                    "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                    "last_flagged_at": generated_at,
                    "blocked_by_judgment_ids": blocked_by_judgment_ids,
                    "reactivation_signals": list(previous_candidate.get("reactivation_signals", []))
                    if isinstance(previous_candidate.get("reactivation_signals"), list)
                    else [],
                    "status": status if status in ARCHIVE_CANDIDATE_STATUSES else "suggested",
                }
            )
            continue
        if previous_candidate:
            reactivation_signals = archive_candidate_reactivation_signals(
                material_entry,
                routing_snapshot,
                previous_candidate,
                active_protocol=active_protocol,
            )
            if reactivation_signals:
                entries.append(
                    {
                        "entry_id": entry_id,
                        "current_temperature": str(material_entry.get("temperature") or ""),
                        "recommended_temperature": str(previous_candidate.get("recommended_temperature") or "cold"),
                        "reason_codes": [],
                        "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                        "last_flagged_at": str(previous_candidate.get("last_flagged_at") or generated_at),
                        "blocked_by_judgment_ids": blocked_by_judgment_ids,
                        "reactivation_signals": reactivation_signals,
                        "status": "reactivated",
                    }
    )
    return {"version": 1, "generated_at": generated_at, "entries": entries}


def routing_bridge_recall_ids(
    machine_query: dict[str, Any],
    routing_state: dict[str, Any],
    *,
    active_protocol: str,
    excluded_source_ids: set[str],
) -> list[str]:
    touched_component_ids = {
        str(component_id)
        for component_id in machine_query.get("touched_component_ids", [])
        if isinstance(component_id, str) and component_id
    }
    candidates: list[tuple[float, str]] = []
    for entry in routing_state.get("entries", []):
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "")
        component_id = str(entry.get("component_id") or "")
        if not entry_id or entry_id in excluded_source_ids:
            continue
        if not touched_component_ids or component_id not in touched_component_ids:
            continue
        protocol_snapshots = [
            snapshot for snapshot in entry.get("protocol_snapshots", []) if isinstance(snapshot, dict)
        ]
        if not cross_protocol_bridge_entry(protocol_snapshots, active_protocol):
            continue
        non_active_scores = [
            float(snapshot.get("total_score", 0.0) or 0.0)
            for snapshot in protocol_snapshots
            if str(snapshot.get("protocol") or "") != active_protocol
        ]
        if not non_active_scores:
            continue
        best_score = max(non_active_scores)
        if best_score < 2.2:
            continue
        candidates.append((best_score, entry_id))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [entry_id for _score, entry_id in candidates[:3]]


def active_corpus_bridge_evidence_ids(
    machine_query: dict[str, Any],
    source_ids: list[str],
    *,
    routing_state: dict[str, Any] | None = None,
    active_protocol: str = DEFAULT_PROTOCOL,
    blocked_source_ids: set[str] | None = None,
) -> list[str]:
    blocked_source_ids = blocked_source_ids or set()
    bridge_concepts = set(machine_query.get("bridge_concept_slugs", []))
    source_set = set(source_ids) | {
        str(source_id)
        for source_id in machine_query.get("ranked_source_ids", [])
        if isinstance(source_id, str) and source_id and source_id not in blocked_source_ids
    }
    for node in machine_query.get("query_subgraph", {}).get("sources", []):
        if isinstance(node, dict):
            node_id = str(node.get("id") or "")
            if node_id and node_id not in blocked_source_ids:
                source_set.add(node_id)
    bridge_ids: list[str] = []
    seen: set[str] = set()
    if bridge_concepts:
        for edge in machine_query.get("query_subgraph", {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("type") != "HAS_CONCEPT":
                continue
            left = str(edge.get("left") or "")
            right = str(edge.get("right") or "")
            if (
                left in source_set
                and left not in blocked_source_ids
                and right in bridge_concepts
                and left not in seen
            ):
                seen.add(left)
                bridge_ids.append(left)
    if routing_state:
        excluded = set(source_set) | set(bridge_ids) | set(blocked_source_ids)
        for entry_id in routing_bridge_recall_ids(
            machine_query,
            routing_state,
            active_protocol=active_protocol,
            excluded_source_ids=excluded,
        ):
            if entry_id not in seen and entry_id not in blocked_source_ids:
                seen.add(entry_id)
                bridge_ids.append(entry_id)
    return bridge_ids


def reconcile_active_corpora_state(
    root: Path,
    *,
    changed_at: str,
    nightly_cooldown: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_active_corpora_state(root)
    changed = not active_corpora_state_path(root).exists()
    corpora: list[dict[str, Any]] = []
    for raw_corpus in state.get("corpora", []):
        corpus = dict(raw_corpus)
        status = str(corpus.get("status") or "active")
        if status not in ACTIVE_CORPUS_STATUSES:
            status = "active"
            changed = True
        expires_at = str(corpus.get("expires_at") or "")
        if expires_at and timestamp_is_newer(changed_at, expires_at):
            if status != "expired":
                status = "expired"
                changed = True
        elif nightly_cooldown and status == "active":
            status = "cooling"
            changed = True
        corpus["status"] = status
        corpora.append(corpus)
    if changed:
        save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return {"version": 1, "corpora": corpora, "changed": changed}


def refresh_material_state(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, Any]:
    documents = build_material_state_documents(
        root,
        generated_at=generated_at,
        entries=entries,
        active_protocol=active_protocol,
    )
    save_material_state(root, documents["material_state"])
    save_material_routing_state(root, documents["material_routing"])
    save_archive_candidates_state(root, documents["archive_candidates"])
    return documents["material_state"]


def build_material_state_documents(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, dict[str, Any]]:
    ensure_layout(root)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    resolved_protocol = active_protocol or load_protocol_state(root)["active_protocol"]
    history = load_runtime_history(root)
    active_corpora = reconcile_active_corpora_state(root, changed_at=generated_at)["corpora"]
    reference_state = scan_material_reference_state(root, manifest_entries)
    machine_memory = load_machine_memory(root)
    graph_context = material_graph_context(machine_memory)
    previous_archive_candidates = load_archive_candidates_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    last_query_hit_at: dict[str, str] = {}
    last_review_reference_at: dict[str, str] = {}

    for event in history:
        occurred_at = str(event.get("occurred_at") or "")
        event_type = str(event.get("event_type") or "")
        source_ids = [str(item) for item in event.get("source_ids", []) if isinstance(item, str)]
        if event_type == "query":
            for entry_id in source_ids:
                update_latest_timestamp(last_query_hit_at, entry_id, occurred_at)
        elif event_type == "review":
            for entry_id in source_ids:
                update_latest_timestamp(last_review_reference_at, entry_id, occurred_at)

    active_corpus_ids_by_entry: dict[str, list[str]] = {}
    for corpus in active_corpora:
        status = str(corpus.get("status") or "")
        if status not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        source_ids = [
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        ]
        for entry_id in source_ids:
            active_corpus_ids_by_entry.setdefault(entry_id, [])
            if corpus_id not in active_corpus_ids_by_entry[entry_id]:
                active_corpus_ids_by_entry[entry_id].append(corpus_id)

    material_entries: list[dict[str, Any]] = []
    routing_entries: list[dict[str, Any]] = []
    for entry in manifest_entries:
        entry_id = str(entry.get("id") or "")
        stored_path = str(entry.get("stored_path") or "")
        preview = read_text_preview(root / stored_path) if stored_path and (root / stored_path).exists() else ""
        supports_judgment_ids = reference_state["supports_judgment_ids"].get(entry_id, [])
        citation_count = int(reference_state["citation_count_by_entry"].get(entry_id, 0))
        active_corpus_ids = sorted(active_corpus_ids_by_entry.get(entry_id, []))
        query_hit_at = last_query_hit_at.get(entry_id, "")
        review_hit_at = last_review_reference_at.get(entry_id, "")
        protocol_hints = protocol_hints_for_material(entry, preview)
        routing_entry = build_material_routing_entry(
            active_protocol=resolved_protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=query_hit_at,
            last_review_reference_at=review_hit_at,
            graph_context=graph_context,
            computed_at=generated_at,
        )
        routing_entries.append(routing_entry)
        archive_record = archived_entries.get(entry_id, {})
        temperature = temperature_from_routing(
            str(routing_entry.get("selected_as") or ""),
            supports_judgment_ids=supports_judgment_ids,
        )
        if archive_record:
            temperature = "archived"
        material_entries.append(
            {
                "entry_id": entry_id,
                "path": stored_path,
                "kind": str(entry.get("kind") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "protocol_hints": protocol_hints,
                "temperature": temperature,
                "last_touched_at": str(entry.get("updated_at") or entry.get("imported_at") or ""),
                "last_query_hit_at": query_hit_at,
                "last_review_reference_at": review_hit_at,
                "citation_count": citation_count,
                "supports_judgment_ids": supports_judgment_ids,
                "active_corpus_ids": active_corpus_ids,
                "archive_override": bool(archive_record),
                "archived_at": str(archive_record.get("archived_at") or ""),
                "archive_receipt_path": str(archive_record.get("last_receipt_path") or ""),
                "archive_candidate": False,
            }
        )

    routing_document = {
        "version": 1,
        "computed_at": generated_at,
        "active_protocol": resolved_protocol,
        "entries": routing_entries,
    }
    archive_document = build_archive_candidate_state(
        material_entries=material_entries,
        routing_entries=routing_entries,
        active_judgment_ids=set(reference_state.get("active_judgment_ids", [])),
        generated_at=generated_at,
        previous_state=previous_archive_candidates,
        active_protocol=resolved_protocol,
    )
    active_archive_ids = {
        str(entry.get("entry_id") or "")
        for entry in archive_document.get("entries", [])
        if str(entry.get("status") or "") in {"suggested", "deferred", "ready"}
    }
    for material_entry in material_entries:
        material_entry["archive_candidate"] = material_entry.get("entry_id") in active_archive_ids
    material_document = {"version": 1, "generated_at": generated_at, "entries": material_entries}
    return {
        "material_state": material_document,
        "material_routing": routing_document,
        "archive_candidates": archive_document,
        "active_corpora_state": {"version": 1, "corpora": active_corpora},
    }


def upsert_active_corpus(
    root: Path,
    *,
    protocol: str,
    question: str,
    source_ids: list[str],
    concept_slugs: list[str],
    bridge_evidence_ids: list[str],
    output_ref: str,
    changed_at: str,
) -> dict[str, Any]:
    ensure_layout(root)
    state = reconcile_active_corpora_state(root, changed_at=changed_at)
    corpora = [dict(corpus) for corpus in state.get("corpora", [])]
    base_timestamp = parse_iso_datetime(changed_at) or datetime.now(timezone.utc)
    signature = question_signature(question)
    seed = slugify(question)[:40] or "question"
    corpus_id = f"{protocol}-{seed}-{signature.split(':', 1)[1][:8]}"
    target: dict[str, Any] | None = None
    for corpus in corpora:
        if str(corpus.get("corpus_id") or "") == corpus_id:
            target = corpus
            break
    if target is None:
        target = {"corpus_id": corpus_id, "created_at": changed_at}
        corpora.append(target)
    output_refs = [str(item) for item in target.get("output_refs", []) if isinstance(item, str)]
    if output_ref and output_ref not in output_refs:
        output_refs.append(output_ref)
    target.update(
        {
            "protocol": protocol,
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": signature,
            "source_ids": source_ids,
            "concept_slugs": concept_slugs,
            "bridge_evidence_ids": bridge_evidence_ids,
            "output_refs": output_refs[-8:],
            "status": "active",
            "last_used_at": changed_at,
            "expires_at": (base_timestamp + ACTIVE_CORPUS_TTL).replace(microsecond=0).isoformat(),
        }
    )
    save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return target


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


@runtime_write_operation
def save_machine_memory_action_state(root: Path, document: dict[str, Any]) -> None:
    machine_memory_action_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_machine_memory(root: Path) -> dict[str, Any]:
    memory = load_json_document(machine_memory_state_path(root))
    return memory if isinstance(memory, dict) else {}


def default_concept_rewrite_state() -> dict[str, Any]:
    return {"version": 1, "proposals": []}


def load_concept_rewrite_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_rewrite_state_path(root))
    if not isinstance(document, dict):
        return default_concept_rewrite_state()
    proposals = document.get("proposals")
    if not isinstance(proposals, list):
        return default_concept_rewrite_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "proposals": [proposal for proposal in proposals if isinstance(proposal, dict)],
    }


@runtime_write_operation
def save_concept_rewrite_state(root: Path, document: dict[str, Any]) -> None:
    concept_rewrite_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def default_manual_link_state() -> dict[str, Any]:
    return {"version": 1, "source_to_concept": []}


def load_manual_link_state(root: Path) -> dict[str, Any]:
    document = load_json_document(manual_link_state_path(root))
    if not isinstance(document, dict):
        return default_manual_link_state()
    source_to_concept = document.get("source_to_concept")
    if not isinstance(source_to_concept, list):
        return default_manual_link_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "source_to_concept": [item for item in source_to_concept if isinstance(item, dict)],
    }


@runtime_write_operation
def save_manual_link_state(root: Path, document: dict[str, Any]) -> None:
    manual_link_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    active_protocol: str = DEFAULT_PROTOCOL,
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
        protocol = str(previous.get("protocol") or action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
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
        last_receipt_path = str(previous.get("last_receipt_path") or "")
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
            "protocol": protocol,
            "status": status,
            "active": True,
            "first_seen_at": first_seen_at,
            "last_seen_at": compiled_at,
            "occurrences": occurrences,
            "status_updated_at": status_updated_at,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "last_receipt_path": last_receipt_path,
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
        preserved_pending = (
            bool(previous.get("active", True))
            and str(previous.get("status") or "") in PENDING_ACTION_STATUSES
            and str(previous.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
        )
        if preserved_pending:
            try:
                validate_low_risk_action_targets(root, previous)
            except RuntimeError:
                preserved_pending = False
        if preserved_pending:
            status = str(previous.get("status") or "proposed")
            reviewed_at = str(previous.get("reviewed_at") or "")
            first_seen_at = str(previous.get("first_seen_at") or compiled_at)
            status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
            revisit_after = str(previous.get("revisit_after") or "")
            escalate_after = str(previous.get("escalate_after") or "")
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows("action", status, base_timestamp)
            record = {
                **dict(previous),
                "protocol": str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                "status": status,
                "active": True,
                "last_seen_at": compiled_at,
                "inactive_since": "",
                "pending_review": "true" if action_needs_review(status) else "false",
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
            }
            record.update(evaluate_page_aging(record, now=now))
            active_records.append(record)
            seen_ids.add(action_id)
            continue
        record = dict(previous)
        record["protocol"] = str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
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
    degree_map: dict[str, int] = {}
    for edge in graph.get("edges", []):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in positions or target not in positions:
            continue
        degree_map[source] = degree_map.get(source, 0) + 1
        degree_map[target] = degree_map.get(target, 0) + 1
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        if str(edge.get("type") or "") == "RELATED_CONCEPT":
            stroke = "#f59e0b"
            dash = ' stroke-dasharray="8 6"'
        else:
            stroke = "#94a3b8"
            dash = ""
        edge_fragments.append(
            f'<line class="graph-edge" data-source="{html.escape(source)}" data-target="{html.escape(target)}" '
            f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="2"{dash} opacity="0.72" />'
        )

    node_fragments: list[str] = []
    node_rows: list[str] = []
    node_records: list[dict[str, Any]] = []
    source_component_ids = health.get("source_component_ids", {})
    concept_component_ids = health.get("concept_component_ids", {})
    component_label_by_id = {str(component.get("id") or ""): str(component.get("id") or "") for component in components}
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
            page_path = str(node.get("source_page") or "")
            href = f"../../{html.escape(page_path)}"
            subtitle = str(node.get("source_type") or "source")
            component_id = str(source_component_ids.get(node_id.removeprefix("source:"), "") or "")
            secondary_metric = str(node.get("stored_path") or "")
        else:
            fill = "#1d4ed8"
            stroke = "#1e40af"
            slug = node_id.removeprefix("concept:")
            page_path = f"wiki/concepts/{slug}.md"
            href = f"../../wiki/concepts/{html.escape(slug)}.md"
            subtitle = "concept"
            component_id = str(concept_component_ids.get(slug, "") or "")
            secondary_metric = f"source_pages {len(node.get('source_pages', []))}"
        safe_title = html.escape(title)
        label = html.escape(truncate_label(title))
        rx = x - 120
        ry = y - 22
        component_label = component_label_by_id.get(component_id, component_id or "none")
        node_fragments.append(
            "\n".join(
                [
                    f'<g class="graph-node" data-node-id="{html.escape(node_id)}" data-kind="{html.escape(kind)}" data-component="{html.escape(component_id)}" data-title="{safe_title.lower()}">',
                    f'  <a href="{href}">',
                    f'    <title>{safe_title}</title>',
                    f'    <rect x="{rx}" y="{ry}" width="240" height="44" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2" />',
                    f'    <text x="{x}" y="{y - 3}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">{label}</text>',
                    f'    <text x="{x}" y="{y + 14}" text-anchor="middle" fill="#dbeafe" font-size="11">{html.escape(subtitle)}</text>',
                    "  </a>",
                    "</g>",
                ]
            )
        )
        node_rows.append(
            "<li class=\"node-row\""
            f" data-node-id=\"{html.escape(node_id)}\""
            f" data-kind=\"{html.escape(kind)}\""
            f" data-component=\"{html.escape(component_id)}\""
            f" data-title=\"{safe_title.lower()}\">"
            f"<button type=\"button\" class=\"node-detail-button\" data-node-id=\"{html.escape(node_id)}\">详情</button> "
            f"<a href=\"{href}\">{safe_title}</a>"
            f" <span class=\"node-meta\">{html.escape(subtitle)} · {html.escape(component_label)} · degree {degree_map.get(node_id, 0)}</span>"
            "</li>"
        )
        node_records.append(
            {
                "id": node_id,
                "kind": kind,
                "title": title,
                "subtitle": subtitle,
                "href": href,
                "page_path": page_path,
                "component_id": component_id,
                "component_label": component_label,
                "degree": degree_map.get(node_id, 0),
                "secondary_metric": secondary_metric,
            }
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
    rewrite_counts = health.get("concept_rewrite", {}).get("counts", {})
    safe_apply_actions = [
        action for action in health.get("repair_plan", {}).get("ready_actions", []) if action_supports_low_risk_apply(action)
    ]
    summary_items = [
        f"来源节点 {len(memory.get('source_nodes', []))}",
        f"概念节点 {len(memory.get('concept_nodes', []))}",
        f"分量 {health.get('component_count', 0)}",
        f"桥接概念 {len(health.get('bridge_concept_slugs', []))}",
        f"修复动作 {actions.get('total', 0)}",
        f"执行提案 {repair_counts.get('proposals', 0)}",
        f"rewrite 提案 {rewrite_counts.get('active', 0)}",
        f"safe apply {len(safe_apply_actions)}",
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
    apply_ready_items = "".join(
        f'<li>{html.escape(str(action.get("title") or action.get("id") or "action"))} | command <code>{html.escape(str(action.get("command_hint") or ""))}</code></li>'
        for action in safe_apply_actions[:8]
        if action.get("command_hint")
    ) or "<li>当前没有可直接 semi-auto apply 的动作。</li>"
    component_options = "".join(
        f'<option value="{html.escape(str(component.get("id") or ""))}">{html.escape(str(component.get("id") or ""))} ({len(component.get("source_ids", [])) + len(component.get("concept_slugs", []))})</option>'
        for component in components
        if component.get("id")
    )
    node_rows_markup = "".join(node_rows) or "<li>当前没有可浏览的节点。</li>"
    node_payload = html_safe_json_literal(
        {
            "nodes": node_records,
            "defaultNodeId": node_records[0]["id"] if node_records else "",
        }
    )

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
            "    .controls { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 18px; }",
            "    label { display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }",
            "    input, select { width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; font: inherit; background: #fff; }",
            "    .canvas { overflow-x: auto; }",
            "    svg { width: 100%; min-width: 1020px; height: auto; display: block; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    .workbench { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); gap: 18px; align-items: start; }",
            "    .node-browser { max-height: 560px; overflow: auto; }",
            "    .node-browser ul { list-style: none; padding-left: 0; }",
            "    .node-row { padding: 10px 0; border-bottom: 1px solid #e2e8f0; }",
            "    .node-row:last-child { border-bottom: 0; }",
            "    .node-meta { color: var(--muted); font-size: 12px; }",
            "    .node-detail-button { margin-right: 8px; border: 1px solid var(--line); background: #eff6ff; color: #1d4ed8; border-radius: 999px; padding: 2px 10px; cursor: pointer; }",
            "    .graph-node.hidden, .graph-edge.hidden, .node-row.hidden { display: none; }",
            "    .details-grid { display: grid; gap: 10px; }",
            "    .details-grid code { background: #eff6ff; padding: 2px 6px; border-radius: 8px; }",
            "    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--muted); }",
            "    .legend span::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 999px; margin-right: 6px; vertical-align: -1px; }",
            "    .legend .source::before { background: #0f766e; }",
            "    .legend .concept::before { background: #1d4ed8; }",
            "    .legend .related::before { background: #f59e0b; }",
            "    .empty { padding: 16px; background: #fff7ed; border: 1px solid #fdba74; border-radius: 14px; color: #9a3412; }",
            "    @media (max-width: 960px) { .workbench { grid-template-columns: 1fr; } }",
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
            '  <section class="panel">',
            '    <div class="controls">',
            '      <div><label for="graph-search">搜索节点</label><input id="graph-search" type="search" placeholder="输入标题、slug、source id" /></div>',
            '      <div><label for="graph-kind">节点类型</label><select id="graph-kind"><option value="">全部</option><option value="source">source</option><option value="concept">concept</option></select></div>',
            f'      <div><label for="graph-component">分量</label><select id="graph-component"><option value="">全部分量</option>{component_options}</select></div>',
            "    </div>",
            '    <div class="workbench">',
            '      <div class="panel canvas">',
            f'        <svg viewBox="0 0 1020 {view_height}" role="img" aria-label="machine memory graph">',
            f"{svg_body}",
            "        </svg>",
            "      </div>",
            '      <div class="details-grid">',
            '        <div class="panel"><h2>节点详情</h2><div id="graph-node-details">选择右侧节点详情按钮，查看 component、degree 和回链路径。</div></div>',
            '        <div class="panel node-browser"><h2>节点浏览器</h2><ul id="graph-node-browser">',
            f"{node_rows_markup}",
            "        </ul></div>",
            "      </div>",
            "    </div>",
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
            '    <div class="panel"><h2>Safe Apply</h2><ul>',
            f"{apply_ready_items}",
            "    </ul></div>",
            "  </section>",
            '  <section class="panel"><h2>相关入口</h2><ul>',
            '    <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '    <li><a href="../../wiki/indexes/graph-view.md">Graph View Dashboard</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory.md">机器记忆</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-topology.md">机器记忆拓扑</a></li>',
            '    <li><a href="../../wiki/indexes/graph-health.md">图谱健康</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>',
            "  </ul></section>",
            "  <script>",
            f"    const graphUiData = {node_payload};",
            "    const nodeMap = new Map((graphUiData.nodes || []).map((node) => [node.id, node]));",
            "    const searchInput = document.getElementById('graph-search');",
            "    const kindSelect = document.getElementById('graph-kind');",
            "    const componentSelect = document.getElementById('graph-component');",
            "    const nodeDetails = document.getElementById('graph-node-details');",
            "    function renderDetails(nodeId) {",
            "      const node = nodeMap.get(nodeId);",
            "      if (!node) { nodeDetails.innerHTML = '当前没有可展示的节点详情。'; return; }",
            "      nodeDetails.innerHTML = [",
            "        `<div><strong>${node.title}</strong></div>`,",
            "        `<div>kind: <code>${node.kind}</code></div>`,",
            "        `<div>component: <code>${node.component_label || 'none'}</code></div>`,",
            "        `<div>degree: <code>${node.degree}</code></div>`,",
            "        `<div>path: <code>${node.page_path}</code></div>`,",
            "        `<div>${node.secondary_metric || ''}</div>`,",
            "        `<div><a href=\"${node.href}\">打开页面</a></div>`",
            "      ].join('');",
            "    }",
            "    function applyFilters() {",
            "      const needle = (searchInput.value || '').trim().toLowerCase();",
            "      const kind = kindSelect.value || '';",
            "      const component = componentSelect.value || '';",
            "      const visibleIds = new Set();",
            "      document.querySelectorAll('.graph-node').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "        if (matches) visibleIds.add(nodeId);",
            "      });",
            "      document.querySelectorAll('.graph-edge').forEach((element) => {",
            "        const visible = visibleIds.has(element.dataset.source || '') && visibleIds.has(element.dataset.target || '');",
            "        element.classList.toggle('hidden', !visible);",
            "      });",
            "      document.querySelectorAll('.node-row').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "      });",
            "      if (!visibleIds.size) {",
            "        nodeDetails.innerHTML = '当前筛选条件下没有节点。';",
            "        return;",
            "      }",
            "      const firstVisible = document.querySelector('.node-row:not(.hidden)');",
            "      if (firstVisible) renderDetails(firstVisible.dataset.nodeId || '');",
            "    }",
            "    document.querySelectorAll('.node-detail-button').forEach((button) => {",
            "      button.addEventListener('click', () => renderDetails(button.dataset.nodeId || ''));",
            "    });",
            "    [searchInput, kindSelect, componentSelect].forEach((element) => element.addEventListener('input', applyFilters));",
            "    [kindSelect, componentSelect].forEach((element) => element.addEventListener('change', applyFilters));",
            "    renderDetails(graphUiData.defaultNodeId || '');",
            "    applyFilters();",
            "  </script>",
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


def build_machine_memory_query(
    memory: dict[str, Any],
    question: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    material_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    archive_candidates_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    time_focus_state = machine_memory_query_time_focus(question)
    time_focus = str(time_focus_state.get("focus") or "")

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

    source_rank_records = [
        machine_memory_source_runtime_record(
            source_id,
            base_score=base_score,
            source_nodes=source_nodes,
            material_by_entry=material_by_entry,
            routing_by_entry=routing_by_entry,
            archive_candidates_by_entry=archive_candidates_by_entry,
            protocol=protocol,
            time_focus=time_focus,
        )
        for source_id, base_score in expanded_source_scores.items()
        if source_id in source_nodes
    ]
    source_rank_records.sort(
        key=lambda item: (
            -float(item.get("combined_score", 0.0) or 0.0),
            -float(item.get("base_score", 0.0) or 0.0),
            -float(item.get("protocol_bonus", 0.0) or 0.0),
            -float(item.get("time_bonus", 0.0) or 0.0),
            str(item.get("title") or item.get("entry_id") or "").lower(),
        )
    )
    ranked_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records[:8]
        if item.get("entry_id")
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
    protocol_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("protocol_shard")) and item.get("entry_id")
    ][:5]
    time_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("time_shard")) and item.get("entry_id")
    ][:5]
    archive_recall_hints = [
        {
            "entry_id": str(item.get("entry_id") or ""),
            "title": str(item.get("title") or item.get("entry_id") or ""),
            "path": str(item.get("path") or ""),
            "temperature": str(item.get("temperature") or ""),
            "archive_status": str(item.get("archive_status") or ""),
            "recommended_temperature": str(item.get("recommended_temperature") or ""),
            "reason_codes": list(item.get("reason_codes", []) or []),
        }
        for item in sorted(
            source_rank_records,
            key=lambda record: (
                -float(record.get("archive_hint_score", 0.0) or 0.0),
                -float(record.get("combined_score", 0.0) or 0.0),
                str(record.get("title") or record.get("entry_id") or "").lower(),
            ),
        )
        if bool(item.get("archive_hint")) and item.get("entry_id")
    ][:3]
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
                "command_hint": action.get("command_hint", ""),
                "apply_ready": action.get("apply_ready", "false"),
                "proposal_kind": proposal.get("proposal_kind", ""),
                "proposal_summary": proposal.get("summary", ""),
                "proposal_targets": proposal.get("target_paths", []),
                "focus_score": action_focus_score(protocol, action),
            }
        )
    relevant_actions.sort(
        key=lambda item: (
            0 if item.get("status") == "accepted" else 1,
            -int(item.get("focus_score", 0)),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "time_focus": time_focus,
        "time_focus_markers": list(time_focus_state.get("markers", []) or []),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "protocol_shard_source_ids": protocol_shard_source_ids,
        "time_shard_source_ids": time_shard_source_ids,
        "archive_recall_hints": archive_recall_hints,
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
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
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
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
        f"- 概念冲突信号：`{health.get('concept_quality', {}).get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念重写候选：`{health.get('concept_quality', {}).get('counts', {}).get('rewrite_candidates', 0)}`",
        f"- Rewrite 提案：`{health.get('concept_rewrite', {}).get('counts', {}).get('active', 0)}`",
        f"- 可应用 Rewrite：`{health.get('concept_rewrite', {}).get('counts', {}).get('apply_ready', 0)}`",
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
        "- [Rewrite Proposals](./rewrite-proposals.md)",
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
    recent_receipts = sorted(
        [
            action
            for action in [*actions, *inactive_actions]
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
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
                f" | band `{action.get('execution_band', 'review-first')}`"
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
                f" | band `{action.get('execution_band', 'review-first')}`"
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
    lines.extend(["", "## 最近执行回执"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
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
        f"- 页级 patch step：`{counts.get('patch_steps', 0)}`",
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
                f" | band `{action.get('execution_band', 'review-first')}`"
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
                f" | band `{action.get('execution_band', 'review-first')}`"
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
                f" | band `{action.get('execution_band', 'review-first')}`"
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
            lines.append(f"  - bundle: `{proposal.get('bundle_path', '') or 'none'}`")
            for edit in proposal.get("suggested_edits", [])[:3]:
                lines.append(f"  - edit: {edit}")
            patch_plan = proposal.get("page_patch_plan", [])
            if patch_plan:
                for patch in patch_plan[:4]:
                    sections = ", ".join(patch.get("sections", [])) or "none"
                    lines.append(
                        f"  - patch `{patch.get('path', '')}`"
                        f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                        f" | mode `{patch.get('mode', 'update')}`"
                        f" | sections `{sections}`"
                    )
    lines.extend(["", "## Page-Level Patch Plans"])
    if not execution_proposals:
        lines.append("- 当前没有页级 patch plan。")
    else:
        for proposal in execution_proposals[:8]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(
                f"### `{proposal.get('action_id', 'proposal')}` · {proposal.get('title', 'unnamed proposal')}"
            )
            lines.append(f"- Summary: {proposal.get('summary', 'n/a')}")
            lines.append(f"- Risk: `{proposal.get('risk', 'medium')}` | Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`")
            for patch in patch_plan:
                sections = ", ".join(patch.get("sections", [])) or "none"
                command_hint = str(patch.get("command_hint") or "")
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{sections}`"
                    f" | exists `{patch.get('exists', False)}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
                if command_hint:
                    lines.append(f"  - command: `{command_hint}`")
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


def render_execution_proposal_page(proposal: dict[str, Any], *, compiled_at: str) -> str:
    frontmatter = render_frontmatter(
        {
            "title": str(proposal.get("title") or proposal.get("action_id") or "Execution Proposal"),
            "kind": "execution-proposal",
            "status": str(proposal.get("status") or "proposed"),
            "action_id": str(proposal.get("action_id") or ""),
            "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
            "risk": str(proposal.get("risk") or "medium"),
            "priority": str(proposal.get("priority") or "medium"),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "target_paths": list(proposal.get("target_paths", [])),
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        f"# {proposal.get('title') or proposal.get('action_id')}",
        "",
        "## Overview",
        f"- Action id: `{proposal.get('action_id', '')}`",
        f"- Status: `{display_action_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
        f"- Risk: `{proposal.get('risk', 'medium')}`",
        f"- Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`",
        f"- Priority: `{proposal.get('priority', 'medium')}`",
        f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
        f"- Bundle: `{proposal.get('bundle_path', '') or 'none'}`",
        "",
        "## Strategy",
        f"- {proposal.get('summary', 'n/a')}",
        "",
        "## Suggested Edits",
    ]
    edits = proposal.get("suggested_edits", [])
    if not edits:
        lines.append("- 当前没有额外建议。")
    else:
        lines.extend(f"- {edit}" for edit in edits)
    lines.extend(["", "## Page-Level Patch Plan"])
    patch_plan = proposal.get("page_patch_plan", [])
    if not patch_plan:
        lines.append("- 当前没有页级 patch step。")
    else:
        for patch in patch_plan:
            sections = ", ".join(patch.get("sections", [])) or "none"
            lines.append(
                f"- `{patch.get('path', '')}`"
                f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                f" | mode `{patch.get('mode', 'update')}`"
                f" | exists `{patch.get('exists', False)}`"
                f" | sections `{sections}`"
            )
            lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
    lines.extend(["", "## Commands"])
    if proposal.get("bundle_path"):
        lines.append(
            f"- Suggested apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {proposal.get('action_id', '')} --bundle {proposal.get('bundle_path', '')}`"
        )
    if proposal.get("command_hint"):
        lines.append(f"- Suggested next step: `{proposal['command_hint']}`")
    else:
        lines.append("- 当前没有直接命令提示。")
    safe_preview = proposal.get("safe_apply_preview")
    lines.extend(["", "## Safe Apply Preview"])
    if not safe_preview:
        lines.append("- 当前 proposal 不支持低风险 safe apply。")
    else:
        entry = safe_preview.get("entry", {})
        lines.append(f"- Apply mode: `{safe_preview.get('apply_mode', 'manual')}`")
        lines.append(f"- State path: `{safe_preview.get('state_path', '')}`")
        lines.append(
            f"- Manual link entry: source `{entry.get('source_id', '')}` -> concept `{entry.get('concept_slug', '')}`"
        )
        lines.append(f"- Affected paths: `{', '.join(safe_preview.get('affected_paths', [])) or 'none'}`")
        lines.append(f"- Follow-up: {safe_preview.get('follow_up', 'n/a')}")
    lines.extend(
        [
            "",
            "## Related Links",
            "- [执行中心](../indexes/execution-center.md)",
            "- [机器记忆修复计划](../indexes/machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](../indexes/machine-memory-actions.md)",
            "- [炉心面板](../indexes/furnace-center.md)",
            f"- [Execution Bundle](../../{proposal.get('bundle_path', '')})" if proposal.get("bundle_path") else "- Execution Bundle: none",
        ]
    )
    return f"{frontmatter}\n\n" + "\n".join(lines).strip() + "\n"


def render_execution_center(memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    lines = [
        "# 执行中心",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Ready actions：`{plan.get('counts', {}).get('ready', 0)}`",
        f"- 可安全执行动作：`{len(apply_ready_actions)}`",
        f"- Execution proposals：`{plan.get('counts', {}).get('proposals', 0)}`",
        f"- Page-level patch steps：`{patch_steps}`",
        "- 本地执行面板：`output/control/execution-center.html`",
        "",
        "## Safe Apply Now",
    ]
    if not apply_ready_actions:
        lines.append("- 当前没有可直接 `apply-action` 的低风险动作。")
    else:
        for action in apply_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | band `{action.get('execution_band', 'bundle-safe-apply')}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action.get('id', '')} --bundle output/control/execution-bundles/{slugify(str(action.get('id') or ''))}.json` | primary `{action.get('primary_path', '')}`"
            )
    lines.extend(["", "## Revert Safe Apply"])
    if not revert_ready_actions:
        lines.append("- 当前没有可回滚的 safe apply。")
    else:
        for action in revert_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action.get('id', '')}` | receipt `{action.get('last_receipt_path', '')}`"
            )
    lines.extend(["", "## Execution Proposals"])
    if not proposals:
        lines.append("- 当前没有 execution proposal。")
    else:
        for proposal in proposals[:12]:
            lines.append(
                f"- [{proposal['title']}](../execution-proposals/{slugify(str(proposal.get('action_id') or ''))}.md)"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | patch `{len(proposal.get('page_patch_plan', []))}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | bundle `{proposal.get('bundle_path', '') or 'none'}`"
            )
    lines.extend(["", "## Recent Receipts"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- `{action['title']}`"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
            "## Quick Links",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [审阅中心](./review-center.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [本地执行面板](../../output/control/execution-center.html)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_center_html(memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    summary_cards = [
        ("Ready Actions", str(plan.get("counts", {}).get("ready", 0))),
        ("Safe Apply", str(len(apply_ready_actions))),
        ("Proposals", str(plan.get("counts", {}).get("proposals", 0))),
        ("Patch Steps", str(patch_steps)),
    ]
    safe_apply_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>{html.escape(str(action.get('command_hint') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('primary_path') or ''))}</div></li>"
        for action in apply_ready_actions[:8]
    ) or "<li>当前没有可直接 safe apply 的动作。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {html.escape(str(action.get('id') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('last_receipt_path') or ''))}</div></li>"
        for action in revert_ready_actions[:8]
    ) or "<li>当前没有可回滚的 safe apply。</li>"
    proposal_markup = "".join(
        f"<li><strong><a href=\"../../wiki/execution-proposals/{html.escape(slugify(str(proposal.get('action_id') or '')))}.md\">{html.escape(str(proposal.get('title') or 'proposal'))}</a></strong>"
        f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))} / patch {len(proposal.get('page_patch_plan', []))}</span>"
        f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(proposal.get('bundle_path') or ''))}\">Execution Bundle</a></div></li>"
        for proposal in proposals[:10]
    ) or "<li>当前没有 execution proposal。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(action.get('last_receipt_path') or ''))}\">Execution Receipt</a></div></li>"
        for action in recent_receipts[:8]
    ) or "<li>当前还没有 safe execution receipt。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Execution Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code>。这里把 safe apply、execution proposal 和 patch-step 执行工作区收敛到一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>Safe Apply Actions</h2><ul>{safe_apply_markup}</ul></div>',
            f'    <div class="panel"><h2>Revert Safe Apply</h2><ul>{revert_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>Recent Receipts</h2><ul>{receipt_markup}</ul></div>',
            '    <div class="panel"><h2>相关入口</h2><ul>'
            '      <li><a href="../../wiki/indexes/execution-center.md">Markdown 执行中心</a></li>'
            '      <li><a href="../../wiki/indexes/execution-audit.md">执行审计</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">动作队列</a></li>'
            '      <li><a href="../../wiki/indexes/review-center.md">审阅中心</a></li>'
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>'
            '      <li><a href="../../output/control/execution-audit.html">审计 HTML</a></li>'
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def collect_execution_consistency_signals(
    root: Path,
    actions: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    manual_state = load_manual_link_state(root)
    active_manual_links: dict[str, list[dict[str, Any]]] = {}
    for item in manual_state.get("source_to_concept", []):
        if not isinstance(item, dict) or not bool(item.get("active", True)):
            continue
        origin_action_id = str(item.get("origin_action_id") or "")
        if not origin_action_id:
            continue
        active_manual_links.setdefault(origin_action_id, []).append(item)
    latest_receipt_by_action: dict[str, dict[str, Any]] = {}
    for record in history:
        action_id = str(record.get("action_id") or "")
        if action_id and action_id not in latest_receipt_by_action:
            latest_receipt_by_action[action_id] = record

    signals: list[dict[str, str]] = []
    for action in actions:
        if str(action.get("kind") or "") not in LOW_RISK_APPLYABLE_ACTION_KINDS:
            continue
        action_id = str(action.get("id") or "")
        if not action_id:
            continue
        status = str(action.get("status") or "proposed")
        latest = latest_receipt_by_action.get(action_id)
        latest_operation = str(latest.get("operation") or "") if latest else ""
        has_active_manual_link = bool(active_manual_links.get(action_id))
        title = str(action.get("title") or action_id)
        primary_path = str(action.get("primary_path") or "")

        if status == "resolved" and latest_operation != "apply":
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但最新 execution receipt 不是 apply。",
                }
            )
        if status == "resolved" and not has_active_manual_link:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但 active manual-link state 缺失。",
                }
            )
        if latest_operation == "revert" and has_active_manual_link:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "最新 receipt 已是 revert，但 manual-link state 仍然 active。",
                }
            )
        if status in PENDING_ACTION_STATUSES and has_active_manual_link:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作仍在待处理状态，但 manual-link state 仍然 active；需要确认是否应先 revert 或直接 resolve。",
                }
            )
    signals.sort(
        key=lambda item: (
            0 if item.get("severity") == "error" else 1,
            str(item.get("title") or "").lower(),
            str(item.get("message") or ""),
        )
    )
    return signals


def build_execution_audit_snapshot(root: Path, memory: dict[str, Any], *, active_protocol: str) -> dict[str, Any]:
    health = memory.get("health", {})
    actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    all_actions = actions + inactive_actions
    history = load_execution_receipt_history(root)
    recent_apply = [record for record in history if str(record.get("operation") or "") == "apply"][:8]
    recent_revert = [record for record in history if str(record.get("operation") or "") == "revert"][:8]
    recent_by_protocol: dict[str, dict[str, list[dict[str, Any]]]] = {
        "recent_apply": {},
        "recent_revert": {},
    }
    band_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    receipt_counts: dict[str, int] = {}
    for record in history:
        protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        action_id = str(record.get("action_id") or "")
        if action_id:
            receipt_counts[action_id] = receipt_counts.get(action_id, 0) + 1
        operation = str(record.get("operation") or "")
        if operation in {"apply", "revert"}:
            bucket_name = "recent_apply" if operation == "apply" else "recent_revert"
            scoped = recent_by_protocol[bucket_name].setdefault(protocol, [])
            if len(scoped) < 8:
                scoped.append(record)
    action_rows: list[dict[str, Any]] = []
    for action in all_actions:
        profile = execution_policy_profile(action)
        band = str(action.get("execution_band") or profile.get("execution_band") or "review-first")
        band_counts[band] = band_counts.get(band, 0) + 1
        action_id = str(action.get("id") or "")
        capabilities = action.get("execution_capability_list")
        if not isinstance(capabilities, list):
            capabilities = list(profile.get("capabilities") or [])
        action_rows.append(
            {
                "id": action_id,
                "title": str(action.get("title") or action_id),
                "status": display_action_status(str(action.get("status") or "proposed")),
                "execution_band": band,
                "execution_band_label": execution_band_label(band),
                "execution_policy": str(action.get("execution_policy") or profile.get("execution_policy") or "triage"),
                "execution_capabilities": [str(item) for item in capabilities if isinstance(item, str) and item],
                "policy_summary": str(action.get("policy_summary") or profile.get("policy_summary") or ""),
                "receipt_count": receipt_counts.get(action_id, 0),
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "primary_path": str(action.get("primary_path") or ""),
            }
        )
    action_rows.sort(
        key=lambda item: (
            0 if item.get("execution_band") == "bundle-safe-apply" else 1,
            0 if item.get("status") == display_action_status("accepted") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    band_rows = [
        {"band": band, "label": execution_band_label(band), "count": band_counts.get(band, 0)}
        for band in ("bundle-safe-apply", "review-first", "manual-repair", "deferred", "closed", "history-only")
        if band_counts.get(band, 0)
    ]
    protocol_rows = [
        {"protocol": protocol, "title": protocol_title(protocol), "count": count}
        for protocol, count in sorted(protocol_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    consistency_signals = collect_execution_consistency_signals(root, all_actions, history)
    return {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "active_protocol": active_protocol,
        "receipt_history_path": relative_path(root, execution_receipt_history_path(root)),
        "counts": {
            "actions": len(all_actions),
            "receipts": len(history),
            "apply": len([record for record in history if str(record.get("operation") or "") == "apply"]),
            "revert": len([record for record in history if str(record.get("operation") or "") == "revert"]),
            "bundle_safe": band_counts.get("bundle-safe-apply", 0),
        },
        "policy_bands": band_rows,
        "protocols": protocol_rows,
        "recent_apply": recent_apply,
        "recent_revert": recent_revert,
        "recent_by_protocol": recent_by_protocol,
        "actions": action_rows[:16],
        "consistency_signals": consistency_signals[:16],
        "consistency_counts": {
            "errors": sum(1 for item in consistency_signals if item.get("severity") == "error"),
            "warns": sum(1 for item in consistency_signals if item.get("severity") == "warn"),
        },
    }


def render_execution_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# 执行审计",
        "",
        f"- 最近编译时间：`{audit.get('compiled_at', '')}`",
        f"- 当前协议：`{audit.get('active_protocol', DEFAULT_PROTOCOL)}` ({protocol_title(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))})",
        f"- 动作总数：`{audit.get('counts', {}).get('actions', 0)}`",
        f"- Receipt 总数：`{audit.get('counts', {}).get('receipts', 0)}`",
        f"- Apply / Revert：`{audit.get('counts', {}).get('apply', 0)}` / `{audit.get('counts', {}).get('revert', 0)}`",
        f"- Bundle-safe actions：`{audit.get('counts', {}).get('bundle_safe', 0)}`",
        f"- Receipt history：`{audit.get('receipt_history_path', '.aiwiki/state/execution-receipts.jsonl')}`",
        "",
        "## Policy Bands",
    ]
    band_rows = audit.get("policy_bands", [])
    if not band_rows:
        lines.append("- 当前还没有可审计的 execution policy band。")
    else:
        for row in band_rows:
            lines.append(f"- `{row['band']}` | {row['label']} | count `{row['count']}`")
    lines.extend(["", "## Recent Apply"])
    recent_apply = audit.get("recent_apply", [])
    if not recent_apply:
        lines.append("- 当前还没有 apply receipt。")
    else:
        for receipt in recent_apply:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | applied `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Recent Revert"])
    recent_revert = audit.get("recent_revert", [])
    if not recent_revert:
        lines.append("- 当前还没有 revert receipt。")
    else:
        for receipt in recent_revert:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | reverted `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Protocol Breakdown"])
    protocols = audit.get("protocols", [])
    if not protocols:
        lines.append("- 当前还没有 protocol 级 execution history。")
    else:
        for row in protocols:
            lines.append(f"- `{row['protocol']}` ({row['title']}) | receipts `{row['count']}`")
    lines.extend(["", "## Consistency Signals"])
    consistency_signals = audit.get("consistency_signals", [])
    if not consistency_signals:
        lines.append("- 当前没有 execution consistency signal。")
    else:
        for signal in consistency_signals:
            lines.append(
                f"- [{signal.get('severity', 'warn')}] `{signal.get('title', signal.get('action_id', 'signal'))}`"
                f" | action `{signal.get('action_id', '')}`"
                f" | {signal.get('message', '')}"
            )
    lines.extend(["", "## Action Audit"])
    actions = audit.get("actions", [])
    if not actions:
        lines.append("- 当前还没有 action audit rows。")
    else:
        for action in actions:
            capabilities = ", ".join(action.get("execution_capabilities", [])) or "none"
            lines.append(
                f"- `{action['title']}`"
                f" | status `{action['status']}`"
                f" | band `{action['execution_band']}`"
                f" | policy `{action['execution_policy']}`"
                f" | receipts `{action['receipt_count']}`"
            )
            lines.append(f"  - capabilities: {capabilities}")
            lines.append(f"  - summary: {action.get('policy_summary', 'n/a')}")
            if action.get("last_receipt_path"):
                lines.append(f"  - last receipt: `{action['last_receipt_path']}`")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [执行中心](./execution-center.md)",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_audit_html(audit: dict[str, Any]) -> str:
    summary_cards = [
        ("Receipts", str(audit.get("counts", {}).get("receipts", 0))),
        ("Apply", str(audit.get("counts", {}).get("apply", 0))),
        ("Revert", str(audit.get("counts", {}).get("revert", 0))),
        ("Bundle Safe", str(audit.get("counts", {}).get("bundle_safe", 0))),
    ]
    band_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('label') or row.get('band') or 'band'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('band') or ''))}</span>"
        f"<div class=\"metric-inline\">count {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("policy_bands", [])
    ) or "<li>当前还没有可审计的 execution policy band。</li>"
    apply_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_apply", [])
    ) or "<li>当前还没有 apply receipt。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_revert", [])
    ) or "<li>当前还没有 revert receipt。</li>"
    protocol_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('title') or row.get('protocol') or 'protocol'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('protocol') or ''))}</span>"
        f"<div>receipts {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("protocols", [])
    ) or "<li>当前还没有 protocol 级 execution history。</li>"
    action_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or action.get('id') or 'action'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('execution_band_label') or action.get('execution_band') or ''))}"
        f" / {html.escape(str(action.get('execution_policy') or 'triage'))}"
        f" / receipts {html.escape(str(action.get('receipt_count') or 0))}</div>"
        f"<div>{html.escape(str(action.get('policy_summary') or ''))}</div></li>"
        for action in audit.get("actions", [])
    ) or "<li>当前还没有 action audit rows。</li>"
    consistency_markup = "".join(
        f"<li><strong>{html.escape(str(signal.get('title') or signal.get('action_id') or 'signal'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(signal.get('severity') or 'warn'))}</span>"
        f"<div>{html.escape(str(signal.get('message') or ''))}</div></li>"
        for signal in audit.get("consistency_signals", [])
    ) or "<li>当前没有 execution consistency signal。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Audit</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #ecfeff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #0f766e; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .metric-inline { color: #0f766e; font-weight: 700; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #0f766e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #ecfeff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <section class=\"panel\">",
            "      <h1>Execution Audit</h1>",
            f"      <p>当前协议 <strong>{html.escape(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))}</strong> · 最近编译 {html.escape(str(audit.get('compiled_at') or ''))}</p>",
            "      <p><a href=\"../../wiki/indexes/execution-audit.md\">Markdown 审计页</a> · <a href=\"../../wiki/indexes/execution-center.md\">执行中心</a> · <a href=\"../../wiki/indexes/furnace-center.md\">炉心面板</a></p>",
            "      <div class=\"meta\">",
            *[
                "\n".join(
                    [
                        '        <div class="card">',
                        f'          <div class="metric-label">{html.escape(label)}</div>',
                        f'          <div class="metric">{html.escape(value)}</div>',
                        "        </div>",
                    ]
                )
                for label, value in summary_cards
            ],
            "      </div>",
            "    </section>",
            "    <section class=\"grid\">",
            f'      <div class="card"><h2>Policy Bands</h2><ul>{band_markup}</ul></div>',
            f'      <div class="card"><h2>Protocol Breakdown</h2><ul>{protocol_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Apply</h2><ul>{apply_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Revert</h2><ul>{revert_markup}</ul></div>',
            f'      <div class="card"><h2>Consistency Signals</h2><ul>{consistency_markup}</ul></div>',
            f'      <div class="card"><h2>Action Audit</h2><ul>{action_markup}</ul></div>',
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_concept_quality(memory: dict[str, Any]) -> str:
    quality = memory.get("health", {}).get("concept_quality", {})
    rewrite_state = memory.get("health", {}).get("concept_rewrite", {})
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
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审提案：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用提案：`{rewrite_state.get('counts', {}).get('apply_ready', 0)}`",
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
    lines.extend(["", "## Rewrite Proposals"])
    if not rewrite_state.get("proposals"):
        lines.append("- 当前还没有 concept rewrite proposal。先运行 `run-compile` 或等待下一次 rewrite proposal 生成。")
    else:
        for proposal in rewrite_state.get("proposals", [])[:10]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
            )
            if proposal.get("rewrite_strategy"):
                lines.append(f"  - strategy: {proposal['rewrite_strategy']}")
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
            "- [Rewrite Proposals](./rewrite-proposals.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def concept_page_snapshot(root: Path, slug: str) -> dict[str, Any]:
    path = root / "wiki" / "concepts" / f"{slug}.md"
    if not path.exists():
        return {
            "path": relative_path(root, path),
            "title": slug,
            "source_signature": "",
            "source_pages": [],
            "summary": "",
            "content": "",
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", [])
    if not isinstance(source_pages, list):
        source_pages = []
    return {
        "path": relative_path(root, path),
        "title": str(frontmatter.get("title") or path.stem),
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "source_pages": [str(item) for item in source_pages if isinstance(item, str)],
        "summary": preserved_section(content, "Summary", ""),
        "content": content,
    }


def concept_rewrite_proposal_digest(candidate_markdown: str) -> str:
    if not candidate_markdown:
        return ""
    return sha256_bytes(candidate_markdown.encode("utf-8"))


def reconcile_concept_rewrite_proposals(
    root: Path,
    quality: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    previous_state = load_concept_rewrite_state(root)
    previous_by_slug = {
        str(proposal.get("slug") or ""): proposal
        for proposal in previous_state.get("proposals", [])
        if proposal.get("slug")
    }
    active_records: list[dict[str, Any]] = []
    inactive_records: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for candidate in quality.get("rewrite_candidates", []):
        slug = str(candidate.get("slug") or "").strip()
        if not slug:
            continue
        snapshot = concept_page_snapshot(root, slug)
        previous = previous_by_slug.get(slug, {})
        source_signature = str(candidate.get("source_signature") or snapshot.get("source_signature") or "")
        status = str(previous.get("status") or "proposed")
        if status not in REWRITE_PROPOSAL_STATUSES:
            status = "proposed"
        previous_signature = str(previous.get("source_signature") or "")
        signature_changed = bool(previous_signature and previous_signature != source_signature)
        if signature_changed and status in {"applied", "rejected"}:
            status = "proposed"
        candidate_markdown = str(previous.get("candidate_markdown") or "")
        candidate_digest = str(previous.get("candidate_digest") or concept_rewrite_proposal_digest(candidate_markdown))
        first_proposed_at = str(previous.get("first_proposed_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0) + 1
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        applied_at = str(previous.get("applied_at") or "")
        if signature_changed:
            status = "proposed"
            candidate_markdown = ""
            candidate_digest = ""
            reviewed_at = ""
            review_note = ""
            applied_at = ""
        record = {
            "slug": slug,
            "title": str(candidate.get("title") or snapshot.get("title") or slug),
            "priority": str(candidate.get("priority") or "medium"),
            "score": int(candidate.get("score") or 0),
            "issues": list(candidate.get("issues") or []),
            "rewrite_strategy": str(candidate.get("rewrite_strategy") or ""),
            "target_path": str(candidate.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": source_signature,
            "source_pages": list(candidate.get("source_pages") or snapshot.get("source_pages") or []),
            "status": status,
            "active": True,
            "first_proposed_at": first_proposed_at,
            "last_proposed_at": compiled_at,
            "occurrences": occurrences,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "applied_at": applied_at,
            "pending_review": "true" if rewrite_proposal_needs_review(status) else "false",
            "candidate_markdown": candidate_markdown,
            "candidate_digest": candidate_digest,
            "apply_ready": False,
            "current_summary": str(snapshot.get("summary") or ""),
        }
        record["apply_ready"] = rewrite_proposal_is_apply_ready(root, record)
        active_records.append(record)
        seen_slugs.add(slug)

    for slug, previous in previous_by_slug.items():
        if slug in seen_slugs:
            continue
        record = dict(previous)
        record["active"] = False
        record["pending_review"] = "false"
        record["apply_ready"] = False
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("applied_at") or item.get("reviewed_at") or item.get("last_proposed_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    document = {
        "version": 1,
        "compiled_at": compiled_at,
        "proposals": active_records + inactive_records,
    }
    save_concept_rewrite_state(root, document)
    counts = {
        "active": len(active_records),
        "inactive": len(inactive_records),
        "pending_review": sum(1 for proposal in active_records if proposal.get("pending_review") == "true"),
        "apply_ready": sum(1 for proposal in active_records if proposal.get("apply_ready")),
        "by_status": {
            status: sum(1 for proposal in active_records if proposal.get("status") == status)
            for status in REWRITE_PROPOSAL_STATUSES
        },
    }
    return {
        "all_proposals": active_records + inactive_records,
        "proposals": active_records[:12],
        "inactive_proposals": inactive_records[:8],
        "counts": counts,
        "state_path": relative_path(root, concept_rewrite_state_path(root)),
    }


def render_concept_rewrite_proposal_page(proposal: dict[str, Any]) -> str:
    frontmatter = render_frontmatter(
        {
            "id": f"rewrite-proposal-{proposal['slug']}",
            "kind": "rewrite-proposal",
            "status": proposal.get("status", "proposed"),
            "title": proposal["title"],
            "target_path": proposal.get("target_path", ""),
            "source_signature": proposal.get("source_signature", ""),
            "generated_by": "aiwiki-run-compile",
            "last_compiled_at": proposal.get("last_proposed_at", ""),
        }
    )
    lines = [
        frontmatter,
        "",
        f"# Rewrite Proposal · {proposal['title']}",
        "",
        "## Proposal Status",
        f"- Status: `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Priority: `{proposal.get('priority', 'n/a')}`",
        f"- Score: `{proposal.get('score', 0)}`",
        f"- Apply ready: `{proposal.get('apply_ready', False)}`",
        f"- First proposed: `{proposal.get('first_proposed_at', '') or 'none'}`",
        f"- Last proposed: `{proposal.get('last_proposed_at', '') or 'none'}`",
        f"- Reviewed at: `{proposal.get('reviewed_at', '') or 'none'}`",
        f"- Applied at: `{proposal.get('applied_at', '') or 'none'}`",
        "",
        "## Target",
        f"- Target page: `{proposal.get('target_path', '')}`",
        f"- Source signature: `{proposal.get('source_signature', '')}`",
        f"- Source pages: `{', '.join(proposal.get('source_pages', [])) or 'none'}`",
        "",
        "## Current Summary Snapshot",
        proposal.get("current_summary", "") or "- No summary snapshot captured.",
        "",
        "## Rewrite Strategy",
        f"- Issues: `{', '.join(proposal.get('issues', [])) or 'none'}`",
        f"- Strategy: {proposal.get('rewrite_strategy', 'n/a')}",
        "",
        "## Commands",
        f"- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite {proposal['slug']} --status accepted`",
        f"- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`",
        "",
        "## Proposed Markdown",
    ]
    if proposal.get("candidate_markdown"):
        lines.extend(
            [
                "```markdown",
                str(proposal["candidate_markdown"]).strip(),
                "```",
            ]
        )
    else:
        lines.append("- 当前还没有生成候选重写内容。先运行 `run-compile`。")
    return "\n".join(lines) + "\n"


def render_concept_rewrite_index(state: dict[str, Any], compiled_at: str) -> str:
    proposals = state.get("proposals", [])
    inactive = state.get("inactive_proposals", [])
    counts = state.get("counts", {})
    lines = [
        "# Rewrite Proposals",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- Active proposals：`{counts.get('active', 0)}`",
        f"- Pending review：`{counts.get('pending_review', 0)}`",
        f"- Apply ready：`{counts.get('apply_ready', 0)}`",
        f"- 状态文件：`{state.get('state_path', '.aiwiki/state/concept-rewrite-proposals.json')}`",
        "",
        "## Pending Review",
    ]
    pending = [proposal for proposal in proposals if proposal.get("pending_review") == "true"]
    if not pending:
        lines.append("- 当前没有待审的 rewrite proposal。")
    else:
        for proposal in pending[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
            )
    lines.extend(["", "## Apply Ready"])
    apply_ready = [proposal for proposal in proposals if proposal.get("apply_ready")]
    if not apply_ready:
        lines.append("- 当前没有可直接应用的 rewrite proposal。")
    else:
        for proposal in apply_ready[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    lines.extend(["", "## Recently Closed"])
    if not inactive:
        lines.append("- 当前没有已关闭的 rewrite proposal。")
    else:
        for proposal in inactive[:8]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | applied `{proposal.get('applied_at', '') or 'none'}`"
            )
    return "\n".join(lines) + "\n"


def store_concept_rewrite_candidate(
    root: Path,
    slug: str,
    *,
    quality_record: dict[str, Any],
    candidate_markdown: str,
    generated_at: str,
) -> dict[str, Any]:
    ensure_layout(root)
    snapshot = concept_page_snapshot(root, slug)
    state = load_concept_rewrite_state(root)
    proposals = [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]
    target: dict[str, Any] | None = None
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            target = proposal
            break
    if target is None:
        target = {
            "slug": slug,
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "status": "proposed",
            "first_proposed_at": generated_at,
        }
        proposals.append(target)
    digest = concept_rewrite_proposal_digest(candidate_markdown)
    previous_digest = str(target.get("candidate_digest") or "")
    previous_status = str(target.get("status") or "proposed")
    if previous_digest and previous_digest != digest and previous_status != "proposed":
        target["status"] = "proposed"
        target["reviewed_at"] = ""
        target["review_note"] = ""
        target["applied_at"] = ""
    target.update(
        {
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "priority": str(quality_record.get("priority") or "medium"),
            "score": int(quality_record.get("score") or 0),
            "issues": list(quality_record.get("issues") or []),
            "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
            "target_path": str(quality_record.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": str(quality_record.get("source_signature") or snapshot.get("source_signature") or ""),
            "source_pages": list(quality_record.get("source_pages") or snapshot.get("source_pages") or []),
            "active": True,
            "last_proposed_at": generated_at,
            "occurrences": int(target.get("occurrences") or 0) + 1,
            "candidate_markdown": candidate_markdown.strip() + "\n",
            "candidate_digest": digest,
            "current_summary": str(snapshot.get("summary") or ""),
        }
    )
    target["pending_review"] = "true" if rewrite_proposal_needs_review(str(target.get("status") or "proposed")) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    write_if_changed(root / str(target["proposal_path"]), render_concept_rewrite_proposal_page(target))
    return {
        "slug": slug,
        "proposal_path": str(target["proposal_path"]),
        "status": str(target.get("status") or "proposed"),
        "candidate_digest": digest,
    }


@runtime_write_operation
def compile_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    previous_manifest = load_manifest(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    compiled_at = utc_now()
    protocol_state = load_protocol_state(root)
    previous_memory = load_json_document(machine_memory_state_path(root))
    changed_pages = 0
    source_changed_pages = 0
    concept_changed_pages = 0
    index_changed_pages = 0
    maintenance_changed_pages = 0
    dirty_index_artifacts: list[str] = []
    clean_index_artifacts: list[str] = []
    dirty_maintenance_artifacts: list[str] = []
    clean_maintenance_artifacts: list[str] = []

    def write_index_artifact(destination: Path, content: str) -> int:
        nonlocal changed_pages
        nonlocal index_changed_pages

        wrote, dirty = write_if_changed_ignoring_timestamps(destination, content)
        relative = relative_path(root, destination)
        if dirty:
            dirty_index_artifacts.append(relative)
        else:
            clean_index_artifacts.append(relative)
        changed_pages += int(wrote)
        index_changed_pages += int(wrote)
        return int(wrote)

    def write_maintenance_artifact(destination: Path, document: dict[str, Any]) -> int:
        nonlocal changed_pages
        nonlocal maintenance_changed_pages

        wrote, dirty = write_json_document_if_changed_ignoring_generated_timestamps(destination, document)
        relative = relative_path(root, destination)
        if dirty:
            dirty_maintenance_artifacts.append(relative)
        else:
            clean_maintenance_artifacts.append(relative)
        changed_pages += int(wrote)
        maintenance_changed_pages += int(wrote)
        return int(wrote)

    previews: dict[str, str] = {}
    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file)
        previews[entry["id"]] = preview
    concepts, entry_terms, concept_build = build_concept_records(
        root,
        entries,
        previews,
        generated_at=compiled_at,
    )
    dirty_concept_source_ids = list(concept_build.get("dirty_concept_source_ids", []))
    clean_concept_source_ids = list(concept_build.get("clean_concept_source_ids", []))
    concept_build_state = concept_build.get("state_document", {})
    if not isinstance(concept_build_state, dict):
        concept_build_state = default_concept_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(concept_build_state_path(root), concept_build_state)
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    dirty_source_id_set: set[str] = set()
    for entry in entries:
        entry_id = str(entry["id"])
        if source_page_requires_compile(root, entry, entry_terms.get(entry_id, [])):
            dirty_source_ids.append(entry_id)
            dirty_source_id_set.add(entry_id)
        else:
            clean_source_ids.append(entry_id)
    for entry in entries:
        if entry["id"] not in dirty_source_id_set:
            continue
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        content = render_source_page_with_state(
            entry,
            previews[entry["id"]],
            compiled_at,
            concepts=entry_terms.get(entry["id"], []),
            existing_page=existing_page,
        )
        wrote = int(write_if_changed(destination, content))
        source_changed_pages += wrote
        changed_pages += wrote

    write_index_artifact(root / "wiki" / "indexes" / "sources.md", render_sources_index(entries, compiled_at))
    write_index_artifact(root / "wiki" / "indexes" / "concepts.md", render_concepts_index(concepts, compiled_at))
    decision_pages = collect_curated_pages(root, "decisions", "decision")
    judgment_pages = collect_curated_pages(root, "judgments", "judgment")
    write_index_artifact(
        root / "wiki" / "indexes" / "decisions.md",
        render_curated_index("决策索引", "决策列表", decision_pages, compiled_at),
    )
    write_index_artifact(
        root / "wiki" / "indexes" / "judgments.md",
        render_curated_index("判断索引", "判断列表", judgment_pages, compiled_at),
    )
    write_index_artifact(
        judgment_assets_path(root),
        render_judgment_assets(
            decision_pages,
            judgment_pages,
            compiled_at,
            active_protocol=protocol_state["active_protocol"],
        ),
    )
    write_index_artifact(
        root / "wiki" / "indexes" / "index.md",
        render_master_index(entries, concepts, decision_pages, judgment_pages, protocol_state, compiled_at),
    )
    ensure_wiki_log(root)

    concept_lookup = {record["slug"]: record for record in concepts}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    dirty_concept_slug_set: set[str] = set()
    for record in concepts:
        record["record_lookup"] = concept_lookup
        record["root"] = root
        record["render_signature"] = concept_render_signature(root, record)
        slug = str(record["slug"])
        if concept_page_requires_compile(root, record):
            dirty_concept_slugs.append(slug)
            dirty_concept_slug_set.add(slug)
        else:
            clean_concept_slugs.append(slug)
    for record in concepts:
        if str(record["slug"]) not in dirty_concept_slug_set:
            continue
        destination = root / "wiki" / "concepts" / f"{record['slug']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        wrote = int(write_if_changed(destination, render_concept_page(record, compiled_at, existing_page)))
        changed_pages += wrote
        concept_changed_pages += wrote

    removed_pages = remove_stale_generated_concept_pages(root, {record["slug"] for record in concepts})
    memory = build_machine_memory(root, entries, concepts, previews, entry_terms, compiled_at)
    memory["health"] = build_machine_memory_health(memory)
    memory["health"].update(
        reconcile_machine_memory_actions(
            root,
            memory["health"],
            compiled_at=compiled_at,
            active_protocol=protocol_state["active_protocol"],
        )
    )
    memory["health"]["repair_plan"] = build_machine_memory_repair_plan(
        root,
        memory["health"],
        active_protocol=protocol_state["active_protocol"],
    )
    memory["health"]["concept_quality"] = build_concept_quality(root, memory)
    memory["health"]["concept_rewrite"] = reconcile_concept_rewrite_proposals(
        root,
        memory["health"]["concept_quality"],
        compiled_at=compiled_at,
    )
    memory["digest"] = machine_memory_digest(memory)
    graph = build_machine_memory_graph(memory)
    memory["graph_digest"] = graph["digest"]
    memory["graph_path"] = relative_path(root, machine_memory_graph_path(root))
    memory["history_path"] = relative_path(root, machine_memory_history_path(root))
    transition = summarize_machine_memory_transition(previous_memory, memory)
    memory["transition"] = transition
    write_index_artifact(machine_memory_state_path(root), json.dumps(memory, indent=2, sort_keys=True) + "\n")
    write_index_artifact(machine_memory_graph_path(root), json.dumps(graph, indent=2, sort_keys=True) + "\n")
    write_index_artifact(machine_memory_graph_html_path(root), render_machine_memory_graph_html(memory, graph))
    append_machine_memory_history(root, memory, transition)
    write_index_artifact(root / "wiki" / "indexes" / "machine-memory.md", render_machine_memory_index(memory))
    write_index_artifact(machine_memory_topology_path(root), render_machine_memory_topology(memory))
    write_index_artifact(machine_memory_actions_path(root), render_machine_memory_actions(memory))
    write_index_artifact(machine_memory_repair_plan_path(root), render_machine_memory_repair_plan(memory))
    write_index_artifact(
        execution_center_path(root),
        render_execution_center(
            memory,
            compiled_at=compiled_at,
            active_protocol=protocol_state["active_protocol"],
        ),
    )
    execution_audit = build_execution_audit_snapshot(
        root,
        memory,
        active_protocol=protocol_state["active_protocol"],
    )
    write_index_artifact(execution_audit_path(root), render_execution_audit(execution_audit))
    all_outputs = collect_output_density_artifacts(root)
    recent_outputs = collect_recent_output_artifacts(root)
    material_state_documents = build_material_state_documents(
        root,
        generated_at=compiled_at,
        entries=entries,
        active_protocol=protocol_state["active_protocol"],
    )
    active_corpora_state = material_state_documents["active_corpora_state"]
    material_state = material_state_documents["material_state"]
    material_routing = material_state_documents["material_routing"]
    archive_candidates = material_state_documents["archive_candidates"]
    knowledge_lifecycle = build_knowledge_lifecycle_document(
        root,
        generated_at=compiled_at,
        decisions=decision_pages,
        judgments=judgment_pages,
        entries=entries,
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    write_maintenance_artifact(material_state_path(root), material_state)
    write_maintenance_artifact(material_routing_state_path(root), material_routing)
    write_maintenance_artifact(archive_candidates_state_path(root), archive_candidates)
    write_maintenance_artifact(knowledge_lifecycle_state_path(root), knowledge_lifecycle)
    write_index_artifact(
        root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            root,
            compiled_at,
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    output_packs = build_output_packs(
        root,
        decision_pages,
        judgment_pages,
        memory,
        protocol_state,
        recent_outputs,
        compiled_at,
        knowledge_lifecycle=knowledge_lifecycle,
    )
    write_index_artifact(
        output_packs_index_path(root),
        render_output_packs_index(output_packs, compiled_at, protocol_state["active_protocol"]),
    )
    for pack in output_packs["review_packs"]:
        write_index_artifact(root / pack["path"], pack["content"])
    for pack in output_packs["decision_memos"]:
        write_index_artifact(root / pack["path"], pack["content"])
    for pack in output_packs["sop_drafts"]:
        write_index_artifact(root / pack["path"], pack["content"])
    removed_pages += remove_stale_generated_markdown_files(
        review_packs_dir(root),
        {Path(pack["path"]).stem for pack in output_packs["review_packs"]},
    )
    removed_pages += remove_stale_generated_markdown_files(
        decision_memos_dir(root),
        {Path(pack["path"]).stem for pack in output_packs["decision_memos"]},
    )
    removed_pages += remove_stale_generated_markdown_files(
        sop_drafts_dir(root),
        {Path(pack["path"]).stem for pack in output_packs["sop_drafts"]},
    )
    domain_pilots = build_domain_pilots(
        root,
        decision_pages,
        judgment_pages,
        memory,
        protocol_state,
        recent_outputs,
        all_outputs,
        output_packs,
        execution_audit,
        compiled_at,
        knowledge_lifecycle=knowledge_lifecycle,
        material_routing=material_routing,
    )
    write_index_artifact(
        domain_pilots_index_path(root),
        render_domain_pilots_index(domain_pilots, compiled_at, protocol_state["active_protocol"]),
    )
    for scorecard in domain_pilots["scorecards"]:
        write_index_artifact(root / scorecard["path"], scorecard["content"])
    removed_pages += remove_stale_generated_markdown_files(
        pilot_scorecards_dir(root),
        {Path(scorecard["path"]).stem for scorecard in domain_pilots["scorecards"]},
    )
    agent_packs = build_agent_packs(
        root,
        entries,
        decision_pages,
        judgment_pages,
        memory,
        protocol_state,
        recent_outputs,
        compiled_at,
        knowledge_lifecycle=knowledge_lifecycle,
    )
    write_index_artifact(
        agent_workbench_path(root),
        render_agent_workbench(
            agent_packs,
            compiled_at,
            protocol_state["active_protocol"],
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    for pack in agent_packs:
        write_index_artifact(root / pack["path"], pack["content"])
    write_index_artifact(
        root / "wiki" / "indexes" / "furnace-center.md",
        render_furnace_center(
            decision_pages,
            judgment_pages,
            memory,
            compiled_at,
            protocol_state,
            recent_outputs,
            output_packs,
            domain_pilots,
            execution_audit,
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    write_index_artifact(
        review_center_html_path(root),
        render_review_center_html(
            decision_pages,
            judgment_pages,
            memory,
            compiled_at,
            active_protocol=protocol_state["active_protocol"],
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    write_index_artifact(
        furnace_center_html_path(root),
        render_furnace_center_html(
            decision_pages,
            judgment_pages,
            memory,
            compiled_at,
            protocol_state,
            recent_outputs,
            output_packs,
            domain_pilots,
            execution_audit,
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    write_index_artifact(
        execution_center_html_path(root),
        render_execution_center_html(
            memory,
            compiled_at=compiled_at,
            active_protocol=protocol_state["active_protocol"],
        ),
    )
    write_index_artifact(execution_audit_html_path(root), render_execution_audit_html(execution_audit))
    write_index_artifact(concept_quality_path(root), render_concept_quality(memory))
    write_index_artifact(
        concept_rewrite_index_path(root),
        render_concept_rewrite_index(memory["health"]["concept_rewrite"], compiled_at),
    )
    for proposal in memory["health"]["concept_rewrite"].get("all_proposals", []):
        write_index_artifact(root / proposal["proposal_path"], render_concept_rewrite_proposal_page(proposal))
    removed_pages += remove_stale_generated_execution_proposal_pages(
        root,
        {
            str(proposal.get("action_id") or "")
            for proposal in memory["health"]["repair_plan"].get("execution_proposals", [])
            if proposal.get("action_id")
        },
    )
    removed_pages += remove_stale_generated_execution_bundle_files(
        root,
        {
            str(proposal.get("action_id") or "")
            for proposal in memory["health"]["repair_plan"].get("execution_proposals", [])
            if proposal.get("action_id")
        },
    )
    for proposal in memory["health"]["repair_plan"].get("execution_proposals", []):
        write_index_artifact(
            root / str(proposal["proposal_path"]),
            render_execution_proposal_page(proposal, compiled_at=compiled_at),
        )
        write_index_artifact(
            root / str(proposal["bundle_path"]),
            json.dumps(
                build_execution_bundle(root, proposal, compiled_at=compiled_at),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    write_index_artifact(graph_health_report_path(root), render_graph_health(memory))
    write_index_artifact(machine_memory_drift_report_path(root), render_drift_report(memory, transition))
    write_index_artifact(
        root / "wiki" / "indexes" / "review-queue.md",
        render_review_queue(
            decision_pages,
            judgment_pages,
            compiled_at,
            active_protocol=protocol_state["active_protocol"],
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    write_index_artifact(
        cognitive_history_path(root),
        render_cognitive_history(
            root,
            decision_pages,
            judgment_pages,
            compiled_at,
            active_protocol=protocol_state["active_protocol"],
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )
    write_index_artifact(
        aging_report_path(root),
        render_aging_report(
            decision_pages,
            judgment_pages,
            compiled_at,
            active_protocol=protocol_state["active_protocol"],
            knowledge_lifecycle=knowledge_lifecycle,
        ),
    )

    metadata_details = manifest_change_summary(previous_manifest.get("entries", []), entries)
    phase_summary = [
        {
            "name": "metadata_refresh",
            "label": "metadata refresh",
            "mode": "full",
            "status": "completed",
            "details": metadata_details,
        },
        {
            "name": "incremental_source_compile",
            "label": "incremental source compile",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "source_pages": len(entries),
                "dirty_sources": len(dirty_source_ids),
                "clean_sources": len(clean_source_ids),
                "updated_pages": source_changed_pages,
                "skipped_pages": len(clean_source_ids),
            },
        },
        {
            "name": "concept_refresh",
            "label": "concept refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "concept_sources": len(entries),
                "dirty_concept_sources": len(dirty_concept_source_ids),
                "clean_concept_sources": len(clean_concept_source_ids),
                "concept_pages": len(concepts),
                "dirty_concepts": len(dirty_concept_slugs),
                "clean_concepts": len(clean_concept_slugs),
                "updated_pages": concept_changed_pages,
                "skipped_pages": len(clean_concept_slugs),
            },
        },
        {
            "name": "index_refresh",
            "label": "index refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(dirty_index_artifacts) + len(clean_index_artifacts),
                "dirty_artifacts": len(dirty_index_artifacts),
                "clean_artifacts": len(clean_index_artifacts),
                "updated_artifacts": index_changed_pages,
                "skipped_artifacts": len(clean_index_artifacts),
            },
        },
        {
            "name": "cold_archive_maintenance",
            "label": "cold/archive maintenance",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(dirty_maintenance_artifacts) + len(clean_maintenance_artifacts),
                "dirty_artifacts": len(dirty_maintenance_artifacts),
                "clean_artifacts": len(clean_maintenance_artifacts),
                "updated_artifacts": maintenance_changed_pages,
                "skipped_artifacts": len(clean_maintenance_artifacts),
                "removed_generated_pages": removed_pages,
                "material_state_entries": len(material_state["entries"]),
                "archive_candidates": len(archive_candidates.get("entries", [])),
                "active_corpora": len(active_corpora_state.get("corpora", [])),
                "knowledge_lifecycle_entries": len(knowledge_lifecycle.get("entries", [])),
            },
        },
    ]
    compile_state = {
        "version": 1,
        "compiled_at": compiled_at,
        "manifest_entry_count": len(entries),
        "dirty_source_ids": dirty_source_ids,
        "clean_source_ids": clean_source_ids,
        "dirty_concept_source_ids": dirty_concept_source_ids,
        "clean_concept_source_ids": clean_concept_source_ids,
        "dirty_concept_slugs": dirty_concept_slugs,
        "clean_concept_slugs": clean_concept_slugs,
        "dirty_index_artifacts": dirty_index_artifacts,
        "clean_index_artifacts": clean_index_artifacts,
        "dirty_maintenance_artifacts": dirty_maintenance_artifacts,
        "clean_maintenance_artifacts": clean_maintenance_artifacts,
        "phase_summary": phase_summary,
    }
    save_compile_state(root, compile_state)
    compile_status_changed = int(
        write_if_changed(
            root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(
                entries,
                concepts,
                decision_pages,
                judgment_pages,
                protocol_state,
                compiled_at,
                compile_state=compile_state,
            ),
        )
    )
    changed_pages += compile_status_changed
    append_wiki_log(
        root,
        "compile",
        "wiki refresh",
        [
            f"compiled_at: `{compiled_at}`",
            f"compile_state: `{relative_path(root, compile_state_path(root))}`",
            f"compile_dirty_sources: `{len(dirty_source_ids)}`",
            f"compile_clean_sources: `{len(clean_source_ids)}`",
            f"compile_dirty_concept_sources: `{len(dirty_concept_source_ids)}`",
            f"compile_clean_concept_sources: `{len(clean_concept_source_ids)}`",
            f"compile_dirty_concepts: `{len(dirty_concept_slugs)}`",
            f"compile_clean_concepts: `{len(clean_concept_slugs)}`",
            f"compile_dirty_index_artifacts: `{len(dirty_index_artifacts)}`",
            f"compile_clean_index_artifacts: `{len(clean_index_artifacts)}`",
            f"compile_dirty_maintenance_artifacts: `{len(dirty_maintenance_artifacts)}`",
            f"compile_clean_maintenance_artifacts: `{len(clean_maintenance_artifacts)}`",
            f"source_pages_updated: `{source_changed_pages}`",
            f"source_pages: `{len(entries)}`",
            f"concept_pages: `{len(concepts)}`",
            f"active_protocol: `{protocol_state['active_protocol']}`",
            f"machine_memory_terms: `{len(memory['term_index'])}`",
            f"graph_components: `{memory['health']['component_count']}`",
            f"output_packs: `{output_packs['counts']['review_packs']}/{output_packs['counts']['decision_memos']}/{output_packs['counts']['sop_drafts']}`",
            f"domain_pilots: `{len(domain_pilots['scorecards'])}`",
            f"material_state_entries: `{len(material_state['entries'])}`",
            f"material_routing_entries: `{len(material_routing.get('entries', []))}`",
            f"archive_candidates: `{len(archive_candidates.get('entries', []))}`",
            f"active_corpora: `{len(active_corpora_state.get('corpora', []))}`",
            f"knowledge_lifecycle_entries: `{len(knowledge_lifecycle.get('entries', []))}`",
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
        "dirty_sources": len(dirty_source_ids),
        "clean_sources": len(clean_source_ids),
        "dirty_source_ids": list(dirty_source_ids),
        "clean_source_ids": list(clean_source_ids),
        "dirty_concept_sources": len(dirty_concept_source_ids),
        "clean_concept_sources": len(clean_concept_source_ids),
        "dirty_concept_source_ids": list(dirty_concept_source_ids),
        "clean_concept_source_ids": list(clean_concept_source_ids),
        "dirty_concepts": len(dirty_concept_slugs),
        "clean_concepts": len(clean_concept_slugs),
        "dirty_concept_slugs": list(dirty_concept_slugs),
        "clean_concept_slugs": list(clean_concept_slugs),
        "dirty_index_artifacts": list(dirty_index_artifacts),
        "clean_index_artifacts": list(clean_index_artifacts),
        "dirty_maintenance_artifacts": list(dirty_maintenance_artifacts),
        "clean_maintenance_artifacts": list(clean_maintenance_artifacts),
        "phase_summary": phase_summary,
        "output_packs": dict(output_packs["counts"]),
        "domain_pilots": len(domain_pilots["scorecards"]),
        "compile_state_path": relative_path(root, compile_state_path(root)),
        "concept_build_state_path": relative_path(root, concept_build_state_path(root)),
        "material_state_path": relative_path(root, material_state_path(root)),
        "active_corpora_path": relative_path(root, active_corpora_state_path(root)),
        "material_routing_path": relative_path(root, material_routing_state_path(root)),
        "archive_candidates_path": relative_path(root, archive_candidates_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "knowledge_lifecycle_overrides_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
    }


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def rank_concepts(
    root: Path,
    question: str,
    boost_concept_slugs: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    lifecycle = load_knowledge_lifecycle_state(root)
    retired_paths = {
        str(entry.get("path") or "")
        for entry in lifecycle.get("entries", [])
        if isinstance(entry, dict)
        and str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "retired"
    }
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        if relative_path(root, path) in retired_paths:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        title = frontmatter.get("title") or path.stem
        haystack = f"{title}\n{strip_frontmatter(content)}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        score += concept_focus_score(protocol, str(title), strip_frontmatter(content))
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


def source_page_requires_compile(root: Path, entry: dict[str, Any], concepts: list[str]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    if compiled_source_sha(content) != entry["sha256"]:
        return True
    frontmatter = parse_frontmatter(content)
    existing_concepts = frontmatter.get("concepts", [])
    if not isinstance(existing_concepts, list):
        existing_concepts = []
    normalized_existing = [str(label) for label in existing_concepts if str(label)]
    normalized_target = [str(label) for label in concepts if str(label)]
    return normalized_existing != normalized_target


def concept_page_requires_compile(root: Path, record: dict[str, Any]) -> bool:
    page = root / "wiki" / "concepts" / f"{record['slug']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    existing_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(existing_source_pages, list):
        existing_source_pages = []
    normalized_existing = [str(path) for path in existing_source_pages if str(path)]
    normalized_target = concept_source_pages(record)
    if normalized_existing != normalized_target:
        return True
    if str(frontmatter.get("source_signature") or "") != record["source_signature"]:
        return True
    render_signature = str(record.get("render_signature") or concept_render_signature(root, record))
    return str(frontmatter.get("render_signature") or "") != render_signature


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
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[float, int, float, dict[str, Any]]] = []
    boost_source_ids = boost_source_ids or set()
    material_state = load_material_state(root)
    material_by_id = {
        str(item.get("entry_id") or ""): item
        for item in material_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    routing_state = load_material_routing_state(root)
    routing_by_id = {
        str(item.get("entry_id") or ""): item
        for item in routing_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    archived_source_ids = active_archived_material_ids(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        material_entry = material_by_id.get(entry_id, {})
        if entry_id in archived_source_ids or str(material_entry.get("temperature") or "") == "archived":
            continue
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
        score += entry_focus_score(protocol, entry, summary_or_preview)
        if entry_id in boost_source_ids:
            score += 5
        if not score:
            continue

        routing_entry = routing_by_id.get(entry_id, {})
        routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
        runtime_score = 0.0
        if material_entry.get("active_corpus_ids"):
            runtime_score += 3.0
        temperature = str(material_entry.get("temperature") or "")
        if temperature == "hot":
            runtime_score += 2.0
        elif temperature == "warm":
            runtime_score += 1.0
        if material_entry.get("supports_judgment_ids"):
            runtime_score += 0.5

        selected_as = str(routing_snapshot.get("selected_as") or "")
        if selected_as == "hot-evidence":
            runtime_score += 2.5
        elif selected_as == "warm-evidence":
            runtime_score += 1.5
        elif selected_as == "cold-evidence":
            runtime_score += 0.5
        elif selected_as == "archive-candidate":
            runtime_score -= 0.5
        runtime_score += min(1.5, float(routing_snapshot.get("total_score", 0.0) or 0.0) * 0.35)

        top_protocols = [
            str(item.get("protocol") or "")
            for item in routing_entry.get("top_protocols", [])
            if isinstance(item, dict) and str(item.get("protocol") or "")
        ]
        if top_protocols[:1] == [protocol]:
            runtime_score += 1.0
        elif protocol in top_protocols[:2]:
            runtime_score += 0.5

        combined_score = float(score * 5) + runtime_score
        scored.append((combined_score, score, runtime_score, entry))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]["title"].lower()))
    return [entry for _combined, _base, _runtime, entry in scored[:5]]


def machine_memory_query_plan_lines(machine_query: dict[str, Any]) -> list[str]:
    lines = [
        f"- 命中词：`{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- 提升权重的来源：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- 提升权重的概念：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- 协议 shard 来源：`{', '.join(machine_query.get('protocol_shard_source_ids', [])) or 'none'}`",
        f"- 时间偏置：`{str(machine_query.get('time_focus') or 'none')}`",
        f"- 时间意图词：`{', '.join(machine_query.get('time_focus_markers', [])) or 'none'}`",
        f"- 时间 shard 来源：`{', '.join(machine_query.get('time_shard_source_ids', [])) or 'none'}`",
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`",
        f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`",
    ]
    archive_hints = machine_query.get("archive_recall_hints", []) or []
    if archive_hints:
        hint_labels = []
        for hint in archive_hints[:3]:
            title = str(hint.get("title") or hint.get("entry_id") or "")
            temperature = str(hint.get("temperature") or "")
            archive_status = str(hint.get("archive_status") or "")
            state_label = "/".join(part for part in (temperature, archive_status) if part) or "hint"
            hint_labels.append(f"{title} [{state_label}]")
        lines.append(f"- 归档召回提示：`{', '.join(hint_labels)}`")
    else:
        lines.append("- 归档召回提示：`none`")
    return lines


def render_report(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(active_protocol, "report")
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "report",
            "query": question,
            "protocol": active_protocol,
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
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的报告偏置。")
    lines.extend(
        [
            "",
            "## 推荐索引页",
            "- [知识库总索引](../../wiki/indexes/index.md)",
            "- [来源索引](../../wiki/indexes/sources.md)",
            "- [概念索引](../../wiki/indexes/concepts.md)",
            "- [决策索引](../../wiki/indexes/decisions.md)",
            "- [判断索引](../../wiki/indexes/judgments.md)",
            "- [判断资产](../../wiki/indexes/judgment-assets.md)",
            "- [Agent Workbench](../../wiki/indexes/agent-workbench.md)",
            "- [认知历史](../../wiki/indexes/cognitive-history.md)",
            "- [输出 Pack 总览](../../wiki/indexes/output-packs.md)",
            "- [领域 Pilot 总览](../../wiki/indexes/domain-pilots.md)",
            "- [协议总览](../../wiki/indexes/protocols.md)",
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
            f"- [当前协议规则](../../schema/protocols/{active_protocol}/index.md)",
            "",
            "## 机器记忆查询计划",
        ]
    )
    matched_terms = machine_query.get("matched_terms", [])
    if matched_terms:
        lines.append(f"- 命中词：`{', '.join(matched_terms)}`")
    else:
        lines.append("- 当前还没有直接命中的机器记忆词。")
    lines.extend(machine_memory_query_plan_lines(machine_query)[1:])
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
        "2. 按当前协议优先组织最相关来源和概念。",
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
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(active_protocol, "slides")
    lines = [
        "---",
        "marp: true",
        'kind: "output"',
        'format: "slides"',
        f"query: {render_scalar(question)}",
        f'protocol: "{active_protocol}"',
        'generated_by: "aiwiki-ask"',
        f'created_at: "{created_at}"',
        f"title: {render_scalar(question)}",
        f"description: {render_scalar(f'Generated at {created_at}')}",
        "---",
        "",
        f"# {question}",
        "",
        "## 使用说明",
        "- 把排好序的来源页整理成 5 到 7 页幻灯片。",
        "- 每页正文都保留引用。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的幻灯片偏置。")
    lines.extend(
        [
            "",
            "## 相关索引",
            "- `wiki/indexes/index.md`",
            "- `wiki/indexes/sources.md`",
            "- `wiki/indexes/concepts.md`",
            "- `wiki/indexes/decisions.md`",
            "- `wiki/indexes/judgments.md`",
            "- `wiki/indexes/judgment-assets.md`",
            "- `wiki/indexes/agent-workbench.md`",
            "- `wiki/indexes/cognitive-history.md`",
            "- `wiki/indexes/output-packs.md`",
            "- `wiki/indexes/domain-pilots.md`",
            "- `wiki/indexes/protocols.md`",
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
            f"- `schema/protocols/{active_protocol}/index.md`",
            "",
            "## 机器记忆查询计划",
            "",
            "## 相关概念",
        ]
    )
    lines[-2:-2] = machine_memory_query_plan_lines(machine_query)
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
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(active_protocol, "figure")
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "figure",
            "query": question,
            "protocol": active_protocol,
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
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的图表偏置。")
    lines.extend(
        [
            "",
            "## 推荐索引页",
            "- [知识库总索引](../../wiki/indexes/index.md)",
            "- [来源索引](../../wiki/indexes/sources.md)",
            "- [概念索引](../../wiki/indexes/concepts.md)",
            "- [决策索引](../../wiki/indexes/decisions.md)",
            "- [判断索引](../../wiki/indexes/judgments.md)",
            "- [判断资产](../../wiki/indexes/judgment-assets.md)",
            "- [Agent Workbench](../../wiki/indexes/agent-workbench.md)",
            "- [认知历史](../../wiki/indexes/cognitive-history.md)",
            "- [输出 Pack 总览](../../wiki/indexes/output-packs.md)",
            "- [领域 Pilot 总览](../../wiki/indexes/domain-pilots.md)",
            "- [协议总览](../../wiki/indexes/protocols.md)",
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
            f"- [当前协议规则](../../schema/protocols/{active_protocol}/index.md)",
            "",
            "## 机器记忆查询计划",
            "",
            "## 推荐概念",
        ]
    )
    lines[-2:-2] = machine_memory_query_plan_lines(machine_query)
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


@runtime_write_operation
def ask_question(root: Path, question: str, output_format: str, protocol: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    protocol_state = load_protocol_state(root)
    active_protocol = resolve_protocol(root, protocol)
    if active_protocol != protocol_state["active_protocol"]:
        protocol_state = {
            **protocol_state,
            "active_protocol": active_protocol,
        }
    blocked_source_ids = active_archived_material_ids(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    memory = load_machine_memory(root)
    machine_query = build_machine_memory_query(
        memory,
        question,
        protocol=active_protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    ranked_concepts = rank_concepts(
        root,
        question,
        boost_concept_slugs=set(machine_query["ranked_concept_slugs"]),
        protocol=active_protocol,
    )
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids, protocol=active_protocol)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_seed = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "slides":
        directory = root / "output" / "slides"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_slides(question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "figure":
        directory = root / "output" / "figures"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_figure_brief(question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.write_text(content, encoding="utf-8")
    artifact_ref = relative_path(root, destination)
    bridge_evidence_ids = active_corpus_bridge_evidence_ids(
        machine_query,
        [entry["id"] for entry in ranked],
        routing_state=routing_state,
        active_protocol=active_protocol,
        blocked_source_ids=blocked_source_ids,
    )
    active_corpus = upsert_active_corpus(
        root,
        protocol=active_protocol,
        question=question,
        source_ids=[entry["id"] for entry in ranked],
        concept_slugs=[concept["slug"] for concept in ranked_concepts],
        bridge_evidence_ids=bridge_evidence_ids,
        output_ref=artifact_ref,
        changed_at=created_at,
    )
    append_runtime_history(
        root,
        {
            "event_type": "query",
            "occurred_at": created_at,
            "protocol": active_protocol,
            "corpus_id": active_corpus["corpus_id"],
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": question_signature(question),
            "output_format": output_format,
            "output_ref": artifact_ref,
            "source_ids": [entry["id"] for entry in ranked],
            "concept_slugs": [concept["slug"] for concept in ranked_concepts],
            "bridge_evidence_ids": bridge_evidence_ids,
            "touched_component_ids": machine_query.get("touched_component_ids", []),
            "time_focus": str(machine_query.get("time_focus") or ""),
            "archive_recall_hint_ids": [
                str(item.get("entry_id") or "")
                for item in machine_query.get("archive_recall_hints", [])
                if isinstance(item, dict) and item.get("entry_id")
            ],
        },
    )
    refresh_material_state(root, generated_at=created_at, active_protocol=active_protocol)
    refresh_knowledge_lifecycle_state(
        root,
        generated_at=created_at,
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=memory,
    )
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{artifact_ref}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"protocol: `{active_protocol}`",
            f"active_corpus: `{active_corpus['corpus_id']}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"time_focus: `{str(machine_query.get('time_focus') or 'none')}`",
            f"protocol_shard_sources: `{len(machine_query.get('protocol_shard_source_ids', []))}`",
            f"time_shard_sources: `{len(machine_query.get('time_shard_source_ids', []))}`",
            f"archive_recall_hints: `{len(machine_query.get('archive_recall_hints', []))}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
        ],
    )
    return {
        "path": artifact_ref,
        "format": output_format,
        "protocol": active_protocol,
        "active_corpus_id": active_corpus["corpus_id"],
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/agent-workbench.md",
            "wiki/indexes/cognitive-history.md",
            "wiki/indexes/output-packs.md",
            "wiki/indexes/domain-pilots.md",
            "wiki/indexes/protocols.md",
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
            "schema/protocols/index.md",
        ],
        "protocol_pages": protocol_paths(root, active_protocol),
    }


@runtime_write_operation
def file_back(
    root: Path,
    artifact: str,
    title: str | None = None,
    kind: str = "derived",
    protocol: str | None = None,
) -> dict[str, Any]:
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
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    citations = extract_provenance_paths(root, original)
    citation_snapshots = build_citation_snapshots(root, citations)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)
    entry_seed = f"{kind}-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(
            kind,
            default_curated_status(kind),
            filed_at,
            protocol=resolved_protocol,
        )
    frontmatter = render_frontmatter(
        {
            "id": entry_id,
            "kind": kind,
            "status": default_curated_status(kind),
            "title": title or artifact_path.stem,
            "protocol": resolved_protocol,
            "source_files": [artifact_ref],
            "citations": citations,
            "citation_snapshots": citation_snapshots,
            "generated_by": "aiwiki-file-back",
            "last_compiled_at": filed_at,
            "confidence": "medium",
            "reviewed_at": "",
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
        }
    )
    stripped = strip_frontmatter(original).strip()
    body_lines = curated_page_template(
        kind=kind,
        protocol=resolved_protocol,
        title=title or artifact_path.stem,
        artifact_ref=artifact_ref,
        filed_at=filed_at,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
    )
    payload = "\n".join([frontmatter, "", *body_lines]).rstrip() + "\n"
    destination.write_text(payload, encoding="utf-8")
    append_wiki_log(
        root,
        "file-back",
        title or artifact_path.stem,
        [
            f"kind: `{kind}`",
            f"protocol: `{resolved_protocol}`",
            f"from: `{artifact_ref}`",
            f"destination: `{relative_path(root, destination)}`",
        ],
    )
    compile_wiki(root)
    return {"path": relative_path(root, destination), "protocol": resolved_protocol}


def _save_machine_memory_action_records(root: Path, actions: list[dict[str, Any]]) -> None:
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})


@runtime_write_operation
def review_concept_rewrite(
    root: Path,
    slug: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in REWRITE_PROPOSAL_STATUSES:
        raise ValueError(f"Unsupported concept rewrite status: {status}")
    state = load_concept_rewrite_state(root)
    proposals = [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]
    target: dict[str, Any] | None = None
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            target = proposal
            break
    if target is None:
        raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")
    if status == "accepted" and not rewrite_proposal_candidate_is_current(root, target):
        raise RuntimeError("Concept rewrite proposal candidate is stale or invalid. Run run-compile again before accepting.")
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if rewrite_proposal_needs_review(status) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    if status != "applied":
        target["applied_at"] = str(target.get("applied_at") or "")
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    append_wiki_log(
        root,
        "rewrite-review",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"status: `{status}`",
            f"target: `{target.get('target_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": status,
        "reviewed_at": reviewed_at,
        "apply_ready": bool(target.get("apply_ready", False)),
    }


def _validate_rewrite_candidate_markdown(
    candidate_markdown: str,
    slug: str,
    source_signature: str,
    source_pages: list[str],
) -> None:
    frontmatter = parse_frontmatter(candidate_markdown)
    if str(frontmatter.get("id") or "") != f"concept-{slug}":
        raise RuntimeError("Rewrite candidate must preserve the concept id.")
    if str(frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Rewrite candidate must preserve `kind: concept`.")
    if str(frontmatter.get("source_signature") or "") != source_signature:
        raise RuntimeError("Rewrite candidate source_signature no longer matches the target concept.")
    candidate_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(candidate_source_pages, list):
        raise RuntimeError("Rewrite candidate must preserve source_pages.")
    normalized_candidate_sources = [str(item) for item in candidate_source_pages if isinstance(item, str)]
    if normalized_candidate_sources != source_pages:
        raise RuntimeError("Rewrite candidate source_pages no longer match the target concept.")


def rewrite_proposal_candidate_is_current(root: Path, proposal: dict[str, Any]) -> bool:
    slug = str(proposal.get("slug") or "")
    candidate_markdown = str(proposal.get("candidate_markdown") or "")
    if not slug or not candidate_markdown:
        return False
    concept_path = root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        return False
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(proposal.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        return False
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        return False
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    try:
        _validate_rewrite_candidate_markdown(
            candidate_markdown,
            slug,
            expected_source_signature,
            normalized_source_pages,
        )
    except RuntimeError:
        return False
    return True


def rewrite_proposal_is_apply_ready(root: Path, proposal: dict[str, Any]) -> bool:
    return str(proposal.get("status") or "") == "accepted" and rewrite_proposal_candidate_is_current(root, proposal)


def validate_low_risk_action_targets(root: Path, action: dict[str, Any]) -> tuple[str, str]:
    if not bool(action.get("active", True)):
        raise RuntimeError("Machine-memory action is no longer active.")
    source_ids = [str(item) for item in action.get("source_ids", []) if isinstance(item, str)]
    concept_slugs = [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)]
    if not source_ids or not concept_slugs:
        raise RuntimeError("Low-risk link action is missing source_ids or concept_slugs.")
    source_id = source_ids[0]
    concept_slug = concept_slugs[0]
    manifest = sync_manifest_with_raw(root)
    known_source_ids = {str(entry.get("id") or "") for entry in manifest.get("entries", []) if isinstance(entry, dict)}
    if source_id not in known_source_ids:
        raise RuntimeError("Low-risk link action references a source that is no longer in the manifest.")
    primary_path = root / str(action.get("primary_path") or "")
    secondary_path = root / str(action.get("secondary_path") or "")
    if not primary_path.is_file() or primary_path.stem != source_id:
        raise RuntimeError("Low-risk link action primary source page is missing or no longer matches the source id.")
    if not secondary_path.is_file() or secondary_path.stem != concept_slug:
        raise RuntimeError("Low-risk link action secondary concept page is missing or no longer matches the concept slug.")
    primary_frontmatter = parse_frontmatter(primary_path.read_text(encoding="utf-8", errors="replace"))
    secondary_frontmatter = parse_frontmatter(secondary_path.read_text(encoding="utf-8", errors="replace"))
    if str(primary_frontmatter.get("kind") or "") != "source":
        raise RuntimeError("Low-risk link action primary path is not a source page anymore.")
    if str(secondary_frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Low-risk link action secondary path is not a concept page anymore.")
    return source_id, concept_slug


@runtime_write_operation
def apply_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    state = load_concept_rewrite_state(root)
    proposals = [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]
    target: dict[str, Any] | None = None
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            target = proposal
            break
    if target is None:
        raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Concept rewrite proposal must be accepted before apply.")
    candidate_markdown = str(target.get("candidate_markdown") or "")
    if not candidate_markdown:
        raise RuntimeError("Concept rewrite proposal has no candidate markdown to apply.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(target.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        raise RuntimeError("Concept page changed since this rewrite proposal was generated.")
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        current_source_pages = []
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    _validate_rewrite_candidate_markdown(
        candidate_markdown,
        slug,
        expected_source_signature,
        normalized_source_pages,
    )
    concept_path.write_text(candidate_markdown.strip() + "\n", encoding="utf-8")
    applied_at = utc_now()
    target["status"] = "applied"
    target["applied_at"] = applied_at
    target["reviewed_at"] = applied_at
    target["review_note"] = note or "Applied accepted rewrite proposal."
    target["pending_review"] = "false"
    target["apply_ready"] = False
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    append_wiki_log(
        root,
        "rewrite-apply",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"proposal_path: `{target.get('proposal_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "applied",
        "applied_at": applied_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
    }


def refresh_knowledge_lifecycle_runtime(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    manifest = sync_manifest_with_raw(root)
    return refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at or utc_now(),
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=load_machine_memory(root),
    )


@runtime_write_operation
def retire_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    lifecycle = refresh_knowledge_lifecycle_runtime(root)
    current_entry = concept_lifecycle_entry(lifecycle, slug)
    if not current_entry:
        raise RuntimeError(f"Concept lifecycle entry not found: {slug}")
    if current_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus concept cannot transition to retired.")
    if str(current_entry.get("lifecycle_state") or "") == "retired" and current_entry.get("override_active"):
        raise RuntimeError(f"Concept is already retired: {slug}")

    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    retired_at = utc_now()
    path_ref = relative_path(root, path)
    page_id = str(current_entry.get("page_id") or f"concept-{slug}")
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        ):
            entry["active"] = False
            entry["cleared_at"] = retired_at
            entry["cleared_note"] = "Superseded by newer concept lifecycle override."
    override_entries.append(
        {
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "kind": "concept",
            "lifecycle_state": "retired",
            "active": True,
            "operation": "retire",
            "reason_codes": ["manual-retire"],
            "applied_at": retired_at,
            "updated_at": retired_at,
            "note": note or "Concept retired from the active knowledge plane.",
        }
    )
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=retired_at)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": retired_at,
            "operation": "retire",
            "kind": "concept",
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": "retired",
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-retire",
        str(current_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `retired`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or "retired"),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": retired_at,
    }


@runtime_write_operation
def reactivate_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    path_ref = relative_path(root, path)
    target: dict[str, Any] | None = None
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
            and str(entry.get("lifecycle_state") or "") == "retired"
        ):
            target = entry
            break
    if target is None:
        raise RuntimeError(f"No active retired concept override exists for slug: {slug}")
    reactivated_at = utc_now()
    target["active"] = False
    target["reactivated_at"] = reactivated_at
    target["reactivate_note"] = note or "Concept reactivated into heuristic lifecycle routing."
    target["updated_at"] = reactivated_at
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=reactivated_at)
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": reactivated_at,
            "operation": "reactivate",
            "kind": "concept",
            "page_id": str(target.get("page_id") or f"concept-{slug}"),
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": str(final_entry.get("lifecycle_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-reactivate",
        str(final_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `{str(final_entry.get('lifecycle_state') or 'unknown')}`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or ""),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": reactivated_at,
    }


@runtime_write_operation
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


@runtime_write_operation
def apply_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
    bundle_path: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Machine-memory action must be accepted before apply.")
    kind = str(target.get("kind") or "")
    if kind not in LOW_RISK_APPLYABLE_ACTION_KINDS:
        raise RuntimeError("Only low-risk accepted actions support semi-auto apply.")
    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    source_id, concept_slug = validate_low_risk_action_targets(root, target)
    preview_proposals = repair_execution_proposals(root, [target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": action_id,
        "title": str(target.get("title") or action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(target.get("priority") or "medium"),
        "protocol": protocol,
        "summary": str(target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(target.get("primary_path") or ""), str(target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, target),
        "command_hint": str(target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, action_id)),
    }
    bundle = build_execution_bundle(root, proposal, compiled_at=utc_now())
    if dry_run:
        return {
            "id": action_id,
            "dry_run": True,
            "apply_mode": "manual-link-state",
            "status": str(target.get("status") or "accepted"),
            "bundle_path": proposal.get("bundle_path", ""),
            "proposal_path": proposal.get("proposal_path", ""),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }

    selected_bundle_path = (
        root / bundle_path.strip()
        if bundle_path and bundle_path.strip()
        else root / str(proposal.get("bundle_path") or "")
    )
    if not selected_bundle_path.exists():
        raise FileNotFoundError(
            f"Execution bundle not found: {relative_path(root, selected_bundle_path)}. Run compile or apply-action --dry-run first."
        )
    stored_bundle = load_execution_bundle(selected_bundle_path)
    if str(stored_bundle.get("action_id") or "") != action_id:
        raise RuntimeError("Execution bundle action_id does not match the requested action.")
    if str(stored_bundle.get("digest") or "") != execution_bundle_digest(stored_bundle):
        raise RuntimeError("Execution bundle digest is invalid; regenerate the bundle before apply.")
    if str(stored_bundle.get("digest") or "") != str(bundle.get("digest") or ""):
        raise RuntimeError("Execution bundle is stale; re-run compile or apply-action --dry-run before apply.")

    applied_at = utc_now()
    apply_mode = "manual-link-state"
    manual_state = load_manual_link_state(root)
    manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
    if kind == "add-source-concept-link":
        existing = next(
            (
                item
                for item in manual_links
                if str(item.get("source_id") or "") == source_id
                and str(item.get("concept_slug") or "") == concept_slug
                and bool(item.get("active", True))
            ),
            None,
        )
        if existing is None:
            manual_links.append(
                {
                    "source_id": source_id,
                    "concept_slug": concept_slug,
                    "active": True,
                    "created_at": applied_at,
                    "applied_at": applied_at,
                    "origin_action_id": action_id,
                    "note": note or "Applied accepted low-risk repair action.",
                }
            )
        else:
            existing["active"] = True
            existing["applied_at"] = applied_at
            existing["origin_action_id"] = action_id
            existing["note"] = note or str(existing.get("note") or "")
        save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
    else:  # pragma: no cover - guarded by allowlist above
        raise RuntimeError(f"Unsupported apply kind: {kind}")

    receipt = build_execution_receipt(root, target, applied_at=applied_at, note=note, proposal=proposal)
    receipt_path = execution_receipt_path(root, action_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    target["status"] = "resolved"
    target["reviewed_at"] = applied_at
    target["status_updated_at"] = applied_at
    target["review_note"] = note or "Semi-auto apply completed."
    target["pending_review"] = "false"
    target["revisit_after"] = ""
    target["escalate_after"] = ""
    target["aging_state"] = ""
    target["overdue_review"] = "false"
    target["escalation_candidate"] = "false"
    target["last_receipt_path"] = relative_path(root, receipt_path)
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-apply",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"kind: `{kind}`",
            f"apply_mode: `{apply_mode}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": "resolved",
        "applied_at": applied_at,
        "apply_mode": apply_mode,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Machine-memory action has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply receipt can be reverted.")
    if str(receipt.get("action_id") or "") != action_id:
        raise RuntimeError("Execution receipt action_id does not match the requested action.")

    manual_state = load_manual_link_state(root)
    manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
    active_entry: dict[str, Any] | None = None
    for item in manual_links:
        if str(item.get("origin_action_id") or "") != action_id:
            continue
        if bool(item.get("active", True)):
            active_entry = item
            break
    if active_entry is None:
        raise RuntimeError("No active safe-apply state exists for this action.")

    reverted_at = utc_now()
    active_entry["active"] = False
    active_entry["reverted_at"] = reverted_at
    active_entry["revert_note"] = note or "Safe apply reverted."
    save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})

    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_target = {
        **dict(target),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "execution_band": "review-first",
        "reviewed_at": reverted_at,
        "status_updated_at": reverted_at,
        "review_note": note or "Safe apply reverted.",
        "pending_review": "true",
        "last_receipt_path": relative_path(root, receipt_path),
        "command_hint": f'PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id} --status accepted --note "Resume reverted repair."',
        "next_step": "回滚后重新 review，确认是否要再次 accepted 再执行。",
    }
    preview_proposals = repair_execution_proposals(root, [reverted_target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": action_id,
        "title": str(reverted_target.get("title") or action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(reverted_target.get("priority") or "medium"),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "summary": str(reverted_target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(reverted_target.get("primary_path") or ""), str(reverted_target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, reverted_target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, reverted_target),
        "command_hint": str(reverted_target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, action_id)),
    }
    revert_receipt = build_execution_receipt(
        root,
        reverted_target,
        applied_at=reverted_at,
        note=note,
        proposal=proposal,
        operation="revert",
        resulting_status="proposed",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["status"] = str(reverted_target["status"])
    target["reviewed_at"] = str(reverted_target["reviewed_at"])
    target["status_updated_at"] = str(reverted_target["status_updated_at"])
    target["review_note"] = str(reverted_target["review_note"])
    target["pending_review"] = str(reverted_target["pending_review"])
    target["last_receipt_path"] = str(reverted_target["last_receipt_path"])
    revisit_after, escalate_after = schedule_review_windows("action", "proposed", reverted_at)
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-revert",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": "proposed",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def apply_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if (
        wiki_requires_compile(root, manifest["entries"])
        or not material_state_path(root).exists()
        or not archive_candidates_state_path(root).exists()
    ):
        compile_wiki(root)
        manifest = load_manifest(root)

    archive_candidates = load_archive_candidates_state(root)
    material_state = load_material_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    if entry_id in archived_entries:
        raise RuntimeError(f"Material is already archived: {entry_id}")

    candidate = next(
        (
            item
            for item in archive_candidates.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if candidate is None:
        raise FileNotFoundError(f"Archive candidate not found: {entry_id}")
    if str(candidate.get("status") or "") != "ready":
        raise RuntimeError("Only ready archive candidates support apply.")
    if str(candidate.get("recommended_temperature") or "") != "archived":
        raise RuntimeError("Only archive candidates recommending `archived` support apply.")

    material_entry = next(
        (
            item
            for item in material_state.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if material_entry is None:
        raise FileNotFoundError(f"Material state entry not found: {entry_id}")
    if str(material_entry.get("temperature") or "") != "cold":
        raise RuntimeError("Only cold material can transition to archived.")
    if material_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus material cannot transition to archived.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or entry_id)
    source_path = f"wiki/sources/{entry_id}.md"
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    applied_at = utc_now()
    receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    receipt_path = execution_receipt_path(root, material_archive_action_id(entry_id))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    archive_entries = [
        dict(item)
        for item in material_archive_state.get("entries", [])
        if isinstance(item, dict) and str(item.get("entry_id") or "") != entry_id
    ]
    archive_entries.append(
        {
            "entry_id": entry_id,
            "title": title,
            "source_path": source_path,
            "active": True,
            "archived_at": applied_at,
            "reverted_at": "",
            "previous_temperature": "cold",
            "note": note or "",
            "recommended_temperature": "archived",
            "last_receipt_path": relative_path(root, receipt_path),
        }
    )
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-apply",
            "occurred_at": applied_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-apply",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `cold -> archived`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "archived",
        "applied_at": applied_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if wiki_requires_compile(root, manifest["entries"]) or not material_state_path(root).exists():
        compile_wiki(root)
        manifest = load_manifest(root)

    material_archive_state = load_material_archive_state(root)
    archive_entries = [dict(item) for item in material_archive_state.get("entries", []) if isinstance(item, dict)]
    target = next((item for item in archive_entries if str(item.get("entry_id") or "") == entry_id), None)
    if target is None or not bool(target.get("active", False)):
        raise RuntimeError(f"No active archived material exists for entry: {entry_id}")

    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Archived material has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply archive receipt can be reverted.")
    if str(receipt.get("subject_id") or "") != entry_id:
        raise RuntimeError("Execution receipt subject_id does not match the requested entry.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or target.get("title") or entry_id)
    source_path = str(target.get("source_path") or f"wiki/sources/{entry_id}.md")
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_at = utc_now()
    revert_receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=reverted_at,
        note=note,
        operation="revert",
        current_temperature="archived",
        resulting_temperature="cold",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["active"] = False
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Material archive reverted."
    target["last_receipt_path"] = relative_path(root, receipt_path)
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-revert",
            "occurred_at": reverted_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-revert",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `archived -> cold`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "cold",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
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
    revisit_after, escalate_after = schedule_review_windows(
        kind,
        status,
        reviewed_at,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
    )
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
    updated_body = append_review_history_entry(
        updated_body,
        reviewed_at=reviewed_at,
        status=status,
        note=note,
        confidence=confidence if kind == "judgment" else None,
    )
    citations = extract_provenance_paths(root, updated_body)
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = build_citation_snapshots(root, citations)
    target.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n", encoding="utf-8")
    _entry_by_id, path_to_entry_id = entry_lookup_maps(load_manifest(root).get("entries", []))
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    append_runtime_history(
        root,
        {
            "event_type": "review",
            "occurred_at": reviewed_at,
            "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "page_id": str(frontmatter.get("id") or target.stem),
            "page_path": relative_path(root, target),
            "page_kind": kind,
            "status": status,
            "source_ids": source_ids,
        },
    )
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


def repair_execution_proposals(
    root: Path,
    actions: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
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
    protocol_hints = {
        "general": {
            "summary_suffix": "",
            "edits": [],
        },
        "investing": {
            "summary_suffix": " 同时检查 thesis、risk、catalyst 和 invalidation 是否需要同步更新。",
            "edits": [
                "如果涉及公司/赛道概念，明确 bull / bear evidence、catalyst、risk 和 invalidation。",
                "优先保持 company / thesis / valuation / risk factor 的边界清晰。",
            ],
        },
        "research": {
            "summary_suffix": " 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。",
            "edits": [
                "如果涉及研发概念，明确 benchmark、experiment、architecture tradeoff 和 regression risk。",
                "优先把 next experiment 或 validation path 写清楚。",
            ],
        },
        "product": {
            "summary_suffix": " 同时检查 user problem、metric、launch readiness 和 validation gap 是否需要同步更新。",
            "edits": [
                "如果涉及产品概念，明确 user problem、bet、metric impact 和 launch risk。",
                "优先把 next validation 或 rollout checkpoint 写清楚。",
            ],
        },
        "ops": {
            "summary_suffix": " 同时检查 incident timeline、blast radius、mitigation 和 follow-up 是否需要同步更新。",
            "edits": [
                "如果涉及运维概念，明确 incident 状态、根因判断、残余风险和 follow-up。",
                "优先把 owner、rollback path 或 next review window 写清楚。",
            ],
        },
    }
    proposals: list[dict[str, Any]] = []
    for action in actions:
        template = strategy_map.get(str(action.get("kind") or ""), {})
        action_id = str(action.get("id") or "")
        proposal_protocol = str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        hint = protocol_hints.get(proposal_protocol, protocol_hints[DEFAULT_PROTOCOL])
        target_paths = [
            path
            for path in (
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            )
            if path
        ]
        proposal = {
            "id": f"proposal-{action_id}",
            "action_id": action_id,
            "title": str(action.get("title") or ""),
            "priority": str(action.get("priority") or "medium"),
            "status": str(action.get("status") or "proposed"),
            "execution_policy": str(action.get("execution_policy") or "triage"),
            "proposal_kind": str(template.get("kind") or "manual-repair"),
            "risk": str(template.get("risk") or "medium"),
            "summary": (
                str(template.get("summary") or action.get("reason") or "")
                + str(hint.get("summary_suffix") or "")
            ).strip(),
            "target_paths": target_paths,
            "suggested_edits": list(template.get("edits") or [str(action.get("reason") or "检查相关页面并补修复说明。")])
            + list(hint.get("edits") or []),
            "command_hint": str(action.get("command_hint") or ""),
            "next_step": str(action.get("next_step") or ""),
            "protocol": proposal_protocol,
            "focus_score": int(action.get("focus_score", 0)),
        }
        proposal["page_patch_plan"] = build_page_patch_plan(root, action, active_protocol=proposal_protocol)
        proposal["proposal_path"] = relative_path(root, execution_proposal_path(root, action_id))
        proposal["bundle_path"] = relative_path(root, execution_bundle_path(root, action_id))
        proposal["safe_apply_preview"] = safe_apply_preview(root, action)
        proposals.append(proposal)
    proposals.sort(
        key=lambda item: (
            action_status_rank(item["status"]),
            -int(item.get("focus_score", 0)),
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
            "source_signature": str(node.get("source_signature") or ""),
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
                    "source_signature": record.get("source_signature", ""),
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
    all_concepts = sorted(
        concept_records.values(),
        key=lambda item: (-int(item.get("score", 0)), item.get("title", "").lower()),
    )
    return {
        "all_concepts": all_concepts,
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


@runtime_write_operation
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
        "wiki/indexes/judgment-assets.md": "Missing judgment asset dashboard page.",
        "wiki/indexes/agent-workbench.md": "Missing agent workbench page.",
        "wiki/indexes/cognitive-history.md": "Missing cognitive history page.",
        "wiki/indexes/output-packs.md": "Missing output packs index page.",
        "wiki/indexes/domain-pilots.md": "Missing domain pilots index page.",
        "wiki/indexes/rewrite-proposals.md": "Missing rewrite proposal index page.",
        "wiki/indexes/protocols.md": "Missing protocol dashboard page.",
        "wiki/indexes/furnace-center.md": "Missing furnace center page.",
        "wiki/indexes/execution-center.md": "Missing execution center page.",
        "wiki/indexes/execution-audit.md": "Missing execution audit page.",
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
        "schema/protocols/index.md": "Missing protocol schema index.",
    }
    for relative, message in required_schema.items():
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, message))

    protocol_state = load_protocol_state(root)
    for relative in protocol_paths(root, protocol_state["active_protocol"]):
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, f"Missing active protocol rule file: `{relative}`."))

    decision_pages = collect_curated_pages(root, "decisions", "decision")
    judgment_pages = collect_curated_pages(root, "judgments", "judgment")
    pack_memory: dict[str, Any] = {}
    if machine_memory_state_path(root).exists():
        pack_memory = load_machine_memory(root)
    expected_output_packs = build_output_packs(
        root,
        decision_pages,
        judgment_pages,
        pack_memory,
        protocol_state,
        collect_recent_output_artifacts(root),
        utc_now(),
    )
    execution_audit_snapshot = build_execution_audit_snapshot(
        root,
        pack_memory,
        active_protocol=protocol_state["active_protocol"],
    ) if pack_memory else {"protocols": [], "counts": {}, "recent_apply": [], "recent_revert": []}
    expected_domain_pilots = build_domain_pilots(
        root,
        decision_pages,
        judgment_pages,
        pack_memory,
        protocol_state,
        collect_recent_output_artifacts(root),
        collect_output_density_artifacts(root),
        expected_output_packs,
        execution_audit_snapshot,
        utc_now(),
    )

    memory_state = machine_memory_state_path(root)
    graph_html = machine_memory_graph_html_path(root)
    furnace_html = furnace_center_html_path(root)
    execution_html = execution_center_html_path(root)
    execution_audit_html = execution_audit_html_path(root)
    review_html = review_center_html_path(root)
    if manifest["entries"] and not memory_state.exists():
        findings.append(Finding("error", relative_path(root, memory_state), "Missing machine memory state file."))
    if manifest["entries"] and not graph_html.exists():
        findings.append(Finding("error", relative_path(root, graph_html), "Missing machine memory graph HTML view."))
    if manifest["entries"] and not furnace_html.exists():
        findings.append(Finding("error", relative_path(root, furnace_html), "Missing furnace center HTML view."))
    if manifest["entries"] and not execution_html.exists():
        findings.append(Finding("error", relative_path(root, execution_html), "Missing execution center HTML view."))
    if manifest["entries"] and not execution_audit_html.exists():
        findings.append(Finding("error", relative_path(root, execution_audit_html), "Missing execution audit HTML view."))
    if manifest["entries"] and not review_html.exists():
        findings.append(Finding("error", relative_path(root, review_html), "Missing review center HTML view."))
    for pack_group in ("review_packs", "decision_memos", "sop_drafts"):
        for pack in expected_output_packs.get(pack_group, []):
            pack_path = root / str(pack.get("path") or "")
            if not pack_path.exists():
                findings.append(
                    Finding(
                        "error",
                        relative_path(root, pack_path),
                        f"Missing output pack `{pack_path.name}` for `{pack_group}`.",
                    )
                )
    for scorecard in expected_domain_pilots.get("scorecards", []):
        scorecard_path = root / str(scorecard.get("path") or "")
        if not scorecard_path.exists():
            findings.append(
                Finding(
                    "error",
                    relative_path(root, scorecard_path),
                    f"Missing domain pilot scorecard `{scorecard_path.name}`.",
                )
            )
    if manifest["entries"]:
        for pack in AGENT_PACK_LIBRARY:
            pack_path = agent_pack_path(root, str(pack["role"]))
            if not pack_path.exists():
                findings.append(
                    Finding("error", relative_path(root, pack_path), f"Missing agent pack for role `{pack['role']}`.")
                )
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
            repair_plan = memory.get("health", {}).get("repair_plan", {}) if isinstance(memory, dict) else {}
            execution_proposals = repair_plan.get("execution_proposals", []) if isinstance(repair_plan, dict) else []
            for proposal in execution_proposals:
                if not isinstance(proposal, dict):
                    continue
                action_id = str(proposal.get("action_id") or "")
                proposal_path = root / str(proposal.get("proposal_path") or relative_path(root, execution_proposal_path(root, action_id)))
                if action_id and not proposal_path.exists():
                    findings.append(
                        Finding("error", relative_path(root, proposal_path), f"Missing execution proposal page for action `{action_id}`.")
                    )
                bundle_path = root / str(proposal.get("bundle_path") or relative_path(root, execution_bundle_path(root, action_id)))
                if action_id and not bundle_path.exists():
                    findings.append(
                        Finding("error", relative_path(root, bundle_path), f"Missing execution bundle for action `{action_id}`.")
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
        else:
            for action in action_state.get("actions", []):
                if not isinstance(action, dict):
                    continue
                receipt_path = str(action.get("last_receipt_path") or "")
                if receipt_path and not (root / receipt_path).exists():
                    findings.append(
                        Finding(
                            "error",
                            receipt_path,
                            f"Referenced execution receipt does not exist for action `{action.get('id', '')}`.",
                        )
                    )
            consistency_signals = collect_execution_consistency_signals(
                root,
                [dict(action) for action in action_state.get("actions", []) if isinstance(action, dict)],
                load_execution_receipt_history(root),
            )
            for signal in consistency_signals:
                findings.append(
                    Finding(
                        str(signal.get("severity") or "warn"),
                        str(signal.get("path") or relative_path(root, action_state_path)),
                        f"Execution consistency issue for action `{signal.get('action_id', '')}`: {signal.get('message', '')}",
                    )
                )

    rewrite_state_path = concept_rewrite_state_path(root)
    if manifest["entries"] and not rewrite_state_path.exists():
        findings.append(
            Finding("warn", relative_path(root, rewrite_state_path), "Concept rewrite proposal state file has not been initialized.")
        )
    elif rewrite_state_path.exists():
        rewrite_state = load_json_document(rewrite_state_path)
        proposals = rewrite_state.get("proposals") if isinstance(rewrite_state, dict) else None
        if not isinstance(proposals, list):
            findings.append(
                Finding("error", relative_path(root, rewrite_state_path), "Concept rewrite proposal state is not valid JSON.")
            )
        else:
            for proposal in proposals:
                if not isinstance(proposal, dict):
                    continue
                slug = str(proposal.get("slug") or "")
                proposal_path = root / str(proposal.get("proposal_path") or f"wiki/rewrite-proposals/{slug}.md")
                if slug and not proposal_path.exists():
                    findings.append(
                        Finding("error", relative_path(root, proposal_path), f"Missing rewrite proposal page for concept `{slug}`.")
                    )
                target_path = root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
                if slug and not target_path.exists():
                    findings.append(
                        Finding("error", relative_path(root, target_path), f"Rewrite proposal target concept page is missing: `{slug}`.")
                    )
                if proposal.get("apply_ready") and not proposal.get("candidate_markdown"):
                    findings.append(
                        Finding("error", relative_path(root, proposal_path), "Rewrite proposal is marked apply_ready but has no candidate markdown.")
                    )
                if proposal.get("apply_ready") and not rewrite_proposal_is_apply_ready(root, proposal):
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, proposal_path),
                            "Rewrite proposal is marked apply_ready but no longer matches the current concept sources.",
                        )
                    )

    knowledge_state_path = knowledge_lifecycle_state_path(root)
    concept_pages = sorted((root / "wiki" / "concepts").glob("*.md"))
    expected_lifecycle_paths = {page["path"] for page in decision_pages + judgment_pages} | {
        relative_path(root, path) for path in concept_pages
    }
    if expected_lifecycle_paths and not knowledge_state_path.exists():
        findings.append(Finding("error", relative_path(root, knowledge_state_path), "Missing knowledge lifecycle state file."))
    elif knowledge_state_path.exists():
        knowledge_state = load_json_document(knowledge_state_path)
        lifecycle_entries = knowledge_state.get("entries") if isinstance(knowledge_state, dict) else None
        if not isinstance(lifecycle_entries, list):
            findings.append(
                Finding("error", relative_path(root, knowledge_state_path), "Knowledge lifecycle state is not valid JSON.")
            )
        else:
            if expected_lifecycle_paths and len(lifecycle_entries) != len(expected_lifecycle_paths):
                findings.append(
                    Finding(
                        "warn",
                        relative_path(root, knowledge_state_path),
                        f"Knowledge lifecycle state entry count `{len(lifecycle_entries)}` does not match curated page count `{len(expected_lifecycle_paths)}`.",
                    )
                )
            for entry in lifecycle_entries:
                if not isinstance(entry, dict):
                    continue
                page_id = str(entry.get("page_id") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                source_ids = entry.get("source_ids")
                active_corpus_ids = entry.get("active_corpus_ids")
                invalidation_signals = entry.get("invalidation_signals")
                if not page_id:
                    findings.append(
                        Finding("error", relative_path(root, knowledge_state_path), "Knowledge lifecycle entry is missing `page_id`.")
                    )
                if kind not in set(KNOWLEDGE_LIFECYCLE_KINDS):
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_state_path),
                            f"Knowledge lifecycle entry has unsupported kind `{kind or 'unknown'}`.",
                        )
                    )
                if lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_state_path),
                            f"Knowledge lifecycle entry has unsupported state `{lifecycle_state or 'unknown'}`.",
                        )
                    )
                if not path:
                    findings.append(
                        Finding("error", relative_path(root, knowledge_state_path), "Knowledge lifecycle entry is missing `path`.")
                    )
                elif not (root / path).exists():
                    findings.append(
                        Finding("error", relative_path(root, knowledge_state_path), f"Knowledge lifecycle entry references missing page `{path}`.")
                    )
                elif expected_lifecycle_paths and path not in expected_lifecycle_paths:
                    findings.append(
                        Finding(
                            "warn",
                            relative_path(root, knowledge_state_path),
                            f"Knowledge lifecycle entry references unmanaged page `{path}`.",
                        )
                    )
                if not isinstance(source_ids, list):
                    findings.append(
                        Finding("error", relative_path(root, knowledge_state_path), "Knowledge lifecycle entry `source_ids` is not a list.")
                    )
                if not isinstance(active_corpus_ids, list):
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_state_path),
                            "Knowledge lifecycle entry `active_corpus_ids` is not a list.",
                        )
                    )
                if not isinstance(invalidation_signals, list):
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_state_path),
                            "Knowledge lifecycle entry `invalidation_signals` is not a list.",
                        )
                    )
                if kind == "concept":
                    if not isinstance(entry.get("issues"), list):
                        findings.append(
                            Finding("error", relative_path(root, knowledge_state_path), "Concept lifecycle entry `issues` is not a list.")
                        )
                    if not isinstance(entry.get("review_signal_codes"), list):
                        findings.append(
                            Finding(
                                "error",
                                relative_path(root, knowledge_state_path),
                                "Concept lifecycle entry `review_signal_codes` is not a list.",
                            )
                        )
                    if not isinstance(entry.get("source_pages"), list):
                        findings.append(
                            Finding(
                                "error",
                                relative_path(root, knowledge_state_path),
                                "Concept lifecycle entry `source_pages` is not a list.",
                            )
                        )
                    if not str(entry.get("quality_state") or ""):
                        findings.append(
                            Finding(
                                "warn",
                                relative_path(root, knowledge_state_path),
                                f"Concept lifecycle entry `{page_id}` is missing `quality_state`.",
                            )
                        )
                    if not isinstance(entry.get("override_reason_codes", []), list):
                        findings.append(
                            Finding(
                                "error",
                                relative_path(root, knowledge_state_path),
                                "Concept lifecycle entry `override_reason_codes` is not a list.",
                            )
                        )
                    override_state = str(entry.get("override_state") or "")
                    if override_state and override_state not in KNOWLEDGE_LIFECYCLE_STATES:
                        findings.append(
                            Finding(
                                "error",
                                relative_path(root, knowledge_state_path),
                                f"Concept lifecycle entry `{page_id}` has unsupported override state `{override_state}`.",
                            )
                        )
                    if not isinstance(entry.get("override_active"), bool):
                        findings.append(
                            Finding(
                                "error",
                                relative_path(root, knowledge_state_path),
                                "Concept lifecycle entry `override_active` is not a bool.",
                            )
                        )

    knowledge_override_path = knowledge_lifecycle_override_state_path(root)
    if concept_pages and not knowledge_override_path.exists():
        findings.append(
            Finding("error", relative_path(root, knowledge_override_path), "Missing knowledge lifecycle override state file.")
        )
    elif knowledge_override_path.exists():
        override_state = load_json_document(knowledge_override_path)
        override_entries = override_state.get("entries") if isinstance(override_state, dict) else None
        if not isinstance(override_entries, list):
            findings.append(
                Finding(
                    "error",
                    relative_path(root, knowledge_override_path),
                    "Knowledge lifecycle override state is not valid JSON.",
                )
            )
        else:
            active_override_paths: dict[str, int] = {}
            for entry in override_entries:
                if not isinstance(entry, dict):
                    continue
                slug = str(entry.get("slug") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                if not slug:
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            "Knowledge lifecycle override entry is missing `slug`.",
                        )
                    )
                if kind and kind != "concept":
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            f"Knowledge lifecycle override entry has unsupported kind `{kind}`.",
                        )
                    )
                if lifecycle_state and lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            f"Knowledge lifecycle override entry has unsupported state `{lifecycle_state}`.",
                        )
                    )
                if not isinstance(entry.get("active"), bool):
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            "Knowledge lifecycle override entry `active` is not a bool.",
                        )
                    )
                if not path:
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            "Knowledge lifecycle override entry is missing `path`.",
                        )
                    )
                elif not (root / path).exists():
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            f"Knowledge lifecycle override entry references missing page `{path}`.",
                        )
                    )
                if bool(entry.get("active")):
                    active_override_paths[path] = active_override_paths.get(path, 0) + 1
                    if lifecycle_state != "retired":
                        findings.append(
                            Finding(
                                "warn",
                                relative_path(root, knowledge_override_path),
                                f"Active concept lifecycle override for `{slug or path}` is `{lifecycle_state or 'unknown'}`; current workflow expects `retired`.",
                            )
                        )
            for path, count in active_override_paths.items():
                if path and count > 1:
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, knowledge_override_path),
                            f"Multiple active knowledge lifecycle overrides reference `{path}`.",
                        )
                    )

    if manifest["entries"] and not concept_pages:
        findings.append(Finding("warn", "wiki/concepts", "No concept pages have been compiled yet."))

    for page in concept_pages:
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "concept":
            findings.append(Finding("warn", relative_path(root, page), "Concept page kind is missing or incorrect."))
        if concept_summary_is_placeholder(content):
            findings.append(Finding("warn", relative_path(root, page), "Concept page still contains the fallback summary."))
        for section in ("## Conflict Signals", "## Evidence Gaps"):
            if section not in content:
                findings.append(
                    Finding("warn", relative_path(root, page), f"Concept page is missing section `{section}`.")
                )
        source_pages = frontmatter.get("source_pages", [])
        if not source_pages:
            findings.append(Finding("warn", relative_path(root, page), "Concept page has no source-page references."))
        for source_page in source_pages:
            candidate = root / source_page
            if not candidate.exists():
                findings.append(
                    Finding("error", relative_path(root, page), f"Concept page references missing source page: `{source_page}`.")
                )

    for group, expected_kind, pages in (
        ("wiki/derived", "derived", None),
        ("wiki/decisions", "decision", decision_pages),
        ("wiki/judgments", "judgment", judgment_pages),
    ):
        for page in sorted((root / group).glob("*.md")):
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            citations = [
                str(path)
                for path in frontmatter.get("citations", [])
                if isinstance(path, str) and path.strip()
            ]
            citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
            if frontmatter.get("kind") != expected_kind:
                findings.append(
                    Finding("warn", relative_path(root, page), f"{expected_kind.capitalize()} page kind is missing or incorrect.")
                )
            if "wiki/sources/" not in content and "raw/" not in content:
                findings.append(
                    Finding("warn", relative_path(root, page), f"{expected_kind.capitalize()} page has no explicit source-page reference.")
                )
            if expected_kind in {"derived", "decision", "judgment"} and not citations:
                findings.append(
                    Finding(
                        "warn",
                        relative_path(root, page),
                        f"{expected_kind.capitalize()} page is missing structured `citations` metadata.",
                    )
                )
            if expected_kind in {"derived", "decision", "judgment"} and citations and not frontmatter.get("citation_snapshots"):
                findings.append(
                    Finding(
                        "warn",
                        relative_path(root, page),
                        f"{expected_kind.capitalize()} page is missing `citation_snapshots` metadata.",
                    )
                )
            for citation in citations:
                candidate = root / citation
                if not candidate.exists():
                    findings.append(
                        Finding(
                            "error",
                            relative_path(root, page),
                            f"{expected_kind.capitalize()} page references missing citation path: `{citation}`.",
                        )
                    )
            if expected_kind in {"decision", "judgment"} and (
                citation_snapshot_state["missing"] or citation_snapshot_state["stale"]
            ):
                findings.append(
                    Finding(
                        "warn",
                        relative_path(root, page),
                        f"{expected_kind.capitalize()} page has citation snapshot gaps: missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                    )
                )
            if expected_kind in {"decision", "judgment"} and not frontmatter.get("protocol"):
                findings.append(
                    Finding("warn", relative_path(root, page), f"{expected_kind.capitalize()} page is missing explicit `protocol` metadata.")
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
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Decision page is missing section `## {heading}`.")
                        )
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"approved", "needs-revisit", "superseded"}
                        and not snapshot["meaningful"]
                    ):
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Decision page still has placeholder `{heading}` content.")
                        )
                    elif heading == "Review History" and frontmatter.get("reviewed_at") and not snapshot["meaningful"]:
                        findings.append(
                            Finding("warn", relative_path(root, page), "Decision page is reviewed but has no populated `Review History`.")
                        )
                if frontmatter.get("status") in {"approved", "needs-revisit", "superseded"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    findings.append(
                        Finding("warn", relative_path(root, page), "Reviewed decision page is missing `reviewed_at`."),
                    )
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    findings.append(
                        Finding(
                            "warn",
                            relative_path(root, page),
                            f"Reviewed decision page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                        )
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
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Judgment page is missing section `## {heading}`.")
                        )
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"tracking", "confirmed", "rejected"}
                        and not snapshot["meaningful"]
                    ):
                        findings.append(
                            Finding("warn", relative_path(root, page), f"Judgment page still has placeholder `{heading}` content.")
                        )
                    elif heading == "Review History" and frontmatter.get("reviewed_at") and not snapshot["meaningful"]:
                        findings.append(
                            Finding("warn", relative_path(root, page), "Judgment page is reviewed but has no populated `Review History`.")
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
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    findings.append(
                        Finding(
                            "warn",
                            relative_path(root, page),
                            f"Reviewed judgment page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                        )
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
    active_protocol: str,
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
    rewrite_state = health.get("concept_rewrite", {})
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    apply_ready_actions = [action for action in actions if action_supports_low_risk_apply(action)]
    execution_proposals = repair_plan.get("execution_proposals", [])
    promotions = promotion_result.get("pages", [])
    lines = [
        "# 修复待办",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
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
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审 Rewrite：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用 Rewrite：`{len(apply_ready_rewrites)}`",
        f"- 可安全执行动作：`{len(apply_ready_actions)}`",
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
    if PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly"):
        lines.extend(["### 协议 Nightly 焦点"])
        for focus in PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly", []):
            lines.append(f"- {focus}")
        lines.append("")
    if error_findings:
        lines.append(f"1. 先解决 `{len(error_findings)}` 个 lint 错误，再继续依赖下游输出。")
    if pending_sources:
        lines.append(f"2. 补齐 `{len(pending_sources)}` 个仍是占位摘要的来源页。")
    if placeholder_concepts:
        lines.append(f"3. 重写 `{len(placeholder_concepts)}` 个仍使用回退摘要的概念页。")
    if concept_quality.get("counts", {}).get("weak", 0):
        lines.append(f"3a. 按概念质量看板优先处理 `{concept_quality.get('counts', {}).get('weak', 0)}` 个弱概念页。")
    if rewrite_state.get("counts", {}).get("pending_review", 0):
        lines.append(f"3b. 先审 `{rewrite_state.get('counts', {}).get('pending_review', 0)}` 个 concept rewrite proposal。")
    if apply_ready_rewrites:
        lines.append(f"3c. 应用 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal，让概念页先收敛。")
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
    if apply_ready_actions:
        lines.append(f"9c. 其中 `{len(apply_ready_actions)}` 个低风险动作可直接走 `apply-action` 半自动执行。")
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
    if rewrite_proposals:
        lines.append("")
        lines.append("### Rewrite Proposals")
        for proposal in rewrite_proposals[:8]:
            command = (
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}"
                if proposal.get("apply_ready")
                else f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite {proposal['slug']} --status accepted"
            )
            lines.append(
                f"- `{proposal['target_path']}` | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | strategy `{proposal.get('rewrite_strategy', 'n/a')}` | command `{command}`"
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
    if apply_ready_actions:
        lines.append("")
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['id']}` | `{action['title']}`"
                f" | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
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
            "- 认知历史：`wiki/indexes/cognitive-history.md`",
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


@runtime_write_operation
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
    protocol_state = load_protocol_state(root)
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    generated_at = utc_now()
    active_corpora_before = load_active_corpora_state(root)
    previous_status_by_corpus = {
        str(corpus.get("corpus_id") or ""): str(corpus.get("status") or "")
        for corpus in active_corpora_before.get("corpora", [])
        if corpus.get("corpus_id")
    }
    active_corpora_state = reconcile_active_corpora_state(root, changed_at=generated_at, nightly_cooldown=True)
    active_corpora = active_corpora_state["corpora"]
    cooled_corpus_ids = [
        str(corpus.get("corpus_id") or "")
        for corpus in active_corpora
        if str(corpus.get("status") or "") == "cooling"
        and previous_status_by_corpus.get(str(corpus.get("corpus_id") or "")) == "active"
    ]
    expired_corpus_ids = [
        str(corpus.get("corpus_id") or "")
        for corpus in active_corpora
        if str(corpus.get("status") or "") == "expired"
        and previous_status_by_corpus.get(str(corpus.get("corpus_id") or "")) != "expired"
    ]
    append_runtime_history(
        root,
        {
            "event_type": "nightly",
            "occurred_at": generated_at,
            "protocol": protocol_state["active_protocol"],
            "cooled_corpus_ids": cooled_corpus_ids,
            "expired_corpus_ids": expired_corpus_ids,
            "active_corpus_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "active"
            ],
        },
    )
    material_state = refresh_material_state(
        root,
        generated_at=generated_at,
        entries=manifest["entries"],
        active_protocol=protocol_state["active_protocol"],
    )
    material_routing = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    knowledge_lifecycle = refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=manifest["entries"],
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=protocol_state["active_protocol"],
    )
    state = {
        "generated_at": generated_at,
        "llm_used": llm_used,
        "protocol": {
            "active_protocol": protocol_state["active_protocol"],
            "state_path": protocol_state["state_path"],
            "available_protocols": protocol_state["available_protocols"],
            "dashboard_path": "wiki/indexes/protocols.md",
            "review_focus": PROTOCOL_LIBRARY.get(protocol_state["active_protocol"], {}).get("review", []),
            "nightly_focus": PROTOCOL_LIBRARY.get(protocol_state["active_protocol"], {}).get("nightly", []),
        },
        "compile": compile_result,
        "lint": {
            "path": lint_result["path"],
            "counts": lint_result["counts"],
        },
        "semantic_report": semantic_report,
        "material_state": {
            "path": relative_path(root, material_state_path(root)),
            "entry_count": len(material_state["entries"]),
        },
        "material_routing": {
            "path": relative_path(root, material_routing_state_path(root)),
            "entry_count": len(material_routing.get("entries", [])),
            "active_protocol": material_routing.get("active_protocol", protocol_state["active_protocol"]),
        },
        "archive_candidates": {
            "path": relative_path(root, archive_candidates_state_path(root)),
            "entry_count": len(archive_candidates.get("entries", [])),
            "ready_ids": [
                str(entry.get("entry_id") or "")
                for entry in archive_candidates.get("entries", [])
                if str(entry.get("status") or "") == "ready"
            ],
            "deferred_ids": [
                str(entry.get("entry_id") or "")
                for entry in archive_candidates.get("entries", [])
                if str(entry.get("status") or "") == "deferred"
            ],
        },
        "active_corpora": {
            "path": relative_path(root, active_corpora_state_path(root)),
            "count": len(active_corpora),
            "active_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "active"
            ],
            "cooling_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "cooling"
            ],
            "expired_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "expired"
            ],
        },
        "knowledge_lifecycle": {
            "path": relative_path(root, knowledge_lifecycle_state_path(root)),
            "overrides_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
            "entry_count": len(knowledge_lifecycle.get("entries", [])),
            "state_counts": dict(knowledge_lifecycle.get("counts", {}).get("by_state", {})),
            "kind_counts": dict(knowledge_lifecycle.get("counts", {}).get("by_kind", {})),
            "invalidated_page_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if entry.get("invalidation_signals")
            ],
            "active_page_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("lifecycle_state") or "") == "active"
            ],
            "active_concept_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("kind") or "") == "concept"
                and entry.get("active_corpus_ids")
            ],
            "retired_concept_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("kind") or "") == "concept"
                and str(entry.get("lifecycle_state") or "") == "retired"
            ],
            "governance_summary": {
                "concept_backlog_count": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
                "review_concept_count": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
                "revisit_concept_count": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
                "retired_concept_count": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
                "concept_backlog_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("concept_backlog", [])
                ],
                "review_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("review_concepts", [])
                ],
                "revisit_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("revisit_concepts", [])
                ],
                "retired_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("retired_concepts", [])
                ],
            },
        },
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
        "concept_rewrite": {
            "path": relative_path(root, concept_rewrite_index_path(root)),
            "state_path": memory.get("health", {}).get("concept_rewrite", {}).get("state_path", ".aiwiki/state/concept-rewrite-proposals.json"),
            "pending_review_slugs": [
                proposal["slug"]
                for proposal in memory.get("health", {}).get("concept_rewrite", {}).get("proposals", [])
                if proposal.get("pending_review") == "true"
            ],
            "apply_ready_slugs": [
                proposal["slug"]
                for proposal in memory.get("health", {}).get("concept_rewrite", {}).get("proposals", [])
                if proposal.get("apply_ready")
            ],
            "active_count": memory.get("health", {}).get("concept_rewrite", {}).get("counts", {}).get("active", 0),
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
        protocol_state["active_protocol"],
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
            f"cooled_active_corpora: `{len(cooled_corpus_ids)}`",
            f"expired_active_corpora: `{len(expired_corpus_ids)}`",
            f"archive_candidates: `{len(archive_candidates.get('entries', []))}`",
            f"knowledge_lifecycle_entries: `{len(knowledge_lifecycle.get('entries', []))}`",
            f"auto_promotions: `{promotion_result.get('count', 0)}`",
            f"weak_concepts: `{memory.get('health', {}).get('concept_quality', {}).get('counts', {}).get('weak', 0)}`",
            f"machine_memory_actions: `{memory.get('health', {}).get('action_counts', {}).get('total', 0)}`",
            f"ready_machine_memory_actions: `{memory.get('health', {}).get('repair_plan', {}).get('counts', {}).get('ready', 0)}`",
            f"repair_backlog: `{relative_path(root, repair_backlog_path(root))}`",
        ],
    )
    return state


@runtime_write_operation
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


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)
