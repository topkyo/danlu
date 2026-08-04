---
title: "炼丹炉进化机制"
kind: "contract"
status: "active"
owner: "tim"
supersedes:
  - docs/archive/Furnace Material Scaling.md
  - docs/archive/Furnace Material State Model.md
  - docs/Furnace Incremental Compile Plan.md
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Elixir.md
  - docs/Furnace Runtime Operations.md
---

# 炼丹炉进化机制

实现契约 SoT：active corpus、金丹生命周期、现行 operator CLI。**不**复述已删 AgentOS 命令表；heavy/light lane、signals/planner-log ops、L3 apply/revert CLI 见 [[docs/Furnace Agent Architecture|架构文档]] §8 与 `docs/archive/`。

与 [[docs/Furnace Agent Architecture|架构文档]] 配对：架构答「边界在哪」，本文答「契约是什么」。

## 1. 范围

**定义**：

- `active_corpus` schema 与生命周期（implemented）
- 金丹 candidate / settled 平面与 promote/revert/demote receipt（implemented）
- Chaining → Distillation → Compounding 最小 CLI 语义（implemented）
- Signal / planner **目标契约**（internal modules；产品 CLI 已删）

**不定义**：Product Shell UI 细节、EP 时间表（见 `PROGRESS.md`）、终局愿景（见架构文档）。

## 2. 现行 operator CLI

顶层：`drop` / `today` / `advanced`。运算符走 `aiwiki advanced ...`。

| 命令 | 语义 | 写目标 |
|---|---|---|
| `compile` / `lint` | 确定性 compile / lint | `wiki/`、`.aiwiki/lint/` 等 |
| `run-nightly` | 确定性 compile + lint + health（无 agent-loop） | receipt / runtime history |
| `run-ask` | LLM 报告主入口 | `output/reports/*.md` + LLM receipt |
| `file-back <artifact>` | judgment-only 回流 wiki | `wiki/judgments/` |
| `review-page <path> --status …` | 单页三态审阅 | target page + review queue |
| `watch` | deterministic compile+lint on inbox | `wiki/` |
| `advanced alchemy start\|distill\|finalize\|promote\|revert\|demote` | 金丹最小链 | `.aiwiki/staging/elixirs/` → `wiki/elixirs/` |
| `trace` / `metrics` / `shell-status` | 诊断与遥测 | 只读或 state append |

> 金丹：推荐 `advanced alchemy …`；旧 `alchemy-*` hyphen 别名仍可用作 compat（见 `docs/USER_GUIDE.md`）。

**已删除（W3/W6/W8）**：`auto-once`、`signals-*`、`planner-log-*`、`audit-*`、`alchemy auto|heavy|light|lane`、`l3-proposal-*`、`apply/revert <proposal>`、`apply-action`、`apply-rewrite`、`apply-archive`、`run-compile`、`run-lint`。完整列表见架构 §8。

## 3. Active corpus

**定位**：可持久化 runtime working set（「当前围绕哪批材料炼化/提问」），不是事实源。

| 文件 | 角色 |
|---|---|
| `.aiwiki/state/active-corpora.json` | canonical state |
| `.aiwiki/state/runtime-history.jsonl` | 统一运行历史 |
| `.aiwiki/state/output-candidates.json` | output 候选状态 |

**原则**：

- 只存在于 `.aiwiki/state/`，不写入 `wiki/`。
- 不能原地升格为金丹；必须走 `distill → finalize → promote`。
- 状态：`active` → `cooling` → `expired`；重新命中可回升。

**已退役写入面**（2026-07-17）：`wiki/indexes/log.md`、`output/control/plugin-runs/`、Judgment 页内无界 Review History append、`output/control/execution-receipts/*.json`（→ `.aiwiki/state/execution-receipts/`）等。操作历史只看 runtime-history / receipts / audit。

## 4. 金丹生命周期

| 状态 | 路径 | 入口 |
|---|---|---|
| `draft` | `.aiwiki/staging/elixirs/` | `advanced alchemy start <corpus_id> --topic …`（compat：`alchemy-start`） |
| `distilling` | 同上 | `advanced alchemy distill <elixir_id> --question …`（compat：`alchemy-distill`） |
| `candidate` | 同上 | `advanced alchemy finalize <elixir-id>`（compat：`alchemy-finalize`） |
| `settled` | `wiki/elixirs/` | `advanced alchemy promote --elixir-id …`（compat：`alchemy-promote`） |
| `superseded` | staging tombstone | promote 成功后原地墓碑化 |

**约束**：

- `elixir_refs` 必须 DAG；须锚定 `wiki/judgments/`（产品路径：`file-back`）或 legacy `wiki/derived/`。
- `counter_evidence` 在 promote gate 强制非空；无反证时写 `[NONE_FOUND]` + `confidence_level: low`。
- promote / demote / revert 分别由 `build_elixir_promotion_receipt` / `build_elixir_demotion_receipt` / `build_elixir_revert_receipt` 构建（`subject_kind`: `elixir_promotion` 等）。

### 三阶段路线图

1. **Chaining**：`run-ask --corpus <id>` 多轮追问；output 写 `output/reports/`，不自动写 `wiki/`。
2. **Distillation**：`file-back` → `advanced alchemy start` → `distill` → `finalize` → `promote`。
3. **Compounding**：`advanced alchemy start --include-elixir …` 显式引用 settled 金丹，DAG 校验。

## 5. Signal / planner（internal 目标契约）

完整 signal taxonomy、planner routing、heavy/light lane 曾是 AgentOS 9.0 目标契约；**W3 已删对应 CLI** 及 `src/aiwiki/signals/`、`src/aiwiki/planner/dry_run` 等库。**Active docs 不得再教 lane/auto/L3 CLI 操作。**

## 6. L2 protocol-learning（W1 已退役）

`protocol-learn-*` CLI、ask `--load-learnings`、nightly aging hook 已删。历史 `wiki/protocol-learnings/` 只读。经验沉淀改走显式 wiki 写回或 staging 候选，不恢复隐式注入。

## 7. L3 prompt/policy proposal（library 保留，CLI 已删）

L3 产品 CLI 与 library 已移除。prompt/policy 写回须 operator 显式路径（现行：`review-page` + 手工编辑 + receipt discipline），不得假装 nightly 自动 adopt。

## 8. Audit / revert

- **Audit 源**：`.aiwiki/state/execution-receipts.jsonl`、`.aiwiki/logs/llm-receipts.jsonl`、`.aiwiki/state/runtime-history.jsonl`（及 direct append 的 universal audit）。
- **可 revert**：金丹 promotion（`advanced alchemy revert`；compat：`alchemy-revert`）；历史 L3 apply 链已删 CLI。
- **不可 revert**：`raw/` 历史事实、audit entry 本体。

## 9. 向后兼容

- 现行 operator primitives 以 `aiwiki advanced --help` 为准。
- 旧 `wiki/elixirs/` 继续可读；新候选默认写 staging。
- Signal / planner / heavy-light 章节描述**目标契约**；已落地 subset 与 W3 裁剪以 `docs/DEVELOPER.md`、`PROGRESS.md` 为准。

## 10. 文档关系

取代：`Furnace Material Scaling.md`、`Furnace Material State Model.md`、`Furnace Incremental Compile Plan.md`（均已归档）。

配套：[[docs/Furnace Agent Architecture|架构文档]]、[[docs/Furnace Elixir|金丹 thesis]]。
