from __future__ import annotations

import pytest

from aiwiki.cli.universal_input import (
    _looks_like_local_path,
    _rewrite_universal_drop_argv,
    _top_level_drop_index,
)


def test_looks_like_local_path_true_for_path_signals(tmp_path) -> None:
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("hello", encoding="utf-8")

    assert _looks_like_local_path("./foo") is True
    assert _looks_like_local_path("/abs/path") is True
    assert _looks_like_local_path("notes/file.docx") is True
    assert _looks_like_local_path(r"C:\foo") is True
    assert _looks_like_local_path(str(existing_file)) is True


@pytest.mark.parametrize("payload", ["what is x?", "", "hello"])
def test_looks_like_local_path_false_for_questions_empty_and_plain_text(payload: str) -> None:
    assert _looks_like_local_path(payload) is False


def test_rewrite_universal_drop_url_to_typed_subcommand() -> None:
    assert _rewrite_universal_drop_argv(["drop", "https://example.com"]) == [
        "drop",
        "url",
        "https://example.com",
    ]


def test_rewrite_universal_drop_question_to_ask() -> None:
    assert _rewrite_universal_drop_argv(["drop", "what is x?"]) == ["advanced", "ask", "what is x?"]


def test_rewrite_universal_drop_path_like_unknown_type_fails_loud(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _rewrite_universal_drop_argv(["drop", "notes/missing.docx"])

    assert exc_info.value.code == 2
    assert "looks like a file path" in capsys.readouterr().err


def test_top_level_drop_index_skips_global_options() -> None:
    assert _top_level_drop_index(["--root", "/x", "--model-fallback=y", "drop", "hello"]) == 3


def test_universal_input_backcompat_imports_resolve_to_same_function() -> None:
    from aiwiki.cli import _rewrite_universal_drop_argv as facade_rewrite
    from aiwiki.cli.dispatch import _rewrite_universal_drop_argv as dispatch_rewrite

    assert facade_rewrite is _rewrite_universal_drop_argv
    assert dispatch_rewrite is _rewrite_universal_drop_argv
