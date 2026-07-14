from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki import app_utils
from aiwiki.app_utils import (
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)


def _tmp_files(directory: Path) -> list[Path]:
    return list(directory.glob("*.tmp.*"))


def test_write_if_changed_uses_os_replace_path() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "artifact.txt"
        calls: list[tuple[Path, Path]] = []
        original_replace = app_utils.os.replace

        def record_replace(src: Path, dst: Path) -> None:
            calls.append((src, dst))
            original_replace(src, dst)

        with patch("aiwiki.app_utils.os.replace", side_effect=record_replace):
            assert write_if_changed(path, "hello") is True

        assert len(calls) == 1
        tmp, dst = calls[0]
        assert tmp.parent == path.parent
        assert tmp.name.startswith(f"{path.name}.tmp.")
        assert dst == path
        assert path.read_text(encoding="utf-8") == "hello"


def test_write_if_changed_ignoring_timestamps_uses_os_replace_path() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "artifact.md"
        calls: list[tuple[Path, Path]] = []
        original_replace = app_utils.os.replace

        def record_replace(src: Path, dst: Path) -> None:
            calls.append((src, dst))
            original_replace(src, dst)

        with patch("aiwiki.app_utils.os.replace", side_effect=record_replace):
            assert write_if_changed_ignoring_timestamps(path, "hello") == (True, True)

        assert len(calls) == 1
        tmp, dst = calls[0]
        assert tmp.parent == path.parent
        assert tmp.name.startswith(f"{path.name}.tmp.")
        assert dst == path
        assert path.read_text(encoding="utf-8") == "hello"


def test_write_json_document_uses_os_replace_path() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "state.json"
        calls: list[tuple[Path, Path]] = []
        original_replace = app_utils.os.replace

        def record_replace(src: Path, dst: Path) -> None:
            calls.append((src, dst))
            original_replace(src, dst)

        with patch("aiwiki.app_utils.os.replace", side_effect=record_replace):
            assert write_json_document_if_changed_ignoring_generated_timestamps(path, {"b": 2, "a": 1}) == (True, True)

        assert len(calls) == 1
        tmp, dst = calls[0]
        assert tmp.parent == path.parent
        assert tmp.name.startswith(f"{path.name}.tmp.")
        assert dst == path
        assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_write_if_changed_no_partial_file_when_replace_fails() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "artifact.txt"
        path.write_text("old", encoding="utf-8")

        def fail_replace(_src: Path, _dst: Path) -> None:
            raise OSError("simulated replace failure")

        with patch("aiwiki.app_utils.os.replace", side_effect=fail_replace):
            with unittest.TestCase().assertRaisesRegex(OSError, "simulated replace failure"):
                write_if_changed(path, "new")

        assert path.read_text(encoding="utf-8") == "old"
        assert _tmp_files(path.parent) == []


def test_change_detection_still_returns_no_op_when_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "artifact.txt"
        path.write_text("x", encoding="utf-8")

        with patch("aiwiki.app_utils.os.replace") as replace:
            assert write_if_changed(path, "x") is False

        replace.assert_not_called()
        assert _tmp_files(path.parent) == []


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for test_fn in [
        test_write_if_changed_uses_os_replace_path,
        test_write_if_changed_ignoring_timestamps_uses_os_replace_path,
        test_write_json_document_uses_os_replace_path,
        test_write_if_changed_no_partial_file_when_replace_fails,
        test_change_detection_still_returns_no_op_when_unchanged,
    ]:
        suite.addTest(unittest.FunctionTestCase(test_fn))
    return suite
