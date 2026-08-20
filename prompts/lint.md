# Lint Prompt

Use this prompt when an external LLM performs semantic maintenance on the wiki.

## Objective

Inspect the wiki for contradictions, missing links, unsupported claims, and worthwhile new concept pages.

## Checklist

1. Identify conflicting statements across `wiki/sources/` and `wiki/derived/`.
2. Flag derived pages that lack clear source-page references.
3. Suggest missing concept pages or backlinks.
4. Separate confirmed issues from hypotheses that need more evidence.

## Output

Write findings into `.aiwiki/lint/` and cite the affected file paths directly.
Return markdown only, with no surrounding commentary or code fences.
