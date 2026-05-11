from aiwiki.app_utils import _restore_file_bytes, _snapshot_file_bytes


def test_snapshot_file_bytes_returns_none_for_missing_path(tmp_path):
    assert _snapshot_file_bytes(tmp_path / "missing.bin") is None


def test_snapshot_file_bytes_returns_exact_bytes(tmp_path):
    path = tmp_path / "data.bin"
    content = b"\x00hello\xff\n"
    path.write_bytes(content)

    assert _snapshot_file_bytes(path) == content


def test_snapshot_file_bytes_handles_empty_file(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    assert _snapshot_file_bytes(path) == b""


def test_restore_file_bytes_none_removes_existing_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"present")

    _restore_file_bytes(path, None)

    assert not path.exists()


def test_restore_file_bytes_none_missing_file_is_noop(tmp_path):
    path = tmp_path / "missing.bin"

    _restore_file_bytes(path, None)

    assert not path.exists()


def test_restore_file_bytes_snapshot_creates_file_with_exact_bytes(tmp_path):
    path = tmp_path / "data.bin"
    snapshot = b"\x00snapshot\xff"

    _restore_file_bytes(path, snapshot)

    assert path.read_bytes() == snapshot


def test_restore_file_bytes_snapshot_overwrites_different_content(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"different")
    snapshot = b"original\nbytes"

    _restore_file_bytes(path, snapshot)

    assert path.read_bytes() == snapshot


def test_restore_file_bytes_snapshot_does_not_leave_restore_tmp(tmp_path):
    path = tmp_path / "data.bin"

    _restore_file_bytes(path, b"restored")

    assert not path.with_suffix(path.suffix + ".restore.tmp").exists()


def test_tx_helper_import_paths_resolve():
    from aiwiki.app_utils import _restore_file_bytes as canonical_restore
    from aiwiki.app_utils import _snapshot_file_bytes as canonical_snapshot
    from aiwiki.execution.alchemy import _snapshot_file_bytes as execution_snapshot

    assert canonical_restore is _restore_file_bytes
    assert canonical_snapshot is _snapshot_file_bytes
    assert execution_snapshot is _snapshot_file_bytes
