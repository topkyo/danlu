"""LLM input planner: classify a universal `drop <payload>` into an executable Plan.

The planner is the LLM-side of the plan/execute split: it looks at the raw
payload (URL, local path, question, natural language) and emits a structured
Plan describing what the deterministic executor should do. It does NOT fetch,
write, or touch raw/ -- that is the executor's job, so raw/ stays a faithful
capture layer (provenance preserved, no LLM summarization in the substrate).

On any LLM failure, JSON parse failure, or autonomy-policy block, the caller
falls back to the deterministic classifier `aiwiki.input_router.classify_universal_input`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLMError

_LOGGER = logging.getLogger("aiwiki.planner")

VALID_ACTIONS = ("fetch_raw", "fetch_page", "read_local_repo", "read_local_note", "ask")
MAX_TARGETS = 12


@dataclass
class Plan:
    action: str
    targets: list[str] = field(default_factory=list)
    title: str = ""
    reason: str = ""

    def validate(self) -> None:
        if self.action not in VALID_ACTIONS:
            raise PlannerError(f"invalid action `{self.action}`; expected one of {VALID_ACTIONS}")
        if self.action == "ask":
            # ask uses the original payload as the single target, not LLM-produced URLs
            return
        if not self.targets:
            raise PlannerError(f"action `{self.action}` requires at least one target")
        if len(self.targets) > MAX_TARGETS:
            raise PlannerError(f"too many targets ({len(self.targets)} > {MAX_TARGETS})")
        for target in self.targets:
            if not isinstance(target, str) or not target.strip():
                raise PlannerError("target must be a non-empty string")


class PlannerError(RuntimeError):
    """Raised when the LLM planner cannot produce a valid Plan.

    Callers catch this to fall back to the deterministic classifier. The
    original LLM error (if any) is chained via __cause__.
    """


PLANNER_SYSTEM_PROMPT = """你是炼丹炉 (aiwiki) 的输入路由器。给定用户的投喂输入，输出一个 JSON 对象决定如何处理。

可选 action:
- fetch_raw: 直接 HTTP GET 若干 URL 的原始字节，原样拼进一个 raw note（适合 raw.githubusercontent.com README、脚本等纯文本资源）
- fetch_page: 抓取网页 HTML 并抽取正文（适合普通网页、需要 HTML 渲染的内容）
- read_local_repo: 快照本地 git 仓库路径（输入是本地目录）
- read_local_note: 把本地 markdown/text 文件或内联文本写进 raw note（输入是本地 .md/.txt 文件或多行文本）
- ask: 输入是一个问题或自然语言提问，交给 LLM 回答

判断要点:
- github.com/<owner>/<repo>（无 .git 后缀、无 /archive/ /blob/ /tree/ 子路径）：优先 fetch_raw，targets 用 https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md（以及 README 提到的关键脚本，若可推断）；不要 clone 整个仓库
- github.com/<owner>/<repo>.git 或 git@ 或 ssh://：fetch_page 抓仓库页面（避免本地 clone 大仓库）
- 普通 http(s) 网页（非 github repo 根）：fetch_page
- 本地目录路径：read_local_repo
- 本地 .md/.txt 文件：read_local_note
- 多行文本或 note: 前缀：read_local_note
- 包含问号的自然语言：ask
- 边界或不确定：ask

输出严格 JSON，无任何额外文本、无 markdown 代码围栏:
{"action": "<one of fetch_raw|fetch_page|read_local_repo|read_local_note|ask>", "targets": ["<url or path, ...>"], "title": "<optional short title>", "reason": "<optional one-line reason>"}

ask action 时 targets 放原始输入本身。"""

PLANNER_USER_TEMPLATE = "输入: {payload}\n\n输出 JSON:"

# Few-shot examples anchored in the prompt to steer the LLM toward the
# github-raw pattern (the original motivating case). Kept compact to limit
# token cost on every drop invocation.
PLANNER_FEW_SHOT = """示例:

输入: https://github.com/34306/vphone-aio
输出: {"action": "fetch_raw", "targets": ["https://raw.githubusercontent.com/34306/vphone-aio/HEAD/README.md"], "title": "vphone-aio", "reason": "github repo, fetch raw README via raw.githubusercontent.com"}

输入: https://example.com/article.html
输出: {"action": "fetch_page", "targets": ["https://example.com/article.html"], "reason": "ordinary webpage"}

输入: /Users/me/projects/myrepo
输出: {"action": "read_local_repo", "targets": ["/Users/me/projects/myrepo"], "reason": "local directory"}

输入: 炼丹炉的 drop-repo 为什么会 clone 整个仓库?
输出: {"action": "ask", "targets": ["炼丹炉的 drop-repo 为什么会 clone 整个仓库?"], "reason": "question"}

输入: # My note\\n\\nsome content
输出: {"action": "read_local_note", "targets": ["# My note\\n\\nsome content"], "reason": "inline markdown text"}

"""


def plan_input(payload: str, root: Path) -> Plan:
    """Call the LLM to produce a Plan for the given payload.

    Raises PlannerError on any failure (LLM error, JSON parse error, schema
    validation error, autonomy block). The caller is expected to fall back to
    the deterministic classifier on PlannerError.
    """
    payload = (payload or "").strip()
    if not payload:
        raise PlannerError("empty payload")

    from .runner.clients import create_client

    try:
        client = create_client(root)
    except Exception as exc:  # noqa: BLE001 - any client failure triggers deterministic fallback
        if isinstance(exc, LLMError):
            raise PlannerError(f"LLM client unavailable: {exc}") from exc
        raise PlannerError(f"LLM client resolution failed: {exc}") from exc

    user_prompt = PLANNER_FEW_SHOT + PLANNER_USER_TEMPLATE.format(payload=payload)
    try:
        result = client.complete(PLANNER_SYSTEM_PROMPT, user_prompt)
    except LLMError as exc:
        raise PlannerError(f"LLM planner call failed: {exc}") from exc

    plan = _parse_plan(result.text)
    plan.validate()
    _LOGGER.info("planner produced plan: action=%s targets=%d reason=%s", plan.action, len(plan.targets), plan.reason)
    return plan


def _parse_plan(text: str) -> Plan:
    raw = _extract_json_object(text)
    if not raw:
        raise PlannerError(f"no JSON object found in planner response: {text[:200]!r}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlannerError(f"planner JSON parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise PlannerError("planner JSON is not an object")

    action = str(data.get("action") or "").strip()
    targets_raw = data.get("targets") or []
    if not isinstance(targets_raw, list):
        raise PlannerError("planner `targets` must be a list")
    targets = [str(item).strip() for item in targets_raw if str(item).strip()]
    title = str(data.get("title") or "").strip()
    reason = str(data.get("reason") or "").strip()
    return Plan(action=action, targets=targets, title=title, reason=reason)


def _extract_json_object(text: str) -> str:
    """Pull the first balanced {...} block out of the LLM response.

    Handles common LLM decorations: leading prose, markdown code fences,
    trailing commentary. Returns "" if no balanced object is found.
    """
    if not text:
        return ""
    # Strip markdown code fences if present.
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return candidate[start : index + 1]
    return ""


def plan_from_dict(data: dict[str, Any]) -> Plan:
    """Build a Plan from a pre-parsed dict (used by tests and replay)."""
    targets_raw = data.get("targets") or []
    plan = Plan(
        action=str(data.get("action") or "").strip(),
        targets=[str(item).strip() for item in targets_raw if str(item).strip()],
        title=str(data.get("title") or "").strip(),
        reason=str(data.get("reason") or "").strip(),
    )
    plan.validate()
    return plan
