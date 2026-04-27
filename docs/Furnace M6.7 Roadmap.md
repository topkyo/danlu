# Furnace M6.7 — Maintainability & Intent Realization Roadmap

> **生成依据**：oracle 代码评审（task `ses_230d4bc9fffeqJ5yl2LLbLfMp1`）+ designer UI 评审（task `ses_230d472d8ffeyb0q2lSo7J1w3w`）+ 综合评估报告（2026-04-27）。
> **Source of Truth**：`README.md`、`AGENTS.md`、`docs/Furnace Agent Architecture.md`、`docs/Furnace Evolution Mechanics.md`、`docs/Furnace Product Shell.md`、`docs/architecture_optimization_v2.md`。
> **当前基线**：M6.6.4 完成；`scripts/verify.sh` 1314 tests / 93% coverage；`scripts/run_acceptance.sh` 12 cases。

---

## 0. 主题与判断

M6.0 ~ M6.6 解决了「功能与结构骨架」：universal input、today feed、metrics、UI smoke、render.js / app_linting / app_shell / plugin.js 拆分。
M6.7 主题转向**复杂度治理与 SoT 视觉意图兑现**：

- 巩固 acceptance gate 可信度（去 byte-flaky）
- 拆 `cli.py` 巨石（1955 LOC）为 command-group sub-modules
- 把 AGENTS.md 的 "no-silent-fail" 契约落到代码里
- 把 Product Shell 从「功能对齐」推进到「视觉与交互意图兑现」
- 把 LLM receipt fallback 字段归一到单一入口，防止漂移

**非目标**（M6.7 不做）：
- hosted service / multi-user sync / heavy RAG infra / fine-tuning
- 引入第三方 bundler、UI 框架、CSS-in-JS
- 任何 hidden backend choice 或 lane judge / auto judge 自动化

---

## 1. Milestone 索引

| ID | 主题 | 维度 | ROI | 依赖 |
|---|---|---|---|---|
| **M6.7.1** | Acceptance determinism — 修 `duration_ms` / `created_at` byte drift | 测试 | 极高 | 无 |
| **M6.7.2** | `cli.py` 拆分 — `cli/{parsers,dispatch,formatters,drop,alchemy,review}.py` | 代码 | 极高 | M6.7.1（gate 必须可信） |
| **M6.7.3** | "Silent fail" 收口 — 5 个吞错点改为可观测 | 代码 | 高 | M6.7.1 |
| **M6.7.4** | Universal Input attachment pill — 杀掉 `DropFileModal` 弹出 | UI | 高 | 无 |
| **M6.7.5** | Typography token + Today Feed 视觉权重 | UI | 高 | M6.7.4 |
| **M6.7.6** | LLM receipt contract 单一入口 | 代码 | 中-高 | M6.7.2 |
| **M6.7.7** | 移除 `input_router.js` 前端镜像 | UI/代码 | 中 | M6.7.4 |

执行顺序：1 → 2 → 3 → 4 → 5 → 6 → 7（每个独立 milestone 内走 contract → fixer → verify → qa-review → 本地 commit；milestone 之间由人审）。

---

## 2. M6.7.1 — Acceptance Determinism

**目标**：所有 `tests/test_acceptance_loop.py` 在固定输入下可重复 byte-stable，移除真实 `duration_ms` / `created_at` 等动态字段对 byte compare 的污染。

**问题事实**：
- 2026-04-27 `scripts/verify.sh` 跑出 `test_happy_run_ask_replay` failure：`b'..."duration_ms": 1...'` vs `b'..."duration_ms": 0...'`，差异在 `tests/test_acceptance_loop.py:161` `_assert_files_byte_equal` 对 `.aiwiki/logs/llm-receipts.jsonl` 的 byte compare。
- 同次 `scripts/run_acceptance.sh -v` 12/12 pass，确认 flaky 而非死锁回归。
- 已有 schema-only 兜底前例：`test_backend_failure_replay`（`tests/test_acceptance_loop.py:489-490`）"The failed receipt schema is stable, but duration_ms can legitimately vary"。

**核心做法**（任选其一或组合）：
1. **JSONL 比较层 normalization**：在 `_assert_files_byte_equal` 之前，对 JSONL 每行解析为 dict，把 `duration_ms`、`created_at`（如果不在 fixed-clock monkeypatch 覆盖范围）等已知动态字段替换为占位常量后再 byte compare。
2. **golden 写入层 normalization**：写 golden 时也走同一 normalization；保证 REFRESH 与 verify 路径对称。
3. **失败路径已有的 schema-only 模式**应用到 happy path 受影响断言。

**Stop Lines（M6.7.1）**：
- 不删除任何已有 byte-frozen golden 文件（只改 compare 路径）
- 不改动 receipt schema / audit schema / shell-summary schema
- 不引入对 `duration_ms` 的人为伪造（必须是 real elapsed ms，只在比较时屏蔽）
- 不放宽 LLM replay 字段（`response_id` / `usage` / `model_final` 必须仍 strict）

**Gate**：
- `bash scripts/verify.sh` pass（≥1314 tests / 93%+ coverage 不下降）
- `bash scripts/run_acceptance.sh -v` 12/12 pass
- 5 次连续 `scripts/run_acceptance.sh -v` 全 pass（稳定性）
- 5 次连续 `scripts/verify.sh` 全 pass

---

## 3. M6.7.2 — `cli.py` 拆分

**目标**：把 `cli.py`（1955 LOC，`main()` 内 `cli.py:1071-1585` 跨业务域 elif 链）拆为 command-group 子模块，**0 行为变化、0 stdout/JSON contract 变化**。

**草拟拆分**（不一次到位，可分批）：
```
src/aiwiki/cli/
  __init__.py        # 保留 main 入口 + back-compat re-export
  parsers.py         # argparse 注册（按 group 注册函数）
  dispatch.py        # main() dispatch 主循环 + 错误码
  formatters.py      # text/JSON 输出共用 formatter
  groups/
    drop.py          # drop-* 系命令
    alchemy.py       # alchemy / signals-replay / planner-log-replay
    review.py        # review / aging / escalation / repair
    today.py         # today / metrics / shell-summary
    runtime.py       # ask / run-ask / nightly
```

**Stop Lines**：
- `cli.py` 顶层 import 路径仍可用（公开 surface）
- `aiwiki.cli.main` 仍是唯一入口
- 0 stdout / JSON / exit-code 改动
- 0 schema / receipt / audit 改动
- 测试中所有 `from aiwiki.cli import main` 仍工作

**Gate**：verify + acceptance 全 pass；`PYTHONPATH=src python3 -m pytest tests/test_cli.py -v` 全 pass。

---

## 4. M6.7.3 — Silent Fail 收口

**目标**：把 AGENTS.md "不得静默吞错" 契约真正落到代码里。允许降级，但必须可观测（log / receipt / audit / 返回 reason）。

**目标点位**：
1. `src/aiwiki/execution/ask.py:318-330` 通知失败裸 `pass`
2. `src/aiwiki/notify.py:68-84` / `:147-158` 双层吞异常（含 audit sink 失败也无声）
3. `src/aiwiki/app_shell/summary.py:289-305` metrics 失败返回 `[]`，shell 不显示 "metrics unavailable"
4. `src/aiwiki/execution/runtime_surfaces.py:62-79` nightly 单项 + 整体错误均 `pass`
5. `src/aiwiki/drop.py:890-897` URL 图片下载失败静默跳过

**输出契约**：每点必须满足：
- 错误事件 append 到 `runs.jsonl` 或 `audit.jsonl`（明确选择，并写在 contract）
- 返回结构带 `skipped_count` / `error_reason` / 同等可读字段
- 主流程不阻断（保留降级语义）

**测试**：每点新增至少 1 个 unit test 模拟失败，断言"主流程成功 + 失败可见"。

**Gate**：verify + acceptance + 新增吞错路径 unit tests 全 pass。

---

## 5. M6.7.4 — Universal Input Attachment Pill

**目标**：兑现 M6.2 "真正统一" 意图。拖文件不再弹 `DropFileModal`，而是在 textarea 里渲染 attachment pill，`<Enter>` 提交时由 launcher 路由。

**做法**：
- 删除 `src/aiwiki/render/input.js`（或对应 `render_input.js`）里 `new DropFileModal(...).setInitialMode("pdf").open()` 路径。
- 在 textarea 容器里渲染 `.furnace-input-attachment` chip（filename + remove ✕）。
- 提交时把 attachment 路径序列化为额外参数交给 launcher CLI；CLI 端复用现有 `drop pdf|image|repo` 分支。

**视觉契约**：
- chip 高度 ≤ 24px，圆角 4px，间距遵循 4-pt scale
- 长 filename 中段省略
- 多 attachment 横向流式排列

**Stop Lines**：
- 0 backend schema 改动
- 0 CLI stdout 改动
- 仍允许传统 `drop-pdf` 命令路径（兼容）

**Gate**：`scripts/product_shell_smoke.sh` pass；`tests/test_product_shell_smoke.py` 新增 attachment-pill 5 个 contract tests。

---

## 6. M6.7.5 — Typography Token + Today Feed 视觉权重

**目标**：兑现 SoT "Linear 骨架 + Notion 报告"。

**做法**：
- `styles.css` 引入 typography token（`--furnace-font-serif`、`--furnace-font-mono`、scale 12/14/16/20/28）
- Report 标题用 serif，Today Feed report 卡片升 hero（full-width，padding 24px）
- elixir / action 降级为紧凑 horizontal sub-list（chip 风格）
- Empty state 改为 `min-height: 120px` + flex 居中 + muted icon + 静默文案

**Stop Lines**：
- 不引入第三方字体加载（用 system serif fallback 链）
- 不破坏 Obsidian 既有主题变量（`--text-normal` 等仍是 fallback）
- 0 DOM contract 破坏：现有 `test_product_shell_smoke.py` / `test_product_shell_metrics.py` 全 pass

**Gate**：29 个 product_shell contract tests 全 pass；新增 5 个 visual-token contract tests。

---

## 7. M6.7.6 — LLM Receipt Contract 单一入口

**目标**：减少 `runner/workflows.py` 各 workflow 手写 receipt 字段导致的漂移。

**做法**：在 `src/aiwiki/runner/receipts.py` 内（不造大 Gateway）建三个纯函数：
- `build_llm_attempt_receipt(...)` → 单次尝试 receipt dict
- `classify_fallback_stage(...)` → `none | model-chain | prompt-profile | deterministic-frontdoor`
- `append_receipt_and_audit(...)` → 三流（receipt + audit + run log）原子追加 + replay normalization

**Stop Lines**：
- 不引入 `LLMGateway` 类抽象
- 不改 receipt JSON 字段名（仅集中产出）
- 0 acceptance golden 改动

**Gate**：verify + acceptance + `tests/test_runner.py` + `tests/test_llm_replay_harness.py` 全 pass。

---

## 8. M6.7.7 — 移除 `input_router.js` 前端镜像

**目标**：守 thin-client 边界。前端只发原文字符串，路由判断回到 Python runtime。

**做法**：
- 删除 `.obsidian/plugins/furnace-product-shell/src/input_router.js`
- Universal Input 提交时直接把原文交给 launcher；CLI 端用 `aiwiki.input_router`（Python）判断 ask/drop URL/drop repo
- 调整 `build.sh` concat 顺序

**Stop Lines**：
- 不改 Python `input_router.py` 路由语法
- UI smoke tests 必须仍 pass

**Gate**：`node --check main.js` pass；29 product_shell tests pass；verify + acceptance pass。

---

## 9. 风险与回退

- **M6.7.1**：normalization 误伤真实 schema 漂移 → 用 dedicated normalizer 函数 + 单元测试覆盖 normalizer 自身行为。
- **M6.7.2**：CLI 拆分破坏 import 路径 → 保留 `cli.py` 作为 facade re-export，1314 tests 是回归保险。
- **M6.7.3**：吞错改为可观测后日志膨胀 → 用 `runs.jsonl` 而非 `audit.jsonl` 收日志类事件。
- **M6.7.4 / M6.7.5**：UI 改动破坏 smoke contract → 先扩 contract tests 再改实现。
- **M6.7.7**：删前端 router 后命令路由错配 → 保留功能开关 `AIWIKI_UI_NATIVE_ROUTER=0`（默认）一轮，灰度后再删。

---

## 10. Source-of-Truth 锚点

- 项目规范：`README.md`、`AGENTS.md`
- 架构 SoT：`docs/Furnace Agent Architecture.md`、`docs/Furnace Evolution Mechanics.md`、`docs/architecture_optimization_v2.md`
- UI SoT：`docs/Furnace Product Shell.md`
- 当前路线（旧）：`docs/Furnace Next Execution Plan.md`（M6.1 ~ M6.6 入口）
- 本文件位置：`docs/Furnace M6.7 Roadmap.md`

---

## 11. 附录 — 评审结论摘录

**Oracle（代码 / 架构）**：方向正确，工程纪律强；最大风险不是功能缺失，而是巨石兼容层 + CLI 调度中心 + 异常吞噬 + golden 非确定性持续累积。Top 5 ROI：fix golden / 拆 cli.py / 收口吞错 / 收窄 facade / receipt 单一入口。

**Designer（UI）**：信息架构对、observation-only 严格守住、Responsive/Collapse 优秀。但视觉离 "Linear 骨架 + Notion 报告" 还远；Universal Input 仍弹 legacy modal；Today Feed 五组等权稀释 Output-first 意图；`input_router.js` 是后端逻辑前端镜像。Top 5：杀 ingestion modal / 注入 typography / 重构 Today Feed 权重 / 改 empty state / 解耦 router。

综合判定：**项目处于 "可用产品" 与 "高维护性产品" 之间。M6.7 是把它推到后者的关键一轮。**
