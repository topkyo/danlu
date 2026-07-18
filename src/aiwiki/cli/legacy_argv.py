"""Rewrite deprecated top-level operator argv into `advanced ...`.

Primary surface stays: drop / today / advanced.
Operator commands are registered only under `advanced`. Old top-level
invocations are rewritten with a stderr deprecation warning so dogfood
scripts keep working without dual argparse registration.
"""

from __future__ import annotations

import sys

PRIMARY_SURFACE_COMMANDS = frozenset({"drop", "today", "advanced"})

# Keep in sync with operator commands registered under `advanced` that still
# accept legacy top-level argv rewrite (not W4-cut surfaces).
LEGACY_TOP_LEVEL_COMMANDS = frozenset({
    "alchemy-demote",
    "alchemy-distill",
    "alchemy-finalize",
    "alchemy-promote",
    "alchemy-revert",
    "alchemy-start",
    "ask",
    "compile",
    "drop-image",
    "drop-note",
    "drop-pdf",
    "drop-repo",
    "drop-url",
    "file-back",
    "layout",
    "lint",
    "llm-check",
    "metrics",
    "new-vault",
    "nightly",
    "review-page",
    "review-queue",
    "run-ask",
    "run-ask-resume",
    "run-ask-submit",
    "run-nightly",
    "shell-status",
    "sync-product-shell",
    "trace",
    "watch",
})


_PRIMARY_DROP_REPLACEMENTS = {
    "drop-url": ("drop", "url"),
    "drop-pdf": ("drop", "pdf"),
    "drop-image": ("drop", "image"),
    "drop-repo": ("drop", "repo"),
    "drop-note": ("drop", "markdown"),
}


def rewrite_legacy_top_level_argv(
    argv: list[str] | None,
    *,
    emit_warning: bool = True,
) -> list[str] | None:
    """Rewrite deprecated top-level operator argv onto the primary/advanced surface.

    - ``drop-*`` legacy entries become primary ``drop <kind>``
    - other operator entries are prefixed with ``advanced``

    Flag pairs such as ``--root PATH`` / ``--model-fallback X`` are preserved
    in front of the rewritten command token.
    """

    if argv is None:
        rewritten = list(sys.argv[1:])
    else:
        rewritten = list(argv)
    index = 0
    while index < len(rewritten):
        token = rewritten[index]
        if token in {"-h", "--help"}:
            return rewritten
        if token.startswith("-"):
            if token in {"--root", "--model-fallback"} and index + 1 < len(rewritten):
                index += 2
                continue
            index += 1
            continue
        break
    if index >= len(rewritten):
        return rewritten
    command = rewritten[index]
    if command in PRIMARY_SURFACE_COMMANDS or command not in LEGACY_TOP_LEVEL_COMMANDS:
        return rewritten
    prefix = rewritten[:index]
    rest = rewritten[index + 1 :]
    if command in _PRIMARY_DROP_REPLACEMENTS:
        drop_cmd = list(_PRIMARY_DROP_REPLACEMENTS[command])
        replacement = " ".join(drop_cmd)
        if emit_warning:
            print(
                f"[deprecated] `aiwiki {command}` is deprecated; use `aiwiki {replacement}` instead.",
                file=sys.stderr,
            )
        return [*prefix, *drop_cmd, *rest]
    if emit_warning:
        print(
            f"[deprecated] `aiwiki {command}` is a legacy top-level entry; "
            f"use `aiwiki advanced {command}` instead.",
            file=sys.stderr,
        )
    return [*prefix, "advanced", command, *rest]
