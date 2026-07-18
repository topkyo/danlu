"""Failure / status helpers for run-ask workflows."""

from __future__ import annotations

from pathlib import Path

from aiwiki.llm import classify_backend_error
from aiwiki.runner.workflow_shared import _receipt_error_class
from aiwiki.runner.workflows_ask_frontmatter import _strip_report_skeleton_reference_hints
from aiwiki.utils.io import atomic_write_text
from aiwiki.utils.markdown import parse_frontmatter, render_frontmatter, strip_frontmatter

_CONTRACT_VALIDATION_PREFIXES = (
    "Ask response is missing",
    "Report ",
)


def _run_ask_failure_llm_status(exc: Exception) -> str:
    backend_error_class = classify_backend_error(str(exc))
    if backend_error_class in {"quota", "timeout", "unavailable"}:
        return "timeout_or_unavailable"
    message = str(exc)
    if any(message.startswith(prefix) for prefix in _CONTRACT_VALIDATION_PREFIXES):
        return "validation_failed"
    if _receipt_error_class(exc) == "parse_error":
        return "validation_failed"
    return "failed"


def _mark_run_ask_artifact_degraded(
    target: Path,
    *,
    reason: str,
    backend: str,
    model: str,
    llm_status: str = "timeout_or_unavailable",
) -> None:
    """Replace the deterministic placeholder artifact with an explicit failed notice."""

    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    title = "LLM 失败：请重试或切换模型"
    query = str(frontmatter.get("query") or "").strip()
    if query:
        try:
            from aiwiki.utils.text import human_query_title

            title = f"LLM 未完成：{human_query_title(query)}"
        except Exception:
            title = "LLM 未完成：请重试或切换模型"
    frontmatter.update(
        {
            "llm_status": llm_status,
            "delivery_mode": "llm-failed",
            "background_status": "failed",
            "llm_failure_reason": reason,
            "llm_backend": backend,
            "llm_model": model,
        }
    )
    body = strip_frontmatter(current)
    references = body[body.find("## 参考") :].strip() if "## 参考" in body else body.strip()
    references = _strip_report_skeleton_reference_hints(references).strip()
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# {title}",
        "",
        "## 当前状态",
        "- LLM 没有返回可用内容；本文件是失败说明，不是最终报告，也不是 fallback 占位答案。",
        f"- 失败原因：`{reason}`。",
        f"- 后端 / 模型：`{backend or 'unknown'}` / `{model or 'unknown'}`.",
        "- 材料投喂、引用解析或上下文准备已完成；可以重试、切换模型，或使用更短的问题。",
        "",
        "## 下一步",
        "- 点击重试 run-ask，或在 Product Shell 设置里切换到更稳定的 backend/model。",
        "- 如果问题来自超长 PDF，优先问一个更具体的问题，避免一次性要求完整分析。",
    ]
    if references:
        lines.extend(["", "## 可用上下文", references])
    atomic_write_text(target, "\n".join(lines).rstrip() + "\n")


def _mark_run_ask_background_artifact_submitted(target: Path, *, job_id: str, status: str = "submitted") -> None:
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    frontmatter.update(
        {
            "background_job_id": job_id,
            "background_status": status,
            "delivery_mode": "background-pending",
            "llm_status": "pending",
        }
    )
    body = strip_frontmatter(current)
    atomic_write_text(target, render_frontmatter(frontmatter).rstrip() + "\n\n" + body.lstrip())


def _mark_run_ask_background_artifact_complete(target: Path, *, status: str, job_id: str = "") -> None:
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    if job_id:
        frontmatter["background_job_id"] = job_id
    frontmatter["background_status"] = status
    body = strip_frontmatter(current)
    atomic_write_text(target, render_frontmatter(frontmatter).rstrip() + "\n\n" + body.lstrip())
