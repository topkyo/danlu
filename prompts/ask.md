# Ask Prompt

Use this prompt when an external LLM fills a query artifact under `output/`.

## Objective

Answer the query using the ranked source pages and reference hints in the artifact. Write a reviewable judgment in free-form Markdown—not a rigid template.

## Writing guidance

- Answer the question directly in clear prose. Use headings, lists, or short sections only when they help readability.
- Prefer citing `wiki/sources/*.md` paths for non-trivial claims; inline citations are fine.
- Mark uncertainty when the source set is thin or conflicting.
- Do not cite `wiki/derived/` as if it were raw evidence.
- Keep provenance frontmatter keys (`kind`, `format`, `query`, `_id`, `protocol`, `created_at`, `generated_by`, refs). Do not keep pending/placeholder markers (`llm_status: pending`, `artifact_quality: placeholder`, `_LLM:`).
- When materials are attached under「本次投喂材料」, answer those files directly. Do not write soft-fail hedges like「无法明确识别这个文件」.
- Optional trailing `## 参考` blocks (protocol bias, ranked sources, concepts, machine-memory hints) are supplementary context. You may keep, prune, or rewrite them; do not treat them as required output sections.

## Deliverable

Replace the whole artifact with the final answer markdown (frontmatter + body).
Return the full replacement artifact only, with no code fences or side commentary.
