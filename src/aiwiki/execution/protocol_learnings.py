from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..app_protocol import PROTOCOL_LIBRARY
from ..app_state import append_runtime_history
from ..app_utils import (
    next_available_stem,
    parse_frontmatter,
    parse_iso_datetime,
    relative_path,
    sha256_bytes,
    slugify,
    utc_now,
)

LEARNINGS_DIR = "wiki/protocol-learnings"
AUDIT_STATE_PATH = ".aiwiki/state/protocol_learnings_age.json"
AGING_THRESHOLD_DAYS = 90
LEARNING_STATES = ("active", "stale", "demoted", "superseded", "archived")
ACTIVATION_REVERT_KEYS = (
    "activation_previous_state",
    "activation_previous_updated_at",
    "activation_previous_last_verified_at",
    "activation_verified_at",
)


def _known_protocols() -> set[str]:
    return set(PROTOCOL_LIBRARY.keys())


def _validate_source_refs(root: Path, refs: list[str]) -> None:
    # Canonicalize allowed roots once so path-traversal via ".." cannot sneak past
    # the string prefix check and land outside wiki/derived|elixirs.
    allowed_roots = [(root / prefix).resolve() for prefix in ("wiki/derived", "wiki/elixirs")]
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("source ref must be non-empty string")
        if not (ref.startswith("wiki/derived/") or ref.startswith("wiki/elixirs/")):
            raise ValueError(f"source ref must be under wiki/derived/ or wiki/elixirs/: {ref}")
        candidate = (root / ref).resolve()
        if not any(candidate == base or base in candidate.parents for base in allowed_roots):
            raise ValueError(f"source ref escapes allowed roots: {ref}")
        if not candidate.is_file():
            raise ValueError(f"source ref missing: {ref}")


def _check_source_refs_aging(root: Path, refs: list[str]) -> list[str]:
    """Aging-signal check: returns list of reasons if any ref is stale.

    Distinguishes from _validate_source_refs: here we only flag **expected** freshness
    signals (missing file, non-settled elixir). Structural issues (path traversal,
    bad prefix) are still raised by validate, not swallowed as stale.
    """
    reasons: list[str] = []
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            continue  # structural issue; caller decides (aging skips, verify raises)
        if not (ref.startswith("wiki/derived/") or ref.startswith("wiki/elixirs/")):
            continue  # structural
        candidate = (root / ref)
        if not candidate.is_file():
            reasons.append(f"source_ref 缺失: {ref}")
            continue
        if ref.startswith("wiki/elixirs/"):
            try:
                fm = parse_frontmatter(candidate.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                reasons.append(f"source_ref 读取失败: {ref} ({exc})")
                continue
            state = str(fm.get("elixir_state") or "")
            if state != "settled":
                reasons.append(f"source_ref elixir 非 settled: {ref} (当前 {state or 'unknown'})")
    return reasons


def _render_inserted_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=True)}")
        else:
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=True)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _scaffold_learning_markdown(*, learning_id: str, protocol: str, title: str, source_refs: list[str], state: str, created_at: str, updated_at: str, last_verified_at: str) -> str:
    frontmatter = {
        "learning_id": learning_id,
        "protocol": protocol,
        "title": title,
        "source_refs": source_refs,
        "state": state,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_verified_at": last_verified_at,
    }
    body = "\n".join([
        "# Protocol Learning",
        "",
        "## Lesson",
        "- Pending.",
        "",
        "## When to apply",
        "- Pending.",
        "",
        "## Evidence",
        "- Pending.",
        "",
    ])
    return _render_inserted_frontmatter(frontmatter) + body


def _atomic_write_text(path: Path, content: str) -> None:
    """Write file atomically: tmp in same dir + os.replace; keep original on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Cleanup best-effort; tmp may not exist if mkstemp failed earlier. Main exception re-raised.
        with suppress(FileNotFoundError):
            tmp_path.unlink()
        raise


def _split_frontmatter_body(text: str) -> tuple[dict[str, Any], str]:
    fm = parse_frontmatter(text)
    parts = text.split("---", 2)
    body = parts[-1].lstrip("\n") if len(parts) >= 3 else text
    return fm, body


def _rewrite_learning(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    content = _render_inserted_frontmatter(frontmatter) + body
    _atomic_write_text(path, content)


def _resolve_learning_id(learning_id: str) -> str:
    learning_id = (learning_id or "").strip()
    if not learning_id:
        raise ValueError("learning id 不能为空")
    if "/" in learning_id or "\\" in learning_id:
        raise ValueError(f"learning id 不允许包含路径分隔符: {learning_id!r}")
    if learning_id in {".", ".."}:
        raise ValueError(f"learning id 非法: {learning_id!r}")
    return learning_id


def _find_learning_path(root: Path, learning_id: str) -> Path:
    learning_id = _resolve_learning_id(learning_id)
    base = root / LEARNINGS_DIR
    if not base.is_dir():
        raise FileNotFoundError(f"learning not found: {learning_id}")
    for pdir in sorted(base.iterdir()):
        if not pdir.is_dir():
            continue
        candidate = pdir / f"{learning_id}.md"
        # Path-traversal safety: ensure resolved path is still under the protocol dir.
        if candidate.resolve().parent != pdir.resolve():
            raise ValueError(f"learning id 非法: {learning_id!r}")
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"learning not found: {learning_id}")


def _materialize_legacy_fields(fm: dict[str, Any]) -> dict[str, Any]:
    """If legacy file lacks state/last_verified_at, fill with safe defaults.

    Called only when a mutating op touches the file, to avoid leaving half-migrated
    files (contract §7: lazy migration with materialize on touch).
    """
    if "state" not in fm:
        fm["state"] = "active"
    if "last_verified_at" not in fm:
        fm["last_verified_at"] = str(fm.get("updated_at") or utc_now())
    return fm


def _effective_state(fm: dict[str, Any]) -> str:
    state = str(fm.get("state") or "").strip()
    if state not in LEARNING_STATES:
        return "active"  # legacy / missing / unknown -> active
    return state


def _effective_last_verified_at(fm: dict[str, Any]) -> str:
    value = str(fm.get("last_verified_at") or "").strip()
    if value:
        return value
    return str(fm.get("updated_at") or "")


def _has_frontmatter_fence(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("---\n") or stripped.startswith("---\r")


def _normalize_optional_learning_ref(value: Any, *, field_name: str, owner_id: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"learning graph inconsistent: {owner_id}.{field_name} must be string")
    raw = value.strip()
    if not raw:
        raise ValueError(f"learning graph inconsistent: {owner_id}.{field_name} must not be blank")
    return _resolve_learning_id(raw)


def _normalize_learning_ref_list(value: Any, *, field_name: str, owner_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"learning graph inconsistent: {owner_id}.{field_name} must be list")
    refs: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"learning graph inconsistent: {owner_id}.{field_name} entries must be strings")
        ref = _resolve_learning_id(item)
        if ref in seen:
            raise ValueError(f"learning graph inconsistent: duplicate {field_name} edge on {owner_id}: {ref}")
        seen.add(ref)
        refs.append(ref)
    return refs


def _assert_acyclic_supersede_graph(records: dict[str, dict[str, Any]]) -> None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            raise ValueError("learning graph inconsistent: supersede cycle detected: " + " -> ".join(cycle))
        if node in visited:
            return
        visiting.append(node)
        for child in records[node].get("supersedes", []):
            visit(child)
        visiting.pop()
        visited.add(node)

    for learning_id in sorted(records):
        visit(learning_id)


def _append_learning_threshold_history(root: Path, result: dict[str, Any], *, emitted_by: str) -> None:
    aged = result.get("aged")
    if not isinstance(aged, list) or not aged:
        return

    by_protocol: dict[str, list[dict[str, Any]]] = {}
    for item in aged:
        if not isinstance(item, dict):
            continue
        protocol = item.get("protocol")
        learning_id = item.get("learning_id")
        if not isinstance(protocol, str) or not protocol:
            continue
        if not isinstance(learning_id, str) or not learning_id:
            continue
        by_protocol.setdefault(protocol, []).append(item)

    for protocol, items in sorted(by_protocol.items()):
        learning_ids = sorted({str(item["learning_id"]) for item in items})
        learning_paths = sorted(
            {
                str(item.get("path") or "")
                for item in items
                if isinstance(item.get("path"), str) and str(item.get("path") or "")
            }
        )
        append_runtime_history(
            root,
            {
                "event_type": "learning-threshold",
                "occurred_at": result.get("run_at"),
                "protocol": protocol,
                "threshold_days": result.get("threshold_days"),
                "learning_ids": learning_ids,
                "aged_ids": learning_ids,
                "learning_paths": learning_paths,
                "audit_path": AUDIT_STATE_PATH,
                "emitted_by": emitted_by,
            },
        )


def _load_learning_records(root: Path) -> dict[str, dict[str, Any]]:
    base = root / LEARNINGS_DIR
    records: dict[str, dict[str, Any]] = {}
    if not base.is_dir():
        return records

    for pdir in sorted(base.iterdir()):
        if not pdir.is_dir():
            continue
        for md in sorted(pdir.glob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            fm, body = _split_frontmatter_body(text)
            if not _has_frontmatter_fence(text):
                raise ValueError(f"learning graph inconsistent: missing frontmatter fence: {relative_path(root, md)}")
            if not fm:
                raise ValueError(f"learning graph inconsistent: empty/corrupt frontmatter: {relative_path(root, md)}")

            learning_id = _resolve_learning_id(str(fm.get("learning_id") or md.stem))
            if learning_id != md.stem:
                raise ValueError(
                    f"learning graph inconsistent: learning_id/path mismatch: {learning_id} vs {md.stem}"
                )
            protocol = str(fm.get("protocol") or "").strip()
            if not protocol:
                raise ValueError(f"learning graph inconsistent: missing protocol on {learning_id}")
            if protocol != pdir.name:
                raise ValueError(
                    f"learning graph inconsistent: protocol/path mismatch on {learning_id}: {protocol} vs {pdir.name}"
                )
            raw_state = str(fm.get("state") or "").strip()
            if raw_state and raw_state not in LEARNING_STATES:
                raise ValueError(f"learning graph inconsistent: unknown state on {learning_id}: {raw_state}")
            state = _effective_state(fm)
            superseded_by = _normalize_optional_learning_ref(
                fm.get("superseded_by"),
                field_name="superseded_by",
                owner_id=learning_id,
            )
            supersedes = _normalize_learning_ref_list(
                fm.get("supersedes"),
                field_name="supersedes",
                owner_id=learning_id,
            )
            superseded_at = str(fm.get("superseded_at") or "").strip()

            if superseded_by == learning_id or learning_id in supersedes:
                raise ValueError(f"learning graph inconsistent: self-loop detected on {learning_id}")
            if state == "superseded":
                if superseded_by is None:
                    raise ValueError(f"learning graph inconsistent: superseded learning missing superseded_by: {learning_id}")
                if not superseded_at:
                    raise ValueError(f"learning graph inconsistent: superseded learning missing superseded_at: {learning_id}")
            else:
                if superseded_by is not None:
                    raise ValueError(
                        f"learning graph inconsistent: non-superseded learning carries superseded_by: {learning_id}"
                    )
                if superseded_at:
                    raise ValueError(
                        f"learning graph inconsistent: non-superseded learning carries superseded_at: {learning_id}"
                    )

            if learning_id in records:
                raise ValueError(f"learning graph inconsistent: duplicate learning_id across protocols: {learning_id}")
            records[learning_id] = {
                "learning_id": learning_id,
                "protocol": protocol,
                "state": state,
                "path": md,
                "frontmatter": fm,
                "body": body,
                "superseded_by": superseded_by,
                "supersedes": supersedes,
            }

    for learning_id, record in records.items():
        for target_id in record["supersedes"]:
            target = records.get(target_id)
            if target is None:
                raise ValueError(
                    f"learning graph inconsistent: supersedes target missing: {learning_id} -> {target_id}"
                )
            if target["protocol"] != record["protocol"]:
                raise ValueError(
                    f"learning graph inconsistent: cross-protocol supersede edge: {learning_id} -> {target_id}"
                )
            if target["state"] != "superseded":
                raise ValueError(
                    f"learning graph inconsistent: supersedes target not marked superseded: {learning_id} -> {target_id}"
                )
            if target["superseded_by"] != learning_id:
                raise ValueError(
                    f"learning graph inconsistent: missing/incorrect backref: {learning_id} -> {target_id}"
                )
        if record["superseded_by"] is not None:
            replacement = records.get(record["superseded_by"])
            if replacement is None:
                raise ValueError(
                    f"learning graph inconsistent: superseded_by target missing: {learning_id} -> {record['superseded_by']}"
                )
            if replacement["protocol"] != record["protocol"]:
                raise ValueError(
                    f"learning graph inconsistent: cross-protocol superseded_by edge: {learning_id} -> {record['superseded_by']}"
                )
            if learning_id not in replacement["supersedes"]:
                raise ValueError(
                    f"learning graph inconsistent: missing replacement edge for backref: {learning_id} -> {record['superseded_by']}"
                )

    _assert_acyclic_supersede_graph(records)
    return records


def _get_validated_learning_record(root: Path, learning_id: str) -> dict[str, Any]:
    resolved_id = _resolve_learning_id(learning_id)
    records = _load_learning_records(root)
    record = records.get(resolved_id)
    if record is None:
        raise FileNotFoundError(f"learning not found: {resolved_id}")
    return record


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def add_learning(root: Path, protocol: str, *, title: str, source_refs: list[str] | None = None) -> dict[str, Any]:
    if protocol not in _known_protocols():
        raise ValueError(f"unknown protocol: {protocol}; known: {sorted(_known_protocols())}")
    refs = list(source_refs or [])
    _validate_source_refs(root, refs)
    directory = root / LEARNINGS_DIR / protocol
    directory.mkdir(parents=True, exist_ok=True)
    seed = f"learn-{protocol}-{slugify(title)[:40]}-{sha256_bytes(title.encode())[:8]}"
    learning_id = next_available_stem(directory, seed)
    path = directory / f"{learning_id}.md"
    now = utc_now()
    _atomic_write_text(
        path,
        _scaffold_learning_markdown(
            learning_id=learning_id,
            protocol=protocol,
            title=title,
            source_refs=refs,
            state="active",
            created_at=now,
            updated_at=now,
            last_verified_at=now,
        ),
    )
    return {
        "learning_id": learning_id,
        "path": f"{LEARNINGS_DIR}/{protocol}/{learning_id}.md",
        "protocol": protocol,
        "title": title,
        "source_refs": refs,
        "state": "active",
    }


def list_learnings(
    root: Path,
    protocol: str | None = None,
    *,
    state_filter: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    if protocol is not None and protocol not in _known_protocols():
        raise ValueError(f"unknown protocol: {protocol}; known: {sorted(_known_protocols())}")
    if state_filter is not None and state_filter not in LEARNING_STATES:
        raise ValueError(f"unknown state: {state_filter}; known: {LEARNING_STATES}")
    base = root / LEARNINGS_DIR
    if not base.is_dir():
        return []
    protocols = [protocol] if protocol else sorted([p.name for p in base.iterdir() if p.is_dir()])
    # --state archived implicitly reveals archived entries (contract §4).
    show_archived = include_archived or (state_filter == "archived")
    results: list[dict[str, Any]] = []
    for proto in protocols:
        pdir = base / proto
        if not pdir.is_dir():
            continue
        for md in sorted(pdir.glob("*.md")):
            fm = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            state = _effective_state(fm)
            if state_filter is not None and state != state_filter:
                continue
            if state == "archived" and not show_archived:
                continue
            refs = fm.get("source_refs") or []
            results.append({
                "learning_id": str(fm.get("learning_id") or md.stem),
                "protocol": str(fm.get("protocol") or proto),
                "title": str(fm.get("title") or ""),
                "state": state,
                "updated_at": str(fm.get("updated_at") or ""),
                "last_verified_at": _effective_last_verified_at(fm),
                "source_refs_count": len([r for r in refs if isinstance(r, str)]),
                "path": f"{LEARNINGS_DIR}/{proto}/{md.name}",
            })
    return results


def show_learning(root: Path, learning_id: str) -> dict[str, Any]:
    path = _find_learning_path(root, learning_id)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_frontmatter_body(text)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "frontmatter": fm,
        "body": body,
        "path": f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}",
        "state": _effective_state(fm),
    }


def load_learnings_for_protocol(root: Path, protocol: str) -> list[dict[str, Any]]:
    records = _load_learning_records(root)
    results: list[dict[str, Any]] = []
    for record in sorted(
        (item for item in records.values() if item["protocol"] == protocol),
        key=lambda item: item["path"].name,
    ):
        if record["state"] != "active":
            continue  # contract §8: only active learnings injected into ask
        fm = record["frontmatter"]
        body = record["body"]
        lesson = ""
        if "## Lesson" in body:
            lesson_part = body.split("## Lesson", 1)[1]
            if "\n## " in lesson_part:
                lesson = lesson_part.split("\n## ", 1)[0].strip()
            else:
                lesson = lesson_part.strip()
            lesson = lesson.lstrip("\n").strip()
            if lesson.startswith("-"):
                lesson = lesson[1:].strip()
        results.append({"learning_id": record["learning_id"], "title": str(fm.get("title") or ""), "lesson": lesson})
    return results


# -----------------------------------------------------------------------------
# Lifecycle: verify / demote / archive / age
# -----------------------------------------------------------------------------

def verify_learning(root: Path, learning_id: str) -> dict[str, Any]:
    record = _get_validated_learning_record(root, learning_id)
    path = record["path"]
    fm = dict(record["frontmatter"])
    body = record["body"]
    # archived / superseded are terminal in protocol-learning lifecycle.
    prev_state_raw = _effective_state(_materialize_legacy_fields(dict(fm)))
    if prev_state_raw in {"archived", "superseded"}:
        raise ValueError(
            f"verify 拒绝: learning {learning_id} 当前 state={prev_state_raw}，terminal state 不允许反向迁移"
        )
    refs = [r for r in (fm.get("source_refs") or []) if isinstance(r, str)]
    # contract Acceptance #6: verify must re-check source_refs; reject on hard failures.
    # Structural issues (path traversal / bad prefix) bubble up as ValueError from validate.
    _validate_source_refs(root, refs)
    # Also reject non-settled elixir refs explicitly.
    aging_reasons = _check_source_refs_aging(root, refs)
    if aging_reasons:
        raise ValueError(
            "verify 拒绝: source_refs 未通过硬校验: " + "; ".join(aging_reasons)
        )
    fm = _materialize_legacy_fields(fm)
    prev_state = _effective_state(fm)
    previous_updated_at = str(fm.get("updated_at") or "")
    previous_last_verified_at = str(fm.get("last_verified_at") or "")
    now = utc_now()
    fm["state"] = "active"
    fm["last_verified_at"] = now
    fm["updated_at"] = now
    for key in ACTIVATION_REVERT_KEYS:
        fm.pop(key, None)
    if prev_state == "stale":
        fm["activation_previous_state"] = "stale"
        fm["activation_previous_updated_at"] = previous_updated_at
        fm["activation_previous_last_verified_at"] = previous_last_verified_at
        fm["activation_verified_at"] = now
    _rewrite_learning(path, fm, body)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "path": f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}",
        "previous_state": prev_state,
        "state": "active",
        "last_verified_at": now,
    }


def revert_learning_activation(root: Path, learning_id: str, *, note: str | None = None) -> dict[str, Any]:
    record = _get_validated_learning_record(root, learning_id)
    path = record["path"]
    fm = dict(record["frontmatter"])
    body = record["body"]
    fm = _materialize_legacy_fields(fm)
    current_state = _effective_state(fm)
    if current_state != "active":
        raise ValueError(
            f"revert activate 拒绝: learning {learning_id} 当前 state={current_state}，只能回滚 active learning"
        )
    previous_state = str(fm.get("activation_previous_state") or "").strip()
    if previous_state != "stale":
        raise ValueError(
            f"revert activate 拒绝: learning {learning_id} 缺少 stale -> active activation metadata"
        )
    activation_verified_at = str(fm.get("activation_verified_at") or "").strip()
    if not activation_verified_at:
        raise ValueError(
            f"revert activate 拒绝: learning {learning_id} 缺少 activation_verified_at"
        )
    if str(fm.get("last_verified_at") or "") != activation_verified_at:
        raise ValueError(
            f"revert activate 拒绝: learning {learning_id} 已在 activation 后再次 verify，不能自动回滚"
        )

    now = utc_now()
    previous_last_verified_at = str(fm.get("activation_previous_last_verified_at") or "")
    fm["state"] = "stale"
    if previous_last_verified_at:
        fm["last_verified_at"] = previous_last_verified_at
    fm["updated_at"] = now
    for key in ACTIVATION_REVERT_KEYS:
        fm.pop(key, None)
    _rewrite_learning(path, fm, body)

    rel_path = f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}"
    event: dict[str, Any] = {
        "event_type": "protocol-learning-activation-reverted",
        "subject_kind": "protocol_learning",
        "occurred_at": now,
        "protocol": path.parent.name,
        "learning_id": learning_id,
        "path": rel_path,
        "previous_state": "active",
        "state": "stale",
        "activation_verified_at": activation_verified_at,
    }
    if note:
        event["note"] = note
    append_runtime_history(root, event)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "path": rel_path,
        "previous_state": "active",
        "state": "stale",
        "activation_verified_at": activation_verified_at,
        "reverted_at": now,
        "runtime_history_event": event["event_type"],
    }


def demote_learning(root: Path, learning_id: str) -> dict[str, Any]:
    record = _get_validated_learning_record(root, learning_id)
    path = record["path"]
    fm = dict(record["frontmatter"])
    body = record["body"]
    fm = _materialize_legacy_fields(fm)
    prev_state = _effective_state(fm)
    if prev_state == "superseded":
        raise ValueError(
            f"demote 拒绝: learning {learning_id} 当前 state=superseded，superseded 为终态"
        )
    if prev_state not in ("active", "stale"):
        raise ValueError(
            f"demote 拒绝: learning {learning_id} 当前 state={prev_state}，只能从 active 或 stale 迁移"
        )
    now = utc_now()
    fm["state"] = "demoted"
    fm["updated_at"] = now
    _rewrite_learning(path, fm, body)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "path": f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}",
        "previous_state": prev_state,
        "state": "demoted",
    }


def archive_learning(root: Path, learning_id: str) -> dict[str, Any]:
    record = _get_validated_learning_record(root, learning_id)
    path = record["path"]
    fm = dict(record["frontmatter"])
    body = record["body"]
    fm = _materialize_legacy_fields(fm)
    prev_state = _effective_state(fm)
    if prev_state == "archived":
        raise ValueError(f"archive 拒绝: learning {learning_id} 已是 archived")
    if prev_state == "superseded":
        raise ValueError(
            f"archive 拒绝: learning {learning_id} 当前 state=superseded，superseded 为终态"
        )
    now = utc_now()
    fm["state"] = "archived"
    fm["archived_at"] = now
    fm["updated_at"] = now
    _rewrite_learning(path, fm, body)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "path": f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}",
        "previous_state": prev_state,
        "state": "archived",
        "archived_at": now,
    }


def supersede_learning(root: Path, replacement_id: str, superseded_ids: list[str]) -> dict[str, Any]:
    replacement_id = _resolve_learning_id(replacement_id)
    targets: list[str] = []
    seen: set[str] = set()
    for raw in superseded_ids:
        target_id = _resolve_learning_id(raw)
        if target_id in seen:
            raise ValueError(f"supersede 拒绝: duplicate target id: {target_id}")
        seen.add(target_id)
        targets.append(target_id)
    if not targets:
        raise ValueError("supersede 拒绝: 至少提供一个 target learning id")
    if replacement_id in seen:
        raise ValueError(f"supersede 拒绝: replacement {replacement_id} 不能 supersede 自己")

    records = _load_learning_records(root)
    replacement = records.get(replacement_id)
    if replacement is None:
        raise FileNotFoundError(f"learning not found: {replacement_id}")
    replacement_state = replacement["state"]
    if replacement_state != "active":
        raise ValueError(
            f"supersede 拒绝: replacement learning {replacement_id} 当前 state={replacement_state}，必须是 active"
        )

    for target_id in targets:
        target = records.get(target_id)
        if target is None:
            raise FileNotFoundError(f"learning not found: {target_id}")
        if target["protocol"] != replacement["protocol"]:
            raise ValueError(
                f"supersede 拒绝: cross-protocol 不允许: {replacement_id}({replacement['protocol']}) -> {target_id}({target['protocol']})"
            )
        if target["state"] in {"superseded", "archived"}:
            raise ValueError(
                f"supersede 拒绝: target learning {target_id} 当前 state={target['state']}，不能再次 supersede"
            )
        if target_id in replacement["supersedes"]:
            raise ValueError(
                f"supersede 拒绝: duplicate edge 已存在: {replacement_id} -> {target_id}"
            )

    now = utc_now()
    replacement_fm = dict(replacement["frontmatter"])
    replacement_supersedes = list(replacement["supersedes"])
    replacement_supersedes.extend(targets)
    replacement_fm["supersedes"] = replacement_supersedes
    replacement_fm["updated_at"] = now

    updated_targets: list[dict[str, Any]] = []
    for target_id in targets:
        target = records[target_id]
        fm = dict(target["frontmatter"])
        fm["state"] = "superseded"
        fm["superseded_by"] = replacement_id
        fm["superseded_at"] = now
        fm["updated_at"] = now
        updated_targets.append({"record": target, "frontmatter": fm})

    preview_records = {
        learning_id: {
            **record,
            "frontmatter": dict(record["frontmatter"]),
            "superseded_by": record["superseded_by"],
            "supersedes": list(record["supersedes"]),
            "state": record["state"],
        }
        for learning_id, record in records.items()
    }
    preview_records[replacement_id]["frontmatter"] = replacement_fm
    preview_records[replacement_id]["supersedes"] = list(replacement_supersedes)
    for item in updated_targets:
        target_record = item["record"]
        target_id = target_record["learning_id"]
        preview_records[target_id]["frontmatter"] = item["frontmatter"]
        preview_records[target_id]["state"] = "superseded"
        preview_records[target_id]["superseded_by"] = replacement_id
    _assert_acyclic_supersede_graph(preview_records)

    _rewrite_learning(replacement["path"], replacement_fm, replacement["body"])
    for item in updated_targets:
        target_record = item["record"]
        _rewrite_learning(target_record["path"], item["frontmatter"], target_record["body"])

    return {
        "replacement_learning_id": replacement_id,
        "protocol": replacement["protocol"],
        "state": replacement_state,
        "superseded_ids": list(targets),
        "supersedes": list(replacement_supersedes),
        "updated_at": now,
    }


def age_learnings(
    root: Path,
    protocol: str | None = None,
    *,
    apply: bool = False,
    threshold_days: int = AGING_THRESHOLD_DAYS,
    emitted_by: str = "user",
) -> dict[str, Any]:
    """Scan learnings and mark stale ones. dry-run by default.

    Returns: {"apply": bool, "aged": [...], "skipped": [...], "errors": [...], "threshold_days": N, "run_at": iso}
    - aged: active learnings transitioned (or would transition) to stale, with reasons
    - skipped: non-active learnings reported but not mutated (stale/demoted/archived)
    - errors: structural/parse issues (non-aging signal); never silently coerced to stale
    """
    if protocol is not None and protocol not in _known_protocols():
        raise ValueError(f"unknown protocol: {protocol}; known: {sorted(_known_protocols())}")
    base = root / LEARNINGS_DIR
    aged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    run_at = now_dt.isoformat()
    threshold_delta = timedelta(days=threshold_days)

    try:
        records = _load_learning_records(root)
    except ValueError as exc:
        result = {
            "apply": apply,
            "run_at": run_at,
            "threshold_days": threshold_days,
            "aged": [],
            "aged_ids": [],
            "skipped": [],
            "errors": [{"reason": str(exc)}],
        }
        if apply:
            _write_age_audit(root, result)
        return result

    if base.is_dir():
        protocols = [protocol] if protocol else sorted([p.name for p in base.iterdir() if p.is_dir()])
        for proto in protocols:
            for record in sorted(
                (item for item in records.values() if item["protocol"] == proto),
                key=lambda item: item["path"].name,
            ):
                rel_path = f"{LEARNINGS_DIR}/{proto}/{record['path'].name}"
                fm = dict(record["frontmatter"])
                body = record["body"]
                refs = [r for r in (fm.get("source_refs") or []) if isinstance(r, str)]
                try:
                    for ref in refs:
                        if not ref.strip():
                            raise ValueError(f"空 source_ref in {rel_path}")
                        if not (ref.startswith("wiki/derived/") or ref.startswith("wiki/elixirs/")):
                            raise ValueError(f"非法 source_ref 目录: {ref}")
                        candidate = (root / ref).resolve()
                        allowed_roots = [(root / p).resolve() for p in ("wiki/derived", "wiki/elixirs")]
                        if not any(candidate == b or b in candidate.parents for b in allowed_roots):
                            raise ValueError(f"source_ref 越界: {ref}")
                except ValueError as exc:
                    errors.append({
                        "learning_id": record["learning_id"],
                        "protocol": proto,
                        "path": rel_path,
                        "reason": str(exc),
                    })
                    continue

                state = record["state"]
                if state != "active":
                    skipped.append({
                        "learning_id": record["learning_id"],
                        "protocol": proto,
                        "path": rel_path,
                        "state": state,
                    })
                    continue

                reasons: list[str] = []
                reasons.extend(_check_source_refs_aging(root, refs))
                last_verified_str = _effective_last_verified_at(fm)
                last_verified_dt = parse_iso_datetime(last_verified_str) if last_verified_str else None
                if last_verified_dt is None:
                    reasons.append("缺失 last_verified_at 且 updated_at 无法解析")
                else:
                    if now_dt - last_verified_dt > threshold_delta:
                        age_days = (now_dt - last_verified_dt).days
                        reasons.append(f"超过 {threshold_days} 天未 verify (当前 {age_days} 天)")

                if not reasons:
                    continue

                entry = {
                    "learning_id": record["learning_id"],
                    "protocol": proto,
                    "path": rel_path,
                    "previous_state": state,
                    "new_state": "stale",
                    "reasons": reasons,
                }
                aged.append(entry)

                if apply:
                    fm = _materialize_legacy_fields(fm)
                    fm["state"] = "stale"
                    fm["updated_at"] = run_at
                    _rewrite_learning(record["path"], fm, body)

    result = {
        "apply": apply,
        "run_at": run_at,
        "threshold_days": threshold_days,
        "aged": aged,
        "aged_ids": [e["learning_id"] for e in aged],
        "skipped": skipped,
        "errors": errors,
    }

    if apply:
        _write_age_audit(root, result)
        _append_learning_threshold_history(root, result, emitted_by=emitted_by)

    return result


def _write_age_audit(root: Path, result: dict[str, Any]) -> None:
    audit_path = root / AUDIT_STATE_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(audit_path, json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    from .audit_preview import append_universal_audit_record, protocol_learnings_age_source_ref

    append_universal_audit_record(
        root,
        source_stream="protocol_learnings_age",
        source_ref=protocol_learnings_age_source_ref(result),
        document=result,
    )
