"""Webhook notification helpers for generated user-facing reports."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execution.audit_preview import append_audit

_FEISHU_ENV = "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL"
_WECOM_ENV = "AIWIKI_NOTIFY_WECOM_WEBHOOK_URL"
_ENABLED_CHANNELS_ENV = "AIWIKI_NOTIFY_ENABLED_CHANNELS"
_HTTP_TIMEOUT_SECONDS = 5


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from .runner.receipts import _append_log

    _append_log(root, event)


@dataclass(frozen=True)
class NotifyConfig:
    """Environment-backed notification settings."""

    feishu_webhook_url: str = ""
    wecom_webhook_url: str = ""
    enabled_channels: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        channels = tuple(
            channel.strip().lower()
            for channel in os.environ.get(_ENABLED_CHANNELS_ENV, "").split(",")
            if channel.strip()
        )
        return cls(
            feishu_webhook_url=os.environ.get(_FEISHU_ENV, "").strip(),
            wecom_webhook_url=os.environ.get(_WECOM_ENV, "").strip(),
            enabled_channels=channels,
        )

    def webhook_url_for(self, channel: str) -> str:
        if channel == "feishu":
            return self.feishu_webhook_url
        if channel == "wecom":
            return self.wecom_webhook_url
        return ""


def notify_report_generated(root: Path, artifact: dict[str, Any]) -> None:
    """
    Send webhook notification for a newly generated user-facing report.

    artifact dict keys (read-only):
      - path: str (workspace-relative path)
      - title: str
      - protocol: str
      - format: str
      - created_at: str (ISO8601)

    Failure mode:
      - never raises to caller
      - 2xx HTTP → silently success (no audit)
      - non-2xx / network error / invalid config → write notify_failed audit
    """

    try:
        config = NotifyConfig.from_env()
        if not config.enabled_channels:
            return

        message = _format_message(artifact)
        for channel in config.enabled_channels:
            webhook_url = config.webhook_url_for(channel)
            if not webhook_url:
                continue
            failure = _post_channel(channel, webhook_url, message)
            if failure is None:
                continue
            reason, status_code, error_type = failure
            _safe_record_notify_failed(root, artifact, channel, reason, status_code, error_type)
    except Exception as exc:
        _append_run_event(
            root,
            {
                "event": "notify_dispatch_failed",
                "reason": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return


def _post_channel(channel: str, webhook_url: str, message: str) -> tuple[str, int | None, str] | None:
    if channel == "feishu":
        payload = _feishu_payload(message)
    elif channel == "wecom":
        payload = _wecom_payload(message)
    else:
        return ("invalid_config", None, "UnsupportedChannel")

    try:
        status_code = _post_json(webhook_url, payload)
    except urllib.error.HTTPError as exc:
        return ("http_status", int(exc.code), exc.__class__.__name__)
    except urllib.error.URLError as exc:
        return ("network_error", None, exc.__class__.__name__)
    except Exception as exc:
        return ("invalid_config", None, exc.__class__.__name__)

    if 200 <= status_code < 300:
        return None
    return ("http_status", status_code, "HTTPStatusError")


def _post_json(webhook_url: str, payload: dict[str, Any]) -> int:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
        return int(response.getcode())


def _feishu_payload(message: str) -> dict[str, Any]:
    return {"msg_type": "text", "content": {"text": message}}


def _wecom_payload(message: str) -> dict[str, Any]:
    return {"msgtype": "text", "text": {"content": message}}


def _format_message(artifact: dict[str, Any]) -> str:
    protocol = str(artifact.get("protocol", ""))
    title = str(artifact.get("title", ""))
    output_format = str(artifact.get("format", ""))
    created_at = _format_created_at(str(artifact.get("created_at", "")))
    return f"[{protocol}] {title} — {output_format} — {created_at}"


def _format_created_at(value: str) -> str:
    if not value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")


def _safe_record_notify_failed(
    root: Path,
    artifact: dict[str, Any],
    channel: str,
    reason: str,
    status_code: int | None,
    error_type: str,
) -> None:
    try:
        _record_notify_failed(root, artifact, channel, reason, status_code, error_type)
    except Exception as exc:
        try:
            _append_run_event(
                root,
                {
                    "event": "notify_audit_append_failed",
                    "channel": channel,
                    "reason": reason,
                    "audit_error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
        except Exception:
            return
        return


def _record_notify_failed(
    root: Path,
    artifact: dict[str, Any],
    channel: str,
    reason: str,
    status_code: int | None,
    error_type: str,
) -> None:
    artifact_path = str(artifact["path"])
    payload = {
        "event_type": "notify_failed",
        "occurred_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_stream": "runtime_history",
        "source_ref": f"notify:{artifact_path}:{channel}",
        "trace_id": f"notify:{artifact_path}",
        "subject": {
            "kind": "output_report",
            "path": artifact_path,
            "protocol": str(artifact["protocol"]),
            "title": str(artifact["title"]),
        },
        "channel": channel,
        "reason": reason,
        "status_code": status_code,
        "error_type": error_type,
        "revert_supported": False,
    }
    append_audit("runtime_history", payload, root=root)
