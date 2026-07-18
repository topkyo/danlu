"""CLI dispatch for aiwiki."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..app_cache import cache_status_summary, drop_query_cache, force_rebuild_query_cache
from ..app_linting.core import lint_wiki
from ..app_protocol import ensure_layout
from ..app_shell import build_shell_summary, rewrite_followup_payload_for_paths, shell_search, shell_status_dashboard
from ..app_state import (
    load_machine_memory_action_state,
    load_machine_memory_action_state_strict,
    load_today_snooze_state,
    save_today_snooze_state,
)
from ..app_vault import bootstrap_new_vault, sync_product_shell_plugin
from ..compile.pipeline import compile_wiki
from ..content.io import ingest_source
from ..content.memory import action_supports_low_risk_apply
from ..drop import drop_image, drop_note, drop_pdf, drop_repo, drop_url
from ..execution.archive import (
    apply_material_archive,
    revert_material_archive,
)
from ..execution.ask import (
    ask_question,
    file_back,
)
from ..execution.concept_rewrite import (
    apply_concept_rewrite,
    revert_concept_rewrite,
    review_concept_rewrite,
    verify_concept_rewrite,
)
from ..execution.lifecycle import (
    reactivate_concept,
    retire_concept,
    review_concept,
    review_concepts_batch,
)
from ..execution.machine_memory_actions import (
    apply_machine_memory_action,
    auto_resolve_machine_memory_actions,
    resolve_machine_memory_action_query,
    revert_machine_memory_action,
    review_machine_memory_action,
    review_machine_memory_actions_batch,
)
from ..execution.machine_memory_batch import (
    apply_machine_memory_actions_batch,
    revert_machine_memory_action_batch,
    review_pages_batch,
)
from ..execution.review import review_page
from ..execution.runtime_surfaces import (
    nightly_health,
    shell_status,
)
from ..planner import write_planner_log
from ..runner.alchemy import (
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
from ..runner.automation import auto_process_once, watch_inbox
from ..runner.clients import llm_probe, llm_status
from ..runner.commands import (
    run_audit_backfill,
    run_audit_preview,
    run_demote,
    run_l3_proposal_accept,
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
from ..runner.workflows import run_ask, run_ask_resume, run_ask_submit, run_compile, run_lint, run_nightly
from ..signals import collect_signals
from ..today_feed import FeedEntry, build_today_feed
from ..vault_queue import drain_vault_queue
from .dispatch_helpers import (
    _action_command,
    _action_review_item,
    _build_parser,
    _classify_review_bucket,
    _emit_legacy_drop_deprecation_warning,
    _feed_entry_to_review_item,
    _first_string,
    _flatten_model_fallback_args,
    _flatten_model_retry_args,
    _format_feed_entry_line,
    _format_l3_generation_preview_line,
    _format_l3_proposal_summary_line,
    _format_planner_decision_summary_line,
    _format_review_next_surface,
    _format_signal_show_text,
    _format_signal_summary_line,
    _handle_batch_review_alias,
    _handle_review_next,
    _l3_command,
    _l3_review_item,
    _latest_run_compile_summary,
    _maybe_auto_process,
    _metric_to_dict,
    _page_review_item,
    _pending_review_pages,
    _print_run_compile_fail_fast_breadcrumb,
    _read_text_argument,
    _ready_actions_batch_helper,
    _render_metrics_text,
    _render_today_text,
    _resolve_action_id,
    _resolve_action_ids,
    _resolve_review_action_ids,
    _resolve_review_concept_slugs,
    _resolve_review_pages,
    _review_action_item,
    _review_page_command,
    _review_queue_detail_buckets,
    _today_feed_to_json,
    _utc_now_iso,
    autonomy_set_command,
    autonomy_status_command,
    metrics_command,
    review_queue_command,
    today_command,
    today_snooze_command,
    trace_command,
)
from .legacy_argv import rewrite_legacy_top_level_argv
from .parsers import build_parser
from .universal_input import (
    _DROP_TYPED_SUBCOMMANDS,
    _looks_like_local_path,
    _rewrite_universal_drop_argv,
    _top_level_drop_index,
)

L3_PROPOSAL_REVIEW_STATUSES = ("accepted", "rejected")


def _resolve_vault_root(args: argparse.Namespace) -> Path:
    """Resolve vault root.

    Precedence: explicit --root > AIWIKI_VAULT env > cwd '.'.
    Prints a one-line stderr breadcrumb only when AIWIKI_VAULT env is used,
    so default-cwd and explicit-root paths stay silent (no test noise).
    """
    explicit = getattr(args, "root", None)
    if explicit is not None:
        return Path(explicit).resolve()
    env_vault = os.environ.get("AIWIKI_VAULT", "").strip()
    if env_vault:
        resolved = Path(env_vault).resolve()
        print(
            f"aiwiki: vault resolved from AIWIKI_VAULT env: {resolved}",
            file=sys.stderr,
        )
        return resolved
    return Path(".").resolve()


def _out(result: object, text_output: str | None = None) -> tuple[object, str | None]:
    return result, text_output


def _handle_vault_admin(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "layout":
        ensure_layout(root)
        return _out({"root": str(root), "status": "ok"})
    if args.handler_command == "new-vault":
        return _out(bootstrap_new_vault(root, Path(args.target).resolve(), force=args.force))
    if args.handler_command == "sync-product-shell":
        return _out(sync_product_shell_plugin(root, Path(args.target).resolve()))
    if args.handler_command == "ingest":
        return _out(ingest_source(root, args.source, title=args.title))
    if args.handler_command == "sync-evidence-graph":
        from ..vault_obsidian_graph import sync_evidence_graph_workspace

        return _out(sync_evidence_graph_workspace(root))
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_drop(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "drop-url":
        result = drop_url(root, args.url, title=args.title)
    elif args.handler_command == "drop-pdf":
        result = drop_pdf(root, args.source, title=args.title)
    elif args.handler_command == "drop-image":
        result = drop_image(root, args.source, title=args.title, enable_vision=not args.no_vision)
    elif args.handler_command == "drop-repo":
        result = drop_repo(root, args.source, title=args.title, max_files=args.max_files)
    elif args.handler_command == "drop-note":
        result = drop_note(
            root,
            args.source,
            title=args.title,
            text=args.text,
            kind=args.kind,
            allow_sensitive=args.allow_sensitive,
        )
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(_maybe_auto_process(root, result, args))


def _handle_compile_family(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "compile":
        result = compile_wiki(root)
        rewrite_state = result.get("concept_rewrite") or {}
        proposal_paths = [str(path or "") for path in rewrite_state.get("proposal_paths", []) if str(path or "")]
        if proposal_paths:
            result = {**result, **rewrite_followup_payload_for_paths(root, proposal_paths)}
        return _out(result)
    if args.handler_command == "run-compile":
        try:
            result = run_compile(root, limit=args.limit, paths=getattr(args, "paths", None))
        except Exception:
            _print_run_compile_fail_fast_breadcrumb(_latest_run_compile_summary(root))
            raise
        _print_run_compile_fail_fast_breadcrumb(result)
        return _out(result)
    if args.handler_command == "file-back":
        result = file_back(root, args.artifact, title=args.title, kind=args.kind)
        if result.get("next_step_hint"):
            print(f"aiwiki: → {result['next_step_hint']}", file=sys.stderr)
        return _out(result)
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_live_surface(args: argparse.Namespace, root: Path) -> tuple[object, str | None] | int:
    if args.handler_command == "today":
        return today_command(root, as_json=getattr(args, "json", False))
    if args.handler_command == "today-snooze":
        return _out(today_snooze_command(root, target=args.target, days=args.days, note=args.note))
    if args.handler_command == "review-queue":
        return review_queue_command(
            root,
            bucket=getattr(args, "bucket", None),
            limit=getattr(args, "limit", None),
            as_json=getattr(args, "json", False),
        )
    if args.handler_command == "trace":
        return trace_command(root, args.asset_id, direction=args.direction, depth=args.depth, as_json=args.json)
    if args.handler_command == "metrics":
        return metrics_command(root, as_json=args.json, delta=args.delta)
    if args.handler_command == "autonomy-status":
        return autonomy_status_command(root, as_json=args.json)
    if args.handler_command == "autonomy-disable":
        return autonomy_set_command(root, flag=args.flag, value=True)
    if args.handler_command == "autonomy-enable":
        return autonomy_set_command(root, flag=args.flag, value=False)
    if args.handler_command == "shell-status":
        return _out(shell_status(root))
    if args.handler_command == "dashboard":
        return _out(shell_status_dashboard(root))
    if args.handler_command == "search":
        return _out(shell_search(root, args.query, limit=args.limit))
    if args.handler_command == "vault-queue-drain":
        return _out(drain_vault_queue(root, limit=args.limit, execute=args.execute))
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_ask_family(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "ask":
        ask_kwargs = {"no_cache": args.no_cache}
        if getattr(args, "corpus", None) is not None:
            ask_kwargs["corpus_id_override"] = args.corpus
        return _out(ask_question(root, args.question, args.format, **ask_kwargs))
    if args.handler_command == "run-ask":
        ask_kwargs = {
            "lean": args.lean,
            "timeout_seconds": args.timeout,
            "no_cache": args.no_cache,
        }
        if hasattr(args, "corpus") and args.corpus is not None:
            ask_kwargs["corpus_id_override"] = args.corpus
        return _out(run_ask(root, args.question, args.format, **ask_kwargs))
    if args.handler_command == "run-ask-submit":
        ask_kwargs = {
            "lean": args.lean,
            "timeout_seconds": args.timeout,
            "no_cache": args.no_cache,
            "spawn": not args.no_spawn,
        }
        if hasattr(args, "corpus") and args.corpus is not None:
            ask_kwargs["corpus_id_override"] = args.corpus
        return _out(run_ask_submit(root, args.question, args.format, **ask_kwargs))
    if args.handler_command == "run-ask-resume":
        return _out(run_ask_resume(root, args.job_id))
    if args.handler_command == "report-subgraph":
        return _handle_report_subgraph(args, root)
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_report_subgraph(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    from ..memory.graph import (
        ReportSubgraphError,
        build_report_subgraph,
        render_report_subgraph_markdown,
    )

    try:
        subgraph = build_report_subgraph(root, args.report)
    except ReportSubgraphError as exc:
        print(f"aiwiki report-subgraph: {exc}", file=sys.stderr)
        sys.exit(2)
    markdown = render_report_subgraph_markdown(subgraph)
    report_path = Path(args.report)
    default_stem = report_path.stem
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
    else:
        output_path = root / "output" / "reports" / f"{default_stem}.subgraph.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    try:
        relative_out = output_path.relative_to(root)
        output_rel = str(relative_out).replace("\\", "/")
    except ValueError:
        output_rel = str(output_path)
    return _out(
        {
            "kind": "report-subgraph",
            "report": subgraph["report"],
            "anchor_node_ids": subgraph["anchor_node_ids"],
            "output_path": output_rel,
            "node_count": len(subgraph["nodes"]),
            "edge_count": len(subgraph["edges"]),
        }
    )


def _handle_promote_demote(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "promote":
        return _out(run_promote(root, args.artifact_ref))
    if args.handler_command == "demote":
        return _out(run_demote(root, args.artifact_ref))
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_alchemy(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "alchemy-start":
        include_elixir_ids = None
        if args.include_elixir is not None:
            include_elixir_ids = [item.strip() for item in args.include_elixir.split(",")]
        kwargs = {}
        if include_elixir_ids is not None:
            kwargs["include_elixir_ids"] = include_elixir_ids
        return _out(run_alchemy_start(root, args.corpus_id, args.topic, **kwargs))
    if args.handler_command == "alchemy-distill":
        include_elixir_ids = None
        if args.include_elixir is not None:
            include_elixir_ids = [item.strip() for item in args.include_elixir.split(",")]
        kwargs = {}
        if include_elixir_ids is not None:
            kwargs["include_elixir_ids"] = include_elixir_ids
        return _out(run_alchemy_distill(root, args.elixir_id, args.question, **kwargs))
    if args.handler_command == "alchemy-finalize":
        return _out(run_alchemy_finalize(root, elixir_id=args.elixir_id))
    if args.handler_command == "alchemy-promote":
        return _out(run_alchemy_promote(root, elixir_id=args.elixir_id, note=args.note))
    if args.handler_command == "alchemy-revert":
        path = run_alchemy_revert(root, elixir_id=args.elixir_id, note=args.note)
        return _out({"elixir_id": args.elixir_id, "path": str(path.relative_to(root))})
    if args.handler_command == "alchemy-demote":
        path = run_alchemy_demote(root, elixir_id=args.elixir_id, note=args.note)
        return _out({"elixir_id": args.elixir_id, "path": str(path.relative_to(root))})
    if args.handler_command == "alchemy":
        return _handle_alchemy_lane(args, root)
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_alchemy_lane(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.alchemy_lane == "legacy-migration":
        result = run_alchemy_legacy_migration_preview(root, limit=args.limit) if args.dry_run else run_alchemy_legacy_migration_apply(root, limit=args.limit, note=args.note)
    elif args.alchemy_lane == "judge":
        if args.apply:
            result = run_alchemy_judge_apply(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit, note=args.note)
        elif args.propose:
            result = run_alchemy_judge_propose(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit, note=args.note)
        else:
            result = run_alchemy_judge_preview(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit)
    elif args.alchemy_lane == "judge-proposal":
        result = run_alchemy_judge_proposal_apply(root, args.proposal, note=args.note)
    elif args.alchemy_lane == "distill":
        if args.apply:
            result = run_alchemy_distill_apply(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit, note=args.note)
        else:
            result = run_alchemy_distill_preview(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit)
    elif args.alchemy_lane == "review":
        if args.apply:
            result = run_alchemy_review_apply(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit, note=args.note)
        else:
            result = run_alchemy_review_preview(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit)
    elif args.alchemy_lane == "propose":
        if args.apply:
            result = run_alchemy_propose_apply(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit, note=args.note)
        else:
            result = run_alchemy_propose_preview(root, scope=args.scope, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens, limit=args.limit)
    elif args.alchemy_lane == "auto":
        result = run_alchemy_auto(root, apply=args.apply, lanes=args.lane or None, scope=args.scope, primitives=args.primitive or None, note=args.note, planner_log_path=args.planner_log_path, signals_path=args.signals_path, max_signals=args.max_signals, max_pages=args.max_pages, max_tokens=args.max_tokens)
    elif args.alchemy_lane == "superseded-cleanup":
        result = run_alchemy_superseded_cleanup_preview(root, limit=args.limit) if args.dry_run else run_alchemy_superseded_cleanup_apply(root, limit=args.limit, note=args.note)
    else:
        if args.dry_run == args.apply:
            raise ValueError("alchemy heavy/light requires exactly one of --dry-run or --apply")
        lane_kwargs = {"lane": args.alchemy_lane, "scope": args.scope, "planner_log_path": args.planner_log_path, "signals_path": args.signals_path, "max_signals": args.max_signals, "max_pages": args.max_pages, "max_tokens": args.max_tokens}
        result = run_alchemy_lane_dry_run(root, **lane_kwargs) if args.dry_run else run_alchemy_lane_apply(root, action_ids=args.action_id, primitives=args.primitive, note=args.note, **lane_kwargs)
    return _out(result)


def _handle_l3(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    text_output = None
    if args.handler_command == "l3-proposal-create":
        result = run_l3_proposal_create(root, kind=args.kind, proposal_id=args.proposal_id, target_file=args.target_file, content=_read_text_argument(root, args.content_file), rationale=args.rationale, evidence_refs=args.evidence_refs, signal_ids=args.signal_ids, pattern=args.pattern)
    elif args.handler_command == "l3-proposal-generate":
        result = run_l3_proposal_generate(root, planner_log_path=args.planner_log_path, limit=args.limit, apply=args.apply)
    elif args.handler_command == "review":
        if args.review_command == "proposals":
            result = run_l3_proposal_list(root, kind=args.kind, state=args.state)
            if not args.json:
                text_output = "\n".join(_format_l3_proposal_summary_line(item) for item in result) or "(no L3 proposals)"
        elif args.review_command == "proposal-generation":
            result = run_l3_proposal_generation_preview(root, planner_log_path=args.planner_log_path, limit=args.limit)
            if not args.json:
                candidates = result.get("candidates", []) if isinstance(result, dict) else []
                text_output = "\n".join(_format_l3_generation_preview_line(item) for item in candidates) or "(no L3 proposal generation candidates)"
        elif args.review_command == "proposal":
            if args.status not in L3_PROPOSAL_REVIEW_STATUSES:
                raise ValueError(f"Unsupported L3 proposal review status: {args.status!r}; expected one of: {L3_PROPOSAL_REVIEW_STATUSES}")
            if args.status == "accepted":
                result = run_l3_proposal_accept(root, args.proposal_id, note=args.note)
            else:
                result = run_l3_proposal_reject(root, args.proposal_id, note=args.note)
        else:
            raise ValueError(f"Unsupported review command: {args.review_command}")
    elif args.handler_command == "apply":
        result = run_l3_proposal_apply(root, args.proposal_id, note=args.note)
    elif args.handler_command == "revert":
        result = run_l3_proposal_revert(root, args.receipt_id, note=args.note)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result, text_output)


def _handle_signals_planner_audit(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    text_output = None
    if args.handler_command == "signals-list":
        result = run_signals_list(root, kind=args.kind, trace_id=args.trace_id, since=args.since, limit=args.limit)
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
        result = run_planner_log_list(root, decision=args.decision, signal_id=args.signal_id, trace_id=args.trace_id, since=args.since, limit=args.limit)
        if not args.json:
            text_output = "\n".join(_format_planner_decision_summary_line(item) for item in result) or "(no planner decisions)"
    elif args.handler_command == "planner-log-rollback":
        result = run_planner_log_rollback_preview(root, signal_id=args.signal_id, trace_id=args.trace_id, limit=args.limit) if args.dry_run else run_planner_log_rollback(root, signal_id=args.signal_id, trace_id=args.trace_id, limit=args.limit, apply=True)
    elif args.handler_command == "audit-preview":
        if not args.dry_run:
            raise ValueError("audit-preview requires --dry-run")
        result = run_audit_preview(root, limit=args.limit)
    elif args.handler_command == "audit-backfill":
        result = run_audit_backfill(root, limit=args.limit, apply=args.apply)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result, text_output)


def _handle_review_lifecycle(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "review-page":
        review_pages = _resolve_review_pages(root, args.page, use_next=args.next, batch=args.batch, all_pending=args.all_pending)
        result = review_pages_batch(root, review_pages, args.status, note=args.note, confidence=args.confidence) if len(review_pages) > 1 or args.batch or args.all_pending else review_page(root, review_pages[0], args.status, note=args.note, confidence=args.confidence)
    elif args.handler_command == "review-rewrite":
        result = review_concept_rewrite(root, args.slug, args.status, note=args.note)
    elif args.handler_command == "apply-rewrite":
        result = apply_concept_rewrite(root, args.slug, note=args.note, dry_run=args.dry_run)
    elif args.handler_command == "verify-rewrite":
        result = verify_concept_rewrite(root, args.slug, note=args.note)
    elif args.handler_command == "revert-rewrite":
        result = revert_concept_rewrite(root, args.slug, note=args.note)
    elif args.handler_command == "retire-concept":
        slugs = list(args.slugs) if isinstance(args.slugs, list) else [args.slugs]
        if len(slugs) == 1:
            result = retire_concept(root, slugs[0], note=args.note)
        else:
            receipts: list[dict[str, object]] = []
            for slug in slugs:
                receipts.append(retire_concept(root, slug, note=args.note))
            result = {"slugs": slugs, "receipts": receipts, "count": len(receipts)}
        compile_wiki(root)
    elif args.handler_command == "reactivate-concept":
        slugs = list(args.slugs) if isinstance(args.slugs, list) else [args.slugs]
        if len(slugs) == 1:
            result = reactivate_concept(root, slugs[0], note=args.note)
        else:
            receipts = []
            for slug in slugs:
                receipts.append(reactivate_concept(root, slug, note=args.note))
            result = {"slugs": slugs, "receipts": receipts, "count": len(receipts)}
        compile_wiki(root)
    elif args.handler_command == "review-concept":
        review_slugs = _resolve_review_concept_slugs(root, list(args.slugs) if isinstance(args.slugs, list) else [], all_pending=args.all_pending)
        result = review_concepts_batch(root, review_slugs, status=args.status, note=args.note) if len(review_slugs) > 1 or args.all_pending else review_concept(root, review_slugs[0], status=args.status, note=args.note)
        compile_wiki(root)
    elif args.handler_command == "review-action":
        review_action_ids = _resolve_review_action_ids(root, list(args.action_ids) if isinstance(args.action_ids, list) else [], all_pending=args.all_pending, kind=args.kind, execution_band=args.execution_band)
        result = review_machine_memory_action(root, review_action_ids[0], args.status, note=args.note) if len(review_action_ids) == 1 and not args.all_pending else review_machine_memory_actions_batch(root, review_action_ids, args.status, note=args.note)
    elif args.handler_command == "apply-action":
        action_ids = _resolve_action_ids(root, args.action_id, batch=args.batch, all_accepted_low_risk=args.all_accepted_low_risk)
        if len(action_ids) > 1 or args.batch or args.all_accepted_low_risk:
            if args.bundle:
                raise ValueError("--bundle is only supported for single-action apply.")
            result = apply_machine_memory_actions_batch(root, action_ids, note=args.note, dry_run=args.dry_run)
        else:
            result = apply_machine_memory_action(root, action_ids[0], note=args.note, dry_run=args.dry_run, bundle_path=args.bundle)
    elif args.handler_command == "auto-resolve-actions":
        result = auto_resolve_machine_memory_actions(
            root,
            dry_run=args.dry_run,
            limit=args.limit,
            include_proposed=not args.accepted_only,
            note=args.note,
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
    elif args.handler_command == "batch-review":
        result = _handle_batch_review_alias(root, args)
    elif args.handler_command == "review-next":
        result = _handle_review_next(root, args)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result)


def _handle_runtime_workflows(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "lint":
        result = lint_wiki(root)
    elif args.handler_command == "run-lint":
        result = run_lint(root)
    elif args.handler_command == "nightly":
        result = nightly_health(root)
    elif args.handler_command == "run-nightly":
        result = run_nightly(root, compile_limit=args.compile_limit, semantic_lint=not args.no_semantic_lint)
    elif args.handler_command == "signals-replay":
        result = collect_signals(root, sources=args.source, trace_id=args.trace_id)
    elif args.handler_command == "planner-log-replay":
        result = write_planner_log(root, signals_path=args.signals_path, mode="execute" if args.execute else "observe_only")
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result)


def _handle_ops(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    text_output = None
    if args.handler_command == "llm-check":
        result = llm_probe(root, probe_all=args.probe_all, timeout_seconds=args.probe_timeout) if args.probe or args.probe_all else llm_status()
        if getattr(args, "format", "json") == "human":
            from aiwiki.cli.llm_check_render import render_llm_check_human

            text_output = render_llm_check_human(result)
    elif args.handler_command == "llm-telemetry":
        from aiwiki.llm_telemetry import aggregate_llm_telemetry

        result = aggregate_llm_telemetry(root, limit=max(1, int(args.limit)))
    elif args.handler_command == "backend-telemetry":
        from aiwiki.llm_telemetry import aggregate_backend_telemetry

        result = aggregate_backend_telemetry(root, limit=max(1, int(args.limit)))
    elif args.handler_command == "cache":
        selected_actions = int(bool(args.status)) + int(bool(args.rebuild)) + int(bool(args.drop))
        if selected_actions != 1:
            raise ValueError("Provide exactly one of --status, --rebuild, or --drop.")
        result = cache_status_summary(root) if args.status else force_rebuild_query_cache(root) if args.rebuild else drop_query_cache(root)
    elif args.handler_command == "auto-once":
        deterministic_only = not bool(getattr(args, "with_llm", False)) or bool(args.deterministic_only)
        result = auto_process_once(root, compile_limit=args.compile_limit, deterministic_only=deterministic_only, semantic_lint=not args.no_semantic_lint)
    elif args.handler_command == "watch":
        deterministic_only = not bool(getattr(args, "with_llm", False)) or bool(args.deterministic_only)
        result = watch_inbox(root, interval_seconds=args.interval, compile_limit=args.compile_limit, deterministic_only=deterministic_only, semantic_lint=not args.no_semantic_lint, process_initial=not args.skip_initial, max_cycles=args.max_cycles)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result, text_output)


_VAULT_ADMIN_HANDLERS = {
    "layout": _handle_vault_admin,
    "new-vault": _handle_vault_admin,
    "sync-product-shell": _handle_vault_admin,
    "ingest": _handle_vault_admin,
    "sync-evidence-graph": _handle_vault_admin,
}

_DROP_HANDLERS = {
    "drop-url": _handle_drop,
    "drop-pdf": _handle_drop,
    "drop-image": _handle_drop,
    "drop-repo": _handle_drop,
    "drop-note": _handle_drop,
}

_COMPILE_PROTOCOL_HANDLERS = {
    "compile": _handle_compile_family,
    "run-compile": _handle_compile_family,
    "file-back": _handle_compile_family,
}

_LIVE_SURFACE_HANDLERS = {
    "today": _handle_live_surface,
    "today-snooze": _handle_live_surface,
    "review-queue": _handle_live_surface,
    "trace": _handle_live_surface,
    "metrics": _handle_live_surface,
    "autonomy-status": _handle_live_surface,
    "autonomy-disable": _handle_live_surface,
    "autonomy-enable": _handle_live_surface,
    "shell-status": _handle_live_surface,
    "dashboard": _handle_live_surface,
    "search": _handle_live_surface,
    "vault-queue-drain": _handle_live_surface,
}

_ASK_HANDLERS = {
    "ask": _handle_ask_family,
    "run-ask": _handle_ask_family,
    "run-ask-submit": _handle_ask_family,
    "run-ask-resume": _handle_ask_family,
    "report-subgraph": _handle_ask_family,
}

_ALCHEMY_HANDLERS = {
    "promote": _handle_promote_demote,
    "demote": _handle_promote_demote,
    "alchemy-start": _handle_alchemy,
    "alchemy-distill": _handle_alchemy,
    "alchemy-finalize": _handle_alchemy,
    "alchemy-promote": _handle_alchemy,
    "alchemy-revert": _handle_alchemy,
    "alchemy-demote": _handle_alchemy,
    "alchemy": _handle_alchemy,
}

_L3_HANDLERS = {
    "l3-proposal-create": _handle_l3,
    "l3-proposal-generate": _handle_l3,
    "review": _handle_l3,
    "apply": _handle_l3,
    "revert": _handle_l3,
}

_SIGNALS_PLANNER_AUDIT_HANDLERS = {
    "signals-list": _handle_signals_planner_audit,
    "signals-show": _handle_signals_planner_audit,
    "planner-log-list": _handle_signals_planner_audit,
    "planner-log-rollback": _handle_signals_planner_audit,
    "audit-preview": _handle_signals_planner_audit,
    "audit-backfill": _handle_signals_planner_audit,
}

_REVIEW_LIFECYCLE_HANDLERS = {
    "review-page": _handle_review_lifecycle,
    "review-rewrite": _handle_review_lifecycle,
    "apply-rewrite": _handle_review_lifecycle,
    "verify-rewrite": _handle_review_lifecycle,
    "revert-rewrite": _handle_review_lifecycle,
    "retire-concept": _handle_review_lifecycle,
    "reactivate-concept": _handle_review_lifecycle,
    "review-concept": _handle_review_lifecycle,
    "review-action": _handle_review_lifecycle,
    "apply-action": _handle_review_lifecycle,
    "auto-resolve-actions": _handle_review_lifecycle,
    "revert-action": _handle_review_lifecycle,
    "apply-archive": _handle_review_lifecycle,
    "revert-archive": _handle_review_lifecycle,
    "batch-review": _handle_review_lifecycle,
    "review-next": _handle_review_lifecycle,
}

_RUNTIME_WORKFLOW_HANDLERS = {
    "lint": _handle_runtime_workflows,
    "run-lint": _handle_runtime_workflows,
    "nightly": _handle_runtime_workflows,
    "run-nightly": _handle_runtime_workflows,
    "signals-replay": _handle_runtime_workflows,
    "planner-log-replay": _handle_runtime_workflows,
}

_OPS_HANDLERS = {
    "llm-check": _handle_ops,
    "llm-telemetry": _handle_ops,
    "backend-telemetry": _handle_ops,
    "cache": _handle_ops,
    "auto-once": _handle_ops,
    "watch": _handle_ops,
}

_HANDLERS = {
    **_VAULT_ADMIN_HANDLERS,
    **_DROP_HANDLERS,
    **_COMPILE_PROTOCOL_HANDLERS,
    **_LIVE_SURFACE_HANDLERS,
    **_ASK_HANDLERS,
    **_ALCHEMY_HANDLERS,
    **_L3_HANDLERS,
    **_SIGNALS_PLANNER_AUDIT_HANDLERS,
    **_REVIEW_LIFECYCLE_HANDLERS,
    **_RUNTIME_WORKFLOW_HANDLERS,
    **_OPS_HANDLERS,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Universal drop may emit `advanced ask`; legacy rewrite handles bare
    # operator top-level tokens (compile, drop-url, ask, ...).
    argv = rewrite_legacy_top_level_argv(argv)
    argv = _rewrite_universal_drop_argv(argv)
    args = parser.parse_args(argv)
    root = _resolve_vault_root(args)
    fallback_env_was_set = "AIWIKI_MODEL_FALLBACK" in os.environ
    previous_fallback_env = os.environ.get("AIWIKI_MODEL_FALLBACK", "")
    model_retry = getattr(args, "model_retry", None)
    if model_retry is not None:
        os.environ["AIWIKI_MODEL_FALLBACK"] = ",".join(_flatten_model_retry_args(model_retry))

    result: object = None
    text_output: str | None = None
    try:
        _emit_legacy_drop_deprecation_warning(args)
        handler = _HANDLERS.get(args.handler_command)
        if handler is None:
            raise ValueError(f"Unsupported command: {args.handler_command}")
        outcome = handler(args, root)
        if isinstance(outcome, int):
            return outcome
        result, text_output = outcome
    except KeyboardInterrupt:  # pragma: no cover - interactive watch mode
        parser.exit(130, "interrupted\n")
    except Exception as exc:  # pragma: no cover - exercised in CLI usage
        parser.exit(1, f"error: {exc}\n")
    finally:
        if model_retry is not None:
            if fallback_env_was_set:
                os.environ["AIWIKI_MODEL_FALLBACK"] = previous_fallback_env
            else:
                os.environ.pop("AIWIKI_MODEL_FALLBACK", None)

    if text_output is not None:
        print(text_output)
        return 0

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
