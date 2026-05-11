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

    # ---- R98.2: citation integrity ----

    def test_r982_multi_citation_passes(self) -> None:
        """body 引用两个 source；## 引用 列出两条，各一次 → 通过。"""
        ok = _GOOD_REPORT_BODY.replace(
            "- 见 wiki/sources/source-1.md\n- 第二条证据。\n- 第三条证据。",
            "- 见 wiki/sources/source-1.md\n- 见 wiki/sources/source-2.md\n- 第三条证据。",
        ).replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n- wiki/sources/source-1.md\n- wiki/sources/source-2.md\n",
        )
        _validate_output_markdown(ok, "report", ["source-1", "source-2"])

    def test_r982_body_repeats_same_citation_passes(self) -> None:
        """body 在不同 section 重复同一引用；## 引用 单条 → 通过（body 侧重复允许）。"""
        ok = _GOOD_REPORT_BODY.replace(
            "- 当 Y 出现时复审。",
            "- 当 Y 出现时复审 wiki/sources/source-1.md 的更新。",
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r982_fenced_body_citation_excluded(self) -> None:
        """body 的 fenced code block 内出现引用，## 引用 未列；fence-aware 应跳过 → 通过。"""
        ok = _GOOD_REPORT_BODY.replace(
            "答案。",
            "答案。\n\n```\n参考片段：wiki/sources/source-99.md\n```",
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r982_skeleton_layout_with_extra_reference_section_passes(self) -> None:
        """模拟真实 skeleton layout：## 引用 后跟 ## 参考；## 参考 含 source paths。
        Phase 4 必须只在 ## 引用 → 下一个 H2 之间检查，不把 ## 参考 当作 citation。"""
        ok = _GOOD_REPORT_BODY + (
            "\n## 参考\n"
            "- 当前协议：investing\n"
            "- wiki/sources/source-z.md  # 由 compact_source_link_lines 渲染\n"
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r982_unusual_filename_chars_pass(self) -> None:
        """文件名含 dot/dash/underscore/digit → regex 应匹配。"""
        ok = _GOOD_REPORT_BODY.replace(
            "- 见 wiki/sources/source-1.md",
            "- 见 wiki/sources/a.v2-3_foo.md",
        ).replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n- wiki/sources/a.v2-3_foo.md\n",
        )
        _validate_output_markdown(ok, "report", ["a.v2-3_foo"])

    def test_r982_reference_section_duplicate_does_not_trigger_dedup(self) -> None:
        """## 参考 内出现同一路径多次；## 引用 内仅一次 → dedup 应只看 ## 引用 → 通过。"""
        ok = _GOOD_REPORT_BODY + (
            "\n## 参考\n"
            "- wiki/sources/source-z.md\n"
            "- wiki/sources/source-z.md\n"
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r982_duplicate_in_citations_rejects(self) -> None:
        """## 引用 列出 source-1 两次 → 拒绝；错误消息含路径。"""
        bad = _GOOD_REPORT_BODY.replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n- wiki/sources/source-1.md\n- wiki/sources/source-1.md\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("duplicate", msg)
        self.assertIn("wiki/sources/source-1.md", msg)

    def test_r982_body_path_missing_from_citations_rejects(self) -> None:
        """body 引用 source-2，## 引用 仅含 source-1 → 拒绝；错误消息指 source-2。"""
        bad = _GOOD_REPORT_BODY.replace(
            "- 第二条证据。",
            "- 见 wiki/sources/source-2.md",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1", "source-2"])
        msg = str(ctx.exception)
        self.assertIn("## 引用", msg)
        self.assertIn("wiki/sources/source-2.md", msg)

    def test_r982_first_missing_path_in_body_order(self) -> None:
        """body 引用 source-1 和 source-2；## 引用 列 source-1 和 source-3 →
        缺 source-2，错误指明 source-2（按 body 出现顺序）。"""
        bad = _GOOD_REPORT_BODY.replace(
            "- 第二条证据。",
            "- 见 wiki/sources/source-2.md",
        ).replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n- wiki/sources/source-1.md\n- wiki/sources/source-3.md\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1", "source-2", "source-3"])
        msg = str(ctx.exception)
        self.assertIn("wiki/sources/source-2.md", msg)

    def test_r982_body_citation_in_last_signal_section_caught(self) -> None:
        """body 引用紧贴 ## 引用 前（## 下次观察信号 末尾 bullet），## 引用 未列 → 拒绝。"""
        bad = _GOOD_REPORT_BODY.replace(
            "- 当 Y 出现时复审。",
            "- 当 wiki/sources/source-77.md 出现新数据时复审。",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1", "source-77"])
        msg = str(ctx.exception)
        self.assertIn("wiki/sources/source-77.md", msg)

    def test_r982_reference_section_path_not_in_citations_passes_when_body_clean(
        self,
    ) -> None:
        """## 参考 含 body 未提及的 path → 不应触发 subset error
        （证明 body slice 严格止于 ## 引用 之前，且 ## 参考 不算 body）。"""
        ok = _GOOD_REPORT_BODY + (
            "\n## 参考\n"
            "- wiki/sources/source-x.md\n"
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r982_stray_duplicate_citations_heading_before_conclusion_not_bypassed(
        self,
    ) -> None:
        """对抗 layout：在 ## 结论 之前出现 stray ## 引用 (含某路径)，真正按序
        匹配到的 ## 引用 在末尾且为空。R98.2 原本由 Phase 4 subset check 捕获；
        R98.3 起 Phase 1.5 在更早阶段直接拒绝任何重复 required H2，所以本输入
        现在落在 duplicate-section 错误上。场景仍被守住，只是更早 + 更具体。"""
        adversarial = """---
format: report
---

# Q

## 引用
- wiki/sources/source-2.md

## 结论
答案。

## 关键证据
- 见 wiki/sources/source-2.md
- 第二条。
- 第三条。

## 反证与不确定性
- 无。

## 行动建议
- 复核。

## 下次观察信号
- 当 Y。

## 引用
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(adversarial, "report", ["source-2"])
        msg = str(ctx.exception)
        # R98.3：duplicate required section 在 Phase 1.5 被显式拒绝
        self.assertIn("duplicate required section", msg)
        self.assertIn("## 引用", msg)

    # ---- R98.3: strictness hardening (deferred notes from R98.1/R98.2) ----

    def test_r983_duplicate_conclusion_section_rejects(self) -> None:
        """两个 ## 结论 H2 → Phase 1.5 拒绝。"""
        bad = _GOOD_REPORT_BODY.replace(
            "## 关键证据\n- 见 wiki/sources/source-1.md",
            "## 结论\n再来一段。\n\n## 关键证据\n- 见 wiki/sources/source-1.md",
        )
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("duplicate required section", msg)
        self.assertIn("## 结论", msg)

    def test_r983_duplicate_non_required_heading_passes(self) -> None:
        """重复的非 required H2 (如重复 ## 参考) 不应被拒绝；
        Phase 1.5 只锁定 _REPORT_REQUIRED_SECTIONS 范围。"""
        ok = _GOOD_REPORT_BODY + (
            "\n## 参考\n"
            "- 第一段参考\n"
            "\n## 参考\n"
            "- 第二段参考\n"
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r983_closed_fence_in_body_still_passes(self) -> None:
        """带闭合 fence 的正常 body 仍通过 → 锁定 Phase 0 不误伤合规 fence。

        fence 内包含 `## 结论` 这种 H2-looking 行 + `_LLM:` 占位串，验证
        fence-aware 扫描会跳过 fence 内文本，因此既不会被 Phase 1.5 当成
        duplicate required H2，也不会被 Phase 2 当成未填充占位。
        """
        ok = _GOOD_REPORT_BODY.replace(
            "答案。",
            "答案。\n\n```\n## 结论\n演示代码片段\n_LLM: 这里在 fence 内是合法的_\n```",
        )
        _validate_output_markdown(ok, "report", ["source-1"])

    def test_r983_unclosed_triple_backtick_fence_rejects(self) -> None:
        """`` ``` `` 开启后未闭合 → Phase 0 拒绝。
        markdown 顶部塞 wiki/sources 字符串以绕过 _validate_output_markdown 的
        precheck，让失败精确归因到 _validate_report_sections Phase 0。"""
        bad = """---
format: report
---

# Q (wiki/sources/source-1.md)

```
unclosed fence opens here

## 结论
答案。

## 关键证据
- one
- two
- three
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("unclosed fenced code block", msg)

    def test_r983_unclosed_tilde_fence_rejects(self) -> None:
        """`` ~~~ `` 开启后未闭合 → Phase 0 同样拒绝（toggle 语义与 ``` 一致）。"""
        bad = """---
format: report
---

# Q (wiki/sources/source-1.md)

## 结论
答案。

~~~
unclosed tilde fence
"""
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "report", ["source-1"])
        msg = str(ctx.exception)
        self.assertIn("unclosed fenced code block", msg)


def load_tests(loader, standard_tests, pattern):  # noqa: ARG001
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(DecisionGradeReportValidatorTests))
    return suite


if __name__ == "__main__":
    unittest.main()
