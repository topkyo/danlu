# Freeform Ask Markdown Only

**Date:** 2026-07-18  
**Status:** Approved (chat: plan B + no compat / hard delete)

## Goal

Ask 只产出一篇自由 Markdown 报告（`output/reports/*.md`）。去掉决策级六段硬骨架与 Ask 多 format 分叉，让 LLM（默认 DeepSeek V4 Pro）按问题自由组织内容。不做旧 format 兼容、不做 alias、不做 silent fallback。

## Constraints

- 技术栈与分层不变：`raw/ → wiki/ → output/`；stdlib-first。
- Shell/CLI 默认 LLM 路由不变：`opencode-api/deepseek-v4-pro`（本轮不改 backend/model）。
- **硬删除、零兼容**：旧 Ask `--format` 值不得 alias 到 report，不得降级成功。
- 不误伤：`drop note` 投料、审阅/apply 的 `note` 备注字段、judgment 派生 packs（`.aiwiki/derived/packs/decision-memos` 等）。
- 不改图谱语义、不改 Obsidian `userIgnoreFilters`、不对 dogfood 历史报告做 bulk rewrite。

## Design

### Architecture

Ask 产物契约收敛为单一路径：

1. CLI / Product Shell / background submit 一律创建 `output/reports/<id>.md`。
2. `format` frontmatter 固定为 `report`（或省略后由 writer 写入 `report`）；语义 =「一篇可审阅 md 回答」。
3. LLM 填充时不再强制 H2 章节集合；prompt 仅软指引。
4. 校验只保留最小正确性：有 frontmatter、正文非空、无未替换的 `_LLM:` 占位（若 skeleton 仍含占位则必须清掉；自由正文路径默认不注入 `_LLM:`）。

### Components

| 区域 | 变更 |
|------|------|
| `src/aiwiki/default_prompts/ask.md` | 删除六段 Required Sections；改为自由 md 指引（直接答、尽量引 `wiki/sources/*.md`、标不确定）。删除 `format: note` 专段。 |
| `src/aiwiki/app_queries.py` `render_report` | 去掉六段 `_LLM:` 骨架；保留标题 + 可选参考（优先来源/概念/协议偏置）。 |
| `src/aiwiki/runner/prompts.py` | **删除** `_validate_report_sections` 及 bullet/引用硬校验；`_validate_output_markdown` 收缩为 frontmatter + 非空 + 无残留 `_LLM:`（若适用）。删除对 note/slides/… 的分支特判（若有）。 |
| `src/aiwiki/execution/ask.py` | Ask 仅保留 `report` 分支；**删除** `decision-memo` / `sop` / `note` / `slides` / `figure` 分支与 `OUTPUT_FORMAT_FILENAME_SUFFIXES` 中对应项。未知 format → `ValueError`（显式失败）。 |
| `src/aiwiki/cli/parsers.py` | `ask` / `run-ask` / `run-ask-submit` 的 `--format`：**仅** `report`（或删除该 flag，缺省永远 report）。传入旧值 → argparse 拒绝（非 0）。**删除** `--direct`（note 专用轻路径）。 |
| `src/aiwiki/runner/workflows_ask.py` | 删除 note/direct 专用路径（`_is_simple_direct_ask` / `_is_material_hint_note_ask` 等依赖 `format==note` 的逻辑）；统一走 report 填充管线。 |
| Product Shell | Ask 不再传/展示非 report format；清理 format 选择 UI（若有）。**顺带修复** Today 卡断线方法：`goToReport` / `viewReviewTodayEntry` / `snoozeTodayEntry`（实现为 `openWorkspacePath` / review center / `runTodaySnoozeCommand`，或恢复 `todayFeedActions` 接线）。 |
| 渲染 helper | 仅被旧 Ask format 使用的 `render_note_answer` / `render_slides` / `render_figure_brief` / `render_decision_memo_query` / `render_sop_query`：**删除**（若仍被非 Ask 路径引用则保留该路径，但 Ask 不得再调用）。 |
| 文档 | Active 文档中 Ask 多 format / 六段骨架说明改为「自由 md 报告」；`PROGRESS.md` 记一笔。 |

### Data flow

```
question → ask/run-ask/run-ask-submit
        → render_report (thin md seed, no six-section placeholders)
        → LLM fill (freeform md)
        → minimal validate (frontmatter + non-empty + no _LLM: leftovers)
        → output/reports/*.md
```

旧 CLI：`--format note|slides|figure|decision-memo|sop` → **立即失败**（argparse choices 或显式错误），不得写文件、不得改写为 report。

### Error handling

- 未知/已删 format：CLI 非 0 + 清晰错误（列出唯一合法值 `report`）。
- LLM 返回缺 frontmatter / 空正文 / 残留 `_LLM:`：失败，不写成功 receipt 伪装完成。
- 不引入 deterministic 占位成功内容。

### Testing

- 更新 / 新增 acceptance 或静态断言：六段校验已不存在；`--format note`（及 slides 等）失败；`--format report` 或默认成功路径仍产出 `output/reports/*.md`。
- Product Shell：打开报告 / 审阅按钮可调用到真实方法（Jest 覆盖）。
- `bash scripts/verify_target_rules.sh` 建议 target，再跑对应 `verify.sh`；至少含触及的 `python-static` / `product-shell-static` / 相关 acceptance。

## Out of scope

- 修改 LLM backend / model / timeout 默认策略（除删除 note `--direct` 路径外）。
- 删除 vault 历史 `output/slides` / `output/figures` 文件或 dogfood 269 份旧六段报告。
- 改 machine-memory 图节点模型、Obsidian ignoreFilters、campaign 降噪归档。
- 删除 judgment 派生 decision-memo packs 或 `drop note` 投料。

## Open questions

(none)
