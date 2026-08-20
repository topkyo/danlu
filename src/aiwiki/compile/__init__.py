"""Compile owner package.

`compile_wiki` is exposed lazily via ``__getattr__`` so that importing leaf
modules (e.g. ``compile.build``, ``compile.state``) does not eagerly pull in
``compile.pipeline`` -> ``content_step`` -> ``app_lifecycle`` and create a
circular import. Direct callers should import ``compile_wiki`` from
``compile.pipeline`` explicitly.
"""

from .context import CompileContext, start_compile_context

__all__ = ["CompileContext", "compile_wiki", "start_compile_context"]


def __getattr__(name: str):
    if name == "compile_wiki":
        from .pipeline import compile_wiki as _compile_wiki

        return _compile_wiki
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

