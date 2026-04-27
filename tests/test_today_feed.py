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
            title="待审议: pending_decisions",
            summary="2 项待审",
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
    assert feed[0].summary == "1 项待审"


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
        }
    )
    for entry in feed:
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


class TodayFeedTests(unittest.TestCase):
    """Expose the same pure function checks to unittest discover."""


for _name, _func in list(globals().items()):
    if _name.startswith("_case_") and callable(_func):
        setattr(TodayFeedTests, f"test_{_name.removeprefix('_case_')}", staticmethod(_func))

del _name, _func
