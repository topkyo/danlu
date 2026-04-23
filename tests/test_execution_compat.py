"""Canary tests for the EP-018A execution-owner lazy compat seam.

Guards (post independent oracle review):

1. Every execution name listed in ``aiwiki.app_compile._LAZY_OWNERS`` is
   resolvable via ``getattr`` and is a real callable.
2. The count and shape match the plan: 21 public execution functions +
   8 private helpers = 29 total.
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

import sys
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
    # Machine-memory action (4 public + 1 private helper)
    "resolve_machine_memory_action_query",
    "review_machine_memory_action",
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
        # Plan promises 21 public + 8 private helpers = 29.
        keys = list(app_compile._LAZY_OWNERS.keys())
        public = [k for k in keys if not k.startswith("_")]
        private = [k for k in keys if k.startswith("_")]
        self.assertEqual(len(keys), 29)
        self.assertEqual(len(public), 21)
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
            result = runtime_surfaces.nightly_health(MagicMock())

        # Two calls per accepted id: one dry-run, one real.
        self.assertEqual(len(observed), 2)
        self.assertEqual(len(result["auto_applied"]), 1)

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
