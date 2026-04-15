from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import parse_frontmatter
from aiwiki.drop import drop_image, drop_pdf, drop_repo, drop_url
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


if __name__ == "__main__":
    unittest.main()
