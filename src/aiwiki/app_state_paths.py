"""Path and state-id helpers kept out of the app_state hub."""

from __future__ import annotations

from pathlib import Path

from .app_utils import slugify


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


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


def today_snooze_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "today-snooze.json"


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
    return root / ".aiwiki" / "derived" / "agents" / f"{slugify(role)}.md"


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


def lint_reports_dir(root: Path) -> Path:
    return root / ".aiwiki" / "lint"


def execution_batches_dir(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-batches"


def execution_batch_receipt_path(root: Path, batch_id: str) -> Path:
    return execution_batches_dir(root) / f"{slugify(batch_id)}.json"


def execution_dry_run_path(root: Path, action_id: str) -> Path:
    from .render.paths import execution_bundles_dir

    return execution_bundles_dir(root) / f"{slugify(action_id)}-dry-run.json"


def run_notes_path(root: Path, run_id: str) -> Path:
    """Legacy path for retired run-progress notes (no longer written)."""

    return root / "output" / "control" / "runs" / slugify(run_id) / "thinking.md"


def material_archive_action_id(entry_id: str) -> str:
    return f"archive-{entry_id}"


def archive_dry_run_path(root: Path, entry_id: str) -> Path:
    from .render.paths import execution_bundles_dir

    return execution_bundles_dir(root) / f"{slugify(material_archive_action_id(entry_id))}-dry-run.json"


def rewrite_dry_run_path(root: Path, slug: str) -> Path:
    from .render.paths import execution_bundles_dir

    return execution_bundles_dir(root) / f"{slugify(f'rewrite-{slug}')}-dry-run.json"


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
