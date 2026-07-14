from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.execution.alchemy import (
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    LegacyMigrationApplyError,
    LegacyMigrationHalfWriteError,
    SupersededCleanupApplyError,
    SupersededCleanupHalfWriteError,
    _parse_elixir_frontmatter,
    _write_elixir_markdown,
    apply_legacy_elixir_migration,
    apply_superseded_elixir_cleanup,
)


def _settled_path(root: Path, elixir_id: str) -> Path:
    return root / ELIXIR_DIR / f"{elixir_id}.md"


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"


def _receipt_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-receipts"


def _receipt_paths(root: Path) -> list[Path]:
    receipt_dir = _receipt_dir(root)
    if not receipt_dir.exists():
        return []
    return sorted(receipt_dir.glob("*.json"))


def _receipt_history_text(root: Path) -> str:
    path = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


class AlchemyLegacyCleanupTransactionTests(unittest.TestCase):
    """Failure-injection tests for legacy elixir migration + superseded cleanup TX paths.

    SC-004 patch seam: targets the high-level transactional helper API at the
    ``aiwiki.execution.alchemy.*`` import binding (i.e. the same name the caller
    invokes). This validates rollback when ``atomic_write_text`` /
    ``append_execution_receipt_history`` / ``_restore_snapshots`` fail.
    Tests deliberately do NOT patch ``os.replace`` (an OS-level primitive that
    sits below the transactional contract); they exercise the helper API the
    refactor relies on.
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_stub_elixir(self, path: Path, *, elixir_id: str, state: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    'kind: "elixir"',
                    f'elixir_id: "{elixir_id}"',
                    f'elixir_state: "{state}"',
                    'protocol: "general"',
                    'iteration: "0"',
                    'provenance_corpus: "corp"',
                    "derived_from:",
                    '  - "wiki/derived/base.md"',
                    'topic: "topic"',
                    "counter_evidence:",
                    '  - "NONE_FOUND"',
                    'confidence_level: "low"',
                    'created_at: "2026-01-01T00:00:00+00:00"',
                    'updated_at: "2026-01-01T00:00:00+00:00"',
                    'distill_history_json: "[]"',
                    "---",
                    "# Elixir",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_legacy_settled_pair(self) -> tuple[str, str, dict[str, str]]:
        first_id = "legacy-one"
        second_id = "legacy-two"
        self._write_stub_elixir(_settled_path(self.root, first_id), elixir_id=first_id, state="settled")
        self._write_stub_elixir(_settled_path(self.root, second_id), elixir_id=second_id, state="settled")
        settled_before = {
            first_id: _settled_path(self.root, first_id).read_text(encoding="utf-8"),
            second_id: _settled_path(self.root, second_id).read_text(encoding="utf-8"),
        }
        return first_id, second_id, settled_before

    def _write_superseded_cleanup_pair(self) -> tuple[str, str, dict[str, str]]:
        first_id = "cleanup-one"
        second_id = "cleanup-two"
        for elixir_id in (first_id, second_id):
            self._write_stub_elixir(_settled_path(self.root, elixir_id), elixir_id=elixir_id, state="settled")
            self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="superseded")
            frontmatter = _parse_elixir_frontmatter(_candidate_path(self.root, elixir_id))
            frontmatter["superseded_by"] = f"wiki/elixirs/{elixir_id}.md"
            _write_elixir_markdown(
                _candidate_path(self.root, elixir_id),
                frontmatter=frontmatter,
                body="# Elixir\n\n",
            )
        candidate_before = {
            first_id: _candidate_path(self.root, first_id).read_text(encoding="utf-8"),
            second_id: _candidate_path(self.root, second_id).read_text(encoding="utf-8"),
        }
        return first_id, second_id, candidate_before

    def _assert_legacy_rolled_back(self, ids: tuple[str, str], settled_before: dict[str, str]) -> None:
        for elixir_id in ids:
            self.assertFalse(_candidate_path(self.root, elixir_id).exists())
            self.assertEqual(_settled_path(self.root, elixir_id).read_text(encoding="utf-8"), settled_before[elixir_id])
        self.assertEqual(_receipt_paths(self.root), [])
        self.assertEqual(_receipt_history_text(self.root), "")

    def _assert_cleanup_restored(self, ids: tuple[str, str], candidate_before: dict[str, str]) -> None:
        for elixir_id in ids:
            candidate = _candidate_path(self.root, elixir_id)
            self.assertTrue(candidate.exists())
            self.assertEqual(candidate.read_text(encoding="utf-8"), candidate_before[elixir_id])
        self.assertEqual(_receipt_paths(self.root), [])

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def test_legacy_migration_receipt_write_failure_rolls_back_tombstones(self) -> None:
        first_id, second_id, settled_before = self._write_legacy_settled_pair()
        from aiwiki.execution import alchemy as _alchemy_module

        original_atomic_write_text = _alchemy_module.atomic_write_text

        def fail_receipt_write(path: Path, content: str, **kwargs: object) -> None:
            if path.suffix == ".json" and path.parent == _receipt_dir(self.root):
                raise OSError("injected receipt write failure")
            original_atomic_write_text(path, content, **kwargs)

        with patch("aiwiki.execution.alchemy.atomic_write_text", side_effect=fail_receipt_write):
            with self.assertRaises(LegacyMigrationApplyError):
                apply_legacy_elixir_migration(self.root)

        self._assert_legacy_rolled_back((first_id, second_id), settled_before)

    def test_legacy_migration_history_append_failure_rolls_back_receipt_and_tombstones(self) -> None:
        first_id, second_id, settled_before = self._write_legacy_settled_pair()

        with patch(
            "aiwiki.execution.alchemy.append_execution_receipt_history",
            side_effect=OSError("injected history append failure"),
        ):
            with self.assertRaises(LegacyMigrationApplyError):
                apply_legacy_elixir_migration(self.root)

        self._assert_legacy_rolled_back((first_id, second_id), settled_before)

    def test_legacy_migration_rollback_failure_raises_half_write_error(self) -> None:
        self._write_legacy_settled_pair()
        from aiwiki.execution import alchemy as _alchemy_module

        original_atomic_write_text = _alchemy_module.atomic_write_text

        def fail_receipt_write(path: Path, content: str, **kwargs: object) -> None:
            if path.suffix == ".json" and path.parent == _receipt_dir(self.root):
                raise OSError("injected receipt write failure")
            original_atomic_write_text(path, content, **kwargs)

        with patch("aiwiki.execution.alchemy.atomic_write_text", side_effect=fail_receipt_write):
            with patch(
                "aiwiki.execution.alchemy._restore_snapshots",
                side_effect=OSError("injected rollback failure"),
            ):
                with self.assertRaises(LegacyMigrationHalfWriteError) as raised:
                    apply_legacy_elixir_migration(self.root)

        self.assertIn(str(raised.exception.phase), {"receipt_rollback", "mutation_rollback"})
        self.assertRegex(str(raised.exception), r"receipt_rollback|mutation_rollback")

    def test_legacy_migration_mutation_failure_rolls_back_first_candidate(self) -> None:
        first_id, second_id, settled_before = self._write_legacy_settled_pair()
        from aiwiki.execution import alchemy as alchemy_module

        # _write_atomic_text is alchemy-internal (not in app_utils); patching the
        # alchemy module-local seam is the correct injection point for this case.
        original_write_atomic_text = alchemy_module._write_atomic_text
        call_count = 0

        def fail_second_candidate_write(path: Path, content: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("injected second candidate write failure")
            original_write_atomic_text(path, content)

        with patch.object(alchemy_module, "_write_atomic_text", side_effect=fail_second_candidate_write):
            with self.assertRaises(LegacyMigrationApplyError):
                apply_legacy_elixir_migration(self.root)

        self._assert_legacy_rolled_back((first_id, second_id), settled_before)

    # ------------------------------------------------------------------
    # Superseded cleanup
    # ------------------------------------------------------------------

    def test_superseded_cleanup_unlink_failure_restores_deleted_candidate(self) -> None:
        first_id, second_id, candidate_before = self._write_superseded_cleanup_pair()
        target_second = _candidate_path(self.root, second_id)
        original_unlink = Path.unlink

        def fail_second_candidate_unlink(self_path: Path, *args: object, **kwargs: object) -> None:
            if Path(self_path) == target_second:
                raise OSError("injected second unlink failure")
            original_unlink(self_path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_second_candidate_unlink):
            with self.assertRaises(SupersededCleanupApplyError):
                apply_superseded_elixir_cleanup(self.root)

        # The first candidate WAS actually unlinked before the second one failed,
        # so the rollback path must restore it from the snapshot bytes.
        self._assert_cleanup_restored((first_id, second_id), candidate_before)

    def test_superseded_cleanup_receipt_write_failure_restores_all_candidates(self) -> None:
        first_id, second_id, candidate_before = self._write_superseded_cleanup_pair()
        from aiwiki.execution import alchemy as _alchemy_module

        original_atomic_write_text = _alchemy_module.atomic_write_text

        def fail_receipt_write(path: Path, content: str, **kwargs: object) -> None:
            if path.suffix == ".json" and path.parent == _receipt_dir(self.root):
                raise OSError("injected receipt write failure")
            original_atomic_write_text(path, content, **kwargs)

        with patch("aiwiki.execution.alchemy.atomic_write_text", side_effect=fail_receipt_write):
            with self.assertRaises(SupersededCleanupApplyError):
                apply_superseded_elixir_cleanup(self.root)

        self._assert_cleanup_restored((first_id, second_id), candidate_before)

    def test_superseded_cleanup_history_append_failure_restores_all_candidates(self) -> None:
        first_id, second_id, candidate_before = self._write_superseded_cleanup_pair()

        with patch(
            "aiwiki.execution.alchemy.append_execution_receipt_history",
            side_effect=OSError("injected history append failure"),
        ):
            with self.assertRaises(SupersededCleanupApplyError):
                apply_superseded_elixir_cleanup(self.root)

        self._assert_cleanup_restored((first_id, second_id), candidate_before)

    def test_superseded_cleanup_rollback_failure_raises_half_write_error(self) -> None:
        self._write_superseded_cleanup_pair()
        from aiwiki.execution import alchemy as _alchemy_module

        original_atomic_write_text = _alchemy_module.atomic_write_text

        def fail_receipt_write(path: Path, content: str, **kwargs: object) -> None:
            if path.suffix == ".json" and path.parent == _receipt_dir(self.root):
                raise OSError("injected receipt write failure")
            original_atomic_write_text(path, content, **kwargs)

        with patch("aiwiki.execution.alchemy.atomic_write_text", side_effect=fail_receipt_write):
            with patch(
                "aiwiki.execution.alchemy._restore_snapshots",
                side_effect=OSError("injected rollback failure"),
            ):
                with self.assertRaises(SupersededCleanupHalfWriteError) as raised:
                    apply_superseded_elixir_cleanup(self.root)

        self.assertEqual(raised.exception.phase, "receipt_rollback")


if __name__ == "__main__":
    unittest.main()
