# Ask Prompt

Use this prompt when an external LLM fills a query artifact under `output/`.

## Objective

Answer the query using the ranked source pages in the artifact.

## Rules

- Cite `wiki/sources/*.md` paths explicitly for every non-trivial claim.
- Mark uncertainty when the source set is thin or conflicting.
- Do not cite `wiki/derived/` as if it were raw evidence.
- If the artifact is a slide deck or figure brief, keep citations close to each slide or caption.

## Deliverable

Fill the generated markdown artifact in place and keep its frontmatter intact.
Return the full replacement artifact only, with no code fences or side commentary.
