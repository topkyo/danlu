"""Compile pipeline orchestration owner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..utils.io import runtime_write_operation
from .content_step import compile_content_phase
from .context import CompileContext, start_compile_context
from .output_step import compile_output_phase
from .persist_step import finalize_compile_phase
from .runtime_step import compile_runtime_phase

CompileStep = Callable[[CompileContext], None]


@runtime_write_operation
def compile_wiki(root: Path, *, force_cache_rebuild: bool = False) -> dict[str, Any]:
    context = start_compile_context(root)
    for step in _compile_steps():
        step(context)
    return finalize_compile_phase(context, force_cache_rebuild=force_cache_rebuild)


def _compile_steps() -> tuple[CompileStep, ...]:
    return (
        compile_content_phase,
        compile_runtime_phase,
        compile_output_phase,
    )


__all__ = ["compile_wiki"]
