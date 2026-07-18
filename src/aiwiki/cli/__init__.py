"""Command line interface for aiwiki.

Backwards-compatible facade for the cli subpackage.
"""

from __future__ import annotations

import sys as _sys
import types as _types

from . import dispatch as _dispatch
from . import parsers as _parsers


def _export_module_symbols(_module: object) -> None:
    for _name, _value in vars(_module).items():
        if _name.startswith("__"):
            continue
        globals()[_name] = _value


_export_module_symbols(_parsers)
_export_module_symbols(_dispatch)


class _CliModule(_types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if hasattr(_dispatch, name):
            setattr(_dispatch, name, value)
        if hasattr(_parsers, name):
            setattr(_parsers, name, value)


_sys.modules[__name__].__class__ = _CliModule

__all__ = [
    _name
    for _name in globals()
    if not _name.startswith("__")
    and _name not in {"_types", "_sys", "_dispatch", "_parsers", "_export_module_symbols", "_CliModule"}
]
