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
    return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()


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
