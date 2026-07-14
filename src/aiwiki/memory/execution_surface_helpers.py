"""Helper line builders for execution surface renderers."""

from __future__ import annotations

from typing import Any


def concept_quality_summary_lines(*, compiled_at: str, quality: dict[str, Any], rewrite_state: dict[str, Any]) -> list[str]:
    counts = quality.get("counts", {})
    return [
        "# 概念质量",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 弱概念页：`{counts.get('weak', 0)}`",
        f"- 稳定概念页：`{counts.get('stable', 0)}`",
        f"- 占位概念页：`{counts.get('placeholders', 0)}`",
        f"- 合并候选：`{counts.get('merge_candidates', 0)}`",
        f"- 重写候选：`{counts.get('rewrite_candidates', 0)}`",
        f"- 冲突信号：`{counts.get('conflict_signals', 0)}`",
        f"- 证据缺口：`{counts.get('gap_signals', 0)}`",
        f"- 平均质量分：`{quality.get('average_quality_score', 0)}`",
        (
            "- Quality bands："
            f" strong `{counts.get('strong_quality', 0)}`"
            f" / stable `{counts.get('stable_quality', 0)}`"
            f" / watch `{counts.get('watch_quality', 0)}`"
            f" / fragile `{counts.get('fragile_quality', 0)}`"
        ),
        (
            "- Hardness："
            f" hard `{counts.get('hard_hardness', 0)}`"
            f" / medium `{counts.get('medium_hardness', 0)}`"
            f" / soft `{counts.get('soft_hardness', 0)}`"
        ),
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审提案：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用提案：`{rewrite_state.get('counts', {}).get('apply_ready', 0)}`",
        f"- 已验证提案：`{rewrite_state.get('counts', {}).get('verified_passed', 0)}`",
        f"- 可回滚提案：`{rewrite_state.get('counts', {}).get('revert_ready', 0)}`",
        "",
    ]


__all__ = ["concept_quality_summary_lines"]
