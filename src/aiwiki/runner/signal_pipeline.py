"""Signal-to-planner deterministic pipeline helpers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from aiwiki import autonomy_policy
from aiwiki.planner.log_writer import write_planner_log
from aiwiki.runner.alchemy import run_alchemy_auto

_HEAVY_SEMANTIC_PRIMITIVES = ["review", "distill", "propose"]


def run_signal_pipeline(
    root: Path,
    *,
    apply_light: bool | None = None,
    apply_heavy_semantic: bool | None = None,
) -> dict[str, Any]:
    """Replay signals, write planner decisions, and build semantic phase feedback.

    Light maintenance can be applied unattended. Under the agentic default,
    heavy non-core semantic work also applies when the policy allows it; callers
    can still force preview by passing ``apply_heavy_semantic=False``.
    """

    collect_signals = import_module("aiwiki.signals.collector").collect_signals
    flags = autonomy_policy.nightly_autonomy_flags(root)
    resolved_apply_light = flags["auto_apply_light"] if apply_light is None else apply_light
    resolved_apply_heavy = flags.get("auto_apply_heavy_semantic", False) if apply_heavy_semantic is None else apply_heavy_semantic
    signals = collect_signals(root)
    planner = write_planner_log(root, mode="execute")
    if int(signals.get("new_count") or 0) <= 0 and int(planner.get("new_count") or 0) <= 0:
        heavy_preview = run_alchemy_auto(
            root,
            apply=False,
            lanes=["heavy"],
            primitives=_HEAVY_SEMANTIC_PRIMITIVES,
            note="signal pipeline heavy semantic preview",
            allow_current_writer_lock=True,
        )
        return {
            "status": "noop",
            "signals_replay": signals,
            "planner_log_replay": planner,
            "heavy_semantic": _semantic_phase_summary(heavy_preview, applied=False),
            "alchemy_auto": {
                "status": "skipped",
                "reason": "no_new_signal_or_planner_decision",
            },
        }

    alchemy_auto = run_alchemy_auto(
        root,
        apply=bool(resolved_apply_light),
        lanes=["light"],
        primitives=["compile", "lint"],
        note="signal pipeline light lane",
        allow_current_writer_lock=True,
    )
    heavy_semantic = run_alchemy_auto(
        root,
        apply=bool(resolved_apply_heavy),
        lanes=["heavy"],
        primitives=_HEAVY_SEMANTIC_PRIMITIVES,
        note="signal pipeline heavy semantic phase",
        allow_current_writer_lock=True,
    )
    return {
        "status": "applied"
        if (resolved_apply_light and alchemy_auto.get("status") == "applied")
        or (resolved_apply_heavy and heavy_semantic.get("status") == "applied")
        else "preview",
        "signals_replay": signals,
        "planner_log_replay": planner,
        "alchemy_auto": alchemy_auto,
        "heavy_semantic": _semantic_phase_summary(heavy_semantic, applied=bool(resolved_apply_heavy)),
        "light_apply_enabled": bool(resolved_apply_light),
        "heavy_semantic_apply_enabled": bool(resolved_apply_heavy),
    }


def _semantic_phase_summary(result: dict[str, Any], *, applied: bool) -> dict[str, Any]:
    lane_results = [item for item in result.get("lane_results", []) if isinstance(item, dict)]
    contracts: list[dict[str, Any]] = []
    for lane in lane_results:
        plan = lane.get("plan") if isinstance(lane.get("plan"), dict) else {}
        scope_preview = plan.get("scope_preview") if isinstance(plan.get("scope_preview"), dict) else {}
        for primitive in lane.get("selected_primitives", []):
            primitive_name = str(primitive or "")
            if primitive_name not in _HEAVY_SEMANTIC_PRIMITIVES:
                continue
            contracts.append(
                {
                    "contract_id": f"semantic:{primitive_name}:{str(plan.get('scope') or 'all')}",
                    "primitive": primitive_name,
                    "phase": "heavy",
                    "scope": str(plan.get("scope") or "all"),
                    "input_refs": {
                        "signal_ids": list(scope_preview.get("signal_ids") or []),
                        "trace_ids": list(scope_preview.get("trace_ids") or []),
                        "source_ids": list(scope_preview.get("source_ids") or []),
                        "concept_slugs": list(scope_preview.get("concept_slugs") or []),
                        "elixir_refs": list(scope_preview.get("elixir_refs") or []),
                        "judgment_refs": list(scope_preview.get("judgment_refs") or []),
                    },
                    "model_contract": "explicit_llm_governed_contract_required_for_semantic_content"
                    if applied
                    else "explicit_llm_or_human_contract_required_for_semantic_content",
                    "human_required": not applied,
                    "target_surfaces": ["review_queue", "elixir_candidate_plane", "l3_proposal_plane"],
                    "receipt_required": True,
                    "rollback_policy": "receipt_or_newer_proposal; core prompt/policy/schema apply remains human-gated",
                }
            )
    return {
        "status": str(result.get("status") or ""),
        "mode": str(result.get("mode") or ""),
        "applied": applied and str(result.get("status") or "") == "applied",
        "side_effects_allowed": bool(result.get("side_effects_allowed", False)),
        "selected_contract_count": len(contracts),
        "semantic_contracts": contracts,
        "source": result,
    }


__all__ = ["run_signal_pipeline"]
