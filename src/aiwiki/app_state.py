"""Phase 0 path/state helpers extracted from aiwiki.app."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .app_utils import relative_path, render_json_document, runtime_write_operation, slugify

logger = logging.getLogger(__name__)


class CorruptStateError(RuntimeError):
    """Raised by strict state loaders when the on-disk JSON/JSONL is unreadable.

    M9-P0.4: hard boundary for callers that cannot tolerate silent fallback to
    empty state (e.g. authoritative reads where missing data == data loss).
    """

    def __init__(self, *, path: Path, reason: str, line_number: int | None = None) -> None:
        self.path = path
        self.reason = reason
        self.line_number = line_number
        loc = f"{path}" + (f":{line_number}" if line_number else "")
        super().__init__(f"corrupt state at {loc}: {reason}")

DEFAULT_PROTOCOL = "general"


KNOWLEDGE_LIFECYCLE_KINDS = ("concept", "decision", "judgment")


KNOWLEDGE_LIFECYCLE_STATES = ("active", "review", "deferred", "retired", "revisit")


JUDGMENT_LIFECYCLE_STATES = ("formed", "active", "under-review", "revised", "retired")


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


def default_manifest() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    if not path.exists():
        return default_manifest()
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def machine_memory_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory.json"


def cache_db_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache.db"


def cache_status_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "cache-status.json"


def machine_memory_graph_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache" / "machine-memory-graph.json"


def machine_memory_graph_html_path(root: Path) -> Path:
    return root / "output" / "graph" / "machine-memory.html"


def review_center_html_path(root: Path) -> Path:
    return root / "output" / "review" / "review-center.html"


def furnace_center_html_path(root: Path) -> Path:
    return root / "output" / "control" / "furnace-center.html"


def shell_summary_path(root: Path) -> Path:
    return root / "output" / "control" / "shell-summary.json"


def product_shell_html_path(root: Path) -> Path:
    return root / "output" / "control" / "product-shell.html"


def execution_center_html_path(root: Path) -> Path:
    return root / "output" / "control" / "execution-center.html"


def execution_audit_html_path(root: Path) -> Path:
    return root / "output" / "control" / "execution-audit.html"


def machine_memory_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-history.jsonl"


def machine_memory_drift_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "drift-report.md"


def graph_health_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "graph-health.md"


def machine_memory_topology_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-topology.md"


def machine_memory_actions_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-actions.md"


def machine_memory_repair_plan_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "machine-memory-repair-plan.md"


def execution_center_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "execution-center.md"


def execution_audit_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "execution-audit.md"


def agent_workbench_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "agent-workbench.md"


def agent_pack_path(root: Path, role: str) -> Path:
    return root / "output" / "agents" / f"{slugify(role)}.md"


def output_packs_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "output-packs.md"


def domain_pilots_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def run_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "runs.jsonl"


def llm_receipt_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "llm-receipts.jsonl"


def execution_batch_receipt_path(root: Path, batch_id: str) -> Path:
    return root / "output" / "control" / "execution-batches" / f"{slugify(batch_id)}.json"


def execution_dry_run_path(root: Path, action_id: str) -> Path:
    return root / "output" / "control" / "execution-bundles" / f"{slugify(action_id)}-dry-run.json"


def archive_dry_run_path(root: Path, entry_id: str) -> Path:
    return root / "output" / "control" / "execution-bundles" / f"{slugify(material_archive_action_id(entry_id))}-dry-run.json"


def rewrite_dry_run_path(root: Path, slug: str) -> Path:
    return root / "output" / "control" / "execution-bundles" / f"{slugify(f'rewrite-{slug}')}-dry-run.json"


def execution_policy_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"


def concept_quality_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "concept-quality.md"


def concept_rewrite_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "rewrite-proposals.md"


def concept_rewrite_proposal_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "rewrite-proposals" / f"{slug}.md"


def machine_memory_action_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-actions.json"


def planner_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "planner-state.json"


def query_route_telemetry_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "query-route-telemetry.json"


def concept_rewrite_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-rewrite-proposals.json"


def l3_proposal_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "l3-proposals.json"


def manual_link_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manual-links.json"


def repair_backlog_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "repair-backlog.md"


def judgment_assets_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "judgment-assets.md"


def cognitive_history_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "cognitive-history.md"


def aging_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "aging-report.md"


def nightly_health_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "nightly-health.json"


def compile_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "compile-state.json"


def concept_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-build-state.json"


def machine_memory_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-build-state.json"


def ranking_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "ranking-build-state.json"


def output_pack_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "output-pack-build-state.json"


def domain_pilot_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "domain-pilot-build-state.json"


def material_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-state.json"


def active_corpora_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "active-corpora.json"


def output_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "output-candidates.json"


def runtime_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime-history.jsonl"


def material_routing_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-routing.json"


def archive_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "archive-candidates.json"


def knowledge_lifecycle_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle.json"


def knowledge_lifecycle_override_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"


def material_archive_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-archives.json"


def load_json_document(path: Path) -> dict[str, Any]:
    """Best-effort JSON loader. Logs a warning on corruption and returns {} as fallback.

    Use this only when the caller's contract explicitly tolerates missing/corrupt state
    (e.g. preview, telemetry, drift hints). Authoritative reads must use
    `load_json_document_strict` instead.
    """
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(
            "corrupt JSON state at %s (line=%d col=%d): %s; returning empty document",
            path,
            getattr(exc, "lineno", -1),
            getattr(exc, "colno", -1),
            exc.msg,
        )
        return {}
    if not isinstance(document, dict):
        logger.warning(
            "non-object JSON top-level at %s (got %s); returning empty document",
            path,
            type(document).__name__,
        )
        return {}
    return document


def load_json_document_strict(path: Path) -> dict[str, Any]:
    """Strict JSON loader. Raises `CorruptStateError` if the file exists but is unparseable.

    M9-P0.4: use this in authoritative read paths where silent fallback to {} would
    constitute data loss or hide drift.
    """
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorruptStateError(
            path=path,
            reason=f"json decode failed: {exc.msg}",
            line_number=getattr(exc, "lineno", None),
        ) from exc
    if not isinstance(document, dict):
        raise CorruptStateError(
            path=path,
            reason=f"expected JSON object, got {type(document).__name__}",
        )
    return document


def save_json_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_document(document), encoding="utf-8")


def load_jsonl_documents(path: Path) -> list[dict[str, Any]]:
    """Best-effort JSONL loader. Logs a warning per corrupt line and skips it.

    Use this only when the caller can tolerate partial truth. Authoritative reads must
    use `load_jsonl_documents_strict`.
    """
    if not path.exists():
        return []
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "corrupt JSONL line at %s:%d: %s; skipping",
                    path,
                    index,
                    exc.msg,
                )
                continue
            if isinstance(document, dict):
                documents.append(document)
            else:
                logger.warning(
                    "non-object JSONL record at %s:%d (got %s); skipping",
                    path,
                    index,
                    type(document).__name__,
                )
    return documents


def load_jsonl_documents_strict(path: Path) -> list[dict[str, Any]]:
    """Strict JSONL loader. Raises `CorruptStateError` on the first unparseable record.

    M9-P0.4: use this for authoritative streams (receipts, audit, runtime history) where
    silent skipping of records would hide system state.
    """
    if not path.exists():
        return []
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    path=path,
                    reason=f"json decode failed: {exc.msg}",
                    line_number=index,
                ) from exc
            if not isinstance(document, dict):
                raise CorruptStateError(
                    path=path,
                    reason=f"expected JSON object, got {type(document).__name__}",
                    line_number=index,
                )
            documents.append(document)
    return documents


def _next_jsonl_line_number(path: Path) -> int:
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count + 1


def default_compile_state() -> dict[str, Any]:
    return {
        "version": 1,
        "compiled_at": "",
        "manifest_entry_count": 0,
        "dirty_source_ids": [],
        "clean_source_ids": [],
        "dirty_concept_source_ids": [],
        "clean_concept_source_ids": [],
        "dirty_concept_slugs": [],
        "clean_concept_slugs": [],
        "dirty_machine_memory_source_ids": [],
        "clean_machine_memory_source_ids": [],
        "dirty_machine_memory_concept_slugs": [],
        "clean_machine_memory_concept_slugs": [],
        "machine_memory_core_reused": False,
        "dirty_ranking_source_ids": [],
        "clean_ranking_source_ids": [],
        "dirty_ranking_concept_slugs": [],
        "clean_ranking_concept_slugs": [],
        "dirty_output_pack_groups": [],
        "clean_output_pack_groups": [],
        "dirty_domain_pilot_protocols": [],
        "clean_domain_pilot_protocols": [],
        "dirty_index_artifacts": [],
        "clean_index_artifacts": [],
        "dirty_maintenance_artifacts": [],
        "clean_maintenance_artifacts": [],
        "drift_warnings": [],
        "phase_summary": [],
    }


def default_cache_status() -> dict[str, Any]:
    return {
        "version": 1,
        "enabled": False,
        "schema_version": 0,
        "updated_at": "",
        "db_path": "",
        "state_path": "",
        "row_counts": {},
        "stats": {
            "query_hits": 0,
            "query_misses": 0,
            "query_bypasses": 0,
            "compile_syncs": 0,
            "rebuilds": 0,
            "drops": 0,
        },
        "last_sync": {},
        "last_query": {},
        "last_drop": {},
        "last_rebuild": {},
    }


def load_compile_state(root: Path) -> dict[str, Any]:
    document = load_json_document(compile_state_path(root))
    if not isinstance(document, dict):
        return default_compile_state()
    dirty_source_ids = document.get("dirty_source_ids", [])
    clean_source_ids = document.get("clean_source_ids", [])
    dirty_concept_source_ids = document.get("dirty_concept_source_ids", [])
    clean_concept_source_ids = document.get("clean_concept_source_ids", [])
    dirty_concept_slugs = document.get("dirty_concept_slugs", [])
    clean_concept_slugs = document.get("clean_concept_slugs", [])
    dirty_machine_memory_source_ids = document.get("dirty_machine_memory_source_ids", [])
    clean_machine_memory_source_ids = document.get("clean_machine_memory_source_ids", [])
    dirty_machine_memory_concept_slugs = document.get("dirty_machine_memory_concept_slugs", [])
    clean_machine_memory_concept_slugs = document.get("clean_machine_memory_concept_slugs", [])
    dirty_ranking_source_ids = document.get("dirty_ranking_source_ids", [])
    clean_ranking_source_ids = document.get("clean_ranking_source_ids", [])
    dirty_ranking_concept_slugs = document.get("dirty_ranking_concept_slugs", [])
    clean_ranking_concept_slugs = document.get("clean_ranking_concept_slugs", [])
    dirty_output_pack_groups = document.get("dirty_output_pack_groups", [])
    clean_output_pack_groups = document.get("clean_output_pack_groups", [])
    dirty_domain_pilot_protocols = document.get("dirty_domain_pilot_protocols", [])
    clean_domain_pilot_protocols = document.get("clean_domain_pilot_protocols", [])
    dirty_index_artifacts = document.get("dirty_index_artifacts", [])
    clean_index_artifacts = document.get("clean_index_artifacts", [])
    dirty_maintenance_artifacts = document.get("dirty_maintenance_artifacts", [])
    clean_maintenance_artifacts = document.get("clean_maintenance_artifacts", [])
    drift_warnings = document.get("drift_warnings", [])
    phase_summary = document.get("phase_summary")
    if (
        not isinstance(dirty_source_ids, list)
        or not isinstance(clean_source_ids, list)
        or not isinstance(dirty_concept_source_ids, list)
        or not isinstance(clean_concept_source_ids, list)
        or not isinstance(dirty_concept_slugs, list)
        or not isinstance(clean_concept_slugs, list)
        or not isinstance(dirty_machine_memory_source_ids, list)
        or not isinstance(clean_machine_memory_source_ids, list)
        or not isinstance(dirty_machine_memory_concept_slugs, list)
        or not isinstance(clean_machine_memory_concept_slugs, list)
        or not isinstance(dirty_ranking_source_ids, list)
        or not isinstance(clean_ranking_source_ids, list)
        or not isinstance(dirty_ranking_concept_slugs, list)
        or not isinstance(clean_ranking_concept_slugs, list)
        or not isinstance(dirty_output_pack_groups, list)
        or not isinstance(clean_output_pack_groups, list)
        or not isinstance(dirty_domain_pilot_protocols, list)
        or not isinstance(clean_domain_pilot_protocols, list)
        or not isinstance(dirty_index_artifacts, list)
        or not isinstance(clean_index_artifacts, list)
        or not isinstance(dirty_maintenance_artifacts, list)
        or not isinstance(clean_maintenance_artifacts, list)
        or not isinstance(drift_warnings, list)
        or not isinstance(phase_summary, list)
    ):
        return default_compile_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "compiled_at": str(document.get("compiled_at") or ""),
        "manifest_entry_count": int(document.get("manifest_entry_count", 0) or 0),
        "dirty_source_ids": [str(entry_id) for entry_id in dirty_source_ids if str(entry_id)],
        "clean_source_ids": [str(entry_id) for entry_id in clean_source_ids if str(entry_id)],
        "dirty_concept_source_ids": [str(entry_id) for entry_id in dirty_concept_source_ids if str(entry_id)],
        "clean_concept_source_ids": [str(entry_id) for entry_id in clean_concept_source_ids if str(entry_id)],
        "dirty_concept_slugs": [str(slug) for slug in dirty_concept_slugs if str(slug)],
        "clean_concept_slugs": [str(slug) for slug in clean_concept_slugs if str(slug)],
        "dirty_machine_memory_source_ids": [
            str(entry_id) for entry_id in dirty_machine_memory_source_ids if str(entry_id)
        ],
        "clean_machine_memory_source_ids": [
            str(entry_id) for entry_id in clean_machine_memory_source_ids if str(entry_id)
        ],
        "dirty_machine_memory_concept_slugs": [
            str(slug) for slug in dirty_machine_memory_concept_slugs if str(slug)
        ],
        "clean_machine_memory_concept_slugs": [
            str(slug) for slug in clean_machine_memory_concept_slugs if str(slug)
        ],
        "machine_memory_core_reused": bool(document.get("machine_memory_core_reused", False)),
        "dirty_ranking_source_ids": [str(entry_id) for entry_id in dirty_ranking_source_ids if str(entry_id)],
        "clean_ranking_source_ids": [str(entry_id) for entry_id in clean_ranking_source_ids if str(entry_id)],
        "dirty_ranking_concept_slugs": [str(slug) for slug in dirty_ranking_concept_slugs if str(slug)],
        "clean_ranking_concept_slugs": [str(slug) for slug in clean_ranking_concept_slugs if str(slug)],
        "dirty_output_pack_groups": [str(group) for group in dirty_output_pack_groups if str(group)],
        "clean_output_pack_groups": [str(group) for group in clean_output_pack_groups if str(group)],
        "dirty_domain_pilot_protocols": [
            str(protocol) for protocol in dirty_domain_pilot_protocols if str(protocol)
        ],
        "clean_domain_pilot_protocols": [
            str(protocol) for protocol in clean_domain_pilot_protocols if str(protocol)
        ],
        "dirty_index_artifacts": [str(path) for path in dirty_index_artifacts if str(path)],
        "clean_index_artifacts": [str(path) for path in clean_index_artifacts if str(path)],
        "dirty_maintenance_artifacts": [str(path) for path in dirty_maintenance_artifacts if str(path)],
        "clean_maintenance_artifacts": [str(path) for path in clean_maintenance_artifacts if str(path)],
        "drift_warnings": [warning for warning in drift_warnings if isinstance(warning, dict)],
        "phase_summary": [phase for phase in phase_summary if isinstance(phase, dict)],
    }


def save_compile_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(compile_state_path(root), document)


def load_cache_status(root: Path) -> dict[str, Any]:
    document = load_json_document(cache_status_path(root))
    if not isinstance(document, dict):
        return default_cache_status()
    row_counts = document.get("row_counts")
    stats = document.get("stats")
    last_sync = document.get("last_sync")
    last_query = document.get("last_query")
    last_drop = document.get("last_drop")
    last_rebuild = document.get("last_rebuild", {})
    if not isinstance(row_counts, dict) or not isinstance(stats, dict):
        return default_cache_status()
    if (
        not isinstance(last_sync, dict)
        or not isinstance(last_query, dict)
        or not isinstance(last_drop, dict)
        or not isinstance(last_rebuild, dict)
    ):
        return default_cache_status()
    return {
        "version": int(document.get("version", 1) or 1),
        "enabled": bool(document.get("enabled", False)),
        "schema_version": int(document.get("schema_version", 0) or 0),
        "updated_at": str(document.get("updated_at") or ""),
        "db_path": str(document.get("db_path") or relative_path(root, cache_db_path(root))),
        "state_path": str(document.get("state_path") or relative_path(root, cache_status_path(root))),
        "row_counts": {str(key): int(value or 0) for key, value in row_counts.items()},
        "stats": {
            "query_hits": int(stats.get("query_hits", 0) or 0),
            "query_misses": int(stats.get("query_misses", 0) or 0),
            "query_bypasses": int(stats.get("query_bypasses", 0) or 0),
            "compile_syncs": int(stats.get("compile_syncs", 0) or 0),
            "rebuilds": int(stats.get("rebuilds", 0) or 0),
            "drops": int(stats.get("drops", 0) or 0),
        },
        "last_sync": dict(last_sync),
        "last_query": dict(last_query),
        "last_drop": dict(last_drop),
        "last_rebuild": dict(last_rebuild),
    }


def save_cache_status(root: Path, document: dict[str, Any]) -> None:
    save_json_document(cache_status_path(root), document)


def default_concept_build_state() -> dict[str, Any]:
    return {"version": 2, "generated_at": "", "entry_records": {}}


def load_concept_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_build_state_path(root))
    if not isinstance(document, dict):
        return default_concept_build_state()
    version = int(document.get("version", 1) or 1)
    if version < 2:
        return default_concept_build_state()
    entry_records = document.get("entry_records")
    if not isinstance(entry_records, dict):
        return default_concept_build_state()
    normalized_records: dict[str, dict[str, Any]] = {}
    for entry_id, record in entry_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        terms = record.get("terms", [])
        if not isinstance(terms, list):
            continue
        normalized_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
            "terms": [str(label) for label in terms if str(label)],
        }
    return {
        "version": version,
        "generated_at": str(document.get("generated_at") or ""),
        "entry_records": normalized_records,
    }


def save_concept_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(concept_build_state_path(root), document)


def default_machine_memory_build_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "source_records": {}, "concept_records": {}}


def load_machine_memory_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(machine_memory_build_state_path(root))
    if not isinstance(document, dict):
        return default_machine_memory_build_state()
    source_records = document.get("source_records")
    concept_records = document.get("concept_records")
    if not isinstance(source_records, dict) or not isinstance(concept_records, dict):
        return default_machine_memory_build_state()

    normalized_source_records: dict[str, dict[str, str]] = {}
    for entry_id, record in source_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        normalized_source_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
        }

    normalized_concept_records: dict[str, dict[str, str]] = {}
    for slug, record in concept_records.items():
        if not isinstance(slug, str) or not slug or not isinstance(record, dict):
            continue
        normalized_concept_records[slug] = {
            "input_signature": str(record.get("input_signature") or ""),
        }

    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "source_records": normalized_source_records,
        "concept_records": normalized_concept_records,
    }


def save_machine_memory_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(machine_memory_build_state_path(root), document)


def default_ranking_build_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "source_records": {}, "concept_records": {}}


def load_ranking_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(ranking_build_state_path(root))
    if not isinstance(document, dict):
        return default_ranking_build_state()
    source_records = document.get("source_records")
    concept_records = document.get("concept_records")
    if not isinstance(source_records, dict) or not isinstance(concept_records, dict):
        return default_ranking_build_state()

    normalized_source_records: dict[str, dict[str, Any]] = {}
    for entry_id, record in source_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        summary_or_preview = str(record.get("summary_or_preview") or "")
        concept_terms = record.get("concept_terms")
        if not isinstance(concept_terms, list):
            continue
        normalized_source_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
            "summary_or_preview": summary_or_preview,
            "concept_terms": [str(term) for term in concept_terms if str(term)],
        }

    normalized_concept_records: dict[str, dict[str, Any]] = {}
    for slug, record in concept_records.items():
        if not isinstance(slug, str) or not slug or not isinstance(record, dict):
            continue
        source_pages = record.get("source_pages")
        if not isinstance(source_pages, list):
            continue
        normalized_concept_records[slug] = {
            "input_signature": str(record.get("input_signature") or ""),
            "title": str(record.get("title") or slug),
            "path": str(record.get("path") or f"wiki/concepts/{slug}.md"),
            "source_pages": [str(path) for path in source_pages if str(path)],
            "content": str(record.get("content") or ""),
        }

    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "source_records": normalized_source_records,
        "concept_records": normalized_concept_records,
    }


def save_ranking_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(ranking_build_state_path(root), document)


def default_output_pack_build_state() -> dict[str, Any]:
    return {
        "version": 1,
        "generated_at": "",
        "active_protocol": DEFAULT_PROTOCOL,
        "group_records": {},
        "lifecycle_summary": {},
        "review_packs": [],
        "decision_memos": [],
        "sop_drafts": [],
        "counts": {
            "review_packs": 0,
            "decision_memos": 0,
            "sop_drafts": 0,
            "execution_proposal_sops": 0,
        },
    }


def load_output_pack_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(output_pack_build_state_path(root))
    if not isinstance(document, dict):
        return default_output_pack_build_state()
    group_records = document.get("group_records")
    lifecycle_summary = document.get("lifecycle_summary")
    review_packs = document.get("review_packs")
    decision_memos = document.get("decision_memos")
    sop_drafts = document.get("sop_drafts")
    counts = document.get("counts")
    if (
        not isinstance(group_records, dict)
        or not isinstance(lifecycle_summary, dict)
        or not isinstance(review_packs, list)
        or not isinstance(decision_memos, list)
        or not isinstance(sop_drafts, list)
        or not isinstance(counts, dict)
    ):
        return default_output_pack_build_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "group_records": {
            str(group): {"input_signature": str(record.get("input_signature") or "")}
            for group, record in group_records.items()
            if str(group) and isinstance(record, dict)
        },
        "lifecycle_summary": lifecycle_summary,
        "review_packs": [record for record in review_packs if isinstance(record, dict)],
        "decision_memos": [record for record in decision_memos if isinstance(record, dict)],
        "sop_drafts": [record for record in sop_drafts if isinstance(record, dict)],
        "counts": {
            "review_packs": int(counts.get("review_packs", 0) or 0),
            "decision_memos": int(counts.get("decision_memos", 0) or 0),
            "sop_drafts": int(counts.get("sop_drafts", 0) or 0),
            "execution_proposal_sops": int(counts.get("execution_proposal_sops", 0) or 0),
        },
    }


def save_output_pack_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(output_pack_build_state_path(root), document)


def default_domain_pilot_build_state() -> dict[str, Any]:
    return {
        "version": 1,
        "generated_at": "",
        "active_protocol": DEFAULT_PROTOCOL,
        "protocol_records": {},
        "scorecards": [],
    }


def load_domain_pilot_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(domain_pilot_build_state_path(root))
    if not isinstance(document, dict):
        return default_domain_pilot_build_state()
    protocol_records = document.get("protocol_records")
    scorecards = document.get("scorecards")
    if not isinstance(protocol_records, dict) or not isinstance(scorecards, list):
        return default_domain_pilot_build_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "protocol_records": {
            str(protocol): {"input_signature": str(record.get("input_signature") or "")}
            for protocol, record in protocol_records.items()
            if str(protocol) and isinstance(record, dict)
        },
        "scorecards": [record for record in scorecards if isinstance(record, dict)],
    }


def save_domain_pilot_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(domain_pilot_build_state_path(root), document)


def default_material_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_material_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_state_path(root))
    if not isinstance(document, dict):
        return default_material_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_state_path(root), document)


def default_active_corpora_state() -> dict[str, Any]:
    return {"version": 1, "corpora": []}


def load_active_corpora_state(root: Path) -> dict[str, Any]:
    document = load_json_document(active_corpora_state_path(root))
    if not isinstance(document, dict):
        return default_active_corpora_state()
    corpora = document.get("corpora")
    if not isinstance(corpora, list):
        return default_active_corpora_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "corpora": [corpus for corpus in corpora if isinstance(corpus, dict)],
    }


def save_active_corpora_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(active_corpora_state_path(root), document)


def default_output_candidates_state() -> dict[str, Any]:
    return {"version": 1, "candidates": []}


def load_output_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(output_candidates_state_path(root))
    if not isinstance(document, dict):
        return default_output_candidates_state()
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        return default_output_candidates_state()
    return {"version": int(document.get("version", 1) or 1), "candidates": [item for item in candidates if isinstance(item, dict)]}


def save_output_candidates_state(root: Path, state: dict[str, Any]) -> None:
    save_json_document(output_candidates_state_path(root), state)


def upsert_output_candidate(
    root: Path,
    *,
    artifact_ref: str,
    candidate_state: str,
    created_at: str,
    updated_at: str,
    format: str,
    protocol: str,
    corpus_id: str,
    question: str,
    promoted_to: str = "",
    promoted_at: str = "",
    demoted_at: str = "",
    promotion_origin: str = "manual",
) -> dict[str, Any]:
    state = load_output_candidates_state(root)
    candidates = list(state.get("candidates", []))
    target = None
    for candidate in candidates:
        if str(candidate.get("artifact_ref") or "") == artifact_ref:
            target = candidate
            break
    if target is None:
        target = {"artifact_ref": artifact_ref, "created_at": created_at}
        candidates.append(target)
    target.update(
        {
            "artifact_ref": artifact_ref,
            "candidate_state": candidate_state,
            "created_at": created_at,
            "updated_at": updated_at,
            "format": format,
            "protocol": protocol,
            "corpus_id": corpus_id,
            "question": question,
            "promoted_to": promoted_to,
            "promoted_at": promoted_at,
            "demoted_at": demoted_at,
            "promotion_origin": promotion_origin or "manual",
        }
    )
    state = {"version": 1, "candidates": candidates}
    save_output_candidates_state(root, state)
    return target


def remove_output_candidate(root: Path, artifact_ref: str) -> bool:
    state = load_output_candidates_state(root)
    candidates = [c for c in state.get("candidates", []) if str(c.get("artifact_ref") or "") != artifact_ref]
    removed = len(candidates) != len(state.get("candidates", []))
    save_output_candidates_state(root, {"version": 1, "candidates": candidates})
    return removed


def load_runtime_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(runtime_history_path(root))


def load_run_log_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(run_log_path(root))


def load_llm_receipt_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(llm_receipt_log_path(root))


def append_runtime_history(root: Path, event: dict[str, Any]) -> None:
    path = runtime_history_path(root)
    line_number = _next_jsonl_line_number(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    from .execution.audit_preview import append_universal_audit_record

    append_universal_audit_record(
        root,
        source_stream="runtime_history",
        source_ref=f"{relative_path(root, path)}#L{line_number}",
        document=event,
    )


def default_material_routing_state() -> dict[str, Any]:
    return {"version": 1, "computed_at": "", "active_protocol": DEFAULT_PROTOCOL, "entries": []}


def load_material_routing_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_routing_state_path(root))
    if not isinstance(document, dict):
        return default_material_routing_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_routing_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "computed_at": str(document.get("computed_at") or ""),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_routing_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_routing_state_path(root), document)


def default_archive_candidates_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_archive_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(archive_candidates_state_path(root))
    if not isinstance(document, dict):
        return default_archive_candidates_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_archive_candidates_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_archive_candidates_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(archive_candidates_state_path(root), document)


def default_knowledge_lifecycle_state() -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    return {
        "version": 1,
        "generated_at": "",
        "entries": [],
        "counts": {
            "total": 0,
            "by_state": dict(by_state),
            "by_kind": {kind: {"total": 0, "by_state": dict(by_state)} for kind in KNOWLEDGE_LIFECYCLE_KINDS},
            "invalidated": 0,
            "active_corpus_linked": 0,
        },
    }


def load_knowledge_lifecycle_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_state_path(root))
    if not isinstance(document, dict):
        return default_knowledge_lifecycle_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_knowledge_lifecycle_state()
    counts = document.get("counts")
    if not isinstance(counts, dict):
        counts = default_knowledge_lifecycle_state()["counts"]
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
        "counts": counts,
    }


def save_knowledge_lifecycle_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_state_path(root), document)


def default_knowledge_lifecycle_override_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_override_state_path(root))
    if not isinstance(document, dict):
        return default_knowledge_lifecycle_override_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_knowledge_lifecycle_override_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_knowledge_lifecycle_override_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_override_state_path(root), document)


def ensure_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    state = load_knowledge_lifecycle_override_state(root)
    path = knowledge_lifecycle_override_state_path(root)
    if not path.exists():
        save_knowledge_lifecycle_override_state(root, state)
    return state


def active_knowledge_lifecycle_overrides(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("path") or ""): entry
        for entry in document.get("entries", [])
        if isinstance(entry, dict) and bool(entry.get("active")) and str(entry.get("path") or "")
    }


def default_material_archive_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_material_archive_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_archive_state_path(root))
    if not isinstance(document, dict):
        return default_material_archive_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_material_archive_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def save_material_archive_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_archive_state_path(root), document)


def active_material_archive_entries(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id") or ""): entry
        for entry in document.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id") and bool(entry.get("active", False))
    }


def active_archived_material_ids(root: Path) -> set[str]:
    return set(active_material_archive_entries(load_material_archive_state(root)))


def material_archive_action_id(entry_id: str) -> str:
    return f"archive-{entry_id}"


def default_machine_memory_action_state() -> dict[str, Any]:
    return {"version": 1, "actions": []}


def load_machine_memory_action_state(root: Path) -> dict[str, Any]:
    document = load_json_document(machine_memory_action_state_path(root))
    if not isinstance(document, dict):
        return default_machine_memory_action_state()
    actions = document.get("actions")
    if not isinstance(actions, list):
        return default_machine_memory_action_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "actions": [action for action in actions if isinstance(action, dict)],
    }


@runtime_write_operation
def save_machine_memory_action_state(root: Path, document: dict[str, Any]) -> None:
    machine_memory_action_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def default_planner_state() -> dict[str, Any]:
    return {
        "version": 1,
        "generated_at": "",
        "state_path": "",
        "active_protocol": DEFAULT_PROTOCOL,
        "pending_proposals": [],
        "priority_queue": [],
        "dependency_graph": {"nodes": [], "edges": []},
        "next_action": {},
        "executed_actions": [],
        "counts": {"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 0},
    }


def load_planner_state(root: Path) -> dict[str, Any]:
    document = load_json_document(planner_state_path(root))
    if not isinstance(document, dict):
        return default_planner_state()
    pending_proposals = document.get("pending_proposals")
    priority_queue = document.get("priority_queue")
    dependency_graph = document.get("dependency_graph")
    counts = document.get("counts")
    next_action = document.get("next_action")
    executed_actions = document.get("executed_actions")
    if not isinstance(pending_proposals, list) or not isinstance(priority_queue, list):
        return default_planner_state()
    if not isinstance(dependency_graph, dict) or not isinstance(counts, dict) or not isinstance(executed_actions, list):
        return default_planner_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "state_path": str(document.get("state_path") or relative_path(root, planner_state_path(root))),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "pending_proposals": [proposal for proposal in pending_proposals if isinstance(proposal, dict)],
        "priority_queue": [item for item in priority_queue if isinstance(item, dict)],
        "dependency_graph": {
            "nodes": [node for node in dependency_graph.get("nodes", []) if isinstance(node, dict)],
            "edges": [edge for edge in dependency_graph.get("edges", []) if isinstance(edge, dict)],
        },
        "next_action": dict(next_action) if isinstance(next_action, dict) else {},
        "executed_actions": [item for item in executed_actions if isinstance(item, dict)],
        "counts": {
            "pending_proposals": int(counts.get("pending_proposals", 0) or 0),
            "blocked": int(counts.get("blocked", 0) or 0),
            "unblocked": int(counts.get("unblocked", 0) or 0),
            "executed_actions": int(counts.get("executed_actions", 0) or 0),
        },
    }


def save_planner_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(planner_state_path(root), document)


def default_query_route_telemetry() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "state_path": "",
        "entries": [],
        "strategy_counts": {},
        "protocol_counts": {},
        "last_entry": {},
    }


def load_query_route_telemetry(root: Path) -> dict[str, Any]:
    document = load_json_document(query_route_telemetry_path(root))
    if not isinstance(document, dict):
        return default_query_route_telemetry()
    entries = document.get("entries")
    strategy_counts = document.get("strategy_counts")
    protocol_counts = document.get("protocol_counts")
    last_entry = document.get("last_entry")
    if not isinstance(entries, list) or not isinstance(strategy_counts, dict) or not isinstance(protocol_counts, dict):
        return default_query_route_telemetry()
    return {
        "version": int(document.get("version", 1) or 1),
        "updated_at": str(document.get("updated_at") or ""),
        "state_path": str(document.get("state_path") or relative_path(root, query_route_telemetry_path(root))),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
        "strategy_counts": {str(key): int(value or 0) for key, value in strategy_counts.items()},
        "protocol_counts": {str(key): int(value or 0) for key, value in protocol_counts.items()},
        "last_entry": dict(last_entry) if isinstance(last_entry, dict) else {},
    }


def save_query_route_telemetry(root: Path, document: dict[str, Any]) -> None:
    save_json_document(query_route_telemetry_path(root), document)


def load_machine_memory(root: Path) -> dict[str, Any]:
    memory = load_json_document(machine_memory_state_path(root))
    return memory if isinstance(memory, dict) else {}


def default_concept_rewrite_state() -> dict[str, Any]:
    return {"version": 1, "proposals": []}


def load_concept_rewrite_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_rewrite_state_path(root))
    if not isinstance(document, dict):
        return default_concept_rewrite_state()
    proposals = document.get("proposals")
    if not isinstance(proposals, list):
        return default_concept_rewrite_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "proposals": [proposal for proposal in proposals if isinstance(proposal, dict)],
    }


@runtime_write_operation
def save_concept_rewrite_state(root: Path, document: dict[str, Any]) -> None:
    concept_rewrite_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def default_manual_link_state() -> dict[str, Any]:
    return {"version": 1, "source_to_concept": []}


def load_manual_link_state(root: Path) -> dict[str, Any]:
    document = load_json_document(manual_link_state_path(root))
    if not isinstance(document, dict):
        return default_manual_link_state()
    source_to_concept = document.get("source_to_concept")
    if not isinstance(source_to_concept, list):
        return default_manual_link_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "source_to_concept": [item for item in source_to_concept if isinstance(item, dict)],
    }


@runtime_write_operation
def save_manual_link_state(root: Path, document: dict[str, Any]) -> None:
    manual_link_state_path(root).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
