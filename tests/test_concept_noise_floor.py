from aiwiki.app_utils import tokenize
from aiwiki.content.concepts import concept_candidates


def test_concept_candidates_filters_stop_words():
    entries = [
        {"title": "Captured Session Notes", "id": "entry-1"},
        {"title": "Fast Task Mode", "id": "entry-2"},
    ]

    result = concept_candidates(entries)

    assert "captured" not in result
    assert "session" not in result
    assert "fast" not in result
    assert "task" not in result
    assert "mode" not in result


def test_concept_candidates_filters_pure_digits():
    entries = [{"title": "Robotics Notes 2026", "id": "entry-1"}]

    result = concept_candidates(entries)

    assert "2026" not in result
    assert "robotics" in result


def test_concept_candidates_keeps_domain_terms():
    entries = [
        {"title": "Jetson SLAM Pipeline", "id": "entry-1"},
        {"title": "Qwen3 VLM Eval", "id": "entry-2"},
        {"title": "Go2 Odom Drift", "id": "entry-3"},
    ]

    result = concept_candidates(entries)

    assert "jetson" in result
    assert "slam" in result
    assert "qwen3" in result
    assert "vlm" in result
    assert "odom" in result


def test_tokenize_drops_pure_digits():
    result = tokenize("notes 2026 jetson")

    assert "2026" not in result
    assert "jetson" in result
    assert "notes" not in result
