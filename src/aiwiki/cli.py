"""Command line interface for aiwiki."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app import (
    ask_question,
    compile_wiki,
    ensure_layout,
    file_back,
    ingest_source,
    lint_wiki,
    nightly_health,
    review_machine_memory_action,
    review_page,
)
from .drop import drop_image, drop_pdf, drop_repo, drop_url
from .runner import auto_process_once, llm_status, run_ask, run_compile, run_lint, run_nightly, watch_inbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiwiki", description="Local-first knowledge compiler scaffold")
    parser.add_argument("--root", default=".", help="Project root. Defaults to the current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("layout", help="Create the expected directory layout.")

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a local file or URL stub.")
    ingest_parser.add_argument("source", help="Local file path or URL.")
    ingest_parser.add_argument("--title", help="Optional display title.")

    drop_url_parser = subparsers.add_parser("drop-url", help="Fetch a web page into raw/inbox as source material.")
    drop_url_parser.add_argument("url", help="Web URL to fetch.")
    drop_url_parser.add_argument("--title", help="Optional display title.")
    _add_auto_flags(drop_url_parser)

    drop_pdf_parser = subparsers.add_parser("drop-pdf", help="Import a PDF into raw/assets and raw/inbox.")
    drop_pdf_parser.add_argument("source", help="Local PDF path or PDF URL.")
    drop_pdf_parser.add_argument("--title", help="Optional display title.")
    _add_auto_flags(drop_pdf_parser)

    drop_image_parser = subparsers.add_parser("drop-image", help="Import an image into raw/assets and raw/inbox.")
    drop_image_parser.add_argument("source", help="Local image path or image URL.")
    drop_image_parser.add_argument("--title", help="Optional display title.")
    drop_image_parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip optional LLM-backed visual analysis for the image note.",
    )
    _add_auto_flags(drop_image_parser)

    drop_repo_parser = subparsers.add_parser("drop-repo", help="Snapshot a local or remote repo into raw/inbox.")
    drop_repo_parser.add_argument("source", help="Local repo path or remote git URL.")
    drop_repo_parser.add_argument("--title", help="Optional display title.")
    drop_repo_parser.add_argument(
        "--max-files",
        type=int,
        default=200,
        help="Maximum number of repo tree entries to capture.",
    )
    _add_auto_flags(drop_repo_parser)

    subparsers.add_parser("compile", help="Compile manifest entries into wiki source pages and indexes.")

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
    ask_parser.add_argument("question", help="Research question to package.")
    ask_parser.add_argument(
        "--format",
        choices=("report", "slides", "figure"),
        default="report",
        help="Output artifact format.",
    )

    run_ask_parser = subparsers.add_parser(
        "run-ask",
        help="Create a query artifact and use the configured LLM to fill it in place.",
    )
    run_ask_parser.add_argument("question", help="Research question to answer.")
    run_ask_parser.add_argument(
        "--format",
        choices=("report", "slides", "figure"),
        default="report",
        help="Output artifact format.",
    )

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

    review_parser = subparsers.add_parser(
        "review-page",
        help="Advance a decision or judgment page through the explicit review workflow.",
    )
    review_parser.add_argument("page", help="Path to a decision or judgment markdown page.")
    review_parser.add_argument("--status", required=True, help="Target review status for the page.")
    review_parser.add_argument("--note", help="Optional review note to store in the page.")
    review_parser.add_argument("--confidence", help="Optional confidence override for judgment pages.")

    action_review_parser = subparsers.add_parser(
        "review-action",
        help="Advance a machine-memory repair action through the explicit action workflow.",
    )
    action_review_parser.add_argument("action_id", help="Machine-memory action id.")
    action_review_parser.add_argument("--status", required=True, help="Target action status.")
    action_review_parser.add_argument("--note", help="Optional action review note.")

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
    subparsers.add_parser("llm-check", help="Show whether the LLM runner is configured.")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        if args.command == "layout":
            ensure_layout(root)
            result = {"root": str(root), "status": "ok"}
        elif args.command == "ingest":
            result = ingest_source(root, args.source, title=args.title)
        elif args.command == "drop-url":
            result = drop_url(root, args.url, title=args.title)
            result = _maybe_auto_process(root, result, args)
        elif args.command == "drop-pdf":
            result = drop_pdf(root, args.source, title=args.title)
            result = _maybe_auto_process(root, result, args)
        elif args.command == "drop-image":
            result = drop_image(root, args.source, title=args.title, enable_vision=not args.no_vision)
            result = _maybe_auto_process(root, result, args)
        elif args.command == "drop-repo":
            result = drop_repo(root, args.source, title=args.title, max_files=args.max_files)
            result = _maybe_auto_process(root, result, args)
        elif args.command == "compile":
            result = compile_wiki(root)
        elif args.command == "run-compile":
            result = run_compile(root, limit=args.limit)
        elif args.command == "ask":
            result = ask_question(root, args.question, args.format)
        elif args.command == "run-ask":
            result = run_ask(root, args.question, args.format)
        elif args.command == "file-back":
            result = file_back(root, args.artifact, title=args.title, kind=args.kind)
        elif args.command == "review-page":
            result = review_page(root, args.page, args.status, note=args.note, confidence=args.confidence)
        elif args.command == "review-action":
            result = review_machine_memory_action(root, args.action_id, args.status, note=args.note)
        elif args.command == "lint":
            result = lint_wiki(root)
        elif args.command == "run-lint":
            result = run_lint(root)
        elif args.command == "nightly":
            result = nightly_health(root)
        elif args.command == "run-nightly":
            result = run_nightly(
                root,
                compile_limit=args.compile_limit,
                semantic_lint=not args.no_semantic_lint,
            )
        elif args.command == "llm-check":
            result = llm_status()
        elif args.command == "auto-once":
            result = auto_process_once(
                root,
                compile_limit=args.compile_limit,
                deterministic_only=args.deterministic_only,
                semantic_lint=not args.no_semantic_lint,
            )
        elif args.command == "watch":
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
            raise ValueError(f"Unsupported command: {args.command}")
    except KeyboardInterrupt:  # pragma: no cover - interactive watch mode
        parser.exit(130, "interrupted\n")
    except Exception as exc:  # pragma: no cover - exercised in CLI usage
        parser.exit(1, f"error: {exc}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
