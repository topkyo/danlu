"""CLI dispatch for aiwiki."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ..app_cache import cache_status_summary, drop_query_cache, force_rebuild_query_cache
from ..app_compile import (
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
from ..app_content import action_supports_low_risk_apply, ingest_source
from ..app_protocol import ensure_layout, load_protocol_state
from ..app_shell import build_shell_summary, rewrite_recovery_payload_for_paths, shell_search, shell_status_dashboard
from ..app_state import load_machine_memory_action_state
from ..app_vault import bootstrap_new_vault
from ..drop import drop_image, drop_note, drop_pdf, drop_repo, drop_url
from ..input_router import UniversalRoute, classify_universal_input
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
)
from ..runner.workflows import run_ask, run_compile, run_lint, run_nightly
from ..signals import collect_signals
from ..today_feed import FeedEntry, build_today_feed
from .parsers import build_parser

_DROP_TYPED_SUBCOMMANDS = {"url", "pdf", "image", "repo", "note"}


def _rewrite_universal_drop_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        rewritten = list(sys.argv[1:])
    else:
        rewritten = list(argv)

    drop_index = _top_level_drop_index(rewritten)
    if drop_index is None:
        return argv
    if len(rewritten) <= drop_index + 1:
        return rewritten

    payload = rewritten[drop_index + 1]
    if payload in _DROP_TYPED_SUBCOMMANDS or payload in {"question", "-h", "--help"}:
        return rewritten
    if "-h" in rewritten[drop_index + 2 :] or "--help" in rewritten[drop_index + 2 :]:
        return rewritten

    if payload == "-":
        payload = sys.stdin.read().strip()
        if not payload:
            print("error: empty stdin payload", file=sys.stderr)
            raise SystemExit(2)

    decision = classify_universal_input(payload)
    routed_payload = decision.payload
    rest = rewritten[drop_index + 2 :]
    if decision.route == UniversalRoute.ASK:
        rewritten[drop_index:] = ["ask", routed_payload, *rest]
    else:
        routed_subcommand = {
            UniversalRoute.URL: "url",
            UniversalRoute.PDF: "pdf",
            UniversalRoute.IMAGE: "image",
            UniversalRoute.REPO: "repo",
            UniversalRoute.NOTE: "note",
        }[decision.route]
        rewritten[drop_index:] = ["drop", routed_subcommand, routed_payload, *rest]
    return rewritten


def _top_level_drop_index(argv: list[str]) -> int | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "drop":
            return index
        if token in {"--root", "--model-fallback"}:
            index += 2
            continue
        if token.startswith("--root=") or token.startswith("--model-fallback="):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = _rewrite_universal_drop_argv(argv)
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
        elif args.handler_command == "trace":
            return trace_command(
                root,
                args.asset_id,
                direction=args.direction,
                depth=args.depth,
                as_json=args.json,
            )
        elif args.handler_command == "metrics":
            return metrics_command(root, as_json=args.json, delta=args.delta)
        elif args.handler_command == "autonomy-status":
            return autonomy_status_command(root, as_json=args.json)
        elif args.handler_command == "autonomy-disable":
            return autonomy_set_command(root, flag=args.flag, value=True)
        elif args.handler_command == "autonomy-enable":
            return autonomy_set_command(root, flag=args.flag, value=False)
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
            if getattr(args, "format", "json") == "human":
                from aiwiki.cli.llm_check_render import render_llm_check_human

                text_output = render_llm_check_human(result)
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
    feed = build_today_feed(summary)
    print(_render_today_text(feed, summary))
    return 0


def trace_command(
    root: Path,
    asset_id: str,
    *,
    direction: str = "up",
    depth: int = 5,
    as_json: bool = False,
) -> int:
    """证据链追溯：渲染 ASCII 树或 JSON。"""
    from aiwiki.trace import render_trace_text, resolve_trace

    node = resolve_trace(root, asset_id, direction=direction, max_depth=depth)
    if as_json:
        print(json.dumps(node.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_trace_text(node, direction=direction))
    return 0


def metrics_command(root: Path, *, as_json: bool = False, delta: str | None = None) -> int:
    from aiwiki import metrics_history
    from aiwiki.metrics import compute_metrics
    from aiwiki.metrics_io import build_metrics_snapshot

    snapshot = build_metrics_snapshot(root)
    metrics = compute_metrics(snapshot)

    # M7.3.1 Stage B: append history snapshot (best-effort).
    now_iso = snapshot.now_iso
    # Numeric subset for delta math.
    numeric_metrics = {
        str(m.key): float(m.value)
        for m in metrics
        if isinstance(m.value, (int, float))
    }
    # Full history record keeps all 7 keys (None becomes null in JSONL) so
    # later samples can always line up against the same schema.
    history_record = {
        str(m.key): (float(m.value) if isinstance(m.value, (int, float)) else None)
        for m in metrics
    }
    metrics_history.append_snapshot(root, now_iso, history_record)

    if as_json:
        print(json.dumps([_metric_to_dict(metric) for metric in metrics], indent=2, ensure_ascii=False))
    else:
        print(_render_metrics_text(metrics))

    if delta:
        window_days = 7 if delta == "7d" else 30
        baseline = metrics_history.find_baseline(root, now_iso, window_days)
        block = metrics_history.format_delta_block(
            window_label=delta,
            baseline=baseline,
            current=numeric_metrics,
        )
        print()
        print(block)

    return 0


def autonomy_status_command(root: Path, *, as_json: bool = False) -> int:
    from aiwiki import autonomy_policy

    status = autonomy_policy.policy_status(root)
    if as_json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    lines = [
        f"policy file : {status['policy_path']}",
        f"file exists : {status['policy_file_exists']}",
        f"global env  : {status['global_override_env']} = {'1 (active)' if status['global_override_active'] else 'unset'}",
        "flags:",
    ]
    for name, info in status["flags"].items():
        marker = "DISABLED" if info["effective"] else "enabled "
        reason = f"  ({info['reason']})" if info["reason"] else ""
        lines.append(f"  [{marker}] {name}  file_value={info['file_value']}{reason}")
    print("\n".join(lines))
    return 0


def autonomy_set_command(root: Path, *, flag: str, value: bool) -> int:
    import sys

    from aiwiki import autonomy_policy

    if flag not in autonomy_policy.KNOWN_FLAGS:
        print(
            f"Unknown autonomy flag: {flag}. Known flags: {', '.join(autonomy_policy.KNOWN_FLAGS)}",
            file=sys.stderr,
        )
        return 2
    autonomy_policy.set_flag(root, flag, value)
    action = "disabled" if value else "enabled"
    print(f"autonomy flag {flag} → {action} (file: {autonomy_policy.policy_path(root)})")
    return 0


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metric_to_dict(metric) -> dict[str, object]:
    return {
        "key": metric.key,
        "value": metric.value,
        "unit": metric.unit,
        "reason": metric.reason,
        "sample_size": metric.sample_size,
    }


def _render_metrics_text(metrics) -> str:
    lines = ["炼丹炉 Knowledge Compounding Metrics", ""]
    labels = {
        "provenance_completeness": "知识溯源完整度",
        "stale_ratio": "过期页面占比",
        "review_closure_rate": "审议关闭率（7d）",
        "proposal_acceptance_rate": "提案接受率",
        "judgment_revisit_rate": "判断重访率",
        "output_file_back_rate": "输出回流率",
        "elixir_reuse_count": "Elixir 复用次数",
    }
    for metric in metrics:
        key = str(metric.key)
        name = labels.get(key, key)
        value = metric.value
        reason = metric.reason
        unit = metric.unit
        sample_size = metric.sample_size
        if value is None:
            lines.append(f"- {name} ({key}): 不可用 — {reason}")
        else:
            lines.append(f"- {name} ({key}): {value} {unit} (n={sample_size})")
    lines.append("")
    return "\n".join(lines)


def _render_today_text(feed: list[FeedEntry], summary: dict[str, object]) -> str:
    generated_at = str(summary.get("generated_at") or "")
    active_protocol = str(summary.get("active_protocol") or "")
    lines = [
        "炼丹炉 Today",
        f"Generated: {generated_at}",
        f"Active protocol: {active_protocol}",
        "",
    ]

    grouped: dict[str, list[FeedEntry]] = {"decision": [], "proposal": [], "report": [], "elixir": [], "action": []}
    for entry in feed:
        grouped[entry.kind].append(entry)

    section_specs = [
        ("Today's Reports", "report", "(no reports today)"),
        ("Needs Review", "decision", "(no pending review)"),
        ("Completed Elixirs", "elixir", "(no completed elixirs today)"),
        ("L3 Proposals", "proposal", "(no L3 proposals need attention)"),
        ("Suggested Next Actions", "action", "(no suggested next actions)"),
    ]

    for heading, kind, empty_msg in section_specs:
        lines.append(heading)
        kind_entries = grouped[kind]
        if kind_entries:
            for entry in kind_entries:
                lines.append(_format_feed_entry_line(entry))
        else:
            lines.append(empty_msg)
        lines.append("")

    lines.extend(
        [
            "Advanced",
            "Run `aiwiki advanced ...` for system status, receipts, audit, repair, lanes, and debugging.",
            "Run `aiwiki metrics` for knowledge compounding metrics.",
        ]
    )
    return "\n".join(lines)


def _format_feed_entry_line(entry: FeedEntry) -> str:
    """统一 entry 渲染：- [{protocol}] {title} — {summary} — {target}"""
    protocol = entry.protocol or "?"
    return f"- [{protocol}] {entry.title} — {entry.summary} — {entry.target}"


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
