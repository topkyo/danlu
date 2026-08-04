from __future__ import annotations


class AuditMirrorError(RuntimeError):
    """Audit mirror append failed; primary file successfully truncated back to pre-call size."""


class AuditMirrorRollbackError(RuntimeError):
    """Audit mirror append failed AND primary truncate also failed; primary in inconsistent state."""
