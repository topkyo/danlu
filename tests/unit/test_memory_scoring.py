from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory import scoring


def test_app_memory_scoring_facades_match_owner():
    mapping: dict[str, str] = {}
    scoring.update_latest_timestamp(mapping, "source-a", "2026-05-25T00:00:00+00:00")
    app_memory.update_latest_timestamp(mapping, "source-a", "2026-05-24T00:00:00+00:00")

    assert mapping == {"source-a": "2026-05-25T00:00:00+00:00"}
    assert app_memory.timestamp_is_newer("2026-05-25T00:00:00+00:00", "2026-05-24T00:00:00+00:00")
    assert app_memory.machine_memory_query_time_focus("latest archive status") == scoring.machine_memory_query_time_focus(
        "latest archive status"
    )


def test_protocol_hints_for_material_defaults_and_scores_protocols():
    assert scoring.protocol_hints_for_material({}, "") == ["general"]
    assert "investing" in scoring.protocol_hints_for_material(
        {"title": "Company valuation catalyst", "source_type": "research"},
        "portfolio thesis revenue margin",
    )


def test_recency_score_and_query_time_focus_contracts():
    assert scoring.recency_score_for_timestamp("") == 0.0
    assert scoring.recency_score_for_timestamp("2099-01-01T00:00:00+00:00") == 1.0
    assert scoring.recency_score_for_timestamp("2000-01-01T00:00:00+00:00") == 0.1

    assert scoring.machine_memory_query_time_focus("latest current notes") == {
        "focus": "recent",
        "markers": ["latest", "current"],
    }
    assert scoring.machine_memory_query_time_focus("legacy archived history") == {
        "focus": "historical",
        "markers": ["history", "legacy", "archive", "archived"],
    }
    assert scoring.machine_memory_query_time_focus("plain question") == {"focus": "", "markers": []}
