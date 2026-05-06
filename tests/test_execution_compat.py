"""Canary tests for the EP-018A execution-owner lazy compat seam.

Guards (post independent oracle review):

1. Every execution name listed in ``aiwiki.app_compile._LAZY_OWNERS`` is
   resolvable via ``getattr`` and is a real callable.
2. The count and shape match the plan: 28 public execution functions +
   8 private helpers = 36 total.
3. Hot patch targets used by ``tests/test_app.py`` (``utc_now``,
   ``entry_concept_terms``, ``build_machine_memory``,
   ``build_ranking_source_record``, ``build_ranking_concept_record``) are
   NOT lazy — they remain directly in ``app_compile.__dict__`` so
   ``unittest.mock.patch`` resolves them without touching ``__getattr__``.
4. The ``__getattr__`` self-reference branch raises ``AttributeError`` for
   a name registered in ``_LAZY_OWNERS`` but absent from ``globals``.
5. **Real seam exercise** (the critical test): by temporarily deleting a
   name from ``app_compile.__dict__`` and pointing ``_LAZY_OWNERS`` at a
   stub module injected into ``sys.modules``, verify that:
   - ``getattr(app_compile, name)`` returns the stub's value,
   - ``from aiwiki.app_compile import <name>`` still works,
   - ``unittest.mock.patch("aiwiki.app_compile.<name>")`` works,
   - the resolved value is cached back into ``app_compile.__dict__``.
   This is the scenario EP-018B will create group-by-group, so the seam
   MUST support it today.
6. ``aiwiki.app_compile`` does NOT define a module-level ``__all__``. Adding
   one would silently redefine the ``from aiwiki.app_compile import *``
   surface and is out of scope for EP-018A.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiwiki import app_compile

EXPECTED_LAZY_NAMES = {
    # Ask / file-back
    "ask_question",
    "file_back",
    # Concept rewrite pipeline (4 public + 5 private helpers)
    "review_concept_rewrite",
    "apply_concept_rewrite",
    "verify_concept_rewrite",
    "revert_concept_rewrite",
    "_load_concept_rewrite_proposals",
    "_find_concept_rewrite_proposal",
    "_save_concept_rewrite_proposals",
    "_evaluate_concept_rewrite_verification",
    "_persist_concept_rewrite_verification",
    # Knowledge lifecycle
    "refresh_knowledge_lifecycle_runtime",
    "retire_concept",
    "reactivate_concept",
    # Concept review-ack (Round 7 / P4-19b)
    "review_concept",
    "review_concepts_batch",
    # Machine-memory action (5 public + 1 private helper)
    "resolve_machine_memory_action_query",
    "review_machine_memory_action",
    "review_machine_memory_actions_batch",
    "apply_machine_memory_action",
    "revert_machine_memory_action",
    "_save_machine_memory_action_records",
    # Archive
    "apply_material_archive",
    "revert_material_archive",
    # Review page & batch (4 public + 2 private helpers)
    "review_page",
    "review_pages_batch",
    "apply_machine_memory_actions_batch",
    "revert_machine_memory_action_batch",
    "_build_batch_id",
    "_load_latest_action_apply_batch_receipt",
    # Runtime surfaces
    "nightly_health",
    "shell_status",
    # L3 prompt/policy proposals
    "create_l3_proposal",
    "list_l3_proposals",
    "preview_l3_proposal_generation",
    "apply_l3_proposal",
    "reject_l3_proposal",
    "revert_l3_proposal",
    "load_l3_proposal_state",
    "save_l3_proposal_state",
}

PATCH_SEAM_NAMES = {
    "utc_now",
    "entry_concept_terms",
    "build_machine_memory",
    "build_ranking_source_record",
    "build_ranking_concept_record",
}


class ExecutionCompatSeamTests(unittest.TestCase):
    def test_lazy_owners_matches_expected_set(self) -> None:
        self.assertEqual(set(app_compile._LAZY_OWNERS.keys()), EXPECTED_LAZY_NAMES)

    def test_lazy_owners_count_matches_plan(self) -> None:
        # Plan promises 32 public + 8 private helpers = 40
        # (Round 8 adds review_machine_memory_actions_batch).
        keys = list(app_compile._LAZY_OWNERS.keys())
        public = [k for k in keys if not k.startswith("_")]
        private = [k for k in keys if k.startswith("_")]
        self.assertEqual(len(keys), 40)
        self.assertEqual(len(public), 32)
        self.assertEqual(len(private), 8)

    def test_all_lazy_owners_self_reference_in_ep_018a(self) -> None:
        # EP-018B flips these owner paths group-by-group to point at concrete
        # ``aiwiki.execution.<submodule>`` modules. Any name listed here has
        # completed migration and is exempt from the self-reference invariant.
        migrated = {
            # B1 — runtime surfaces
            "nightly_health": "aiwiki.execution.runtime_surfaces",
            "shell_status": "aiwiki.execution.runtime_surfaces",
            # B2 — ask / file-back
            "ask_question": "aiwiki.execution.ask",
            "file_back": "aiwiki.execution.ask",
            # B3 — lifecycle
            "refresh_knowledge_lifecycle_runtime": "aiwiki.execution.lifecycle",
            "retire_concept": "aiwiki.execution.lifecycle",
            "reactivate_concept": "aiwiki.execution.lifecycle",
            # Round 7 / P4-19b — review-concept manual ack
            "review_concept": "aiwiki.execution.lifecycle",
            "review_concepts_batch": "aiwiki.execution.lifecycle",
            # B4 — material archive
            "apply_material_archive": "aiwiki.execution.archive",
            "revert_material_archive": "aiwiki.execution.archive",
            # B5 — concept rewrite
            "review_concept_rewrite": "aiwiki.execution.concept_rewrite",
            "apply_concept_rewrite": "aiwiki.execution.concept_rewrite",
            "verify_concept_rewrite": "aiwiki.execution.concept_rewrite",
            "revert_concept_rewrite": "aiwiki.execution.concept_rewrite",
            "_load_concept_rewrite_proposals": "aiwiki.execution.concept_rewrite",
            "_find_concept_rewrite_proposal": "aiwiki.execution.concept_rewrite",
            "_save_concept_rewrite_proposals": "aiwiki.execution.concept_rewrite",
            "_evaluate_concept_rewrite_verification": "aiwiki.execution.concept_rewrite",
            "_persist_concept_rewrite_verification": "aiwiki.execution.concept_rewrite",
            # B6 — machine-memory action
            "resolve_machine_memory_action_query": "aiwiki.execution.machine_memory_actions",
            "review_machine_memory_action": "aiwiki.execution.machine_memory_actions",
            "review_machine_memory_actions_batch": "aiwiki.execution.machine_memory_actions",
            "apply_machine_memory_action": "aiwiki.execution.machine_memory_actions",
            "revert_machine_memory_action": "aiwiki.execution.machine_memory_actions",
            "_save_machine_memory_action_records": "aiwiki.execution.machine_memory_actions",
            # B7 — review page & machine-memory batch
            "review_page": "aiwiki.execution.review",
            "review_pages_batch": "aiwiki.execution.machine_memory_batch",
            "apply_machine_memory_actions_batch": "aiwiki.execution.machine_memory_batch",
            "revert_machine_memory_action_batch": "aiwiki.execution.machine_memory_batch",
            "_build_batch_id": "aiwiki.execution.machine_memory_batch",
            "_load_latest_action_apply_batch_receipt": "aiwiki.execution.machine_memory_batch",
            # M3.6 — L3 prompt/policy proposals
            "create_l3_proposal": "aiwiki.execution.l3_proposals",
            "list_l3_proposals": "aiwiki.execution.l3_proposals",
            "preview_l3_proposal_generation": "aiwiki.execution.l3_proposals",
            "apply_l3_proposal": "aiwiki.execution.l3_proposals",
            "reject_l3_proposal": "aiwiki.execution.l3_proposals",
            "revert_l3_proposal": "aiwiki.execution.l3_proposals",
            "load_l3_proposal_state": "aiwiki.execution.l3_proposals",
            "save_l3_proposal_state": "aiwiki.execution.l3_proposals",
        }
        for name, owner in app_compile._LAZY_OWNERS.items():
            expected = migrated.get(name, "aiwiki.app_compile")
            self.assertEqual(
                owner,
                expected,
                msg=f"{name!r} owner expected {expected!r}; got {owner!r}",
            )

    def test_module_does_not_define_dunder_all(self) -> None:
        # EP-018A must not redefine the star-import surface.
        self.assertFalse(
            hasattr(app_compile, "__all__"),
            msg=(
                "aiwiki.app_compile grew a module-level __all__. This would "
                "silently change `from aiwiki.app_compile import *` behavior. "
                "Remove it or justify in the plan."
            ),
        )

    def test_every_lazy_name_resolves_to_callable(self) -> None:
        for name in EXPECTED_LAZY_NAMES:
            with self.subTest(name=name):
                value = getattr(app_compile, name)
                self.assertTrue(
                    callable(value),
                    msg=f"{name!r} resolved to non-callable {value!r}",
                )

    def test_patch_seam_names_are_direct_bound_not_lazy(self) -> None:
        for name in PATCH_SEAM_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(name, app_compile._LAZY_OWNERS)
                # Must be a real entry in __dict__, not just a lazy-resolvable
                # attribute.
                self.assertIn(
                    name,
                    app_compile.__dict__,
                    msg=f"{name!r} must live directly in app_compile.__dict__",
                )

    def test_patch_on_utc_now_still_works(self) -> None:
        with patch("aiwiki.app_compile.utc_now", return_value="patched") as mocked:
            self.assertEqual(app_compile.utc_now(), "patched")
        self.assertTrue(mocked.called)

    def test_unknown_attribute_raises(self) -> None:
        with self.assertRaises(AttributeError):
            _ = app_compile.this_name_should_never_exist_xyz

    def test_self_reference_missing_binding_raises(self) -> None:
        # Register a fake name with self-reference, but don't define it in
        # globals. The seam must raise AttributeError, not return None.
        fake = "_ep018a_fake_self_ref_probe"
        app_compile._LAZY_OWNERS[fake] = "aiwiki.app_compile"
        try:
            with self.assertRaises(AttributeError) as cm:
                getattr(app_compile, fake)
            self.assertIn("no concrete binding", str(cm.exception))
        finally:
            app_compile._LAZY_OWNERS.pop(fake, None)


class ExecutionCompatSeamMigratedGroupTests(unittest.TestCase):
    """Smoke tests for EP-018B groups that have completed migration.

    Each assertion proves the real migrated module (not a stub) is what
    callers see via ``aiwiki.app_compile.<name>``. This is the regression
    canary the migration-simulation tests cannot provide on their own:
    they only exercise the seam's forwarding mechanics against a synthetic
    stub, not the actual post-migration wiring.
    """

    def test_b1_runtime_surfaces_resolve_to_execution_module(self) -> None:
        import importlib

        runtime_surfaces = importlib.import_module(
            "aiwiki.execution.runtime_surfaces"
        )
        # Drop any cached binding so the seam forwards freshly.
        for name in ("nightly_health", "shell_status"):
            app_compile.__dict__.pop(name, None)
        try:
            self.assertIs(app_compile.nightly_health, runtime_surfaces.nightly_health)
            self.assertIs(app_compile.shell_status, runtime_surfaces.shell_status)
        finally:
            # Re-prime the cache; no need to clean up since the resolution
            # above already cached the real migrated targets.
            pass

    def test_b1_from_import_works(self) -> None:
        # Pop any cached bindings so the seam forwards freshly during this
        # test; otherwise a prior test that already resolved these names
        # could make this one pass via cache alone, weakening the proof.
        for name in ("nightly_health", "shell_status"):
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import nightly_health, shell_status",
            {"__builtins__": __builtins__},
            local_ns,
        )
        self.assertIn("nightly_health", local_ns)
        self.assertIn("shell_status", local_ns)
        self.assertTrue(callable(local_ns["nightly_health"]))
        self.assertTrue(callable(local_ns["shell_status"]))

    def test_b2_ask_module_resolves_to_execution_module(self) -> None:
        import importlib

        ask_mod = importlib.import_module("aiwiki.execution.ask")
        for name in ("ask_question", "file_back"):
            app_compile.__dict__.pop(name, None)
        self.assertIs(app_compile.ask_question, ask_mod.ask_question)
        self.assertIs(app_compile.file_back, ask_mod.file_back)

    def test_b2_from_import_works(self) -> None:
        for name in ("ask_question", "file_back"):
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import ask_question, file_back",
            {"__builtins__": __builtins__},
            local_ns,
        )
        self.assertIn("ask_question", local_ns)
        self.assertIn("file_back", local_ns)
        self.assertTrue(callable(local_ns["ask_question"]))
        self.assertTrue(callable(local_ns["file_back"]))

    def test_b2_ask_question_uses_patched_utc_now_and_rank_concepts(self) -> None:
        # Mirror the file_back test: verify that patches on
        # ``aiwiki.app_compile.utc_now`` AND ``aiwiki.app_compile.rank_concepts``
        # are picked up by ``ask_question`` after the B2 migration. This
        # guards against regressions where either name gets bound at module
        # top of ``execution/ask.py`` and defeats the hot-patch seam.
        import importlib
        import tempfile

        ask_mod = importlib.import_module("aiwiki.execution.ask")
        utc_calls: list[str] = []
        rank_calls: list[tuple] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(utc_calls)}"
            utc_calls.append(stamp)
            return stamp

        def _fake_rank(*args, **kwargs):
            rank_calls.append((args, kwargs))
            # Return a stub with the shape ``ask_question`` unpacks later.
            return [
                {
                    "slug": "stub-concept",
                    "source_pages": [],
                }
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output" / "reports").mkdir(parents=True, exist_ok=True)
            # Stub every surface ``ask_question`` calls before and around
            # the ``utc_now`` + ``rank_concepts`` sites. We only need to
            # reach those two lazy calls; downstream work can return
            # whatever the first checkpoint needs. Use ExitStack to avoid
            # Python's 20-level nested-block limit.
            import contextlib

            mm_query = {
                "ranked_concept_slugs": [],
                "ranked_source_ids": [],
                "matched_terms": [],
                "bridge_concept_slugs": [],
                "query_routes": [],
            }
            stubs = {
                "ensure_layout": None,
                "sync_manifest_with_raw": {"entries": []},
                "wiki_requires_compile": False,
                "load_protocol_state": {"active_protocol": "general"},
                "resolve_protocol": "general",
                "active_archived_material_ids": set(),
                "load_material_state": {},
                "load_material_routing_state": {},
                "load_archive_candidates_state": {},
                "load_machine_memory": {},
                "build_machine_memory_query": mm_query,
                "rank_sources": [],
                "slugify": "q",
                "next_available_stem": "q-1",
                "render_report": "body",
                "relative_path": "output/reports/q-1.md",
                "active_corpus_bridge_evidence_ids": [],
                "upsert_active_corpus": {"corpus_id": "corpus-1"},
                "append_runtime_history": None,
                "record_query_route_telemetry": {"last_entry": {}},
                "question_signature": "hash",
                "refresh_material_state": None,
                "refresh_knowledge_lifecycle_state": None,
                "load_active_corpora_state": {},
                "build_shell_summary": {},
                "write_shell_summary": None,
                "append_wiki_log": None,
                "protocol_paths": [],
                "compile_wiki": None,
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(ask_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                stack.enter_context(
                    patch(
                        "aiwiki.app_compile.rank_concepts",
                        side_effect=_fake_rank,
                    )
                )
                ask_mod.ask_question(
                    root, "what", "report", protocol="general"
                )

        # If either name ever regresses to a module-top binding in ask.py,
        # one of these assertions would fail because the patched sentinel
        # would not fire.
        self.assertTrue(
            utc_calls,
            msg="ask_question did not route utc_now through aiwiki.app_compile",
        )
        self.assertTrue(
            rank_calls,
            msg="ask_question did not route rank_concepts through "
            "aiwiki.app_compile",
        )

    def test_b2_file_back_uses_patched_utc_now(self) -> None:
        # ``file_back`` resolves ``utc_now`` lazily via
        # ``aiwiki.app_compile`` so that hot-patch sites like
        # ``patch("aiwiki.app_compile.utc_now", ...)`` in tests/test_app.py
        # still take effect after the B2 migration. Stub the surrounding
        # heavy work and assert the patched sentinel fires.
        import importlib
        import tempfile

        ask_mod = importlib.import_module("aiwiki.execution.ask")
        observed: list[str] = []

        def _fake_utc_now() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "output" / "reports" / "stub.md"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("body\n", encoding="utf-8")
            # ``file_back`` writes into ``wiki/derived`` after the
            # ``ensure_layout`` stub skips directory creation.
            (root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)

            with patch.object(ask_mod, "ensure_layout"), patch.object(
                ask_mod, "resolve_protocol", return_value="general"
            ), patch.object(
                ask_mod, "parse_frontmatter", return_value={}
            ), patch.object(
                ask_mod, "extract_provenance_paths", return_value=[]
            ), patch.object(
                ask_mod, "build_citation_snapshots", return_value=[]
            ), patch.object(
                ask_mod, "relative_path", return_value="wiki/derived/x.md"
            ), patch.object(
                ask_mod, "slugify", return_value="stub"
            ), patch.object(
                ask_mod, "next_available_stem", return_value="derived-1"
            ), patch.object(
                ask_mod, "render_frontmatter", return_value="---\nid: x\n---"
            ), patch.object(
                ask_mod, "strip_frontmatter", return_value="body"
            ), patch.object(
                ask_mod, "curated_page_template", return_value=["# title"]
            ), patch.object(
                ask_mod, "append_wiki_log"
            ), patch.object(
                ask_mod, "compile_wiki", return_value={}
            ), patch(
                "aiwiki.app_compile.utc_now", side_effect=_fake_utc_now
            ):
                ask_mod.file_back(root, str(artifact), title="Stub", kind="derived")

        # If the lazy lookup ever regresses to a module-level
        # ``from ..app_compile import utc_now`` binding, the patch above
        # would NOT affect this call and ``observed`` would stay empty.
        self.assertTrue(
            observed,
            msg="file_back did not route utc_now through aiwiki.app_compile; "
            "the B2 lazy-lookup seam regressed.",
        )

    def test_b1_nightly_health_resolves_apply_action_lazily(self) -> None:
        # ``nightly_health`` calls ``app_compile.apply_machine_memory_action``
        # through the seam so future B6 owner flips do not require editing
        # this module. Verify by patching the attribute on ``app_compile``
        # and confirming ``nightly_health`` picks up the patched callable.
        # This also guards the ``except Exception: pass`` swallow block: if
        # the lazy resolution ever silently returned a broken value, this
        # test would fail because the patched sentinel would never fire.
        import importlib

        runtime_surfaces = importlib.import_module(
            "aiwiki.execution.runtime_surfaces"
        )
        observed: list[tuple[tuple, dict]] = []

        def _fake_apply(*args, **kwargs):
            observed.append((args, kwargs))
            return {"bundle_path": ""}

        # Arrange a minimal state so the auto-consume loop actually reaches
        # ``apply_machine_memory_action``. We stub the surrounding heavy
        # calls to keep this a focused seam test.
        with patch.object(runtime_surfaces, "ensure_layout"), patch.object(
            runtime_surfaces, "compile_wiki", return_value={"status": "ok"}
        ), patch.object(
            runtime_surfaces, "promote_recurring_outputs", return_value={"count": 0}
        ), patch.object(
            runtime_surfaces, "lint_wiki", return_value={}
        ), patch.object(
            runtime_surfaces,
            "load_machine_memory_action_state",
            return_value={
                "actions": [
                    {
                        "id": "act-1",
                        "status": "accepted",
                        "active": True,
                        "kind": next(
                            iter(runtime_surfaces.LOW_RISK_APPLYABLE_ACTION_KINDS)
                        ),
                    }
                ]
            },
        ), patch.object(
            runtime_surfaces,
            "write_nightly_health",
            return_value={"aging": {}, "repair_backlog": {"path": "x"}},
        ), patch.object(
            runtime_surfaces, "nightly_health_state_path", return_value=MagicMock()
        ), patch.object(
            runtime_surfaces, "relative_path", return_value="x"
        ), patch(
            "aiwiki.app_compile.apply_machine_memory_action",
            side_effect=_fake_apply,
        ):
            with tempfile.TemporaryDirectory() as tempdir:
                result = runtime_surfaces.nightly_health(Path(tempdir))

        # Two calls per accepted id: one dry-run, one real.
        self.assertEqual(len(observed), 2)
        self.assertEqual(len(result["auto_applied"]), 1)

    def test_nightly_auto_consume_per_item_failure_is_returned(self) -> None:
        from aiwiki.execution import runtime_surfaces

        with patch.object(runtime_surfaces, "ensure_layout"), patch.object(
            runtime_surfaces, "compile_wiki", return_value={"status": "ok"}
        ), patch.object(
            runtime_surfaces, "promote_recurring_outputs", return_value={"count": 0}
        ), patch.object(
            runtime_surfaces, "lint_wiki", return_value={}
        ), patch.object(
            runtime_surfaces,
            "load_machine_memory_action_state",
            return_value={
                "actions": [
                    {
                        "id": "act-fail",
                        "status": "accepted",
                        "active": True,
                        "kind": next(iter(runtime_surfaces.LOW_RISK_APPLYABLE_ACTION_KINDS)),
                    }
                ]
            },
        ), patch.object(
            runtime_surfaces,
            "write_nightly_health",
            return_value={"aging": {}, "repair_backlog": {"path": "x"}},
        ), patch.object(
            runtime_surfaces, "nightly_health_state_path", return_value=MagicMock()
        ), patch.object(
            runtime_surfaces, "relative_path", return_value="x"
        ), patch(
            "aiwiki.app_compile.apply_machine_memory_action",
            side_effect=RuntimeError("apply boom"),
        ):
            with tempfile.TemporaryDirectory() as tempdir:
                result = runtime_surfaces.nightly_health(Path(tempdir))

        self.assertEqual(result["auto_applied"], [])
        self.assertEqual(
            result["auto_failed"],
            [{"id": "act-fail", "reason": "apply boom", "error_type": "RuntimeError"}],
        )

    def test_nightly_auto_consume_outer_failure_writes_run_event(self) -> None:
        from aiwiki.execution import runtime_surfaces

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            with patch.object(runtime_surfaces, "compile_wiki", return_value={"status": "ok"}), patch.object(
                runtime_surfaces, "promote_recurring_outputs", return_value={"count": 0}
            ), patch.object(runtime_surfaces, "lint_wiki", return_value={}), patch.object(
                runtime_surfaces,
                "load_machine_memory_action_state",
                side_effect=RuntimeError("state unreadable"),
            ), patch.object(
                runtime_surfaces,
                "write_nightly_health",
                return_value={"aging": {}, "repair_backlog": {"path": "x"}},
            ), patch.object(
                runtime_surfaces, "relative_path", return_value=".aiwiki/state/nightly-health.json"
            ):
                result = runtime_surfaces.nightly_health(root)

            events = [
                json.loads(line)
                for line in (root / ".aiwiki/logs/runs.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertEqual(result["auto_failed"], [])
        self.assertEqual(events[-1]["event"], "nightly_auto_consume_outer_failure")
        self.assertEqual(events[-1]["reason"], "state unreadable")
        self.assertEqual(events[-1]["error_type"], "RuntimeError")

    def test_b3_lifecycle_module_resolves_to_execution_module(self) -> None:
        import importlib

        lifecycle_mod = importlib.import_module("aiwiki.execution.lifecycle")
        for name in (
            "refresh_knowledge_lifecycle_runtime",
            "retire_concept",
            "reactivate_concept",
        ):
            app_compile.__dict__.pop(name, None)
        self.assertIs(
            app_compile.refresh_knowledge_lifecycle_runtime,
            lifecycle_mod.refresh_knowledge_lifecycle_runtime,
        )
        self.assertIs(app_compile.retire_concept, lifecycle_mod.retire_concept)
        self.assertIs(app_compile.reactivate_concept, lifecycle_mod.reactivate_concept)

    def test_b3_from_import_works(self) -> None:
        for name in (
            "refresh_knowledge_lifecycle_runtime",
            "retire_concept",
            "reactivate_concept",
        ):
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import (\n"
            "    refresh_knowledge_lifecycle_runtime,\n"
            "    retire_concept,\n"
            "    reactivate_concept,\n"
            ")",
            {"__builtins__": __builtins__},
            local_ns,
        )
        self.assertIn("refresh_knowledge_lifecycle_runtime", local_ns)
        self.assertIn("retire_concept", local_ns)
        self.assertIn("reactivate_concept", local_ns)
        self.assertTrue(callable(local_ns["refresh_knowledge_lifecycle_runtime"]))
        self.assertTrue(callable(local_ns["retire_concept"]))
        self.assertTrue(callable(local_ns["reactivate_concept"]))

    def test_b3_refresh_knowledge_lifecycle_runtime_uses_patched_utc_now(self) -> None:
        # When ``generated_at`` is not supplied, the function lazy-resolves
        # ``utc_now`` via ``aiwiki.app_compile``. A ``patch`` on that seam
        # must intercept the call after the B3 migration.
        import importlib
        import tempfile

        lifecycle_mod = importlib.import_module("aiwiki.execution.lifecycle")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(
                lifecycle_mod,
                "sync_manifest_with_raw",
                return_value={"entries": []},
            ), patch.object(
                lifecycle_mod,
                "refresh_knowledge_lifecycle_state",
                return_value={"entries": []},
            ), patch.object(
                lifecycle_mod, "load_active_corpora_state", return_value={}
            ), patch.object(
                lifecycle_mod, "load_machine_memory", return_value={}
            ), patch(
                "aiwiki.app_compile.utc_now", side_effect=_fake_utc
            ):
                lifecycle_mod.refresh_knowledge_lifecycle_runtime(root)

        self.assertTrue(
            observed,
            msg="refresh_knowledge_lifecycle_runtime did not route utc_now "
            "through aiwiki.app_compile; B3 lazy-lookup seam regressed.",
        )

    def test_b3_retire_concept_uses_patched_utc_now(self) -> None:
        # ``retire_concept`` lazy-resolves ``utc_now`` for the timestamp it
        # stamps onto the override record. Stub the surrounding heavy work
        # so we reach that lazy call and assert the patched sentinel fires.
        import importlib
        import tempfile

        lifecycle_mod = importlib.import_module("aiwiki.execution.lifecycle")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # ``concept_page_path`` returns a real path; we create the file
            # so ``path.exists()`` is True.
            concept_file = root / "concept.md"
            concept_file.write_text("x", encoding="utf-8")

            with patch.object(lifecycle_mod, "ensure_layout"), patch.object(
                lifecycle_mod, "concept_page_path", return_value=concept_file
            ), patch.object(
                lifecycle_mod, "relative_path", return_value="wiki/concepts/x.md"
            ), patch.object(
                lifecycle_mod,
                "refresh_knowledge_lifecycle_runtime",
                return_value={"entries": []},
            ), patch.object(
                lifecycle_mod,
                "concept_lifecycle_entry",
                side_effect=[
                    {"page_id": "concept-x", "title": "X", "lifecycle_state": "active"},
                    {"lifecycle_state": "retired"},
                ],
            ), patch.object(
                lifecycle_mod,
                "ensure_knowledge_lifecycle_override_state",
                return_value={"entries": []},
            ), patch.object(
                lifecycle_mod, "save_knowledge_lifecycle_override_state"
            ), patch.object(
                lifecycle_mod, "append_runtime_history"
            ), patch.object(
                lifecycle_mod, "append_wiki_log"
            ), patch.object(
                lifecycle_mod,
                "knowledge_lifecycle_override_state_path",
                return_value=root / "override.json",
            ), patch.object(
                lifecycle_mod,
                "knowledge_lifecycle_state_path",
                return_value=root / "lifecycle.json",
            ), patch(
                "aiwiki.app_compile.utc_now", side_effect=_fake_utc
            ):
                lifecycle_mod.retire_concept(root, "x", note="probe")

        self.assertTrue(
            observed,
            msg="retire_concept did not route utc_now through "
            "aiwiki.app_compile; B3 lazy-lookup seam regressed.",
        )

    def test_b3_reactivate_concept_uses_patched_utc_now(self) -> None:
        # Same hot-patch seam check for ``reactivate_concept``.
        import importlib
        import tempfile

        lifecycle_mod = importlib.import_module("aiwiki.execution.lifecycle")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            concept_file = root / "concept.md"
            concept_file.write_text("x", encoding="utf-8")
            # ``reactivate_concept`` requires an active retired override
            # entry matching the concept path, so seed one.
            override_state = {
                "entries": [
                    {
                        "active": True,
                        "kind": "concept",
                        "path": "wiki/concepts/x.md",
                        "lifecycle_state": "retired",
                        "page_id": "concept-x",
                    }
                ]
            }

            with patch.object(lifecycle_mod, "ensure_layout"), patch.object(
                lifecycle_mod, "concept_page_path", return_value=concept_file
            ), patch.object(
                lifecycle_mod, "relative_path", return_value="wiki/concepts/x.md"
            ), patch.object(
                lifecycle_mod,
                "ensure_knowledge_lifecycle_override_state",
                return_value=override_state,
            ), patch.object(
                lifecycle_mod, "save_knowledge_lifecycle_override_state"
            ), patch.object(
                lifecycle_mod,
                "refresh_knowledge_lifecycle_runtime",
                return_value={"entries": []},
            ), patch.object(
                lifecycle_mod,
                "concept_lifecycle_entry",
                return_value={"lifecycle_state": "active", "title": "X"},
            ), patch.object(
                lifecycle_mod, "append_runtime_history"
            ), patch.object(
                lifecycle_mod, "append_wiki_log"
            ), patch.object(
                lifecycle_mod,
                "knowledge_lifecycle_override_state_path",
                return_value=root / "override.json",
            ), patch.object(
                lifecycle_mod,
                "knowledge_lifecycle_state_path",
                return_value=root / "lifecycle.json",
            ), patch(
                "aiwiki.app_compile.utc_now", side_effect=_fake_utc
            ):
                lifecycle_mod.reactivate_concept(root, "x", note="probe")

        self.assertTrue(
            observed,
            msg="reactivate_concept did not route utc_now through "
            "aiwiki.app_compile; B3 lazy-lookup seam regressed.",
        )

    def test_b4_archive_module_resolves_to_execution_module(self) -> None:
        import importlib

        archive_mod = importlib.import_module("aiwiki.execution.archive")
        for name in ("apply_material_archive", "revert_material_archive"):
            app_compile.__dict__.pop(name, None)
        self.assertIs(
            app_compile.apply_material_archive, archive_mod.apply_material_archive
        )
        self.assertIs(
            app_compile.revert_material_archive, archive_mod.revert_material_archive
        )

    def test_b4_from_import_works(self) -> None:
        import importlib

        archive_mod = importlib.import_module("aiwiki.execution.archive")
        for name in ("apply_material_archive", "revert_material_archive"):
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import (\n"
            "    apply_material_archive,\n"
            "    revert_material_archive,\n"
            ")",
            {"__builtins__": __builtins__},
            local_ns,
        )
        self.assertIs(
            local_ns["apply_material_archive"], archive_mod.apply_material_archive
        )
        self.assertIs(
            local_ns["revert_material_archive"], archive_mod.revert_material_archive
        )

    def test_b4_apply_material_archive_uses_patched_utc_now(self) -> None:
        # ``apply_material_archive`` lazy-resolves ``utc_now`` for its
        # ``applied_at`` timestamp. Stub surrounding heavy surfaces and
        # verify ``patch("aiwiki.app_compile.utc_now")`` is honored.
        # Use ExitStack to avoid Python's 20-level nested-block limit.
        import contextlib
        import importlib
        import tempfile

        archive_mod = importlib.import_module("aiwiki.execution.archive")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wiki" / "state").mkdir(parents=True, exist_ok=True)
            material_state_file = root / "material_state.json"
            material_state_file.write_text("{}", encoding="utf-8")
            archive_candidates_file = root / "archive_candidates.json"
            archive_candidates_file.write_text("{}", encoding="utf-8")

            candidate = {
                "entry_id": "e1",
                "status": "ready",
                "recommended_temperature": "archived",
            }
            material_entry = {
                "entry_id": "e1",
                "temperature": "cold",
                "active_corpus_ids": [],
            }

            stubs = {
                "ensure_layout": None,
                "sync_manifest_with_raw": {"entries": []},
                "wiki_requires_compile": False,
                "material_state_path": material_state_file,
                "archive_candidates_state_path": archive_candidates_file,
                "compile_wiki": None,
                "load_manifest": {"entries": []},
                "load_archive_candidates_state": {"entries": [candidate]},
                "load_material_state": {"entries": [material_entry]},
                "load_material_archive_state": {"entries": []},
                "active_material_archive_entries": {},
                "load_protocol_state": {"active_protocol": "general"},
                "build_material_archive_bundle": {
                    "bundle_path": "wiki/bundles/e1.json"
                },
                "write_execution_bundle_document": None,
                "archive_dry_run_path": root / "dry.json",
                "write_execution_dry_run_document": None,
                "relative_path": "wiki/bundles/e1.json",
                "append_runtime_history": None,
                "append_wiki_log": None,
                "material_archive_action_id": "archive-e1",
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(archive_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                archive_mod.apply_material_archive(root, "e1", dry_run=True)

        self.assertTrue(
            observed,
            msg="apply_material_archive did not route utc_now through "
            "aiwiki.app_compile; B4 lazy-lookup seam regressed.",
        )

    def test_b4_revert_material_archive_uses_patched_utc_now(self) -> None:
        # Same hot-patch seam check for ``revert_material_archive``.
        # Use ExitStack to avoid Python's 20-level nested-block limit.
        import contextlib
        import importlib
        import tempfile

        archive_mod = importlib.import_module("aiwiki.execution.archive")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material_state_file = root / "material_state.json"
            material_state_file.write_text("{}", encoding="utf-8")
            receipt_file = root / "receipt.json"
            receipt_file.write_text("{}", encoding="utf-8")

            active_entry = {
                "entry_id": "e1",
                "title": "E1",
                "source_path": "wiki/sources/e1.md",
                "active": True,
                "last_receipt_path": "receipt.json",
            }
            valid_receipt = {
                "kind": "execution-receipt",
                "operation": "apply",
                "subject_id": "e1",
            }

            stubs = {
                "ensure_layout": None,
                "sync_manifest_with_raw": {"entries": []},
                "wiki_requires_compile": False,
                "material_state_path": material_state_file,
                "compile_wiki": None,
                "load_manifest": {"entries": []},
                "load_material_archive_state": {"entries": [active_entry]},
                "load_json_document_strict": valid_receipt,
                "load_protocol_state": {"active_protocol": "general"},
                "build_material_archive_receipt": {"kind": "execution-receipt"},
                "append_execution_receipt_history": None,
                "relative_path": "receipt.json",
                "save_material_archive_state": None,
                "append_runtime_history": None,
                "append_wiki_log": None,
                "material_archive_action_id": "archive-e1",
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(archive_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                archive_mod.revert_material_archive(root, "e1")

        self.assertTrue(
            observed,
            msg="revert_material_archive did not route utc_now through "
            "aiwiki.app_compile; B4 lazy-lookup seam regressed.",
        )

    def test_b5_concept_rewrite_module_resolves_to_execution_module(self) -> None:
        import importlib

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        migrated_names = (
            "review_concept_rewrite",
            "apply_concept_rewrite",
            "verify_concept_rewrite",
            "revert_concept_rewrite",
            "_load_concept_rewrite_proposals",
            "_find_concept_rewrite_proposal",
            "_save_concept_rewrite_proposals",
            "_evaluate_concept_rewrite_verification",
            "_persist_concept_rewrite_verification",
        )
        for name in migrated_names:
            app_compile.__dict__.pop(name, None)
        for name in migrated_names:
            self.assertIs(
                getattr(app_compile, name),
                getattr(concept_mod, name),
                msg=f"B5 seam for {name!r} did not resolve to aiwiki.execution.concept_rewrite",
            )

    def test_b5_from_import_works(self) -> None:
        import importlib

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        public_names = (
            "review_concept_rewrite",
            "apply_concept_rewrite",
            "verify_concept_rewrite",
            "revert_concept_rewrite",
        )
        for name in public_names:
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import (\n"
            "    review_concept_rewrite,\n"
            "    apply_concept_rewrite,\n"
            "    verify_concept_rewrite,\n"
            "    revert_concept_rewrite,\n"
            ")",
            {"__builtins__": __builtins__},
            local_ns,
        )
        for name in public_names:
            self.assertIs(
                local_ns[name],
                getattr(concept_mod, name),
                msg=f"B5 from-import for {name!r} did not resolve to migrated function",
            )

    def test_b5_review_concept_rewrite_uses_patched_utc_now(self) -> None:
        # ``review_concept_rewrite`` lazy-resolves ``utc_now`` for its
        # ``reviewed_at`` stamp. Verify the hot-patch seam.
        import contextlib
        import importlib

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        proposal = {
            "slug": "c1",
            "title": "C1",
            "status": "proposed",
            "target_path": "wiki/concepts/c1.md",
        }
        stubs = {
            "ensure_layout": None,
            "_load_concept_rewrite_proposals": [proposal],
            "_find_concept_rewrite_proposal": proposal,
            "rewrite_proposal_candidate_is_current": True,
            "rewrite_proposal_is_apply_ready": False,
            "rewrite_proposal_needs_review": False,
            "_save_concept_rewrite_proposals": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
            "compile_wiki": None,
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(
                    patch.object(concept_mod, name, return_value=return_value)
                )
            stack.enter_context(
                patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
            )
            concept_mod.review_concept_rewrite(Path("/tmp"), "c1", "accepted")

        self.assertTrue(
            observed,
            msg="review_concept_rewrite did not route utc_now through "
            "aiwiki.app_compile; B5 lazy-lookup seam regressed.",
        )

    def test_b5_apply_concept_rewrite_dry_run_uses_patched_utc_now(self) -> None:
        # ``apply_concept_rewrite`` dry-run path lazy-resolves ``utc_now``
        # for its ``previewed_at`` / ``generated_at`` stamp.
        import contextlib
        import importlib
        import tempfile

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            concept_path = root / "wiki" / "concepts"
            concept_path.mkdir(parents=True, exist_ok=True)
            target_file = concept_path / "c1.md"
            target_file.write_text(
                "---\nid: concept-c1\nkind: concept\n---\n\n## Summary\n\nOld summary\n",
                encoding="utf-8",
            )

            proposal = {
                "slug": "c1",
                "title": "C1",
                "status": "accepted",
                "target_path": "wiki/concepts/c1.md",
                "candidate_markdown": (
                    "---\nid: concept-c1\nkind: concept\n---\n\n"
                    "## Summary\n\nNew summary\n"
                ),
                "source_signature": "",
                "proposal_path": "wiki/review/c1.md",
            }
            stubs = {
                "ensure_layout": None,
                "_load_concept_rewrite_proposals": [proposal],
                "_find_concept_rewrite_proposal": proposal,
                "_validate_rewrite_candidate_markdown": None,
                "rewrite_dry_run_path": root / "dry.json",
                "write_execution_dry_run_document": None,
                "append_runtime_history": None,
                "append_wiki_log": None,
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(concept_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                concept_mod.apply_concept_rewrite(root, "c1", dry_run=True)

        self.assertTrue(
            observed,
            msg="apply_concept_rewrite(dry_run=True) did not route utc_now "
            "through aiwiki.app_compile; B5 lazy-lookup seam regressed.",
        )

    def test_b5_apply_concept_rewrite_real_uses_patched_utc_now(self) -> None:
        # ``apply_concept_rewrite`` non-dry-run path lazy-resolves
        # ``utc_now`` for its ``applied_at`` stamp. Distinct from the
        # dry-run canary because the two branches reach different
        # utc_now call sites in the same function.
        import contextlib
        import importlib
        import tempfile

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            concept_path = root / "wiki" / "concepts"
            concept_path.mkdir(parents=True, exist_ok=True)
            target_file = concept_path / "c1.md"
            target_file.write_text(
                "---\nid: concept-c1\nkind: concept\n---\n\n## Summary\n\nOld summary\n",
                encoding="utf-8",
            )

            proposal = {
                "slug": "c1",
                "title": "C1",
                "status": "accepted",
                "target_path": "wiki/concepts/c1.md",
                "candidate_markdown": (
                    "---\nid: concept-c1\nkind: concept\n---\n\n"
                    "## Summary\n\nNew summary\n"
                ),
                "source_signature": "",
                "proposal_path": "wiki/review/c1.md",
            }
            stubs = {
                "ensure_layout": None,
                "_load_concept_rewrite_proposals": [proposal],
                "_find_concept_rewrite_proposal": proposal,
                "_validate_rewrite_candidate_markdown": None,
                "concept_page_snapshot": {"content": "old"},
                "_save_concept_rewrite_proposals": None,
                "append_wiki_log": None,
                "compile_wiki": None,
                "_persist_concept_rewrite_verification": {
                    "status": "pending",
                    "summary": "",
                    "issues": [],
                    "checked_at": "",
                },
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(concept_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                concept_mod.apply_concept_rewrite(root, "c1", dry_run=False)

        self.assertTrue(
            observed,
            msg="apply_concept_rewrite(dry_run=False) did not route utc_now "
            "through aiwiki.app_compile; B5 lazy-lookup seam regressed.",
        )

    def test_b5_evaluate_verification_uses_patched_utc_now(self) -> None:
        # ``_evaluate_concept_rewrite_verification`` lazy-resolves
        # ``utc_now`` for its ``checked_at`` stamp. This covers the code
        # path that ``verify_concept_rewrite`` reaches via
        # ``_persist_concept_rewrite_verification``.
        import contextlib
        import importlib

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        proposal = {
            "slug": "c1",
            "target_path": "wiki/concepts/c1.md",
            "source_signature": "sig-x",
            "source_pages": ["a.md"],
            "candidate_markdown": "## Summary\n\nBody\n",
        }
        stubs = {
            "preserved_section": "Body",
            "concept_page_snapshot": {
                "content": (
                    "---\nid: concept-c1\nkind: concept\n"
                    "source_signature: sig-x\nsource_pages:\n- a.md\n---\n\n"
                    "## Summary\n\nBody\n"
                ),
                "summary": "Body",
            },
            "parse_frontmatter": {
                "id": "concept-c1",
                "kind": "concept",
                "source_signature": "sig-x",
                "source_pages": ["a.md"],
            },
            "load_machine_memory": {
                "concept_nodes": [{"slug": "c1", "source_pages": ["a.md"]}],
                "health": {
                    "concept_quality": {
                        "all_concepts": [
                            {"slug": "c1", "quality_score": 90, "quality_state": "good"}
                        ]
                    }
                },
            },
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(
                    patch.object(concept_mod, name, return_value=return_value)
                )
            stack.enter_context(
                patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
            )
            concept_mod._evaluate_concept_rewrite_verification(Path("/tmp"), proposal)

        self.assertTrue(
            observed,
            msg="_evaluate_concept_rewrite_verification did not route utc_now "
            "through aiwiki.app_compile; B5 lazy-lookup seam regressed.",
        )

    def test_b5_revert_concept_rewrite_uses_patched_utc_now(self) -> None:
        # ``revert_concept_rewrite`` lazy-resolves ``utc_now`` for its
        # ``reverted_at`` stamp.
        import contextlib
        import importlib
        import tempfile

        concept_mod = importlib.import_module("aiwiki.execution.concept_rewrite")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            concept_dir = root / "wiki" / "concepts"
            concept_dir.mkdir(parents=True, exist_ok=True)
            target_file = concept_dir / "c1.md"
            target_file.write_text("current\n", encoding="utf-8")

            proposal = {
                "slug": "c1",
                "title": "C1",
                "status": "applied",
                "target_path": "wiki/concepts/c1.md",
                "candidate_markdown": "## Summary\n\nNew\n",
                "previous_markdown": "## Summary\n\nOld\n",
                "last_applied_at": "2026-04-23T00:00:00Z",
            }
            stubs = {
                "ensure_layout": None,
                "_load_concept_rewrite_proposals": [proposal],
                "_find_concept_rewrite_proposal": proposal,
                "preserved_section": "New",
                "concept_page_snapshot": {"summary": "New"},
                "rewrite_proposal_needs_review": False,
                "rewrite_proposal_is_apply_ready": False,
                "_save_concept_rewrite_proposals": None,
                "append_runtime_history": None,
                "append_wiki_log": None,
                "compile_wiki": None,
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(
                        patch.object(concept_mod, name, return_value=return_value)
                    )
                stack.enter_context(
                    patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc)
                )
                concept_mod.revert_concept_rewrite(root, "c1")

        self.assertTrue(
            observed,
            msg="revert_concept_rewrite did not route utc_now through "
            "aiwiki.app_compile; B5 lazy-lookup seam regressed.",
        )

    def test_b6_machine_memory_actions_module_resolves_to_execution_module(self) -> None:
        import importlib


        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        migrated_names = (
            "resolve_machine_memory_action_query",
            "review_machine_memory_action",
            "review_machine_memory_actions_batch",
            "apply_machine_memory_action",
            "revert_machine_memory_action",
            "_save_machine_memory_action_records",
        )
        for name in migrated_names:
            app_compile.__dict__.pop(name, None)
        for name in migrated_names:
            self.assertIs(
                getattr(app_compile, name),
                getattr(mm_mod, name),
                msg=f"B6 seam for {name!r} did not resolve to aiwiki.execution.machine_memory_actions",
            )

    def test_b6_from_import_works(self) -> None:
        import importlib


        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        public_names = (
            "resolve_machine_memory_action_query",
            "review_machine_memory_action",
            "review_machine_memory_actions_batch",
            "apply_machine_memory_action",
            "revert_machine_memory_action",
        )
        for name in public_names:
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import (\n"
            "    resolve_machine_memory_action_query,\n"
            "    review_machine_memory_action,\n"
            "    review_machine_memory_actions_batch,\n"
            "    apply_machine_memory_action,\n"
            "    revert_machine_memory_action,\n"
            ")",
            {"__builtins__": __builtins__},
            local_ns,
        )
        for name in public_names:
            self.assertIs(
                local_ns[name],
                getattr(mm_mod, name),
                msg=f"B6 from-import for {name!r} did not resolve to migrated function",
            )

    def test_b6_review_machine_memory_action_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib


        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        stubs = {
            "ensure_layout": None,
            "load_machine_memory_action_state_strict": {"actions": [{"id": "a1", "title": "A1", "protocol": "general"}]},
            "resolve_machine_memory_action_query": {"id": "a1", "title": "A1", "protocol": "general"},
            "schedule_review_windows": ("", ""),
            "evaluate_page_aging": {},
            "save_machine_memory_action_state": None,
            "append_wiki_log": None,
            "compile_wiki": None,
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(mm_mod, name, return_value=return_value))
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            mm_mod.review_machine_memory_action(Path("/tmp"), "a1", "accepted")

        self.assertTrue(
            observed,
            msg="review_machine_memory_action did not route utc_now through aiwiki.app_compile; B6 lazy-lookup seam regressed.",
        )

    def test_b6_apply_machine_memory_action_dry_run_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib

        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        target = {"id": "a1", "title": "A1", "status": "accepted", "protocol": "general"}
        proposal = {"bundle_path": "bundle.json", "proposal_path": "proposal.json", "safe_apply_preview": {"apply_mode": "resolve-monitor"}}
        stubs = {
            "ensure_layout": None,
            "load_machine_memory_action_state_strict": {"actions": [target]},
            "resolve_machine_memory_action_query": target,
            "load_protocol_state": {"active_protocol": "general"},
            "repair_execution_proposals": [proposal],
            "build_page_patch_plan": {},
            "safe_apply_preview": {"apply_mode": "resolve-monitor"},
            "execution_bundle_path": Path("bundle.json"),
            "execution_proposal_path": Path("proposal.json"),
            "relative_path": "bundle.json",
            "build_execution_bundle": {"digest": "d1"},
            "write_execution_bundle_document": None,
            "execution_dry_run_path": Path("dry-run.json"),
            "write_execution_dry_run_document": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(mm_mod, name, return_value=return_value))
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            mm_mod.apply_machine_memory_action(Path("/tmp"), "a1", dry_run=True)

        self.assertTrue(
            observed,
            msg="apply_machine_memory_action(dry_run=True) did not route utc_now through aiwiki.app_compile; B6 lazy-lookup seam regressed.",
        )

    def test_b6_apply_machine_memory_action_real_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib
        import json
        import tempfile

        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_path = root / "receipt.json"
            receipt_path.write_text(
                json.dumps({"kind": "execution-receipt", "operation": "apply", "action_id": "a1", "safe_apply_preview": {"apply_mode": "resolve-monitor"}}),
                encoding="utf-8",
            )
            target = {"id": "a1", "title": "A1", "status": "accepted", "protocol": "general", "last_receipt_path": "receipt.json"}
            bundle = {"action_id": "a1", "digest": "digest-1", "safe_apply_preview": {"apply_mode": "resolve-monitor"}}
            stubs = {
                "ensure_layout": None,
                "load_machine_memory_action_state_strict": {"actions": [target]},
                "resolve_machine_memory_action_query": target,
                "load_protocol_state": {"active_protocol": "general"},
                "repair_execution_proposals": [bundle],
                "build_page_patch_plan": {},
                "safe_apply_preview": {"apply_mode": "resolve-monitor"},
                "execution_bundle_path": root / "bundle.json",
                "execution_proposal_path": root / "proposal.json",
                "relative_path": "receipt.json",
                "build_execution_bundle": {"digest": "digest-1", "safe_apply_preview": {"apply_mode": "resolve-monitor"}},
                "load_execution_bundle": bundle,
                "execution_bundle_digest": "digest-1",
                "build_execution_receipt": {"kind": "execution-receipt"},
                "append_execution_receipt_history": None,
                "execution_receipt_path": receipt_path,
                "append_runtime_history": None,
                "append_wiki_log": None,
                "compile_wiki": None,
                "_save_machine_memory_action_records": None,
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(patch.object(mm_mod, name, return_value=return_value))
                stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
                result = mm_mod.apply_machine_memory_action(root, "a1", dry_run=False)

        # Distinct-call-site proof: dry_run=False reaches TWO utc_now call
        # sites — line ~257 ``previewed_at`` (shared with dry_run) AND line
        # ~332 ``applied_at`` (unique to the real branch). If the second
        # site regresses to an unpatched lookup, a mere truthy assertion
        # on ``observed`` still passes because the first site fired. Lock
        # both sites individually.
        self.assertEqual(
            len(observed),
            2,
            msg=(
                "apply_machine_memory_action(dry_run=False) must reach both "
                "utc_now call sites (previewed_at + applied_at); got "
                f"{len(observed)} observed stamps: {observed!r}. B6 "
                "lazy-lookup seam regressed on the applied_at site."
            ),
        )
        self.assertEqual(
            result.get("applied_at"),
            "patched-utc-1",
            msg=(
                "apply_machine_memory_action(dry_run=False) did not route "
                "the applied_at stamp through the patched aiwiki.app_compile.utc_now; "
                "B6 lazy-lookup seam regressed on the second utc_now call site."
            ),
        )

    def test_b6_revert_machine_memory_action_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib
        import json
        import tempfile

        mm_mod = importlib.import_module("aiwiki.execution.machine_memory_actions")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_path = root / "receipt.json"
            receipt_path.write_text(
                json.dumps({"kind": "execution-receipt", "operation": "apply", "action_id": "a1", "safe_apply_preview": {"apply_mode": "resolve-monitor"}}),
                encoding="utf-8",
            )
            target = {"id": "a1", "title": "A1", "status": "resolved", "protocol": "general", "last_receipt_path": "receipt.json"}
            stubs = {
                "ensure_layout": None,
                "load_machine_memory_action_state_strict": {"actions": [target]},
                "resolve_machine_memory_action_query": target,
                "load_json_document_strict": {"kind": "execution-receipt", "operation": "apply", "action_id": "a1", "safe_apply_preview": {"apply_mode": "resolve-monitor"}},
                "load_protocol_state": {"active_protocol": "general"},
                "repair_execution_proposals": [{"safe_apply_preview": {"apply_mode": "resolve-monitor"}}],
                "build_page_patch_plan": {},
                "safe_apply_preview": {"apply_mode": "resolve-monitor"},
                "execution_bundle_path": root / "bundle.json",
                "execution_proposal_path": root / "proposal.json",
                "relative_path": "receipt.json",
                "build_execution_receipt": {"kind": "execution-receipt"},
                "append_execution_receipt_history": None,
                "schedule_review_windows": ("", ""),
                "evaluate_page_aging": {},
                "_save_machine_memory_action_records": None,
                "append_wiki_log": None,
                "compile_wiki": None,
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(patch.object(mm_mod, name, return_value=return_value))
                stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
                mm_mod.revert_machine_memory_action(root, "a1")

        self.assertTrue(
            observed,
            msg="revert_machine_memory_action did not route utc_now through aiwiki.app_compile; B6 lazy-lookup seam regressed.",
        )

    # ------------------------------------------------------------------
    # EP-018B7 — review page & machine-memory batch
    # ------------------------------------------------------------------

    def test_b7_review_module_resolves_to_execution_module(self) -> None:
        import importlib

        review_mod = importlib.import_module("aiwiki.execution.review")
        name = "review_page"
        app_compile.__dict__.pop(name, None)
        self.assertIs(
            getattr(app_compile, name),
            review_mod.review_page,
            msg="B7 seam for 'review_page' did not resolve to aiwiki.execution.review",
        )

    def test_b7_machine_memory_batch_module_resolves_to_execution_module(self) -> None:
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        migrated_names = (
            "review_pages_batch",
            "apply_machine_memory_actions_batch",
            "revert_machine_memory_action_batch",
            "_build_batch_id",
            "_load_latest_action_apply_batch_receipt",
        )
        for name in migrated_names:
            app_compile.__dict__.pop(name, None)
        for name in migrated_names:
            self.assertIs(
                getattr(app_compile, name),
                getattr(batch_mod, name),
                msg=f"B7 seam for {name!r} did not resolve to aiwiki.execution.machine_memory_batch",
            )

    def test_b7_from_import_works(self) -> None:
        import importlib

        review_mod = importlib.import_module("aiwiki.execution.review")
        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        expected = {
            "review_page": review_mod.review_page,
            "review_pages_batch": batch_mod.review_pages_batch,
            "apply_machine_memory_actions_batch": batch_mod.apply_machine_memory_actions_batch,
            "revert_machine_memory_action_batch": batch_mod.revert_machine_memory_action_batch,
        }
        for name in expected:
            app_compile.__dict__.pop(name, None)
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import (\n"
            "    review_page,\n"
            "    review_pages_batch,\n"
            "    apply_machine_memory_actions_batch,\n"
            "    revert_machine_memory_action_batch,\n"
            ")",
            {"__builtins__": __builtins__},
            local_ns,
        )
        for name, target in expected.items():
            self.assertIs(
                local_ns[name],
                target,
                msg=f"B7 from-import for {name!r} did not resolve to migrated function",
            )

    def test_b7_review_page_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib
        import tempfile

        review_mod = importlib.import_module("aiwiki.execution.review")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_path = root / "page.md"
            target_path.write_text(
                "---\nkind: judgment\nstatus: draft\n---\n\nBody.\n",
                encoding="utf-8",
            )
            stubs = {
                "ensure_layout": None,
                "parse_frontmatter": {"kind": "judgment", "status": "draft"},
                "strip_frontmatter": "Body.",
                "valid_curated_statuses": ("active",),
                "schedule_review_windows": ("", ""),
                "upsert_markdown_section": "Body.",
                "append_review_history_entry": "Body.",
                "extract_provenance_paths": [],
                "build_citation_snapshots": [],
                "analyze_citation_snapshots": {"has_drift": False, "missing": [], "stale": []},
                "judgment_lifecycle_profile": ("active", []),
                "render_frontmatter": "---\nkind: judgment\n---",
                "review_history_entries": [],
                "entry_lookup_maps": ({}, {}),
                "load_manifest": {"entries": []},
                "entry_ids_from_paths": [],
                "append_runtime_history": None,
                "append_wiki_log": None,
                "compile_wiki": None,
                "relative_path": "page.md",
            }
            with contextlib.ExitStack() as stack:
                for name, return_value in stubs.items():
                    stack.enter_context(patch.object(review_mod, name, return_value=return_value))
                stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
                review_mod.review_page(root, str(target_path), "active", confidence="medium")

        self.assertEqual(
            len(observed),
            1,
            msg=(
                "review_page must reach exactly one utc_now call site; got "
                f"{len(observed)} observed stamps: {observed!r}. B7 lazy-lookup "
                "seam regressed (double-call or missing call)."
            ),
        )

    def test_b7_build_batch_id_uses_patched_utc_now(self) -> None:
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        with patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc):
            result = batch_mod._build_batch_id("review-page-batch", ["pages/foo.md"])

        self.assertEqual(
            len(observed),
            1,
            msg=(
                "_build_batch_id must reach exactly one utc_now call site; got "
                f"{len(observed)} observed stamps: {observed!r}. B7 lazy-lookup "
                "seam regressed."
            ),
        )
        self.assertIn(
            "patched-utc-0",
            result,
            msg=(
                "_build_batch_id did not route the timestamp through the "
                "patched aiwiki.app_compile.utc_now; B7 lazy-lookup seam regressed."
            ),
        )

    def test_b7_review_pages_batch_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        stubs = {
            "ensure_layout": None,
            "build_execution_batch_receipt": {"kind": "execution-batch-receipt", "batch_id": "b1"},
            "execution_batch_receipt_path": Path("receipt.json"),
            "write_execution_batch_receipt_document": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
            "relative_path": "receipt.json",
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(batch_mod, name, return_value=return_value))
            # review_page is invoked via _app_compile.review_page(...) lazy
            # seam (B7 MF1 fix); patch must target the app_compile namespace,
            # NOT batch_mod (where the symbol no longer exists).
            stack.enter_context(
                patch("aiwiki.app_compile.review_page", return_value={"path": "page.md", "status": "active"})
            )
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            batch_mod.review_pages_batch(Path("/tmp"), ["page.md"], "active")

        # review_pages_batch reaches TWO utc_now sites: its own
        # ``generated_at`` AND ``_build_batch_id``'s site. Lock both.
        self.assertEqual(
            len(observed),
            2,
            msg=(
                "review_pages_batch must reach both utc_now call sites "
                "(generated_at + _build_batch_id); got "
                f"{len(observed)} observed stamps: {observed!r}. B7 "
                "lazy-lookup seam regressed."
            ),
        )

    def test_b7_apply_machine_memory_actions_batch_dry_run_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        action = {"id": "a1", "title": "A1", "status": "accepted"}
        preview = {"id": "a1", "bundle_path": "bundle.json"}
        stubs = {
            "ensure_layout": None,
            "load_machine_memory_action_state_strict": {"actions": [action]},
            "action_supports_low_risk_apply": True,
            "build_execution_batch_receipt": {"kind": "execution-batch-receipt", "batch_id": "b1"},
            "execution_batch_receipt_path": Path("receipt.json"),
            "write_execution_batch_receipt_document": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
            "relative_path": "receipt.json",
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(batch_mod, name, return_value=return_value))
            # apply_machine_memory_action goes through _app_compile.<name>(...)
            # lazy seam (B7 MF1 fix); patch in app_compile namespace.
            stack.enter_context(
                patch("aiwiki.app_compile.apply_machine_memory_action", return_value=preview)
            )
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            batch_mod.apply_machine_memory_actions_batch(Path("/tmp"), ["a1"], dry_run=True)

        # dry_run=True reaches TWO utc_now sites: ``generated_at`` +
        # ``_build_batch_id``.
        self.assertEqual(
            len(observed),
            2,
            msg=(
                "apply_machine_memory_actions_batch(dry_run=True) must reach "
                "both utc_now call sites (generated_at + _build_batch_id); got "
                f"{len(observed)} observed stamps: {observed!r}. B7 "
                "lazy-lookup seam regressed."
            ),
        )

    def test_b7_apply_machine_memory_actions_batch_real_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        action = {"id": "a1", "title": "A1", "status": "accepted"}
        preview = {"id": "a1", "bundle_path": "bundle.json"}
        applied = {"id": "a1", "applied_at": "real-applied"}
        # apply_machine_memory_action is called TWICE in non-dry-run path
        # (preview + real). Stub returns in sequence.
        apply_sequence = [preview, applied]
        stubs = {
            "ensure_layout": None,
            "load_machine_memory_action_state_strict": {"actions": [action]},
            "action_supports_low_risk_apply": True,
            "build_execution_batch_receipt": {"kind": "execution-batch-receipt", "batch_id": "b1"},
            "execution_batch_receipt_path": Path("receipt.json"),
            "write_execution_batch_receipt_document": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
            "relative_path": "receipt.json",
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(batch_mod, name, return_value=return_value))
            # apply_machine_memory_action is invoked twice via
            # _app_compile.apply_machine_memory_action(...) lazy seam (B7
            # MF1 fix); patch in app_compile namespace, NOT batch_mod.
            stack.enter_context(
                patch("aiwiki.app_compile.apply_machine_memory_action", side_effect=apply_sequence)
            )
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            batch_mod.apply_machine_memory_actions_batch(Path("/tmp"), ["a1"], dry_run=False)

        # dry_run=False reaches the same TWO utc_now sites as dry_run=True.
        # The B6 ``apply_machine_memory_action`` it calls has its own utc_now
        # sites, but those are mocked out here.
        self.assertEqual(
            len(observed),
            2,
            msg=(
                "apply_machine_memory_actions_batch(dry_run=False) must reach "
                "both utc_now call sites (generated_at + _build_batch_id); got "
                f"{len(observed)} observed stamps: {observed!r}. B7 "
                "lazy-lookup seam regressed."
            ),
        )

    def test_b7_revert_machine_memory_action_batch_uses_patched_utc_now(self) -> None:
        import contextlib
        import importlib

        batch_mod = importlib.import_module("aiwiki.execution.machine_memory_batch")
        observed: list[str] = []

        def _fake_utc() -> str:
            stamp = f"patched-utc-{len(observed)}"
            observed.append(stamp)
            return stamp

        target_receipt = {
            "kind": "execution-batch-receipt",
            "operation": "action-apply-batch",
            "batch_id": "b-apply-1",
            "items": [{"id": "a1"}],
        }
        stubs = {
            "ensure_layout": None,
            "_load_latest_action_apply_batch_receipt": target_receipt,
            "build_execution_batch_receipt": {"kind": "execution-batch-receipt", "batch_id": "b-revert-1"},
            "execution_batch_receipt_path": Path("receipt.json"),
            "write_execution_batch_receipt_document": None,
            "append_runtime_history": None,
            "append_wiki_log": None,
            "relative_path": "receipt.json",
        }
        with contextlib.ExitStack() as stack:
            for name, return_value in stubs.items():
                stack.enter_context(patch.object(batch_mod, name, return_value=return_value))
            # revert_machine_memory_action is invoked via
            # _app_compile.revert_machine_memory_action(...) lazy seam (B7
            # MF1 fix); patch in app_compile namespace, NOT batch_mod.
            stack.enter_context(
                patch(
                    "aiwiki.app_compile.revert_machine_memory_action",
                    return_value={"id": "a1", "reverted": True},
                )
            )
            stack.enter_context(patch("aiwiki.app_compile.utc_now", side_effect=_fake_utc))
            batch_mod.revert_machine_memory_action_batch(Path("/tmp"))

        # revert_machine_memory_action_batch reaches TWO utc_now sites:
        # ``generated_at`` + ``_build_batch_id``.
        self.assertEqual(
            len(observed),
            2,
            msg=(
                "revert_machine_memory_action_batch must reach both utc_now "
                "call sites (generated_at + _build_batch_id); got "
                f"{len(observed)} observed stamps: {observed!r}. B7 "
                "lazy-lookup seam regressed."
            ),
        )


class ExecutionCompatSeamMigrationSimulationTests(unittest.TestCase):
    """Simulate the EP-018B flip: temporarily remove a lazy name from
    ``app_compile.__dict__`` and point its owner at a stub sibling module
    injected into ``sys.modules``. The seam's non-self-reference branch
    MUST handle every access pattern callers use today.
    """

    STUB_MODULE_NAME = "aiwiki._ep018a_stub_owner"
    TARGET_NAME = "shell_status"  # low-risk stable execution surface

    def setUp(self) -> None:
        # Snapshot everything we mutate so tearDown fully restores the module.
        self._original_dict_entry_present = self.TARGET_NAME in app_compile.__dict__
        self._original_value = app_compile.__dict__.get(self.TARGET_NAME)
        self._original_owner = app_compile._LAZY_OWNERS[self.TARGET_NAME]

        def _stub_impl(root, *, sentinel: str = "ep018a-stub") -> dict[str, str]:
            return {"sentinel": sentinel, "root": str(root)}

        stub = types.ModuleType(self.STUB_MODULE_NAME)
        setattr(stub, self.TARGET_NAME, _stub_impl)
        sys.modules[self.STUB_MODULE_NAME] = stub
        self._stub = stub
        self._stub_impl = _stub_impl

        # Flip the seam: remove direct binding, retarget owner to the stub.
        if self._original_dict_entry_present:
            del app_compile.__dict__[self.TARGET_NAME]
        app_compile._LAZY_OWNERS[self.TARGET_NAME] = self.STUB_MODULE_NAME

    def tearDown(self) -> None:
        # Drop any cache-to-globals write the seam did during the test.
        app_compile.__dict__.pop(self.TARGET_NAME, None)
        # Restore original owner + original direct binding.
        app_compile._LAZY_OWNERS[self.TARGET_NAME] = self._original_owner
        if self._original_dict_entry_present:
            app_compile.__dict__[self.TARGET_NAME] = self._original_value
        sys.modules.pop(self.STUB_MODULE_NAME, None)

    def test_getattr_resolves_to_stub_after_flip(self) -> None:
        resolved = getattr(app_compile, self.TARGET_NAME)
        self.assertIs(resolved, self._stub_impl)
        self.assertEqual(
            resolved("/tmp/root"), {"sentinel": "ep018a-stub", "root": "/tmp/root"}
        )

    def test_getattr_caches_resolved_value_into_globals(self) -> None:
        self.assertNotIn(self.TARGET_NAME, app_compile.__dict__)
        _ = getattr(app_compile, self.TARGET_NAME)
        self.assertIn(self.TARGET_NAME, app_compile.__dict__)
        self.assertIs(app_compile.__dict__[self.TARGET_NAME], self._stub_impl)

    def test_from_import_works_after_flip(self) -> None:
        # ``from aiwiki.app_compile import shell_status`` must resolve
        # through the seam. Drive a real from-import path by executing it
        # in a fresh namespace — ``importlib.import_module`` + ``getattr``
        # would only retrace the normal attribute lookup we already cover,
        # not the bytecode ``IMPORT_FROM`` opcode's path.
        local_ns: dict[str, object] = {}
        exec(
            "from aiwiki.app_compile import shell_status",
            {"__builtins__": __builtins__},
            local_ns,
        )
        self.assertIn(self.TARGET_NAME, local_ns)
        self.assertIs(local_ns[self.TARGET_NAME], self._stub_impl)

        # And the ``__import__(..., fromlist=[...])`` path (what ``from X
        # import Y`` lowers to when ``X`` is a dotted name) must also work.
        mod = __import__(
            "aiwiki.app_compile", fromlist=[self.TARGET_NAME]
        )
        self.assertIs(getattr(mod, self.TARGET_NAME), self._stub_impl)

    def test_patch_works_after_flip(self) -> None:
        # Critical: tests/test_execution.py & friends patch lazy names. Even
        # with the direct binding removed and owner pointing to a stub,
        # ``unittest.mock.patch`` must resolve cleanly.
        with patch(
            f"aiwiki.app_compile.{self.TARGET_NAME}",
            return_value={"probe": "patched"},
        ) as mocked:
            result = getattr(app_compile, self.TARGET_NAME)("ignored")
            self.assertEqual(result, {"probe": "patched"})
            self.assertTrue(mocked.called)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
