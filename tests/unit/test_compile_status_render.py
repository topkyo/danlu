from __future__ import annotations

from aiwiki.app_surfaces import render_compile_status as legacy_render_compile_status
from aiwiki.render.compile_status import compile_phase_lines, render_compile_status


def test_compile_phase_lines_renders_known_details_and_empty_state() -> None:
    assert compile_phase_lines([]) == ["- 当前还没有 compile phase summary。"]
    assert compile_phase_lines(
        [
            {
                "name": "sources",
                "label": "Source pages",
                "mode": "incremental",
                "status": "completed",
                "details": {"dirty_sources": 2, "ignored": 99},
            }
        ]
    ) == ["- `sources` `Source pages` [incremental/completed] | dirty=2"]


def test_render_compile_status_includes_dirty_links_and_overflow() -> None:
    entries = [{"id": f"s{i}", "title": f"Source {i}"} for i in range(10)]
    concepts = [{"slug": f"c{i}", "title": f"Concept {i}"} for i in range(10)]
    rendered = render_compile_status(
        entries,
        concepts,
        decisions=[{"status": "proposed", "citation_drift": "true"}],
        judgments=[{"status": "tentative"}],
        protocol_state={"active_protocol": "product"},
        compiled_at="2026-05-26T00:00:00Z",
        compile_state={
            "phase_summary": [{"name": "sources", "details": {"dirty_sources": 10}}],
            "dirty_source_ids": [f"s{i}" for i in range(10)],
            "dirty_concept_slugs": [f"c{i}" for i in range(10)],
            "dirty_index_artifacts": [f"output/a{i}.md" for i in range(13)],
            "machine_memory_core_reused": True,
        },
    )

    assert "# 编译状态" in rendered
    assert "当前 active protocol：`product`" in rendered
    assert "- `sources` `sources` [full/completed] | dirty=10" in rendered
    assert "[Source 0](../sources/s0.md)" in rendered
    assert "- 其余 dirty source：`2`" in rendered
    assert "[Concept 0](../concepts/c0.md)" in rendered
    assert "- 其余 dirty concept：`2`" in rendered
    assert "- 其余 dirty artifact：`1`" in rendered
    assert "- Machine-memory core reused：`True`" in rendered


def test_app_surfaces_reexports_compile_status_renderer_for_compatibility() -> None:
    assert legacy_render_compile_status is render_compile_status
