"""Shared runner interfaces."""

from __future__ import annotations

from typing import Protocol

from aiwiki.llm import CompletionResult


class SupportsComplete(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult: ...
