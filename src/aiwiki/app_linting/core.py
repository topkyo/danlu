"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..content.io import (
    sync_manifest_with_raw,
)
from ..protocol.scaffold import ensure_layout
from ..state.paths import (
    lint_reports_dir,
)
from ..utils.io import (
    atomic_write_text,
    runtime_write_operation,
)
from ..utils.path import relative_path
from ..utils.time import utc_now


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def pending_source_summary_ids(root: Path, entries: list[dict[str, Any]]) -> list[str]:
    pending: list[str] = []
    for entry in entries:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending.append(entry["id"])
    return pending


@runtime_write_operation
def lint_wiki(root: Path) -> dict[str, Any]:
    context = _start_lint_context(root)
    _lint_layout_phase(context)
    _lint_runtime_phase(context)
    _lint_governance_phase(context)
    _lint_curated_phase(context)
    return _write_lint_report(context)


@dataclass
class _LintContext:
    root: Path
    manifest: dict[str, Any]
    findings: list[Finding] = field(default_factory=list)
    protocol_state: dict[str, Any] = field(default_factory=dict)
    decision_pages: list[dict[str, Any]] = field(default_factory=list)
    judgment_pages: list[dict[str, Any]] = field(default_factory=list)
    pack_memory: dict[str, Any] = field(default_factory=dict)
    expected_output_packs: dict[str, Any] = field(default_factory=dict)
    expected_domain_pilots: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, path: str | Path, message: str) -> None:
        finding_path = relative_path(self.root, path) if isinstance(path, Path) else str(path)
        self.findings.append(Finding(severity, finding_path, message))


def _start_lint_context(root: Path) -> _LintContext:
    ensure_layout(root)
    return _LintContext(root=root, manifest=sync_manifest_with_raw(root))


_LINT_REPORT_KEEP = 10


def _rotate_lint_reports(lint_dir: Path) -> None:
    """Keep only the most recent _LINT_REPORT_KEEP reports per lint family."""
    for pattern in ("lint-*.md", "semantic-lint-*.md"):
        reports = sorted(lint_dir.glob(pattern))
        if len(reports) <= _LINT_REPORT_KEEP:
            continue
        for old in reports[: len(reports) - _LINT_REPORT_KEEP]:
            old.unlink(missing_ok=True)


def _write_lint_report(context: _LintContext) -> dict[str, Any]:
    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    lint_dir = lint_reports_dir(context.root)
    lint_dir.mkdir(parents=True, exist_ok=True)
    report_path = lint_dir / report_name
    error_count = sum(1 for finding in context.findings if finding.severity == "error")
    warn_count = sum(1 for finding in context.findings if finding.severity == "warn")
    lines = [
        "# Lint 报告",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 错误数：`{error_count}`",
        f"- 警告数：`{warn_count}`",
        "",
        "## 发现",
    ]
    if not context.findings:
        lines.append("- 没有发现问题。")
    else:
        for finding in context.findings:
            lines.append(f"- `{finding.severity}` {finding.path}: {finding.message}")
    atomic_write_text(report_path, "\n".join(lines) + "\n")
    _rotate_lint_reports(lint_dir)
    return {
        "path": relative_path(context.root, report_path),
        "counts": {"errors": error_count, "warnings": warn_count},
        "findings": [
            {"severity": finding.severity, "path": finding.path, "message": finding.message}
            for finding in context.findings
        ],
    }


from .phases import (  # noqa: E402
    _lint_layout_phase,
    _lint_runtime_phase,
)
from .phases_governance import (  # noqa: E402
    _lint_curated_phase,
    _lint_governance_phase,
)
