from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aiwiki.signals.schema import (
    REQUIRED_TOP_LEVEL,
    TOP_LEVEL_FIELD_ORDER,
    canonical_dumps,
    compute_dedupe_key,
    detect_trace_id_conflict,
    parse_trace_id,
    validate,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "signals"


def _fixture_lines(name: str) -> list[str]:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8").splitlines()


def _fixture_records(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in _fixture_lines(name)]


def _dedupe_by_key(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for record in records:
        dedupe_key = record["dedupe_key"]
        if isinstance(dedupe_key, str) and dedupe_key not in seen:
            seen[dedupe_key] = record
    return list(seen.values())


class TestValidateValidSignal(unittest.TestCase):
    def test_valid_signal_fixture_rows_are_valid(self) -> None:
        for line in _fixture_lines("valid_signal_v1.jsonl"):
            result = validate(json.loads(line))
            self.assertTrue(result.ok)
            self.assertEqual(result.errors, ())

    def test_valid_signal_has_required_fields(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        self.assertTrue(REQUIRED_TOP_LEVEL.issubset(set(record)))
        self.assertEqual(record["schema_version"], 1)
        self.assertIn("budget_hint", record)


class TestCanonicalDumps(unittest.TestCase):
    def test_canonical_dumps_matches_valid_fixture_golden_line(self) -> None:
        line = _fixture_lines("valid_signal_v1.jsonl")[0]
        record = json.loads(line)
        self.assertEqual(canonical_dumps(record), line)

    def test_canonical_dumps_reorders_top_level_and_nested_scope_fields(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        reversed_record = {key: record[key] for key in reversed(tuple(record.keys()))}
        scope = reversed_record["scope"]
        self.assertIsInstance(scope, dict)
        reversed_record["scope"] = {key: scope[key] for key in reversed(tuple(scope.keys()))}

        dumped = canonical_dumps(reversed_record)
        loaded = json.loads(dumped)

        self.assertEqual(tuple(loaded.keys()), tuple(key for key in TOP_LEVEL_FIELD_ORDER if key in loaded))
        self.assertEqual(tuple(loaded["scope"].keys()), ("protocol", "corpus_id", "source_ids", "concept_slugs", "elixir_refs", "judgment_refs"))

    def test_canonical_dumps_deduplicates_and_sorts_list_fields(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["evidence_refs"] = [
            "wiki/judgments/foo.md",
            "raw/inbox/example.md#L12",
            "wiki/judgments/foo.md",
        ]
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["source_ids"] = ["src-2", "src-1", "src-2"]
        scope["concept_slugs"] = ["zeta", "alpha", "alpha"]

        canonical = json.loads(canonical_dumps(record))
        self.assertEqual(canonical["evidence_refs"], ["raw/inbox/example.md#L12", "wiki/judgments/foo.md"])
        self.assertEqual(canonical["scope"]["source_ids"], ["src-1", "src-2"])
        self.assertEqual(canonical["scope"]["concept_slugs"], ["alpha", "zeta"])

    def test_canonical_dumps_budget_hint_order(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["budget_hint"] = {"max_tokens": 4000, "max_pages": 20}
        canonical = json.loads(canonical_dumps(record))
        self.assertEqual(tuple(canonical["budget_hint"].keys()), ("max_pages", "max_tokens"))

    def test_canonical_dumps_idempotent(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        once = canonical_dumps(record)
        twice = canonical_dumps(json.loads(once))
        self.assertEqual(once, twice)


class TestDedupeReplay(unittest.TestCase):
    def test_dedupe_replay_rows_validate(self) -> None:
        for record in _fixture_records("signal_dedupe_replay.jsonl"):
            result = validate(record)
            self.assertTrue(result.ok)
            self.assertEqual(result.errors, ())

    def test_dedupe_replay_volatile_fields_differ(self) -> None:
        first, second = _fixture_records("signal_dedupe_replay.jsonl")
        self.assertEqual(first["dedupe_key"], second["dedupe_key"])
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertNotEqual(first["signal_id"], second["signal_id"])
        self.assertNotEqual(first["emitted_at"], second["emitted_at"])
        self.assertNotEqual(first["source_event_ref"], second["source_event_ref"])
        self.assertEqual(first["severity"], second["severity"])
        self.assertEqual(first["evidence_refs"], second["evidence_refs"])

    def test_dedupe_replay_dedupes_to_single_first_record(self) -> None:
        records = _fixture_records("signal_dedupe_replay.jsonl")
        deduped = _dedupe_by_key(records)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0], records[0])


class TestBadSchemaMissingRequired(unittest.TestCase):
    def test_bad_missing_required_rows_are_invalid(self) -> None:
        for record in _fixture_records("bad_schema_missing_required.jsonl"):
            self.assertFalse(validate(record).ok)

    def test_missing_source_kind_error_contains_field_name(self) -> None:
        record = _fixture_records("bad_schema_missing_required.jsonl")[0]
        errors = validate(record).errors
        self.assertTrue(any("source_kind" in error for error in errors))

    def test_missing_evidence_refs_error_contains_field_name(self) -> None:
        record = _fixture_records("bad_schema_missing_required.jsonl")[1]
        errors = validate(record).errors
        self.assertTrue(any("evidence_refs" in error for error in errors))

    def test_null_value_error_mentions_null(self) -> None:
        record = _fixture_records("bad_schema_missing_required.jsonl")[2]
        errors = validate(record).errors
        self.assertTrue(any("severity" in error or "null" in error for error in errors))


class TestBadSchemaUnknownOrVersion(unittest.TestCase):
    def test_bad_unknown_or_version_rows_are_invalid(self) -> None:
        for record in _fixture_records("bad_schema_unknown_or_version.jsonl"):
            self.assertFalse(validate(record).ok)

    def test_unknown_top_level_contains_unknown_error(self) -> None:
        record = _fixture_records("bad_schema_unknown_or_version.jsonl")[0]
        errors = validate(record).errors
        self.assertTrue(any("extra_field" in error for error in errors))

    def test_unknown_scope_field_contains_unknown_error(self) -> None:
        record = _fixture_records("bad_schema_unknown_or_version.jsonl")[1]
        errors = validate(record).errors
        self.assertTrue(any("unknown_nested" in error and "scope" in error for error in errors))

    def test_schema_version_error_mentions_schema_version(self) -> None:
        record = _fixture_records("bad_schema_unknown_or_version.jsonl")[2]
        errors = validate(record).errors
        self.assertTrue(any("schema_version" in error for error in errors))


class TestTraceBacklinkChain(unittest.TestCase):
    def test_first_three_rows_validate_and_share_same_trace_id(self) -> None:
        records = _fixture_records("trace_backlink_chain.jsonl")
        first_three = records[:3]

        for record in first_three:
            result = validate(record)
            self.assertTrue(result.ok)
            self.assertEqual(result.errors, ())

        trace_ids = {record["trace_id"] for record in first_three}
        self.assertEqual(len(trace_ids), 1)

    def test_fourth_row_conflicts_by_dedupe_key_and_trace_id(self) -> None:
        records = _fixture_records("trace_backlink_chain.jsonl")
        self.assertTrue(detect_trace_id_conflict(records[:1], records[3]))
        self.assertEqual(records[0]["dedupe_key"], records[3]["dedupe_key"])
        self.assertNotEqual(records[0]["trace_id"], records[3]["trace_id"])

    def test_same_record_does_not_conflict(self) -> None:
        record = _fixture_records("trace_backlink_chain.jsonl")[0]
        self.assertFalse(detect_trace_id_conflict([record], record))

    def test_replay_records_with_same_trace_id_do_not_conflict(self) -> None:
        replay_first, replay_second = _fixture_records("signal_dedupe_replay.jsonl")
        self.assertFalse(detect_trace_id_conflict([replay_first], replay_second))


class TestParseTraceId(unittest.TestCase):
    def test_valid_uuidv4_returns_original(self) -> None:
        raw = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(parse_trace_id(raw), raw)

    def test_uppercase_uuidv4_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id("550E8400-E29B-41D4-A716-446655440000")

    def test_uuidv1_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    def test_uuidv3_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id("f47ac10b-58cc-3372-a567-0e02b2c3d479")

    def test_uuidv5_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id("21f7f8de-8051-5b89-8680-0195ef798b6a")

    def test_non_uuid_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id("not-a-uuid")


class TestComputeDedupeKey(unittest.TestCase):
    def test_compute_dedupe_key_uses_v1_format(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        dedupe_key = compute_dedupe_key(record, "raw/inbox/example.md")
        self.assertEqual(dedupe_key, "raw_added:research:runtime_history:raw/inbox/example.md")

    def test_compute_dedupe_key_requires_source_identity(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        with self.assertRaises(ValueError):
            compute_dedupe_key(record, "")

    def test_compute_dedupe_key_requires_scope_protocol(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["scope"] = {}
        with self.assertRaises(ValueError):
            compute_dedupe_key(record, "raw/inbox/example.md")

    def test_compute_dedupe_key_requires_kind_string(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["kind"] = 123
        with self.assertRaises(ValueError):
            compute_dedupe_key(record, "raw/inbox/example.md")

    def test_compute_dedupe_key_requires_source_kind_string(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["source_kind"] = 123
        with self.assertRaises(ValueError):
            compute_dedupe_key(record, "raw/inbox/example.md")


class TestValidateErrorPaths(unittest.TestCase):
    def _valid_record(self) -> dict[str, object]:
        return _fixture_records("valid_signal_v1.jsonl")[0]

    def _assert_source_event_ref_valid(self, source_kind: str, source_event_ref: str) -> None:
        record = self._valid_record()
        record["source_kind"] = source_kind
        record["source_event_ref"] = source_event_ref
        result = validate(record)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())

    def _assert_source_event_ref_rejected(self, source_kind: str, source_event_ref: object) -> None:
        record = self._valid_record()
        record["source_kind"] = source_kind
        record["source_event_ref"] = source_event_ref
        result = validate(record)
        self.assertFalse(result.ok)
        self.assertTrue(any("source_event_ref" in error for error in result.errors))

    def test_validate_rejects_non_object(self) -> None:
        result = validate("not-an-object")  # type: ignore[arg-type]
        self.assertFalse(result.ok)
        self.assertTrue(any("object" in error for error in result.errors))

    def test_validate_schema_version_must_be_integer(self) -> None:
        record = self._valid_record()
        record["schema_version"] = "1"
        errors = validate(record).errors
        self.assertTrue(any("schema_version" in error and "integer" in error for error in errors))

    def test_validate_signal_id_format(self) -> None:
        record = self._valid_record()
        record["signal_id"] = "bad-id"
        errors = validate(record).errors
        self.assertTrue(any("signal_id" in error for error in errors))

    def test_validate_kind_enum(self) -> None:
        record = self._valid_record()
        record["kind"] = "unknown-kind"
        errors = validate(record).errors
        self.assertTrue(any("kind" in error for error in errors))

    def test_validate_scope_object_required(self) -> None:
        record = self._valid_record()
        record["scope"] = "bad"
        errors = validate(record).errors
        self.assertTrue(any("scope must be an object" in error for error in errors))

    def test_validate_scope_missing_required_field(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope.pop("source_ids")
        errors = validate(record).errors
        self.assertTrue(any("scope.source_ids" in error for error in errors))

    def test_validate_scope_protocol_type_and_enum(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["protocol"] = 123
        errors = validate(record).errors
        self.assertTrue(any("scope.protocol must be a string" in error for error in errors))

        scope["protocol"] = "unknown"
        errors = validate(record).errors
        self.assertTrue(any("scope.protocol" in error and "closed-set" in error for error in errors))

    def test_validate_scope_corpus_id_must_be_string(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["corpus_id"] = 123
        errors = validate(record).errors
        self.assertTrue(any("scope.corpus_id" in error for error in errors))

    def test_validate_scope_unknown_field(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["extra"] = "x"
        errors = validate(record).errors
        self.assertTrue(any("unknown nested field in scope" in error for error in errors))

    def test_validate_severity_enum(self) -> None:
        record = self._valid_record()
        record["severity"] = "urgent"
        errors = validate(record).errors
        self.assertTrue(any("severity" in error for error in errors))

    def test_validate_emitted_at_format(self) -> None:
        record = self._valid_record()
        record["emitted_at"] = "2026-04-24T04:00:00+08:00"
        errors = validate(record).errors
        self.assertTrue(any("emitted_at" in error for error in errors))

    def test_validate_emitted_by_enum(self) -> None:
        record = self._valid_record()
        record["emitted_by"] = "daemon"
        errors = validate(record).errors
        self.assertTrue(any("emitted_by" in error for error in errors))

    def test_validate_source_kind_enum(self) -> None:
        record = self._valid_record()
        record["source_kind"] = "other"
        errors = validate(record).errors
        self.assertTrue(any("source_kind" in error for error in errors))

    def test_validate_trace_id_invalid(self) -> None:
        record = self._valid_record()
        record["trace_id"] = "not-a-uuid"
        errors = validate(record).errors
        self.assertTrue(any("trace_id" in error for error in errors))

    def test_validate_budget_hint_must_be_object(self) -> None:
        record = self._valid_record()
        record["budget_hint"] = "bad"
        errors = validate(record).errors
        self.assertTrue(any("budget_hint must be an object" in error for error in errors))

    def test_validate_budget_hint_constraints(self) -> None:
        record = self._valid_record()
        record["budget_hint"] = {}
        errors = validate(record).errors
        self.assertTrue(any("at least one" in error for error in errors))

        record["budget_hint"] = {"max_pages": 0}
        errors = validate(record).errors
        self.assertTrue(any("max_pages" in error for error in errors))

        record["budget_hint"] = {"max_tokens": -1}
        errors = validate(record).errors
        self.assertTrue(any("max_tokens" in error for error in errors))

        record["budget_hint"] = {"max_pages": 1, "extra": 2}
        errors = validate(record).errors
        self.assertTrue(any("unknown nested field in budget_hint" in error for error in errors))

    def test_validate_list_type_and_members(self) -> None:
        record = self._valid_record()
        record["evidence_refs"] = "bad"
        errors = validate(record).errors
        self.assertTrue(any("evidence_refs" in error and "list" in error for error in errors))

        record["evidence_refs"] = ["ok", 1]
        errors = validate(record).errors
        self.assertTrue(any("evidence_refs[1]" in error for error in errors))

    def test_validate_list_duplicate_and_unsorted(self) -> None:
        record = self._valid_record()
        record["evidence_refs"] = ["b", "a", "a"]
        errors = validate(record).errors
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("sorted" in error for error in errors))

    def test_validate_scope_source_ids_duplicate_rejected(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["source_ids"] = ["a", "a"]
        errors = validate(record).errors
        self.assertTrue(any("scope.source_ids" in error and "duplicate" in error for error in errors))

    def test_validate_scope_source_ids_unsorted_rejected(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["source_ids"] = ["b", "a"]
        errors = validate(record).errors
        self.assertTrue(any("scope.source_ids" in error and "sorted" in error for error in errors))

    def test_validate_scope_source_ids_non_string_rejected(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["source_ids"] = [123]
        errors = validate(record).errors
        self.assertTrue(any("scope.source_ids" in error and "string" in error for error in errors))

    def test_validate_scope_source_ids_nested_object_rejected(self) -> None:
        record = self._valid_record()
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["source_ids"] = [{"id": "a"}]
        errors = validate(record).errors
        self.assertTrue(any("scope.source_ids" in error and "string" in error for error in errors))

    def test_validate_budget_hint_bool_is_rejected(self) -> None:
        record = self._valid_record()
        record["budget_hint"] = {"max_pages": True}
        errors = validate(record).errors
        self.assertTrue(any("max_pages" in error for error in errors))

    def test_validate_budget_hint_negative_is_rejected(self) -> None:
        record = self._valid_record()
        record["budget_hint"] = {"max_pages": -5}
        errors = validate(record).errors
        self.assertTrue(any("max_pages" in error for error in errors))

    def test_validate_emitted_at_fractional_seconds_rejected(self) -> None:
        record = self._valid_record()
        record["emitted_at"] = "2026-04-24T04:00:00.000Z"
        errors = validate(record).errors
        self.assertTrue(any("emitted_at" in error for error in errors))

    def test_validate_emitted_at_offset_form_rejected(self) -> None:
        record = self._valid_record()
        record["emitted_at"] = "2026-04-24T04:00:00+00:00"
        errors = validate(record).errors
        self.assertTrue(any("emitted_at" in error for error in errors))

    def test_validate_null_and_float_forbidden(self) -> None:
        record = self._valid_record()
        record["budget_hint"] = {"max_pages": 1.2}
        errors = validate(record).errors
        self.assertTrue(any("float" in error for error in errors))

        record = self._valid_record()
        record["severity"] = None
        errors = validate(record).errors
        self.assertTrue(any("null" in error for error in errors))

    def test_validate_source_event_ref_mismatch_rules(self) -> None:
        cases = [
            ("runtime_history", "raw/inbox/a.md#L1"),
            ("llm_receipt", "runtime-history.jsonl#L1"),
            ("review_outcome", "wiki/sources/a.md#L1"),
            ("archive_event", "wiki/sources/a.md#L1"),
            ("protocol_learning_event", "wiki/sources/a.md#L1"),
        ]
        for source_kind, source_ref in cases:
            record = self._valid_record()
            record["source_kind"] = source_kind
            record["source_event_ref"] = source_ref
            errors = validate(record).errors
            self.assertTrue(any("source_event_ref mismatches" in error for error in errors))

    def test_validate_source_event_ref_runtime_history_hyphen_valid(self) -> None:
        self._assert_source_event_ref_valid("runtime_history", "runtime-history.jsonl#L42")

    def test_validate_source_event_ref_runtime_history_underscore_valid(self) -> None:
        self._assert_source_event_ref_valid("runtime_history", "runtime_history.jsonl#L42")

    def test_validate_source_event_ref_llm_receipt_hyphen_plural_valid(self) -> None:
        self._assert_source_event_ref_valid("llm_receipt", "llm-receipts.jsonl#L7")

    def test_validate_source_event_ref_llm_receipt_underscore_plural_valid(self) -> None:
        self._assert_source_event_ref_valid("llm_receipt", "llm_receipts.jsonl#L7")

    def test_validate_source_event_ref_llm_receipt_hyphen_singular_valid(self) -> None:
        self._assert_source_event_ref_valid("llm_receipt", "llm-receipt.jsonl#L7")

    def test_validate_source_event_ref_protocol_learning_colon_row_id_valid(self) -> None:
        self._assert_source_event_ref_valid(
            "protocol_learning_event",
            ".aiwiki/state/protocol_learnings_age.json:some_key",
        )

    def test_validate_source_event_ref_empty_string_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "")

    def test_validate_source_event_ref_none_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", None)

    def test_validate_source_event_ref_non_string_int_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", 123)

    def test_validate_source_event_ref_non_string_list_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", ["runtime-history.jsonl#L1"])

    def test_validate_source_event_ref_missing_path_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "#L42")

    def test_validate_source_event_ref_path_traversal_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "../../etc/passwd#L1")

    def test_validate_source_event_ref_path_traversal_with_allowed_fragment_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "../../runtime-history.jsonl#L1")

    def test_validate_source_event_ref_absolute_path_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "/etc/passwd#L1")

    def test_validate_source_event_ref_source_kind_mismatch_rejected(self) -> None:
        self._assert_source_event_ref_rejected("llm_receipt", "runtime-history.jsonl#L1")

    def test_validate_source_event_ref_missing_line_suffix_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "runtime-history.jsonl")

    def test_validate_source_event_ref_non_positive_line_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "runtime-history.jsonl#L0")

    def test_validate_source_event_ref_negative_line_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "runtime-history.jsonl#L-1")

    def test_validate_source_event_ref_non_numeric_line_rejected(self) -> None:
        self._assert_source_event_ref_rejected("runtime_history", "runtime-history.jsonl#Labc")


class TestCanonicalDumpsFallbackPaths(unittest.TestCase):
    def test_canonical_dumps_preserves_unknown_top_level_in_sorted_tail(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["z_extra"] = "z"
        record["a_extra"] = "a"
        loaded = json.loads(canonical_dumps(record))
        keys = tuple(loaded.keys())
        self.assertEqual(keys[-2:], ("a_extra", "z_extra"))

    def test_canonical_dumps_scope_unknown_field_sorted_tail(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope["z_extra"] = "z"
        scope["a_extra"] = "a"
        loaded = json.loads(canonical_dumps(record))
        scope_keys = tuple(loaded["scope"].keys())
        self.assertEqual(scope_keys[-2:], ("a_extra", "z_extra"))

    def test_canonical_dumps_budget_unknown_field_sorted_tail(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["budget_hint"] = {"z": 1, "max_tokens": 2, "a": 3, "max_pages": 4}
        loaded = json.loads(canonical_dumps(record))
        self.assertEqual(tuple(loaded["budget_hint"].keys()), ("max_pages", "max_tokens", "a", "z"))

    def test_canonical_dumps_ignores_missing_optional_canonical_fields(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record.pop("budget_hint")
        scope = record["scope"]
        self.assertIsInstance(scope, dict)
        scope.pop("corpus_id")
        loaded = json.loads(canonical_dumps(record))
        self.assertNotIn("budget_hint", loaded)
        self.assertNotIn("corpus_id", loaded["scope"])

    def test_canonical_dumps_list_non_string_or_non_list_passes_through(self) -> None:
        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["evidence_refs"] = "not-a-list"
        loaded = json.loads(canonical_dumps(record))
        self.assertEqual(loaded["evidence_refs"], "not-a-list")

        record = _fixture_records("valid_signal_v1.jsonl")[0]
        record["evidence_refs"] = ["ok", 1]
        loaded = json.loads(canonical_dumps(record))
        self.assertEqual(loaded["evidence_refs"], ["ok", 1])


class TestTraceHelpers(unittest.TestCase):
    def test_parse_trace_id_rejects_non_string(self) -> None:
        with self.assertRaises(ValueError):
            parse_trace_id(123)  # type: ignore[arg-type]

    def test_parse_trace_id_uuid_version_guard_branch(self) -> None:
        class _FakeUUID:
            version = 1

            def __str__(self) -> str:
                return "550e8400-e29b-41d4-a716-446655440000"

        with patch("aiwiki.signals.schema.uuid.UUID", return_value=_FakeUUID()):
            with self.assertRaises(ValueError):
                parse_trace_id("550e8400-e29b-41d4-a716-446655440000")

    def test_detect_trace_id_conflict_false_paths(self) -> None:
        self.assertFalse(detect_trace_id_conflict([], {"trace_id": "x"}))
        self.assertFalse(
            detect_trace_id_conflict(
                [{"dedupe_key": "k", "trace_id": "t"}, "bad"],
                {"dedupe_key": "k", "trace_id": "t"},
            )
        )


class TestIsolation(unittest.TestCase):
    def test_from_aiwiki_signals_imports_stay_inside_signals_package(self) -> None:
        src_root = Path(__file__).resolve().parent.parent / "src" / "aiwiki"
        offending_paths: list[str] = []

        for path in src_root.rglob("*.py"):
            lines = path.read_text(encoding="utf-8").splitlines()
            if any("from aiwiki.signals" in line for line in lines):
                if not str(path).startswith(str(src_root / "signals")):
                    offending_paths.append(str(path.relative_to(src_root.parent.parent)))

        self.assertEqual(offending_paths, [])


if __name__ == "__main__":
    unittest.main()
