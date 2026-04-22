#!/usr/bin/env python3
"""Local-only benchmark for machine-memory query cache paths."""

from __future__ import annotations

import argparse
import json
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
from aiwiki.app_memory import build_machine_memory_query
from aiwiki.app_state import (
    load_archive_candidates_state,
    load_cache_status,
    load_machine_memory,
    load_material_routing_state,
    load_material_state,
)
from aiwiki.app_protocol import ensure_layout


def _seed_fixture(root: Path, *, count: int) -> None:
    topics = [
        ("Transformer Scaling", "Transformers benefit from scale. Inference cost rises with larger deployments."),
        ("Latency Benchmark", "Benchmark runs show latency regressions after architecture changes."),
        ("Cache Rebuild Notes", "SQLite cache rebuilds should remain observable and reviewable."),
        ("Routing Signals", "Protocol-aware routing can shift source priority across research workflows."),
    ]
    for index in range(count):
        title, body = topics[index % len(topics)]
        source = root / f"benchmark-source-{index:03d}.md"
        source.write_text(f"# {title} {index}\n\n{body}\n", encoding="utf-8")
        ingest_source(root, str(source), title=f"{title} {index}")


def _timed_query(root: Path, question: str, *, no_cache: bool) -> tuple[float, dict[str, object]]:
    memory = load_machine_memory(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    started = time.perf_counter()
    result = build_machine_memory_query(
        memory,
        question,
        root=root,
        protocol="general",
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
        no_cache=no_cache,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, result


def run_benchmark(*, fixture_count: int, question: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="aiwiki-cache-benchmark-") as tempdir:
        root = Path(tempdir)
        ensure_layout(root)
        _seed_fixture(root, count=fixture_count)
        compile_wiki(root)

        cold_ms, cold_result = _timed_query(root, question, no_cache=False)
        warm_ms, warm_result = _timed_query(root, question, no_cache=False)
        bypass_ms, bypass_result = _timed_query(root, question, no_cache=True)
        cache_status = load_cache_status(root)

        return {
            "fixture_count": fixture_count,
            "question": question,
            "timings_ms": {
                "cold_cache": round(cold_ms, 3),
                "warm_cache": round(warm_ms, 3),
                "no_cache": round(bypass_ms, 3),
            },
            "query_shapes": {
                "cold_cache_sources": len(cold_result.get("ranked_source_ids", []) or []),
                "warm_cache_sources": len(warm_result.get("ranked_source_ids", []) or []),
                "no_cache_sources": len(bypass_result.get("ranked_source_ids", []) or []),
                "cold_cache_routes": len(cold_result.get("query_routes", []) or []),
                "warm_cache_routes": len(warm_result.get("query_routes", []) or []),
                "no_cache_routes": len(bypass_result.get("query_routes", []) or []),
            },
            "cache_status": {
                "enabled": bool(cache_status.get("enabled", False)),
                "schema_version": int(cache_status.get("schema_version", 0) or 0),
                "row_count_total": int(sum(int(value or 0) for value in cache_status.get("row_counts", {}).values())),
                "stats": dict(cache_status.get("stats", {})),
                "last_query": dict(cache_status.get("last_query", {})),
                "last_sync": dict(cache_status.get("last_sync", {})),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark aiwiki SQLite cache query paths.")
    parser.add_argument("--fixture-count", type=int, default=24, help="Number of synthetic sources to ingest.")
    parser.add_argument(
        "--question",
        default="Compare cache rebuild observability and latency benchmark signals",
        help="Question used for cache/no-cache query timing.",
    )
    args = parser.parse_args()
    result = run_benchmark(fixture_count=args.fixture_count, question=args.question)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
