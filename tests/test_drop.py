from __future__ import annotations

import base64
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import parse_frontmatter
from aiwiki.drop import (
    _analyze_image_asset,
    _best_image_source,
    _client_backend_name,
    _clone_repo,
    _detect_mime_type,
    _extract_html_document,
    _extract_image_text,
    _extract_pdf_text,
    _fetch_url,
    _git_output,
    _image_dimensions,
    _jpeg_dimensions,
    _looks_like_repo_url,
    _materialize_binary_source,
    _materialize_url_images,
    _maybe_create_image_client,
    _note_title,
    _render_url_in_browser,
    _render_url_with_browser_cli,
    _repo_key_files,
    _repo_snapshot,
    _repo_tree,
    _resolve_asset_url,
    _suffix_from_source,
    _truncate_text,
    _unique_path,
    drop_image,
    drop_note,
    drop_pdf,
    drop_repo,
    drop_url,
)
from aiwiki.llm import CompletionResult


class StubVisionClient:
    def __init__(self, response: str, backend: str = "codex-cli") -> None:
        self.response = response
        self.config = type("Config", (), {"backend": backend, "model": "stub-vision-model"})()

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        return CompletionResult(text=self.response, response_id="stub-vision", usage={})


class DropTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_drop_url_writes_note_from_fetched_payload(self) -> None:
        fetched = {
            "title": "Agent Architecture Survey",
            "final_url": "https://example.com/agents",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "A survey of agent runtime tradeoffs.",
            "image_urls": [],
            "text": "Agents coordinate tools, planning, and memory.",
        }
        with patch("aiwiki.drop._fetch_url", return_value=fetched):
            result = drop_url(self.root, "https://example.com/agents")

        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        self.assertEqual(result["material"], "url")
        self.assertIn("# Agent Architecture Survey", note)
        self.assertIn("- Final URL: `https://example.com/agents`", note)
        self.assertIn("A survey of agent runtime tradeoffs.", note)
        self.assertIn("Agents coordinate tools, planning, and memory.", note)

    def test_drop_pdf_renames_binary_asset_and_records_frontmatter(self) -> None:
        source = self.root / "paper.bin"
        source.write_bytes(b"%PDF-1.4 fake payload")

        with patch("aiwiki.drop._extract_pdf_text", return_value="Recovered PDF text."):
            result = drop_pdf(self.root, str(source), title="Runtime Paper")

        asset_path = self.root / result["asset_path"]
        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(note)

        self.assertTrue(asset_path.exists())
        self.assertEqual(asset_path.suffix, ".pdf")
        self.assertEqual(frontmatter["asset_files"], [result["asset_path"]])
        self.assertIn("Recovered PDF text.", note)
        self.assertIn("Runtime Paper", note)

    def test_drop_image_records_generated_visual_analysis(self) -> None:
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        image_path = self.root / "chart.png"
        image_path.write_bytes(image_bytes)

        with patch("aiwiki.drop._image_dimensions", return_value=(640, 480)):
            with patch("aiwiki.drop._extract_image_text", return_value="Latency chart OCR text"):
                result = drop_image(
                    self.root,
                    str(image_path),
                    title="Latency Chart",
                    client=StubVisionClient("- Chart summary\n- Confidence: medium"),
                )

        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(note)

        self.assertEqual(result["material"], "image")
        self.assertEqual(result["vision_status"], "generated")
        self.assertTrue(result["visual_analysis_present"])
        self.assertEqual(frontmatter["vision_backend"], "codex-cli")
        self.assertEqual(frontmatter["vision_status"], "generated")
        self.assertIn("Latency chart OCR text", note)
        self.assertIn("- Chart summary", note)

    def test_drop_repo_snapshots_local_repository_tree(self) -> None:
        repo = self.root / "fixture-repo"
        (repo / "src").mkdir(parents=True)
        (repo / "README.md").write_text("# Fixture Repo\n\nRepository summary.\n", encoding="utf-8")
        (repo / "src" / "main.py").write_text("print('hello repo')\n", encoding="utf-8")

        result = drop_repo(self.root, str(repo), max_files=10)

        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        self.assertEqual(result["material"], "repo")
        self.assertIn("Repository summary.", note)
        self.assertIn("- `README.md`", note)
        self.assertIn("- `src/main.py`", note)
        self.assertIn("### src/main.py", note)

    def test_drop_repo_clones_remote_url_and_cleans_temp_directory(self) -> None:
        captured: dict[str, Path] = {}

        def fake_clone(source: str, destination: Path) -> None:
            del source
            captured["cleanup_dir"] = destination.parent
            destination.mkdir(parents=True)

        with patch("aiwiki.drop._clone_repo", side_effect=fake_clone):
            with patch(
                "aiwiki.drop._repo_snapshot",
                return_value={
                    "name": "Remote Fixture",
                    "commit": "abc123",
                    "origin": "https://example.test/repo.git",
                    "readme": "Remote repo summary.",
                    "tree": ["- `README.md`"],
                    "files": [],
                },
            ):
                result = drop_repo(self.root, "https://example.test/repo.git")

        self.assertEqual(result["material"], "repo")
        self.assertFalse(captured["cleanup_dir"].exists())

    def test_drop_note_accepts_inline_text_and_marks_transcript_kind(self) -> None:
        result = drop_note(
            self.root,
            text="# Weekly Sync\n\nAlice: Ship review queue.\nBob: Follow up on runtime drift.\n",
            kind="transcript",
        )

        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(note)

        self.assertEqual(result["material"], "note")
        self.assertEqual(result["note_kind"], "transcript")
        self.assertEqual(frontmatter["source_type"], "note-drop")
        self.assertEqual(frontmatter["note_kind"], "transcript")
        self.assertEqual(frontmatter["original_path"], "inline://note")
        self.assertIn("Alice: Ship review queue.", note)

    def test_drop_note_reads_markdown_file_and_derives_title(self) -> None:
        source = self.root / "meeting.md"
        source.write_text("# Product Review\n\nLatency budget and reviewer load.\n", encoding="utf-8")

        result = drop_note(self.root, str(source))

        note_path = self.root / result["note_path"]
        note = note_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(note)

        self.assertEqual(result["title"], "Product Review")
        self.assertEqual(frontmatter["note_kind"], "note")
        self.assertEqual(frontmatter["original_path"], str(source))
        self.assertIn("Latency budget and reviewer load.", note)

    def test_fetch_url_uses_plain_text_fallback_when_html_extraction_is_not_applicable(self) -> None:
        with patch(
            "aiwiki.drop._http_fetch_url",
            return_value={
                "final_url": "https://example.test/plain",
                "content_type": "text/plain",
                "status": "200",
                "text": "Plain text body",
                "error": "",
            },
        ):
            payload = _fetch_url("https://example.test/plain")

        self.assertEqual(payload["title"], "plain")
        self.assertEqual(payload["extraction_mode"], "plain-text")
        self.assertEqual(payload["text"], "Plain text body")

    def test_fetch_url_recovers_when_browser_render_raises(self) -> None:
        with patch(
            "aiwiki.drop._http_fetch_url",
            return_value={
                "final_url": "https://example.test/page",
                "content_type": "text/html",
                "status": "",
                "text": "<html><title>Page</title><body>Rendered body</body></html>",
                "error": "",
            },
        ):
            with patch("aiwiki.drop._should_try_browser_render", return_value=True):
                with patch("aiwiki.drop._render_url_in_browser", side_effect=RuntimeError("no browser")):
                    with patch(
                        "aiwiki.drop._extract_html_document",
                        return_value={
                            "title": "Recovered Page",
                            "description": "Recovered description",
                            "text": "Recovered body",
                            "image_urls": ["https://example.test/a.png"],
                            "mode": "readability",
                        },
                    ):
                        payload = _fetch_url("https://example.test/page")

        self.assertEqual(payload["title"], "Recovered Page")
        self.assertEqual(payload["browser_backend"], "")
        self.assertEqual(payload["extraction_mode"], "readability")
        self.assertEqual(payload["status"], "browser-rendered")

    def test_fetch_url_raises_when_no_text_can_be_recovered(self) -> None:
        with patch(
            "aiwiki.drop._http_fetch_url",
            return_value={
                "final_url": "https://example.test/fail",
                "content_type": "",
                "status": "",
                "text": "",
                "error": "connection reset",
            },
        ):
            with self.assertRaises(RuntimeError) as ctx:
                _fetch_url("https://example.test/fail")

        self.assertIn("connection reset", str(ctx.exception))

    def test_extract_html_document_prefers_bs4_main_content_and_assets(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:title" content="Rich Page" />
            <meta name="description" content="Meta summary" />
            <meta property="og:image" content="/cover.png" />
          </head>
          <body>
            <nav>Navigation should disappear</nav>
            <article>
              <h2>Signals</h2>
              <p>Important body text.</p>
              <ul><li>First bullet</li></ul>
              <img data-src="/body.png" />
            </article>
          </body>
        </html>
        """

        payload = _extract_html_document(html, "https://example.test/posts/rich")

        self.assertEqual(payload["mode"], "bs4-main-content")
        self.assertEqual(payload["title"], "Rich Page")
        self.assertEqual(payload["description"], "Meta summary")
        self.assertIn("## Signals", payload["text"])
        self.assertIn("- First bullet", payload["text"])
        self.assertEqual(
            payload["image_urls"],
            ["https://example.test/body.png", "https://example.test/cover.png"],
        )

    def test_extract_html_document_regex_fallback_uses_title_description_and_images(self) -> None:
        html = """
        <html>
          <head>
            <title>Fallback Page</title>
            <meta content="Fallback summary" name="description" />
            <meta property="og:image" content="/hero.png" />
          </head>
          <body>
            <img src="/inline.png" />
            <div>Main fallback text</div>
          </body>
        </html>
        """

        with patch("aiwiki.drop.BeautifulSoup", None):
            payload = _extract_html_document(html, "https://example.test/fallback")

        self.assertEqual(payload["mode"], "regex-fallback")
        self.assertEqual(payload["title"], "Fallback Page")
        self.assertEqual(payload["description"], "Fallback summary")
        self.assertIn("Main fallback text", payload["text"])
        self.assertEqual(
            payload["image_urls"],
            ["https://example.test/inline.png", "https://example.test/hero.png"],
        )

    def test_materialize_url_images_skips_failed_downloads(self) -> None:
        created = self.root / "raw" / "assets" / "one.png"
        created.parent.mkdir(parents=True, exist_ok=True)
        created.write_bytes(b"png")

        def fake_download(root: Path, source: str, preferred_slug: str) -> tuple[Path, str]:
            del root
            del preferred_slug
            if source.endswith("broken.png"):
                raise RuntimeError("boom")
            return created, source

        with patch("aiwiki.drop._download_asset_url", side_effect=fake_download):
            paths = _materialize_url_images(
                self.root,
                ["https://example.test/one.png", "https://example.test/broken.png"],
                "rich-page",
            )

        self.assertEqual(paths, [f"raw/assets/{created.name}"])

    def test_materialize_binary_source_supports_remote_and_missing_local_file(self) -> None:
        remote_asset = self.root / "raw" / "assets" / "remote.bin"
        remote_asset.parent.mkdir(parents=True, exist_ok=True)
        remote_asset.write_bytes(b"remote")

        with patch(
            "aiwiki.drop._download_asset_url",
            return_value=(remote_asset, "https://example.test/file.bin"),
        ):
            asset_path, original = _materialize_binary_source(
                self.root,
                "https://example.test/file.bin",
                "remote-file",
            )

        self.assertEqual(asset_path, remote_asset)
        self.assertEqual(original, "https://example.test/file.bin")
        with self.assertRaises(FileNotFoundError):
            _materialize_binary_source(self.root, str(self.root / "missing.bin"), "missing-file")

    def test_binary_helpers_handle_tool_failures_and_fallbacks(self) -> None:
        source = self.root / "paper.pdf"
        source.write_bytes(b"%PDF-1.4")

        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="bad pdf"),
        ):
            with self.assertRaises(RuntimeError):
                _extract_pdf_text(source)

        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ):
            self.assertEqual(_detect_mime_type(source), "application/octet-stream")

        with patch("aiwiki.drop.shutil.which", return_value=None):
            self.assertEqual(_extract_image_text(source), "")
        with patch("aiwiki.drop.shutil.which", return_value="/usr/bin/tesseract"):
            with patch(
                "aiwiki.drop.subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="ocr failed"),
            ):
                self.assertEqual(_extract_image_text(source), "")

    def test_image_helpers_detect_dimensions_and_backend_metadata(self) -> None:
        gif = self.root / "tiny.gif"
        gif.write_bytes(b"GIF89a\x02\x00\x03\x00" + b"\x00" * 24)
        self.assertEqual(_image_dimensions(gif), (2, 3))

        self.assertEqual(_resolve_asset_url("https://example.test/base/", "/chart.png"), "https://example.test/chart.png")
        self.assertEqual(_resolve_asset_url("https://example.test/base/", "data:image/png;base64,aaaa"), "")
        self.assertEqual(_best_image_source({"srcset": "/hero.png 2x, /hero-small.png 1x"}), "/hero.png")
        self.assertTrue(_looks_like_repo_url("git@github.com:owner/repo.git"))
        self.assertEqual(_client_backend_name(StubVisionClient("ok", backend="openai-api")), "openai-api")

    def test_analyze_image_asset_handles_disabled_skipped_and_failed_states(self) -> None:
        image = self.root / "chart.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)

        disabled = _analyze_image_asset(
            self.root,
            image,
            mime="image/png",
            width=1,
            height=1,
            ocr_text="",
            client=None,
            enable_vision=False,
        )
        skipped = _analyze_image_asset(
            self.root,
            image,
            mime="image/png",
            width=1,
            height=1,
            ocr_text="",
            client=object(),
            enable_vision=True,
        )
        failing_client = type(
            "FailingClient",
            (),
            {
                "config": type("Config", (), {"backend": "codex-cli"})(),
                "analyze_image": lambda self, system_prompt, user_prompt, image_path: (_ for _ in ()).throw(
                    RuntimeError("boom")
                ),
            },
        )()
        failed = _analyze_image_asset(
            self.root,
            image,
            mime="image/png",
            width=1,
            height=1,
            ocr_text="",
            client=failing_client,
            enable_vision=True,
        )

        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(failed["status"], "failed")

    def test_clone_repo_raises_on_git_failure(self) -> None:
        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fatal"),
        ):
            with self.assertRaises(RuntimeError):
                _clone_repo("https://example.test/repo.git", self.root / "repo")

    def test_browser_render_helpers_cover_playwright_cli_and_sandbox_fallbacks(self) -> None:
        with patch("aiwiki.drop.sync_playwright", object()):
            with patch("aiwiki.drop._render_url_with_playwright", return_value="<html>pw</html>"):
                rendered = _render_url_in_browser("https://example.test/page")
        self.assertEqual(rendered, {"html": "<html>pw</html>", "backend": "playwright-chromium"})

        with patch("aiwiki.drop.sync_playwright", None):
            with patch("aiwiki.drop._browser_command", return_value=""):
                self.assertEqual(_render_url_in_browser("https://example.test/page"), {"html": "", "backend": ""})

        with patch("aiwiki.drop.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="sandbox blocked"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="<html>fallback</html>", stderr=""),
            ]
            html = _render_url_with_browser_cli("https://example.test/page", "chromium")
        self.assertEqual(html, "<html>fallback</html>")

        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="still bad"),
        ):
            with self.assertRaises(RuntimeError):
                _render_url_with_browser_cli("https://example.test/page", "chromium")

    def test_repo_and_text_helpers_cover_truncation_unique_paths_and_git_output(self) -> None:
        repo = self.root / "snapshot-repo"
        (repo / "src").mkdir(parents=True)
        (repo / "build").mkdir()
        (repo / "README.md").write_text("# Repo\n\nReadme body.\n", encoding="utf-8")
        (repo / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (repo / "binary.bin").write_bytes(b"\x00\x01")
        (repo / "build" / "ignored.txt").write_text("ignore\n", encoding="utf-8")

        with patch("aiwiki.drop._git_output", side_effect=["abc123", ""]):
            snapshot = _repo_snapshot(repo, max_files=1)

        self.assertEqual(snapshot["commit"], "abc123")
        self.assertEqual(snapshot["readme"], "# Repo\n\nReadme body.")
        self.assertEqual(snapshot["tree"], ["- `README.md`"])
        self.assertEqual(snapshot["files"][0]["path"], "src/main.py")
        self.assertEqual(_repo_tree(repo, max_files=10), ["README.md", "binary.bin", "src/main.py"])
        self.assertEqual(_repo_key_files(repo), ["README.md", "src/main.py"])

        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
        ):
            self.assertEqual(_git_output(repo, ["rev-parse", "HEAD"]), "abc123")
        with patch(
            "aiwiki.drop.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fatal"),
        ):
            self.assertEqual(_git_output(repo, ["rev-parse", "HEAD"]), "")

        collision_dir = self.root / "raw" / "inbox"
        collision_dir.mkdir(parents=True, exist_ok=True)
        first = collision_dir / "note.md"
        first.write_text("x\n", encoding="utf-8")
        self.assertEqual(_unique_path(collision_dir, "note", ".md").name, "note-2.md")
        self.assertEqual(_note_title("\nFirst useful line\n", fallback="Fallback"), "First useful line")
        self.assertEqual(_truncate_text("abcdef", 4), "abcd\n...[truncated]")
        self.assertEqual(_suffix_from_source("https://example.test/file", "image/png"), ".png")

    def test_image_and_client_helpers_cover_jpeg_and_backend_filters(self) -> None:
        jpeg = self.root / "chart.jpg"
        jpeg.write_bytes(
            b"\xff\xd8"
            + b"\xff\xe0\x00\x04AB"
            + b"\xff\xc0\x00\x11\x08\x00\x02\x00\x03\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        )
        self.assertEqual(_jpeg_dimensions(jpeg), (3, 2))
        self.assertEqual(_image_dimensions(jpeg), (3, 2))

        bad_client = type("ConfigHolder", (), {"backend": "copilot-cli"})()
        with patch("aiwiki.drop.LLMConfig.from_env", return_value=bad_client):
            self.assertIsNone(_maybe_create_image_client(self.root))
        good_client = type("ConfigHolder", (), {"backend": "codex-cli"})()
        with patch("aiwiki.drop.LLMConfig.from_env", return_value=good_client):
            with patch("aiwiki.drop.create_backend_client", return_value="client") as factory:
                self.assertEqual(_maybe_create_image_client(self.root), "client")
        factory.assert_called_once_with(good_client, self.root)


if __name__ == "__main__":
    unittest.main()
