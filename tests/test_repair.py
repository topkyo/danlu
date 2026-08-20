"""Offline unit tests for the lint/repair path (audit + rollback main path).

Covers:
- ``aiwiki.app_linting.repair.render_repair_backlog`` — repair backlog markdown
  (summary counts, priority-queue branching, section truncation, dedup rules)

All tests are deterministic: no network, no LLM.
"""

from __future__ import annotations

from aiwiki.app_linting.repair import render_repair_backlog

GENERATED_AT = "2026-08-05T00:00:00+00:00"


# ---------------------------------------------------------------------------
# app_linting.repair.render_repair_backlog
# ---------------------------------------------------------------------------


def _lint_result(errors: int = 0, warnings: int = 0, findings: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "counts": {"errors": errors, "warnings": warnings},
        "findings": list(findings or []),
        "path": "wiki/indexes/lint-report.md",
    }


def _render(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "compile_result": {},
        "lint_result": _lint_result(),
        "memory": {},
        "active_protocol": "general",
        "promotion_result": {},
        "pending_sources": [],
        "placeholder_concepts": [],
        "pending_review_decisions": [],
        "pending_review_judgments": [],
        "overdue_pages": [],
        "escalated_pages": [],
        "semantic_report": "",
        "generated_at": GENERATED_AT,
    }
    kwargs.update(overrides)
    return render_repair_backlog(**kwargs)  # type: ignore[arg-type]


class TestRenderRepairBacklog:
    def test_empty_state_renders_relax_line_and_empty_sections(self) -> None:
        text = _render()
        assert text.startswith("# 修复待办\n")
        assert f"- 生成时间：`{GENERATED_AT}`" in text
        assert "- 当前协议焦点：`general` (通用协议)" in text
        assert "- Lint 错误：`0`" in text
        assert "- Lint 警告：`0`" in text
        # The general protocol declares a nightly focus list.
        assert "### 协议 Nightly 焦点" in text
        assert "- 关注 pending review、aging、repair backlog、weak concepts。" in text
        assert "1. 当前没有紧急修复项，继续观察 nightly 漂移和 lint 输出。" in text
        assert "- 当前没有 machine-memory 动作。" in text
        assert "- 当前没有图谱专项修复项。" in text
        assert "- Lint 报告：`wiki/indexes/lint-report.md`" in text
        assert "- 语义 lint：" not in text
        assert text.endswith("\n")

    def test_unknown_protocol_skips_nightly_section(self) -> None:
        text = _render(active_protocol="nonexistent")
        assert "### 协议 Nightly 焦点" not in text
        assert "- 当前协议焦点：`nonexistent` (Nonexistent)" in text

    def test_priority_queue_orders_errors_first_then_sources_then_concepts(self) -> None:
        text = _render(
            lint_result=_lint_result(
                errors=2,
                findings=[
                    {"severity": "error", "path": "wiki/a.md", "message": "broken"},
                    {"severity": "error", "path": "wiki/b.md", "message": "broken too"},
                ],
            ),
            pending_sources=["s1"],
            placeholder_concepts=["c1"],
            pending_review_decisions=[{"path": "wiki/decisions/d1.md", "status": "pending-review"}],
        )
        assert "1. 先解决 `2` 个 lint 错误，再继续依赖下游输出。" in text
        assert "2. 补齐 `1` 个仍是占位摘要的来源页。" in text
        assert "3. 重写 `1` 个仍使用回退摘要的概念页。" in text
        assert "4. 审阅 `1` 个等待批准或复审的决策页。" in text
        assert text.index("1. 先解决") < text.index("2. 补齐") < text.index("3. 重写") < text.index("4. 审阅")
        # The relax line must not appear once any urgent bucket is non-empty.
        assert "当前没有紧急修复项" not in text

    def test_actions_only_still_render_relax_line(self) -> None:
        # The "no urgent items" check deliberately ignores machine-memory actions.
        memory = {
            "health": {
                "actions": [
                    {
                        "id": "a1",
                        "kind": "connect-isolated-source",
                        "status": "proposed",
                        "priority": "medium",
                        "title": "Connect source",
                        "primary_path": "wiki/sources/s1.md",
                    }
                ]
            }
        }
        text = _render(memory=memory)
        assert "1. 当前没有紧急修复项，继续观察 nightly 漂移和 lint 输出。" in text
        assert "9. 在 advanced review-queue 查看 `1` 个 machine-memory 修复动作。" in text

    def test_lint_findings_truncated_to_ten(self) -> None:
        findings = [
            {"severity": "error", "path": f"wiki/p{index:02d}.md", "message": f"m{index}"} for index in range(12)
        ]
        text = _render(lint_result=_lint_result(errors=12, findings=findings))
        assert "### Lint 错误" in text
        assert "- `wiki/p09.md`: m9" in text
        assert "wiki/p10.md" not in text
        assert "wiki/p11.md" not in text

    def test_warn_findings_render_under_own_section(self) -> None:
        findings = [
            {"severity": "warn", "path": "wiki/w.md", "message": "soft"},
            {"severity": "error", "path": "wiki/e.md", "message": "hard"},
        ]
        text = _render(lint_result=_lint_result(errors=1, warnings=1, findings=findings))
        assert "### Lint 警告" in text
        assert "- `wiki/w.md`: soft" in text
        # Warn findings must not leak into the error section.
        error_section = text.split("### Lint 错误")[1].split("### Lint 警告")[0]
        assert "wiki/w.md" not in error_section

    def test_overdue_page_listed_in_escalated_is_not_duplicated(self) -> None:
        page = {"path": "wiki/x.md", "status": "pending-review"}
        text = _render(overdue_pages=[page], escalated_pages=[page])
        assert "- 升级：`wiki/x.md` | 状态 `待审`" in text
        assert "- 到期：`wiki/x.md`" not in text

    def test_non_dict_counter_evidence_and_judgment_entries_skipped(self) -> None:
        memory = {
            "health": {
                "counter_evidence_scan": {
                    "pages": [
                        "junk-entry",
                        {
                            "page_path": "wiki/judgments/j1.md",
                            "candidate_count": 2,
                            "source_ids": ["s1"],
                            "shared_terms": ["term"],
                        },
                    ]
                },
                "judgment_review_actions": [
                    42,
                    {"title": "Review j1", "priority": "high", "reason_codes": ["overdue"]},
                    {"title": "Review j2", "review_command": "advanced review-queue"},
                ],
            }
        }
        text = _render(memory=memory)
        assert "### Counter-evidence Candidates" in text
        assert "- `wiki/judgments/j1.md` | candidates `2` | sources `s1` | shared `term`" in text
        assert "junk-entry" not in text
        assert "### Judgment Review Actions" in text
        assert "- `Review j1` | priority `high` | reasons `overdue`" in text
        assert "- `Review j2` | priority `medium` | reasons `none` | command `advanced review-queue`" in text

    def test_non_dict_counter_evidence_scan_is_ignored(self) -> None:
        text = _render(memory={"health": {"counter_evidence_scan": "not-a-dict"}})
        assert "Counter-evidence" not in text.split("## 可执行事项")[1]

    def test_rewrite_proposals_are_not_actionable_in_repair(self) -> None:
        memory = {
            "health": {
                "concept_rewrite": {
                    "counts": {"active": 3, "pending_review": 1},
                    "proposals": [
                        {
                            "slug": "p1",
                            "status": "applied",
                            "previous_markdown": "old body",
                            "target_path": "wiki/concepts/a.md",
                        },
                        {"slug": "p2", "status": "accepted", "apply_ready": True, "target_path": "wiki/concepts/b.md"},
                        {"slug": "p3", "status": "proposed", "target_path": "wiki/concepts/c.md"},
                    ],
                }
            }
        }
        text = _render(memory=memory)
        assert "### Rewrite Proposals" not in text
        assert "concept rewrite proposal" not in text
        assert "advanced alchemy revert" not in text
        assert "可应用 Rewrite" not in text
        assert "待审 Rewrite" not in text

    def test_full_backlog_renders_all_sections(self) -> None:
        memory = {
            "drift": {"sources_without_concepts": ["s9"]},
            "health": {
                "isolated_source_ids": ["iso1"],
                "singleton_concept_slugs": ["single1"],
                "bridge_concept_slugs": ["bridge1", "bridge2"],
                "overloaded_concept_slugs": ["over1"],
                "component_count": 4,
                "actions": [
                    {
                        "id": "a1",
                        "kind": "add-source-concept-link",
                        "status": "accepted",
                        "active": True,
                        "priority": "high",
                        "title": "Link s1",
                        "primary_path": "wiki/sources/s1.md",
                        "secondary_path": "wiki/concepts/c1.md",
                        "occurrences": 3,
                        "command_hint": "advanced review-queue",
                    }
                ],
                "overdue_actions": [
                    {"id": "a2", "title": "Overdue act", "status": "accepted", "revisit_after": "2026-01-01"},
                    {"id": "a6", "title": "Overdue only", "status": "proposed", "revisit_after": "2026-01-03"},
                ],
                "escalated_actions": [
                    {"id": "a3", "title": "Escalated act", "status": "proposed"},
                    {"id": "a2", "title": "Overdue act", "status": "accepted"},
                ],
                "inactive_actions": [{"id": "a4", "title": "Cleared act", "inactive_since": "2026-01-02"}],
                "concept_quality": {
                    "counts": {
                        "weak": 1,
                        "soft_hardness": 2,
                        "medium_or_hard": 3,
                        "merge_candidates": 1,
                        "conflict_signals": 1,
                        "gap_signals": 5,
                    },
                    "weak_concepts": [{"path": "wiki/concepts/w.md", "issues": ["thin"], "source_count": 0}],
                    "rewrite_candidates": [
                        {"path": "wiki/concepts/r.md", "priority": "high", "rewrite_strategy": "split"}
                    ],
                    "conflict_signals": [{"slug": "conflict1", "label": "矛盾", "source_pages": ["wiki/sources/s1.md"]}],
                    "merge_candidates": [
                        {"left_slug": "l", "right_slug": "r", "shared_sources": ["s1", "s2"], "shared_tokens": ["tok"]}
                    ],
                },
                "link_suggestions": [
                    {"source_page": "wiki/sources/s1.md", "concept_page": "wiki/concepts/c1.md",
                     "shared_terms": ["t1", "t2"], "score": 3}
                ],
            },
            "transition": {
                "changed": True,
                "previous_digest": "prev",
                "current_digest": "cur",
                "added_source_ids": ["s2"],
                "added_concept_slugs": ["c2"],
                "added_edges": 3,
                "removed_edges": 1,
            },
        }
        text = _render(
            memory=memory,
            pending_sources=["s1"],
            pending_review_judgments=[{"path": "wiki/judgments/j1.md", "status": "pending-review"}],
            overdue_pages=[
                {"path": "wiki/e.md", "status": "pending-review"},
                {"path": "wiki/o.md", "status": "confirmed"},
            ],
            escalated_pages=[{"path": "wiki/e.md", "status": "pending-review"}],
            promotion_result={"count": 1, "pages": [
                {"kind": "decision", "path": "wiki/decisions/d1.md", "action": "promote", "occurrences": 2}
            ]},
            semantic_report="wiki/indexes/semantic-lint.md",
        )
        # Header counts.
        assert "- 图谱分量数：`4`" in text
        assert "- 弱概念页：`1`" in text
        assert "- 概念证据缺口：`5`" in text
        assert "- 图谱修复动作：`1`" in text
        assert "可安全执行" not in text
        assert "Ready 动作" not in text
        assert "执行批次" not in text
        assert "可应用 Rewrite" not in text
        # Priority queue lines.
        assert "3a. 按概念质量看板优先处理 `1` 个弱概念页。" in text
        assert "3d. 把 `2` 个仍停留在 `hardness: soft` 的概念页提升到更可复用的结构层。" in text
        assert "5. 审阅 `1` 个仍处于暂定或跟踪状态的判断页。" in text
        assert "6. 先清理 `2` 个已到期但还没复审的页面。" in text
        assert "7. 提升 `1` 个已经超过升级阈值的页面优先级。" in text
        assert "8. 检查本轮自动晋升的 `1` 个页面，确认是否需要补证据和审阅。" in text
        assert "9. 在 advanced review-queue 查看 `1` 个 machine-memory 修复动作。" in text
        assert "10. 优先清理 `2` 个已到期待处理的 machine-memory 动作。" in text
        assert "11. 先处理 `2` 个已升级的 machine-memory 动作。" in text
        assert "11a. 先把 `1` 个概念冲突信号显式写进相关概念页。" in text
        assert "17. 在下一轮研究前先检查最新的机器记忆漂移。" in text
        # Machine-memory action line with secondary path and display status.
        assert (
            "- [high] `wiki/sources/s1.md` | secondary `wiki/concepts/c1.md` | Link s1"
            " | status `已接受` | seen `3`"
        ) in text
        # Review queue: judgments render with their display status.
        assert "- 判断：`wiki/judgments/j1.md` 状态 `待审`" in text
        # Page aging: escalated pages are not repeated as overdue.
        assert "### Aging 信号" in text
        assert "- 升级：`wiki/e.md` | 状态 `待审`" in text
        assert "- 到期：`wiki/e.md`" not in text
        assert "- 到期：`wiki/o.md` | 状态 `已确认`" in text
        # Action aging: escalated first, overdue deduped by id.
        assert "### Action Aging" in text
        assert "- 升级：`a3` | Escalated act | status `待处理`" in text
        assert "- 升级：`a2` | Overdue act | status `已接受`" in text
        assert "- 到期：`a2`" not in text
        assert "- 到期：`a6` | Overdue only | revisit `2026-01-03`" in text
        assert "### 最近清除动作" in text
        assert "- 清除：`a4` | Cleared act | inactive_since `2026-01-02`" in text
        # Concept quality sections.
        assert "- `wiki/concepts/w.md` | issues `thin` | sources `0`" in text
        assert "### 概念重写优先级" not in text
        assert "- `wiki/concepts/r.md` | priority `high` | strategy `split`" not in text
        assert "- `conflict1` | signal `矛盾` | sources `wiki/sources/s1.md`" in text
        assert "- `l` <-> `r` | shared_sources `2` | shared_tokens `tok`" in text
        # Link suggestions / graph repair.
        assert "- `wiki/sources/s1.md` -> `wiki/concepts/c1.md` | shared `t1, t2` | score `3`" in text
        assert "- `wiki/sources/s9.md`" in text
        assert "- 将孤立来源 `wiki/sources/iso1.md` 至少连接到一个稳定概念。" in text
        assert "- 检查单节点概念 `wiki/concepts/single1.md` 是否缺少相关概念或来源链接。" in text
        assert "- 考虑把过宽的概念 `wiki/concepts/over1.md` 拆成更窄的页面。" in text
        assert "- 保留桥接概念：`bridge1, bridge2`，因为它们连接了多个簇。" in text
        # Promotion line.
        assert "- 决策：`wiki/decisions/d1.md` | 动作 `promote` | 重复次数 `2`" in text
        # Transition drift section.
        assert "### 结构漂移" in text
        assert "- 上一版摘要：`prev`" in text
        assert "- 新增边：`3`" in text
        # Semantic report line appended to related artifacts.
        assert "- 语义 lint：`wiki/indexes/semantic-lint.md`" in text

