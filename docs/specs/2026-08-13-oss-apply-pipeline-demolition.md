# OSS：拆除 apply 执行管线

**Date:** 2026-08-13  
**Status:** Approved  
**Owner:** compile / machine-memory / Product Shell / review-queue  
**Depends on:** `docs/specs/2026-08-13-oss-public-truth.md`（公开文案已求真；本规格拆掉仍在算「可 apply」的子系统）

## Goal

apply / revert 产品 CLI 已不存在。compile、shell-summary、review-queue、repair-backlog、Today 不得再**计算、存储或展示**「可执行 / 可 apply / 执行批次 / rewrite 提案队列」。

机器记忆动作作为**只读观察**留下：`advanced review-queue --bucket machine_memory_actions` 仍可查看 status、occurrences、overdue、escalated。没有 apply 按钮，也不再算 apply。

## First principles

工作没了的东西整簇拆；工作还在的东西不顺手铲。

| 项 | 本轮 | 原因 |
|---|---|---|
| apply 执行管线（`can_apply` / `apply_ready` / patch plan / repair-plan 批次与提案 / rewrite 提案状态机 / Shell rewrite_state） | **拆** | 唯一工作是执行一次已不存在的 apply |
| `--bucket ready_actions` 与 Today `ready_actions` | **拆** | 面向「待执行安全动作」，不是观察 |
| `review-queue --bucket machine_memory_actions` | **留** | 过期 / 升级 / 次数仍是真人工作 |
| 概念质量 / 弱概念 | **留** | 「这篇写得差」≠ 「这篇有一张可 apply 的提案」 |
| `gc-orphans --apply` | **留** | 这是 GC 删除，不是治理 apply |
| 金丹 revert / `file-back` / compile / nightly | **留** | 仍有入口 |
| `alchemy-start` action id | **永不做** | 产品契约，不是求真 |
| `AGENTS.md` 本机路径、CONTRIBUTING 三件套 | **开源发布前** | 与本簇无关 |
| `docs/archive/**` 改写成现行产品 | **永不做** | 史料 |

「诊断保留」= 半拆除：引擎继续假装有执行管线，只把按钮藏起来。对开源读者比缺功能更糟。

## Constraints

- 不改产品 CLI 顶层形状：`drop` / `today` / `advanced`。
- 不删 `review-queue`；不把弱概念重新变成 rewrite 提案。
- 不改 `alchemy-start` / `file-back-judgment` action id。
- 不改 archive；不改历史 plan 的已勾选叙述。
- 改 Product Shell JS 后必须 `bash .obsidian/plugins/furnace-product-shell/build.sh`。
- `ready_actions` **不加兼容别名**；该桶名从 help / Today / JSON 消失后，再敲应空桶或明确不是命令，不偷偷映射到 `machine_memory_actions`。
- 用户自己丢进 `wiki/rewrite-proposals/` 的笔记（非 `kind: rewrite-proposal` + `generated_by: aiwiki-run-compile`）必须保留。
- vault 里已有的空 concept-rewrite state 文件：不迁移、不强制删除；compile 停止写入与 lint 停止要求即可。
- `aiwiki.corpus` 分层不变：不引入 content↔memory 互 import。

## Design

### Architecture

公开含义：

```
观察（还在）          执行（拆除）
─────────────        ─────────────────
machine-memory       apply_ready / can_apply
  actions 列表       safe_apply_preview
overdue / escalated  patch_plan / execution batches
weak concepts        rewrite proposal queue
review-page /        Shell rewrite_state
  file-back          --bucket ready_actions
```

内部不得再保留「给已删 CLI 用」的兼容字段来喂 UI。JSON 里留 `can_apply: false` 仍是广告。

### Components

| 面 | 现状 | 改为 |
|---|---|---|
| `execution/repair_plan.py` | compile 每轮建批次 / 提案 / 把 planner 当 apply 队列 | **删除模块**。health 不再挂 `repair_plan` |
| `execution/patch_plan.py` | 为 apply 生成页级补丁 | **删除模块**（若删除后无其它调用方） |
| `memory/rewrite_readiness.py` | 判定 rewrite 提案是否 apply-ready | **删除模块**（若删除后无其它调用方） |
| `action_supports_low_risk_apply` / `safe_apply_preview` / `LOW_RISK_APPLYABLE_*` | 低风险 apply 判定与预览 | **删除**；`action_core` 描述动作时不再写 `apply_ready` |
| compile `runtime_step` | 调用 `build_machine_memory_repair_plan` + `reconcile_concept_rewrite_proposals` | 停调用。planner_state 仍独立落盘（见 Data flow）。rewrite 提案：只 prune compile 生成页，不写空 state |
| `memory/execution_surfaces.py` | reconcile 空提案 + 渲染提案页 | 抽掉提案状态机；若文件被掏空则删除。compile 生成页的 prune 可留在 compile 侧短函数 |
| lint `phases.py` | 要求 concept-rewrite state；校验 `apply_ready` | 不再要求该文件；删除 apply_ready 校验。planner_state 文件要求保留（Ask/nightly 仍用） |
| `app_shell/controls.py` | 从 rewrite state / repair_plan 填 `can_apply` | 去掉 rewrite 提案控件与 apply 控制。动作控件最多 `can_review`（查看），无 `can_apply` |
| `cli/dispatch_helpers.py` | `--bucket ready_actions`、batch-helper、`can_apply` 字段；`machine_memory_actions` 用 apply/review 过滤 | 删除 `ready_actions` 桶与 batch-helper。review-queue JSON **不发射** `can_apply`。`machine_memory_actions` 列出被追踪的动作（可见性不依赖 apply-ready） |
| Today / `today_feed.py` / `app_shell/rendering.py` | `ready_actions`：「确认待执行动作」 | 从 feed 键与文案删除 |
| repair-backlog / `memory/status.py` | Ready / 批次 / 可安全执行 / 可应用 Rewrite | 只保留观察口径：动作总数、过期、升级、弱概念。不提批次、提案、可执行 |
| nightly receipt | `repair_plan_counts` / ready action ids / rewrite apply_ready slugs | 删除这些字段；可留 action overdue/escalated 与 concept quality |
| Ask `graph_query.py` | 把 `execution_proposals` / planner `next_action` 当查询上下文 | 停止注入；Ask 仍可用动作观察与弱概念 |
| cache `query.py` / `sync.py` | 快照含 `repair_plan` | 去掉该键 |
| Product Shell `rewrite_state.js` | normalize 空提案 / followup apply | **整文件删除**。`plugin.js` / `run_state.js` / `plugin_helpers.js` 去掉只为它服务的 wrapper 与 run 记录字段 |
| Jest | `rewrite-state.test.js` 及 run-state 里 rewrite 提案断言 | 删除或改成「无 rewrite 字段」 |
| `lifecycle` rewrite 提案 status / `REWRITE_PROPOSAL_STATUSES` | 提案状态机 | 无调用方则删除；不要留死常量「以备将来」 |
| `corpus` `load/save_concept_rewrite_state` | 空队列 I/O | 无调用方则删除 |

`gc-orphans --apply`、alchemy revert、`can_review`、`can_revert`（仅金丹真实可 revert 时）不动。

### Data flow

**compile**

1. 仍 `reconcile_machine_memory_actions` → health.actions / overdue / escalated。
2. **不再** 建 `health.repair_plan`。
3. **不再** 写 concept-rewrite state，**不再** 往 `health` 塞提案队列。仍删除 `wiki/rewrite-proposals/*.md` 中 compile 生成页（`kind: rewrite-proposal` 且 `generated_by: aiwiki-run-compile`）。
4. planner_state：继续 `load` 后写回（更新 `generated_at` / `state_path`，保留 `executed_actions` 历史）。**不要** 从 repair-plan 重建 `pending_proposals` / `priority_queue`。schema 若仍含空数组以通过现有 loader，可以留；用户可见页面不得把它们写成 apply 队列。
5. 仍渲染 review-queue 与 repair-backlog；后者只谈查看 / 过期 / 升级 / 弱概念。
6. `write_shell_summary` 不再含 rewrite 提案控件或 `can_apply`。

**review-queue**

- `--bucket machine_memory_actions`：列出追踪中的动作；command 指向查看，不指向 apply。
- `--bucket ready_actions`：不再是产品桶。

**Product Shell**

- run 记录不再携带 rewrite proposal objects / followup apply actions。
- 单写者警告保持上一轮口径（compile / nightly / alchemy / file-back），不因本轮改回 apply。

**vault 残留**

- 已有空 rewrite state JSON：忽略。
- 用户笔记在 `rewrite-proposals/`：保留。
- ignore/hide 该目录可留。

### Error handling

| 情况 | 行为 |
|---|---|
| 旧 vault 仍有 concept-rewrite state 文件 | 不报错、不强制删；compile 不再更新它 |
| 旧 vault 仍有 compile 生成的 rewrite-proposal 页 | 下次 compile prune |
| `advanced review-queue --bucket ready_actions` | 空桶（与已删的 `mm_actions` 同策略：不加别名） |
| 测试或代码仍 import 已删模块 | 直接改调用方，不留 re-export facade |

### Testing

- `tests/test_repair.py`：删除 repair-plan / patch-plan / apply_ready 断言；留下 repair-backlog 观察文案与动作 reconcile 相关测。
- CLI：`review-queue --bucket machine_memory_actions` 仍可列出动作；`--bucket ready_actions` 为空；JSON 无 `can_apply`。
- library：无 `aiwiki.execution.repair_plan` / `patch_plan` import。
- Product Shell：删除 rewrite-state 专测；`npm test` / `verify.sh product-shell-static`；`build.sh` 后 `main.js` 无 drift。
- 若 Ask prompt 因去掉 execution_proposals 而变：只刷新对应 acceptance `prompt_hash` 帧，不改无关 prompt 正文。
- 收口：`bash scripts/verify.sh all`。计数钉随删除的测试条数更新（AGENTS / Scorecard / DEVELOPER / CHANGELOG / `docs_consistency_check.sh`）。

## Out of scope

- 删除 machine-memory **动作**本身或 `review-queue` 命令
- 删除概念质量 / 弱概念 lint
- 删除 `planner/` 或 query-route telemetry
- 去 AGENTS.md / sync 脚本中的 `/Users/ht`
- 新增 CONTRIBUTING / SECURITY / `.env.example`
- 改写 `docs/archive/**`
- 恢复 apply CLI 或把弱概念再写成 rewrite 提案

## Open questions

(none)
