from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from aiwiki.cli import main
from aiwiki.vault_queue import drain_vault_queue, list_pending_queue


def _write_queue(root: Path, queue_id: str, payload: dict[str, object]) -> Path:
    path = root / ".aiwiki" / "queue" / f"{queue_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "version": 1,
        "id": queue_id,
        "kind": "note",
        "created_at": f"2026-07-14T00:00:0{len(queue_id)}+00:00",
        "payload": {},
        "status": "pending",
        "source": "companion",
    }
    body.update(payload)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_list_pending_queue_returns_only_pending(tmp_path: Path) -> None:
    _write_queue(tmp_path, "b", {"kind": "ask", "created_at": "2026-07-14T00:00:02+00:00"})
    _write_queue(tmp_path, "a", {"kind": "note", "created_at": "2026-07-14T00:00:01+00:00"})
    _write_queue(tmp_path, "done", {"status": "done"})

    pending = list_pending_queue(tmp_path)

    assert [item["id"] for item in pending] == ["a", "b"]
    assert pending[0]["queue_path"] == ".aiwiki/queue/a.json"


def test_drain_vault_queue_dry_run_does_not_mutate_items(tmp_path: Path) -> None:
    path = _write_queue(
        tmp_path,
        "note1",
        {"kind": "note", "payload": {"argv": ["drop", "markdown", "--text", "hello"]}},
    )

    result = drain_vault_queue(tmp_path, limit=1)

    assert result["status"] == "dry-run"
    assert result["processed"] == [
        {"id": "note1", "kind": "note", "status": "pending", "queue_path": ".aiwiki/queue/note1.json"}
    ]
    assert _read_json(path)["status"] == "pending"


def test_drain_vault_queue_execute_note_marks_done_and_writes_receipt(tmp_path: Path) -> None:
    path = _write_queue(
        tmp_path,
        "note1",
        {
            "kind": "note",
            "payload": {"argv": ["drop", "markdown", "--text", "mobile note", "--title", "Mobile Note"]},
        },
    )

    result = drain_vault_queue(tmp_path, limit=1, execute=True)

    assert result["status"] == "ok"
    processed = result["processed"][0]
    assert processed["status"] == "done"
    updated = _read_json(path)
    assert updated["status"] == "done"
    receipt_path = tmp_path / str(updated["receipt_path"])
    receipt = _read_json(receipt_path)
    assert receipt["status"] == "done"
    assert receipt["queue_id"] == "note1"
    assert receipt["result"]["action"] == "drop-note"
    assert list((tmp_path / "raw" / "inbox").glob("*.md"))


def test_drain_vault_queue_execute_ask_uses_deterministic_safe_entry(tmp_path: Path) -> None:
    path = _write_queue(
        tmp_path,
        "ask1",
        {
            "kind": "ask",
            "payload": {"argv": ["run-ask-submit", "What changed?", "--format", "report", "--protocol", "research"]},
        },
    )

    with patch("aiwiki.vault_queue.ask_question", return_value={"output_path": "output/reports/answer.md"}) as ask:
        result = drain_vault_queue(tmp_path, limit=1, execute=True)

    ask.assert_called_once_with(tmp_path, "What changed?", "report", protocol="research")
    assert result["status"] == "ok"
    updated = _read_json(path)
    receipt = _read_json(tmp_path / str(updated["receipt_path"]))
    assert receipt["result"]["action"] == "ask"
    assert receipt["result"]["execution_mode"] == "deterministic"


def test_drain_vault_queue_execute_unsupported_drop_marks_failed(tmp_path: Path) -> None:
    path = _write_queue(
        tmp_path,
        "drop1",
        {"kind": "drop", "payload": {"argv": ["drop", "pdf", "/tmp/file.pdf"]}},
    )

    result = drain_vault_queue(tmp_path, limit=1, execute=True)

    assert result["status"] == "partial-failed"
    processed = result["processed"][0]
    assert processed["status"] == "failed"
    assert "desktop full runtime" in processed["error"]
    updated = _read_json(path)
    assert updated["status"] == "failed"
    receipt = _read_json(tmp_path / str(updated["receipt_path"]))
    assert receipt["status"] == "failed"
    assert "desktop full runtime" in receipt["error"]


def test_drain_vault_queue_execute_unknown_kind_marks_failed(tmp_path: Path) -> None:
    path = _write_queue(tmp_path, "bad1", {"kind": "mystery"})

    result = drain_vault_queue(tmp_path, limit=1, execute=True)

    assert result["status"] == "partial-failed"
    updated = _read_json(path)
    assert updated["status"] == "failed"
    assert "Unsupported vault queue kind" in updated["error"]


def test_cli_vault_queue_drain_dry_run(tmp_path: Path) -> None:
    _write_queue(tmp_path, "note1", {"kind": "note"})
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
        code = main(["--root", str(tmp_path), "advanced", "vault-queue-drain", "--limit", "1"])

    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["kind"] == "vault-queue-drain"
    assert payload["status"] == "dry-run"
    assert payload["processed"][0]["id"] == "note1"
