"""Module execution entry point for ``python -m aiwiki.cli``."""

from __future__ import annotations

from .dispatch import main

if __name__ == "__main__":
    raise SystemExit(main())
