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
- `schema/`: runtime rules for ingest, citations, conflicts, and writeback

## Architecture

- [[wiki/indexes/Alchemy Furnace]]: runtime architecture for the `aiwiki` knowledge system
- [[schema/index]]: runtime schema used by compile, ask, and lint flows

## Reading Order

1. Start with a source page in `wiki/sources/`.
2. Follow links into related indexes or derived pages.
3. Use backlinks and outgoing links in the right sidebar to navigate context.

## Search

- Obsidian left search tab: `path:"wiki/sources" OR path:"wiki/indexes" OR path:"wiki/derived"`
