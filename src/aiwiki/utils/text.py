from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import html
import http.client
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

STOP_WORDS = {
    "about",
    "after",
    "against",
    "and",
    "article",
    "articles",
    "batch",
    "brief",
    "browser",
    # Round 2 P4-9 additions: empirically observed noise tokens from dogfood
    # receipt v0 §F6 (28 dogfood concepts had 11 stop-word-tier slugs).
    "capture",
    "captured",
    "compare",
    "compiled",
    "fast",
    "file",
    "files",
    "figure",
    "five",
    "for",
    "four",
    "from",
    "full",
    "image",
    "images",
    "into",
    "kind",
    "lite",
    "mode",
    "must",
    "note",
    "notes",
    "one",
    "page",
    "pages",
    "question",
    "report",
    "rendered",
    "receipt",
    "receipts",
    "session",
    "slow",
    "smoke",
    "sota",
    "source",
    "sources",
    "slides",
    "sub",
    "task",
    "that",
    "the",
    "their",
    "there",
    "these",
    "three",
    "this",
    "two",
    "with",
    "wiki",
}


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "item"


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".rst"}:
        return "text"
    if suffix in {".json", ".yaml", ".yml", ".csv", ".tsv", ".toml"}:
        return "data"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if not suffix:
        return "file"
    return suffix.lstrip(".")


_BATCH_TAG_PATTERN = re.compile(r"^round\d+$")
_TIMESTAMP_FRAGMENT_PATTERN = re.compile(r"^\d{2,}t\d{2,}$")
_QUARTER_TAG_PATTERN = re.compile(r"^(?:[12]\d{3}q[1-4]|q[1-4][12]\d{3})$")


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [
        token
        for token in tokens
        if len(token) > 2
        and not token.isdigit()
        and token not in STOP_WORDS
        and not _BATCH_TAG_PATTERN.match(token)
        and not _TIMESTAMP_FRAGMENT_PATTERN.match(token)
        and not _QUARTER_TAG_PATTERN.match(token)
    ]
