from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory.source_records import machine_memory_source_runtime_record


def _record_kwargs():
    return {
        "source_nodes": {
            "source-a": {
                "title": "Source A",
                "source_page": "wiki/sources/source-a.md",
            }
        },
        "material_by_entry": {
            "source-a": {
                "temperature": "cold",
                "last_touched_at": "2000-01-01T00:00:00+00:00",
                "last_query_hit_at": "",
                "last_review_reference_at": "",
            }
        },
        "routing_by_entry": {
            "source-a": {
                "top_protocols": [{"protocol": "research"}, {"protocol": "general"}],
                "protocols": {
                    "research": {
                        "selected_as": "hot-evidence",
                        "total_score": 4.0,
                    }
                },
            }
        },
        "archive_candidates_by_entry": {
            "source-a": {
                "status": "candidate",
                "recommended_temperature": "archived",
                "reason_codes": ["stale", "", 1],
            }
        },
    }


def test_app_memory_source_runtime_record_facade_matches_owner():
    kwargs = _record_kwargs()

    owner = machine_memory_source_runtime_record(
        "source-a",
        base_score=3.0,
        protocol="research",
        time_focus="historical",
        **kwargs,
    )
    facade = app_memory.machine_memory_source_runtime_record(
        "source-a",
        base_score=3.0,
        protocol="research",
        time_focus="historical",
        **kwargs,
    )

    assert facade == owner
    assert facade["protocol_shard"] is True
    assert facade["time_shard"] is True
    assert facade["archive_hint"] is True
    assert facade["reason_codes"] == ["stale"]


def test_source_runtime_record_recent_focus_penalizes_cold_sources():
    kwargs = _record_kwargs()

    record = machine_memory_source_runtime_record(
        "source-a",
        base_score=3.0,
        protocol="research",
        time_focus="recent",
        **kwargs,
    )

    assert record["time_bonus"] < 1.0
    assert record["combined_score"] == round(record["base_score"] + record["protocol_bonus"] + record["time_bonus"], 3)
