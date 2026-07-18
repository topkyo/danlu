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


def html_safe_json_literal(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
