---
title: "Search Presets"
kind: "reference"
---

# Search Presets

These queries match the preloaded search tabs in the Obsidian workspace.

## Raw Intake

```text
path:"raw/inbox"
```

## Compiled Wiki

```text
path:"wiki/sources" OR path:"wiki/indexes" OR path:"wiki/derived"
```

## Outputs

```text
path:"output/reports" OR path:"output/slides" OR path:"output/figures" OR path:"output/lint"
```

## Unresolved Summaries

```text
"Pending LLM summary." path:"wiki/sources"
```

## Missing Provenance

```text
"Missing source page:" path:"output/lint"
```
