"""Argparse registration for aiwiki CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

PRIMARY_SURFACE_COMMANDS: tuple[str, ...] = ("drop", "today", "advanced")

_ALCHEMY_SUBCOMMAND_HANDLERS: dict[str, str] = {
    "start": "alchemy-start",
    "distill": "alchemy-distill",
    "finalize": "alchemy-finalize",
    "promote": "alchemy-promote",
    "revert": "alchemy-revert",
    "demote": "alchemy-demote",
}

_ALCHEMY_COMPAT_COMMANDS: frozenset[str] = frozenset(
    {"alchemy-" + name for name in _ALCHEMY_SUBCOMMAND_HANDLERS}
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiwiki",
        description=(
            "炼丹炉 local-first knowledge agent runtime. "
            f"PRIMARY_SURFACE commands: {', '.join(PRIMARY_SURFACE_COMMANDS)}. "
            "Daily path: `aiwiki drop ...` to feed material, `aiwiki today` to read outputs. "
            "Use `aiwiki advanced ...` for operator commands."
        ),
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root. Defaults to AIWIKI_VAULT env when set, else current directory.",
    )
    parser.add_argument(
        "--model-fallback",
        action="append",
        dest="model_retry",
        help="Retry model to try on the same backend when current model fails. Repeatable or comma-separated. Overrides AIWIKI_MODEL_FALLBACK env.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{" + ",".join(PRIMARY_SURFACE_COMMANDS) + "}",
    )
    # Operator commands are registered only under `advanced` (no top-level aliases).
    today_parser = subparsers.add_parser("today", help="炼丹炉今日产出 / 待办 / 建议")
    today_parser.add_argument("--json", action="store_true", help="JSON 输出（按 section 桶化）")
    today_parser.set_defaults(handler_command="today")
    drop_parser = subparsers.add_parser("drop", help="炼丹炉输入端：投喂 URL / PDF / 图片 / 仓库 / Markdown / 问题")
    drop_subparsers = drop_parser.add_subparsers(dest="drop_command", required=True)
    _register_drop_subcommand_parsers(drop_subparsers)
    advanced_parser = subparsers.add_parser(
        "advanced",
        help="高级抽屉：系统状态、receipts、compile/lint、review-page、alchemy、调试入口",
    )
    advanced_subparsers = advanced_parser.add_subparsers(dest="advanced_command", required=True)
    _register_advanced_parsers(advanced_subparsers)
    _converge_default_help_surface(subparsers)
    return parser


def _converge_default_help_surface(subparsers: argparse._SubParsersAction) -> None:
    """Keep top-level help product-first (drop / today / advanced only)."""
    visible = {
        getattr(action, "dest", ""): action
        for action in subparsers._choices_actions  # type: ignore[attr-defined]
        if getattr(action, "dest", "") in PRIMARY_SURFACE_COMMANDS
    }
    subparsers._choices_actions = [  # type: ignore[attr-defined]  # argparse private display hook.
        visible[name] for name in PRIMARY_SURFACE_COMMANDS if name in visible
    ]


def _register_advanced_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register operator commands under the advanced drawer."""

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

    sync_product_shell_parser = subparsers.add_parser(
        "sync-product-shell",
        help="Sync Product Shell plugin release files from this runtime root into an existing Obsidian vault.",
    )
    sync_product_shell_parser.add_argument("target", help="Target vault directory to update.")

    subparsers.add_parser("compile", help="Compile manifest entries into wiki source pages and indexes.")

    subparsers.add_parser(
        "shell-status",
        help="Write and return the Product Shell summary contract for front-end workbench integrations.",
    )

    run_ask_parser = subparsers.add_parser(
        "run-ask",
        help="Create a query artifact and use the configured LLM to fill it in place.",
    )
    run_ask_parser.add_argument("question", help="Research question to answer.")
    run_ask_parser.add_argument(
        "--format",
        choices=("report",),
        default="report",
        help="Output artifact format.",
    )
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
    run_ask_parser.add_argument("--corpus", help="Optional active corpus id to reuse across ask rounds.")

    file_back_parser = subparsers.add_parser(
        "file-back",
        help="File a markdown artifact back into wiki/judgments for thin review-page workflow.",
    )
    file_back_parser.add_argument("artifact", help="Path to a markdown artifact.")
    file_back_parser.add_argument("--title", help="Optional filed-back title.")

    alchemy_parser = subparsers.add_parser(
        "alchemy",
        help="金丹生命周期：start / distill / finalize / promote / revert / demote。",
    )
    alchemy_subparsers = alchemy_parser.add_subparsers(dest="alchemy_command", required=True)
    _register_alchemy_subcommand_parsers(alchemy_subparsers)
    _register_alchemy_compat_aliases(subparsers)

    review_parser = subparsers.add_parser(
        "review-page",
        help="Advance a decision or judgment page through the explicit review workflow.",
    )
    review_parser.add_argument("page", nargs="?", help="Path to a decision or judgment markdown page.")
    review_parser.add_argument("--status", required=True, help="Target review status for the page.")
    review_parser.add_argument("--note", help="Optional review note to store in the page.")
    review_parser.add_argument("--confidence", help="Optional confidence override for judgment pages.")

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

    gc_orphans_parser = subparsers.add_parser(
        "gc-orphans",
        help="显式 GC：清 broken file-back / 噪音概念 / 误投（默认 dry-run）。",
    )
    apply_group = gc_orphans_parser.add_mutually_exclusive_group()
    apply_group.add_argument(
        "--dry-run",
        dest="gc_apply",
        action="store_false",
        help="只列候选（默认）。",
    )
    apply_group.add_argument(
        "--apply",
        dest="gc_apply",
        action="store_true",
        help="删除候选并写 execution receipt。",
    )
    gc_orphans_parser.set_defaults(gc_apply=False)
    gc_orphans_parser.add_argument("--judgments", action="store_true", help="纳入 wiki/judgments。")
    gc_orphans_parser.add_argument("--derived", action="store_true", help="纳入 wiki/derived。")
    gc_orphans_parser.add_argument("--elixirs", action="store_true", help="纳入 wiki/elixirs。")
    gc_orphans_parser.add_argument(
        "--force-degraded",
        action="store_true",
        help="file-back 类同时删除 provenance_status=degraded。",
    )
    gc_orphans_parser.add_argument(
        "--noise-concepts",
        action="store_true",
        help="删除噪音概念（词表∪singleton，白名单 hub 除外）。",
    )
    gc_orphans_parser.add_argument(
        "--misdrops",
        action="store_true",
        help="删除 vphone 等误投指纹匹配的 raw/sources。",
    )
    gc_orphans_parser.add_argument(
        "--force",
        action="store_true",
        help="misdrop 仍被 judgment 引用时仍删 source。",
    )
    gc_orphans_parser.set_defaults(handler_command="gc-orphans")

    subparsers.add_parser("lint", help="Run deterministic lint checks against the wiki.")
    run_nightly_parser = subparsers.add_parser(
        "run-nightly",
        help="Run deterministic compile + lint and write nightly repair artifacts.",
    )
    run_nightly_parser.add_argument(
        "--compile-limit",
        type=int,
        default=5,
        help="Compatibility metadata for nightly receipts (deterministic compile is not LLM-batched).",
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
        help="Recorded in automation state for each watcher pass.",
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

    # Diagnostic / periodic — keep after daily operator verbs so help lists it last.
    metrics_parser = subparsers.add_parser(
        "metrics",
        help="诊断：知识复利指标快照（非日常主路径；需要复盘时再跑）。",
    )
    metrics_parser.add_argument("--json", action="store_true", help="JSON 输出")
    metrics_parser.add_argument(
        "--delta",
        choices=["7d", "30d"],
        default=None,
        help="对比 7 天前 / 30 天前 baseline（基于 .aiwiki/state/metrics-history.jsonl）",
    )
    metrics_parser.set_defaults(handler_command="metrics")

    _set_handler_command_defaults(subparsers)
    _converge_advanced_help_surface(subparsers)


def _register_alchemy_subcommand_parsers(subparsers: argparse._SubParsersAction) -> None:
    start_parser = subparsers.add_parser("start", help="Start a new elixir from a corpus.")
    _configure_alchemy_start_parser(start_parser)

    distill_parser = subparsers.add_parser("distill", help="Distill an existing draft elixir.")
    _configure_alchemy_distill_parser(distill_parser)

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Finalize a draft/distilling elixir into candidate state.",
    )
    _configure_alchemy_finalize_parser(finalize_parser)

    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote a candidate elixir into settled with receipt+tombstone.",
    )
    _configure_alchemy_promote_parser(promote_parser)

    revert_parser = subparsers.add_parser(
        "revert",
        help="Revert the latest elixir promote from settled back to candidate.",
    )
    _configure_alchemy_revert_parser(revert_parser)

    demote_parser = subparsers.add_parser(
        "demote",
        help="Demote a settled elixir back to candidate using current settled content.",
    )
    _configure_alchemy_demote_parser(demote_parser)


def _register_alchemy_compat_aliases(subparsers: argparse._SubParsersAction) -> None:
    alchemy_start_parser = subparsers.add_parser(
        "alchemy-start",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_start_parser(alchemy_start_parser)

    alchemy_distill_parser = subparsers.add_parser(
        "alchemy-distill",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_distill_parser(alchemy_distill_parser)

    alchemy_finalize_parser = subparsers.add_parser(
        "alchemy-finalize",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_finalize_parser(alchemy_finalize_parser)

    alchemy_promote_parser = subparsers.add_parser(
        "alchemy-promote",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_promote_parser(alchemy_promote_parser)

    alchemy_revert_parser = subparsers.add_parser(
        "alchemy-revert",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_revert_parser(alchemy_revert_parser)

    alchemy_demote_parser = subparsers.add_parser(
        "alchemy-demote",
        help=argparse.SUPPRESS,
    )
    _configure_alchemy_demote_parser(alchemy_demote_parser)


def _configure_alchemy_start_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("corpus_id")
    parser.add_argument("--topic", required=True)
    parser.add_argument(
        "--include-elixir", type=str, default=None, help="可选：额外包含的金丹 id，多个用逗号分隔。"
    )


def _configure_alchemy_distill_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("elixir_id")
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--include-elixir", type=str, default=None, help="可选：额外包含的金丹 id，多个用逗号分隔。"
    )


def _configure_alchemy_finalize_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--elixir-id", required=True)


def _configure_alchemy_promote_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--elixir-id", required=True)
    parser.add_argument("--note", default=None)


def _configure_alchemy_revert_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--elixir-id", required=True)
    parser.add_argument("--note", default=None)


def _configure_alchemy_demote_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--elixir-id", required=True)
    parser.add_argument("--note", default=None)


def _converge_advanced_help_surface(subparsers: argparse._SubParsersAction) -> None:
    """Hide flat alchemy-* compat aliases from default advanced help."""
    subparsers._choices_actions = [  # type: ignore[attr-defined]
        action
        for action in subparsers._choices_actions  # type: ignore[attr-defined]
        if getattr(action, "dest", "") not in _ALCHEMY_COMPAT_COMMANDS
    ]
    visible = [action.dest for action in subparsers._choices_actions]  # type: ignore[attr-defined]
    subparsers.metavar = "{" + ",".join(visible) + "}"


def _set_handler_command_defaults(
    subparsers: argparse._SubParsersAction,
    handler_command: str | None = None,
    *,
    alchemy_leaves: bool = False,
) -> None:
    for name, choice in subparsers.choices.items():
        if alchemy_leaves and name in _ALCHEMY_SUBCOMMAND_HANDLERS:
            choice.set_defaults(handler_command=_ALCHEMY_SUBCOMMAND_HANDLERS[name])
            continue
        if name == "alchemy" and not alchemy_leaves:
            for action in choice._actions:
                if isinstance(action, argparse._SubParsersAction):
                    _set_handler_command_defaults(action, alchemy_leaves=True)
            continue
        canonical_command = handler_command or name
        choice.set_defaults(handler_command=canonical_command)
        for action in choice._actions:
            if isinstance(action, argparse._SubParsersAction):
                _set_handler_command_defaults(action, canonical_command)


def _register_drop_subcommand_parsers(subparsers: argparse._SubParsersAction) -> None:
    drop_url_parser = subparsers.add_parser("url", help="Fetch a web page into raw/inbox as source material.")
    _configure_drop_url_parser(drop_url_parser)
    drop_url_parser.set_defaults(handler_command="drop-url")

    drop_pdf_parser = subparsers.add_parser("pdf", help="Import a PDF asset into raw/assets without rewriting it.")
    _configure_drop_pdf_parser(drop_pdf_parser)
    drop_pdf_parser.set_defaults(handler_command="drop-pdf")

    drop_image_parser = subparsers.add_parser(
        "image", help="Import an image asset into raw/assets without converting it to markdown."
    )
    _configure_drop_image_parser(drop_image_parser)
    drop_image_parser.set_defaults(handler_command="drop-image")

    drop_repo_parser = subparsers.add_parser("repo", help="Snapshot a local or remote repo into raw/inbox.")
    _configure_drop_repo_parser(drop_repo_parser)
    drop_repo_parser.set_defaults(handler_command="drop-repo")

    drop_markdown_parser = subparsers.add_parser(
        "markdown",
        help="Capture inline markdown/text or copy a local markdown/text file into raw/inbox without metadata wrapping.",
    )
    _configure_drop_note_parser(drop_markdown_parser)
    drop_markdown_parser.set_defaults(handler_command="drop-note")

    drop_plan_parser = subparsers.add_parser(
        "plan",
        help="LLM-planned drop: classify a universal payload and execute the chosen action.",
    )
    _configure_drop_plan_parser(drop_plan_parser)
    drop_plan_parser.set_defaults(handler_command="drop-plan")


def _configure_drop_url_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="Web URL to fetch.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch and overwrite the existing raw note for this URL when one already exists.",
    )
    _add_auto_flags(parser)


def _configure_drop_plan_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "payload",
        help="Universal payload: URL, local path, question, or inline text. The LLM planner decides how to handle it.",
    )
    parser.add_argument("--title", help="Optional display title override.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch and overwrite the existing raw note for this URL when one already exists.",
    )
    _add_auto_flags(parser)


def _configure_drop_pdf_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source",
        help="Local PDF path (inside or outside the vault) or PDF URL. PDF assets must be ≤50 MB and start with %%PDF- magic bytes.",
    )
    parser.add_argument("--title", help="Optional display title.")
    _add_auto_flags(parser)


def _configure_drop_image_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source",
        help="Local image path (inside or outside the vault) or image URL. Image assets must be ≤25 MB and one of: PNG/JPEG/GIF/WebP/SVG.",
    )
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip optional LLM-backed visual analysis for the image drop.",
    )
    _add_auto_flags(parser)


def _configure_drop_repo_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="Vault-local repo path or remote git URL.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--max-files",
        type=int,
        default=200,
        help="Maximum number of repo tree entries to capture (1..1000).",
    )
    _add_auto_flags(parser)


def _configure_drop_note_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source", nargs="?", help="Optional markdown or text file path; local files are copied byte-for-byte."
    )
    parser.add_argument("--text", help="Inline note text. Use this instead of SOURCE for free-text capture.")
    parser.add_argument("--title", help="Optional display title.")
    parser.add_argument(
        "--kind",
        choices=("note", "transcript"),
        default="note",
        help="Capture kind. Transcript enables transcript-aware compile prompts.",
    )
    parser.add_argument(
        "--allow-sensitive",
        action="store_true",
        help="Allow note ingestion even when credential-like content is detected.",
    )
    _add_auto_flags(parser)


def _add_auto_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-auto",
        action="store_true",
        help="Skip deterministic compile+lint after a successful drop.",
    )
