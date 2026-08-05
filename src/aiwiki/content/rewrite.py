"""Concept-rewrite proposal state helpers.

Extracted from the legacy app_state hub. Owned by the content layer.
State IO lives in ``aiwiki.corpus.link_state`` (shared with memory).
"""

from __future__ import annotations

from ..corpus.link_state import (
    default_concept_rewrite_state as default_concept_rewrite_state,
)
from ..corpus.link_state import (
    load_concept_rewrite_state as load_concept_rewrite_state,
)
from ..corpus.link_state import (
    save_concept_rewrite_state as save_concept_rewrite_state,
)

__all__ = [
    "default_concept_rewrite_state",
    "load_concept_rewrite_state",
    "save_concept_rewrite_state",
]
