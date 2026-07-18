"""Top-level orchestration extracted from aiwiki.app.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to
`aiwiki.compile.*` rather than added here. See AGENTS.md migration policy.
"""

from __future__ import annotations

from .compile import CompileContext, start_compile_context

_CompileContext = CompileContext
_start_compile_context = start_compile_context


# EP-018B: execution entry points live under ``aiwiki.execution.*``.
# Import them from owner modules directly; this module no longer lazy-forwards.
# Ranking helpers migrated to ``aiwiki.compile.ranking``; machine-memory
# builder is owned by ``aiwiki.memory.builder``.
