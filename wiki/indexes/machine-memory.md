# Machine Memory

- Last compiled at: `2026-04-07T09:16:58+00:00`
- Runtime state file: `.aiwiki/state/machine-memory.json`
- Graph export: `.aiwiki/cache/machine-memory-graph.json`
- Drift report: `wiki/indexes/drift-report.md`
- Source nodes: `0`
- Concept nodes: `0`
- Source-to-concept edges: `0`
- Concept-to-concept edges: `0`
- Indexed terms: `0`
- Machine digest: `93afc12caa746000fbf7659e7fddef3c61e3666e45e1124367379e1d2d7f5fad`
- Graph digest: `f5f601586348141cb59f4afc4fab6c1a56cf15d36b9b45c2bfbfcc92b9154bcc`

## Graph Health
- Connected components: `0`
- Isolated sources: `0`
- Singleton concepts: `0`
- Bridge concepts: `0`
- Overloaded concepts: `0`
- Indexed components: `0`

## Human Judgment Layers
- Decision index: `wiki/indexes/decisions.md`
- Judgment index: `wiki/indexes/judgments.md`
- Review queue: `wiki/indexes/review-queue.md`

## Drift Summary
- Missing raw files: `0`
- Missing source pages: `0`
- Missing concept pages: `0`
- Sources without concepts: `0`

## Links
- [Graph Health](./graph-health.md)
- [Drift Report](./drift-report.md)
- [Repair Backlog](./repair-backlog.md)

## Query Acceleration
- `ask` and `run-ask` use the machine-memory term index as a first-pass query planner.
- Source-to-concept and concept-to-concept edges expand related candidates before prompt assembly.
- Query planning also extracts shortest graph routes and touched components for deeper retrieval.
- The graph export is for agent/tool consumption, not for direct human editing.

## Top Concepts
- No concept nodes compiled yet.

## Runtime Schema
- [Schema Index](../../schema/index.md)
- [Citation Rules](../../schema/citations.md)
- [Conflict Rules](../../schema/conflicts.md)
- [Review Rules](../../schema/review.md)
