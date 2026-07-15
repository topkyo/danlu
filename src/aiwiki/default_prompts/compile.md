# Compile Prompt

Use this prompt when an external LLM enriches the local wiki.

## Objective

Read the current `raw/` and `wiki/` trees, then upgrade the compiled wiki without violating provenance.

## Rules

- `raw/` is the fact source. Do not rewrite or summarize facts back into `raw/`.
- `wiki/sources/` stays source-centric. Keep one page per ingested item.
- `wiki/derived/` is for filed-back analyses, not primary facts.
- Preserve or improve explicit citations to `wiki/sources/*.md`.
- If evidence is missing, leave a TODO instead of inventing facts.

## Expected Work

1. Replace placeholder summaries in `wiki/sources/`.
2. Create or update `wiki/concepts/*.md` pages when multiple sources justify them.
3. Add backlinks between concept pages, source pages, and derived pages.
4. Keep `wiki/indexes/` aligned with the current state.
5. Return the full replacement markdown for the target file, not commentary.
