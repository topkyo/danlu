from __future__ import annotations

import pytest

from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import alchemy_support as support


def test_replace_review_queue_section_preserves_review_queue_contract():
    section = (
        support.ALCHEMY_REVIEW_QUEUE_START
        + "\nnew\n"
        + support.ALCHEMY_REVIEW_QUEUE_END
        + "\n"
    )

    assert support.replace_review_queue_section("", section) == "# Review Queue\n\n" + section
    assert support.replace_review_queue_section("# Existing\n", section) == "# Existing\n\n" + section

    existing = (
        "# Review Queue\n\n"
        + support.ALCHEMY_REVIEW_QUEUE_START
        + "\nold\n"
        + support.ALCHEMY_REVIEW_QUEUE_END
        + "\n\nTail\n"
    )
    assert support.replace_review_queue_section(existing, section) == "# Review Queue\n\n" + section + "Tail\n"


def test_unique_alchemy_action_id_reuses_receipt_path_collision_contract(tmp_path):
    applied_at = "2026-05-25T01:02:03+00:00"
    first = support.unique_alchemy_action_id(tmp_path, prefix="alchemy-review", applied_at=applied_at)
    assert first == "alchemy-review-20260525010203"

    path = execution_receipt_path(tmp_path, first)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")

    second = support.unique_alchemy_action_id(tmp_path, prefix="alchemy-review", applied_at=applied_at)
    assert second == "alchemy-review-20260525010203-2"


def test_named_alchemy_action_id_helpers_use_stable_prefixes(tmp_path):
    applied_at = "2026-05-25T01:02:03+00:00"

    assert support.unique_alchemy_propose_action_id(tmp_path, applied_at=applied_at) == "alchemy-propose-20260525010203"
    assert support.unique_alchemy_distill_action_id(tmp_path, applied_at=applied_at) == "alchemy-distill-20260525010203"
    assert support.unique_alchemy_judge_action_id(tmp_path, applied_at=applied_at) == "alchemy-judge-20260525010203"
    assert support.unique_alchemy_judge_proposal_action_id(tmp_path, applied_at=applied_at) == "alchemy-judge-proposal-20260525010203"
    assert support.unique_alchemy_judge_proposal_apply_action_id(tmp_path, applied_at=applied_at) == "alchemy-judge-proposal-apply-20260525010203"
    assert support.unique_alchemy_review_action_id(tmp_path, applied_at=applied_at) == "alchemy-review-20260525010203"


def test_named_preview_summaries_add_primitive_specific_contract_flags():
    preview = {
        "status": "ok",
        "scope": "all",
        "selected_count": 1,
        "scope_preview": {"trace_ids": ["trace-a"]},
        "apply_contract": {"scope_enforced": True},
    }
    candidates = [{"candidate_id": "cand-1"}]

    assert support.review_preview_receipt_summary(preview, candidates) == {
        "status": "ok",
        "scope": "all",
        "selected_count": 1,
        "candidate_count": 1,
        "candidate_ids": ["cand-1"],
        "scope_preview": {"trace_ids": ["trace-a"]},
        "apply_contract": {"scope_enforced": True},
    }
    assert support.propose_preview_receipt_summary(preview, candidates)["human_accept_required_after_apply"] is True
    assert support.distill_preview_receipt_summary(preview, candidates) | {
        "direct_apply_only": False,
        "lane_apply_supported": True,
    } == support.distill_preview_receipt_summary(preview, candidates)
    assert support.judge_preview_receipt_summary(preview, candidates) | {
        "semantic_rewrite": False,
        "lane_apply_supported": False,
    } == support.judge_preview_receipt_summary(preview, candidates)


def test_named_idempotency_keys_keep_prefix_and_extra_contracts():
    kwargs = {"scope": "all", "candidate_ids": ["b", "a"], "trace_ids": ["t2", "t1"]}

    assert support.alchemy_review_idempotency_key(**kwargs).startswith("alchemy-review:")
    assert support.alchemy_propose_idempotency_key(**kwargs).startswith("alchemy-propose:")
    assert support.alchemy_distill_idempotency_key(**kwargs).startswith("alchemy-distill:")
    assert support.alchemy_judge_idempotency_key(**kwargs).startswith("alchemy-judge:")
    assert support.alchemy_judge_proposal_idempotency_key(**kwargs).startswith("alchemy-judge-proposal:")
    assert support.alchemy_review_idempotency_key(**kwargs) == support.alchemy_review_idempotency_key(
        scope="all",
        candidate_ids=["a", "b"],
        trace_ids=["t1", "t2"],
    )
    assert support.alchemy_distill_idempotency_key(**kwargs) != support.alchemy_idempotency_key(
        "alchemy-distill",
        primitive="distill",
        scope="all",
        candidate_ids=["a", "b"],
        trace_ids=["t1", "t2"],
    )


def test_normalize_preview_lock_status_only_rewrites_lock_subtrees():
    payload = {
        "lock": {
            "status": "held_by_current_process",
            "would_acquire": False,
        },
        "unrelated": {
            "status": "held_by_current_process",
            "would_acquire": False,
        },
        "items": [
            {
                "lock": {
                    "status": "held_by_current_process",
                    "would_acquire": False,
                }
            }
        ],
    }

    result = support.normalize_preview_lock_status(payload)

    assert result["lock"] == {"status": "available", "would_acquire": True}
    assert result["unrelated"] == {"status": "held_by_current_process", "would_acquire": False}
    assert result["items"][0]["lock"] == {"status": "available", "would_acquire": True}


def test_alchemy_distill_helpers_preserve_stable_question_contract(tmp_path):
    candidate = {
        "candidate_id": "cand-1",
        "target_ref": "wiki/derived/My Page.md",
        "signal_ids": ["sig-b", "", "sig-a", "sig-a"],
    }

    assert support.alchemy_distill_target_id(" wiki/derived/My Page.md ") == "My Page"
    assert support.alchemy_distill_target_id(" ") == ""
    assert (
        support.alchemy_distill_question(candidate)
        == "Alchemy scoped distill refresh for cand-1 (wiki/derived/My Page.md); signals=sig-a,sig-b"
    )
    assert support.alchemy_distill_question({}) == "Alchemy scoped distill refresh for distill (); signals=none"

    page = tmp_path / "candidate.md"
    page.write_text(
        '---\ndistill_history_json: "[{\\"question\\": \\"q1\\"}, {\\"question\\": 3}]"\n---\nBody\n',
        encoding="utf-8",
    )
    assert support.alchemy_distill_history_questions(page) == {"q1"}

    page.write_text('---\ndistill_history_json: "not json"\n---\nBody\n', encoding="utf-8")
    assert support.alchemy_distill_history_questions(page) == set()


def test_alchemy_propose_prompt_content_appends_review_marker(tmp_path):
    target = tmp_path / "wiki" / "target.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Existing\n\nBody\n\n", encoding="utf-8")

    content = support.alchemy_propose_prompt_content(
        tmp_path,
        target_file="wiki/target.md",
        scope="ops",
        candidate={
            "candidate_id": "cand-1",
            "target_ref": "wiki/target.md",
            "signal_ids": ["sig-b", "sig-a"],
        },
    )

    assert content.startswith("# Existing\n\nBody\n")
    assert "<!-- aiwiki:alchemy-propose:start -->" in content
    assert "<!-- scope: ops -->" in content
    assert "<!-- candidate_id: cand-1 -->" in content
    assert "<!-- target_ref: wiki/target.md -->" in content
    assert "<!-- signal_ids: sig-a, sig-b -->" in content
    assert content.endswith("<!-- aiwiki:alchemy-propose:end -->\n")


def test_lane_receipt_helpers_preserve_receipt_contract(tmp_path):
    applied_at = "2026-05-25T01:02:03+00:00"
    action_id = support.unique_lane_primitive_action_id(
        tmp_path,
        lane="quality",
        primitive="compile",
        applied_at=applied_at,
    )
    assert action_id == "alchemy-quality-compile-20260525010203"

    plan = {
        "lane": "quality",
        "scope": "all",
        "selected_count": 2,
        "scope_preview": {
            "protocols": ["ops", "product"],
            "trace_ids": [" trace-b ", "trace-a", "", "trace-a", 7],
        },
        "primitive_plan": [
            {"primitive": "compile", "apply_supported": True},
            {"primitive": "lint", "apply_supported": True},
        ],
    }

    assert support.lane_primitive_plan_step(plan, "lint") == {"primitive": "lint", "apply_supported": True}
    assert support.lane_primitive_plan_step(plan, "missing") is None
    assert support.first_plan_protocol(plan) == "ops"
    assert support.lane_receipt_trace_ids(plan) == ["trace-a", "trace-b"]
    assert support.lane_receipt_plan_summary(plan) == {
        "lane": "quality",
        "scope": "all",
        "selected_count": 2,
        "scope_preview": plan["scope_preview"],
        "primitive_plan": plan["primitive_plan"],
    }


def test_normalize_auto_lanes_dedupes_case_and_rejects_invalid_values():
    assert support.normalize_auto_lanes([" Heavy ", "light", "HEAVY"]) == ["heavy", "light"]

    with pytest.raises(ValueError, match="requires at least one lane"):
        support.normalize_auto_lanes([])
    with pytest.raises(ValueError, match="unsupported alchemy auto lane"):
        support.normalize_auto_lanes(["heavy", "manual"])


def test_normalize_lane_primitives_dedupes_case_and_rejects_unknown_values():
    assert support.normalize_lane_primitives([" Compile ", "", "lint", "COMPILE", "review"]) == [
        "compile",
        "lint",
        "review",
    ]

    with pytest.raises(ValueError, match="unsupported alchemy lane primitive"):
        support.normalize_lane_primitives(["compile", "invent"])


def test_auto_primitives_for_lane_uses_lane_defaults_and_apply_support():
    plan = {
        "primitive_plan": [
            {"primitive": "compile", "apply_supported": True},
            {"primitive": "lint", "apply_supported": True},
            {"primitive": "nightly", "apply_supported": True},
            {"primitive": "review", "apply_supported": True},
            {"primitive": "distill", "apply_supported": False},
            {"primitive": "propose", "apply_supported": True},
        ]
    }

    assert support.auto_primitives_for_lane("heavy", plan, requested_primitives=[]) == ["compile", "lint"]
    assert support.auto_primitives_for_lane("light", plan, requested_primitives=[]) == [
        "compile",
        "lint",
        "nightly",
    ]
    assert support.auto_primitives_for_lane(
        "heavy",
        plan,
        requested_primitives=["review", "distill", "propose", "nightly"],
    ) == ["review", "propose", "nightly"]
    assert support.auto_primitives_for_lane(
        "light",
        plan,
        requested_primitives=["review", "nightly"],
    ) == ["nightly"]


def test_auto_skip_reason_reports_plan_state_before_selection_state():
    assert support.auto_skip_reason({"status": "blocked", "selected_count": 1}, ["compile"]) == "plan_blocked"
    assert support.auto_skip_reason({"status": "", "selected_count": 1}, ["compile"]) == "plan_unknown"
    assert support.auto_skip_reason({"status": "ok", "selected_count": 0}, ["compile"]) == "empty_execute_plan"
    assert support.auto_skip_reason({"status": "ok", "selected_count": 1}, []) == "no_apply_supported_primitives"
    assert support.auto_skip_reason({"status": "ok", "selected_count": 1}, ["compile"]) == ""


def test_apply_preview_candidates_normalizes_filters_and_preserves_error_messages():
    preview = {
        "status": "ok",
        "lock": {"status": "held_by_current_process", "would_acquire": True},
        "candidates": [
            {"candidate_id": "a", "kind": "judgment_refresh", "apply_supported": True},
            {"candidate_id": "b", "kind": "judgment_refresh", "apply_supported": False},
            {"candidate_id": "c", "kind": "other", "apply_supported": True},
            "not-a-candidate",
        ],
    }

    normalized, candidates = support.apply_preview_candidates(
        preview,
        status_error_template="bad status {status}",
        empty_error_message="empty candidates",
        kind="judgment_refresh",
        require_apply_supported=True,
    )

    assert normalized["lock"]["status"] == "available"
    assert candidates == [{"candidate_id": "a", "kind": "judgment_refresh", "apply_supported": True}]

    with pytest.raises(RuntimeError, match="bad status blocked"):
        support.apply_preview_candidates(
            {"status": "blocked", "candidates": []},
            status_error_template="bad status {status}",
            empty_error_message="empty candidates",
        )
    with pytest.raises(RuntimeError, match="empty candidates"):
        support.apply_preview_candidates(
            {"status": "ok", "candidates": [{"kind": "other", "apply_supported": True}]},
            status_error_template="bad status {status}",
            empty_error_message="empty candidates",
            kind="judgment_refresh",
            require_apply_supported=True,
        )


def test_lane_receipt_result_summary_and_primary_path():
    result = {
        "state_path": "",
        "path": "wiki/derived/result.md",
        "repair_backlog": "wiki/derived/repair.md",
        "semantic_report": "output/reports/semantic.md",
        "llm_used": True,
        "updated_source_pages": ["a", "b"],
        "updated_concept_pages": ["c"],
        "counts": {"errors": 0},
        "ignored": "not in receipt summary",
    }

    assert support.primary_result_path(result) == "wiki/derived/result.md"
    assert support.primary_result_path({"repair_backlog": "wiki/derived/repair.md"}) == "wiki/derived/repair.md"
    assert support.lane_receipt_result_summary(result) == {
        "state_path": "",
        "repair_backlog": "wiki/derived/repair.md",
        "semantic_report": "output/reports/semantic.md",
        "llm_used": True,
        "updated_source_pages_count": 2,
        "updated_concept_pages_count": 1,
        "counts": {"errors": 0},
    }


def test_render_alchemy_review_queue_section_escapes_table_cells():
    section = support.render_alchemy_review_queue_section(
        preview={
            "scope": "ops|risk",
            "scope_preview": {"trace_ids": ["trace-b", "trace-a", "trace-a"]},
        },
        candidates=[
            {
                "candidate_id": "cand|1",
                "kind": "decision",
                "protocol": "ops",
                "target_ref": "wiki/decisions/a.md",
                "signal_ids": ["sig|2", "sig1"],
            }
        ],
    )

    assert section.startswith(support.ALCHEMY_REVIEW_QUEUE_START)
    assert "- scope: `ops\\|risk`" in section
    assert "- trace_ids: `trace-a, trace-b`" in section
    assert "| cand\\|1 | decision | ops | wiki/decisions/a.md | sig1, sig\\|2 |" in section
    assert section.rstrip().endswith(support.ALCHEMY_REVIEW_QUEUE_END)


def test_render_alchemy_judge_sections_keep_markers_and_contract_text():
    refresh = support.render_alchemy_judge_refresh_section(
        preview={"scope": "ops"},
        candidate={
            "candidate_id": "cand-1",
            "target_ref": "wiki/judgments/a.md",
            "signal_ids": ["sig1"],
            "trace_ids": ["trace1"],
        },
    )
    assert support.ALCHEMY_JUDGE_REFRESH_START in refresh
    assert "- candidate_id: `cand-1`" in refresh
    assert "does not rewrite the judgment conclusion" in refresh
    assert support.ALCHEMY_JUDGE_REFRESH_END in refresh

    accepted = support.render_alchemy_judge_accepted_target_section(
        proposal_id="proposal|1",
        proposal_path="output/_proposals/judge/p.md",
        accepted_body="\nAccepted body\n",
    )
    assert support.ALCHEMY_JUDGE_ACCEPTED_TARGET_START in accepted
    assert "- proposal_id: `proposal\\|1`" in accepted
    assert "Accepted body" in accepted
    assert support.ALCHEMY_JUDGE_ACCEPTED_TARGET_END in accepted


def test_render_alchemy_judge_proposal_page_records_baseline_contract():
    proposal = support.render_alchemy_judge_proposal_page(
        preview={"scope": "ops"},
        candidate={
            "candidate_id": "cand-1",
            "signal_ids": ["sig1"],
            "trace_ids": ["trace1"],
            "source_ids": ["source1"],
            "concept_slugs": ["concept-a"],
        },
        target_ref="wiki/judgments/a.md",
        proposal_id="proposal-1",
        target_kind="judgment",
        before_hash="abc123",
    )

    assert 'kind: "alchemy-judge-proposal"' in proposal
    assert "# Judge Proposal: proposal-1" in proposal
    assert support.ALCHEMY_JUDGE_PROPOSAL_START in proposal
    assert "- target_file: `wiki/judgments/a.md`" in proposal
    assert "- llm_invoked: `false`" in proposal
    assert "Do not apply changes directly to the target page." in proposal
    assert support.ALCHEMY_JUDGE_PROPOSAL_END in proposal
