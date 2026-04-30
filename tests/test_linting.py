from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_linting import (
    _LINT_REPORT_KEEP,
    Finding,
    _lint_curated_phase,
    _lint_governance_phase,
    _lint_layout_phase,
    _lint_runtime_phase,
    _LintContext,
    _rotate_lint_reports,
    _write_lint_report,
    render_repair_backlog,
)
from aiwiki.app_protocol import PROTOCOL_LIBRARY, ensure_layout, load_protocol_state
from aiwiki.app_utils import render_frontmatter


class LintingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "output" / "lint").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_markdown(self, path: Path, frontmatter: dict[str, object], body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{render_frontmatter(frontmatter)}\n\n{body.strip()}\n", encoding="utf-8")

    def test_write_lint_report_handles_empty_findings(self) -> None:
        context = _LintContext(root=self.root, manifest={"entries": []}, findings=[])

        result = _write_lint_report(context)

        report_path = self.root / result["path"]
        self.assertTrue(report_path.exists())
        self.assertIn("没有发现问题", report_path.read_text(encoding="utf-8"))
        self.assertEqual(result["counts"], {"errors": 0, "warnings": 0})

    def test_render_repair_backlog_renders_rich_and_empty_sections(self) -> None:
        active_protocol = next(
            slug for slug, profile in PROTOCOL_LIBRARY.items() if isinstance(profile, dict) and profile.get("nightly")
        )
        rich_backlog = render_repair_backlog(
            {"changed_pages": 3, "machine_memory_changed": True},
            {
                "counts": {"errors": 1, "warnings": 1},
                "findings": [
                    {"severity": "error", "path": "wiki/sources/a.md", "message": "missing source"},
                    {"severity": "warn", "path": "wiki/concepts/a.md", "message": "thin concept"},
                ],
                "path": "output/lint/lint-rich.md",
            },
            {
                "drift": {"sources_without_concepts": ["src-1"]},
                "health": {
                    "isolated_source_ids": ["src-2"],
                    "singleton_concept_slugs": ["single-concept"],
                    "bridge_concept_slugs": ["bridge-concept"],
                    "overloaded_concept_slugs": ["wide-concept"],
                    "actions": [
                        {
                            "id": "safe-apply-action",
                            "kind": "add-source-concept-link",
                            "title": "Repair alpha link",
                            "primary_path": "wiki/sources/src-1.md",
                            "secondary_path": "wiki/concepts/alpha.md",
                            "status": "accepted",
                            "priority": "low",
                            "occurrences": 2,
                            "command_hint": "apply-action safe-apply-action --dry-run",
                        }
                    ],
                    "overdue_actions": [
                        {
                            "id": "safe-apply-action",
                            "title": "Repair alpha link",
                            "status": "accepted",
                            "revisit_after": "2025-01-01T00:00:00+00:00",
                        },
                        {
                            "id": "overdue-action",
                            "title": "Refresh judgment",
                            "status": "proposed",
                            "revisit_after": "2025-01-02T00:00:00+00:00",
                        },
                    ],
                    "escalated_actions": [
                        {"id": "safe-apply-action", "title": "Repair alpha link", "status": "accepted"}
                    ],
                    "inactive_actions": [
                        {"id": "inactive-action", "title": "Old repair", "inactive_since": "2025-01-03T00:00:00+00:00"}
                    ],
                    "repair_plan": {
                        "counts": {"ready": 1, "triage": 1, "batches": 1, "proposals": 1},
                        "execution_batches": [
                            {
                                "label": "Alpha batch",
                                "actions": [{"id": "safe-apply-action"}],
                                "escalated": True,
                                "overdue": False,
                                "primary_paths": ["wiki/sources/src-1.md"],
                            }
                        ],
                        "execution_proposals": [
                            {
                                "action_id": "safe-apply-action",
                                "target_paths": ["wiki/sources/src-1.md"],
                                "risk": "low",
                                "summary": "Patch the source-to-concept link.",
                            }
                        ],
                    },
                    "concept_quality": {
                        "counts": {
                            "weak": 1,
                            "merge_candidates": 1,
                            "conflict_signals": 1,
                            "gap_signals": 1,
                            "soft_hardness": 1,
                            "medium_or_hard": 2,
                        },
                        "weak_concepts": [
                            {"path": "wiki/concepts/alpha.md", "issues": ["thin-evidence"], "source_count": 1}
                        ],
                        "rewrite_candidates": [
                            {
                                "path": "wiki/concepts/alpha.md",
                                "priority": "high",
                                "rewrite_strategy": "expand",
                            }
                        ],
                        "conflict_signals": [
                            {
                                "slug": "alpha",
                                "label": "contradiction",
                                "source_pages": ["wiki/sources/src-1.md"],
                            }
                        ],
                        "merge_candidates": [
                            {
                                "left_slug": "alpha",
                                "right_slug": "beta",
                                "shared_sources": ["wiki/sources/src-1.md"],
                                "shared_tokens": ["latency"],
                            }
                        ],
                    },
                    "concept_rewrite": {
                        "counts": {"active": 2, "pending_review": 1},
                        "proposals": [
                            {
                                "slug": "alpha",
                                "target_path": "wiki/concepts/alpha.md",
                                "status": "applied",
                                "previous_markdown": "old",
                                "quality_score": 87,
                                "verification_status": "failed",
                                "rewrite_strategy": "clarify",
                            },
                            {
                                "slug": "beta",
                                "target_path": "wiki/concepts/beta.md",
                                "status": "accepted",
                                "apply_ready": True,
                                "quality_score": 93,
                                "verification_status": "passed",
                                "rewrite_strategy": "merge",
                            },
                        ],
                    },
                    "counter_evidence_scan": {
                        "pages": [
                            {
                                "page_path": "wiki/judgments/judgment-a.md",
                                "candidate_count": 2,
                                "source_ids": ["src-1"],
                                "shared_terms": ["cost"],
                            }
                        ]
                    },
                    "judgment_review_actions": [
                        {
                            "title": "Re-review alpha judgment",
                            "priority": "high",
                            "reason_codes": ["drift"],
                            "review_command": "review-page wiki/judgments/judgment-a.md --status confirmed",
                        }
                    ],
                    "link_suggestions": [
                        {
                            "source_page": "wiki/sources/src-1.md",
                            "concept_page": "wiki/concepts/alpha.md",
                            "shared_terms": ["latency"],
                            "score": 9,
                        }
                    ],
                    "component_count": 2,
                },
                "transition": {
                    "changed": True,
                    "previous_digest": "old",
                    "current_digest": "new",
                    "added_source_ids": ["src-1"],
                    "added_concept_slugs": ["alpha"],
                    "added_edges": 3,
                    "removed_edges": 1,
                },
            },
            active_protocol,
            {"count": 1, "pages": [{"kind": "decision", "path": "wiki/decisions/decision-a.md", "action": "promote", "occurrences": 3}]},
            ["src-1"],
            ["placeholder-concept"],
            [{"path": "wiki/decisions/decision-a.md", "status": "proposed"}],
            [{"path": "wiki/judgments/judgment-a.md", "status": "tracking"}],
            [{"path": "wiki/judgments/judgment-b.md", "status": "tracking"}],
            [{"path": "wiki/judgments/judgment-a.md", "status": "tracking"}],
            "output/lint/semantic.md",
            "2025-01-01T00:00:00+00:00",
        )
        empty_backlog = render_repair_backlog(
            {"changed_pages": 0, "machine_memory_changed": False},
            {"counts": {"errors": 0, "warnings": 0}, "findings": [], "path": "output/lint/lint-empty.md"},
            {"drift": {}, "health": {}, "transition": {}},
            active_protocol,
            {"count": 0, "pages": []},
            [],
            [],
            [],
            [],
            [],
            [],
            "",
            "2025-01-01T00:00:00+00:00",
        )

        self.assertIn("### 协议 Nightly 焦点", rich_backlog)
        self.assertIn("### Rewrite Proposals", rich_backlog)
        self.assertIn("### 执行批次", rich_backlog)
        self.assertIn("### Safe Apply Actions", rich_backlog)
        self.assertIn("### 图谱修复候选", rich_backlog)
        self.assertIn("### 结构漂移", rich_backlog)
        self.assertIn("Soft 概念页", rich_backlog)
        self.assertIn("Medium+/Hard 概念页", rich_backlog)
        self.assertIn("- 当前没有 machine-memory 动作。", empty_backlog)
        self.assertIn("当前没有图谱专项修复项", empty_backlog)
        self.assertIn("当前没有紧急修复项", empty_backlog)

    def test_lint_layout_phase_reports_missing_sources_schema_and_rules(self) -> None:
        bad_source = self.root / "wiki" / "sources" / "bad.md"
        self._write_markdown(
            bad_source,
            {"kind": "source", "generated_by": "aiwiki", "source_files": ["raw/missing.md"]},
            "Pending LLM summary.",
        )
        context = _LintContext(root=self.root, manifest={"entries": [{"id": "missing"}, {"id": "bad"}]})

        _lint_layout_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(any("Missing source page for manifest entry `missing`" in message for message in messages))
        self.assertTrue(any("Frontmatter is missing required key `id`" in message for message in messages))
        self.assertTrue(any("Referenced source file does not exist" in message for message in messages))
        self.assertTrue(any("placeholder summary" in message for message in messages))
        self.assertTrue(any("Missing master wiki index page." in message for message in messages))
        self.assertTrue(any("Missing sources index page." in message for message in messages))

    def test_lint_runtime_phase_reports_invalid_and_missing_runtime_artifacts(self) -> None:
        context = _LintContext(
            root=self.root,
            manifest={"entries": [{"id": "entry-1"}]},
            protocol_state=load_protocol_state(self.root),
        )
        invalid_documents = {
            self.root / ".aiwiki" / "state" / "machine-memory.json": "{",
            self.root / ".aiwiki" / "cache" / "machine-memory-graph.json": "{",
            self.root / ".aiwiki" / "state" / "planner-state.json": "{}",
            self.root / ".aiwiki" / "state" / "query-route-telemetry.json": "{}",
            self.root / "output" / "control" / "shell-summary.json": "[]",
            self.root / ".aiwiki" / "state" / "machine-memory-actions.json": "{}",
            self.root / ".aiwiki" / "state" / "concept-rewrite-proposals.json": "{}",
        }
        for path, payload in invalid_documents.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        policy_history = self.root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"
        policy_history.parent.mkdir(parents=True, exist_ok=True)
        policy_history.write_text("not-json\n", encoding="utf-8")

        _lint_runtime_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(any("Machine memory state is not valid JSON." in message for message in messages))
        self.assertTrue(any("Missing machine memory graph HTML view." in message for message in messages))
        self.assertTrue(any("Planner state is not valid JSON." in message for message in messages))
        self.assertTrue(any("Query route telemetry is not valid JSON." in message for message in messages))
        self.assertTrue(any("Shell summary is not valid JSON." in message for message in messages))
        self.assertTrue(any("Machine memory graph export is not valid JSON." in message for message in messages))
        self.assertTrue(any("Machine memory action state is not valid JSON." in message for message in messages))
        self.assertTrue(any("Execution policy log line `1` is not valid JSON." in message for message in messages))
        self.assertTrue(any("Concept rewrite proposal state is not valid JSON." in message for message in messages))

    def test_lint_runtime_phase_reports_missing_execution_artifacts_from_valid_state(self) -> None:
        context = _LintContext(
            root=self.root,
            manifest={"entries": [{"id": "entry-1"}]},
            protocol_state=load_protocol_state(self.root),
        )
        machine_memory = {
            "source_nodes": [],
            "concept_nodes": [],
            "health": {
                "repair_plan": {
                    "execution_proposals": [
                        {
                            "action_id": "act-1",
                            "proposal_path": "wiki/execution-proposals/act-1.md",
                            "bundle_path": "output/control/execution-bundles/act-1.json",
                        }
                    ]
                }
            },
        }
        (self.root / ".aiwiki" / "state").mkdir(parents=True, exist_ok=True)
        (self.root / ".aiwiki" / "state" / "machine-memory.json").write_text(
            json.dumps(machine_memory),
            encoding="utf-8",
        )
        (self.root / ".aiwiki" / "cache").mkdir(parents=True, exist_ok=True)
        (self.root / ".aiwiki" / "cache" / "machine-memory-graph.json").write_text(
            json.dumps({"nodes": []}),
            encoding="utf-8",
        )
        (self.root / ".aiwiki" / "state" / "machine-memory-actions.json").write_text(
            json.dumps({"actions": [{"id": "act-1", "last_receipt_path": "output/control/execution-receipts/act-1.json"}]}),
            encoding="utf-8",
        )
        (self.root / ".aiwiki" / "state" / "concept-rewrite-proposals.json").write_text(
            json.dumps(
                {
                    "proposals": [
                        {
                            "slug": "alpha",
                            "proposal_path": "wiki/rewrite-proposals/alpha.md",
                            "target_path": "wiki/concepts/alpha.md",
                            "apply_ready": True,
                            "candidate_markdown": "",
                            "status": "applied",
                            "previous_markdown": "",
                            "verification_status": "",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        _lint_runtime_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(any("Machine memory state is missing a stable digest." in message for message in messages))
        self.assertTrue(any("Missing execution proposal page for action `act-1`." in message for message in messages))
        self.assertTrue(any("Missing execution bundle for action `act-1`." in message for message in messages))
        self.assertTrue(any("Referenced execution receipt does not exist for action `act-1`." in message for message in messages))
        self.assertTrue(any("Execution policy decision log has not been initialized." in message for message in messages))
        self.assertTrue(any("Missing rewrite proposal page for concept `alpha`." in message for message in messages))
        self.assertTrue(any("Rewrite proposal target concept page is missing: `alpha`." in message for message in messages))
        self.assertTrue(any("Rewrite proposal is marked apply_ready but has no candidate markdown." in message for message in messages))
        self.assertTrue(any("Applied rewrite proposal has no rollback snapshot." in message for message in messages))

    def test_lint_governance_and_curated_phases_flag_state_shape_issues(self) -> None:
        concept_path = self.root / "wiki" / "concepts" / "alpha.md"
        self._write_markdown(
            concept_path,
            {
                "kind": "derived",
                "title": "Alpha Concept",
                "source_pages": ["wiki/sources/missing.md"],
            },
            "# Alpha Concept\n\nFallback concept summary.\n",
        )
        decision_path = self.root / "wiki" / "decisions" / "decision-a.md"
        self._write_markdown(
            decision_path,
            {
                "title": "Decision A",
                "kind": "derived",
                "citations": ["wiki/sources/missing.md"],
            },
            "# Decision A\n\nNo explicit source references here.\n",
        )
        judgment_path = self.root / "wiki" / "judgments" / "judgment-a.md"
        self._write_markdown(
            judgment_path,
            {
                "title": "Judgment A",
                "kind": "judgment",
                "citations": ["wiki/sources/missing.md"],
            },
            "# Judgment A\n\nNo explicit source references here.\n",
        )
        knowledge_state = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        knowledge_state.parent.mkdir(parents=True, exist_ok=True)
        knowledge_state.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "kind": "decision",
                            "lifecycle_state": "bad-state",
                            "path": "wiki/missing.md",
                            "source_ids": "oops",
                            "active_corpus_ids": "oops",
                            "invalidation_signals": "oops",
                            "judgment_lifecycle_state": "bad-state",
                            "judgment_lifecycle_reason_codes": "oops",
                        },
                        {
                            "page_id": "concept-alpha",
                            "kind": "concept",
                            "lifecycle_state": "active",
                            "path": "wiki/concepts/alpha.md",
                            "source_ids": [],
                            "active_corpus_ids": [],
                            "invalidation_signals": [],
                            "issues": "oops",
                            "review_signal_codes": "oops",
                            "source_pages": "oops",
                            "quality_state": "",
                            "override_reason_codes": "oops",
                            "override_state": "bad-state",
                            "override_active": "oops",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        override_state = self.root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"
        override_state.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "slug": "",
                            "path": "wiki/missing.md",
                            "kind": "decision",
                            "lifecycle_state": "bad-state",
                            "active": "oops",
                        },
                        {
                            "slug": "dup-a",
                            "path": "wiki/concepts/alpha.md",
                            "kind": "concept",
                            "lifecycle_state": "active",
                            "active": True,
                        },
                        {
                            "slug": "dup-b",
                            "path": "wiki/concepts/alpha.md",
                            "kind": "concept",
                            "lifecycle_state": "active",
                            "active": True,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        context = _LintContext(
            root=self.root,
            manifest={"entries": [{"id": "entry-1"}]},
            decision_pages=[{"path": "wiki/decisions/decision-a.md", "status": "proposed"}],
            judgment_pages=[{"path": "wiki/judgments/judgment-a.md", "status": "tracking"}],
        )

        _lint_governance_phase(context)
        _lint_curated_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(any("Knowledge lifecycle entry is missing `page_id`." in message for message in messages))
        self.assertTrue(any("unsupported kind `decision`" in message for message in messages if "override" in message.lower()))
        self.assertTrue(any("Concept lifecycle entry `issues` is not a list." in message for message in messages))
        self.assertTrue(any("Multiple active knowledge lifecycle overrides reference `wiki/concepts/alpha.md`." in message for message in messages))
        self.assertTrue(any("Concept page kind is missing or incorrect." in message for message in messages))
        self.assertTrue(any("Concept page is missing section `## Conflict Signals`." in message for message in messages))
        self.assertTrue(any("Concept page is missing explicit `hardness` metadata." in message for message in messages))
        self.assertTrue(any("Decision page kind is missing or incorrect." in message for message in messages))
        self.assertTrue(any("Judgment page references missing citation path" in message for message in messages))
        self.assertTrue(any("Judgment page is missing explicit `protocol` metadata." in message for message in messages))
        self.assertTrue(any("Judgment page is missing explicit confidence metadata." in message for message in messages))

    def test_lint_governance_phase_accepts_active_review_lifecycle_override(self) -> None:
        concept_path = self.root / "wiki" / "concepts" / "alpha.md"
        self._write_markdown(
            concept_path,
            {
                "kind": "concept",
                "title": "Alpha Concept",
                "source_pages": [],
                "hardness": "soft",
            },
            "# Alpha Concept\n\nStable concept.\n\n## Conflict Signals\n- Boundary noted.\n\n## Evidence Gaps\n- None.\n",
        )
        override_state = self.root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"
        override_state.parent.mkdir(parents=True, exist_ok=True)
        override_state.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "slug": "alpha",
                            "path": "wiki/concepts/alpha.md",
                            "kind": "concept",
                            "lifecycle_state": "deferred",
                            "operation": "review",
                            "active": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        context = _LintContext(root=self.root, manifest={"entries": []})

        _lint_governance_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertFalse(
            any("Active concept lifecycle override for `alpha`" in message for message in messages)
        )

    def test_lint_governance_phase_warns_for_active_non_review_lifecycle_override(self) -> None:
        concept_path = self.root / "wiki" / "concepts" / "alpha.md"
        self._write_markdown(
            concept_path,
            {
                "kind": "concept",
                "title": "Alpha Concept",
                "source_pages": [],
                "hardness": "soft",
            },
            "# Alpha Concept\n\nStable concept.\n\n## Conflict Signals\n- Boundary noted.\n\n## Evidence Gaps\n- None.\n",
        )
        override_state = self.root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"
        override_state.parent.mkdir(parents=True, exist_ok=True)
        override_state.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "slug": "alpha",
                            "path": "wiki/concepts/alpha.md",
                            "kind": "concept",
                            "lifecycle_state": "deferred",
                            "operation": "manual-link-state",
                            "active": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        context = _LintContext(root=self.root, manifest={"entries": []})

        _lint_governance_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(
            any(
                "Active concept lifecycle override for `alpha` is `deferred`; current workflow expects `retired`."
                in message
                for message in messages
            )
        )

    def test_lint_governance_phase_flags_undergrounded_hard_concepts(self) -> None:
        source_path = self.root / "wiki" / "sources" / "alpha.md"
        self._write_markdown(
            source_path,
            {"kind": "source", "title": "Alpha Source", "source_files": ["raw/inbox/alpha.md"], "source_sha256": "sha"},
            "# Alpha Source\n\n## Summary\n- Stable source.\n",
        )
        concept_path = self.root / "wiki" / "concepts" / "alpha.md"
        self._write_markdown(
            concept_path,
            {
                "id": "concept-alpha",
                "kind": "concept",
                "title": "Alpha",
                "source_pages": ["wiki/sources/alpha.md"],
                "source_signature": "sig",
                "confidence": "low",
                "hardness": "hard",
            },
            "\n".join(
                [
                    "# Alpha",
                    "",
                    "## Summary",
                    "- Grounded synthesis.",
                    "",
                    "## Conflict Signals",
                    "- 当前没有显式冲突信号。",
                    "",
                    "## Evidence Gaps",
                    "- 当前没有显式证据缺口。",
                ]
            ),
        )
        context = _LintContext(root=self.root, manifest={"entries": [{"id": "alpha"}]})

        _lint_governance_phase(context)

        messages = [finding.message for finding in context.findings]
        self.assertTrue(any("`hardness >= medium` should keep `confidence` at least `medium`" in message for message in messages))
        self.assertTrue(any("`hardness >= medium` should be grounded by at least 3 source pages" in message for message in messages))
        self.assertTrue(any("`hardness >= medium` should record at least one explicit conflict or boundary signal" in message for message in messages))

    def test_lint_report_rotation_keeps_latest(self) -> None:
        """Lint reports should be rotated to keep only the most recent N."""
        lint_dir = self.root / "output" / "lint"
        lint_dir.mkdir(parents=True, exist_ok=True)
        # Create more than _LINT_REPORT_KEEP reports
        total = _LINT_REPORT_KEEP + 5
        names = [f"lint-20260415-{100000 + i}.md" for i in range(total)]
        for name in names:
            (lint_dir / name).write_text("# report\n")
        self.assertEqual(len(list(lint_dir.glob("lint-*.md"))), total)
        _rotate_lint_reports(lint_dir)
        remaining = sorted(lint_dir.glob("lint-*.md"))
        self.assertEqual(len(remaining), _LINT_REPORT_KEEP)
        # The most recent files should be kept
        expected_kept = sorted(names[-_LINT_REPORT_KEEP:])
        self.assertEqual([r.name for r in remaining], expected_kept)


if __name__ == "__main__":
    unittest.main()
