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


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def question_signature(question: str) -> str:
    normalized = " ".join(question.lower().split())
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compiled_source_sha(markdown: str) -> str:
    from .markdown import parse_frontmatter

    if not markdown:
        return ""
    frontmatter = parse_frontmatter(markdown)
    sha = frontmatter.get("source_sha256")
    if isinstance(sha, str) and sha:
        return sha
    match = re.search(r"(?m)^- SHA256: `([^`]+)`", markdown)
    if match:
        return match.group(1)
    return ""
