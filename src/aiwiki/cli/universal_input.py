"""Universal-input rewrite for the aiwiki CLI.

Encapsulates the rules that translate top-level `drop <payload>` invocations
into typed subcommands (`drop url|pdf|image|repo|markdown`) or `advanced run-ask`,
based on payload classification. See EP-001/EP-003a/EP-003c history for the
fail-loud rejection path for ambiguous local-path-like payloads.
"""

from __future__ import annotations

import os
import re
import sys

from ..input_router import UniversalRoute, classify_universal_input, rewrite_github_raw_url

_DROP_TYPED_SUBCOMMANDS = {"url", "pdf", "image", "repo", "markdown", "plan"}
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _llm_planner_enabled() -> bool:
    """Default ON. Set AIWIKI_LLM_PLANNER=0 to disable and use the deterministic classifier."""
    return os.environ.get("AIWIKI_LLM_PLANNER", "1").strip().lower() not in {"0", "false", "no", "off"}


def _looks_like_local_path(value: str) -> bool:
    """Detect drop payloads that resemble local file paths to avoid silent ASK fallthrough.

    Heuristic only; no LLM, deterministic. Triggers on:
    - explicit relative/absolute prefixes (./, ../, /, ~/)
    - POSIX-style nested path with '/' (e.g. notes/file.docx) when not CJK Q&A
    - Windows-style path with '\\' or drive letter (e.g. C:\\x, notes\\x)
    - the payload pointing at an existing file or directory on disk
    Excludes URL schemes, '?' questions, and CJK text that only has '/' as
    typography (e.g. ``A/B测试怎么做``) unless the path exists on disk.
    """
    if not value or "?" in value or "？" in value:
        return False
    if value.startswith(("http://", "https://", "git@", "ssh://", "ask:", "note:")):
        return False
    # strong path signals
    if value.startswith(("./", "../", "/", "~/")):
        return True
    if "\\" in value:
        return True
    if len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in ("\\", "/"):
        return True
    # Existing file/dir (bare names like ``reponame`` that are real directories)
    try:
        if os.path.isfile(value) or os.path.isdir(value):
            return True
    except (OSError, ValueError):
        pass
    # POSIX nested path: must contain '/' and have no whitespace.
    # CJK natural-language with an embedded slash is not a path unless it exists
    # (existence already handled above).
    if "/" in value and not any(ch.isspace() for ch in value):
        if _CJK_RE.search(value):
            return False
        return True
    return False


def _reject_ambiguous_path_ask(payload: str) -> None:
    print(
        f"error: drop payload looks like a file path but matches no known type: {payload!r}\n"
        "hint: use 'drop markdown <path>' for markdown/text files, "
        "'drop repo <dir>' for directories, "
        "or prefix with 'ask:' to force a question.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _rewrite_universal_drop_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        rewritten = list(sys.argv[1:])
    else:
        rewritten = list(argv)

    drop_index = _top_level_drop_index(rewritten)
    if drop_index is None:
        return argv
    if len(rewritten) <= drop_index + 1:
        return rewritten

    payload = rewritten[drop_index + 1]
    if payload == "note":
        print("error: `drop note` is not a command; use `drop markdown`.", file=sys.stderr)
        raise SystemExit(2)
    if payload in _DROP_TYPED_SUBCOMMANDS or payload in {"question", "-h", "--help"}:
        return rewritten
    if "-h" in rewritten[drop_index + 2 :] or "--help" in rewritten[drop_index + 2 :]:
        return rewritten

    if payload == "-":
        payload = sys.stdin.read().strip()
        if not payload:
            print("error: empty stdin payload", file=sys.stderr)
            raise SystemExit(2)

    rest = rewritten[drop_index + 2 :]

    # Existing local directory → typed drop repo (before planner / ASK fail-loud).
    try:
        if os.path.isdir(payload):
            rewritten[drop_index:] = ["drop", "repo", payload, *rest]
            return rewritten
        if os.path.isfile(payload):
            decision = classify_universal_input(payload)
            if decision.route != UniversalRoute.ASK:
                routed_subcommand = {
                    UniversalRoute.URL: "url",
                    UniversalRoute.PDF: "pdf",
                    UniversalRoute.IMAGE: "image",
                    UniversalRoute.REPO: "repo",
                    UniversalRoute.NOTE: "markdown",
                }[decision.route]
                rewritten[drop_index:] = ["drop", routed_subcommand, decision.payload, *rest]
                return rewritten
    except (OSError, ValueError):
        pass

    # EP-001/EP-003: path-like payloads that classify as ASK must fail loud —
    # but not for existing dirs (handled above) or CJK Q&A with '/'.
    if _looks_like_local_path(payload):
        decision = classify_universal_input(payload)
        if decision.route == UniversalRoute.ASK:
            _reject_ambiguous_path_ask(payload)

    if _llm_planner_enabled():
        # Default ON: route through the LLM planner. The planner decides
        # fetch_raw / fetch_page / read_local_repo / read_local_note / ask,
        # and the deterministic executor runs it. On planner failure the
        # dispatch layer falls back to classify_universal_input.
        rewritten[drop_index:] = ["drop", "plan", payload, *rest]
        return rewritten

    decision = classify_universal_input(payload)
    routed_payload = decision.payload
    if decision.route == UniversalRoute.ASK:
        if _looks_like_local_path(routed_payload):
            _reject_ambiguous_path_ask(routed_payload)
        # Questions require LLM run-ask — no deterministic empty-shell CLI.
        rewritten[drop_index:] = ["advanced", "run-ask", routed_payload, *rest]
    else:
        if decision.route == UniversalRoute.URL:
            routed_payload = rewrite_github_raw_url(routed_payload) or routed_payload
        routed_subcommand = {
            UniversalRoute.URL: "url",
            UniversalRoute.PDF: "pdf",
            UniversalRoute.IMAGE: "image",
            UniversalRoute.REPO: "repo",
            UniversalRoute.NOTE: "markdown",
        }[decision.route]
        rewritten[drop_index:] = ["drop", routed_subcommand, routed_payload, *rest]
    return rewritten


def _top_level_drop_index(argv: list[str]) -> int | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "drop":
            return index
        if token == "--root":
            index += 2
            continue
        if token.startswith("--root="):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return None
    return None
