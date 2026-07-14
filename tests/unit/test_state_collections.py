from __future__ import annotations

from aiwiki.state.collections import active_records_by_key, normalize_versioned_record_list_state


def default_items_state() -> dict[str, object]:
    return {"version": 1, "items": []}


def test_normalize_versioned_record_list_state_filters_records_and_preserves_version():
    assert normalize_versioned_record_list_state(
        {"version": 2, "items": [{"id": "a"}, "skip", {"id": "b"}]},
        default_state=default_items_state,
        list_key="items",
    ) == {"version": 2, "items": [{"id": "a"}, {"id": "b"}]}


def test_normalize_versioned_record_list_state_preserves_string_metadata():
    assert normalize_versioned_record_list_state(
        {"version": 2, "generated_at": "2026-05-25T00:00:00+00:00", "protocol": "", "items": [{"id": "a"}]},
        default_state=default_items_state,
        list_key="items",
        string_fields={"generated_at": "", "protocol": "general"},
    ) == {
        "version": 2,
        "generated_at": "2026-05-25T00:00:00+00:00",
        "protocol": "general",
        "items": [{"id": "a"}],
    }


def test_normalize_versioned_record_list_state_falls_back_on_invalid_shape():
    assert normalize_versioned_record_list_state(None, default_state=default_items_state, list_key="items") == {
        "version": 1,
        "items": [],
    }
    assert normalize_versioned_record_list_state(
        {"version": 2, "items": {}},
        default_state=default_items_state,
        list_key="items",
    ) == {"version": 1, "items": []}


def test_active_records_by_key_filters_inactive_and_missing_keys():
    document = {
        "items": [
            {"id": "a", "active": True},
            {"id": "b", "active": False},
            {"id": "", "active": True},
            "skip",
        ]
    }

    assert active_records_by_key(document, list_key="items", key="id") == {"a": {"id": "a", "active": True}}
