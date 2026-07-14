"""Pure helpers for drop ingestion."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_FILENAME_TITLE_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".md",
    ".markdown",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
}


def timestamped_stem(label: str) -> str:
    """Convert a user-facing title or filename into a stable safe file stem."""
    filename_label = re.sub(r"[\\/]+", " ", label.strip())
    suffix = Path(filename_label).suffix.lower()
    if suffix in _FILENAME_TITLE_SUFFIXES:
        filename_label = filename_label[: -len(suffix)]
    result = re.sub(r"[^\w\u3400-\u9fff]+", "-", filename_label.lower(), flags=re.UNICODE).strip("-_.")[:64]
    result = result.strip("-_.")
    if result and result != "item":
        return result
    return f"doc-{hashlib.sha256(label.encode()).hexdigest()[:12]}"
