from __future__ import annotations

import json
import os

import pytest

from aiwiki.app_utils import atomic_append_jsonl, atomic_append_line, atomic_write_text


def _tmp_residue(directory):
    return list(directory.glob("*.tmp.*"))


def test_atomic_write_text_happy_path_no_tmp_residue(tmp_path):
    path = tmp_path / "state.json"

    atomic_write_text(path, "hello\n")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert _tmp_residue(tmp_path) == []


def test_atomic_write_text_creates_parent_dir(tmp_path):
    path = tmp_path / "missing" / "nested" / "state.json"

    atomic_write_text(path, "created")

    assert path.read_text(encoding="utf-8") == "created"


def test_atomic_write_text_cleans_tmp_on_fsync_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("original", encoding="utf-8")

    def fail_fsync(_fd):
        raise OSError("fsync failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failed"):
        atomic_write_text(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert _tmp_residue(tmp_path) == []


def test_atomic_write_text_cleans_tmp_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("original", encoding="utf-8")

    def fail_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert _tmp_residue(tmp_path) == []


def test_atomic_write_text_fsync_false_skips_fsync(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    calls = 0

    def count_fsync(_fd):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(os, "fsync", count_fsync)

    atomic_write_text(path, "no fsync", fsync=False)

    assert path.read_text(encoding="utf-8") == "no fsync"
    assert calls == 0


def test_atomic_append_jsonl_happy_path_appends_in_order(tmp_path):
    path = tmp_path / "history.jsonl"

    atomic_append_jsonl(path, {"b": 2, "a": 1})
    atomic_append_jsonl(path, {"event": "second"})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line) for line in lines] == [{"a": 1, "b": 2}, {"event": "second"}]
    assert lines[0] == '{"a": 1, "b": 2}'


@pytest.mark.parametrize("record", [[], "record", 1, None])
def test_atomic_append_jsonl_raises_type_error_on_non_dict(tmp_path, record):
    with pytest.raises(TypeError, match="atomic_append_jsonl expects dict"):
        atomic_append_jsonl(tmp_path / "history.jsonl", record)


def test_atomic_append_jsonl_fsync_false_skips_fsync(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    calls = 0

    def count_fsync(_fd):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(os, "fsync", count_fsync)

    atomic_append_jsonl(path, {"ok": True}, fsync=False)

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert calls == 0


def test_atomic_append_jsonl_creates_parent_dir(tmp_path):
    path = tmp_path / "missing" / "nested" / "history.jsonl"

    atomic_append_jsonl(path, {"first": 1})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"first": 1}


def test_atomic_append_jsonl_typeerror_does_not_create_file(tmp_path):
    path = tmp_path / "history.jsonl"

    with pytest.raises(TypeError):
        atomic_append_jsonl(path, ["not", "a", "dict"])

    assert not path.exists()


def test_atomic_append_jsonl_partial_failure_no_corruption(tmp_path, monkeypatch):
    """A failed os.write must not leave a half-written line behind."""
    import unittest.mock as mock

    path = tmp_path / "history.jsonl"

    atomic_append_jsonl(path, {"a": 1})

    with mock.patch("os.write", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError, match="simulated crash"):
            atomic_append_jsonl(path, {"b": 2})

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"a": 1}


def test_atomic_append_jsonl_short_write_rolls_back(tmp_path, monkeypatch):
    """os.write returning fewer bytes than requested must truncate back."""
    path = tmp_path / "history.jsonl"
    atomic_append_jsonl(path, {"a": 1})
    before = path.read_bytes()
    original_write = os.write

    def short_write(fd, data):
        # Persist a real truncated fragment, then report short count.
        fragment = data[: max(1, len(data) // 2)]
        original_write(fd, fragment)
        return len(fragment)

    monkeypatch.setattr(os, "write", short_write)
    with pytest.raises(OSError, match="partial write"):
        atomic_append_jsonl(path, {"b": 2})

    assert path.read_bytes() == before
    assert json.loads(path.read_text(encoding="utf-8").strip().split("\n")[0]) == {"a": 1}


def test_atomic_append_jsonl_rollback_failure_preserves_cause(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    atomic_append_jsonl(path, {"keep": True})

    def fail_fsync(_fd):
        raise OSError("jsonl fsync failed")

    def fail_truncate(_path, _size):
        raise OSError("truncate failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    monkeypatch.setattr("aiwiki.app_utils._durable_truncate", fail_truncate)
    with pytest.raises(OSError, match="rollback also failed") as ctx:
        atomic_append_jsonl(path, {"event": "boom"})
    assert "jsonl fsync failed" in str(ctx.value)
    assert isinstance(ctx.value.__cause__, OSError)


def test_atomic_append_jsonl_fsync_failure_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    atomic_append_jsonl(path, {"keep": True})
    before = path.read_bytes()

    def fail_fsync(_fd):
        raise OSError("jsonl fsync failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="jsonl fsync failed"):
        atomic_append_jsonl(path, {"event": "boom"})

    assert path.read_bytes() == before


def test_atomic_append_jsonl_fsync_failure_propagates(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"

    def fail_fsync(_fd):
        raise OSError("jsonl fsync failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="jsonl fsync failed"):
        atomic_append_jsonl(path, {"event": "boom"})

    assert not path.exists() or path.read_text(encoding="utf-8") == ""

def test_atomic_append_line_happy_path_round_trip(tmp_path):
    path = tmp_path / "history.jsonl"

    atomic_append_line(path, '{"schema_version":1,"kind":"signal"}')
    atomic_append_line(path, '{"schema_version":1,"kind":"planner"}')

    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"schema_version":1,"kind":"signal"}',
        '{"schema_version":1,"kind":"planner"}',
    ]


def test_atomic_append_line_fsync_failure_propagates(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"

    def fail_fsync(_fd):
        raise OSError("line fsync failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="line fsync failed"):
        atomic_append_line(path, '{"event":"boom"}')


def test_atomic_append_line_rejects_embedded_newline(tmp_path):
    with pytest.raises(ValueError, match="embedded newlines"):
        atomic_append_line(tmp_path / "history.jsonl", '{"a":1}\n{"b":2}')


def test_atomic_append_line_creates_parent_dir(tmp_path):
    path = tmp_path / "missing" / "nested" / "history.jsonl"

    atomic_append_line(path, '{"first":1}')

    assert path.read_text(encoding="utf-8") == '{"first":1}\n'


def test_atomic_write_text_concurrent_same_path_yields_one_winner(tmp_path):
    """Two threads writing same path must end with one of the two contents intact, never mixed."""
    import threading

    path = tmp_path / "state.json"
    payload_a = "A" * 4096 + "\n"
    payload_b = "B" * 4096 + "\n"
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(payload: str) -> None:
        try:
            barrier.wait(timeout=2)
            atomic_write_text(path, payload)
        except BaseException as exc:  # noqa: BLE001 - capture for assertion
            errors.append(exc)

    t1 = threading.Thread(target=write, args=(payload_a,))
    t2 = threading.Thread(target=write, args=(payload_b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    final = path.read_text(encoding="utf-8")
    assert final in (payload_a, payload_b)
    # No tmp residue from either thread.
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_atomic_write_text_cleans_tmp_on_keyboard_interrupt(tmp_path, monkeypatch):
    """BaseException (e.g. KeyboardInterrupt during fsync) must still clean tmp."""
    path = tmp_path / "state.json"
    path.write_text("original", encoding="utf-8")

    def raise_kbd(_fd):
        raise KeyboardInterrupt()

    monkeypatch.setattr(os, "fsync", raise_kbd)

    with pytest.raises(KeyboardInterrupt):
        atomic_write_text(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp.*")) == []
