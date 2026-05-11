from __future__ import annotations

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


def classify_universal_input(value: str) -> RouteDecision:
    """Deterministic classifier. No IO, no LLM, no subprocess."""
    payload = value.strip()
    if not payload:
        raise ValueError("empty input")

    lower_payload = payload.lower()

    if lower_payload.startswith(("http://", "https://")):
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

    if "?" in payload:
        return RouteDecision(UniversalRoute.ASK, payload, "contains-question-mark")

    return RouteDecision(UniversalRoute.ASK, payload, "default-ambiguous-text")
