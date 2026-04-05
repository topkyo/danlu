---
title: "Raw Inbox"
kind: "dashboard"
---

# Raw Inbox

This is the intake surface for new material.

## What Belongs Here

- clipped web articles
- source notes emitted by `drop-url`, `drop-pdf`, `drop-image`, and `drop-repo`
- manual markdown notes that should become first-class sources

## Search

- Obsidian left search tab: `path:"raw/inbox"`
- CLI automation: `watch` or the installed `aiwiki-watch.service`

## Expectations

- notes here should preserve provenance in frontmatter
- attachments should live in `raw/assets/`, not beside the note
- the watcher will turn these into `wiki/sources/` pages
