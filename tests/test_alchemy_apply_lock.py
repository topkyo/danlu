"""R92-ALCHEMY-LOCK-TX: alchemy apply / auto / lane writers must hold runtime_write_lock.

Covers:
- 7 顶层 apply / auto / lane 入口必须在主体执行前持有 runtime_write_lock
- reentrant 嵌套 (lane apply 内嵌 primitive apply) 不 deadlock
- receipt JSON 写入失败时不留半文件 (atomic_write_text 语义)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_utils import _RUNTIME_LOCKS, runtime_write_lock


class AlchemyApplyLockTests(unittest.TestCase):
    """每个顶层 apply / auto / lane 入口必须在主体逻辑运行前持有 runtime_write_lock。

    策略：patch 入口在主体最早期调用的 helper（preview / kill switch / scheduler 入口），
    在 patch side-effect 内断言 _RUNTIME_LOCKS depth >= 1，然后让 helper 抛 short-circuit
    异常以避免触发完整下游流程。这种模式与 tests/test_auto_adopt_lock.py 一致。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _assert_lock_held(self, *_args: object, **_kwargs: object) -> None:
        state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
        self.assertIsNotNone(state, "runtime_write_lock not held")
        self.assertGreaterEqual(int(state.get("depth", 0)), 1)
        raise RuntimeError("short-circuit after lock probe")

    def test_run_alchemy_judge_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_judge_apply

        with patch("aiwiki.runner.alchemy.run_alchemy_judge_preview", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_judge_apply(self.root, scope="all")

    def test_run_alchemy_judge_proposal_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_judge_proposal_apply

        with patch(
            "aiwiki.runner.alchemy._resolve_alchemy_judge_proposal_path",
            side_effect=self._assert_lock_held,
        ):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_judge_proposal_apply(self.root, "dummy-proposal")

    def test_run_alchemy_distill_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_distill_apply

        with patch("aiwiki.runner.alchemy.run_alchemy_distill_preview", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_distill_apply(self.root, scope="all")

    def test_run_alchemy_review_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_review_apply

        with patch("aiwiki.runner.alchemy.run_alchemy_review_preview", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_review_apply(self.root, scope="all")

    def test_run_alchemy_propose_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_propose_apply

        with patch("aiwiki.autonomy_policy.disabled_reason", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_propose_apply(self.root, scope="all")

    def test_run_alchemy_lane_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_lane_apply

        with patch("aiwiki.autonomy_policy.disabled_reason", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_lane_apply(
                    self.root,
                    lane="heavy",
                    scope="all",
                    action_ids=["dummy-id"],
                )

    def test_run_alchemy_auto_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_auto

        with patch("aiwiki.runner.alchemy._normalize_auto_lanes", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_auto(self.root, apply=False)


class AlchemyApplyReentrantLockTests(unittest.TestCase):
    """runtime_write_lock 是 reentrant —— 已持有 lock 的 caller 调入 apply 入口不应 deadlock。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_judge_apply_reentrant_under_existing_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_judge_apply

        observed_depth: list[int] = []

        def probe(*_args: object, **_kwargs: object) -> None:
            state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
            observed_depth.append(int(state["depth"]) if state else 0)
            raise RuntimeError("short-circuit")

        with runtime_write_lock(self.root):
            outer_state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
            self.assertEqual(int(outer_state["depth"]), 1)

            with patch("aiwiki.runner.alchemy.run_alchemy_judge_preview", side_effect=probe):
                with self.assertRaisesRegex(RuntimeError, "short-circuit"):
                    run_alchemy_judge_apply(self.root, scope="all")

            # 嵌套调用进入应观测到 depth=2，未死锁
            self.assertEqual(observed_depth, [2])
            # 嵌套退出后 depth 应回到 1
            recovered_state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
            self.assertEqual(int(recovered_state["depth"]), 1)


class AlchemyReceiptAtomicWriteTests(unittest.TestCase):
    """alchemy apply receipt 写入应使用 atomic_write_text 语义：失败时不留半文件。

    atomic_write_text 实现：写到 path.tmp → fsync → rename(path)。失败时清理 tmp，
    确保 path 不存在。这里通过 unit-level 直接测试 atomic_write_text 的失败语义，
    并用 grep 校验 alchemy.py 中所有 alchemy apply receipt 写入都通过 atomic_write_text。
    """

    def test_atomic_write_text_failure_leaves_no_partial_file(self) -> None:
        from aiwiki.app_utils import atomic_write_text

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "receipt.json"

            with patch("os.replace", side_effect=OSError("simulated rename failure")):
                with self.assertRaises(OSError):
                    atomic_write_text(target, '{"hello": "world"}\n')

            # 半文件不存在
            self.assertFalse(target.exists())
            # tmp 也已清理
            self.assertFalse(any(p.name.endswith(".tmp") for p in Path(tmp).iterdir()))

    def test_alchemy_module_uses_atomic_write_text_for_receipts(self) -> None:
        """grep 守门：alchemy.py 中不应再有裸 receipt JSON 路径上的 `.write_text(json.dumps(...)`。

        泛化匹配：扫所有形如 ``<expr>.write_text(json.dumps(`` 的字面，且 expr 名带 ``receipt``，
        而非依赖固定变量名 ``receipt_path``。同时保留对原有变量名的精确守门，作回归 floor。
        """
        import re

        from aiwiki.runner import alchemy

        source = Path(alchemy.__file__).read_text(encoding="utf-8")

        # 精确守门（R92 原始 guard floor）
        self.assertNotIn(
            'receipt_path.write_text(json.dumps(',
            source,
            "alchemy receipt 必须使用 atomic_write_text；发现裸 receipt_path.write_text 残留",
        )

        # 泛化守门：任何 receipt-like 变量上的裸 write_text(json.dumps(
        pattern = re.compile(r"\b(\w*receipt\w*)\.write_text\(\s*json\.dumps\(")
        matches = pattern.findall(source)
        self.assertEqual(
            matches,
            [],
            f"alchemy.py 中发现 receipt-like 变量裸 .write_text(json.dumps(: {matches}",
        )


class AlchemyAdditionalApplyLockTests(unittest.TestCase):
    """R92.1: 3 个 R92-ALCHEMY 残余 unlocked writers 现在也必须持锁。

    覆盖：
    - run_alchemy_judge_propose
    - run_alchemy_legacy_migration_apply
    - run_alchemy_superseded_cleanup_apply
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _assert_lock_held(self, *_args: object, **_kwargs: object) -> None:
        state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
        self.assertIsNotNone(state, "runtime_write_lock not held")
        self.assertGreaterEqual(int(state.get("depth", 0)), 1)
        raise RuntimeError("short-circuit after lock probe")

    def test_run_alchemy_judge_propose_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_judge_propose

        with patch("aiwiki.runner.alchemy.run_alchemy_judge_preview", side_effect=self._assert_lock_held):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_judge_propose(self.root, scope="all")

    def test_run_alchemy_legacy_migration_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_legacy_migration_apply

        with patch(
            "aiwiki.execution.alchemy.apply_legacy_elixir_migration",
            side_effect=self._assert_lock_held,
        ):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_legacy_migration_apply(self.root)

    def test_run_alchemy_superseded_cleanup_apply_acquires_lock(self) -> None:
        from aiwiki.runner.alchemy import run_alchemy_superseded_cleanup_apply

        with patch(
            "aiwiki.execution.alchemy.apply_superseded_elixir_cleanup",
            side_effect=self._assert_lock_held,
        ):
            with self.assertRaisesRegex(RuntimeError, "short-circuit after lock probe"):
                run_alchemy_superseded_cleanup_apply(self.root)


class AlchemyLaneNestedLockTests(unittest.TestCase):
    """R92.1: lane apply 调入 _run_receipted_lane_primitive 路径下，inner 应观测到 depth>=2。

    `_run_receipted_lane_primitive` 不加 @runtime_write_operation，依赖 lane_apply 已持锁；
    此测试锁住"lane apply outer + receipted primitive inner"嵌套 reentrant 语义。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lane_apply_inner_primitive_observes_reentrant_depth(self) -> None:
        """覆盖 lane_apply (outer @runtime_write_operation, depth=1) →
        _run_receipted_lane_primitive (无装饰器, 持 outer lock) →
        run_alchemy_review_apply (@runtime_write_operation, depth=2) 的 reentrant 路径。

        Probe 落在 decorated primitive apply 上，断言 depth>=2。
        """
        from aiwiki.runner.alchemy import run_alchemy_lane_apply

        observed_depths: list[int] = []

        def probe(*_args: object, **_kwargs: object) -> dict:
            state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
            observed_depths.append(int(state["depth"]) if state else 0)
            raise RuntimeError("short-circuit at decorated primitive apply")

        # Fake plan: status=ok, selected_count>=1, primitive_plan 含 apply_supported review 步。
        # _lane_primitive_plan_step 读 plan["primitive_plan"][primitive] 或类似结构；
        # 兼容多种存放，提供 list+map 两形态。
        fake_plan = {
            "status": "ok",
            "lane": "heavy",
            "scope": "all",
            "selected_count": 1,
            "primitive_plan": [
                {"primitive": "review", "apply_supported": True, "apply_blocker": None},
            ],
        }

        with patch(
            "aiwiki.planner.preview_alchemy_lane",
            return_value=fake_plan,
        ), patch(
            # Probe inside review_preview (called by review_apply *after* its own
            # @runtime_write_operation decorator has incremented depth). Patching
            # review_apply itself would replace the decorator wrapper and miss depth=2.
            "aiwiki.runner.alchemy.run_alchemy_review_preview",
            side_effect=probe,
        ):
            with self.assertRaisesRegex(RuntimeError, "short-circuit at decorated primitive apply"):
                run_alchemy_lane_apply(
                    self.root,
                    lane="heavy",
                    scope="all",
                    primitives=["review"],
                )

        # 必须真正进入 probe（非 vacuous）
        self.assertEqual(
            len(observed_depths),
            1,
            "decorated primitive apply must be invoked exactly once via lane_apply",
        )
        self.assertGreaterEqual(
            observed_depths[0],
            2,
            "decorated primitive apply must observe reentrant depth>=2 under lane_apply outer lock",
        )


class AlchemyNormalizeLockStatusTightenedTests(unittest.TestCase):
    """R92.1: _normalize_preview_lock_status 应只改写 `lock` 子树，不误伤同形 dict。"""

    def test_only_rewrites_lock_subtree(self) -> None:
        from aiwiki.runner.alchemy import _normalize_preview_lock_status

        payload = {
            "lock": {
                "status": "held_by_current_process",
                "would_acquire": False,
            },
            # 非 lock 字段，但同形（status + would_acquire）。不应被改写。
            "unrelated": {
                "status": "held_by_current_process",
                "would_acquire": False,
            },
        }
        result = _normalize_preview_lock_status(payload)
        self.assertEqual(result["lock"]["status"], "available")
        self.assertEqual(result["lock"]["would_acquire"], True)
        # unrelated 同形 dict 必须保持原值，不被误伤
        self.assertEqual(result["unrelated"]["status"], "held_by_current_process")
        self.assertEqual(result["unrelated"]["would_acquire"], False)

    def test_nested_lock_in_list_is_normalized(self) -> None:
        from aiwiki.runner.alchemy import _normalize_preview_lock_status

        payload = {
            "candidates": [
                {
                    "lock": {"status": "held_by_current_process", "would_acquire": False},
                    "name": "x",
                }
            ]
        }
        result = _normalize_preview_lock_status(payload)
        self.assertEqual(result["candidates"][0]["lock"]["status"], "available")


if __name__ == "__main__":
    unittest.main()
