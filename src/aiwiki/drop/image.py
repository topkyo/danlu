"""Image drop handler (OCR + optional vision-LLM analysis)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import LLMConfig, _backend_supports_image_analysis
from ..drop_helpers import timestamped_stem
from ..llm import LLMError, create_backend_client
from ..protocol.scaffold import ensure_layout
from ..render.paths import append_wiki_log
from ..utils.io import atomic_copy_file, runtime_write_lock
from ..utils.path import relative_path
from .common import (
    _LOCAL_IMAGE_MAX_BYTES,
    _append_manifest_entry,
    _append_raw_added_history,
    _assert_file_size,
    _assert_supported_image_mime,
    _cleanup_tmp_dir,
    _collect_binary_to_tmp,
    _normalize_text,
    _rollback_created_paths,
    _snapshot_append_files,
    _truncate_append_files,
    _truncate_text,
    _unique_path,
)

MIME_DETECT_TIMEOUT_SECONDS = 5
IMAGE_OCR_TIMEOUT_SECONDS = 60
_MAX_TEXT_CHARS = 120000
_OCR_TEXT_LIMIT = 20000


def drop_image(
    root: Path,
    source: str,
    title: str | None = None,
    enable_vision: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    collection = _collect_image(root, source, title, enable_vision, client)
    try:
        _validate_image(collection)
        with runtime_write_lock(root):
            return _materialize_image(root, source, title, collection)
    finally:
        _cleanup_tmp_dir(collection["tmp_dir"])


def _collect_image(
    root: Path,
    source: str,
    title: str | None = None,
    enable_vision: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    collection = _collect_binary_to_tmp(
        root, source, prefix="aiwiki-drop-image-", preferred_slug=title or Path(source).stem
    )
    try:
        tmp_path = collection["tmp_path"]
        mime = _detect_mime_type(tmp_path)
        _assert_supported_image_mime(mime)
        _assert_file_size(tmp_path, _LOCAL_IMAGE_MAX_BYTES, "image asset")
        width, height = _image_dimensions(tmp_path)
        ocr_text = _extract_image_text(tmp_path)
        vision_result = _analyze_image_asset(
            root,
            tmp_path,
            mime=mime,
            width=width,
            height=height,
            ocr_text=ocr_text,
            client=client,
            enable_vision=enable_vision,
        )
    except Exception:
        _cleanup_tmp_dir(collection["tmp_dir"])
        raise
    collection.update(
        {
            "mime": mime,
            "width": width,
            "height": height,
            "ocr_text": ocr_text,
            "vision_result": vision_result,
        }
    )
    return collection


def _validate_image(collection: dict[str, Any]) -> None:
    _assert_supported_image_mime(collection["mime"])
    _assert_file_size(collection["tmp_path"], _LOCAL_IMAGE_MAX_BYTES, "image asset")


def _materialize_image(root: Path, source: str, title: str | None, collection: dict[str, Any]) -> dict[str, Any]:
    del source
    tmp_path = collection["tmp_path"]
    original_path = collection["original_path"]
    mime = collection["mime"]
    width = collection["width"]
    height = collection["height"]
    ocr_text = collection["ocr_text"]
    vision_result = collection["vision_result"]
    visual_analysis = vision_result["analysis"]
    vision_backend = vision_result["backend"]
    vision_status = vision_result["status"]
    display_title = title or Path(original_path).stem or tmp_path.stem
    asset_path = _unique_path(
        root / "raw" / "assets", timestamped_stem(display_title), tmp_path.suffix.lower() or ".bin"
    )
    created_paths: list[Path] = []
    append_file_sizes = _snapshot_append_files(root)
    try:
        atomic_copy_file(tmp_path, asset_path, fsync=True)
        created_paths.append(asset_path)
        entry = _append_manifest_entry(
            root,
            stored_path=asset_path,
            original_path=original_path,
            source_type="image-drop",
            title=display_title,
        )
        append_wiki_log(
            root,
            "ingest",
            display_title,
            [
                "source_type: `image-drop`",
                f"asset_path: `{relative_path(root, asset_path)}`",
                f"vision_status: `{vision_status}`",
            ],
        )
        _append_raw_added_history(
            root,
            material="image",
            stored_path=asset_path,
            original_path=original_path,
            source_type="image-drop",
            title=display_title,
            entry_id=entry["id"],
        )
    except Exception:
        _rollback_created_paths(created_paths)
        _truncate_append_files(append_file_sizes)
        raise
    return {
        "material": "image",
        "asset_path": relative_path(root, asset_path),
        "stored_path": relative_path(root, asset_path),
        "original_path": original_path,
        "mime_type": mime,
        "dimensions": {"width": width, "height": height},
        "ocr_text_present": bool(ocr_text),
        "visual_analysis_present": bool(visual_analysis),
        "vision_backend": vision_backend,
        "vision_status": vision_status,
        "title": display_title,
    }


def _detect_mime_type(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["file", "--brief", "--mime-type", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=MIME_DETECT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "application/octet-stream"
    mime = completed.stdout.strip()
    return mime or "application/octet-stream"


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        data = handle.read(32)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(path)
    return None, None


def _jpeg_dimensions(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        handle.read(2)
        while True:
            marker_prefix = handle.read(1)
            if marker_prefix != b"\xff":
                return None, None
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb"}:
                segment_length = int.from_bytes(handle.read(2), "big")
                handle.read(1)
                height = int.from_bytes(handle.read(2), "big")
                width = int.from_bytes(handle.read(2), "big")
                return width, height
            if marker in {b"\xd8", b"\xd9"}:
                return None, None
            segment_length = int.from_bytes(handle.read(2), "big")
            handle.seek(segment_length - 2, os.SEEK_CUR)


def _extract_image_text(path: Path) -> str:
    if shutil.which("tesseract") is None:
        return ""
    try:
        completed = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            text=True,
            check=False,
            timeout=IMAGE_OCR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return _truncate_text(_normalize_text(completed.stdout), _OCR_TEXT_LIMIT)


def _analyze_image_asset(
    root: Path,
    image_path: Path,
    *,
    mime: str,
    width: int | None,
    height: int | None,
    ocr_text: str,
    client: Any | None,
    enable_vision: bool,
) -> dict[str, str]:
    if not enable_vision:
        return {"analysis": "", "backend": "", "status": "disabled"}
    effective_client = client or _maybe_create_image_client(root)
    if effective_client is None or not hasattr(effective_client, "analyze_image"):
        return {"analysis": "", "backend": "", "status": "skipped"}

    system_prompt = (
        "You analyze images for a local-first research wiki. "
        "Return only markdown. "
        "Describe observable content, readable text, layout, chart or diagram structure, and notable signals. "
        "Do not invent details that are not visible in the image."
    )
    try:
        asset_label = relative_path(root, image_path)
    except ValueError:
        asset_label = str(image_path)
    user_prompt = "\n".join(
        [
            "Analyze this image asset for a source note.",
            f"- Asset path: `{asset_label}`",
            f"- MIME type: `{mime}`",
            f"- Dimensions: `{width or 'unknown'}x{height or 'unknown'}`",
            "",
            "Use 4 to 8 markdown bullet points, then finish with `- Confidence: low|medium|high`.",
            "If OCR text is provided, you may use it as supporting evidence but should still focus on what is visually observable.",
            "",
            "OCR excerpt:",
            ocr_text or "(none)",
        ]
    )
    backend_name = _client_backend_name(effective_client)
    try:
        result = effective_client.analyze_image(system_prompt, user_prompt, image_path)
    except (LLMError, RuntimeError, OSError) as exc:
        _record_image_llm_attempt(root, effective_client, status="failed", error=str(exc))
        return {"analysis": "", "backend": backend_name, "status": "failed"}
    analysis = _normalize_text(result.text)
    if not analysis:
        _record_image_llm_attempt(root, effective_client, status="failed", error="empty analysis")
        return {"analysis": "", "backend": backend_name, "status": "failed"}
    _record_image_llm_attempt(root, effective_client, status="success", usage=getattr(result, "usage", None))
    return {"analysis": analysis, "backend": backend_name, "status": "generated"}


def _record_image_llm_attempt(
    root: Path,
    client: Any,
    *,
    status: str,
    error: str = "",
    usage: dict[str, Any] | None = None,
) -> None:
    """Best-effort LLM receipt for the vision path; never breaks image drop."""

    try:
        from aiwiki.runner.receipts import _build_llm_audit, record_llm_attempt

        record_llm_attempt(
            root,
            {"event": "drop-image-vision"},
            _build_llm_audit(client),
            status=status,
            error=error,
            usage=usage,
            error_class="llm" if status != "success" else "",
        )
    except Exception:  # noqa: BLE001 - observability must not break the drop path
        logging.getLogger("aiwiki").warning("image vision LLM receipt append failed", exc_info=True)


def _maybe_create_image_client(root: Path) -> Any | None:
    try:
        config = LLMConfig.from_env()
    except RuntimeError:
        return None
    if not _backend_supports_image_analysis(config.backend, config.model):
        return None
    return create_backend_client(config, root)


def _client_backend_name(client: Any) -> str:
    config = getattr(client, "config", None)
    backend = getattr(config, "backend", "")
    return backend if isinstance(backend, str) else ""
