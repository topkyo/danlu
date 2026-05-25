"""Protocol runtime configuration constants."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

PROTOCOL_ELIXIR_REVIEW_DAYS: dict[str, int] = {
    # P4-INV-4 (Round 59): default `review_after` window for settled elixirs,
    # by protocol. Investing has the fastest rhythm because catalysts /
    # invalidation triggers tend to resolve in 1-2 quarters; ops is the
    # fastest because operational decisions are rechecked weekly.
    "general": 90,
    "investing": 60,
    "research": 90,
    "product": 60,
    "ops": 30,
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


CONCEPT_HARDNESS_LEVELS = ("soft", "medium", "hard")


CAUSAL_RELATION_TYPES = ("causes", "enables", "constrains", "conflicts_with")


LOW_RISK_APPLYABLE_ACTION_KINDS = {"add-source-concept-link", "refresh-citation-snapshots"}

# Monitoring action kinds that can be resolved with an acknowledge-and-close preview.
RESOLVABLE_MONITOR_ACTION_KINDS = {
    "monitor-bridge-concept",
    "split-overloaded-concept",
    "expand-singleton-concept",
    "connect-isolated-source",
}


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
