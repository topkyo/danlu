"""Protocol runtime configuration constants."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from ..state.constants import DEFAULT_PROTOCOL

PROTOCOL_ELIXIR_REVIEW_DAYS: dict[str, int] = {
    "general": 90,
}


PROTOCOL_REVIEW_WINDOWS: dict[str, dict[tuple[str, str], tuple[int, int]]] = {
    "general": {},
}


PROTOCOL_CLASSIFICATION_MARKERS: dict[str, dict[str, tuple[str, ...]]] = {
    "general": {"decision": (), "judgment": ()},
}


PROTOCOL_PROMOTION_PREFIXES: dict[str, dict[str, str]] = {
    "general": {"decision": "决策沉淀", "judgment": "判断沉淀"},
}


PROTOCOL_FOCUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "general": (),
}


PROTOCOL_ACTION_KIND_WEIGHTS: dict[str, dict[str, int]] = {
    "general": {},
}


PROTOCOL_OUTPUT_GUIDANCE: dict[str, dict[str, tuple[str, ...]]] = {
    "general": {
        "report": (
            "先重述问题，再列证据、分歧、缺口和下一步问题。",
            "不要把猜测写成事实。",
        ),
        "decision-memo": ("优先组织成结论、证据、反证、失效条件和下一次复核信号。",),
        "sop": ("优先组织成前置检查、步骤、风险控制、回滚和复盘记录。",),
        "slides": ("每页都保留引用和关键不确定性。",),
        "figure": ("图表应强调变量关系、假设和证据边界。",),
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
}


PROTOCOL_QUERY_ROUTE_CONFIG: dict[str, dict[str, Any]] = {
    "general": {
        "default_strategy": "concept-first",
        "strategy_order": ("concept-first", "graph-walk", "source-first"),
        "source_markers": ("source", "citation", "quote", "file", "raw", "证据", "引用", "来源", "原文"),
        "graph_markers": (
            "why",
            "how",
            "impact",
            "dependency",
            "relationship",
            "root cause",
            "为什么",
            "因果",
            "关系",
            "根因",
        ),
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


def protocol_output_guidance(root: Path, protocol: str, output_format: str) -> tuple[str, ...]:
    from .runtime_schema import default_protocol_runtime_schema, load_protocol_runtime_schema

    default_guidance = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("output_guidance", {})
    protocol_guidance = load_protocol_runtime_schema(root, protocol).get("output_guidance", default_guidance)
    if not isinstance(default_guidance, dict):
        default_guidance = {}
    if not isinstance(protocol_guidance, dict):
        protocol_guidance = default_guidance
    return tuple(protocol_guidance.get(output_format, default_guidance.get(output_format, ())))


def protocol_execution_policy_rule(root: Path, protocol: str, action_kind: str) -> dict[str, Any]:
    from .runtime_schema import default_protocol_runtime_schema, load_protocol_runtime_schema

    default_rules = (
        default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("execution_policy", {}).get("accepted_rules", {})
    )
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
    from .runtime_schema import default_protocol_runtime_schema, load_protocol_runtime_schema

    default_config = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("query_routes", {})
    protocol_config = load_protocol_runtime_schema(root, protocol).get("query_routes", default_config)
    if not isinstance(default_config, dict):
        default_config = {}
    if not isinstance(protocol_config, dict):
        protocol_config = default_config
    return {
        "default_strategy": str(
            protocol_config.get("default_strategy") or default_config.get("default_strategy") or "concept-first"
        ),
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
