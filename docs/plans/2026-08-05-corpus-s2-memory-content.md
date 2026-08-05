# corpus S2：断 memory→content

> **For agentic workers:** executing-plans。禁止 broad rewrite。

**Goal:** 窄 snapshot / 纯解析 / link state 下沉 `aiwiki.corpus`，使 `memory ↛ content`。  
**Depends on:** S1（`content ↛ memory` + paths/scoring/ranks）已落地。

## Done

- [x] `corpus/{parse,sections,snapshots,link_state}.py`
- [x] content 薄转发；`page_sections` 与 `corpus.sections` 同源
- [x] memory 全改引 corpus；`action_core` 校验用 `load_manifest`；nightly → `corpus.snapshots`
- [x] `docs_consistency` + library AST：`memory ↛ content`
- [x] Verify：python-static / unit / acceptance / llm / scripts

## 验证口径

```bash
rg 'from \.\.content|from aiwiki\.content' src/aiwiki/memory   # empty
rg 'from \.\.memory|from aiwiki\.memory' src/aiwiki/content   # empty
rg 'from \.\.(content|memory)|from aiwiki\.(content|memory)' src/aiwiki/corpus  # empty
```
