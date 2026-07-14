from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory.builder import build_machine_memory


def test_app_memory_builder_facade_matches_owner_and_builds_snapshot(tmp_path):
    (tmp_path / "raw" / "inbox").mkdir(parents=True)
    (tmp_path / "wiki" / "sources").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "raw" / "inbox" / "source-a.md").write_text("Alpha source", encoding="utf-8")
    (tmp_path / "wiki" / "sources" / "source-a.md").write_text("# Source A\n", encoding="utf-8")
    (tmp_path / "wiki" / "concepts" / "alpha.md").write_text(
        "\n".join(
            [
                "---",
                "confidence: high",
                "hardness: hard",
                "causal_links:",
                '  - "beta|enables|Alpha enables beta"',
                "---",
                "# Alpha",
                "",
            ]
        ),
        encoding="utf-8",
    )

    entries = [
        {
            "id": "source-a",
            "title": "Source A",
            "source_type": "note",
            "kind": "text",
            "stored_path": "raw/inbox/source-a.md",
            "original_path": "raw/inbox/source-a.md",
            "sha256": "sha-a",
        }
    ]
    concepts = [
        {
            "slug": "alpha",
            "title": "Alpha",
            "entry_ids": ["source-a"],
            "related_slugs": ["beta"],
            "source_signature": "sig-alpha",
        }
    ]
    previews = {"source-a": "Alpha preview"}
    entry_terms = {"source-a": ["alpha"]}

    owner = build_machine_memory(
        tmp_path,
        entries,
        concepts,
        previews,
        entry_terms,
        "2026-05-25T00:00:00+00:00",
    )
    facade = app_memory.build_machine_memory(
        tmp_path,
        entries,
        concepts,
        previews,
        entry_terms,
        "2026-05-25T00:00:00+00:00",
    )

    assert facade == owner
    assert owner["source_nodes"][0]["id"] == "source-a"
    assert owner["concept_nodes"][0]["slug"] == "alpha"
    assert owner["concept_nodes"][0]["confidence"] == "high"
    assert owner["concept_nodes"][0]["hardness"] == "hard"
    assert owner["edges"]["source_to_concept"] == [{"source_id": "source-a", "concept_slug": "alpha"}]
    assert owner["edges"]["concept_to_concept"] == [{"from": "alpha", "to": "beta"}]
    assert owner["edges"]["concept_causal"] == [
        {
            "from": "alpha",
            "to": "beta",
            "relation": "enables",
            "evidence": "Alpha enables beta",
        }
    ]
    assert owner["term_index"]["alpha"]["source_ids"] == ["source-a"]
    assert owner["term_index"]["alpha"]["concept_slugs"] == ["alpha"]
    assert owner["drift"] == {
        "missing_raw_files": [],
        "missing_source_pages": [],
        "missing_concept_pages": [],
        "sources_without_concepts": [],
    }
