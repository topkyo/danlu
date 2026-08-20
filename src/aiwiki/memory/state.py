"""Machine-memory top-level state loader.

Extracted from the legacy app_state hub. Owned by the memory layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state.io import load_json_document
from ..state.paths import machine_memory_state_path


def load_machine_memory(root: Path) -> dict[str, Any]:
    memory = load_json_document(machine_memory_state_path(root))
    return memory if isinstance(memory, dict) else {}
