---
title: "Wiki Hub"
kind: "dashboard"
---

# Wiki Hub

This area is the compiled knowledge layer.

## Main Areas

- `wiki/sources/`: summaries, provenance, and source-level backlinks
- `wiki/indexes/`: inventory and operational dashboards
- `wiki/derived/`: filed-back reports, slide decks, and notes worth keeping
- `wiki/decisions/` and `wiki/judgments/`: explicit decision and judgment layers under review
- `schema/`: runtime rules for ingest, citations, conflicts, and writeback
- `.aiwiki/state/`: machine-memory state and history for agents
- `.aiwiki/cache/`: graph export and rebuildable machine-side indexes

## Architecture

- [[wiki/indexes/Alchemy Furnace]]: runtime architecture for the `aiwiki` knowledge system
- [[schema/index]]: runtime schema used by compile, ask, and lint flows
- [[wiki/indexes/machine-memory]]: current machine-memory summary
- [[wiki/indexes/graph-health]]: current graph-health dashboard
- [[wiki/indexes/drift-report]]: latest structural drift report
- [[wiki/indexes/repair-backlog]]: latest nightly repair queue
- [[wiki/indexes/review-queue]]: current decision/judgment review queue

## Reading Order

1. Start with a source page in `wiki/sources/`.
2. Check `machine-memory`, `review-queue`, and `repair-backlog` when you need system state.
3. Follow links into related indexes or derived pages.
4. Use backlinks and outgoing links in the right sidebar to navigate context.

## Search

- Obsidian left search tab: `path:"wiki/sources" OR path:"wiki/indexes" OR path:"wiki/derived"`
