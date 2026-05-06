#!/usr/bin/env python3
"""Local-only benchmark for compile_wiki end-to-end timing."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aiwiki.app_compile import compile_wiki
from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout


def _seed_fixture(root: Path, *, count: int) -> None:
    topics = [
        ("Compile Pipeline", "Compile runs should preserve provenance across generated wiki pages."),
        ("Research Notes", "Research sources mention benchmarks, architecture tradeoffs, and follow-up questions."),
        ("Decision Context", "Decision records need clear signals, risks, invalidation, and review windows."),
        ("Machine Memory", "Machine memory should summarize durable concepts without overwriting source pages."),
    ]
    for index in range(count):
        title, body = topics[index % len(topics)]
        source = root / f"compile-benchmark-source-{index:03d}.md"
        source.write_text(
            f"# {title} {index}\n\n{body}\n\nSynthetic fixture paragraph {index}.\n",
            encoding="utf-8",
        )
        ingest_source(root, str(source), title=f"{title} {index}")


def _timed_compile(root: Path) -> float:
    started = time.perf_counter()
    compile_wiki(root)
    return (time.perf_counter() - started) * 1000.0


def _summary(values: list[float]) -> dict[str, object]:
    rounded = [round(value, 3) for value in values]
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "max": round(max(values), 3),
        "all": rounded,
    }


def _vault_metrics(root: Path) -> dict[str, object]:
    state_dir = root / ".aiwiki" / "state"
    machine_memory_state = state_dir / "machine-memory.json"
    machine_memory_state_bytes = machine_memory_state.stat().st_size if machine_memory_state.exists() else 0

    cache_dir = root / ".aiwiki" / "cache"
    machine_memory_graph = cache_dir / "machine-memory-graph.json"
    machine_memory_graph_bytes = machine_memory_graph.stat().st_size if machine_memory_graph.exists() else 0

    cache_status_path = state_dir / "cache-status.json"
    cache_row_count_total = 0
    cache_status_enabled = False
    if cache_status_path.exists():
        try:
            cache_status = json.loads(cache_status_path.read_text(encoding="utf-8"))
            cache_status_enabled = bool(cache_status.get("enabled", False))
            row_counts = cache_status.get("row_counts", {}) or {}
            cache_row_count_total = sum(int(value or 0) for value in row_counts.values())
        except (json.JSONDecodeError, OSError):
            pass

    compile_state_path = state_dir / "compile-state.json"
    phase_summary = {}
    if compile_state_path.exists():
        try:
            compile_state = json.loads(compile_state_path.read_text(encoding="utf-8"))
            phase_summary_raw = compile_state.get("phase_summary", {}) or {}
            if isinstance(phase_summary_raw, dict):
                phase_summary = {
                    key: value
                    for key, value in phase_summary_raw.items()
                    if isinstance(value, (int, float, str, bool))
                }
            elif isinstance(phase_summary_raw, list):
                phase_summary = {"phase_count": len(phase_summary_raw)}
                for phase in phase_summary_raw:
                    if not isinstance(phase, dict):
                        continue
                    phase_name = str(phase.get("name") or "phase")
                    details = phase.get("details", {}) or {}
                    if not isinstance(details, dict):
                        continue
                    for key, value in details.items():
                        if isinstance(value, (int, float, str, bool)):
                            phase_summary[f"{phase_name}_{key}"] = value
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "source_pages_count": len(list((root / "wiki" / "sources").glob("*.md"))),
        "concept_pages_count": len(list((root / "wiki" / "concepts").glob("*.md"))),
        "machine_memory_state_bytes": machine_memory_state_bytes,
        "machine_memory_graph_bytes": machine_memory_graph_bytes,
        "cache_status_enabled": cache_status_enabled,
        "cache_row_count_total": cache_row_count_total,
        "phase_summary": phase_summary,
    }


def run_benchmark(*, fixture_count: int, iterations: int) -> dict[str, object]:
    cold_timings: list[float] = []
    warm_timings: list[float] = []
    vault_metrics: dict[str, object] | None = None

    for iteration in range(iterations):
        with tempfile.TemporaryDirectory(prefix="aiwiki-compile-benchmark-") as tempdir:
            root = Path(tempdir)
            ensure_layout(root)
            _seed_fixture(root, count=fixture_count)

            cold_timings.append(_timed_compile(root))
            if iteration == 0:
                vault_metrics = _vault_metrics(root)
            warm_timings.append(_timed_compile(root))

    return {
        "fixture_count": fixture_count,
        "iterations": iterations,
        "timings_ms": {
            "cold": _summary(cold_timings),
            "warm": _summary(warm_timings),
        },
        "vault_metrics": vault_metrics or {
            "source_pages_count": 0,
            "concept_pages_count": 0,
            "machine_memory_state_bytes": 0,
            "machine_memory_graph_bytes": 0,
            "cache_status_enabled": False,
            "cache_row_count_total": 0,
            "phase_summary": {},
        },
        "environment": {
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "platform": platform.platform(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark aiwiki compile_wiki end-to-end timing.")
    parser.add_argument("--fixture-count", type=int, default=50, help="Number of synthetic sources to ingest.")
    parser.add_argument("--iterations", type=int, default=3, help="Number of fresh-vault benchmark iterations.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output (default).")
    args = parser.parse_args()

    if args.fixture_count < 0:
        parser.error("--fixture-count must be >= 0")
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")

    result = run_benchmark(fixture_count=args.fixture_count, iterations=args.iterations)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
