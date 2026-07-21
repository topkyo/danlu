"""Compile phase: scrub dead output/reports provenance on curated pages."""

from __future__ import annotations

from ..lifecycle.provenance_scrub import scrub_curated_pages
from .context import CompileContext


def compile_provenance_scrub_phase(context: CompileContext) -> None:
    result = scrub_curated_pages(context.root)
    context.provenance_degraded = int(result.get("degraded") or 0)
    context.provenance_broken = int(result.get("broken") or 0)
    context.provenance_dead_report_refs_stripped = int(result.get("dead_report_refs_stripped") or 0)
    context.changed_pages += len(result.get("changed_paths") or [])


__all__ = ["compile_provenance_scrub_phase"]
