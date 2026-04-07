---
title: "aiwiki Home"
kind: "dashboard"
---

# aiwiki Home

This vault treats Obsidian as the frontend for `aiwiki`.

`aiwiki` owns ingest, compile, ask, lint, provenance, and automation.
Obsidian is the place where you browse the local artifact tree and inspect what the pipeline produced.

## Quick Links

- [[wiki/indexes/Raw Inbox]]
- [[wiki/indexes/Wiki Hub]]
- [[wiki/indexes/Alchemy Furnace]]
- [[schema/index]]
- [[wiki/indexes/Outputs]]
- [[wiki/indexes/Search Presets]]

## Folder Map

- `raw/inbox/`: inbound source notes and direct drops
- `raw/assets/`: local PDFs, images, and page assets captured during ingest
- `schema/`: runtime ingest, citation, conflict, and writeback rules
- `wiki/sources/`: one compiled source page per raw item
- `wiki/indexes/`: dashboards, compile indexes, and operating notes
- `wiki/derived/`: filed-back reports and other derived markdown
- `output/`: reports, slides, figures, and lint artifacts

## Operating Model

1. Drop material into `raw/inbox/` or use one of the `drop-*` entry points.
2. Let the watcher compile source pages and refresh lint outputs.
3. Read `wiki/sources/` and `output/` in Obsidian.
4. File back high-value outputs into `wiki/derived/`.

## Notes

- New notes created from Obsidian will default to `raw/inbox/`.
- New attachments created from Obsidian will default to `raw/assets/`.
- The left sidebar search tabs are scoped to `raw`, `wiki`, and `output`.
