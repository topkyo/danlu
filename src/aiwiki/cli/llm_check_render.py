"""Human-readable renderer for ``aiwiki advanced llm-check`` results."""

from __future__ import annotations

from typing import Any


def render_llm_check_human(result: dict[str, Any]) -> str:
    """Render an ``llm-check`` status/probe result as plain text."""

    if result.get("configured") is False:
        message = str(result.get("message") or "").strip()
        if message:
            return f"LLM runner is not configured. {message}"
        return (
            "LLM runner is not configured. "
            "Set AIWIKI_DEEPSEEK_API_KEY (or DEEPSEEK_API_KEY) for the default deepseek-api backend."
        )

    probe = result.get("probe")
    probes = result.get("probes") or []
    if probe is None and not probes:
        return (
            f"LLM runner configured: backend={result.get('backend', '')}, model={result.get('model', '')}\n"
            "Run with --probe or --probe-all to check compatibility."
        )

    backend = str(result.get("backend", ""))
    model = str(result.get("model", ""))
    effective_probe = _effective_probe(result, probes)
    if effective_probe is None:
        summary_status = "unknown"
    else:
        summary_status = _status_marker(str(effective_probe.get("compatibility", "")))

    table_probes = probes or ([probe] if isinstance(probe, dict) else [])
    rows = _build_rows(table_probes)
    lines = [f"Effective backend: {backend}/{model} ({summary_status})", ""]
    lines.extend(_render_table(rows))

    raw_response_lines = [
        f"raw_response[{str(item.get('backend', ''))}]: {str(item.get('raw_response_path'))}"
        for item in table_probes
        if isinstance(item, dict) and item.get("raw_response_path")
    ]
    if raw_response_lines:
        lines.append("")
        lines.extend(raw_response_lines)
    return "\n".join(lines)


def _effective_probe(result: dict[str, Any], probes: list[Any]) -> dict[str, Any] | None:
    probe = result.get("probe")
    if isinstance(probe, dict):
        return probe

    backend = result.get("backend")
    for item in probes:
        if isinstance(item, dict) and item.get("backend") == backend:
            return item
    return None


def _build_rows(probes: list[Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in probes:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                str(item.get("backend", "")),
                str(item.get("model", "")),
                _status_marker(str(item.get("compatibility", ""))),
                _format_duration(item.get("duration_ms")),
                _truncate_hint(str(item.get("compatibility_hint") or "")),
            ]
        )
    return rows


def _render_table(rows: list[list[str]]) -> list[str]:
    headers = ["Backend", "Model", "Status", "Duration", "Hint"]
    min_widths = [14, 20, 24, 10, 60]
    widths = [
        max(min_width, len(header), *(len(row[index]) for row in rows))
        for index, (header, min_width) in enumerate(zip(headers, min_widths))
    ]
    lines = [_format_row(headers, widths), _format_row(["-" * width for width in widths], widths)]
    lines.extend(_format_row(row, widths) for row in rows)
    return lines


def _format_row(cells: list[str], widths: list[int]) -> str:
    return " | ".join(cell.ljust(width) for cell, width in zip(cells, widths))


def _status_marker(compat: str) -> str:
    if compat == "compatible":
        return "[OK] compatible"
    if compat == "degraded":
        return "[!]  degraded"
    if compat == "unavailable":
        return "[X]  unavailable"
    if compat == "requires_credential":
        return "[?]  requires_credential"
    return "[??] unknown"


def _truncate_hint(hint: str, width: int = 60) -> str:
    if not hint:
        return "-"
    if width <= 0:
        return ""
    if len(hint) <= width:
        return hint
    if width == 1:
        return "…"
    return f"{hint[: width - 1]}…"


def _format_duration(ms: int | None) -> str:
    if not isinstance(ms, int):
        return "-"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"
