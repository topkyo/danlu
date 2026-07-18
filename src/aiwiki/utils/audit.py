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


class AuditMirrorError(RuntimeError):
    """Audit mirror append failed; primary file successfully truncated back to pre-call size."""


class AuditMirrorRollbackError(RuntimeError):
    """Audit mirror append failed AND primary truncate also failed; primary in inconsistent state."""
