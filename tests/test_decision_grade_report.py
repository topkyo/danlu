"""R97 + R98.1: Decision-grade Report skeleton & bullet-minimum validation.

Covers `_validate_output_markdown` report-format extension:
- 6-section fixed order (R97)
- per-section minimum `- ` bullet counts (R98.1)
- strict rejection of `_LLM:` placeholder residue (R98.1)
- `render_report` skeleton structure (skeleton-only, does NOT pass filled validator)
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki.app_queries import render_report
from aiwiki.runner.prompts import (
    _REPORT_REQUIRED_SECTIONS,
    _REPORT_SECTION_BULLET_MINIMUMS,
    _validate_output_markdown,
)

_GOOD_REPORT_BODY = """---
format: report
---

# Q

## 结论
答案。

## 关键证据
- 见 wiki/sources/source-1.md
- 第二条证据。
- 第三条证据。

## 反证与不确定性
- 未发现明显反证。

## 行动建议
- 下一步：复核 X。

## 下次观察信号
- 当 Y 出现时复审。

## 引用
- wiki/sources/source-1.md
"""


class DecisionGradeReportValidatorTests(unittest.TestCase):
    def test_all_six_sections_in_order_passes(self) -> None:
        _validate_output_markdown(_GOOD_REPORT_BODY, "report", ["source-1"])

    def test_missing_counter_evidence_section_raises_with_name(self) -> None:
        bad = _GOOD_REPORT_BODY.replace("## 反证与不确定性\n- 未发现明显反证。\n\n", "")
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 反证与不确定性", str(ctx.exception))

    def test_missing_conclusion_section_raises(self) -> None:
        bad = _GOOD_REPORT_BODY.replace("## 结论\n答案。\n\n", "")
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 结论", str(ctx.exception))

    def test_missing_citations_section_raises(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 引用\n- wiki/sources/source-1.md\n", ""
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 引用", str(ctx.exception))

    def test_out_of_order_sections_raises(self) -> None:
        # Swap 行动建议 before 关键证据
        bad = """---
format: report
---

# Q

## 结论
答案。

## 行动建议
- 下一步：复核 X。

## 关键证据
- 见 wiki/sources/source-1.md
- 第二条证据。
- 第三条证据。

## 反证与不确定性
- 未发现明显反证。

## 下次观察信号
- 当 Y 出现时复审。

## 引用
- wiki/sources/source-1.md
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("Report missing required section", str(ctx.exception))

    def test_no_frontmatter_still_raises_original_error(self) -> None:
        bad = _GOOD_REPORT_BODY.replace("---\nformat: report\n---\n\n", "")
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("frontmatter", str(ctx.exception))

    def test_missing_wiki_sources_citation_still_raises(self) -> None:
        bad = _GOOD_REPORT_BODY.replace("wiki/sources/source-1.md", "elsewhere.md")
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("citations", str(ctx.exception))

    def test_non_report_formats_skip_section_check(self) -> None:
        # decision-memo / sop / figure / slides 只受原有 frontmatter / citation 约束
        minimal = "---\nformat: decision-memo\n---\n\nSee wiki/sources/source-1.md\n"
        _validate_output_markdown(minimal, "decision-memo", ["source-1"])
        _validate_output_markdown(minimal, "sop", ["source-1"])
        _validate_output_markdown(minimal, "figure", ["source-1"])
        slides_minimal = "anything with wiki/sources/source-1.md inside\n"
        _validate_output_markdown(slides_minimal, "slides", ["source-1"])

    def test_render_report_skeleton_has_required_sections_in_order(self) -> None:
        """R98.1 改语义：render_report skeleton 含 `_LLM:` 故 NOT pass filled validator；
        本测试只断言 skeleton 结构（6 个必填 H2 顺序正确）。
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            protocol_state = {"active_protocol": "general"}
            entries = [{"id": "source-1", "title": "Sample Source"}]
            concepts: list[dict] = []
            machine_query: dict = {}
            output = render_report(
                root,
                question="What should we do?",
                entries=entries,
                concepts=concepts,
                machine_query=machine_query,
                protocol_state=protocol_state,
                created_at="2026-05-11T00:00:00Z",
                artifact_id="test-id",
            )
            # Local fence-aware H2 scan
            h2_titles: list[str] = []
            in_fence = False
            for line in output.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                if line.startswith("## ") and not line.startswith("### "):
                    h2_titles.append(line.strip())
            cursor = 0
            for heading in _REPORT_REQUIRED_SECTIONS:
                self.assertIn(heading, h2_titles[cursor:],
                              f"Skeleton missing or out-of-order section: {heading}")
                cursor = h2_titles.index(heading, cursor) + 1
            # Skeleton MUST contain at least one `_LLM:` hint line (otherwise
            # there is no placeholder for LLM to fill).
            self.assertIn("_LLM:", output)

    def test_required_sections_constant_is_tuple_of_six(self) -> None:
        self.assertEqual(len(_REPORT_REQUIRED_SECTIONS), 6)
        self.assertEqual(_REPORT_REQUIRED_SECTIONS[0], "## 结论")
        self.assertEqual(_REPORT_REQUIRED_SECTIONS[-1], "## 引用")

    def test_inline_body_match_does_not_satisfy_section(self) -> None:
        """正文中出现 `这里讨论 ## 结论 的写法` 不能算作 H2。"""
        bad = _GOOD_REPORT_BODY.replace(
            "## 结论\n答案。\n", "正文中提到 ## 结论 这种写法。\n"
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 结论", str(ctx.exception))

    def test_fenced_code_block_match_does_not_satisfy_section(self) -> None:
        """fenced code block 内的 `## 结论` 不能算作真实 H2。"""
        bad = """---
format: report
---

# Q

```markdown
## 结论
## 关键证据
## 反证与不确定性
## 行动建议
## 下次观察信号
## 引用
```

正文里其实没有任何 H2，仅引用了一段 wiki/sources/source-1.md。
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 结论", str(ctx.exception))

    def test_lookalike_longer_heading_does_not_satisfy_section(self) -> None:
        """`## 结论补充` 不能冒充 `## 结论`。"""
        bad = _GOOD_REPORT_BODY.replace("## 结论\n答案。\n", "## 结论补充\n说明。\n")
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("## 结论", str(ctx.exception))

    # ---- R98.1 new tests ----

    def test_bullet_minimums_constant_locks_in_contract(self) -> None:
        self.assertEqual(_REPORT_SECTION_BULLET_MINIMUMS["## 关键证据"], 3)
        self.assertEqual(_REPORT_SECTION_BULLET_MINIMUMS["## 反证与不确定性"], 1)
        self.assertEqual(_REPORT_SECTION_BULLET_MINIMUMS["## 行动建议"], 1)
        self.assertEqual(_REPORT_SECTION_BULLET_MINIMUMS["## 下次观察信号"], 1)
        self.assertEqual(_REPORT_SECTION_BULLET_MINIMUMS["## 引用"], 1)
        # 结论 deliberately excluded — it's a paragraph, not a bullet list.
        self.assertNotIn("## 结论", _REPORT_SECTION_BULLET_MINIMUMS)

    def test_key_evidence_with_only_two_bullets_raises_with_counts(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 关键证据\n- 见 wiki/sources/source-1.md\n- 第二条证据。\n- 第三条证据。\n",
            "## 关键证据\n- 见 wiki/sources/source-1.md\n- 第二条证据。\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 关键证据", msg)
        self.assertIn("at least 3", msg)
        self.assertIn("found 2", msg)

    def test_counter_evidence_with_zero_bullets_raises(self) -> None:
        # Section heading present but body is prose with no `- ` bullet.
        bad = _GOOD_REPORT_BODY.replace(
            "## 反证与不确定性\n- 未发现明显反证。\n",
            "## 反证与不确定性\n本节为散文，没有 bullet。\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 反证与不确定性", msg)
        self.assertIn("found 0", msg)

    def test_numbered_list_does_not_count_as_bullet(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 行动建议\n- 下一步：复核 X。\n",
            "## 行动建议\n1. 下一步：复核 X。\n2. 跟进 Y。\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 行动建议", msg)
        self.assertIn("found 0", msg)

    def test_subbullet_does_not_count_toward_parent_section(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 下次观察信号\n- 当 Y 出现时复审。\n",
            "## 下次观察信号\n  - 缩进的 sub-bullet。\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 下次观察信号", msg)
        self.assertIn("found 0", msg)

    def test_fenced_code_block_bullets_do_not_count(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 关键证据\n- 见 wiki/sources/source-1.md\n- 第二条证据。\n- 第三条证据。\n",
            "## 关键证据\n```\n- 假的 bullet 1\n- 假的 bullet 2\n- 假的 bullet 3\n```\n"
            "- 见 wiki/sources/source-1.md\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 关键证据", msg)
        self.assertIn("found 1", msg)

    def test_unfilled_llm_placeholder_marker_is_rejected(self) -> None:
        bad = _GOOD_REPORT_BODY.replace(
            "## 行动建议\n- 下一步：复核 X。\n",
            "## 行动建议\n_LLM: 请在此填入具体行动。_\n- 下一步：复核 X。\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        self.assertIn("_LLM:", str(ctx.exception))

    def test_llm_marker_inside_fenced_code_block_is_allowed(self) -> None:
        """fence 内的 `_LLM:` 是文档说明，不算残留。"""
        ok = _GOOD_REPORT_BODY.replace(
            "## 结论\n答案。\n",
            "## 结论\n答案。\n\n```\n_LLM: 这是文档说明里展示的占位符样例。_\n```\n",
        )
        # 应不抛
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_empty_dash_line_does_not_count_as_bullet(self) -> None:
        # 保留正文中其他 wiki/sources 引用，避免被 citation 检查先吃掉；
        # 让失败精确归因到 ## 引用 段 bullet count = 0。
        bad = _GOOD_REPORT_BODY.replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n-   \n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("## 引用", msg)
        self.assertIn("found 0", msg)


def load_tests(loader, standard_tests, pattern):  # noqa: ARG001
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(DecisionGradeReportValidatorTests))
    return suite


if __name__ == "__main__":
    unittest.main()
