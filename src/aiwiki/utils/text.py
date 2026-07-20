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
    # CJK function-word bigrams from Lucene-style overlapping segmentation.
    # Without these, term_index/search drown in 这个/我们/这是 noise.
    "这是",
    "是一",
    "一个",
    "我们",
    "这个",
    "这些",
    "那些",
    "没有",
    "可以",
    "因为",
    "所以",
    "但是",
    "如果",
    "已经",
    "还有",
    "不是",
    "什么",
    "怎么",
    "自己",
    "他们",
    "以及",
    "进行",
    "通过",
    "对于",
    "一种",
    "一些",
    "不会",
    "不能",
    "时候",
    "之后",
    "之前",
    "然后",
    "或者",
    "而且",
    "不过",
    "只是",
    "就是",
    "还是",
    "其实",
    "当然",
    "比如",
    "例如",
    "等等",
    "之中",
    "之间",
    "以上",
    "以下",
    "其中",
    "其他",
    "其它",
}


AUTO_ASK_PATH_MARKER = "本次投喂材料路径："
AUTO_ASK_QUESTION_MARKER = "用户问题："
AUTO_ASK_INLINE_PATH_MARKER = "材料路径供系统路由使用："
AUTO_ASK_INLINE_HINT_PREFIX = "请优先使用本次投喂材料回答"


def human_query_title(question: str) -> str:
    """Return the user-facing title for an ask artifact.

    Product Shell auto-ask prompts include repo paths as routing hints.  Those
    hints are useful to the runtime but should not leak into report headings,
    Obsidian titles, or output filenames.
    """

    text = str(question or "").strip()
    if not text:
        return "未命名问题"
    marker_index = text.rfind(AUTO_ASK_QUESTION_MARKER)
    if marker_index >= 0:
        candidate = text[marker_index + len(AUTO_ASK_QUESTION_MARKER) :].strip()
        if candidate:
            text = candidate
    visible_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if AUTO_ASK_INLINE_PATH_MARKER in stripped:
            before_marker = stripped.split(AUTO_ASK_INLINE_PATH_MARKER, 1)[0].strip()
            before_marker = before_marker.removesuffix("；").removesuffix(";").strip()
            if before_marker and before_marker != AUTO_ASK_INLINE_HINT_PREFIX:
                visible_lines.append(before_marker)
            continue
        if stripped == AUTO_ASK_INLINE_HINT_PREFIX or stripped.startswith(f"{AUTO_ASK_INLINE_HINT_PREFIX}；"):
            continue
        visible_lines.append(line)
    text = "\n".join(visible_lines).strip()
    text = re.sub(r"(?m)^\s*-\s*(?:raw|wiki|output|\.aiwiki)/\S+\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text or "未命名问题"


def slugify(value: str) -> str:
    """Slug for paths/ids: keep Latin alnum and CJK; collapse other runs to '-' .

    Pure-CJK labels must not collapse to the shared fallback `item` (that merged
    distinct Chinese concepts into one slug). Latin behavior unchanged.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
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


def _is_meaningful_token(token: str) -> bool:
    # CJK bigrams/unigrams are pre-segmented to length 1-2; keep them.
    # Latin tokens: keep 3+ char non-numeric runs.
    if re.search(r"[\u4e00-\u9fff]", token):
        return len(token) >= 2
    return len(token) > 2 and not token.isdigit()


def _cjk_ngrams(run: str) -> list[str]:
    # Dependency-free CJK segmentation via overlapping bigrams (Lucene
    # CJKAnalyzer style). Chinese has no word spaces, so a whole run collapses
    # into one unmatchable token; bigrams give matchable retrieval units
    # without a dictionary segmenter (jieba) that would violate stdlib-first.
    if len(run) <= 2:
        return [run]
    return [run[index : index + 2] for index in range(len(run) - 1)]


def tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text.lower())
    tokens: list[str] = []
    for token in raw_tokens:
        if re.search(r"[\u4e00-\u9fff]", token):
            tokens.extend(_cjk_ngrams(token))
        else:
            tokens.append(token)
    return [
        token
        for token in tokens
        if _is_meaningful_token(token)
        and token not in STOP_WORDS
        and not _BATCH_TAG_PATTERN.match(token)
        and not _TIMESTAMP_FRAGMENT_PATTERN.match(token)
        and not _QUARTER_TAG_PATTERN.match(token)
    ]
