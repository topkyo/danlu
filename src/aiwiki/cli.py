"""Command line interface for aiwiki."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .app_cache import cache_status_summary, drop_query_cache, force_rebuild_query_cache
from .app_compile import (
    apply_concept_rewrite,
    apply_machine_memory_action,
    apply_machine_memory_actions_batch,
    apply_material_archive,
    ask_question,
    compile_wiki,
    file_back,
    lint_wiki,
    nightly_health,
    reactivate_concept,
    resolve_machine_memory_action_query,
    retire_concept,
    revert_concept_rewrite,
    revert_machine_memory_action,
    revert_machine_memory_action_batch,
    revert_material_archive,
    review_concept_rewrite,
    review_machine_memory_action,
    review_page,
    review_pages_batch,
    set_active_protocol,
    shell_status,
    verify_concept_rewrite,
)
from .app_content import action_supports_low_risk_apply, ingest_source
from .app_protocol import ensure_layout, load_protocol_state
from .app_shell import build_shell_summary, rewrite_recovery_payload_for_paths, shell_search, shell_status_dashboard
from .app_state import load_machine_memory_action_state
from .app_vault import bootstrap_new_vault
from .drop import drop_image, drop_note, drop_pdf, drop_repo, drop_url
from .planner import write_planner_log
from .runner import (
    auto_process_once,
    llm_probe,
    llm_status,
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
    run_ask,
    run_audit_backfill,
    run_audit_preview,
    run_compile,
    run_demote,
    run_l3_proposal_apply,
    run_l3_proposal_create,
    run_l3_proposal_generate,
    run_l3_proposal_generation_preview,
    run_l3_proposal_list,
    run_l3_proposal_reject,
    run_l3_proposal_revert,
    run_lint,
    run_nightly,
    run_planner_log_list,
    run_planner_log_rollback,
    run_planner_log_rollback_preview,
    run_promote,
    run_protocol_learn_add,
    run_protocol_learn_age,
    run_protocol_learn_archive,
    run_protocol_learn_demote,
    run_protocol_learn_list,
    run_protocol_learn_revert_activate,
    run_protocol_learn_show,
    run_protocol_learn_supersede,
    run_protocol_learn_verify,
    run_signals_list,
    run_signals_show,
    watch_inbox,
)
from .signals import collect_signals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiwiki", description="Local-first knowledge compiler scaffold")
    parser.add_argument("--root", default=".", help="Project root. Defaults to the current directory.")
    parser.add_argument(
        "--model-fallback",
        action="append",
        dest="model_fallback",
        help="Fallback model to try when current model fails. Repeatable or comma-separated. Overrides AIWIKI_MODEL_FALLBACK env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _register_legacy_top_level_parsers(subparsers)
    today_parser = subparsers.add_parser("today", help="炼丹炉今日产出 / 待办 / 建议")
    today_parser.set_defaults(handler_command="today")
    drop_parser = subparsers.add_parser("drop", help="炼丹炉输入端：投喂 URL / PDF / 图片 / 仓库 / 笔记 / 问题")
    drop_subparsers = drop_parser.add_subparsers(dest="drop_command", required=True)
    _register_drop_subcommand_parsers(drop_subparsers)
    advanced_parser = subparsers.add_parser(
        "advanced",
        help="高级抽屉：系统状态、receipts、audit、repair、lanes、调试入口",
    )
    advanced_subparsers = advanced_parser.add_subparsers(dest="advanced_command", required=True)
    _register_legacy_top_level_parsers(advanced_subparsers)
    return parser


def _register_legacy_top_level_parsers(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("layout", help="Create the expected directory layout.")

    new_vault_parser = subparsers.add_parser(
        "new-vault",
        help="Scaffold a new Obsidian 炼丹炉 vault that points back to this runtime root.",
    )
    new_vault_parser.add_argument("target", help="Target directory for the new vault.")
    new_vault_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing managed scaffold files into an existing non-empty directory.",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a local file or URL stub.")
    ingest_parser.add_argument("source", help="Local file path or URL.")
    ingest_parser.add_argument("--title", help="Optional display title.")

    _configure_drop_url_parser(subparsers.add_parser("drop-url", help="Fetch a web page into raw/inbox as source material."))
    _configure_drop_pdf_parser(subparsers.add_parser("drop-pdf", help="Import a PDF into raw/assets and raw/inbox."))
    _configure_drop_image_parser(subparsers.add_parser("drop-image", help="Import an image into raw/assets and raw/inbox."))
    _configure_drop_repo_parser(subparsers.add_parser("drop-repo", help="Snapshot a local or remote repo into raw/inbox."))
    _configure_drop_note_parser(subparsers.add_parser("drop-note", help="Capture a free-text note or transcript into raw/inbox."))

    subparsers.add_parser("compile", help="Compile manifest entries into wiki source pages and indexes.")

    protocol_status_parser = subparsers.add_parser(
        "protocol-status",
        help="Show the active furnace protocol and available protocol library.",
    )
    protocol_status_parser.add_argument(
        "--set",
        dest="set_protocol",
        help="Optional protocol slug to activate before printing status.",
    )

    protocol_set_parser = subparsers.add_parser(
        "protocol-set",
        help="Set the active furnace protocol for subsequent ask/file-back/nightly workflows.",
    )
    protocol_set_parser.add_argument("protocol", help="Protocol slug, for example general, investing, or research.")

    subparsers.add_parser(
        "shell-status",
        help="Write and return the Product Shell summary contract for front-end workbench integrations.",
    )
    subparsers.add_parser("dashboard", help="Return the Product Shell dashboard contract.")

    search_parser = subparsers.add_parser("search", help="Search compiled wiki pages from the Product Shell.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--limit", type=int, default=12, help="Maximum number of results to return.")

    run_compile_parser = subparsers.add_parser(
        "run-compile",
        help="Compile sources and use the configured LLM to replace placeholder summaries.",
    )
    run_compile_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of pending source pages to enrich in one run.",
    )

    ask_parser = subparsers.add_parser("ask", help="Generate a query artifact grounded in the wiki.")
    _configure_ask_parser(ask_parser)

    protocol_learn_add_parser = subparsers.add_parser("protocol-learn-add", help="Add a protocol learning.")
    protocol_learn_add_parser.add_argument("protocol", help="Protocol slug.")
    protocol_learn_add_parser.add_argument("--title", required=True, help="Learning title.")
    protocol_learn_add_parser.add_argument("--source-ref", action="append", dest="source_refs", help="Source reference.")

    protocol_learn_list_parser = subparsers.add_parser("protocol-learn-list", help="List protocol learnings.")
    protocol_learn_list_parser.add_argument("protocol", nargs="?", help="Optional protocol slug.")
    protocol_learn_list_parser.add_argument(
        "--state",
        choices=("active", "stale", "demoted", "superseded", "archived"),
        help="可选：仅显示指定 state 的 learning。",
    )
    protocol_learn_list_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="包含 archived learning；默认隐藏 archived。",
    )

    protocol_learn_show_parser = subparsers.add_parser("protocol-learn-show", help="Show a protocol learning.")
    protocol_learn_show_parser.add_argument("learning_id", help="Learning id.")

    signals_list_parser = subparsers.add_parser("signals-list", help="List runtime signals (read-only inspection).")
    signals_list_parser.add_argument("--kind", help="Optional exact signal kind filter.")
    signals_list_parser.add_argument("--trace-id", help="Optional exact trace_id filter.")
    signals_list_parser.add_argument("--since", help="Optional ISO datetime lower bound (inclusive).")
    signals_list_parser.add_argument("--limit", type=int, default=20, help="Maximum number of results (recent first).")
    signals_list_parser.add_argument("--json", action="store_true", help="Return full JSON records.")

    signals_show_parser = subparsers.add_parser("signals-show", help="Show one signal and related planner decisions.")
    signals_show_parser.add_argument("signal_id", help="Signal id.")
    signals_show_parser.add_argument("--json", action="store_true", help="Return full JSON payload.")

    planner_log_list_parser = subparsers.add_parser(
        "planner-log-list",
        help="List planner log records (read-only inspection).",
    )
    planner_log_list_parser.add_argument("--decision", help="Optional exact planner decision filter.")
    planner_log_list_parser.add_argument("--signal-id", help="Optional exact signal_id filter.")
    planner_log_list_parser.add_argument("--trace-id", help="Optional exact trace_id filter.")
    planner_log_list_parser.add_argument("--since", help="Optional ISO datetime lower bound (inclusive).")
    planner_log_list_parser.add_argument("--limit", type=int, default=20, help="Maximum number of results (recent first).")
    planner_log_list_parser.add_argument("--json", action="store_true", help="Return full JSON records.")

    planner_log_rollback_parser = subparsers.add_parser(
        "planner-log-rollback",
        help="Preview append-only planner-log rollback markers without writing them.",
    )
    planner_log_rollback_mode = planner_log_rollback_parser.add_mutually_exclusive_group(required=True)
    planner_log_rollback_mode.add_argument("--dry-run", action="store_true", help="Preview without writing rollback markers.")
    planner_log_rollback_mode.add_argument("--apply", action="store_true", help="Append missing rollback markers.")
    planner_log_rollback_parser.add_argument("--signal-id", default=None)
    planner_log_rollback_parser.add_argument("--trace-id", default=None)
    planner_log_rollback_parser.add_argument("--limit", type=int, default=20)

    audit_preview_parser = subparsers.add_parser(
        "audit-preview",
        help="Preview a universal audit stream backfill without writing audit.jsonl.",
    )
    audit_preview_parser.add_argument("--dry-run", action="store_true", help="Required; preview only.")
    audit_preview_parser.add_argument("--limit", type=int, default=50)

    audit_backfill_parser = subparsers.add_parser(
        "audit-backfill",
        help="Backfill the universal audit stream from existing audit sources.",
    )
    audit_backfill_mode = audit_backfill_parser.add_mutually_exclusive_group(required=True)
    audit_backfill_mode.add_argument("--dry-run", action="store_true", help="Preview without writing audit.jsonl.")
    audit_backfill_mode.add_argument("--apply", action="store_true", help="Append missing audit records.")
    audit_backfill_parser.add_argument("--limit", type=int, default=50)

    protocol_learn_age_parser = subparsers.add_parser(
        "protocol-learn-age",
        help="Scan protocol learnings for aging and optionally apply stale transitions.",
    )
    protocol_learn_age_parser.add_argument("--protocol", help="可选：仅扫描指定 protocol。")
    protocol_learn_age_parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入 active → stale 变更；默认仅 dry-run。",
    )

    protocol_learn_verify_parser = subparsers.add_parser(
        "protocol-learn-verify",
        help="Verify a protocol learning and restore it to active.",
    )
    protocol_learn_verify_parser.add_argument("learning_id", help="Learning id.")

    protocol_learn_revert_activate_parser = subparsers.add_parser(
        "protocol-learn-revert-activate",
        help="Revert the latest supported stale -> active protocol learning activation.",
    )
    protocol_learn_revert_activate_parser.add_argument("learning_id", help="Learning id.")
    protocol_learn_revert_activate_parser.add_argument("--note", help="Optional revert note.")

    protocol_learn_demote_parser = subparsers.add_parser(
        "protocol-learn-demote",
        help="Demote a protocol learning.",
    )
    protocol_learn_demote_parser.add_argument("learning_id", help="Learning id.")

    protocol_learn_archive_parser = subparsers.add_parser(
        "protocol-learn-archive",
        help="Archive a protocol learning.",
    )
    protocol_learn_archive_parser.add_argument("learning_id", help="Learning id.")

    protocol_learn_supersede_parser = subparsers.add_parser(
        "protocol-learn-supersede",
        help="Supersede one or more protocol learnings with an active replacement learning.",
    )
    protocol_learn_supersede_parser.add_argument("replacement_id", help="Active replacement learning id.")
    protocol_learn_supersede_parser.add_argument(
        "superseded_ids",
        nargs="+",
        help="One or more target learning ids to mark as superseded.",
    )

    run_ask_parser = subparsers.add_parser(
        "run-ask",
        help="Create a query artifact and use the configured LLM to fill it in place.",
    )
    run_ask_parser.add_argument("question", help="Research question to answer.")
    run_ask_parser.add_argument(
        "--format",
        choices=("report", "decision-memo", "sop", "slides", "figure"),
        default="report",
        help="Output artifact format.",
    )
    run_ask_parser.add_argument("--protocol", help="Optional protocol override for this query.")
    run_ask_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass volatile SQLite query cache and force deterministic JSON scan.",
    )
    run_ask_parser.add_argument(
        "--lean",
        action="store_true",
        help="Start with a smaller prompt profile for stability instead of waiting for timeout retry.",
    )
    run_ask_parser.add_argument(
        "--timeout",
        type=int,
        help="Override the LLM timeout seconds for this run only.",
    )
    run_ask_parser.add_argument(
        "--fallback-to-ask",
        action="store_true",
        help="If the LLM backend is unavailable, return the deterministic ask artifact from the same runtime call.",
    )
    run_ask_parser.add_argument("--corpus", help="Optional active corpus id to reuse across ask rounds.")

    file_back_parser = subparsers.add_parser(
        "file-back",
        help="File a markdown artifact back into wiki/derived, wiki/decisions, or wiki/judgments.",
    )
    file_back_parser.add_argument("artifact", help="Path to a markdown artifact.")
    file_back_parser.add_argument("--title", help="Optional filed-back title.")
    file_back_parser.add_argument(
        "--kind",
        choices=("derived", "decision", "judgment"),
        default="derived",
        help="Filed-back page kind.",
    )
    file_back_parser.add_argument("--protocol", help="Optional protocol override for the filed-back page.")

    promote_parser = subparsers.add_parser("promote", help="Promote an output candidate into wiki/derived.")
    promote_parser.add_argument("artifact_ref", help="Output candidate artifact_ref.")

    demote_parser = subparsers.add_parser("demote", help="Mark an output candidate as demoted.")
    demote_parser.add_argument("artifact_ref", help="Output candidate artifact_ref.")

    alchemy_start_parser = subparsers.add_parser("alchemy-start", help="Start a new elixir from a corpus.")
    alchemy_start_parser.add_argument("corpus_id")
    alchemy_start_parser.add_argument("--topic", required=True)
    alchemy_start_parser.add_argument("--protocol", required=True)
    alchemy_start_parser.add_argument("--include-elixir", type=str, default=None, help="可选：额外包含的金丹 id，多个用逗号分隔。")

    alchemy_distill_parser = subparsers.add_parser("alchemy-distill", help="Distill an existing draft elixir.")
    alchemy_distill_parser.add_argument("elixir_id")
    alchemy_distill_parser.add_argument("--question", required=True)
    alchemy_distill_parser.add_argument("--include-elixir", type=str, default=None, help="可选：额外包含的金丹 id，多个用逗号分隔。")

    alchemy_finalize_parser = subparsers.add_parser(
        "alchemy-finalize",
        help="Finalize a draft/distilling elixir into candidate state.",
    )
    alchemy_finalize_parser.add_argument("--elixir-id", required=True)

    alchemy_promote_parser = subparsers.add_parser(
        "alchemy-promote",
        help="Promote a candidate elixir into settled with receipt+tombstone.",
    )
    alchemy_promote_parser.add_argument("--elixir-id", required=True)
    alchemy_promote_parser.add_argument("--note", default=None)

    alchemy_revert_parser = subparsers.add_parser(
        "alchemy-revert",
        help="Revert the latest elixir promote from settled back to candidate.",
    )
    alchemy_revert_parser.add_argument("--elixir-id", required=True)
    alchemy_revert_parser.add_argument("--note", default=None)

    alchemy_demote_parser = subparsers.add_parser(
        "alchemy-demote",
        help="Demote a settled elixir back to candidate using current settled content.",
    )
    alchemy_demote_parser.add_argument("--elixir-id", required=True)
    alchemy_demote_parser.add_argument("--note", default=None)

    alchemy_parser = subparsers.add_parser(
        "alchemy",
        help="Preview heavy/light alchemy lanes. M4 supports dry-run only.",
    )
    alchemy_subparsers = alchemy_parser.add_subparsers(dest="alchemy_lane", required=True)
    for lane_name in ("heavy", "light"):
        lane_parser = alchemy_subparsers.add_parser(
            lane_name,
            help=f"Preview the {lane_name} alchemy lane without executing primitives.",
        )
        lane_parser.add_argument(
            "scope",
            help="Scope selector: all, protocol:<name>, source:<id>, concept:<slug>, elixir:<ref>, or judgment:<ref>.",
        )
        lane_parser.add_argument("--dry-run", action="store_true", help="Preview without executing primitives.")
        lane_parser.add_argument("--apply", action="store_true", help="M5 controlled apply bridge for explicit receipted action ids.")
        lane_parser.add_argument("--action-id", action="append", default=[], help="Machine-memory action id to apply; may be repeated.")
        lane_parser.add_argument(
            "--primitive",
            action="append",
            default=[],
            choices=("compile", "lint", "nightly", "review", "propose", "distill"),
            help="Receipted lane primitive to apply; may be repeated.",
        )
        lane_parser.add_argument("--note", default=None)
        lane_parser.add_argument("--planner-log-path", type=Path, default=None)
        lane_parser.add_argument("--signals-path", type=Path, default=None)
        lane_parser.add_argument("--max-signals", type=int, default=None)
        lane_parser.add_argument("--max-pages", type=int, default=None)
        lane_parser.add_argument("--max-tokens", type=int, default=None)
    judge_parser = alchemy_subparsers.add_parser(
        "judge",
        help="Preview scoped judgment refresh candidates without applying them.",
    )
    judge_parser.add_argument(
        "scope",
        help="Scope selector: all, protocol:<name>, source:<id>, concept:<slug>, elixir:<ref>, or judgment:<ref>.",
    )
    judge_mode = judge_parser.add_mutually_exclusive_group(required=True)
    judge_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    judge_mode.add_argument("--apply", action="store_true", help="Apply deterministic scoped judge refresh markers with receipt/audit.")
    judge_mode.add_argument("--propose", action="store_true", help="Create semantic judge proposal-preview artifacts without mutating target pages.")
    judge_parser.add_argument("--planner-log-path", type=Path, default=None)
    judge_parser.add_argument("--signals-path", type=Path, default=None)
    judge_parser.add_argument("--max-signals", type=int, default=None)
    judge_parser.add_argument("--max-pages", type=int, default=None)
    judge_parser.add_argument("--max-tokens", type=int, default=None)
    judge_parser.add_argument("--limit", type=int, default=50)
    judge_parser.add_argument("--note", default=None)
    judge_proposal_parser = alchemy_subparsers.add_parser(
        "judge-proposal",
        help="Apply an accepted semantic judge proposal artifact.",
    )
    judge_proposal_parser.add_argument("proposal")
    judge_proposal_parser.add_argument("--apply", action="store_true", required=True)
    judge_proposal_parser.add_argument("--note", default=None)
    distill_preview_parser = alchemy_subparsers.add_parser(
        "distill",
        help="Preview scoped elixir distillation candidates without applying them.",
    )
    distill_preview_parser.add_argument(
        "scope",
        help="Scope selector: all, protocol:<name>, source:<id>, concept:<slug>, elixir:<ref>, or judgment:<ref>.",
    )
    distill_preview_mode = distill_preview_parser.add_mutually_exclusive_group(required=True)
    distill_preview_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    distill_preview_mode.add_argument("--apply", action="store_true", help="Refresh existing scoped elixir candidates with receipt/audit.")
    distill_preview_parser.add_argument("--planner-log-path", type=Path, default=None)
    distill_preview_parser.add_argument("--signals-path", type=Path, default=None)
    distill_preview_parser.add_argument("--max-signals", type=int, default=None)
    distill_preview_parser.add_argument("--max-pages", type=int, default=None)
    distill_preview_parser.add_argument("--max-tokens", type=int, default=None)
    distill_preview_parser.add_argument("--limit", type=int, default=50)
    distill_preview_parser.add_argument("--note", default=None)
    review_preview_parser = alchemy_subparsers.add_parser(
        "review",
        help="Preview scoped review enqueue candidates without applying them.",
    )
    review_preview_parser.add_argument(
        "scope",
        help="Scope selector: all, protocol:<name>, source:<id>, concept:<slug>, elixir:<ref>, or judgment:<ref>.",
    )
    review_preview_mode = review_preview_parser.add_mutually_exclusive_group(required=True)
    review_preview_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    review_preview_mode.add_argument("--apply", action="store_true", help="Apply scoped review enqueue with receipt/audit.")
    review_preview_parser.add_argument("--planner-log-path", type=Path, default=None)
    review_preview_parser.add_argument("--signals-path", type=Path, default=None)
    review_preview_parser.add_argument("--max-signals", type=int, default=None)
    review_preview_parser.add_argument("--max-pages", type=int, default=None)
    review_preview_parser.add_argument("--max-tokens", type=int, default=None)
    review_preview_parser.add_argument("--limit", type=int, default=50)
    review_preview_parser.add_argument("--note", default=None)
    propose_preview_parser = alchemy_subparsers.add_parser(
        "propose",
        help="Preview scoped proposal opportunities without applying them.",
    )
    propose_preview_parser.add_argument(
        "scope",
        help="Scope selector: all, protocol:<name>, source:<id>, concept:<slug>, elixir:<ref>, or judgment:<ref>.",
    )
    propose_preview_mode = propose_preview_parser.add_mutually_exclusive_group(required=True)
    propose_preview_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    propose_preview_mode.add_argument("--apply", action="store_true", help="Create scoped L3 proposal candidates.")
    propose_preview_parser.add_argument("--planner-log-path", type=Path, default=None)
    propose_preview_parser.add_argument("--signals-path", type=Path, default=None)
    propose_preview_parser.add_argument("--max-signals", type=int, default=None)
    propose_preview_parser.add_argument("--max-pages", type=int, default=None)
    propose_preview_parser.add_argument("--max-tokens", type=int, default=None)
    propose_preview_parser.add_argument("--limit", type=int, default=50)
    propose_preview_parser.add_argument("--note", default=None)
    legacy_migration_parser = alchemy_subparsers.add_parser(
        "legacy-migration",
        help="Preview legacy wiki/elixirs entries that lack candidate tombstones.",
    )
    legacy_migration_mode = legacy_migration_parser.add_mutually_exclusive_group(required=True)
    legacy_migration_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    legacy_migration_mode.add_argument("--apply", action="store_true", help="Create missing candidate tombstones.")
    legacy_migration_parser.add_argument("--limit", type=int, default=50)
    legacy_migration_parser.add_argument("--note", default=None)
    auto_parser = alchemy_subparsers.add_parser(
        "auto",
        help="Preview or apply execute-mode planner decisions through safe alchemy lanes.",
    )
    auto_mode = auto_parser.add_mutually_exclusive_group(required=True)
    auto_mode.add_argument("--dry-run", action="store_true", help="Preview scheduler decisions only.")
    auto_mode.add_argument("--apply", action="store_true", help="Run deterministic apply-supported lane primitives.")
    auto_parser.add_argument("--scope", default="all")
    auto_parser.add_argument("--lane", action="append", choices=("heavy", "light"), default=[])
    auto_parser.add_argument(
        "--primitive",
        action="append",
        choices=("compile", "lint", "nightly"),
        default=[],
        help="Restrict automatic execution to one or more deterministic primitives.",
    )
    auto_parser.add_argument("--note", default=None)
    auto_parser.add_argument("--planner-log-path", type=Path, default=None)
    auto_parser.add_argument("--signals-path", type=Path, default=None)
    auto_parser.add_argument("--max-signals", type=int, default=None)
    auto_parser.add_argument("--max-pages", type=int, default=None)
    auto_parser.add_argument("--max-tokens", type=int, default=None)
    superseded_cleanup_parser = alchemy_subparsers.add_parser(
        "superseded-cleanup",
        help="Preview or apply superseded elixir candidate tombstone cleanup.",
    )
    superseded_cleanup_mode = superseded_cleanup_parser.add_mutually_exclusive_group(required=True)
    superseded_cleanup_mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    superseded_cleanup_mode.add_argument("--apply", action="store_true", help="Delete supported superseded tombstones.")
    superseded_cleanup_parser.add_argument("--limit", type=int, default=50)
    superseded_cleanup_parser.add_argument("--note", default=None)

    l3_create_parser = subparsers.add_parser(
        "l3-proposal-create",
        help="Create a manual L3 prompt/policy proposal fixture without applying it.",
    )
    l3_create_parser.add_argument("--kind", required=True, choices=("prompt_proposal", "policy_proposal"))
    l3_create_parser.add_argument("--proposal-id", default=None)
    l3_create_parser.add_argument("--target-file", required=True)
    l3_create_parser.add_argument("--content-file", required=True)
    l3_create_parser.add_argument("--rationale", default="")
    l3_create_parser.add_argument("--evidence-ref", action="append", dest="evidence_refs", default=[])
    l3_create_parser.add_argument("--signal-id", action="append", dest="signal_ids", default=[])
    l3_create_parser.add_argument(
        "--pattern",
        default="manual_fixture",
        choices=("failure_cluster", "recurring_feedback", "drift", "contract_failure", "manual_fixture"),
    )
    l3_generate_parser = subparsers.add_parser(
        "l3-proposal-generate",
        help="Generate L3 proposal candidates from execute-mode planner decisions.",
    )
    l3_generate_mode = l3_generate_parser.add_mutually_exclusive_group(required=True)
    l3_generate_mode.add_argument("--dry-run", action="store_true", help="Preview generation candidates only.")
    l3_generate_mode.add_argument("--apply", action="store_true", help="Create eligible proposal candidates.")
    l3_generate_parser.add_argument("--planner-log-path", type=Path, default=None)
    l3_generate_parser.add_argument("--limit", type=int, default=20)

    review_group_parser = subparsers.add_parser("review", help="Review queue inspection commands.")
    review_group_subparsers = review_group_parser.add_subparsers(dest="review_command", required=True)
    review_proposals_parser = review_group_subparsers.add_parser(
        "proposals",
        help="List L3 prompt/policy proposals without mutating targets.",
    )
    review_proposals_parser.add_argument("--kind", choices=("prompt_proposal", "policy_proposal"))
    review_proposals_parser.add_argument(
        "--state",
        choices=("candidate", "accepted", "rejected", "reverted", "stale", "revert_conflict"),
    )
    review_proposals_parser.add_argument("--json", action="store_true", help="Return full JSON records.")
    review_proposal_generation_parser = review_group_subparsers.add_parser(
        "proposal-generation",
        help="Preview L3 proposal generation candidates from planner-log.",
    )
    review_proposal_generation_parser.add_argument("--planner-log-path", type=Path, default=None)
    review_proposal_generation_parser.add_argument("--limit", type=int, default=20)
    review_proposal_generation_parser.add_argument("--json", action="store_true", help="Return full JSON payload.")
    review_proposal_parser = review_group_subparsers.add_parser(
        "proposal",
        help="Review one L3 prompt/policy proposal.",
    )
    review_proposal_parser.add_argument("proposal_id")
    review_proposal_parser.add_argument("--status", required=True, choices=("rejected",))
    review_proposal_parser.add_argument("--note")

    apply_parser = subparsers.add_parser("apply", help="Accept and apply a manual L3 proposal by id.")
    apply_parser.add_argument("proposal_id")
    apply_parser.add_argument("--note")

    revert_parser = subparsers.add_parser("revert", help="Revert an L3 proposal apply receipt.")
    revert_parser.add_argument("receipt_id")
    revert_parser.add_argument("--note")

    review_parser = subparsers.add_parser(
        "review-page",
        help="Advance a decision or judgment page through the explicit review workflow.",
    )
    review_parser.add_argument("page", nargs="?", help="Path to a decision or judgment markdown page.")
    review_parser.add_argument("--status", required=True, help="Target review status for the page.")
    review_parser.add_argument("--note", help="Optional review note to store in the page.")
    review_parser.add_argument("--confidence", help="Optional confidence override for judgment pages.")
    review_parser.add_argument(
        "--next",
        action="store_true",
        help="Auto-select the highest-priority review page from the current shell summary.",
    )
    review_parser.add_argument(
        "--batch",
        nargs="+",
        help="Review multiple pages in one batch receipt.",
    )
    review_parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Review every currently reviewable page from the shell summary.",
    )

    rewrite_review_parser = subparsers.add_parser(
        "review-rewrite",
        help="Advance a concept rewrite proposal through the explicit rewrite workflow.",
    )
    rewrite_review_parser.add_argument("slug", help="Concept slug.")
    rewrite_review_parser.add_argument("--status", required=True, help="Target rewrite proposal status.")
    rewrite_review_parser.add_argument("--note", help="Optional review note.")

    apply_rewrite_parser = subparsers.add_parser(
        "apply-rewrite",
        help="Apply an accepted concept rewrite proposal to the target concept page.",
    )
    apply_rewrite_parser.add_argument("slug", help="Concept slug.")
    apply_rewrite_parser.add_argument("--note", help="Optional apply note.")
    apply_rewrite_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write a rewrite preview artifact without mutating the concept page.",
    )

    verify_rewrite_parser = subparsers.add_parser(
        "verify-rewrite",
        help="Verify that an applied concept rewrite still matches the current concept/runtime state.",
    )
    verify_rewrite_parser.add_argument("slug", help="Concept slug.")
    verify_rewrite_parser.add_argument("--note", help="Optional verification note.")

    revert_rewrite_parser = subparsers.add_parser(
        "revert-rewrite",
        help="Revert the latest applied concept rewrite and restore the previous concept snapshot.",
    )
    revert_rewrite_parser.add_argument("slug", help="Concept slug.")
    revert_rewrite_parser.add_argument("--note", help="Optional revert note.")

    retire_concept_parser = subparsers.add_parser(
        "retire-concept",
        help="Apply an explicit concept lifecycle override and retire a concept from default query ranking.",
    )
    retire_concept_parser.add_argument("slug", help="Concept slug.")
    retire_concept_parser.add_argument("--note", help="Optional retire note.")

    reactivate_concept_parser = subparsers.add_parser(
        "reactivate-concept",
        help="Clear the active retired override for a concept and return it to heuristic lifecycle routing.",
    )
    reactivate_concept_parser.add_argument("slug", help="Concept slug.")
    reactivate_concept_parser.add_argument("--note", help="Optional reactivate note.")

    action_review_parser = subparsers.add_parser(
        "review-action",
        help="Advance a machine-memory repair action through the explicit action workflow.",
    )
    action_review_parser.add_argument("action_id", help="Machine-memory action id or title fragment.")
    action_review_parser.add_argument("--status", required=True, help="Target action status.")
    action_review_parser.add_argument("--note", help="Optional action review note.")

    apply_action_parser = subparsers.add_parser(
        "apply-action",
        help="Apply an accepted low-risk machine-memory repair action through the safe execution layer.",
    )
    apply_action_parser.add_argument("action_id", nargs="?", help="Machine-memory action id or title fragment.")
    apply_action_parser.add_argument("--note", help="Optional apply note.")
    apply_action_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the safe-apply bundle without mutating manual-link state.",
    )
    apply_action_parser.add_argument(
        "--bundle",
        help="Optional execution bundle path to validate and consume during apply.",
    )
    apply_action_parser.add_argument(
        "--batch",
        nargs="+",
        help="Apply multiple action ids/title fragments in one batch receipt.",
    )
    apply_action_parser.add_argument(
        "--all-accepted-low-risk",
        action="store_true",
        help="Apply every currently accepted low-risk action as a batch.",
    )

    revert_action_parser = subparsers.add_parser(
        "revert-action",
        help="Revert the latest low-risk safe apply for a machine-memory action.",
    )
    revert_action_parser.add_argument("action_id", nargs="?", help="Machine-memory action id.")
    revert_action_parser.add_argument("--note", help="Optional revert note.")
    revert_action_parser.add_argument(
        "--last-batch",
        action="store_true",
        help="Revert the most recent unreverted action apply batch.",
    )

    apply_archive_parser = subparsers.add_parser(
        "apply-archive",
        help="Apply a ready archive candidate and pin the material temperature to archived.",
    )
    apply_archive_parser.add_argument("entry_id", help="Manifest/material entry id.")
    apply_archive_parser.add_argument("--note", help="Optional apply note.")
    apply_archive_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write an archive bundle preview without mutating material state.",
    )

    revert_archive_parser = subparsers.add_parser(
        "revert-archive",
        help="Revert the latest explicit archive transition and restore the material to cold.",
    )
    revert_archive_parser.add_argument("entry_id", help="Manifest/material entry id.")
    revert_archive_parser.add_argument("--note", help="Optional revert note.")

    subparsers.add_parser("lint", help="Run deterministic lint checks against the wiki.")
    subparsers.add_parser("run-lint", help="Run deterministic lint plus an LLM-backed semantic lint pass.")
    subparsers.add_parser("nightly", help="Run deterministic compile + lint and write nightly repair artifacts.")
    run_nightly_parser = subparsers.add_parser(
        "run-nightly",
        help="Run compile + semantic lint and write nightly repair artifacts.",
    )
    run_nightly_parser.add_argument(
        "--compile-limit",
        type=int,
        default=5,
        help="Maximum number of pending source pages to summarize in one run.",
    )
    run_nightly_parser.add_argument(
        "--no-semantic-lint",
        action="store_true",
        help="Skip the semantic lint pass and write deterministic nightly artifacts only.",
    )
    signals_replay_parser = subparsers.add_parser(
        "signals-replay",
        help="Replay runtime signal sources into .aiwiki/state/signals.jsonl.",
    )
    signals_replay_parser.add_argument(
        "--source",
        action="append",
        choices=("runtime_history", "llm_receipt", "archive"),
        help="Signal source to replay; may be repeated. Defaults to all sources.",
    )
    signals_replay_parser.add_argument(
        "--trace-id",
        help="Optional lowercase UUIDv4 trace id for this replay batch.",
    )
    planner_log_replay_parser = subparsers.add_parser(
        "planner-log-replay",
        help="Replay signals to planner-log.",
    )
    planner_log_replay_parser.add_argument("--signals-path", type=Path, default=None)
    planner_log_replay_parser.add_argument(
        "--execute",
        action="store_true",
        help="Write execute-mode planner decisions. Default remains observe-only.",
    )
    llm_check_parser = subparsers.add_parser("llm-check", help="Show whether the LLM runner is configured.")
    llm_check_parser.add_argument(
        "--probe",
        action="store_true",
        help="Run a tiny real completion against the current effective backend.",
    )
    llm_check_parser.add_argument(
        "--probe-all",
        action="store_true",
        help="Probe every discovered CLI backend individually. Implies --probe.",
    )
    llm_check_parser.add_argument(
        "--probe-timeout",
        type=int,
        default=20,
        help="Timeout in seconds for each LLM probe request.",
    )

    cache_parser = subparsers.add_parser("cache", help="Inspect, rebuild, or drop the volatile SQLite query cache.")
    cache_parser.add_argument(
        "--status",
        action="store_true",
        help="Show the current cache status summary.",
    )
    cache_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a rebuild of the volatile cache from the latest snapshot.",
    )
    cache_parser.add_argument(
        "--drop",
        action="store_true",
        help="Delete `.aiwiki/cache.db` unconditionally.",
    )

    auto_once_parser = subparsers.add_parser(
        "auto-once",
        help="Automatically process the inbox once: compile, summarize, and lint.",
    )
    auto_once_parser.add_argument(
        "--compile-limit",
        type=int,
        default=5,
        help="Maximum number of pending source pages to summarize in one run.",
    )
    auto_once_parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Skip the LLM layer and run deterministic compile + lint only.",
    )
    auto_once_parser.add_argument(
        "--no-semantic-lint",
        action="store_true",
        help="Skip the LLM semantic lint pass.",
    )

    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch raw/inbox and automatically process changes in the background loop.",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds.",
    )
    watch_parser.add_argument(
        "--compile-limit",
        type=int,
        default=5,
        help="Maximum number of pending source pages to summarize per run.",
    )
    watch_parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Skip the LLM layer and run deterministic compile + lint only.",
    )
    watch_parser.add_argument(
        "--no-semantic-lint",
        action="store_true",
        help="Skip the LLM semantic lint pass.",
    )
    watch_parser.add_argument(
        "--skip-initial",
        action="store_true",
        help="Do not process the current inbox state immediately on startup.",
    )
    watch_parser.add_argument(
        "--max-cycles",
        type=int,
        help="Stop after N polling cycles. Useful for tests and short-lived runs.",
    )
    _set_handler_command_defaults(subparsers)


def _set_handler_command_defaults(subparsers: argparse._SubParsersAction, handler_command: str | None = None) -> None:
    for name, choice in subparsers.choices.items():
        canonical_command = handler_command or name
        choice.set_defaults(handler_command=canonical_command)
        for action in choice._actions:
            if isinstance(action, argparse._SubParsersAction):
                _set_handler_command_defaults(action, canonical_command)


def _register_drop_subcommand_parsers(subparsers: argparse._SubParsersAction) -> None:
    drop_url_parser = subparsers.add_parser("url", help="Fetch a web page into raw/inbox as source material.")
    _configure_drop_url_parser(drop_url_parser)
    drop_url_parser.set_defaults(handler_command="drop-url")

    drop_pdf_parser = subparsers.add_parser("pdf", help="Import a PDF into raw/assets and raw/inbox.")
    _configure_drop_pdf_parser(drop_pdf_parser)
    drop_pdf_parser.set_defaults(handler_command="drop-pdf")

    drop_image_parser = subparsers.add_parser("image", help="Import an image into raw/assets and raw/inbox.")
    _configure_drop_image_parser(drop_image_parser)
    drop_image_parser.set_defaults(handler_command="drop-image")

    drop_repo_parser = subparsers.add_parser("repo", help="Snapshot a local or remote repo into raw/inbox.")
    _configure_drop_repo_parser(drop_repo_parser)
    drop_repo_parser.set_defaults(handler_command="drop-repo")

    drop_note_parser = subparsers.add_parser("note", help="Capture a free-text note or transcript into raw/inbox.")
    _configure_drop_note_parser(drop_note_parser)
    drop_note_parser.set_defaults(handler_command="drop-note")

    drop_question_parser = subparsers.add_parser("question", help="Generate a deterministic query artifact grounded in the wiki.")
    _configure_ask_parser(drop_question_parser)
    drop_question_parser.set_defaults(handler_command="ask")


def _configure_drop_url_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="Web URL to fetch.")
    parser.add_argument("--title", help="Optional display title.")
    _add_auto_flags(parser)


def _configure_drop_pdf_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="Local PDF path or PDF URL.")
    parser.add_argument("--title", help="Optional display title.")
    _add_auto_flags(parser)


def _configure_drop_image_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="Local image path or image URL.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip optional LLM-backed visual analysis for the image note.",
    )
    _add_auto_flags(parser)


def _configure_drop_repo_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="Local repo path or remote git URL.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--max-files",
        type=int,
        default=200,
        help="Maximum number of repo tree entries to capture.",
    )
    _add_auto_flags(parser)


def _configure_drop_note_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", nargs="?", help="Optional markdown or text file path.")
    parser.add_argument("--text", help="Inline note text. Use this instead of SOURCE for free-text capture.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--kind",
        choices=("note", "transcript"),
        default="note",
        help="Capture kind. Transcript enables transcript-aware compile prompts.",
    )
    _add_auto_flags(parser)


def _configure_ask_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("question", help="Research question to package.")
    parser.add_argument(
        "--format",
        choices=("report", "decision-memo", "sop", "slides", "figure"),
        default="report",
        help="Output artifact format.",
    )
    parser.add_argument("--protocol", help="Optional protocol override for this query.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass volatile SQLite query cache and force deterministic JSON scan.",
    )
    parser.add_argument("--corpus", help="Optional active corpus id to reuse across ask rounds.")
    parser.add_argument("--load-learnings", action="store_true", help="Load protocol learnings into the prompt.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    text_output: str | None = None
    fallback_env_was_set = "AIWIKI_MODEL_FALLBACK" in os.environ
    previous_fallback_env = os.environ.get("AIWIKI_MODEL_FALLBACK", "")
    if args.model_fallback is not None:
        os.environ["AIWIKI_MODEL_FALLBACK"] = ",".join(_flatten_model_fallback_args(args.model_fallback))

    try:
        _emit_legacy_drop_deprecation_warning(args)
        if args.handler_command == "layout":
            ensure_layout(root)
            result = {"root": str(root), "status": "ok"}
        elif args.handler_command == "new-vault":
            result = bootstrap_new_vault(root, Path(args.target).resolve(), force=args.force)
        elif args.handler_command == "ingest":
            result = ingest_source(root, args.source, title=args.title)
        elif args.handler_command == "drop-url":
            result = drop_url(root, args.url, title=args.title)
            result = _maybe_auto_process(root, result, args)
        elif args.handler_command == "drop-pdf":
            result = drop_pdf(root, args.source, title=args.title)
            result = _maybe_auto_process(root, result, args)
        elif args.handler_command == "drop-image":
            result = drop_image(root, args.source, title=args.title, enable_vision=not args.no_vision)
            result = _maybe_auto_process(root, result, args)
        elif args.handler_command == "drop-repo":
            result = drop_repo(root, args.source, title=args.title, max_files=args.max_files)
            result = _maybe_auto_process(root, result, args)
        elif args.handler_command == "drop-note":
            result = drop_note(root, args.source, title=args.title, text=args.text, kind=args.kind)
            result = _maybe_auto_process(root, result, args)
        elif args.handler_command == "compile":
            result = compile_wiki(root)
            rewrite_state = result.get("concept_rewrite") or {}
            proposal_paths = [
                str(path or "")
                for path in rewrite_state.get("proposal_paths", [])
                if str(path or "")
            ]
            if proposal_paths:
                result = {
                    **result,
                    **rewrite_recovery_payload_for_paths(root, proposal_paths),
                }
        elif args.handler_command == "protocol-status":
            if args.set_protocol:
                result = set_active_protocol(root, args.set_protocol)
            else:
                result = load_protocol_state(root)
        elif args.handler_command == "protocol-set":
            result = set_active_protocol(root, args.protocol)
        elif args.handler_command == "today":
            return today_command(root)
        elif args.handler_command == "shell-status":
            result = shell_status(root)
        elif args.handler_command == "dashboard":
            result = shell_status_dashboard(root)
        elif args.handler_command == "search":
            result = shell_search(root, args.query, limit=args.limit)
        elif args.handler_command == "run-compile":
            result = run_compile(root, limit=args.limit)
        elif args.handler_command == "ask":
            ask_kwargs = {"protocol": args.protocol, "no_cache": args.no_cache, "load_protocol_learnings": args.load_learnings}
            if getattr(args, "corpus", None) is not None:
                ask_kwargs["corpus_id_override"] = args.corpus
            result = ask_question(root, args.question, args.format, **ask_kwargs)
        elif args.handler_command == "run-ask":
            ask_kwargs = {
                "protocol": args.protocol,
                "lean": args.lean,
                "timeout_seconds": args.timeout,
                "no_cache": args.no_cache,
                "fallback_to_ask": args.fallback_to_ask,
            }
            if hasattr(args, "corpus") and args.corpus is not None:
                ask_kwargs["corpus_id_override"] = args.corpus
            result = run_ask(root, args.question, args.format, **ask_kwargs)
        elif args.handler_command == "file-back":
            result = file_back(root, args.artifact, title=args.title, kind=args.kind, protocol=args.protocol)
        elif args.handler_command == "promote":
            result = run_promote(root, args.artifact_ref)
        elif args.handler_command == "demote":
            result = run_demote(root, args.artifact_ref)
        elif args.handler_command == "alchemy-start":
            include_elixir_ids = None
            if args.include_elixir is not None:
                include_elixir_ids = [item.strip() for item in args.include_elixir.split(",")]
            kwargs = {"protocol": args.protocol}
            if include_elixir_ids is not None:
                kwargs["include_elixir_ids"] = include_elixir_ids
            result = run_alchemy_start(root, args.corpus_id, args.topic, **kwargs)
        elif args.handler_command == "alchemy-distill":
            include_elixir_ids = None
            if args.include_elixir is not None:
                include_elixir_ids = [item.strip() for item in args.include_elixir.split(",")]
            kwargs = {}
            if include_elixir_ids is not None:
                kwargs["include_elixir_ids"] = include_elixir_ids
            result = run_alchemy_distill(root, args.elixir_id, args.question, **kwargs)
        elif args.handler_command == "alchemy-finalize":
            result = run_alchemy_finalize(root, elixir_id=args.elixir_id)
        elif args.handler_command == "alchemy-promote":
            result = run_alchemy_promote(root, elixir_id=args.elixir_id, note=args.note)
        elif args.handler_command == "alchemy-revert":
            path = run_alchemy_revert(root, elixir_id=args.elixir_id, note=args.note)
            result = {"elixir_id": args.elixir_id, "path": str(path.relative_to(root))}
        elif args.handler_command == "alchemy-demote":
            path = run_alchemy_demote(root, elixir_id=args.elixir_id, note=args.note)
            result = {"elixir_id": args.elixir_id, "path": str(path.relative_to(root))}
        elif args.handler_command == "alchemy":
            if args.alchemy_lane == "legacy-migration":
                if args.dry_run:
                    result = run_alchemy_legacy_migration_preview(root, limit=args.limit)
                else:
                    result = run_alchemy_legacy_migration_apply(root, limit=args.limit, note=args.note)
            elif args.alchemy_lane == "judge":
                if args.apply:
                    result = run_alchemy_judge_apply(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                        note=args.note,
                    )
                elif args.propose:
                    result = run_alchemy_judge_propose(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                        note=args.note,
                    )
                else:
                    result = run_alchemy_judge_preview(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                    )
            elif args.alchemy_lane == "judge-proposal":
                result = run_alchemy_judge_proposal_apply(root, args.proposal, note=args.note)
            elif args.alchemy_lane == "distill":
                if args.apply:
                    result = run_alchemy_distill_apply(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                        note=args.note,
                    )
                else:
                    result = run_alchemy_distill_preview(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                    )
            elif args.alchemy_lane == "review":
                if args.apply:
                    result = run_alchemy_review_apply(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                        note=args.note,
                    )
                else:
                    result = run_alchemy_review_preview(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                    )
            elif args.alchemy_lane == "propose":
                if args.apply:
                    result = run_alchemy_propose_apply(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                        note=args.note,
                    )
                else:
                    result = run_alchemy_propose_preview(
                        root,
                        scope=args.scope,
                        planner_log_path=args.planner_log_path,
                        signals_path=args.signals_path,
                        max_signals=args.max_signals,
                        max_pages=args.max_pages,
                        max_tokens=args.max_tokens,
                        limit=args.limit,
                    )
            elif args.alchemy_lane == "auto":
                result = run_alchemy_auto(
                    root,
                    apply=args.apply,
                    lanes=args.lane or None,
                    scope=args.scope,
                    primitives=args.primitive or None,
                    note=args.note,
                    planner_log_path=args.planner_log_path,
                    signals_path=args.signals_path,
                    max_signals=args.max_signals,
                    max_pages=args.max_pages,
                    max_tokens=args.max_tokens,
                )
            elif args.alchemy_lane == "superseded-cleanup":
                if args.dry_run:
                    result = run_alchemy_superseded_cleanup_preview(root, limit=args.limit)
                else:
                    result = run_alchemy_superseded_cleanup_apply(root, limit=args.limit, note=args.note)
            else:
                if args.dry_run == args.apply:
                    raise ValueError("alchemy heavy/light requires exactly one of --dry-run or --apply")
                lane_kwargs = {
                    "lane": args.alchemy_lane,
                    "scope": args.scope,
                    "planner_log_path": args.planner_log_path,
                    "signals_path": args.signals_path,
                    "max_signals": args.max_signals,
                    "max_pages": args.max_pages,
                    "max_tokens": args.max_tokens,
                }
                if args.dry_run:
                    result = run_alchemy_lane_dry_run(root, **lane_kwargs)
                else:
                    result = run_alchemy_lane_apply(
                        root,
                        action_ids=args.action_id,
                        primitives=args.primitive,
                        note=args.note,
                        **lane_kwargs,
                    )
        elif args.handler_command == "l3-proposal-create":
            result = run_l3_proposal_create(
                root,
                kind=args.kind,
                proposal_id=args.proposal_id,
                target_file=args.target_file,
                content=_read_text_argument(root, args.content_file),
                rationale=args.rationale,
                evidence_refs=args.evidence_refs,
                signal_ids=args.signal_ids,
                pattern=args.pattern,
            )
        elif args.handler_command == "l3-proposal-generate":
            result = run_l3_proposal_generate(
                root,
                planner_log_path=args.planner_log_path,
                limit=args.limit,
                apply=args.apply,
            )
        elif args.handler_command == "review":
            if args.review_command == "proposals":
                result = run_l3_proposal_list(root, kind=args.kind, state=args.state)
                if not args.json:
                    text_output = "\n".join(_format_l3_proposal_summary_line(item) for item in result) or "(no L3 proposals)"
            elif args.review_command == "proposal-generation":
                result = run_l3_proposal_generation_preview(
                    root,
                    planner_log_path=args.planner_log_path,
                    limit=args.limit,
                )
                if not args.json:
                    candidates = result.get("candidates", []) if isinstance(result, dict) else []
                    text_output = "\n".join(_format_l3_generation_preview_line(item) for item in candidates) or "(no L3 proposal generation candidates)"
            elif args.review_command == "proposal":
                if args.status != "rejected":
                    raise ValueError(f"Unsupported L3 proposal review status: {args.status}")
                result = run_l3_proposal_reject(root, args.proposal_id, note=args.note)
            else:
                raise ValueError(f"Unsupported review command: {args.review_command}")
        elif args.handler_command == "apply":
            result = run_l3_proposal_apply(root, args.proposal_id, note=args.note)
        elif args.handler_command == "revert":
            result = run_l3_proposal_revert(root, args.receipt_id, note=args.note)
        elif args.handler_command == "protocol-learn-add":
            result = run_protocol_learn_add(root, args.protocol, args.title, args.source_refs)
        elif args.handler_command == "protocol-learn-list":
            result = run_protocol_learn_list(
                root,
                args.protocol,
                state_filter=args.state,
                include_archived=args.include_archived,
            )
        elif args.handler_command == "protocol-learn-show":
            result = run_protocol_learn_show(root, args.learning_id)
        elif args.handler_command == "signals-list":
            result = run_signals_list(
                root,
                kind=args.kind,
                trace_id=args.trace_id,
                since=args.since,
                limit=args.limit,
            )
            if not args.json:
                text_output = "\n".join(_format_signal_summary_line(item) for item in result) or "(no signals)"
        elif args.handler_command == "signals-show":
            result = run_signals_show(root, args.signal_id)
            if result.get("status") == "not_found":
                raise ValueError(f"signal not found: {args.signal_id}")
            if not args.json:
                signal = result.get("signal")
                planner_decisions = result.get("planner_decisions")
                if not isinstance(signal, dict) or not isinstance(planner_decisions, list):
                    raise ValueError("Invalid runner payload for signals-show.")
                text_output = _format_signal_show_text(signal, planner_decisions)
        elif args.handler_command == "planner-log-list":
            result = run_planner_log_list(
                root,
                decision=args.decision,
                signal_id=args.signal_id,
                trace_id=args.trace_id,
                since=args.since,
                limit=args.limit,
            )
            if not args.json:
                text_output = (
                    "\n".join(_format_planner_decision_summary_line(item) for item in result)
                    or "(no planner decisions)"
                )
        elif args.handler_command == "planner-log-rollback":
            if args.dry_run:
                result = run_planner_log_rollback_preview(
                    root,
                    signal_id=args.signal_id,
                    trace_id=args.trace_id,
                    limit=args.limit,
                )
            else:
                result = run_planner_log_rollback(
                    root,
                    signal_id=args.signal_id,
                    trace_id=args.trace_id,
                    limit=args.limit,
                    apply=True,
                )
        elif args.handler_command == "audit-preview":
            if not args.dry_run:
                raise ValueError("audit-preview requires --dry-run")
            result = run_audit_preview(root, limit=args.limit)
        elif args.handler_command == "audit-backfill":
            result = run_audit_backfill(root, limit=args.limit, apply=args.apply)
        elif args.handler_command == "protocol-learn-age":
            result = run_protocol_learn_age(root, protocol=args.protocol, apply=args.apply)
        elif args.handler_command == "protocol-learn-verify":
            result = run_protocol_learn_verify(root, args.learning_id)
        elif args.handler_command == "protocol-learn-revert-activate":
            result = run_protocol_learn_revert_activate(root, args.learning_id, note=args.note)
        elif args.handler_command == "protocol-learn-demote":
            result = run_protocol_learn_demote(root, args.learning_id)
        elif args.handler_command == "protocol-learn-archive":
            result = run_protocol_learn_archive(root, args.learning_id)
        elif args.handler_command == "protocol-learn-supersede":
            result = run_protocol_learn_supersede(root, args.replacement_id, args.superseded_ids)
        elif args.handler_command == "review-page":
            review_pages = _resolve_review_pages(
                root,
                args.page,
                use_next=args.next,
                batch=args.batch,
                all_pending=args.all_pending,
            )
            if len(review_pages) > 1 or args.batch or args.all_pending:
                result = review_pages_batch(
                    root,
                    review_pages,
                    args.status,
                    note=args.note,
                    confidence=args.confidence,
                )
            else:
                result = review_page(
                    root,
                    review_pages[0],
                    args.status,
                    note=args.note,
                    confidence=args.confidence,
                )
        elif args.handler_command == "review-rewrite":
            result = review_concept_rewrite(root, args.slug, args.status, note=args.note)
        elif args.handler_command == "apply-rewrite":
            result = apply_concept_rewrite(root, args.slug, note=args.note, dry_run=args.dry_run)
        elif args.handler_command == "verify-rewrite":
            result = verify_concept_rewrite(root, args.slug, note=args.note)
        elif args.handler_command == "revert-rewrite":
            result = revert_concept_rewrite(root, args.slug, note=args.note)
        elif args.handler_command == "retire-concept":
            result = retire_concept(root, args.slug, note=args.note)
        elif args.handler_command == "reactivate-concept":
            result = reactivate_concept(root, args.slug, note=args.note)
        elif args.handler_command == "review-action":
            result = review_machine_memory_action(
                root,
                _resolve_action_id(root, args.action_id),
                args.status,
                note=args.note,
            )
        elif args.handler_command == "apply-action":
            action_ids = _resolve_action_ids(
                root,
                args.action_id,
                batch=args.batch,
                all_accepted_low_risk=args.all_accepted_low_risk,
            )
            if len(action_ids) > 1 or args.batch or args.all_accepted_low_risk:
                if args.bundle:
                    raise ValueError("--bundle is only supported for single-action apply.")
                result = apply_machine_memory_actions_batch(
                    root,
                    action_ids,
                    note=args.note,
                    dry_run=args.dry_run,
                )
            else:
                result = apply_machine_memory_action(
                    root,
                    action_ids[0],
                    note=args.note,
                    dry_run=args.dry_run,
                    bundle_path=args.bundle,
                )
        elif args.handler_command == "revert-action":
            if args.last_batch:
                result = revert_machine_memory_action_batch(root, note=args.note)
            else:
                if not args.action_id:
                    raise ValueError("Provide an action id or use --last-batch.")
                result = revert_machine_memory_action(root, _resolve_action_id(root, args.action_id), note=args.note)
        elif args.handler_command == "apply-archive":
            result = apply_material_archive(root, args.entry_id, note=args.note, dry_run=args.dry_run)
        elif args.handler_command == "revert-archive":
            result = revert_material_archive(root, args.entry_id, note=args.note)
        elif args.handler_command == "lint":
            result = lint_wiki(root)
        elif args.handler_command == "run-lint":
            result = run_lint(root)
        elif args.handler_command == "nightly":
            result = nightly_health(root)
        elif args.handler_command == "run-nightly":
            result = run_nightly(
                root,
                compile_limit=args.compile_limit,
                semantic_lint=not args.no_semantic_lint,
            )
        elif args.handler_command == "signals-replay":
            result = collect_signals(root, sources=args.source, trace_id=args.trace_id)
        elif args.handler_command == "planner-log-replay":
            result = write_planner_log(
                root,
                signals_path=args.signals_path,
                mode="execute" if args.execute else "observe_only",
            )
        elif args.handler_command == "llm-check":
            if args.probe or args.probe_all:
                result = llm_probe(root, probe_all=args.probe_all, timeout_seconds=args.probe_timeout)
            else:
                result = llm_status()
        elif args.handler_command == "cache":
            selected_actions = int(bool(args.status)) + int(bool(args.rebuild)) + int(bool(args.drop))
            if selected_actions != 1:
                raise ValueError("Provide exactly one of --status, --rebuild, or --drop.")
            if args.status:
                result = cache_status_summary(root)
            elif args.rebuild:
                result = force_rebuild_query_cache(root)
            else:
                result = drop_query_cache(root)
        elif args.handler_command == "auto-once":
            result = auto_process_once(
                root,
                compile_limit=args.compile_limit,
                deterministic_only=args.deterministic_only,
                semantic_lint=not args.no_semantic_lint,
            )
        elif args.handler_command == "watch":
            result = watch_inbox(
                root,
                interval_seconds=args.interval,
                compile_limit=args.compile_limit,
                deterministic_only=args.deterministic_only,
                semantic_lint=not args.no_semantic_lint,
                process_initial=not args.skip_initial,
                max_cycles=args.max_cycles,
            )
        else:
            raise ValueError(f"Unsupported command: {args.handler_command}")
    except KeyboardInterrupt:  # pragma: no cover - interactive watch mode
        parser.exit(130, "interrupted\n")
    except Exception as exc:  # pragma: no cover - exercised in CLI usage
        parser.exit(1, f"error: {exc}\n")
    finally:
        if args.model_fallback is not None:
            if fallback_env_was_set:
                os.environ["AIWIKI_MODEL_FALLBACK"] = previous_fallback_env
            else:
                os.environ.pop("AIWIKI_MODEL_FALLBACK", None)

    if text_output is not None:
        print(text_output)
        return 0

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _flatten_model_fallback_args(values: list[str]) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in str(value or "").split(","):
            model = item.strip()
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
    return models


def today_command(root: Path) -> int:
    summary = build_shell_summary(root)
    print(_render_today_text(summary))
    return 0


def _render_today_text(summary: dict[str, object]) -> str:
    generated_at = str(summary.get("generated_at") or "")
    active_protocol = str(summary.get("active_protocol") or "")
    today_date = _date_part(generated_at)
    lines = [
        "炼丹炉 Today",
        f"Generated: {generated_at}",
        f"Active protocol: {active_protocol}",
        "",
        "Today's Reports",
    ]
    report_lines = _today_report_lines(summary, today_date)
    lines.extend(report_lines or ["(no reports today)"])
    lines.extend(["", "Needs Review"])
    review_lines = _needs_review_lines(summary)
    lines.extend(review_lines or ["(no pending review)"])
    lines.extend(["", "Completed Elixirs"])
    elixir_lines = _completed_elixir_lines(summary, today_date)
    lines.extend(elixir_lines or ["(no completed elixirs today)"])
    lines.extend(["", "L3 Proposals"])
    l3_lines = _l3_proposal_lines(summary)
    lines.extend(l3_lines or ["(no L3 proposals need attention)"])
    lines.extend(["", "Suggested Next Actions"])
    action_lines = _suggested_next_action_lines(summary)
    lines.extend(action_lines or ["(no suggested next actions)"])
    lines.extend(
        [
            "",
            "Advanced",
            "Run `aiwiki advanced ...` for system status, receipts, audit, repair, lanes, and debugging.",
        ]
    )
    return "\n".join(lines)


def _today_report_lines(summary: dict[str, object], today_date: str) -> list[str]:
    lines: list[str] = []
    for item in _dict_items(summary.get("recent_outputs")):
        if _date_part(_first_text(item, "generated_at", "created_at")) != today_date:
            continue
        path = _first_text(item, "path", "artifact_path")
        title = _first_text(item, "title") or Path(path).name or "?"
        protocol = _first_text(item, "protocol") or "?"
        output_format = _first_text(item, "format") or "?"
        lines.append(f"- [{protocol}] {title} — {output_format} — {path or '?'}")
    return lines


def _needs_review_lines(summary: dict[str, object]) -> list[str]:
    counts = summary.get("review_backlog_counts")
    if not isinstance(counts, dict):
        return []
    lines: list[str] = []
    for kind in sorted(counts):
        value = counts.get(kind)
        if isinstance(value, bool):
            count = int(value)
        elif isinstance(value, int):
            count = value
        else:
            try:
                count = int(str(value))
            except (TypeError, ValueError):
                count = 0
        if count:
            lines.append(f"- {kind} count={count} — review_backlog_counts — pending")
    return lines


def _completed_elixir_lines(summary: dict[str, object], today_date: str) -> list[str]:
    lines: list[str] = []
    for item in _dict_items(summary.get("recent_receipts")):
        if _date_part(_first_text(item, "applied_at", "generated_at", "created_at")) != today_date:
            continue
        operation = _first_text(item, "operation") or "?"
        subject_kind = _first_text(item, "subject_kind")
        subject_id = _first_text(item, "subject_id")
        action_id = _first_text(item, "action_id")
        elixir_text = " ".join([operation, subject_kind, subject_id, action_id]).lower()
        if "elixir" not in elixir_text and not any(token in operation.lower() for token in ("promote", "demote", "revert", "finalize")):
            continue
        title = _first_text(item, "title") or subject_id or "?"
        receipt_path = _first_text(item, "receipt_path", "path") or "?"
        lines.append(f"- {title} — {operation} — {receipt_path}")
    return lines


def _l3_proposal_lines(summary: dict[str, object]) -> list[str]:
    review_controls = summary.get("review_controls")
    if not isinstance(review_controls, dict):
        return []
    lines: list[str] = []
    for item in _dict_items(review_controls.get("l3_proposals")):
        if not item.get("needs_attention"):
            continue
        proposal_id = _first_text(item, "proposal_id") or "?"
        kind = _first_text(item, "kind") or "?"
        state = _first_text(item, "state", "current_status") or "?"
        target_file = _first_text(item, "target_file") or "?"
        lines.append(f"- {proposal_id} — {kind} — {state} — {target_file}")
    return lines


def _suggested_next_action_lines(summary: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for item in _dict_items(summary.get("suggested_next_actions")):
        title = _first_text(item, "title", "label", "name") or "?"
        command = _first_text(item, "command", "cli", "action") or "?"
        lines.append(f"- {title} — {command}")
    return lines


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_text(item: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _date_part(value: str) -> str:
    text = str(value or "").strip()
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text[:10]


def _format_signal_summary_line(record: dict[str, object]) -> str:
    scope_protocol = ""
    scope = record.get("scope")
    if isinstance(scope, dict):
        scope_protocol = str(scope.get("protocol") or "")
    return "  ".join(
        [
            str(record.get("signal_id") or ""),
            str(record.get("kind") or ""),
            str(record.get("severity") or ""),
            str(record.get("emitted_at") or ""),
            scope_protocol,
            str(record.get("source_event_ref") or ""),
        ]
    )


def _format_planner_decision_summary_line(record: dict[str, object]) -> str:
    reason_codes = record.get("reason_codes")
    if isinstance(reason_codes, list):
        rendered_reasons = json.dumps(reason_codes, ensure_ascii=False)
    else:
        rendered_reasons = str(reason_codes or "[]")
    return "  ".join(
        [
            str(record.get("decided_at") or ""),
            str(record.get("decision") or ""),
            str(record.get("mode") or ""),
            str(record.get("signal_id") or ""),
            rendered_reasons,
        ]
    )


def _format_l3_proposal_summary_line(record: dict[str, object]) -> str:
    return "  ".join(
        [
            str(record.get("proposal_id") or ""),
            str(record.get("kind") or ""),
            str(record.get("state") or ""),
            str(record.get("target_file") or ""),
            str(record.get("proposal_path") or ""),
        ]
    )


def _format_l3_generation_preview_line(record: dict[str, object]) -> str:
    blockers = record.get("blockers")
    if isinstance(blockers, list):
        rendered_blockers = json.dumps(blockers, ensure_ascii=False)
    else:
        rendered_blockers = str(blockers or "[]")
    return "  ".join(
        [
            str(record.get("decided_at") or ""),
            str(record.get("signal_id") or ""),
            str(record.get("proposal_kind") or "unknown"),
            "blocked",
            rendered_blockers,
        ]
    )


def _format_signal_show_text(signal: dict[str, object], planner_decisions: list[object]) -> str:
    lines = [f"Signal: {str(signal.get('signal_id') or '')}"]
    for key in sorted(signal):
        value = signal[key]
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        lines.append(f"  {key}: {rendered}")
    lines.append("Related planner decisions:")
    decisions = [item for item in planner_decisions if isinstance(item, dict)]
    if not decisions:
        lines.append("  (none)")
    else:
        for decision in decisions:
            lines.append(f"  - {_format_planner_decision_summary_line(decision)}")
    return "\n".join(lines)


def _add_auto_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run one automatic processing pass after the material is dropped.",
    )
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="When used with --auto, skip the LLM layer and run deterministic compile + lint only.",
    )
    parser.add_argument(
        "--no-semantic-lint",
        action="store_true",
        help="When used with --auto, skip the LLM semantic lint pass.",
    )


_LEGACY_DROP_REPLACEMENTS = {
    "drop-url": "drop url",
    "drop-pdf": "drop pdf",
    "drop-image": "drop image",
    "drop-repo": "drop repo",
    "drop-note": "drop note",
}


def _emit_legacy_drop_deprecation_warning(args: argparse.Namespace) -> None:
    if args.handler_command not in _LEGACY_DROP_REPLACEMENTS:
        return
    if args.command != args.handler_command:
        return
    replacement = _LEGACY_DROP_REPLACEMENTS[args.handler_command]
    print(
        f"[deprecated] `aiwiki {args.handler_command}` is deprecated; use `aiwiki {replacement}` instead.",
        file=sys.stderr,
    )


def _maybe_auto_process(root: Path, result: dict[str, object], args: argparse.Namespace) -> dict[str, object]:
    if not getattr(args, "auto", False):
        return result
    auto_result = auto_process_once(
        root,
        deterministic_only=getattr(args, "deterministic_only", False),
        semantic_lint=not getattr(args, "no_semantic_lint", False),
    )
    return {
        **result,
        "auto_process": auto_result,
    }


def _read_text_argument(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return path.read_text(encoding="utf-8")
    workspace_path = root / value
    if workspace_path.exists():
        return workspace_path.read_text(encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    return build_parser()


def _pending_review_pages(root: Path) -> list[str]:
    summary = build_shell_summary(root)
    review_controls = summary.get("review_controls", {})
    if not isinstance(review_controls, dict):
        review_controls = {}
    pending: list[str] = []
    for candidate in review_controls.get("pages", []):
        if not isinstance(candidate, dict) or not candidate.get("can_review"):
            continue
        candidate_path = str(candidate.get("path") or "")
        if candidate_path:
            pending.append(candidate_path)
    return pending


def _resolve_review_pages(
    root: Path,
    page: str | None,
    *,
    use_next: bool,
    batch: list[str] | None,
    all_pending: bool,
) -> list[str]:
    selected_modes = int(bool(use_next)) + int(bool(batch)) + int(bool(all_pending))
    if page and selected_modes:
        raise ValueError("Use PAGE by itself, or choose exactly one of --next/--batch/--all-pending.")
    if selected_modes > 1:
        raise ValueError("Choose only one of --next, --batch, or --all-pending.")
    if use_next:
        pending = _pending_review_pages(root)
        if not pending:
            raise RuntimeError("No review page is ready for --next.")
        return [pending[0]]
    if batch:
        return [item for item in batch if item.strip()]
    if all_pending:
        pending = _pending_review_pages(root)
        if not pending:
            raise RuntimeError("No review pages are currently pending.")
        return pending
    if page:
        return [page]
    raise ValueError("Provide a review page path or use --next/--batch/--all-pending.")


def _resolve_action_id(root: Path, action_query: str) -> str:
    normalized_query = action_query.strip()
    if not normalized_query:
        raise ValueError("Action id cannot be empty.")
    state = load_machine_memory_action_state(root)
    actions = [action for action in state.get("actions", []) if isinstance(action, dict)]
    if not actions:
        return normalized_query
    return str(resolve_machine_memory_action_query(actions, normalized_query).get("id") or normalized_query)


def _resolve_action_ids(
    root: Path,
    action_id: str | None,
    *,
    batch: list[str] | None,
    all_accepted_low_risk: bool,
) -> list[str]:
    selected_modes = int(bool(action_id)) + int(bool(batch)) + int(bool(all_accepted_low_risk))
    if selected_modes != 1:
        raise ValueError("Provide one action id, or use exactly one of --batch/--all-accepted-low-risk.")
    if action_id:
        return [_resolve_action_id(root, action_id)]
    if batch:
        return [_resolve_action_id(root, item) for item in batch if item.strip()]
    state = load_machine_memory_action_state(root)
    action_ids = [
        str(action.get("id") or "")
        for action in state.get("actions", [])
        if isinstance(action, dict)
        and action_supports_low_risk_apply(action)
    ]
    if not action_ids:
        raise RuntimeError("No accepted low-risk actions are ready for batch apply.")
    return action_ids


if __name__ == "__main__":
    raise SystemExit(main())
