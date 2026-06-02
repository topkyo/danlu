# Ask Prompt

Use this prompt when an external LLM fills a query artifact under `output/`.

## Objective

Answer the query using the ranked source pages in the artifact, producing a reviewable judgment asset rather than a research draft.

When the artifact's frontmatter shows `format: report`, treat it as a **decision-grade report** and follow the required-section skeleton in the section below. Other formats (`slides`, `figure`, `decision-memo`, `sop`, `note`) keep their existing per-format conventions and are not subject to the 6-section requirement.

When the artifact's frontmatter shows `format: note`, treat it as a **note-grade answer**: 2–5 段自然语言直接回答问题，保留 `## 优先来源` / `## 优先概念` 两个 H2 区块和最末的协议提示行。不要强行套用 report 的六段骨架；仍需对所有非琐碎断言显式引用 `wiki/sources/*.md` 路径。

## General Rules

- Cite `wiki/sources/*.md` paths explicitly for every non-trivial claim.
- Mark uncertainty when the source set is thin or conflicting.
- Do not cite `wiki/derived/` as if it were raw evidence.
- If the artifact is a slide deck or figure brief, keep citations close to each slide or caption.

## Required Sections (format: report)

When the artifact's frontmatter shows `format: report`, the filled markdown MUST contain the following 6 H2 sections, **in this exact order**, using the exact Chinese headings shown:

Before writing, choose the report depth from the actual question and supplied material, without changing the file type:

- Use a short report when the user asks a narrow/direct question or the evidence set is thin: keep `## 结论` brief, use the minimum required bullets, and avoid padding.
- Use a long report when the user asks for deep analysis, comparison, synthesis, planning, or multiple source materials: expand the evidence, uncertainty, actions, and observation signals enough for review.
- Do not create separate `note` outputs or alternate filenames; both depths are Markdown reports under the same report contract.

1. `## 结论` — One-sentence direct answer to the query (max 3 lines). State your judgment clearly; do not hedge into a non-answer.
2. `## 关键证据` — At least 3 bullets. Each bullet must include at least one `wiki/sources/*.md` citation.
3. `## 反证与不确定性` — At least 1 bullet. If the evidence set is genuinely strong, explicitly state so (e.g. "未发现明显反证；证据集合覆盖 N 份来源，覆盖面 …") rather than fabricating a counter-point.
4. `## 行动建议` — At least 1 actionable next step the user can take.
5. `## 下次观察信号` — At least 1 trigger condition that would warrant revisiting this conclusion ("当 X 出现 / Y 指标变化时复审").
6. `## 引用` — A deduplicated list of all `wiki/sources/*.md` paths cited in the body, in order of first appearance.

The skeleton produced by `aiwiki ask` includes these headings with placeholder hints (`_LLM: 请在此填入 …`). Replace each placeholder hint line with substantive content; keep the H2 headings exactly as shown.

A `## 参考` section follows `## 引用` and provides ranked source / concept hints plus the active protocol's output guidance. It is supplementary context for your writing; you may keep, prune, or reformat its content as useful, but do **not** rename it.

## Deliverable

Fill the generated markdown artifact in place and keep its frontmatter intact.
Return the full replacement artifact only, with no code fences or side commentary.
