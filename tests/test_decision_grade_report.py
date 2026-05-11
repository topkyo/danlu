"""R97: Decision-grade Report skeleton validation tests.

Covers `_validate_output_markdown` report-format extension and
`render_report` self-roundtrip through the new validator.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki.app_queries import render_report
from aiwiki.runner.prompts import (
    _REPORT_REQUIRED_SECTIONS,
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

## 反证与不确定性
- 未发现明显反证。

## 下次观察信号
- 当 Y 出现时复审。

## 引用
- wiki/sources/source-1.md
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        # 乱序时，扫到 关键证据 仍找不到（因为它出现在 行动建议 之前的 cursor 已超过）
        # 触发的具体缺失 section 是排在 行动建议 之后的某一个
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
        # slides 不在 frontmatter-required 集合中，且本来就不做新增检查
        slides_minimal = "anything with wiki/sources/source-1.md inside\n"
        _validate_output_markdown(slides_minimal, "slides", ["source-1"])

    def test_render_report_self_roundtrip_passes_validator(self) -> None:
        """render_report() 产生的 placeholder skeleton 必须自身合规。"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 最小 protocol_state，仅满足 active_protocol 字段
            protocol_state = {"active_protocol": "general"}
            entries = [
                {"id": "source-1", "title": "Sample Source"},
            ]
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
            # render_report 输出含 wiki/sources/source-1.md（来自 compact_source_link_lines）
            _validate_output_markdown(output, "report", ["source-1"])

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


def load_tests(loader, standard_tests, pattern):  # noqa: ARG001
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(DecisionGradeReportValidatorTests))
    return suite


if __name__ == "__main__":
    unittest.main()
