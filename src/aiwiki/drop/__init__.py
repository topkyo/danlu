"""Direct raw-material entry points for aiwiki.

This package replaces the former monolithic ``aiwiki/drop.py`` module. Public
drop handlers are split by ingestion kind (url / pdf / image / repo / note)
with shared helpers in ``common``. The package re-exports the public surface so
existing ``from aiwiki.drop import drop_url`` / ``drop_pdf`` / ... call sites
and ``monkeypatch.setattr("aiwiki.drop.utc_now"|"aiwiki.drop._fetch_url", ...)``
sites continue to work unchanged.
"""

from __future__ import annotations

# ``utc_now`` is re-exported from ``utils.time`` so that
# ``monkeypatch.setattr("aiwiki.drop.utc_now", ...)`` continues to replace the
# attribute read by every handler's internal helpers
# (``_append_raw_added_history`` / ``_append_manifest_entry`` /
# ``_materialize_url`` / ``_materialize_repo``) via ``_drop_pkg.utc_now()``.
from ..utils.time import utc_now

# Shared helpers (and the SensitiveContentError sentinel) live in ``common``.
from .common import SensitiveContentError

# Handler modules. Imported after ``common`` so their ``import aiwiki.drop as
# _drop_pkg`` alias (used for monkeypatch-compat) binds to a package object
# that already has the ``common`` symbols attached.
from .image import drop_image
from .note import drop_note
from .pdf import drop_pdf
from .repo import drop_repo
from .url import _fetch_url, drop_url

__all__ = [
    "SensitiveContentError",
    "_fetch_url",
    "drop_image",
    "drop_note",
    "drop_pdf",
    "drop_repo",
    "drop_url",
    "utc_now",
]
