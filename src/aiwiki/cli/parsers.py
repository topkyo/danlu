"""Argparse registration for aiwiki CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiwiki", description="Local-first knowledge compiler scaffold")
    parser.add_argument(
        "--root",
        default=None,
        help="Project root. Defaults to AIWIKI_VAULT env when set, else current directory.",
    )
    parser.add_argument(
        "--model-fallback",
        action="append",
        dest="model_fallback",
        help="Fallback model to try when current model fails. Repeatable or comma-separated. Overrides AIWIKI_MODEL_FALLBACK env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _register_legacy_top_level_parsers(subparsers)
    today_parser = subparsers.add_parser("today", help="炼丹炉今日产出 / 待办 / 建议")
    today_parser.add_argument("--json", action="store_true", help="JSON 输出（按 section 桶化）")
    today_parser.set_defaults(handler_command="today")
    metrics_parser = subparsers.add_parser("metrics", help="炼丹炉知识复利指标")
    metrics_parser.add_argument("--json", action="store_true", help="JSON 输出")
    metrics_parser.add_argument(
        "--delta",
        choices=["7d", "30d"],
        default=None,
        help="对比 7 天前 / 30 天前 baseline（基于 .aiwiki/state/metrics-history.jsonl）",
    )
    metrics_parser.set_defaults(handler_command="metrics")
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

    autonomy_status_parser = subparsers.add_parser(
        "autonomy-status",
        help="炼丹炉自动化 kill switch 状态：policy 文件 + 全局 override + 4 flag effective 状态。",
    )
    autonomy_status_parser.add_argument("--json", action="store_true", help="JSON 输出")
    autonomy_status_parser.set_defaults(handler_command="autonomy-status")

    autonomy_disable_parser = subparsers.add_parser(
        "autonomy-disable",
        help="开启某个 autonomy flag（写入 .aiwiki/state/autonomy-policy.json）。",
    )
    autonomy_disable_parser.add_argument(
        "flag",
        help="flag 名（disable_lane_apply / disable_alchemy_auto / disable_l3_generate / disable_external_llm）",
    )
    autonomy_disable_parser.set_defaults(handler_command="autonomy-disable")

    autonomy_enable_parser = subparsers.add_parser(
        "autonomy-enable",
        help="关闭某个 autonomy flag。",
    )
    autonomy_enable_parser.add_argument("flag", help="flag 名（同 autonomy-disable）")
    autonomy_enable_parser.set_defaults(handler_command="autonomy-enable")

    trace_parser = subparsers.add_parser(
        "trace",
        help="证据链追溯：输入资产 ID（raw / source / judgment / decision / elixir / proposal / receipt action_id），输出 provenance 树。",
    )
    trace_parser.add_argument(
        "asset_id",
        help="资产 ID 或路径。raw 用 raw/... 路径；wiki 资产用 frontmatter id 或 wiki/.../*.md。",
    )
    trace_parser.add_argument(
        "--direction",
        choices=["up", "down", "both"],
        default="up",
        help="up=向上找来源（默认）；down=向下找派生；both=同时。",
    )
    trace_parser.add_argument(
        "--depth",
        type=int,
        default=5,
        help="最大递归深度（1~10，默认 5）。",
    )
    trace_parser.add_argument("--json", action="store_true", help="JSON 输出（机器可读）。")
    trace_parser.set_defaults(handler_command="trace")

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
        help=(
            "Max number of LLM-enriched pages per stage. Note: run-compile is fail-fast — "
            "first failure aborts remaining items in this stage."
        ),
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
        help="File a markdown artifact back into wiki/derived (machine-memory terminal layer, no review), wiki/decisions, or wiki/judgments (subject to review-page workflow).",
    )
    file_back_parser.add_argument("artifact", help="Path to a markdown artifact.")
    file_back_parser.add_argument("--title", help="Optional filed-back title.")
    file_back_parser.add_argument(
        "--kind",
        choices=("derived", "decision", "judgment"),
        default="derived",
        help="Filed-back page kind. Note: 'derived' is terminal (no review) and separate from the corpus candidate plane; 'decision' and 'judgment' enter the review-page workflow.",
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
    revert_parser.add_argument(
        "receipt_id",
        help="Receipt id of the L3 proposal apply receipt (action_id field inside output/control/execution-receipts/l3-proposal-apply-<proposal_id>.json; or full receipt path; or receipt JSON basename).",
    )
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
        help="Apply an explicit concept lifecycle override and retire one or more concepts from default query ranking.",
    )
    retire_concept_parser.add_argument(
        "slugs",
        nargs="+",
        help="One or more concept slugs (fail-fast: first failure aborts remaining).",
    )
    retire_concept_parser.add_argument("--note", help="Optional retire note (applied to all slugs).")

    reactivate_concept_parser = subparsers.add_parser(
        "reactivate-concept",
        help="Clear the active retired override for one or more concepts and return them to heuristic lifecycle routing.",
    )
    reactivate_concept_parser.add_argument(
        "slugs",
        nargs="+",
        help="One or more concept slugs (fail-fast: first failure aborts remaining).",
    )
    reactivate_concept_parser.add_argument("--note", help="Optional reactivate note (applied to all slugs).")

    review_concept_parser = subparsers.add_parser(
        "review-concept",
        help=(
            "Manual review-ack for concepts in the revisit/review buckets — "
            "writes a concept lifecycle override pinning lifecycle_state."
        ),
    )
    review_concept_parser.add_argument(
        "slugs",
        nargs="*",
        help="One or more concept slugs (omit when using --all-pending).",
    )
    review_concept_parser.add_argument(
        "--status",
        required=True,
        choices=("active", "deferred", "review"),
        help="Target lifecycle_state for the override.",
    )
    review_concept_parser.add_argument("--note", help="Optional review note (applied to all slugs).")
    review_concept_parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Review every concept currently in the revisit_concepts and review_concepts buckets.",
    )

    review_queue_parser = subparsers.add_parser(
        "review-queue",
        help="List pending review items grouped by sub-bucket (decision-kind feed entries).",
    )
    review_queue_parser.add_argument(
        "--bucket",
        help="Filter to one sub-bucket name (e.g. concept_backlog, revisit, mm_actions, counter_evidence, drift).",
    )
    review_queue_parser.add_argument(
        "--limit",
        type=int,
        help="Truncate each bucket to N items (>=0).",
    )
    review_queue_parser.add_argument("--json", action="store_true", help="Structured JSON output.")
    review_queue_parser.set_defaults(handler_command="review-queue")

    action_review_parser = subparsers.add_parser(
        "review-action",
        help="Advance a machine-memory repair action through the explicit action workflow.",
    )
    action_review_parser.add_argument(
        "action_ids",
        nargs="*",
        help="Machine-memory action ids or title fragments.",
    )
    action_review_parser.add_argument(
        "--status",
        required=True,
        choices=("proposed", "accepted", "deferred", "resolved", "rejected"),
        help="Target action status.",
    )
    action_review_parser.add_argument("--note", help="Optional action review note.")
    action_review_parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Review all proposed review-first actions matching --kind.",
    )
    action_review_parser.add_argument(
        "--kind",
        help="Required with --all-pending; filters action kind (e.g. add-source-concept-link).",
    )
    action_review_parser.add_argument(
        "--execution-band",
        default="review-first",
        help="Execution band filter for --all-pending (default: review-first).",
    )

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
    llm_check_parser.add_argument(
        "--format",
        choices=["json", "human"],
        default="json",
        help="Output format. 'human' renders a backend compatibility table; 'json' (default) preserves machine-readable schema.",
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
