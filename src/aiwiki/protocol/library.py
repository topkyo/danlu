"""Static protocol library definitions extracted from app_protocol."""

from __future__ import annotations

from typing import Any

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

PROTOCOL_JUDGMENT_EXTRA_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "investing": {
        "judgment": {
            "thesis": "",
            "catalyst": [],
            "risk": [],
            "invalidation_threshold": "",
        },
        "decision": {
            "thesis": "",
            "position_change": "",
            "sizing_rationale": "",
            "invalidation_threshold": "",
        },
    },
    "research": {
        "judgment": {
            "hypothesis": "",
            "falsification": "",
            "experiment_refs": [],
        },
    },
    "product": {
        "judgment": {
            "user_value_claim": "",
            "kill_metric": "",
        },
    },
    "ops": {
        "judgment": {
            "runbook_ref": "",
            "blast_radius": "",
        },
    },
    "general": {},
}


def protocol_judgment_extra_fields(protocol: str, kind: str) -> dict[str, Any]:
    """Return a fresh copy of protocol-specific frontmatter slots for a kind."""

    protocol_map = PROTOCOL_JUDGMENT_EXTRA_FIELDS.get(protocol, {})
    fields = protocol_map.get(kind, {})
    return {key: (list(value) if isinstance(value, list) else value) for key, value in fields.items()}


__all__ = [
    "PROTOCOL_JUDGMENT_EXTRA_FIELDS",
    "PROTOCOL_LIBRARY",
    "protocol_judgment_extra_fields",
]
