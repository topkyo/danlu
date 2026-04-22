"""Execution owner subpackage (炼丹炉 EP-018B target).

This package is a placeholder introduced by EP-018A. The real migration of
execution-layer functions (ask / file-back / concept rewrite / lifecycle /
machine-memory action / archive / review / batch / runtime surfaces) from
``aiwiki.app_compile`` into this subpackage happens in EP-018B, group by
group.

Until then, this module stays empty and ``aiwiki.app_compile`` retains
owner semantics for every execution function. The PEP 562 ``__getattr__``
compat seam at the bottom of ``aiwiki.app_compile`` self-resolves each
execution name back to ``app_compile`` itself — this lets EP-018B flip
``_LAZY_OWNERS`` entries from ``"aiwiki.app_compile"`` to the new owner
module one group at a time, without breaking any caller.
"""

from __future__ import annotations

__all__: list[str] = []
