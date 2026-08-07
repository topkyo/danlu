"""Offline unit tests for the lint/repair path (audit + rollback main path).

Covers:
- ``aiwiki.app_linting.repair.render_repair_backlog`` — repair backlog markdown
  (summary counts, priority-queue branching, section truncation, dedup rules)
- ``aiwiki.execution.patch_plan`` — patch role/section/summary/mode resolution
  and ``build_page_patch_plan`` assembly (incl. low-risk state-path append)
- ``aiwiki.execution.repair_plan`` — repair-plan builder, proposal scoring,
  dependency derivation, planner-state assembly, execution-proposal strategy

All tests are deterministic: no network, no LLM; vault fixtures live under
``tmp_path``. Corrupt-state behavior is pinned where the modules own it:
planner-state JSON is loaded best-effort (corrupt -> defaults, no raise),
while a corrupt manifest surfaced through ``safe_apply_preview`` degrades to
``None`` instead of propagating ``CorruptStateError``.
"""

from __future__ import annotations

import json
from pathlib import Path

from aiwiki.app_linting.repair import render_repair_backlog
from aiwiki.execution.patch_plan import (
    build_page_patch_plan,
    patch_mode_for_action,
    patch_role_for_path,
    patch_sections_for_action,
    patch_summary_for_action,
)
from aiwiki.execution.repair_plan import (
    build_machine_memory_repair_plan,
    build_planner_state,
    derive_proposal_dependencies,
    proposal_dependency_weight,
    proposal_impact_score,
    proposal_rollback_summary,
    proposals_overlap,
    repair_execution_proposals,
)

GENERATED_AT = "2026-08-05T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------


def _write_page(root: Path, relative: str, frontmatter: dict[str, object], body: str = "body") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _low_risk_link_vault(root: Path) -> None:
    """Minimal vault where an accepted add-source-concept-link action validates.

    Manifest already lists ``source-alpha`` (validate uses read-only
    ``load_manifest``, not ``sync_manifest_with_raw``). Source/concept pages
    match the action targets.
    """

    (root / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
    (root / "raw" / "inbox" / "alpha.md").write_text("alpha body\n", encoding="utf-8")
    _write_page(root, "wiki/sources/source-alpha.md", {"kind": "source", "title": "Alpha Source"})
    _write_page(root, "wiki/concepts/beta.md", {"kind": "concept", "title": "Beta Concept"})
    manifest_path = root / ".aiwiki" / "state" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "id": "source-alpha",
                        "title": "Alpha Source",
                        "source_type": "raw-drop",
                        "note_kind": "",
                        "original_path": "raw/inbox/alpha.md",
                        "stored_path": "raw/inbox/alpha.md",
                        "kind": "note",
                        "sha256": "deadbeef",
                        "imported_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _low_risk_link_action(**overrides: object) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "act-link",
        "kind": "add-source-concept-link",
        "status": "accepted",
        "active": True,
        "priority": "high",
        "title": "Link alpha into beta",
        "primary_path": "wiki/sources/source-alpha.md",
        "secondary_path": "wiki/concepts/beta.md",
        "source_ids": ["source-alpha"],
        "concept_slugs": ["beta"],
        "occurrences": 2,
    }
    action.update(overrides)
    return action


def _write_planner_state(root: Path, document: dict[str, object]) -> None:
    path = root / ".aiwiki" / "state" / "planner-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")


def _valid_planner_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "state_path": ".aiwiki/state/planner-state.json",
        "active_protocol": "general",
        "pending_proposals": [],
        "priority_queue": [],
        "dependency_graph": {"nodes": [], "edges": []},
        "next_action": {},
        "executed_actions": [],
        "counts": {"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 0},
    }
    document.update(overrides)
    return document


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
        assert "- 关注 pending review、aging、repair backlog、concept rewrite。" in text
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
        assert "9. 按动作队列处理 `1` 个 machine-memory 修复动作。" in text

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

    def test_rewrite_proposal_command_branches(self) -> None:
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
        assert "library receipt / `advanced alchemy-revert` — proposal `p1`" in text
        assert "status `已应用`" in text
        assert "advanced review-queue — proposal `p2` (operator review)" in text
        # Plain proposed proposals keep the default review-queue command.
        assert "- `wiki/concepts/c.md` | status `待审提案` | quality `0` | verify `pending` | strategy `n/a`" in text

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
                "repair_plan": {
                    "counts": {"ready": 1, "triage": 2, "batches": 1, "proposals": 1},
                    "execution_batches": [
                        {
                            "label": "component `c1`",
                            "actions": [{"id": "a1"}, {"id": "a5"}],
                            "escalated": False,
                            "overdue": True,
                            "primary_paths": ["wiki/sources/s1.md"],
                        }
                    ],
                    "execution_proposals": [
                        {
                            "action_id": "a1",
                            "target_paths": ["wiki/sources/s1.md"],
                            "risk": "low",
                            "summary": "cross-link",
                        }
                    ],
                },
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
        assert "- 可安全执行动作：`1`" in text
        # Priority queue lines.
        assert "3a. 按概念质量看板优先处理 `1` 个弱概念页。" in text
        assert "3d. 把 `2` 个仍停留在 `hardness: soft` 的概念页提升到更可复用的结构层。" in text
        assert "5. 审阅 `1` 个仍处于暂定或跟踪状态的判断页。" in text
        assert "6. 先清理 `2` 个已到期但还没复审的页面。" in text
        assert "7. 提升 `1` 个已经超过升级阈值的页面优先级。" in text
        assert "8. 检查本轮自动晋升的 `1` 个页面，确认是否需要补证据和审阅。" in text
        assert "9a. 先执行 `1` 个已接受动作和 `1` 个批次。" in text
        assert "9b. 参考 `1` 个页级执行提案决定下一批修复。" in text
        assert "9c. 其中 `1` 个低风险动作可在 advanced review-queue 中查看。" in text
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
        assert "- `wiki/concepts/r.md` | priority `high` | strategy `split`" in text
        assert "- `conflict1` | signal `矛盾` | sources `wiki/sources/s1.md`" in text
        assert "- `l` <-> `r` | shared_sources `2` | shared_tokens `tok`" in text
        # Repair-plan sections.
        assert "- component `c1` | actions `2` | escalated `False` | overdue `True` | primary `wiki/sources/s1.md`" in text
        assert "- `a1` | targets `wiki/sources/s1.md` | risk `low` | strategy `cross-link`" in text
        assert "- `a1` | `Link s1` | command `advanced review-queue` | primary `wiki/sources/s1.md`" in text
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


# ---------------------------------------------------------------------------
# execution.patch_plan
# ---------------------------------------------------------------------------


class TestPatchRoleForPath:
    def test_prefix_mapping(self) -> None:
        assert patch_role_for_path("wiki/sources/a.md") == "source"
        assert patch_role_for_path("wiki/concepts/a.md") == "concept"
        assert patch_role_for_path("wiki/indexes/a.md") == "index"
        assert patch_role_for_path(".aiwiki/state/x.json") == "state"
        assert patch_role_for_path("output/control/x.md") == "output"
        assert patch_role_for_path("wiki/judgments/j1.md") == "other"
        assert patch_role_for_path("") == "other"


class TestPatchTemplateLookup:
    def test_sections_template_hit(self) -> None:
        assert patch_sections_for_action("add-source-concept-link", "source") == ("概念链接", "摘要", "引用")
        assert patch_sections_for_action("add-source-concept-link", "state") == ("source_to_concept",)
        assert patch_sections_for_action("refresh-citation-snapshots", "other") == ("frontmatter", "引用")

    def test_sections_fallback_for_unknown_kind(self) -> None:
        assert patch_sections_for_action("mystery", "source") == ("摘要", "概念链接", "引用")
        assert patch_sections_for_action("mystery", "index") == ("Status", "Open Questions")
        assert patch_sections_for_action("mystery", "state") == ("state",)

    def test_summary_template_role_and_kind_fallback(self) -> None:
        assert (
            patch_summary_for_action("add-source-concept-link", "source")
            == "在来源页补 concept 引用，并保留 raw/source provenance。"
        )
        # split-overloaded-concept has no "source" role: fall back to the kind summary.
        assert (
            patch_summary_for_action("split-overloaded-concept", "source")
            == "把过载概念拆成更窄的主题，并把来源重新分流。"
        )
        assert patch_summary_for_action("mystery", "source") == "检查相关页面并补充修复说明。"

    def test_mode_template_and_fallback(self) -> None:
        assert patch_mode_for_action("refresh-citation-snapshots", "other") == "semi-auto-apply"
        assert patch_mode_for_action("connect-isolated-source", "index") == "review"
        assert patch_mode_for_action("split-overloaded-concept", "concept") == "rewrite"
        assert patch_mode_for_action("mystery", "concept") == "update"


class TestBuildPagePatchPlan:
    def test_dedups_strips_and_skips_empty_paths(self, tmp_path: Path) -> None:
        action = {
            "kind": "add-source-concept-link",
            "status": "proposed",
            "primary_path": "  wiki/sources/a.md  ",
            "secondary_path": "wiki/sources/a.md",
        }
        plan = build_page_patch_plan(tmp_path, action)
        assert len(plan) == 1
        entry = plan[0]
        assert entry["path"] == "wiki/sources/a.md"
        assert entry["role"] == "source"
        assert entry["role_label"] == "来源页"
        assert entry["exists"] is False
        # Missing file: title falls back to the path stem.
        assert entry["title"] == "a"

    def test_reads_frontmatter_title_for_existing_page(self, tmp_path: Path) -> None:
        _write_page(tmp_path, "wiki/sources/alpha.md", {"kind": "source", "title": "Alpha Title"})
        action = {"kind": "connect-isolated-source", "status": "proposed", "primary_path": "wiki/sources/alpha.md"}
        plan = build_page_patch_plan(tmp_path, action)
        assert plan[0]["title"] == "Alpha Title"
        assert plan[0]["exists"] is True

    def test_state_role_skips_frontmatter_title(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".aiwiki" / "state" / "manual-links.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{}\n", encoding="utf-8")
        action = {
            "kind": "add-source-concept-link",
            "status": "proposed",
            "primary_path": ".aiwiki/state/manual-links.json",
        }
        plan = build_page_patch_plan(tmp_path, action)
        assert plan[0]["role"] == "state"
        assert plan[0]["exists"] is True
        assert plan[0]["title"] == "manual-links"

    def test_auxiliary_paths_appended_per_kind(self, tmp_path: Path) -> None:
        action = {"kind": "split-overloaded-concept", "status": "proposed", "primary_path": "wiki/concepts/c.md"}
        plan = build_page_patch_plan(tmp_path, action)
        assert [entry["path"] for entry in plan] == [
            "wiki/concepts/c.md",
            "wiki/indexes/repair-backlog.md",
        ]
        assert plan[1]["role"] == "index"
        assert plan[1]["mode"] == "review"

    def test_low_risk_action_appends_manual_link_state_path(self, tmp_path: Path) -> None:
        _low_risk_link_vault(tmp_path)
        plan = build_page_patch_plan(tmp_path, _low_risk_link_action())
        assert [entry["path"] for entry in plan] == [
            "wiki/sources/source-alpha.md",
            "wiki/concepts/beta.md",
            ".aiwiki/state/manual-links.json",
        ]
        state_entry = plan[-1]
        assert state_entry["role"] == "state"
        assert state_entry["mode"] == "semi-auto-apply"
        assert state_entry["sections"] == ["source_to_concept"]
        assert state_entry["exists"] is False
        # Real pages pick up frontmatter titles.
        assert plan[0]["title"] == "Alpha Source"
        assert plan[1]["title"] == "Beta Concept"

    def test_non_low_risk_action_skips_state_path(self, tmp_path: Path) -> None:
        _low_risk_link_vault(tmp_path)
        plan = build_page_patch_plan(tmp_path, _low_risk_link_action(status="proposed"))
        assert [entry["path"] for entry in plan] == [
            "wiki/sources/source-alpha.md",
            "wiki/concepts/beta.md",
        ]

    def test_corrupt_manifest_degrades_to_no_state_path(self, tmp_path: Path) -> None:
        # load_manifest is strict (CorruptStateError); safe_apply_preview catches
        # RuntimeError and returns None, so the patch plan simply omits the
        # state path instead of raising.
        _low_risk_link_vault(tmp_path)
        manifest = tmp_path / ".aiwiki" / "state" / "manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{not-json", encoding="utf-8")
        plan = build_page_patch_plan(tmp_path, _low_risk_link_action())
        assert [entry["path"] for entry in plan] == [
            "wiki/sources/source-alpha.md",
            "wiki/concepts/beta.md",
        ]


# ---------------------------------------------------------------------------
# execution.repair_plan — pure scoring / dependency helpers
# ---------------------------------------------------------------------------


class TestProposalRollbackSummary:
    def test_manual_link_state_branch(self) -> None:
        proposal = {"safe_apply_preview": {"apply_mode": "manual-link-state"}}
        assert proposal_rollback_summary(proposal) == "禁用对应的 manual-link state 条目并重跑 compile。"

    def test_citation_snapshot_refresh_branch(self) -> None:
        proposal = {"safe_apply_preview": {"apply_mode": "citation-snapshot-refresh"}}
        assert proposal_rollback_summary(proposal) == "恢复之前的 citation_snapshots metadata 并重跑 compile。"

    def test_default_branch_for_other_modes_and_missing_preview(self) -> None:
        fallback = "回滚时需要人工恢复目标页，然后重跑 compile。"
        assert proposal_rollback_summary({"safe_apply_preview": {"apply_mode": "resolve-monitor"}}) == fallback
        assert proposal_rollback_summary({"safe_apply_preview": None}) == fallback
        assert proposal_rollback_summary({"safe_apply_preview": "junk"}) == fallback
        assert proposal_rollback_summary({}) == fallback


class TestProposalImpactScore:
    def test_defaults_to_medium_base(self) -> None:
        assert proposal_impact_score({}, {}) == 35

    def test_priority_base_mapping(self) -> None:
        assert proposal_impact_score({"priority": "high"}, {}) == 55
        assert proposal_impact_score({"priority": "low"}, {}) == 20
        assert proposal_impact_score({"priority": "weird"}, {}) == 20

    def test_proposal_priority_used_when_action_lacks_it(self) -> None:
        assert proposal_impact_score({}, {"priority": "high"}) == 55

    def test_bonuses_and_caps(self) -> None:
        action = {
            "priority": "high",
            "focus_score": 100,
            "occurrences": 100,
            "status": "accepted",
            "escalation_candidate": "true",
            "overdue_review": "true",
            "policy_decision": "allow",
        }
        # 55 + 24 + 12 + 10 + 8 + 6 + 6 = 121 -> capped at 100.
        assert proposal_impact_score(action, {}) == 100
        # Individual caps: focus bonus max 24, occurrence bonus max 12.
        assert proposal_impact_score({"focus_score": 8}, {}) == 35 + 24
        assert proposal_impact_score({"occurrences": 6}, {}) == 35 + 12
        # Status / policy fall back to the proposal when the action lacks them.
        assert proposal_impact_score({}, {"status": "accepted", "policy_decision": "allow"}) == 35 + 10 + 6


class TestProposalDependencyWeight:
    def test_kind_ranking(self) -> None:
        assert proposal_dependency_weight({"proposal_kind": "split-concept"}) == (5, 0)
        assert proposal_dependency_weight({"proposal_kind": "expand-concept"}) == (4, 0)
        assert proposal_dependency_weight({"proposal_kind": "connect-source"}) == (3, 0)
        assert proposal_dependency_weight({"proposal_kind": "cross-link"}) == (2, 0)
        assert proposal_dependency_weight({"proposal_kind": "refresh-snapshots"}) == (1, 0)
        assert proposal_dependency_weight({"proposal_kind": "monitor-bridge"}) == (1, 0)
        assert proposal_dependency_weight({"proposal_kind": "manual-repair"}) == (0, 0)

    def test_unknown_kind_and_impact_tiebreak(self) -> None:
        assert proposal_dependency_weight({"proposal_kind": "mystery", "impact_score": 42}) == (0, 42)
        assert proposal_dependency_weight({}) == (0, 0)


class TestProposalsOverlap:
    def test_target_path_intersection(self) -> None:
        left = {"target_paths": ["wiki/a.md"]}
        right = {"target_paths": ["wiki/a.md", "wiki/b.md"]}
        assert proposals_overlap(left, right) is True

    def test_source_and_concept_intersection(self) -> None:
        assert proposals_overlap({"source_ids": ["s1"]}, {"source_ids": ["s1"]}) is True
        assert proposals_overlap({"concept_slugs": ["c1"]}, {"concept_slugs": ["c1"]}) is True

    def test_component_id_match_requires_non_empty(self) -> None:
        assert proposals_overlap({"component_id": "c1"}, {"component_id": "c1"}) is True
        assert proposals_overlap({}, {"component_id": ""}) is False

    def test_disjoint_and_non_string_entries(self) -> None:
        assert proposals_overlap({"target_paths": ["a"]}, {"target_paths": ["b"]}) is False
        assert proposals_overlap({"target_paths": [None, 7]}, {"target_paths": [7]}) is False


class TestDeriveProposalDependencies:
    def test_lower_weight_overlapping_proposal_depends_on_higher(self) -> None:
        proposals = [
            {"action_id": "low", "proposal_kind": "manual-repair", "impact_score": 10, "target_paths": ["p"]},
            {"action_id": "high", "proposal_kind": "split-concept", "impact_score": 10, "target_paths": ["p"]},
        ]
        derive_proposal_dependencies(proposals)
        assert proposals[0]["depends_on"] == ["high"]
        assert proposals[1]["depends_on"] == []

    def test_equal_weight_does_not_create_dependency(self) -> None:
        proposals = [
            {"action_id": "a", "proposal_kind": "cross-link", "impact_score": 5, "target_paths": ["p"]},
            {"action_id": "b", "proposal_kind": "cross-link", "impact_score": 5, "target_paths": ["p"]},
        ]
        derive_proposal_dependencies(proposals)
        assert proposals[0]["depends_on"] == []
        assert proposals[1]["depends_on"] == []

    def test_non_overlapping_and_missing_action_id_skipped(self) -> None:
        proposals = [
            {"action_id": "a", "proposal_kind": "manual-repair", "target_paths": ["p1"]},
            {"proposal_kind": "split-concept", "impact_score": 99, "target_paths": ["p1"]},
            {"action_id": "c", "proposal_kind": "split-concept", "target_paths": ["other"]},
        ]
        derive_proposal_dependencies(proposals)
        assert proposals[0]["depends_on"] == []
        assert proposals[1]["depends_on"] == []
        assert proposals[2]["depends_on"] == []


# ---------------------------------------------------------------------------
# execution.repair_plan — build_machine_memory_repair_plan
# ---------------------------------------------------------------------------


def _action(action_id: str, status: str, **overrides: object) -> dict[str, object]:
    action: dict[str, object] = {
        "id": action_id,
        "kind": "connect-isolated-source",
        "status": status,
        "active": True,
        "priority": "medium",
        "title": f"Action {action_id}",
        "primary_path": f"wiki/sources/{action_id}.md",
    }
    action.update(overrides)
    return action


class TestBuildMachineMemoryRepairPlan:
    def test_empty_health_returns_zero_counts(self, tmp_path: Path) -> None:
        plan = build_machine_memory_repair_plan(tmp_path, {})
        assert plan["counts"] == {
            "ready": 0,
            "triage": 0,
            "deferred": 0,
            "inactive": 0,
            "batches": 0,
            "proposals": 0,
            "patch_steps": 0,
            "blocked_proposals": 0,
        }
        assert plan["ready_actions"] == []
        assert plan["triage_actions"] == []
        assert plan["deferred_actions"] == []
        assert plan["inactive_actions"] == []
        assert plan["execution_batches"] == []
        assert plan["execution_proposals"] == []
        assert plan["planner_state"]["counts"]["pending_proposals"] == 0

    def test_status_partition_and_enrichment(self, tmp_path: Path) -> None:
        health = {
            "actions": [
                _action("a1", "accepted", kind="add-source-concept-link"),
                _action("a2", "proposed"),
                _action("a3", "deferred"),
                _action("a4", "resolved"),
                "not-a-dict",
            ],
            "inactive_actions": [_action("a5", "resolved", active=False)],
        }
        plan = build_machine_memory_repair_plan(tmp_path, health)
        assert [action["id"] for action in plan["ready_actions"]] == ["a1"]
        assert [action["id"] for action in plan["triage_actions"]] == ["a2"]
        assert [action["id"] for action in plan["deferred_actions"]] == ["a3"]
        # Resolved active actions land in no bucket; non-dict entries are dropped.
        assert plan["counts"]["ready"] == 1
        assert plan["counts"]["triage"] == 1
        assert plan["counts"]["deferred"] == 1
        assert plan["counts"]["inactive"] == 1
        # describe_machine_memory_action enrichment: general protocol rule allows
        # low-risk apply for accepted add-source-concept-link.
        ready = plan["ready_actions"][0]
        assert ready["execution_band"] == "bundle-safe-apply"
        assert ready["policy_decision"] == "allow"
        assert ready["apply_ready"] == "true"
        assert ready["focus_score"] == 0
        triage = plan["triage_actions"][0]
        assert triage["execution_policy"] == "triage"
        assert triage["apply_ready"] == "false"

    def test_batches_grouped_by_component_and_sorted(self, tmp_path: Path) -> None:
        health = {
            "actions": [
                _action("a1", "accepted", priority="low", component_id="c1", secondary_path="wiki/concepts/c1.md"),
                _action("a2", "accepted", priority="high", component_id="c1"),
                _action("a3", "accepted"),
            ],
            "escalated_actions": [{"id": "a3"}],
            "overdue_actions": [{"id": "a1"}],
        }
        plan = build_machine_memory_repair_plan(tmp_path, health)
        batches = plan["execution_batches"]
        assert len(batches) == 2
        # Escalated batch sorts first even though its priority rank is worse.
        assert batches[0]["id"] == "wiki/sources/a3.md"
        assert batches[0]["label"] == "page `wiki/sources/a3.md`"
        assert batches[0]["escalated"] is True
        assert batches[0]["overdue"] is False
        component_batch = batches[1]
        assert component_batch["id"] == "c1"
        assert component_batch["label"] == "component `c1`"
        assert component_batch["component_id"] == "c1"
        assert component_batch["overdue"] is True
        # priority_rank is the min across the batch (high=0 wins over low=2).
        assert component_batch["priority_rank"] == 0
        assert component_batch["action_ids"] == ["a1", "a2"]
        assert component_batch["primary_paths"] == ["wiki/sources/a1.md", "wiki/sources/a2.md"]
        assert component_batch["secondary_paths"] == ["wiki/concepts/c1.md"]
        # Actions inside the batch sort by priority rank (high before low).
        assert [action["id"] for action in component_batch["actions"]] == ["a2", "a1"]

    def test_batch_and_inactive_truncation(self, tmp_path: Path) -> None:
        health = {
            "actions": [_action(f"a{index}", "accepted") for index in range(11)],
            "inactive_actions": [_action(f"i{index}", "resolved", active=False) for index in range(13)],
        }
        plan = build_machine_memory_repair_plan(tmp_path, health)
        # counts reflect the untruncated totals; lists are capped.
        assert plan["counts"]["batches"] == 11
        assert len(plan["execution_batches"]) == 10
        assert plan["counts"]["inactive"] == 13
        assert len(plan["inactive_actions"]) == 12

    def test_missing_planner_state_file_uses_defaults(self, tmp_path: Path) -> None:
        plan = build_machine_memory_repair_plan(tmp_path, {})
        planner_state = plan["planner_state"]
        assert planner_state["pending_proposals"] == []
        assert planner_state["priority_queue"] == []
        assert planner_state["counts"] == {
            "pending_proposals": 0,
            "blocked": 0,
            "unblocked": 0,
            "executed_actions": 0,
        }

    def test_corrupt_planner_state_falls_back_to_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / ".aiwiki" / "state" / "planner-state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")
        plan = build_machine_memory_repair_plan(tmp_path, {})
        planner_state = plan["planner_state"]
        assert planner_state["executed_actions"] == []
        assert planner_state["counts"]["pending_proposals"] == 0
        assert plan["counts"]["blocked_proposals"] == 0

    def test_valid_previous_planner_state_preserved_but_counts_reset(self, tmp_path: Path) -> None:
        _write_planner_state(
            tmp_path,
            _valid_planner_document(
                pending_proposals=[{"action_id": "old"}],
                priority_queue=[{"item_id": "proposal:old"}],
                executed_actions=[{"action_id": "done-1"}],
                counts={"pending_proposals": 3, "blocked": 1, "unblocked": 2, "executed_actions": 1},
            ),
        )
        plan = build_machine_memory_repair_plan(tmp_path, {})
        planner_state = plan["planner_state"]
        # Executed history survives; pending queue is rebuilt empty.
        assert planner_state["executed_actions"] == [{"action_id": "done-1"}]
        assert planner_state["pending_proposals"] == []
        assert planner_state["priority_queue"] == []
        assert planner_state["counts"]["executed_actions"] == 1
        assert planner_state["counts"]["pending_proposals"] == 0
        assert planner_state["counts"]["blocked"] == 0
        assert planner_state["counts"]["unblocked"] == 0


# ---------------------------------------------------------------------------
# execution.repair_plan — build_planner_state
# ---------------------------------------------------------------------------


class TestBuildPlannerState:
    def test_empty_proposals(self, tmp_path: Path) -> None:
        state = build_planner_state(tmp_path, [])
        assert state["version"] == 1
        assert state["state_path"] == ".aiwiki/state/planner-state.json"
        assert state["active_protocol"] == "general"
        assert state["generated_at"]
        assert state["pending_proposals"] == []
        assert state["priority_queue"] == []
        assert state["dependency_graph"] == {"nodes": [], "edges": []}
        assert state["next_action"] == {}
        assert state["counts"] == {"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 0}

    def test_blocked_and_auto_bundle_flags(self, tmp_path: Path) -> None:
        proposals = [
            {"action_id": "a", "risk": "low", "status": "accepted", "priority_score": 10},
            {"action_id": "b", "risk": "high", "status": "proposed", "depends_on": ["a"]},
        ]
        state = build_planner_state(tmp_path, proposals)
        records = {item["action_id"]: item for item in state["pending_proposals"]}
        assert records["a"]["blocked"] is False
        assert records["a"]["auto_bundle_candidate"] is True
        assert records["a"]["human_required"] is False
        assert records["b"]["blocked"] is True
        assert records["b"]["auto_bundle_candidate"] is False
        assert records["b"]["human_required"] is True
        # Unblocked items sort first; next_action is the queue head.
        assert state["next_action"]["item_id"] == "proposal:a"
        assert state["next_action"]["item_kind"] == "execution-proposal"
        assert state["next_action"]["protocol"] == "general"
        assert state["counts"] == {"pending_proposals": 2, "blocked": 1, "unblocked": 1, "executed_actions": 0}
        # Dependency graph mirrors depends_on edges.
        assert state["dependency_graph"]["edges"] == [{"from": "b", "to": "a"}]
        assert len(state["dependency_graph"]["nodes"]) == 2

    def test_queue_orders_by_priority_score_within_unblocked(self, tmp_path: Path) -> None:
        proposals = [
            {"action_id": "low", "priority_score": 5, "priority": "high"},
            {"action_id": "high", "priority_score": 50, "priority": "low"},
        ]
        state = build_planner_state(tmp_path, proposals)
        assert [item["action_id"] for item in state["priority_queue"]] == ["high", "low"]

    def test_caps_on_queue_nodes_edges_and_executed(self, tmp_path: Path) -> None:
        proposals = [{"action_id": f"p{index}"} for index in range(17)]
        proposals.append({"action_id": "blocked", "depends_on": [f"dep{index}" for index in range(25)]})
        _write_planner_state(
            tmp_path,
            _valid_planner_document(
                executed_actions=[{"action_id": f"done-{index}"} for index in range(17)],
                counts={"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 17},
            ),
        )
        state = build_planner_state(tmp_path, proposals)
        assert state["counts"]["pending_proposals"] == 18
        assert len(state["priority_queue"]) == 12
        assert len(state["dependency_graph"]["nodes"]) == 16
        assert len(state["dependency_graph"]["edges"]) == 24
        assert len(state["executed_actions"]) == 16
        assert state["counts"]["executed_actions"] == 17

    def test_corrupt_previous_state_uses_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / ".aiwiki" / "state" / "planner-state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")
        state = build_planner_state(tmp_path, [{"action_id": "a"}])
        assert state["executed_actions"] == []
        assert state["counts"]["pending_proposals"] == 1


# ---------------------------------------------------------------------------
# execution.repair_plan — repair_execution_proposals
# ---------------------------------------------------------------------------


class TestRepairExecutionProposals:
    def test_empty_actions_returns_empty_list(self, tmp_path: Path) -> None:
        assert repair_execution_proposals(tmp_path, []) == []

    def test_known_kind_uses_strategy_template(self, tmp_path: Path) -> None:
        actions = [
            {
                "id": "a1",
                "kind": "connect-isolated-source",
                "status": "proposed",
                "priority": "medium",
                "title": "Connect source",
                "primary_path": "wiki/sources/x.md",
                "source_ids": [7, "s1"],
            }
        ]
        proposals = repair_execution_proposals(tmp_path, actions)
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal["id"] == "proposal-a1"
        assert proposal["action_id"] == "a1"
        assert proposal["proposal_kind"] == "connect-source"
        assert proposal["risk"] == "medium"
        assert proposal["summary"].startswith("把孤立来源接入至少一个稳定概念")
        assert len(proposal["suggested_edits"]) == 3
        assert proposal["target_paths"] == ["wiki/sources/x.md"]
        # Non-string source ids are filtered out.
        assert proposal["source_ids"] == ["s1"]
        assert proposal["proposal_path"] == "wiki/execution-proposals/a1.md"
        assert proposal["bundle_path"] == ".aiwiki/state/execution-bundles/a1.json"
        # Monitor kinds get an acknowledge-and-close preview without disk access.
        assert proposal["safe_apply_preview"]["apply_mode"] == "resolve-monitor"
        assert proposal["rollback_summary"] == "回滚时需要人工恢复目标页，然后重跑 compile。"
        assert proposal["apply_ready"] == "false"
        # Patch plan covers the primary page plus the kind's auxiliary index.
        patch_paths = [entry["path"] for entry in proposal["page_patch_plan"]]
        assert patch_paths == ["wiki/sources/x.md", "wiki/indexes/concepts.md"]

    def test_unknown_kind_falls_back_to_manual_repair(self, tmp_path: Path) -> None:
        actions = [{"id": "a9", "kind": "mystery", "reason": "Because reasons"}]
        proposal = repair_execution_proposals(tmp_path, actions)[0]
        assert proposal["proposal_kind"] == "manual-repair"
        assert proposal["risk"] == "medium"
        assert proposal["summary"] == "Because reasons"
        assert proposal["suggested_edits"] == ["Because reasons"]
        assert proposal["target_paths"] == []
        assert proposal["safe_apply_preview"] is None
        assert proposal["rollback_summary"] == "回滚时需要人工恢复目标页，然后重跑 compile。"

    def test_unknown_kind_without_reason_uses_default_edit(self, tmp_path: Path) -> None:
        proposal = repair_execution_proposals(tmp_path, [{"id": "a9", "kind": "mystery"}])[0]
        assert proposal["summary"] == ""
        assert proposal["suggested_edits"] == ["检查相关页面并补修复说明。"]

    def test_refresh_citation_snapshots_preview(self, tmp_path: Path) -> None:
        (tmp_path / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
        (tmp_path / "raw" / "inbox" / "evidence.md").write_text("evidence\n", encoding="utf-8")
        _write_page(
            tmp_path,
            "wiki/judgments/j1.md",
            {"kind": "judgment", "title": "J1", "citations": ["raw/inbox/evidence.md"]},
        )
        action = {
            "id": "a2",
            "kind": "refresh-citation-snapshots",
            "status": "accepted",
            "active": True,
            "primary_path": "wiki/judgments/j1.md",
            "policy_decision": "allow",
            "execution_band": "bundle-safe-apply",
        }
        proposal = repair_execution_proposals(tmp_path, [action])[0]
        assert proposal["proposal_kind"] == "refresh-snapshots"
        assert proposal["risk"] == "low"
        preview = proposal["safe_apply_preview"]
        assert preview["apply_mode"] == "citation-snapshot-refresh"
        assert preview["page_path"] == "wiki/judgments/j1.md"
        assert len(preview["updated_citation_snapshots"]) == 1
        assert preview["updated_citation_snapshots"][0].startswith("raw/inbox/evidence.md#")
        assert proposal["rollback_summary"] == "恢复之前的 citation_snapshots metadata 并重跑 compile。"
        # The refresh template patches the judgment page itself (role "other").
        assert [entry["path"] for entry in proposal["page_patch_plan"]] == ["wiki/judgments/j1.md"]
        assert proposal["page_patch_plan"][0]["mode"] == "semi-auto-apply"

    def test_refresh_citation_snapshots_without_citations_has_no_preview(self, tmp_path: Path) -> None:
        _write_page(tmp_path, "wiki/judgments/j1.md", {"kind": "judgment", "title": "J1"})
        action = {
            "id": "a2",
            "kind": "refresh-citation-snapshots",
            "status": "accepted",
            "active": True,
            "primary_path": "wiki/judgments/j1.md",
        }
        proposal = repair_execution_proposals(tmp_path, [action])[0]
        assert proposal["safe_apply_preview"] is None

    def test_manual_link_state_preview_with_valid_targets(self, tmp_path: Path) -> None:
        _low_risk_link_vault(tmp_path)
        proposal = repair_execution_proposals(tmp_path, [_low_risk_link_action()])[0]
        assert proposal["proposal_kind"] == "cross-link"
        assert proposal["risk"] == "low"
        preview = proposal["safe_apply_preview"]
        assert preview["apply_mode"] == "manual-link-state"
        assert preview["entry"]["source_id"] == "source-alpha"
        assert preview["entry"]["concept_slug"] == "beta"
        assert proposal["rollback_summary"] == "禁用对应的 manual-link state 条目并重跑 compile。"
        patch_paths = [entry["path"] for entry in proposal["page_patch_plan"]]
        assert patch_paths[-1] == ".aiwiki/state/manual-links.json"

    def test_priority_score_composition(self, tmp_path: Path) -> None:
        action = {
            "id": "a3",
            "kind": "connect-isolated-source",
            "status": "accepted",
            "priority": "high",
            "policy_decision": "allow",
            "execution_band": "bundle-safe-apply",
            "focus_score": 2,
            "occurrences": 1,
            "primary_path": "wiki/sources/x.md",
        }
        proposal = repair_execution_proposals(tmp_path, [action])[0]
        # impact = 55 (high) + 6 (focus 2*3) + 2 (occ 1*2) + 10 (accepted) + 6 (allow) = 79
        assert proposal["impact_score"] == 79
        # priority = 79 + 16 (accepted) + 8 (allow) + 6 (bundle-safe-apply) = 109
        assert proposal["priority_score"] == 109

    def test_dependencies_penalize_score_and_sort_blocked_last(self, tmp_path: Path) -> None:
        actions = [
            {
                "id": "low",
                "kind": "add-source-concept-link",
                "status": "proposed",
                "priority": "medium",
                "title": "Link",
                "primary_path": "wiki/sources/s.md",
                "source_ids": ["s1"],
                "concept_slugs": ["c1"],
            },
            {
                "id": "high",
                "kind": "split-overloaded-concept",
                "status": "proposed",
                "priority": "medium",
                "title": "Split",
                "primary_path": "wiki/concepts/c1.md",
                "concept_slugs": ["c1"],
            },
        ]
        proposals = repair_execution_proposals(tmp_path, actions)
        # cross-link (rank 2) overlaps split-concept (rank 5) via concept_slugs,
        # so the lower-weight proposal depends on the higher-weight one.
        by_id = {proposal["action_id"]: proposal for proposal in proposals}
        assert by_id["low"]["depends_on"] == ["high"]
        assert by_id["high"]["depends_on"] == []
        # Base score 35 (impact) + 8 (proposed) = 43; dependency penalty -4.
        assert by_id["low"]["priority_score"] == 39
        assert by_id["high"]["priority_score"] == 43
        # Blocked proposals sort after unblocked ones.
        assert [proposal["action_id"] for proposal in proposals] == ["high", "low"]

    def test_status_rank_sorts_before_priority_score(self, tmp_path: Path) -> None:
        actions = [
            {
                "id": "accepted",
                "kind": "connect-isolated-source",
                "status": "accepted",
                "priority": "high",
                "primary_path": "wiki/sources/a.md",
            },
            {
                "id": "proposed",
                "kind": "connect-isolated-source",
                "status": "proposed",
                "priority": "low",
                "primary_path": "wiki/sources/b.md",
            },
        ]
        proposals = repair_execution_proposals(tmp_path, actions)
        # proposed (status rank 0) sorts ahead of accepted (rank 1) despite the
        # accepted proposal's higher priority_score.
        assert [proposal["action_id"] for proposal in proposals] == ["proposed", "accepted"]

    def test_proposals_capped_at_sixteen(self, tmp_path: Path) -> None:
        actions = [
            {"id": f"a{index}", "kind": "connect-isolated-source", "primary_path": f"wiki/sources/s{index}.md"}
            for index in range(17)
        ]
        proposals = repair_execution_proposals(tmp_path, actions)
        assert len(proposals) == 16
