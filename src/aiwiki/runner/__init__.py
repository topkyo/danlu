"""Runner package façade. Re-exports public and test-used names from sibling modules.

Submodules:
- interfaces: SupportsComplete protocol
- clients: LLM client lifecycle and fallback helpers
- receipts: LLM audit, receipt, and run-log helpers
- prompts: prompt profiles, builders, context, and validators
- workflows: run_compile / run_ask / run_lint / run_nightly
- commands: thin command façades for L3, audit, planner, protocol, and signals
- alchemy: alchemy lifecycle, scoped primitives, lane, and auto orchestration
- automation: auto_process_once / watch_inbox / inbox_snapshot
"""

from __future__ import annotations

from aiwiki.runner.alchemy import (  # noqa: F401
    run_alchemy_auto,
    run_alchemy_demote,
    run_alchemy_distill,
    run_alchemy_distill_apply,
    run_alchemy_distill_preview,
    run_alchemy_finalize,
    run_alchemy_judge_apply,
    run_alchemy_judge_preview,
    run_alchemy_judge_proposal_apply,
    run_alchemy_judge_propose,
    run_alchemy_lane_apply,
    run_alchemy_lane_dry_run,
    run_alchemy_legacy_migration_apply,
    run_alchemy_legacy_migration_preview,
    run_alchemy_promote,
    run_alchemy_propose_apply,
    run_alchemy_propose_preview,
    run_alchemy_revert,
    run_alchemy_review_apply,
    run_alchemy_review_preview,
    run_alchemy_start,
    run_alchemy_superseded_cleanup_apply,
    run_alchemy_superseded_cleanup_preview,
)
from aiwiki.runner.automation import (  # noqa: F401
    _pending_summary_count,
    _write_automation_state,
    auto_process_once,
    inbox_snapshot,
    watch_inbox,
)
from aiwiki.runner.clients import (  # noqa: F401
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _client_selected_model_name,
    _fallback_stage_label,
    _fallback_to_next_model,
    _fallback_to_next_model_with_stage,
    create_client,
    llm_probe,
    llm_status,
)
from aiwiki.runner.commands import (  # noqa: F401
    run_audit_backfill,
    run_audit_preview,
    run_demote,
    run_l3_proposal_apply,
    run_l3_proposal_create,
    run_l3_proposal_generate,
    run_l3_proposal_generation_preview,
    run_l3_proposal_list,
    run_l3_proposal_reject,
    run_l3_proposal_revert,
    run_planner_log_list,
    run_planner_log_rollback,
    run_planner_log_rollback_preview,
    run_promote,
    run_signals_list,
    run_signals_show,
)
from aiwiki.runner.interfaces import SupportsComplete  # noqa: F401
from aiwiki.runner.prompts import (  # noqa: F401
    ASK_INDEX_PAGES_BASE,
    ASK_INDEX_PAGES_BY_FORMAT,
    ASK_PROMPT_PROFILES,
    ASK_PROTOCOL_PAGE_NAMES_BASE,
    ASK_PROTOCOL_PAGE_NAMES_BY_FORMAT,
    COMPILE_PROMPT_PROFILES,
    LINT_PROMPT_PROFILES,
    _ask_prompt_profile,
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _compile_prompt_profile,
    _context_budget,
    _dedupe_report_citations,
    _extract_related_concept_slugs,
    _fit_prompt_section,
    _initial_ask_prompt_profile,
    _initial_compile_prompt_profile,
    _initial_lint_prompt_profile,
    _lean_ask_prompt_profile,
    _lint_prompt_profile,
    _load_prompt,
    _normalize_markdown,
    _protocol_context,
    _read_context,
    _render_machine_query,
    _retry_ask_prompt_profile,
    _retry_compile_prompt_profile,
    _retry_lint_prompt_profile,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _schema_context,
    _select_ask_index_pages,
    _select_ask_protocol_pages,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
)
from aiwiki.runner.receipts import (  # noqa: F401
    _append_jsonl_log,
    _append_llm_receipt,
    _append_llm_receipt_and_log,
    _append_log,
    _build_llm_audit,
    _empty_llm_audit,
    _infer_delivery_mode,
    _llm_audit_from_result,
    _merge_llm_audits,
    _next_jsonl_line_number,
    append_receipt_and_audit,
    build_llm_attempt_receipt,
    classify_fallback_stage,
    record_llm_attempt,
)
from aiwiki.runner.workflows import (  # noqa: F401
    _reinject_candidate_frontmatter,
    promote_recurring_outputs,
    run_ask,
    run_compile,
    run_lint,
    run_nightly,
)
