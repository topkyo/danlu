"""Library + argv/dispatch smoke for previously zero-coverage CLI surfaces.

Covers entry functions and ``cli.dispatch.main`` argv paths for: run-nightly,
watch, review-queue, alchemy demote/revert, drop pdf, drop image.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from aiwiki.cli.dispatch import main as cli_main
from aiwiki.cli.dispatch_helpers import review_queue_command
from aiwiki.drop.image import drop_image
from aiwiki.drop.pdf import drop_pdf
from aiwiki.execution.alchemy import promote_elixir
from aiwiki.execution.alchemy_helpers import _candidate_path, _parse_elixir_frontmatter, _settled_path
from aiwiki.protocol.scaffold import ensure_layout
from aiwiki.runner.alchemy import run_alchemy_demote
from aiwiki.runner.automation import watch_inbox
from aiwiki.runner.workflows import run_nightly
from tests.test_alchemy_revert import ELIXIR_ID, _seed_promote_vault

_MIN_PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_run_nightly_smoke(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    result = run_nightly(tmp_path, compile_limit=1)
    assert result["compile"] is not None
    assert result["lint"] is not None
    assert result["state_path"].endswith("nightly-health.json")
    assert (tmp_path / result["state_path"]).is_file()
    assert result["receipt_path"]


def test_watch_inbox_zero_cycles(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    result = watch_inbox(tmp_path, interval_seconds=0.01, max_cycles=0, process_initial=True)
    assert result["watch_cycles"] == 0
    assert result["processed_runs"] == 1
    assert result["last_result"] is not None


def test_review_queue_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_layout(tmp_path)
    code = review_queue_command(tmp_path, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["buckets"], dict)
    assert payload["total"] == 0


def test_drop_pdf_local(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(_MIN_PDF)
    result = drop_pdf(tmp_path, str(pdf), title="Sample PDF")
    assert result["material"] == "pdf"
    assert result["asset_path"].startswith("raw/assets/")
    assert (tmp_path / result["asset_path"]).is_file()


def test_drop_image_local_no_vision(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    image = tmp_path / "pixel.png"
    image.write_bytes(_MIN_PNG)
    result = drop_image(tmp_path, str(image), title="Pixel", enable_vision=False)
    assert result["material"] == "image"
    assert result["vision_status"] == "disabled"
    assert (tmp_path / result["asset_path"]).is_file()


def test_alchemy_demote_after_promote(tmp_path: Path) -> None:
    _seed_promote_vault(tmp_path)
    promote_elixir(tmp_path, elixir_id=ELIXIR_ID, note="cli-surface promote")
    path = run_alchemy_demote(tmp_path, elixir_id=ELIXIR_ID, note="cli-surface demote")
    assert path.is_file()
    assert path.name == f"{ELIXIR_ID}.md"
    assert not (tmp_path / "wiki" / "elixirs" / f"{ELIXIR_ID}.md").exists()


def _cli_json(argv: list[str]) -> dict:
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli_main(argv)
    assert code == 0, buf.getvalue()
    return json.loads(buf.getvalue())


def test_argv_run_nightly(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    payload = _cli_json(["--root", str(tmp_path), "advanced", "run-nightly", "--compile-limit", "1"])
    assert payload["state_path"].endswith("nightly-health.json")
    assert (tmp_path / payload["state_path"]).is_file()


def test_argv_watch_zero_cycles(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    payload = _cli_json(
        ["--root", str(tmp_path), "advanced", "watch", "--interval", "0.01", "--max-cycles", "0"]
    )
    assert payload["watch_cycles"] == 0
    assert payload["processed_runs"] == 1


def test_argv_review_queue_json(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    payload = _cli_json(["--root", str(tmp_path), "advanced", "review-queue", "--json"])
    assert isinstance(payload["buckets"], dict)
    assert payload["total"] == 0


def test_argv_drop_pdf(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(_MIN_PDF)
    payload = _cli_json(["--root", str(tmp_path), "drop", "pdf", str(pdf), "--title", "Sample PDF"])
    assert payload["material"] == "pdf"
    assert (tmp_path / payload["asset_path"]).is_file()


def test_argv_drop_image_no_vision(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    image = tmp_path / "pixel.png"
    image.write_bytes(_MIN_PNG)
    payload = _cli_json(
        ["--root", str(tmp_path), "drop", "image", str(image), "--title", "Pixel", "--no-vision"]
    )
    assert payload["material"] == "image"
    assert payload["vision_status"] == "disabled"


def test_argv_alchemy_demote_after_promote(tmp_path: Path) -> None:
    _seed_promote_vault(tmp_path)
    promote = _cli_json(
        [
            "--root",
            str(tmp_path),
            "advanced",
            "alchemy",
            "promote",
            "--elixir-id",
            ELIXIR_ID,
            "--note",
            "argv promote",
        ]
    )
    assert "receipt_path" in promote or promote.get("elixir_id") == ELIXIR_ID or "path" in promote
    demote = _cli_json(
        [
            "--root",
            str(tmp_path),
            "advanced",
            "alchemy",
            "demote",
            "--elixir-id",
            ELIXIR_ID,
            "--note",
            "argv demote",
        ]
    )
    assert demote["elixir_id"] == ELIXIR_ID
    assert demote["path"].endswith(f"{ELIXIR_ID}.md")
    assert not (tmp_path / "wiki" / "elixirs" / f"{ELIXIR_ID}.md").exists()


def test_argv_alchemy_revert_after_promote(tmp_path: Path) -> None:
    _seed_promote_vault(tmp_path)
    promote = _cli_json(
        [
            "--root",
            str(tmp_path),
            "advanced",
            "alchemy",
            "promote",
            "--elixir-id",
            ELIXIR_ID,
            "--note",
            "argv promote",
        ]
    )
    assert "receipt_path" in promote or promote.get("elixir_id") == ELIXIR_ID or "path" in promote
    settled_path = _settled_path(tmp_path, ELIXIR_ID)
    assert settled_path.is_file()

    revert = _cli_json(
        [
            "--root",
            str(tmp_path),
            "advanced",
            "alchemy",
            "revert",
            "--elixir-id",
            ELIXIR_ID,
            "--note",
            "argv revert",
        ]
    )
    assert revert["elixir_id"] == ELIXIR_ID
    assert revert["path"].endswith(f"{ELIXIR_ID}.md")

    candidate_path = _candidate_path(tmp_path, ELIXIR_ID)
    assert revert["path"] == str(candidate_path.relative_to(tmp_path))
    assert not settled_path.exists()
    assert candidate_path.is_file()
    fm = _parse_elixir_frontmatter(candidate_path)
    assert fm["elixir_state"] == "candidate"
    assert "superseded_by" not in fm
    assert "promoted_at" not in fm
