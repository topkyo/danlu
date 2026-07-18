"""Vault queue companion drain for mobile Product Shell requests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .drop import drop_note
from .execution.ask import ask_question
from .utils.io import atomic_write_text
from .utils.path import relative_path
from .utils.time import utc_now

QUEUE_DIR = ".aiwiki/queue"
QUEUE_VERSION = 1
SUPPORTED_STATUSES = {"pending", "claimed", "done", "failed"}


def list_pending_queue(root: Path) -> list[dict[str, Any]]:
    """Return pending queue items sorted by creation time, without mutating them."""

    queue_dir = root / QUEUE_DIR
    if not queue_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(queue_dir.glob("*.json")):
        if path.name.endswith(".receipt.json"):
            continue
        item = _read_queue_item(path)
        if item.get("status") != "pending":
            continue
        items.append(_with_queue_path(root, path, item))
    return sorted(items, key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))


def drain_vault_queue(root: Path, *, limit: int = 5, execute: bool = False) -> dict[str, Any]:
    """Drain pending vault queue items.

    The default is a dry-run preview.  ``execute=True`` intentionally supports
    only low-risk local actions in the first slice: text notes and deterministic
    ask artifacts.  Other drop kinds are marked failed with an explicit receipt
    so the companion never reports queued work as successful execution.
    """

    normalized_limit = max(0, int(limit))
    pending = list_pending_queue(root)
    selected = pending[:normalized_limit]
    processed: list[dict[str, Any]] = []
    if not execute:
        return {
            "kind": "vault-queue-drain",
            "status": "dry-run",
            "execute": False,
            "limit": normalized_limit,
            "pending_count": len(pending),
            "processed": [
                {
                    "id": str(item.get("id") or ""),
                    "kind": str(item.get("kind") or ""),
                    "status": str(item.get("status") or ""),
                    "queue_path": str(item.get("queue_path") or ""),
                }
                for item in selected
            ],
        }

    for item in selected:
        queue_path = root / str(item["queue_path"])
        claimed = _update_queue_item(root, queue_path, item, status="claimed")
        try:
            result = _execute_queue_item(root, claimed)
            receipt = _write_queue_receipt(root, queue_path, claimed, status="done", result=result)
            final_item = _update_queue_item(
                root, queue_path, claimed, status="done", receipt_path=receipt["receipt_path"]
            )
            processed.append(
                {
                    "id": final_item["id"],
                    "kind": final_item.get("kind"),
                    "status": "done",
                    "queue_path": final_item["queue_path"],
                    "receipt_path": receipt["receipt_path"],
                    "result": result,
                }
            )
        except Exception as exc:  # explicit per-item failure; continue draining remaining queue items.
            message = str(exc) or exc.__class__.__name__
            receipt = _write_queue_receipt(root, queue_path, claimed, status="failed", error=message)
            final_item = _update_queue_item(
                root, queue_path, claimed, status="failed", error=message, receipt_path=receipt["receipt_path"]
            )
            processed.append(
                {
                    "id": final_item["id"],
                    "kind": final_item.get("kind"),
                    "status": "failed",
                    "queue_path": final_item["queue_path"],
                    "receipt_path": receipt["receipt_path"],
                    "error": message,
                }
            )
    status = "ok" if not any(item.get("status") == "failed" for item in processed) else "partial-failed"
    return {
        "kind": "vault-queue-drain",
        "status": status,
        "execute": True,
        "limit": normalized_limit,
        "pending_count": len(pending),
        "processed": processed,
    }


def _read_queue_item(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid queue JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid queue item: {path}: expected object")
    status = str(raw.get("status") or "")
    if status and status not in SUPPORTED_STATUSES:
        raise ValueError(f"Invalid queue status in {path}: {status}")
    return raw


def _with_queue_path(root: Path, path: Path, item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "queue_path": relative_path(root, path)}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _update_queue_item(root: Path, path: Path, item: dict[str, Any], **updates: Any) -> dict[str, Any]:
    next_item = {key: value for key, value in item.items() if key != "queue_path"}
    next_item.update(updates)
    next_item["updated_at"] = utc_now()
    _write_json(path, next_item)
    return _with_queue_path(root, path, next_item)


def _write_queue_receipt(
    root: Path,
    queue_path: Path,
    item: dict[str, Any],
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    receipt_path = queue_path.with_name(f"{queue_path.stem}.receipt.json")
    receipt = {
        "version": QUEUE_VERSION,
        "kind": "vault-queue-receipt",
        "queue_id": str(item.get("id") or ""),
        "queue_path": relative_path(root, queue_path),
        "status": status,
        "created_at": utc_now(),
        "result": result or {},
        "error": error or "",
        "message": _receipt_message(item, status, error),
    }
    _write_json(receipt_path, receipt)
    return {**receipt, "receipt_path": relative_path(root, receipt_path)}


def _receipt_message(item: dict[str, Any], status: str, error: str | None) -> str:
    if status == "done":
        return "Vault queue item executed by desktop drain."
    return error or f"Vault queue item failed: {item.get('kind') or 'unknown'}"


def _execute_queue_item(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind") or "").strip()
    if kind == "note":
        return _execute_note_item(root, item)
    if kind == "ask":
        return _execute_ask_item(root, item)
    if (
        kind == "drop"
        and _queue_argv(item)[:2]
        and _queue_argv(item)[0] == "drop"
        and _queue_argv(item)[1] in {"markdown", "md", "note"}
    ):
        return _execute_note_item(root, item)
    if kind == "drop":
        raise ValueError(
            "Vault queue drop requires desktop full runtime for this material kind; no execution was performed."
        )
    raise ValueError(f"Unsupported vault queue kind: {kind or 'missing'}")


def _execute_note_item(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    request = _queue_request(item)
    argv = _queue_argv(item)
    source = str(request.get("source") or "").strip()
    text = str(request.get("text") or "").strip()
    title = str(request.get("title") or "").strip() or None
    note_kind = str(request.get("kind") or "note").strip() or "note"
    allow_sensitive = bool(request.get("allow_sensitive"))
    if argv:
        parsed = _parse_drop_note_argv(argv)
        source = parsed.get("source", source)
        text = parsed.get("text", text)
        title = parsed.get("title", title)
        note_kind = parsed.get("kind", note_kind)
        allow_sensitive = parsed.get("allow_sensitive", allow_sensitive)
    result = drop_note(
        root, source or None, title=title, text=text or None, kind=note_kind, allow_sensitive=allow_sensitive
    )
    return {"action": "drop-note", **result}


def _execute_ask_item(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    request = _queue_request(item)
    argv = _queue_argv(item)
    question = str(request.get("question") or "").strip()
    output_format = str(request.get("format") or "report").strip() or "report"
    protocol = str(request.get("protocol") or "").strip() or None
    if argv:
        parsed = _parse_ask_argv(argv)
        question = parsed.get("question", question)
        output_format = parsed.get("format", output_format)
        protocol = parsed.get("protocol", protocol)
    if not question:
        raise ValueError("Vault queue ask requires a question.")
    result = ask_question(root, question, output_format, protocol=protocol)
    return {"action": "ask", "execution_mode": "deterministic", **result}


def _queue_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else {}


def _queue_request(item: dict[str, Any]) -> dict[str, Any]:
    request = _queue_payload(item).get("request")
    return request if isinstance(request, dict) else {}


def _queue_argv(item: dict[str, Any]) -> list[str]:
    argv = _queue_payload(item).get("argv")
    return [str(value) for value in argv] if isinstance(argv, list) else []


def _parse_drop_note_argv(argv: list[str]) -> dict[str, Any]:
    if not argv:
        return {}
    start = 1
    if argv[0] == "drop" and len(argv) > 1:
        start = 2
    elif argv[0] == "drop-note":
        start = 1
    parsed: dict[str, Any] = {
        "source": "",
        "text": _option_value(argv, "--text") or "",
        "title": _option_value(argv, "--title") or None,
        "kind": _option_value(argv, "--kind") or "note",
        "allow_sensitive": "--allow-sensitive" in argv,
    }
    for value in argv[start:]:
        if value.startswith("--"):
            break
        if value:
            parsed["source"] = value
            break
    return parsed


def _parse_ask_argv(argv: list[str]) -> dict[str, Any]:
    question = ""
    if len(argv) > 1 and not argv[1].startswith("--"):
        question = argv[1]
    return {
        "question": question,
        "format": _option_value(argv, "--format") or "report",
        "protocol": _option_value(argv, "--protocol") or None,
    }


def _option_value(argv: list[str], option: str) -> str | None:
    for index, value in enumerate(argv):
        if value == option and index + 1 < len(argv):
            return argv[index + 1]
    return None
