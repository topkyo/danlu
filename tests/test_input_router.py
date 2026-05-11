from __future__ import annotations

import unittest

from aiwiki.input_router import RouteDecision, UniversalRoute, classify_universal_input


class InputRouterTests(unittest.TestCase):
    def assertDecision(self, value: str, route: UniversalRoute, payload: str, reason: str) -> None:
        self.assertEqual(classify_universal_input(value), RouteDecision(route, payload, reason))

    def test_http_url_routes_to_url(self) -> None:
        self.assertDecision("http://example.com/page", UniversalRoute.URL, "http://example.com/page", "url-scheme")

    def test_https_url_routes_to_url_case_insensitive_scheme(self) -> None:
        self.assertDecision("HTTPS://example.com/X", UniversalRoute.URL, "HTTPS://example.com/X", "url-scheme")

    def test_url_query_question_mark_stays_url(self) -> None:
        self.assertDecision("https://example.com/x?y=z", UniversalRoute.URL, "https://example.com/x?y=z", "url-scheme")

    def test_url_pdf_suffix_routes_to_pdf(self) -> None:
        self.assertDecision(
            "https://example.com/report.pdf", UniversalRoute.PDF, "https://example.com/report.pdf", "pdf-suffix-on-url"
        )

    def test_url_pdf_suffix_ignores_query_string(self) -> None:
        self.assertDecision(
            "https://example.com/report.PDF?download=1",
            UniversalRoute.PDF,
            "https://example.com/report.PDF?download=1",
            "pdf-suffix-on-url",
        )

    def test_url_image_suffix_routes_to_image(self) -> None:
        self.assertDecision(
            "https://example.com/chart.png", UniversalRoute.IMAGE, "https://example.com/chart.png", "image-suffix-on-url"
        )

    def test_url_image_suffix_is_case_insensitive_and_ignores_fragment(self) -> None:
        self.assertDecision(
            "https://example.com/PHOTO.JPEG#view",
            UniversalRoute.IMAGE,
            "https://example.com/PHOTO.JPEG#view",
            "image-suffix-on-url",
        )

    def test_local_pdf_suffix_routes_to_pdf(self) -> None:
        self.assertDecision("./docs/report.pdf", UniversalRoute.PDF, "./docs/report.pdf", "pdf-suffix")

    def test_file_pdf_suffix_routes_to_pdf_case_insensitive(self) -> None:
        self.assertDecision("file:///tmp/REPORT.PDF", UniversalRoute.PDF, "file:///tmp/REPORT.PDF", "pdf-suffix")

    def test_local_image_suffix_routes_to_image(self) -> None:
        self.assertDecision("./images/chart.webp", UniversalRoute.IMAGE, "./images/chart.webp", "image-suffix")

    def test_local_image_suffix_is_case_insensitive(self) -> None:
        self.assertDecision("diagram.SVG", UniversalRoute.IMAGE, "diagram.SVG", "image-suffix")

    def test_md_suffix_routes_to_note(self) -> None:
        self.assertDecision("notes/meeting.md", UniversalRoute.NOTE, "notes/meeting.md", "note-text-suffix")

    def test_markdown_suffix_routes_to_note_case_insensitive(self) -> None:
        self.assertDecision("README.MARKDOWN", UniversalRoute.NOTE, "README.MARKDOWN", "note-text-suffix")

    def test_txt_suffix_routes_to_note(self) -> None:
        self.assertDecision("./inbox/raw.txt", UniversalRoute.NOTE, "./inbox/raw.txt", "note-text-suffix")

    def test_md_filename_with_question_mark_still_routes_to_ask(self) -> None:
        self.assertDecision("what.md?", UniversalRoute.ASK, "what.md?", "contains-question-mark")

    def test_ask_prefix_wins_over_md_suffix(self) -> None:
        self.assertDecision(
            "ask: summarize README.md", UniversalRoute.ASK, "summarize README.md", "ask-prefix"
        )

    def test_git_ssh_shorthand_routes_to_repo(self) -> None:
        self.assertDecision(
            "git@github.com:user/repo.git", UniversalRoute.REPO, "git@github.com:user/repo.git", "git-ssh-shorthand"
        )

    def test_ssh_scheme_routes_to_repo(self) -> None:
        self.assertDecision("ssh://git@host/repo.git", UniversalRoute.REPO, "ssh://git@host/repo.git", "ssh-scheme")

    def test_git_suffix_routes_to_repo(self) -> None:
        self.assertDecision("./local/repo.git", UniversalRoute.REPO, "./local/repo.git", "git-suffix")

    def test_note_prefix_routes_to_note_and_strips_prefix(self) -> None:
        self.assertDecision("note: hi", UniversalRoute.NOTE, "hi", "note-prefix")

    def test_note_prefix_is_case_insensitive(self) -> None:
        self.assertDecision("NOTE: x", UniversalRoute.NOTE, "x", "note-prefix")

    def test_multiline_text_routes_to_note(self) -> None:
        self.assertDecision("line1\nline2", UniversalRoute.NOTE, "line1\nline2", "multiline-text")

    def test_multiline_text_trims_outer_whitespace_only(self) -> None:
        self.assertDecision("  line1\nline2  ", UniversalRoute.NOTE, "line1\nline2", "multiline-text")

    def test_ask_prefix_routes_to_ask_and_strips_prefix(self) -> None:
        self.assertDecision("ask: explain x", UniversalRoute.ASK, "explain x", "ask-prefix")

    def test_ask_prefix_is_case_insensitive(self) -> None:
        self.assertDecision("Ask: explain y", UniversalRoute.ASK, "explain y", "ask-prefix")

    def test_question_mark_routes_to_ask(self) -> None:
        self.assertDecision("what is x?", UniversalRoute.ASK, "what is x?", "contains-question-mark")

    def test_filename_with_question_mark_routes_to_ask(self) -> None:
        self.assertDecision("file?.txt", UniversalRoute.ASK, "file?.txt", "contains-question-mark")

    def test_plain_text_defaults_to_ask(self) -> None:
        self.assertDecision("hello world", UniversalRoute.ASK, "hello world", "default-ambiguous-text")

    def test_ambiguous_repo_like_plain_text_defaults_to_ask(self) -> None:
        self.assertDecision("is_this_a_repo", UniversalRoute.ASK, "is_this_a_repo", "default-ambiguous-text")

    def test_empty_input_raises(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "empty input"):
                    classify_universal_input(value)

    def test_empty_note_payload_raises(self) -> None:
        for value in ("note:", "note:   "):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "empty note payload"):
                    classify_universal_input(value)


if __name__ == "__main__":
    unittest.main()
