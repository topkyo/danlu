---
title: "Alchemy Furnace"
kind: "architecture"
status: "active"
---

# Alchemy Furnace

`Alchemy Furnace` is the product architecture for turning `aiwiki` into a compounding knowledge system.

It is not a note-taking metaphor. It is a runtime model:

- raw material goes in
- the compiler turns it into structured knowledge
- agents query and produce artifacts
- high-value outputs flow back into the system
- lint and drift checks keep the system coherent over time

## Goal

Build a local-first system where:

- humans feed source material and exercise judgment
- `aiwiki` maintains the compiled knowledge layer
- Obsidian acts as the human-facing frontend
- machine-facing indexes and graph memory accelerate future agent work

The end state is not "more notes".
The end state is a durable knowledge operating system that compounds.

## Layer Model

### 1. Raw Sources

Purpose: the earliest locally controlled evidence layer plus ingest-generated capture artifacts.

Current paths:

- `raw/inbox/`
- `raw/assets/`
- `raw/normalized/`

Typical contents:

- articles, docs, and clipped webpages
- papers and PDFs
- screenshots, diagrams, and whiteboard photos
- repository snapshots
- logs, meeting notes, transcripts, and field notes
- ingest-generated notes such as extracted PDF text, OCR notes, and repository capture notes

Rules:

- preserve original assets when available
- capture notes must point back to their original file or URL
- `raw/` is earlier than `wiki/`, but not every file under it is a pristine original
- derived conclusions must never overwrite evidence or capture notes

### 2. Compiled Wiki

Purpose: the human-readable consensus layer maintained by `aiwiki`.

Current and planned paths:

- `wiki/sources/`
- `wiki/concepts/`
- `wiki/indexes/`
- `wiki/derived/`

Typical contents:

- source pages with summaries and citations
- concept pages spanning multiple sources
- decision pages and comparison pages
- indexes, logs, open questions, and operating dashboards
- filed-back reports worth preserving

Rules:

- this is the layer humans read first
- every important claim must preserve provenance
- concept and decision pages should synthesize, not just restate

### 3. Machine Memory

Purpose: the planned machine-readable acceleration layer for agents.

Planned paths:

- `.aiwiki/cache/`
- `.aiwiki/state/`
- future graph or retrieval indexes under `.aiwiki/` or `machine/`

Typical contents:

- chunk and citation indexes
- entity or concept graph
- retrieval cache
- temporal snapshots
- drift records
- graph exports or query accelerators

Rules:

- optimize for agent lookup, not human browsing
- keep it rebuildable from raw and compiled layers
- make drift between machine memory and wiki observable

This is the part most aligned with graph-oriented systems such as `graphify`.

### 4. Schema

Purpose: the furnace rules that tell agents how to ingest, compile, cite, lint, and write back.

Current runtime paths:

- `prompts/compile.md`
- `prompts/ask.md`
- `prompts/lint.md`

Planned runtime paths:

- `schema/`
- `policy/`

Typical contents:

- ingest rules
- citation and provenance rules
- conflict handling rules
- output templates
- taxonomy and naming conventions

Rules:

- schema is runtime policy, not just documentation
- when the system is corrected, the rule should be corrected here too

Boundary:

- `AGENTS.md` and `CLAUDE.md` are developer-facing project files
- they document repository and engineering rules
- they are not part of the `aiwiki` runtime architecture

### 5. Outputs

Purpose: consumable artifacts produced from the compiled knowledge layer.

Current paths:

- `output/reports/`
- `output/slides/`
- `output/figures/`
- `output/lint/`

Typical contents:

- reports
- slide outlines
- figure briefs
- lint reports
- future SOPs, decision memos, and review packs

Rules:

- outputs are not the end of the loop
- high-value outputs should be filed back into `wiki/derived/`

## Operating Loops

### Ingest Loop

1. Material enters through `drop-url`, `drop-pdf`, `drop-image`, `drop-repo`, or direct file drops.
2. `aiwiki` records provenance and stores local assets.
3. Deterministic compile creates source pages and indexes.

### Compile Loop

1. `compile` builds source, concept, and index layers.
2. `run-compile` upgrades placeholder summaries with LLM synthesis.
3. Changed raw material invalidates stale summaries and concept pages.

### Query Loop

1. `ask` or `run-ask` reads the compiled wiki first.
2. The system produces reports, slides, or figure briefs.
3. High-value results can be filed back with `file-back`.

### Lint Loop

1. `lint` checks missing pages, broken references, and obvious provenance gaps.
2. `run-lint` adds semantic review.
3. Future night jobs should also check drift between wiki and machine memory.

## Role Split

### Human

- chooses what to feed the furnace
- asks good questions
- reviews important judgments
- decides what is worth filing back

### aiwiki Runtime

- owns ingest, compile, ask, lint, watch, and provenance
- maintains the local artifact tree
- enforces source and derived separation

### LLM Backend

- upgrades summaries
- synthesizes concepts
- answers grounded questions
- performs semantic lint

### Obsidian

- serves as the frontend and IDE
- is where humans inspect raw, wiki, and output layers
- is not the compiler itself

## Current State

Implemented now:

- raw ingest paths and four `drop-*` entry points
- source, concept, and index compilation
- output generation and filed-back derived notes
- automation via `watch` and the user service
- Obsidian as the frontend

Next-stage extensions:

- stronger machine-memory layer
- graph indexing and drift tracking
- richer concept maintenance by the LLM
- nightly health checks and repair loops
- more explicit decision pages and judgment pages
- a dedicated runtime schema directory separate from developer governance files

## Architectural Invariants

- original evidence and capture notes must stay in `raw/`
- `wiki/derived/` must not silently rewrite `raw/`
- provenance must survive every compile and query step
- human-facing wiki and machine-facing memory should stay separate
- schema changes should capture learned corrections
- important outputs should compound back into the system

## Practical Reading Order

1. Start in `raw/` when you need evidence.
2. Move to `wiki/sources/` and `wiki/concepts/` for synthesis.
3. Use `wiki/indexes/` for navigation and status.
4. Use `output/` for task-specific artifacts.
5. Treat machine memory as supporting infrastructure, not the primary interface.

## Summary

`Alchemy Furnace` is the operating architecture behind `aiwiki`:

- `raw/` stores ore
- `wiki/` stores refined knowledge
- machine memory is the planned fast lookup layer
- schema stores the rules of refinement
- `output/` stores the usable artifacts

That is the product direction: not a smarter notebook, but a compounding knowledge operating system.
