"""Tests for aiwiki.trace — P1 / M8.2 evidence chain resolver."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki.trace import _classify, render_trace_text, resolve_trace

# --- fixture helpers --------------------------------------------------------


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _seed_minimal_vault(root: Path) -> None:
    """Populate raw + sources + judgment + decision + elixir + l3 proposal state."""
    _write(root / "raw" / "inbox" / "note.md", "# raw note\nhello world\n")
    _write(
        root / "wiki" / "sources" / "discovered-20260427-test.md",
        """---
id: discovered-20260427-test
title: Test Source
source_files:
  - raw/inbox/note.md
source_sha256: abcd1234
---

# Test Source
""",
    )
    _write(
        root / "wiki" / "judgments" / "judgment-20260427-test.md",
        """---
id: judgment-20260427-test
title: Test Judgment
status: candidate
confidence: medium
citations:
  - wiki/sources/discovered-20260427-test.md
source_files:
  - output/_candidates/reports/judgment-20260427-test.md
---

# Test Judgment
""",
    )
    _write(
        root / "wiki" / "decisions" / "decision-20260427-test.md",
        """---
id: decision-20260427-test
title: Test Decision
status: candidate
protocol: general
supports:
  - wiki/judgments/judgment-20260427-test.md
citations:
  - wiki/sources/discovered-20260427-test.md
---

# Test Decision
""",
    )
    _write(
        root / "output" / "_candidates" / "elixirs" / "elixir-test.md",
        """---
elixir_id: elixir-test
title: Test Elixir
status: candidate
derived_from:
  - judgment-20260427-test
evidence:
  - wiki/sources/discovered-20260427-test.md
---

# Test Elixir
""",
    )


def _seed_l3_proposal(root: Path) -> None:
    state_dir = root / ".aiwiki" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposals": [
            {
                "proposal_id": "proposal-test-001",
                "kind": "prompt_proposal",
                "state": "candidate",
                "target_file": "prompts/test.md",
                "evidence_refs": [
                    "wiki/judgments/judgment-20260427-test.md",
                    "wiki/sources/discovered-20260427-test.md",
                ],
                "proposal_path": "output/_proposals/prompt/proposal-test-001.md",
            }
        ],
        "version": 1,
    }
    (state_dir / "l3-proposals.json").write_text(json.dumps(payload), encoding="utf-8")


def _seed_receipt(root: Path) -> None:
    state_dir = root / ".aiwiki" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "action_id": "abc12345-action",
            "subject_id": "decision-20260427-test",
            "subject_kind": "decision",
            "operation": "promote",
            "ts": "2026-04-27T10:00:00Z",
        }
    )
    (state_dir / "execution-receipts.jsonl").write_text(line + "\n", encoding="utf-8")


# --- cases ------------------------------------------------------------------


def _case_classify_recognizes_known_prefixes() -> None:
    assert _classify("raw/inbox/x.md") == "raw"
    assert _classify("./raw/x.md") == "raw"
    assert _classify("wiki/sources/foo.md") == "source"
    assert _classify("discovered-20260101-foo") == "source"
    assert _classify("wiki/judgments/j.md") == "judgment"
    assert _classify("judgment-20260101-x") == "judgment"
    assert _classify("wiki/decisions/d.md") == "decision"
    assert _classify("decision-20260101-x") == "decision"
    assert _classify("elixir-test") == "elixir"
    assert _classify("output/_candidates/elixirs/elixir-test.md") == "elixir"
    assert _classify("proposal-test-001") == "proposal"
    assert _classify("output/_proposals/prompt/p.md") == "proposal"
    assert _classify("abc12345-uuid-action") == "receipt"
    assert _classify("") == "unknown"


def _case_resolve_raw_path_finds_referrer_when_down() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "raw/inbox/note.md", direction="down", max_depth=3)
        assert node.kind == "raw"
        assert not node.not_found
        kinds = [c.kind for c in node.children]
        assert "source" in kinds


def _case_resolve_source_walks_up_to_raw() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "discovered-20260427-test", direction="up", max_depth=3)
        assert node.kind == "source"
        assert node.label == "Test Source"
        # parent should be the raw file
        assert any(p.kind == "raw" for p in node.parents)


def _case_resolve_judgment_walks_up_to_source_and_raw() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "judgment-20260427-test", direction="up", max_depth=4)
        assert node.kind == "judgment"
        sources = [p for p in node.parents if p.kind == "source"]
        assert sources, "judgment should cite source"
        # source's parent should be raw
        raws = [p for p in sources[0].parents if p.kind == "raw"]
        assert raws, "source should walk up to raw"


def _case_resolve_decision_walks_up_through_judgment() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "decision-20260427-test", direction="up", max_depth=5)
        assert node.kind == "decision"
        judgment_parents = [p for p in node.parents if p.kind == "judgment"]
        assert judgment_parents, "decision.supports should produce judgment parent"


def _case_resolve_decision_down_is_empty() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "decision-20260427-test", direction="down", max_depth=3)
        # decisions are leaf-most in our chain (no auto-discovery downward yet)
        assert node.kind == "decision"
        assert node.children == []


def _case_resolve_elixir_walks_up_to_judgment_and_source() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "elixir-test", direction="up", max_depth=4)
        assert node.kind == "elixir"
        assert node.metadata.get("plane") == "candidate"
        kinds = {p.kind for p in node.parents}
        assert "judgment" in kinds
        assert "source" in kinds


def _case_resolve_l3_proposal_walks_up_to_evidence() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        _seed_l3_proposal(root)
        node = resolve_trace(root, "proposal-test-001", direction="up", max_depth=4)
        assert node.kind == "proposal"
        kinds = {p.kind for p in node.parents}
        assert "judgment" in kinds
        assert "source" in kinds


def _case_resolve_receipt_walks_up_to_subject() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        _seed_receipt(root)
        node = resolve_trace(root, "abc12345-action", direction="up", max_depth=3)
        assert node.kind == "receipt"
        assert node.metadata.get("subject_kind") == "decision"
        decisions = [p for p in node.parents if p.kind == "decision"]
        assert decisions


def _case_unknown_asset_marked_not_found() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "judgment-does-not-exist", direction="up")
        assert node.not_found is True


def _case_depth_limit_truncates() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "decision-20260427-test", direction="up", max_depth=1)
        # depth=1 → root only, no parents expanded beyond placeholder
        for parent in node.parents:
            # parents at depth-1 land on the next level; their grandparents must be empty
            assert parent.parents == [] or all(p.label == "(depth limit)" for p in parent.parents)


def _case_cycle_detection_marks_node() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        # build artificial cycle: judgment cites decision, decision supports judgment
        _write(
            root / "wiki" / "judgments" / "judgment-cycle.md",
            """---
id: judgment-cycle
title: Cycle J
citations:
  - wiki/decisions/decision-cycle.md
---
""",
        )
        _write(
            root / "wiki" / "decisions" / "decision-cycle.md",
            """---
id: decision-cycle
title: Cycle D
supports:
  - wiki/judgments/judgment-cycle.md
---
""",
        )
        node = resolve_trace(root, "judgment-cycle", direction="up", max_depth=5)
        # walk down the parent chain — should hit a cycle marker eventually
        seen_cycle = [False]

        def walk(n) -> None:
            if n.cycle:
                seen_cycle[0] = True
            for p in n.parents:
                walk(p)

        walk(node)
        assert seen_cycle[0], "cycle should be detected"


def _case_render_text_contains_kind_and_label() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "decision-20260427-test", direction="up", max_depth=3)
        text = render_trace_text(node, direction="up")
        assert "[decision]" in text
        assert "[judgment]" in text
        assert "[source]" in text
        assert "[raw]" in text
        assert "Test Decision" in text


def _case_to_dict_serializable_and_includes_metadata() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_minimal_vault(root)
        node = resolve_trace(root, "elixir-test", direction="up", max_depth=3)
        payload = node.to_dict()
        assert payload["kind"] == "elixir"
        assert payload["metadata"]["plane"] == "candidate"
        # JSON round-trip safe
        json.dumps(payload, ensure_ascii=False)


def _case_invalid_direction_raises() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            resolve_trace(root, "x", direction="sideways")
        except ValueError:
            return
        raise AssertionError("expected ValueError for invalid direction")


# --- runner -----------------------------------------------------------------


class TraceTests(unittest.TestCase):
    """Expose pure-function checks to unittest discover."""


for _name, _func in list(globals().items()):
    if _name.startswith("_case_") and callable(_func):
        setattr(TraceTests, f"test_{_name.removeprefix('_case_')}", staticmethod(_func))

del _name, _func
