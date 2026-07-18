# Ask Prompt

Use this prompt when an external LLM fills a query artifact under `output/`.

## Objective

Answer the query using the ranked source pages and reference hints in the artifact. Write a reviewable judgment in free-form Markdown—not a rigid template.

## Writing guidance

- Answer the question directly in clear prose. Use headings, lists, or short sections only when they help readability.
- Prefer citing `wiki/sources/*.md` paths for non-trivial claims; inline citations are fine.
- Mark uncertainty when the source set is thin or conflicting.
- Do not cite `wiki/derived/` as if it were raw evidence.
- Keep the artifact frontmatter intact.
- Optional trailing `## 参考` blocks (protocol bias, ranked sources, concepts, machine-memory hints) are supplementary context. You may keep, prune, or rewrite them; do not treat them as required output sections.

## Deliverable

Fill the generated markdown artifact in place and keep its frontmatter intact.
Return the full replacement artifact only, with no code fences or side commentary.
