"""CLI dispatch for aiwiki."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ..app_linting.core import lint_wiki
from ..app_shell import build_shell_summary, rewrite_followup_payload_for_paths
from ..compile.pipeline import compile_wiki
from ..drop import drop_image, drop_note, drop_pdf, drop_repo, drop_url
from ..execution.ask import (
    ask_question,
    file_back,
)
from ..execution.review import review_page
from ..execution.runtime_surfaces import (
    nightly_health,
    shell_status,
)
from ..executor import AskSignal, execute_plan
from ..input_planner import PlannerError, plan_input
from ..input_router import UniversalRoute, classify_universal_input
from ..runner.alchemy import (
    run_alchemy_demote,
    run_alchemy_distill,
    run_alchemy_finalize,
    run_alchemy_promote,
    run_alchemy_revert,
    run_alchemy_start,
)
from ..runner.automation import watch_inbox
from ..runner.clients import llm_probe, llm_status
from ..runner.workflows import run_ask, run_ask_resume, run_ask_submit, run_nightly
from ..vault.bootstrap import bootstrap_new_vault
from ..vault.plugin import sync_product_shell_plugin
from .dispatch_helpers import (
    _emit_legacy_drop_deprecation_warning,
    _flatten_model_retry_args,
    _maybe_auto_process,
    metrics_command,
    review_queue_command,
    today_command,
    trace_command,
)
from .legacy_argv import rewrite_legacy_top_level_argv
from .parsers import build_parser
from .universal_input import _rewrite_universal_drop_argv


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
    if args.handler_command == "new-vault":
        return _out(bootstrap_new_vault(root, Path(args.target).resolve(), force=args.force))
    if args.handler_command == "sync-product-shell":
        return _out(sync_product_shell_plugin(root, Path(args.target).resolve()))
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_drop(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    refresh = bool(getattr(args, "refresh", False))
    if args.handler_command == "drop-url":
        result = drop_url(root, args.url, title=args.title, refresh=refresh)
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
    elif args.handler_command == "drop-plan":
        return _handle_drop_plan(args, root)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(_maybe_auto_process(root, result, args))


def _reject_path_like_ask(payload: str) -> None:
    """Fail loud when a path-like payload would otherwise become ASK."""
    from .universal_input import _looks_like_local_path

    if _looks_like_local_path(payload):
        print(
            f"error: drop payload looks like a file path but matches no known type: {payload!r}\n"
            "hint: use 'drop markdown <path>' for markdown/text files, "
            "or prefix with 'ask:' to force a question.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _handle_drop_plan(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    """LLM-planned drop: planner decides action, executor runs it.

    On any planner failure (LLM error, JSON parse error, autonomy block),
    fall back to the deterministic classifier and re-dispatch to the existing
    typed drop_* handler. This keeps `drop <payload>` working offline and
    when the LLM is unavailable.
    """
    payload = args.payload
    title = getattr(args, "title", None)
    try:
        plan = plan_input(payload, root)
    except PlannerError as exc:
        print(f"aiwiki: LLM planner unavailable ({exc}); falling back to deterministic router.", file=sys.stderr)
        return _dispatch_fallback_route(root, payload, title, args)

    result = execute_plan(root, plan, payload, refresh=bool(getattr(args, "refresh", False)))
    if isinstance(result, AskSignal):
        ask_payload = result.get("payload") or payload
        _reject_path_like_ask(str(ask_payload))
        ask_result = ask_question(root, ask_payload, "report")
        return _out(_maybe_auto_process(root, ask_result, args))
    return _out(_maybe_auto_process(root, result, args))


def _dispatch_fallback_route(
    root: Path, payload: str, title: str | None, args: argparse.Namespace
) -> tuple[object, str | None]:
    """Deterministic fallback: use classify_universal_input and call the matching drop_*."""
    decision = classify_universal_input(payload)
    routed_payload = decision.payload
    if decision.route == UniversalRoute.URL:
        result = drop_url(root, routed_payload, title=title, refresh=bool(getattr(args, "refresh", False)))
    elif decision.route == UniversalRoute.PDF:
        result = drop_pdf(root, routed_payload, title=title)
    elif decision.route == UniversalRoute.IMAGE:
        result = drop_image(root, routed_payload, title=title, enable_vision=True)
    elif decision.route == UniversalRoute.REPO:
        result = drop_repo(root, routed_payload, title=title)
    elif decision.route == UniversalRoute.NOTE:
        result = drop_note(root, routed_payload, title=title)
    else:  # ASK
        _reject_path_like_ask(routed_payload)
        result = ask_question(root, routed_payload, "report")
    return _out(_maybe_auto_process(root, result, args))


def _handle_compile_family(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "compile":
        result = compile_wiki(root)
        rewrite_state = result.get("concept_rewrite") or {}
        proposal_paths = [str(path or "") for path in rewrite_state.get("proposal_paths", []) if str(path or "")]
        if proposal_paths:
            result = {**result, **rewrite_followup_payload_for_paths(root, proposal_paths)}
        return _out(result)
    if args.handler_command == "file-back":
        result = file_back(root, args.artifact, title=args.title, kind="judgment")
        if result.get("next_step_hint"):
            print(f"aiwiki: → {result['next_step_hint']}", file=sys.stderr)
        return _out(result)
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_live_surface(args: argparse.Namespace, root: Path) -> tuple[object, str | None] | int:
    if args.handler_command == "today":
        return today_command(root, as_json=getattr(args, "json", False))
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
    if args.handler_command == "shell-status":
        return _out(shell_status(root))
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
    raise ValueError(f"Unsupported command: {args.handler_command}")


def _handle_review_lifecycle(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "review-page":
        if not args.page:
            raise ValueError("Provide a review page path.")
        result = review_page(
            root,
            args.page,
            args.status,
            note=args.note,
            confidence=args.confidence,
        )
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result)


def _handle_runtime_workflows(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    if args.handler_command == "lint":
        result = lint_wiki(root)
    elif args.handler_command == "nightly":
        result = nightly_health(root)
    elif args.handler_command == "run-nightly":
        result = run_nightly(root, compile_limit=args.compile_limit)
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result)


def _handle_ops(args: argparse.Namespace, root: Path) -> tuple[object, str | None]:
    text_output = None
    if args.handler_command == "llm-check":
        result = (
            llm_probe(root, probe_all=args.probe_all, timeout_seconds=args.probe_timeout)
            if args.probe or args.probe_all
            else llm_status()
        )
        if getattr(args, "format", "json") == "human":
            from aiwiki.cli.llm_check_render import render_llm_check_human

            text_output = render_llm_check_human(result)
    elif args.handler_command == "watch":
        result = watch_inbox(
            root,
            interval_seconds=args.interval,
            compile_limit=args.compile_limit,
            process_initial=not args.skip_initial,
            max_cycles=args.max_cycles,
        )
    else:
        raise ValueError(f"Unsupported command: {args.handler_command}")
    return _out(result, text_output)


_VAULT_ADMIN_HANDLERS = {
    "new-vault": _handle_vault_admin,
    "sync-product-shell": _handle_vault_admin,
}

_DROP_HANDLERS = {
    "drop-url": _handle_drop,
    "drop-pdf": _handle_drop,
    "drop-image": _handle_drop,
    "drop-repo": _handle_drop,
    "drop-note": _handle_drop,
    "drop-plan": _handle_drop,
}

_COMPILE_PROTOCOL_HANDLERS = {
    "compile": _handle_compile_family,
    "file-back": _handle_compile_family,
}

_LIVE_SURFACE_HANDLERS = {
    "today": _handle_live_surface,
    "review-queue": _handle_live_surface,
    "trace": _handle_live_surface,
    "metrics": _handle_live_surface,
    "shell-status": _handle_live_surface,
}

_ASK_HANDLERS = {
    "ask": _handle_ask_family,
    "run-ask": _handle_ask_family,
    "run-ask-submit": _handle_ask_family,
    "run-ask-resume": _handle_ask_family,
}

_ALCHEMY_HANDLERS = {
    "alchemy-start": _handle_alchemy,
    "alchemy-distill": _handle_alchemy,
    "alchemy-finalize": _handle_alchemy,
    "alchemy-promote": _handle_alchemy,
    "alchemy-revert": _handle_alchemy,
    "alchemy-demote": _handle_alchemy,
}

_REVIEW_LIFECYCLE_HANDLERS = {
    "review-page": _handle_review_lifecycle,
}

_RUNTIME_WORKFLOW_HANDLERS = {
    "lint": _handle_runtime_workflows,
    "nightly": _handle_runtime_workflows,
    "run-nightly": _handle_runtime_workflows,
}

_OPS_HANDLERS = {
    "llm-check": _handle_ops,
    "watch": _handle_ops,
}

_HANDLERS = {
    **_VAULT_ADMIN_HANDLERS,
    **_DROP_HANDLERS,
    **_COMPILE_PROTOCOL_HANDLERS,
    **_LIVE_SURFACE_HANDLERS,
    **_ASK_HANDLERS,
    **_ALCHEMY_HANDLERS,
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
