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
}

PROTOCOL_JUDGMENT_EXTRA_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
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
