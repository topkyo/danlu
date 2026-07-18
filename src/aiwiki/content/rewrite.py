"""Concept-rewrite proposal state helpers.

Extracted from the legacy app_state hub. Owned by the content layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..memory.paths import concept_rewrite_state_path
from ..state.io import load_json_document
from ..utils.io import atomic_write_text, runtime_write_operation


def default_concept_rewrite_state() -> dict[str, Any]:
    return {"version": 1, "proposals": []}


def load_concept_rewrite_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_rewrite_state_path(root))
    if not isinstance(document, dict):
        return default_concept_rewrite_state()
    proposals = document.get("proposals")
    if not isinstance(proposals, list):
        return default_concept_rewrite_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "proposals": [proposal for proposal in proposals if isinstance(proposal, dict)],
    }


@runtime_write_operation
def save_concept_rewrite_state(root: Path, document: dict[str, Any]) -> None:
    atomic_write_text(concept_rewrite_state_path(root), json.dumps(document, indent=2, sort_keys=True) + "\n")
