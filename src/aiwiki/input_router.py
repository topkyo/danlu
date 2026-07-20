from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class UniversalRoute(str, Enum):
    URL = "url"
    PDF = "pdf"
    IMAGE = "image"
    REPO = "repo"
    NOTE = "note"
    ASK = "ask"


@dataclass(frozen=True)
class RouteDecision:
    route: UniversalRoute
    payload: str
    reason: str


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
NOTE_TEXT_SUFFIXES = (".md", ".markdown", ".txt")

# github.com/<owner>/<repo>/blob|tree/<ref>/<path...>
_GITHUB_BLOB_TREE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:blob|tree)/"
    r"(?P<ref>[^/]+)/(?P<path>.+)$",
    re.IGNORECASE,
)
# github.com/<owner>/<repo> optional trailing slash / .git — no further path
_GITHUB_REPO_ROOT_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def rewrite_github_raw_url(url: str) -> str | None:
    """Rewrite github.com blob/tree/repo-root URLs to raw.githubusercontent.com.

    Returns None when the URL is not a rewriteable GitHub content URL.
    Deterministic counterpart to the LLM planner few-shot rules.
    """
    text = (url or "").strip()
    match = _GITHUB_BLOB_TREE_RE.match(text)
    if match:
        owner = match.group("owner")
        repo = match.group("repo")
        ref = match.group("ref")
        path = match.group("path").rstrip("/")
        # tree/ directory → prefer README.md under that path
        if "/tree/" in text.lower() and "." not in path.rsplit("/", 1)[-1]:
            path = f"{path}/README.md" if path else "README.md"
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    root = _GITHUB_REPO_ROOT_RE.match(text)
    if root:
        owner = root.group("owner")
        repo = root.group("repo")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
    return None


def is_obsidian_open_link(value: str) -> bool:
    return value.strip().lower().startswith("obsidian://open")


def classify_universal_input(value: str) -> RouteDecision:
    """Deterministic classifier. No IO, no LLM, no subprocess."""
    payload = value.strip()
    if not payload:
        raise ValueError("empty input")

    lower_payload = payload.lower()

    if is_obsidian_open_link(payload):
        raise ValueError("obsidian open links are navigation targets, not ask inputs")

    if lower_payload.startswith(("http://", "https://")):
        rewritten = rewrite_github_raw_url(payload)
        if rewritten is not None:
            return RouteDecision(UniversalRoute.URL, rewritten, "github-raw-rewrite")
        url_path = urlparse(payload).path.lower()
        if url_path.endswith(".pdf"):
            return RouteDecision(UniversalRoute.PDF, payload, "pdf-suffix-on-url")
        if url_path.endswith(IMAGE_SUFFIXES):
            return RouteDecision(UniversalRoute.IMAGE, payload, "image-suffix-on-url")
        return RouteDecision(UniversalRoute.URL, payload, "url-scheme")

    if lower_payload.endswith(".pdf"):
        return RouteDecision(UniversalRoute.PDF, payload, "pdf-suffix")

    if lower_payload.endswith(IMAGE_SUFFIXES):
        return RouteDecision(UniversalRoute.IMAGE, payload, "image-suffix")

    if lower_payload.startswith("git@"):
        return RouteDecision(UniversalRoute.REPO, payload, "git-ssh-shorthand")

    if lower_payload.startswith("ssh://"):
        return RouteDecision(UniversalRoute.REPO, payload, "ssh-scheme")

    if lower_payload.endswith(".git"):
        return RouteDecision(UniversalRoute.REPO, payload, "git-suffix")

    if lower_payload.startswith("note:"):
        note_payload = payload[len("note:") :].strip()
        if not note_payload:
            raise ValueError("empty note payload")
        return RouteDecision(UniversalRoute.NOTE, note_payload, "note-prefix")

    if lower_payload.startswith("ask:"):
        return RouteDecision(UniversalRoute.ASK, payload[len("ask:") :].strip(), "ask-prefix")

    if "?" not in payload and lower_payload.endswith(NOTE_TEXT_SUFFIXES):
        return RouteDecision(UniversalRoute.NOTE, payload, "note-text-suffix")

    if "\n" in payload:
        return RouteDecision(UniversalRoute.NOTE, payload, "multiline-text")

    if "?" in payload or "？" in payload:
        return RouteDecision(UniversalRoute.ASK, payload, "contains-question-mark")

    return RouteDecision(UniversalRoute.ASK, payload, "default-ambiguous-text")
