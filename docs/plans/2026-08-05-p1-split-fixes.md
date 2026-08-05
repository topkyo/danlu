# P1 分修清单（本轮无 P0）

> executing-plans inline。禁止 broad rewrite。

| # | 项 | Done when | Status |
|---|-----|-----------|--------|
| 1 | `_frontmatter_string_list` → 统一 `utils.markdown.frontmatter_string_list` | 4 拷贝删除；语义 = utils（list 仅 str 项） | [x] |
| 2 | `metrics_io._read_review_counts` 静默吞错 | 记 warning 日志；仍 best-effort 返回 () | [x] |
| 3 | alchemy promote receipt `revert_supported: true` | promote receipt + audit 为 true；unit 断言 | [x] |
| 4 | 文档：CHANGELOG + Unreleased 记 corpus/facade/hub；AGENTS + Architecture corpus 叙事；unit pin **160** | pins 一致 | [x] |
| 5 | 六命令零覆盖：run-nightly / watch / review-queue / alchemy demote / drop pdf / drop image | library 烟测入 `verify unit` | [x] |
| 6 | hub：`workflows_ask` 单 seam（writeback 簇） | 786→**334**；writeback **479**；`ask_question` 本轮只记债不拆 | [x] |

Out：Commercial 三阻断；Jest 环境性误败（npm ci）不改产品逻辑。

## 债

- `ask_question` 仍 ~295 行单函数 — 下一轮再评估是否单 seam。
