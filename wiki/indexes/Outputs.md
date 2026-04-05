---
title: "Outputs"
kind: "dashboard"
---

# Outputs

`output/` is where transient query artifacts land before you decide whether they should be filed back.

## Output Areas

- `output/reports/`: markdown reports
- `output/slides/`: Marp slide decks
- `output/figures/`: figure briefs and image-oriented outputs
- `output/lint/`: deterministic and semantic lint reports

## Review Pattern

1. Read the newest output.
2. Check whether the citations point back to `wiki/sources/`.
3. If the output is durable, move it into `wiki/derived/` with `file-back`.

## Search

- Obsidian left search tab: `path:"output/reports" OR path:"output/slides" OR path:"output/figures" OR path:"output/lint"`
