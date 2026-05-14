from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.app_utils import LockTimeoutError, _resolve_lock_timeout, runtime_write_lock
from aiwiki.drop import _clone_repo, drop_repo

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_install_user_service_auto_adopt_defaults_off() -> None:
    completed = subprocess.run(
        ["bash", "-n", "scripts/install_user_service.sh"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    content = (PROJECT_ROOT / "scripts" / "install_user_service.sh").read_text(encoding="utf-8")
    defaults = {
        "AUTO_APPLY_LIGHT": "AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT",
        "AUTO_ADOPT_L1": "AIWIKI_NIGHTLY_AUTO_ADOPT_L1",
        "AUTO_ADOPT_L2": "AIWIKI_NIGHTLY_AUTO_ADOPT_L2",
        "AUTO_ADOPT_L3": "AIWIKI_NIGHTLY_AUTO_ADOPT_L3",
        "AUTO_ADOPT_JUDGMENTS": "AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS",
    }
    for short_name, env_name in defaults.items():
        assert re.search(rf"{env_name}.*\$\{{{short_name}:-0\}}", content), env_name


def test_run_watch_requires_vault() -> None:
    env = {"PATH": os.environ.get("PATH", "")}
    completed = subprocess.run(
        ["bash", "scripts/run_watch.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "AIWIKI_VAULT" in completed.stderr


def test_run_nightly_requires_vault() -> None:
    env = {"PATH": os.environ.get("PATH", "")}
    completed = subprocess.run(
        ["bash", "scripts/run_nightly.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "AIWIKI_VAULT" in completed.stderr


def test_run_nightly_fallback_default_off() -> None:
    content = (PROJECT_ROOT / "scripts" / "run_nightly.sh").read_text(encoding="utf-8")
    assert "AIWIKI_NIGHTLY_FALLBACK_ENABLED:-0" in content


def test_run_dogfood_maturity_requires_explicit_vault_and_skips_same_day() -> None:
    script = PROJECT_ROOT / "scripts" / "run_dogfood_maturity.sh"
    syntax = subprocess.run(
        ["bash", "-n", str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    env = {"PATH": os.environ.get("PATH", "")}
    missing_vault = subprocess.run(
        ["bash", str(script)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_vault.returncode != 0
    assert "AIWIKI_DOGFOOD_VAULT" in missing_vault.stderr

    with tempfile.TemporaryDirectory() as tempdir:
        vault = Path(tempdir)
        receipt_dir = vault / "output" / "control" / "maturity-gate"
        receipt_dir.mkdir(parents=True)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        receipt = receipt_dir / f"run-{today.replace('-', '')}T001500Z.json"
        receipt.write_text(
            '{\n  "kind": "dogfood-maturity-run-receipt",\n  "generated_at": "' + today + 'T00:15:00Z"\n}\n',
            encoding="utf-8",
        )
        skip_env = {
            "PATH": os.environ.get("PATH", ""),
            "AIWIKI_DOGFOOD_VAULT": str(vault),
        }
        skipped = subprocess.run(
            ["bash", str(script)],
            cwd=PROJECT_ROOT,
            env=skip_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert skipped.returncode == 0, skipped.stderr
        assert "skip: receipt already exists" in skipped.stdout

    with tempfile.TemporaryDirectory() as tempdir:
        vault = Path(tempdir)
        receipt_dir = vault / "output" / "control" / "maturity-gate"
        receipt_dir.mkdir(parents=True)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        filename_only_receipt = receipt_dir / f"run-{today.replace('-', '')}T235959Z.json"
        filename_only_receipt.write_text(
            '{\n  "kind": "dogfood-maturity-run-receipt",\n  "generated_at": ""\n}\n',
            encoding="utf-8",
        )
        skipped_by_filename = subprocess.run(
            ["bash", str(script)],
            cwd=PROJECT_ROOT,
            env={"PATH": os.environ.get("PATH", ""), "AIWIKI_DOGFOOD_VAULT": str(vault)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert skipped_by_filename.returncode == 0, skipped_by_filename.stderr
        assert "skip: receipt already exists" in skipped_by_filename.stdout

    content = script.read_text(encoding="utf-8")
    assert "AIWIKI_DOGFOOD_MATURITY_FORCE" in content
    assert 'FORCE_RUN="${AIWIKI_DOGFOOD_MATURITY_FORCE:-0}"' in content
    assert 'if [[ "$FORCE_RUN" != "1" ]]' in content
    assert 'glob("run-*.json")' in content
    assert 'payload.get("generated_at")' in content
    assert "filename_day" in content


def test_runtime_write_lock_timeout_raises() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        with patch("aiwiki.app_utils._resolve_lock_timeout", return_value=0.2):
            with patch("aiwiki.app_utils.fcntl.flock", side_effect=BlockingIOError):
                try:
                    with runtime_write_lock(root):
                        pass
                except LockTimeoutError as exc:
                    assert "runtime write lock timeout" in str(exc)
                else:  # pragma: no cover - defensive assertion path
                    raise AssertionError("LockTimeoutError was not raised")


def test_runtime_write_lock_timeout_real_subprocess_holder(tmp_path: Path) -> None:
    """Real OS-level lock contention must time out through the LOCK_NB retry loop."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / ".aiwiki" / "state").mkdir(parents=True)

    holder_script = (
        "import time\n"
        "from pathlib import Path\n"
        "from aiwiki.app_utils import runtime_write_lock\n"
        f"root = Path({str(root)!r})\n"
        "with runtime_write_lock(root):\n"
        "    print('HOLDING', flush=True)\n"
        "    time.sleep(4)\n"
    )
    holder_env = os.environ.copy()
    holder_env["AIWIKI_RUNTIME_LOCK_TIMEOUT"] = "60"
    holder_env["PYTHONPATH"] = f"src{os.pathsep}{holder_env['PYTHONPATH']}" if holder_env.get("PYTHONPATH") else "src"
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_script],
        cwd=PROJECT_ROOT,
        env=holder_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if holder.poll() is not None:
                stderr = holder.stderr.read().decode("utf-8", errors="replace") if holder.stderr else ""
                raise AssertionError(f"holder subprocess exited before acquiring lock: {stderr}")
            readable, _, _ = select.select([holder.stdout], [], [], 0.05)
            if readable:
                line = holder.stdout.readline()
                if b"HOLDING" in line:
                    break
        else:
            raise AssertionError("holder subprocess never acquired lock")

        previous_timeout = os.environ.get("AIWIKI_RUNTIME_LOCK_TIMEOUT")
        os.environ["AIWIKI_RUNTIME_LOCK_TIMEOUT"] = "1"
        try:
            started_at = time.monotonic()
            with pytest.raises(LockTimeoutError):
                with runtime_write_lock(root):
                    pass
            elapsed = time.monotonic() - started_at
            assert elapsed < 3.0, f"timeout took too long: {elapsed:.2f}s"
        finally:
            if previous_timeout is None:
                os.environ.pop("AIWIKI_RUNTIME_LOCK_TIMEOUT", None)
            else:
                os.environ["AIWIKI_RUNTIME_LOCK_TIMEOUT"] = previous_timeout
    finally:
        holder.terminate()
        holder.wait(timeout=5)
        if holder.stdout is not None:
            holder.stdout.close()
        if holder.stderr is not None:
            holder.stderr.close()


def test_runtime_write_lock_reentrant_does_not_timeout() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        with runtime_write_lock(root):
            with patch.dict(os.environ, {"AIWIKI_RUNTIME_LOCK_TIMEOUT": "1"}):
                with runtime_write_lock(root):
                    pass


def test_runtime_write_lock_invalid_env_uses_default() -> None:
    with patch.dict(os.environ, {"AIWIKI_RUNTIME_LOCK_TIMEOUT": "garbage"}, clear=False):
        assert _resolve_lock_timeout() == 300
    with patch.dict(os.environ, {"AIWIKI_RUNTIME_LOCK_TIMEOUT": "99999"}, clear=False):
        assert _resolve_lock_timeout() == 3600
    with patch.dict(os.environ, {"AIWIKI_RUNTIME_LOCK_TIMEOUT": "0"}, clear=False):
        assert _resolve_lock_timeout() == 1


def test_drop_repo_remote_requires_env() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        with patch.dict(os.environ, {}, clear=True):
            try:
                drop_repo(root, "https://github.com/foo/bar.git")
            except ValueError as exc:
                assert "remote repo drop disabled" in str(exc)
            else:  # pragma: no cover - defensive assertion path
                raise AssertionError("ValueError was not raised")

        def fake_clone(_source: str, destination: Path) -> None:
            destination.mkdir(parents=True)

        with patch.dict(os.environ, {"AIWIKI_ALLOW_REMOTE_REPO_DROP": "1"}, clear=False):
            with patch("aiwiki.drop._clone_repo", side_effect=fake_clone):
                with patch(
                    "aiwiki.drop._repo_snapshot",
                    return_value={
                        "name": "Remote Fixture",
                        "commit": "abc123",
                        "origin": "https://github.com/foo/bar.git",
                        "readme": "Remote repo summary.",
                        "tree": ["- `README.md`"],
                        "files": [],
                    },
                ):
                    result = drop_repo(root, "https://github.com/foo/bar.git")
        assert result["material"] == "repo"


def test_drop_repo_local_path_unaffected() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        repo = root / "fixture-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Local Repo\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            result = drop_repo(root, str(repo), max_files=10)
        assert result["material"] == "repo"


def test_clone_repo_subprocess_timeout() -> None:
    with tempfile.TemporaryDirectory() as tempdir:
        destination = Path(tempdir) / "repo"
        destination.mkdir()
        (destination / "partial").write_text("partial", encoding="utf-8")
        with patch(
            "aiwiki.drop.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=60),
        ):
            try:
                _clone_repo("https://example.test/repo.git", destination)
            except RuntimeError as exc:
                assert "git clone timed out after 60s" in str(exc)
            else:  # pragma: no cover - defensive assertion path
                raise AssertionError("RuntimeError was not raised")
        assert not destination.exists()


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for test_fn in [
        test_install_user_service_auto_adopt_defaults_off,
        test_run_watch_requires_vault,
        test_run_nightly_requires_vault,
        test_run_nightly_fallback_default_off,
        test_run_dogfood_maturity_requires_explicit_vault_and_skips_same_day,
        test_runtime_write_lock_timeout_raises,
        test_runtime_write_lock_reentrant_does_not_timeout,
        test_runtime_write_lock_invalid_env_uses_default,
        test_drop_repo_remote_requires_env,
        test_drop_repo_local_path_unaffected,
        test_clone_repo_subprocess_timeout,
    ]:
        suite.addTest(unittest.FunctionTestCase(test_fn))

    def run_real_subprocess_holder() -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            test_runtime_write_lock_timeout_real_subprocess_holder(Path(tempdir))

    run_real_subprocess_holder.__name__ = test_runtime_write_lock_timeout_real_subprocess_holder.__name__
    suite.addTest(unittest.FunctionTestCase(run_real_subprocess_holder))
    return suite
