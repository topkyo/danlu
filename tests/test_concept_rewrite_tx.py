"""R94.4 — apply/revert concept-rewrite are transactional over the
file-write + state-save critical pair.

Previously `apply_concept_rewrite` overwrote the concept page with the
candidate markdown BEFORE saving the proposal state. If the state save
failed (disk full, lock contention, IOError), the concept file was left
overwritten with no recoverable `previous_markdown` in proposal state =
permanent data loss of the prior concept synthesis.

`revert_concept_rewrite` had the symmetric bug.

These tests exercise that critical pair via injected save failure and
assert:
- the concept file is rolled back to its pre-call bytes
- the original IOError surfaces (not a rollback exception)
- best-effort follow-ups (compile, history, log, verification) failing
  AFTER state save do NOT trigger a rollback (state is the SOT)
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import save_concept_rewrite_state
from aiwiki.execution import concept_rewrite as cr_mod


def _seed_proposal(root: Path, *, slug: str, current: str, candidate: str) -> None:
    """Materialise a minimally-valid concept page + accepted rewrite proposal.

    Bypasses `_validate_rewrite_candidate_markdown` and `concept_page_snapshot`
    via patching at call time — those are tested elsewhere; here we focus on
    the transactional contract of the apply/revert critical pair.
    """
    concept_dir = root / "wiki" / "concepts"
    concept_dir.mkdir(parents=True, exist_ok=True)
    concept_path = concept_dir / f"{slug}.md"
    concept_path.write_text(current, encoding="utf-8")
    save_concept_rewrite_state(
        root,
        {
            "version": 1,
            "proposals": [
                {
                    "slug": slug,
                    "title": f"Concept {slug}",
                    "status": "accepted",
                    "candidate_markdown": candidate,
                    "target_path": f"wiki/concepts/{slug}.md",
                    "proposal_path": f"wiki/concepts/{slug}.proposal.md",
                    "source_signature": "sig-1",
                    "source_pages": ["wiki/sources/s1.md"],
                }
            ],
        },
    )


class ApplyConceptRewriteTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.slug = "scaling"
        self.current_text = "# Concept scaling\n\nOriginal synthesis content.\n"
        self.candidate_text = "# Concept scaling\n\nRewritten synthesis content.\n"
        _seed_proposal(
            self.root,
            slug=self.slug,
            current=self.current_text,
            candidate=self.candidate_text,
        )
        self.concept_path = self.root / "wiki" / "concepts" / f"{self.slug}.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _stub_validation(self, stack: object) -> None:
        # Fast-skip frontmatter validation + source_signature check — those
        # are invariants of upstream pipeline, not of the TX contract.
        stack.enter_context(
            patch.object(cr_mod, "_validate_rewrite_candidate_markdown", return_value=None)
        )
        stack.enter_context(
            patch.object(cr_mod, "parse_frontmatter", return_value={"source_signature": "sig-1", "source_pages": ["wiki/sources/s1.md"]})
        )
        stack.enter_context(
            patch.object(cr_mod, "concept_page_snapshot", return_value={"content": self.current_text, "summary": ""})
        )

    def test_apply_state_save_failure_rolls_back_concept_file(self) -> None:
        import contextlib

        with contextlib.ExitStack() as stack:
            self._stub_validation(stack)
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "_save_concept_rewrite_proposals",
                    side_effect=OSError("simulated disk full"),
                )
            )
            with self.assertRaises(OSError) as ctx:
                cr_mod.apply_concept_rewrite(self.root, self.slug, note="trigger")

        self.assertIn("simulated disk full", str(ctx.exception))
        # Concept file must be restored to its pre-apply bytes.
        self.assertEqual(
            self.concept_path.read_text(encoding="utf-8"),
            self.current_text,
        )

    def test_apply_compile_failure_does_not_roll_back_concept_file(self) -> None:
        # Phase 2 (post state-save) failures must NOT roll back the file —
        # state is already SOT and re-running compile fixes derived layer.
        import contextlib

        with contextlib.ExitStack() as stack:
            self._stub_validation(stack)
            stack.enter_context(
                patch.object(cr_mod, "compile_wiki", side_effect=RuntimeError("compile boom"))
            )
            with self.assertRaises(RuntimeError):
                cr_mod.apply_concept_rewrite(self.root, self.slug, note="trigger")

        # File should hold the candidate content (apply succeeded for SOT).
        self.assertEqual(
            self.concept_path.read_text(encoding="utf-8").strip(),
            self.candidate_text.strip(),
        )

    def test_apply_state_save_failure_preserves_original_exception(self) -> None:
        # Even if rollback itself raises (atomic_write_bytes fails), the
        # original IOError must be the surfaced exception, not a double-fault
        # from the rollback path. Rollback failure is logged, not re-raised.
        import contextlib

        with contextlib.ExitStack() as stack:
            self._stub_validation(stack)
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "atomic_write_bytes",
                    side_effect=OSError("rollback also failed"),
                )
            )
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "_save_concept_rewrite_proposals",
                    side_effect=OSError("simulated state corruption"),
                )
            )
            with self.assertLogs(cr_mod.logger, level="WARNING") as log_ctx:
                with self.assertRaises(OSError) as ctx:
                    cr_mod.apply_concept_rewrite(self.root, self.slug, note="trigger")

        # The original state-save error wins. Rollback fault is logged.
        self.assertIn("simulated state corruption", str(ctx.exception))
        self.assertTrue(
            any("rollback failed" in msg for msg in log_ctx.output),
            msg=f"expected rollback warning, got: {log_ctx.output}",
        )

    def test_apply_failure_after_forward_write_before_state_save_rolls_back(self) -> None:
        # R94.4 oracle BLOCK fix: try/except must cover the *entire* critical
        # section, not just the state-save call. Patch utc_now (called between
        # forward write and state save) to raise — file must be restored.
        import contextlib

        from aiwiki import app_compile as _app_compile

        with contextlib.ExitStack() as stack:
            self._stub_validation(stack)
            stack.enter_context(
                patch.object(_app_compile, "utc_now", side_effect=RuntimeError("clock boom"))
            )
            with self.assertRaises(RuntimeError) as ctx:
                cr_mod.apply_concept_rewrite(self.root, self.slug, note="trigger")

        self.assertIn("clock boom", str(ctx.exception))
        # File must be rolled back even though _save_concept_rewrite_proposals
        # was never called.
        self.assertEqual(
            self.concept_path.read_text(encoding="utf-8"),
            self.current_text,
        )


class RevertConceptRewriteTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.slug = "scaling"
        self.previous_text = "# Concept scaling\n\nOriginal synthesis content.\n"
        self.candidate_text = "# Concept scaling\n\nRewritten synthesis content.\n"

        # Seed proposal in *applied* state so revert_concept_rewrite proceeds.
        concept_dir = self.root / "wiki" / "concepts"
        concept_dir.mkdir(parents=True, exist_ok=True)
        self.concept_path = concept_dir / f"{self.slug}.md"
        self.concept_path.write_text(self.candidate_text, encoding="utf-8")
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": self.slug,
                        "title": f"Concept {self.slug}",
                        "status": "applied",
                        "candidate_markdown": self.candidate_text,
                        "previous_markdown": self.previous_text,
                        "target_path": f"wiki/concepts/{self.slug}.md",
                        "proposal_path": f"wiki/concepts/{self.slug}.proposal.md",
                        "source_signature": "sig-1",
                        "source_pages": ["wiki/sources/s1.md"],
                        "applied_at": "2026-01-01T00:00:00+00:00",
                        "last_applied_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_revert_state_save_failure_rolls_back_concept_file(self) -> None:
        import contextlib

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "concept_page_snapshot",
                    return_value={"content": self.candidate_text, "summary": ""},
                )
            )
            stack.enter_context(
                patch.object(cr_mod, "preserved_section", return_value="")
            )
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "_save_concept_rewrite_proposals",
                    side_effect=OSError("simulated disk full on revert"),
                )
            )
            with self.assertRaises(OSError) as ctx:
                cr_mod.revert_concept_rewrite(self.root, self.slug, note="trigger")

        self.assertIn("simulated disk full on revert", str(ctx.exception))
        # Concept file must be restored to candidate content (the applied state).
        self.assertEqual(
            self.concept_path.read_text(encoding="utf-8"),
            self.candidate_text,
        )

    def test_revert_failure_after_forward_write_before_state_save_rolls_back(self) -> None:
        # Mirror of apply-side window test: critical section covers everything
        # from forward write through state save. Patch rewrite_proposal_is_apply_ready
        # (called between forward write and state save) to raise.
        import contextlib

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "concept_page_snapshot",
                    return_value={"content": self.candidate_text, "summary": ""},
                )
            )
            stack.enter_context(
                patch.object(cr_mod, "preserved_section", return_value="")
            )
            stack.enter_context(
                patch.object(
                    cr_mod,
                    "rewrite_proposal_is_apply_ready",
                    side_effect=RuntimeError("apply-ready boom"),
                )
            )
            with self.assertRaises(RuntimeError) as ctx:
                cr_mod.revert_concept_rewrite(self.root, self.slug, note="trigger")

        self.assertIn("apply-ready boom", str(ctx.exception))
        # File rolled back to candidate (applied) bytes even though state save
        # was never reached.
        self.assertEqual(
            self.concept_path.read_text(encoding="utf-8"),
            self.candidate_text,
        )


if __name__ == "__main__":
    unittest.main()
