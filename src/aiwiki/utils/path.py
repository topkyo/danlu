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


def relative_path(root: Path, path: Path) -> str:
    """Return a vault-relative POSIX path.

    If ``.aiwiki/state`` is a symlink to a directory outside the vault (dogfood
    anti-iCloud-fork layout), rewrite resolved state paths back to
    ``.aiwiki/state/...`` so callers keep a stable in-vault logical path.
    """
    root_resolved = root.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    try:
        return path_resolved.relative_to(root_resolved).as_posix()
    except ValueError:
        state_link = root_resolved / ".aiwiki" / "state"
        try:
            state_target = state_link.resolve(strict=False)
            under_state = path_resolved.relative_to(state_target)
        except (OSError, ValueError):
            raise
        return (Path(".aiwiki") / "state" / under_state).as_posix()


def next_identifier(existing_ids: set[str], seed: str) -> str:
    candidate = seed
    index = 2
    while candidate in existing_ids:
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def next_available_stem(directory: Path, seed: str, suffix: str = ".md") -> str:
    candidate = seed
    index = 2
    while (directory / f"{candidate}{suffix}").exists():
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def normalize_workspace_path(value: str) -> str:
    normalized = value.strip().strip("'\"`")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip(".,;:")
