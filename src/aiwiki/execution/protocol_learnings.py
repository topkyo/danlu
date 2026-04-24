from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..app_protocol import PROTOCOL_LIBRARY
from ..app_utils import next_available_stem, parse_frontmatter, parse_iso_datetime, sha256_bytes, slugify, utc_now

LEARNINGS_DIR = "wiki/protocol-learnings"
AUDIT_STATE_PATH = ".aiwiki/state/protocol_learnings_age.json"
AGING_THRESHOLD_DAYS = 90
LEARNING_STATES = ("active", "stale", "demoted", "archived")


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
    base = root / LEARNINGS_DIR / protocol
    if not base.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for md in sorted(base.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if _effective_state(fm) != "active":
            continue  # contract §8: only active learnings injected into ask
        body = text.split("---", 2)[-1].lstrip("\n")
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
        results.append({"learning_id": str(fm.get("learning_id") or md.stem), "title": str(fm.get("title") or ""), "lesson": lesson})
    return results


# -----------------------------------------------------------------------------
# Lifecycle: verify / demote / archive / age
# -----------------------------------------------------------------------------

def verify_learning(root: Path, learning_id: str) -> dict[str, Any]:
    path = _find_learning_path(root, learning_id)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_frontmatter_body(text)
    # contract Acceptance #8: archived 是终态，verify 不能把它拉回 active。
    prev_state_raw = _effective_state(_materialize_legacy_fields(dict(fm)))
    if prev_state_raw == "archived":
        raise ValueError(
            f"verify 拒绝: learning {learning_id} 已 archived，archived 为终态，不允许反向迁移"
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
    now = utc_now()
    fm["state"] = "active"
    fm["last_verified_at"] = now
    fm["updated_at"] = now
    _rewrite_learning(path, fm, body)
    return {
        "learning_id": learning_id,
        "protocol": path.parent.name,
        "path": f"{LEARNINGS_DIR}/{path.parent.name}/{path.name}",
        "previous_state": prev_state,
        "state": "active",
        "last_verified_at": now,
    }


def demote_learning(root: Path, learning_id: str) -> dict[str, Any]:
    path = _find_learning_path(root, learning_id)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_frontmatter_body(text)
    fm = _materialize_legacy_fields(fm)
    prev_state = _effective_state(fm)
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
    path = _find_learning_path(root, learning_id)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_frontmatter_body(text)
    fm = _materialize_legacy_fields(fm)
    prev_state = _effective_state(fm)
    if prev_state == "archived":
        raise ValueError(f"archive 拒绝: learning {learning_id} 已是 archived")
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


def age_learnings(
    root: Path,
    protocol: str | None = None,
    *,
    apply: bool = False,
    threshold_days: int = AGING_THRESHOLD_DAYS,
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

    if base.is_dir():
        protocols = [protocol] if protocol else sorted([p.name for p in base.iterdir() if p.is_dir()])
        for proto in protocols:
            pdir = base / proto
            if not pdir.is_dir():
                continue
            for md in sorted(pdir.glob("*.md")):
                rel_path = f"{LEARNINGS_DIR}/{proto}/{md.name}"
                try:
                    text = md.read_text(encoding="utf-8", errors="replace")
                    fm, body = _split_frontmatter_body(text)
                except Exception as exc:
                    errors.append({
                        "learning_id": md.stem,
                        "protocol": proto,
                        "path": rel_path,
                        "reason": f"解析失败: {exc}",
                    })
                    continue

                # contract Acceptance #11: frontmatter 结构损坏（有 --- 分隔但 parse 为空 / 关键字段缺失）
                # 必须进 errors 通道，禁止静默当成 stale/unknown。
                stripped = text.lstrip()
                has_fm_fence = stripped.startswith("---\n") or stripped.startswith("---\r")
                if has_fm_fence and not fm:
                    errors.append({
                        "learning_id": md.stem,
                        "protocol": proto,
                        "path": rel_path,
                        "reason": "frontmatter 解析为空 dict（可能 YAML 损坏）",
                    })
                    continue
                if not has_fm_fence:
                    errors.append({
                        "learning_id": md.stem,
                        "protocol": proto,
                        "path": rel_path,
                        "reason": "缺失 frontmatter 分隔符",
                    })
                    continue

                refs = [r for r in (fm.get("source_refs") or []) if isinstance(r, str)]
                # Structural validation (path traversal / bad prefix) -> error channel, not stale.
                try:
                    # Only validate structural constraints; missing-file is demoted to aging signal below.
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
                        "learning_id": str(fm.get("learning_id") or md.stem),
                        "protocol": proto,
                        "path": rel_path,
                        "reason": str(exc),
                    })
                    continue

                state = _effective_state(fm)
                if state != "active":
                    skipped.append({
                        "learning_id": str(fm.get("learning_id") or md.stem),
                        "protocol": proto,
                        "path": rel_path,
                        "state": state,
                    })
                    continue

                reasons: list[str] = []
                # Freshness signal 1: source_ref aging
                reasons.extend(_check_source_refs_aging(root, refs))
                # Freshness signal 2: last_verified_at age
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
                    "learning_id": str(fm.get("learning_id") or md.stem),
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
                    _rewrite_learning(md, fm, body)

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
        audit_path = root / AUDIT_STATE_PATH
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(audit_path, json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    return result
