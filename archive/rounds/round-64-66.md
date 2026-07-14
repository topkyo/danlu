# Round 64-66 — UX Earnest 收口

status: 完成
commit: 

Round 64-66 — UX Earnest 收口 — 完成
- **目的**: 以"用户只关心报告和金丹"为红线，收口文件命名、投料体验、面板复杂度、治理自动化和图谱锚点
- **方向 SoT**: 用户在线指令
- **R64 — 文件命名去时间戳 + 投料修复**:
  - `drop.py:_timestamped_stem()` 去除 UTC 时间前缀，中文标题 fallback 到 sha256 hash
  - `content/io.py` manifest entry_id 去 `discovered-<timestamp>-` 前缀，改为 `source-<slug>`
  - `modals.js` DropFileModal/DropImageModal 新增 `setInitialSource()` 方法
  - `render_input.js` DropZone 拖放时自动预填 `file.path` 到模态框
  - 文件命名: `20260428T040740+0000-title.md` → `title.md`
- **R65 — 面板精简 + L3 自动采纳**:
  - `render_review.js` 369→70 行: 只保留待决策/待判断计数 + 下一审阅
  - `render_execution.js` 315→60 行: 只保留待执行动作 + 最近 3 条收据
  - `render_runs.js` 282→170 行: 只保留最近 5 条运行列表
  - `auto_adopt.py` 新增 `auto_adopt_l3()`: 自动采纳 candidate L3 proposal，写 receipt 保留回滚
  - `agent_loop.py`/`workflows.py` 新增 `AIWIKI_NIGHTLY_AUTO_ADOPT_L3` 环境变量
  - dogfood vault 清空重投，3 份料 → compile → run-compile → multi-round ask → 12 judgments
- **R66 — 图谱锚点链接化 + 导航树简化 + ask 移除**:
  - `execution/ask.py:_append_graph_anchor_section` 从 node ID 列表改为可点击 `[标题](../../path/to/file.md)` 链接
  - `.obsidian/app.json` + `app_vault.py` 添加 `userIgnoreFilters` 隐藏 wiki/schema/output 内部目录
  - Product Shell Ask modal 去掉模式选择，硬编码 `run-ask`
  - Settings 删除 Default ask mode 配置项
  - `ask` 命令保留为 `run-ask` 内部 subroutine
- **文件修改**: 21 files (Python 7 + JS 5 + tests 2 + docs 2 + config 1 + main.js rebuild × 2)
- **指标**:
  - `bash scripts/verify.sh`: All checks passed
  - `ruff check`: 0 errors
  - `main.js`: 7400 lines, `npx jest`: 48/48 passed
  - dogfood vault: 14 sources, 30 concepts, 190 edges, 12 judgments, 8 reports
  - 知识复利: provenance=100%, stale=0%, review_closure=100%, judgment_revisit=83.3%
- **Stop Lines**: 0 review/apply/revert 状态机改动；0 schema mutation；0 npm 依赖新增
- **UX 评估**: 投料链路(URL/PDF/图片)畅通，文件命名简洁无时间戳，面板从运维仪表盘变为报告摘要，导航树仅暴露 raw/ 和 output/reports/，图谱锚点可点击跳转

## Addendum (R107 EP-007, 2026-05-11)

R66 原标题写「ask 移除」与实际不符。当时的工作是 Product Shell UI 整理（Ask modal 简化 + Settings 清理），ask 后端能力始终保留。EP-002/EP-003 后的准确口径：

1. `drop question` legacy CLI alias 在 **EP-003a（R103）** 删除（`cli/parsers.py` 删 subparser；`cli/dispatch.py:161` `"question"` 短路保留以触发 fail-loud `SystemExit(2)`）。
2. plugin `furnace-product-shell:run-ask` palette entry 在 **EP-003a（R103）** 包入 `if (this.settings.showAdvancedCommands)`（默认 `false`，常规用户不可见），**不是移除**。
3. Universal Input 统一为 plugin 主入口；Interaction Send 面板、AskBox、Start Here Ask 按钮三处冗余 UI anchor 在 **EP-003c（R104）** 删除（`render_primitives.js` / `render_input.js` / `plugin.js` 同步退役 wrapper）。
4. Ask modal 仍存在，作为 expert format / protocol / mode 入口，由命令面板的 `run-ask` advanced entry 唤起。`runAskCommand` 签名不变。
5. ask `--format` default 在 **EP-002b（R101）** 从 `report` 切到 `note`；plugin `defaultAskFormat` 在 **EP-002c（R102）** 同步。Ask modal format 下拉从 `[report, slides, figure]` 扩为 `[note, report, slides, figure]`。

R64 文件命名去时间戳、R65 面板精简 + L3 自动采纳 描述保持准确，无需校正。
