"""Output-pack, dashboard-index, and pack/path helpers extracted from app_content."""

# ruff: noqa: I001

from __future__ import annotations

# EP-017A step 1: paths/wiki-log helpers extracted to aiwiki.render.paths.
# Re-exported here to preserve `from aiwiki.app_render import <name>` for
# external callers (execution/* owners, app_compile, app_content, compile/*).
from .render.paths import (  # noqa: F401
    append_wiki_log,
    decision_memo_path,
    decision_memos_dir,
    ensure_wiki_log,
    execution_bundle_path,
    execution_bundles_dir,
    execution_proposal_path,
    execution_proposals_dir,
    execution_receipt_path,
    execution_receipts_dir,
    pack_stem,
    remove_stale_generated_concept_pages,
    remove_stale_generated_concept_pages_detailed,
    review_pack_path,
    review_packs_dir,
    sop_draft_path,
    sop_drafts_dir,
)

# EP-017A step 2: output-pack helpers + builders + index + protocol pack
# rows extracted to aiwiki.render.packs. Re-exported here to preserve
# `from aiwiki.app_render import <name>` for external callers
# (app_content, app_compile_ops, app_linting, app_queries, compile/*,
# execution/*).
from .render.packs import (  # noqa: F401
    build_output_pack_decision_memos,
    build_output_pack_review_packs,
    build_output_pack_sop_drafts,
    build_output_packs,
    build_output_packs_incremental,
    compact_section_lines,
    decision_memo_recommendation_lines,
    decision_memo_section_lines,
    extract_sop_pattern_frequencies,
    load_workspace_markdown,
    output_pack_decision_memo_group_input_signature,
    output_pack_group_is_reusable,
    output_pack_lifecycle_summary_input_signature,
    output_pack_repair_plan_candidates,
    output_pack_review_candidates,
    output_pack_review_group_input_signature,
    output_pack_reviewed_candidates,
    output_pack_sop_group_input_signature,
    output_pack_state_records,
    output_pack_version_history_lines,
    pack_workspace_link,
    protocol_output_pack_rows,
    render_output_packs_index,
    sop_pattern_key,
    workspace_file_signature,
    workspace_link,
)

# EP-017A step 3: domain-pilot scorecard helpers/builders extracted to
# aiwiki.render.pilots. Re-exported here to preserve
# `from aiwiki.app_render import <name>` for external callers.
from .render.pilots import (  # noqa: F401
    build_domain_pilot_scorecard,
    build_domain_pilots,
    build_domain_pilots_incremental,
    domain_pilot_protocol_input_signature,
    domain_pilot_protocol_inputs,
    domain_pilot_scorecard_is_reusable,
    domain_pilot_state_scorecard,
    domain_pilots_index_path,
    pilot_scorecard_path,
    pilot_scorecards_dir,
    pilot_stage,
    protocol_scorecard,
)

# EP-017A step 4: dashboard view renderers extracted to aiwiki.render.views.
# Re-exported here to preserve `from aiwiki.app_render import <name>` for
# external callers (app_compile, app_content, app_surfaces, compile/*,
# execution/*, runner, cli).
from .render.views import (  # noqa: F401
    furnace_quick_commands,
    judgment_asset_attention_sort_key,
    judgment_asset_gap_codes,
    judgment_asset_shell_record,
    judgment_asset_summary,
    protocol_execution_receipts,
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_cognitive_history,
    render_compile_status,
    render_curated_index,
    render_curated_page_summary,
    render_domain_pilots_index,
    render_furnace_center,
    render_furnace_center_html,
    render_judgment_assets,
    render_master_index,
    render_review_center_html,
    render_review_queue,
)
