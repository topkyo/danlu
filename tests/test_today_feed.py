from __future__ import annotations

import unittest

from aiwiki.today_feed import FeedEntry, build_today_feed

MECHANISM_WORDS = {
    "shell-summary",
    "review_backlog_counts",
    "planner-log",
    "audit.jsonl",
    "receipt",
    "lane",
    "signal",
}


def _case_empty_summary_returns_empty_feed() -> None:
    assert build_today_feed({}) == []


def _case_summary_not_dict_returns_empty() -> None:
    assert build_today_feed(None) == []  # type: ignore[arg-type]


def _case_decision_entry_built_from_review_backlog() -> None:
    feed = build_today_feed(
        {"generated_at": "2026-04-27T10:00:00Z", "review_backlog_counts": {"pending_decisions": 2}}
    )
    assert feed == [
        FeedEntry(
            kind="decision",
            title="处理待定决策",
            summary="2 项待处理 · 确认待定判断与执行入口",
            target="review:pending_decisions",
            timestamp="2026-04-27T10:00:00Z",
            protocol="",
        )
    ]


def _case_decision_entry_skipped_when_count_zero() -> None:
    feed = build_today_feed({"review_backlog_counts": {"pending_decisions": 0, "pending_judgments": "0", "bad": "many"}})
    assert feed == []


def _case_decision_entry_skipped_for_blank_kind() -> None:
    assert build_today_feed({"review_backlog_counts": {" ": 1}}) == []


def _case_decision_entry_built_from_bool_count() -> None:
    feed = build_today_feed({"review_backlog_counts": {"pending_decisions": True}})
    assert len(feed) == 1
    assert feed[0].summary == "1 项待处理 · 确认待定判断与执行入口"


def _case_review_backlog_uses_product_labels() -> None:
    feed = build_today_feed(
        {
            "review_backlog_counts": {
                "counter_evidence_candidates": 1,
                "judgment_review_actions": 1,
                "l3_proposals": 1,
                "machine_memory_actions": 6,
            }
        }
    )
    titles = [entry.title for entry in feed]
    assert titles == ["补充反证候选", "复核研究判断", "处理 L3 提案", "修复机器记忆"]
    assert all("_" not in entry.title for entry in feed)


def _case_proposal_entry_built() -> None:
    feed = build_today_feed(
        {
            "review_controls": {
                "l3_proposals": [
                    {
                        "proposal_id": "prop-1",
                        "kind": "rewrite",
                        "state": "candidate",
                        "target_file": "wiki/a.md",
                        "proposal_path": "output/control/l3/prop-1.json",
                        "created_at": "2026-04-26T12:00:00Z",
                        "needs_attention": True,
                    }
                ]
            }
        }
    )
    assert len(feed) == 1
    assert feed[0].kind == "proposal"
    assert feed[0].title == "wiki/a.md"
    assert feed[0].target == "output/control/l3/prop-1.json"
    assert feed[0].timestamp == "2026-04-26T12:00:00Z"


def _case_proposal_falls_back_to_top_level_l3_proposals() -> None:
    feed = build_today_feed({"l3_proposals": [{"proposal_id": "p-top", "needs_attention": True}]})
    assert len(feed) == 1
    assert feed[0].target == "p-top"


def _case_proposal_skipped_when_attention_false() -> None:
    assert build_today_feed({"l3_proposals": [{"proposal_id": "p-top", "needs_attention": False}]}) == []


def _case_proposal_entry_skipped_without_target() -> None:
    feed = build_today_feed({"review_controls": {"l3_proposals": [{"title": "No target", "needs_attention": True}]}})
    assert feed == []


def _case_report_entry_filtered_by_today_date() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_outputs": [
                {
                    "path": "output/reports/today.md",
                    "title": "Today Report",
                    "format": "report",
                    "protocol": "research",
                    "created_at": "2026-04-27T08:00:00Z",
                }
            ],
        }
    )
    assert feed == [
        FeedEntry(
            kind="report",
            title="Today Report",
            summary="report 输出",
            target="output/reports/today.md",
            timestamp="2026-04-27T08:00:00Z",
            protocol="research",
        )
    ]


def _case_report_entry_skipped_when_not_today() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_outputs": [{"path": "output/reports/old.md", "created_at": "2026-04-26T23:59:59Z"}],
        }
    )
    assert feed == []


def _case_report_uses_generated_at_and_artifact_path_fallbacks() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27",
            "recent_outputs": [{"artifact_path": "output/reports/from-generated.md", "generated_at": "2026-04-27 10:00:00"}],
        }
    )
    assert len(feed) == 1
    assert feed[0].title == "from-generated.md"


def _case_elixir_entry_filtered_by_today_date() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_receipts": [
                {
                    "title": "Decision A",
                    "operation": "promote",
                    "receipt_path": "output/control/execution-receipts/a.json",
                    "applied_at": "2026-04-27T07:00:00Z",
                    "protocol": "investing",
                }
            ],
        }
    )
    assert len(feed) == 1
    assert feed[0].kind == "elixir"
    assert feed[0].summary == "已完成 promote"


def _case_elixir_entry_filtered_by_operation_keyword() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_receipts": [
                {
                    "title": "Compile",
                    "operation": "compile",
                    "receipt_path": "output/control/execution-receipts/c.json",
                    "applied_at": "2026-04-27T07:00:00Z",
                }
            ],
        }
    )
    assert feed == []


def _case_elixir_entry_skipped_when_not_today() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_receipts": [
                {"title": "Old", "operation": "promote", "receipt_path": "old.json", "applied_at": "2026-04-26T07:00:00Z"}
            ],
        }
    )
    assert feed == []


def _case_elixir_entry_skipped_without_target() -> None:
    feed = build_today_feed(
        {"generated_at": "2026-04-27T09:00:00Z", "recent_receipts": [{"title": "No target", "operation": "promote", "applied_at": "2026-04-27T07:00:00Z"}]}
    )
    assert feed == []


def _case_action_entry_built() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "suggested_next_actions": [
                {"title": "Review page", "command": "aiwiki review-page wiki/a.md", "reason": "review-needed"}
            ],
        }
    )
    assert feed == [
        FeedEntry(
            kind="action",
            title="Review page",
            summary="建议下一步：review-needed",
            target="aiwiki review-page wiki/a.md",
            timestamp="2026-04-27T09:00:00Z",
            protocol="",
        )
    ]


def _case_action_entry_skipped_without_command() -> None:
    assert build_today_feed({"suggested_next_actions": [{"title": "No command"}]}) == []


def _case_agent_loop_entry_built_from_nightly_summary() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-30T09:00:00+00:00",
            "active_protocol": "research",
            "nightly": {
                "generated_at": "2026-04-30T08:00:00+00:00",
                "agent_loop": {
                    "status": "ok",
                    "generated_at": "2026-04-30T08:01:00+00:00",
                    "signals": {"new_count": 1},
                    "planner": {"execute": {"new_count": 2}},
                    "auto_preview": {"ready_count": 1},
                },
            },
        }
    )

    assert len(feed) == 1
    entry = feed[0]
    assert entry.kind == "action"
    assert entry.title == "预演下一步维护"
    assert entry.summary == "今日发现 2 个新变化，1 条维护路径可人工确认"
    assert entry.target.endswith("alchemy auto --dry-run")
    assert entry.protocol == "research"


def _case_agent_loop_failed_entry_uses_product_copy() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-30T09:00:00+00:00",
            "nightly": {
                "agent_loop": {
                    "status": "failed",
                    "generated_at": "2026-04-30T08:01:00+00:00",
                    "error_type": "RuntimeError",
                }
            },
        }
    )

    assert len(feed) == 1
    assert feed[0].title == "预演下一步维护"
    assert feed[0].summary == "今日维护预演失败，需要人工查看"


def _case_agent_loop_entry_skipped_when_not_today() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-30T09:00:00+00:00",
            "nightly": {"agent_loop": {"status": "ok", "generated_at": "2026-04-29T23:59:59+00:00"}},
        }
    )
    assert feed == []


def _case_priority_ordering() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "suggested_next_actions": [{"title": "Act", "command": "cmd"}],
            "recent_receipts": [
                {"title": "Elixir", "operation": "finalize", "receipt_path": "r.json", "applied_at": "2026-04-27T01:00:00Z"}
            ],
            "recent_outputs": [{"path": "out.md", "created_at": "2026-04-27T02:00:00Z"}],
            "review_controls": {"l3_proposals": [{"proposal_id": "p", "needs_attention": True}]},
            "review_backlog_counts": {"pending_decisions": 1},
        }
    )
    assert [entry.kind for entry in feed] == ["decision", "proposal", "report", "elixir", "action"]


def _case_timestamp_desc_within_same_priority() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "recent_outputs": [
                {"path": "old.md", "created_at": "2026-04-27T01:00:00Z"},
                {"path": "new.md", "created_at": "2026-04-27T08:00:00Z"},
            ],
        }
    )
    assert [entry.target for entry in feed] == ["new.md", "old.md"]


def _case_empty_timestamp_sorts_last_within_same_priority() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27",
            "recent_outputs": [
                {"path": "dated.md", "created_at": "2026-04-27"},
                {"path": "empty.md", "created_at": "2026-04-27", "generated_at": ""},
            ],
        }
    )
    assert [entry.target for entry in feed] == ["dated.md", "empty.md"]


def _case_malformed_list_fields_are_ignored() -> None:
    assert build_today_feed({"recent_outputs": {}, "recent_receipts": {}, "suggested_next_actions": {}}) == []


def _case_pure_function_idempotent() -> None:
    summary = {"generated_at": "2026-04-27T09:00:00Z", "review_backlog_counts": {"pending_decisions": 1}}
    assert build_today_feed(summary) == build_today_feed(summary)
    assert summary == {"generated_at": "2026-04-27T09:00:00Z", "review_backlog_counts": {"pending_decisions": 1}}


def _case_no_mechanism_words_in_summary_text() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "review_backlog_counts": {"pending_decisions": 1},
            "recent_receipts": [
                {"title": "A", "operation": "promote", "receipt_path": "receipt.json", "applied_at": "2026-04-27T01:00:00Z"}
            ],
            "suggested_next_actions": [{"title": "Act", "command": "cmd", "reason": "continue"}],
            "nightly": {
                "agent_loop": {
                    "status": "ok",
                    "generated_at": "2026-04-27T02:00:00Z",
                    "signals": {"new_count": 1},
                    "planner": {"execute": {"new_count": 1}},
                    "auto_preview": {"ready_count": 1},
                }
            },
        }
    )
    for entry in feed:
        assert not any(word in entry.title for word in MECHANISM_WORDS)
        assert not any(word in entry.summary for word in MECHANISM_WORDS)


def _case_missing_generated_at_handled_gracefully() -> None:
    feed = build_today_feed({"review_backlog_counts": {"pending_decisions": 1}, "recent_outputs": [{"path": "x.md"}]})
    assert len(feed) == 2
    assert feed[0].kind == "decision"
    assert feed[1].kind == "report"


def _case_malformed_recent_outputs_skipped() -> None:
    feed = build_today_feed(
        {"generated_at": "2026-04-27T09:00:00Z", "recent_outputs": ["bad", {}, {"created_at": "2026-04-27T01:00:00Z"}]}
    )
    assert feed == []


def _case_target_field_present() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "review_backlog_counts": {"pending_decisions": 1},
            "review_controls": {"l3_proposals": [{"proposal_id": "p", "needs_attention": True}]},
            "recent_outputs": [{"path": "out.md", "created_at": "2026-04-27T01:00:00Z"}],
            "recent_receipts": [{"title": "E", "operation": "revert", "receipt_path": "r.json", "applied_at": "2026-04-27T01:00:00Z"}],
            "suggested_next_actions": [{"title": "A", "command": "cmd"}],
        }
    )
    assert feed
    assert all(entry.target for entry in feed)


def _case_kind_values_in_allowed_set() -> None:
    allowed = {"decision", "proposal", "report", "elixir", "action"}
    feed = build_today_feed(
        {
            "generated_at": "2026-04-27T09:00:00Z",
            "review_backlog_counts": {"pending_decisions": 1},
            "suggested_next_actions": [{"title": "A", "command": "cmd"}],
        }
    )
    assert {entry.kind for entry in feed} <= allowed


# --- P0 M8.1: counter-evidence / drift / metric-alert entries ---


def _case_counter_evidence_entry_built() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-28T09:00:00Z",
            "counter_evidence_pages": [
                {
                    "path": "wiki/judgments/x.md",
                    "subject": "Judgment X",
                    "summary": "新证据反驳原结论",
                    "detected_at": "2026-04-28T08:00:00Z",
                    "protocol": "investing",
                }
            ],
        }
    )
    assert len(feed) == 1
    entry = feed[0]
    assert entry.kind == "decision"
    assert entry.title == "反证待复核: Judgment X"
    assert entry.target == "wiki/judgments/x.md"
    assert entry.protocol == "investing"


def _case_counter_evidence_skipped_without_path() -> None:
    feed = build_today_feed(
        {"counter_evidence_pages": [{"subject": "no path"}, "bad", None, {}]}
    )
    assert feed == []


def _case_drift_entry_built() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-28T09:00:00Z",
            "drift_warnings": [
                {
                    "kind": "source-reference-break",
                    "path": "wiki/sources/missing.md",
                    "message": "Missing source page `wiki/sources/missing.md`.",
                }
            ],
        }
    )
    assert len(feed) == 1
    entry = feed[0]
    assert entry.kind == "decision"
    assert entry.title.startswith("知识漂移:")
    assert "missing" in entry.target


def _case_drift_skipped_when_empty() -> None:
    assert build_today_feed({"drift_warnings": []}) == []
    assert build_today_feed({"drift_warnings": "bad"}) == []


def _case_metric_alert_entry_built() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-28T09:00:00Z",
            "metrics_history_delta": {
                "available": True,
                "window": "7d",
                "baseline_ts": "2026-04-21T09:00:00Z",
                "alerts": [
                    {
                        "metric_key": "stale_ratio",
                        "previous": 0.10,
                        "current": 0.20,
                        "diff": 0.10,
                        "direction": "up",
                    }
                ],
            },
        }
    )
    assert len(feed) == 1
    entry = feed[0]
    assert entry.kind == "action"
    assert "stale_ratio" in entry.title
    assert "↑" in entry.title
    assert entry.target == "metric:stale_ratio"


def _case_metric_alert_skipped_when_unavailable() -> None:
    assert build_today_feed({"metrics_history_delta": {"available": False}}) == []
    assert build_today_feed({"metrics_history_delta": {}}) == []


def _case_metric_alert_skipped_when_no_alerts() -> None:
    feed = build_today_feed(
        {
            "metrics_history_delta": {
                "available": True,
                "window": "7d",
                "baseline_ts": "2026-04-21T09:00:00Z",
                "alerts": [],
            }
        }
    )
    assert feed == []


def _case_p0_signals_combine_with_existing_kinds() -> None:
    feed = build_today_feed(
        {
            "generated_at": "2026-04-28T09:00:00Z",
            "review_backlog_counts": {"pending_decisions": 1},
            "counter_evidence_pages": [
                {"path": "wiki/judgments/y.md", "subject": "Y", "summary": "反证"}
            ],
            "drift_warnings": [
                {"kind": "concept-disappear", "path": "wiki/concepts/z.md", "message": "missing z"}
            ],
            "metrics_history_delta": {
                "available": True,
                "window": "7d",
                "baseline_ts": "2026-04-21T09:00:00Z",
                "alerts": [{"metric_key": "stale_ratio", "previous": 0.1, "current": 0.2, "diff": 0.1, "direction": "up"}],
            },
            "suggested_next_actions": [{"title": "A", "command": "cmd"}],
        }
    )
    kinds = [entry.kind for entry in feed]
    # priority: decision (3 of: backlog + counter-evidence + drift) before action (2: alert + suggested)
    assert kinds.count("decision") == 3
    assert kinds.count("action") == 2
    # decisions all sort before actions per _PRIORITY
    assert kinds[:3] == ["decision", "decision", "decision"]
    assert kinds[3:] == ["action", "action"]


class TodayFeedTests(unittest.TestCase):
    """Expose the same pure function checks to unittest discover."""


for _name, _func in list(globals().items()):
    if _name.startswith("_case_") and callable(_func):
        setattr(TodayFeedTests, f"test_{_name.removeprefix('_case_')}", staticmethod(_func))

del _name, _func
