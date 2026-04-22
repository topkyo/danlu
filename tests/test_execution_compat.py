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
from unittest.mock import patch

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
        for name, owner in app_compile._LAZY_OWNERS.items():
            self.assertEqual(
                owner,
                "aiwiki.app_compile",
                msg=f"EP-018A expects {name!r} to self-reference; got {owner!r}",
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
