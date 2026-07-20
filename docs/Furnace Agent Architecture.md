---
title: "炼丹炉 Agent 架构"
kind: "architecture"
status: "active"
owner: "tim"
supersedes:
  - docs/Alchemy Furnace.md
  - docs/archive/Furnace Ultimate Architecture.md
  - docs/archive/Furnace Protocols.md
related_docs:
  - docs/Furnace Evolution Mechanics.md
  - docs/Furnace Elixir.md
  - docs/Furnace Runtime Operations.md
  - docs/USER_GUIDE.md
---

# 炼丹炉 Agent 架构

**现行契约 SoT**：用户面见 `docs/USER_GUIDE.md`、运维见 `docs/Furnace Runtime Operations.md`；实现细节见 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]]。本文定义架构边界与不变量，不教已删 AgentOS CLI。

## 1. 定位

炼丹炉（`aiwiki` runtime）是 **local-first、single-writer** 的知识 agent：把 `raw/` 证据炼成可审计的 wiki、machine memory 与 `output/` 报告，支持知识复利与受控进化。

**不是**：笔记库、一次性 RAG 前端、hosted service、multi-user sync、heavy RAG、fine-tuning。

**是**：跑在本地文件系统上的长期 runtime；deterministic baseline + 显式 LLM 路径；所有写回可 receipt / 可审计。

## 2. 用户面（第一性原理）

> **一个输入端 + 一个输出端，其余隐藏。**

| 面 | 入口 | 内容 |
|---|---|---|
| **输入** | `drop` | URL / PDF / image / repo / text / question；默认 LLM plan → deterministic execute（`AIWIKI_LLM_PLANNER=0` 可关） |
| **输出** | `today` | 今日报告、待 review 判断、金丹进展、稀缺复利建议 |
| **Operator** | `advanced` | compile、lint、run-ask、file-back、review-page、watch、run-nightly、金丹链、metrics、trace、shell-status 等 |

下列概念对用户隐藏，仅 operator / debugger 可见：backend 选择、phase 调度、planner/signal 内部状态、candidate plane、legacy autonomy 层级编号。

Product Shell 投影见 `docs/Furnace Product Shell.md`（归档史料见 `docs/archive/`）。

## 3. 五层平面

| 平面 | 路径 | 角色 |
|---|---|---|
| 事实 | `raw/` | 唯一事实输入，不可被派生层覆盖 |
| 知识/判断 | `wiki/sources/`、`wiki/concepts/`、`wiki/judgments/`、`wiki/decisions/`、`wiki/elixirs/` | 人读资产；保留 provenance |
| 运行态 | `.aiwiki/state/*` | machine-readable state（manifest、active corpus、receipts、history） |
| 规则 | `schema/`、`prompts/` | 显式契约 |
| 产物/候选 | `.aiwiki/staging/`、`output/reports/`、`.aiwiki/derived/packs/` | 报告、金丹候选、导出 |

## 4. 不变量

- **Single writer, many readers**：同一时刻一个 writer 写 `wiki/`、`.aiwiki/state/`、`output/control/`。
- **`raw/` 不可覆盖**；派生层必须保留 provenance。
- **Deterministic baseline**：`compile` / `lint` / `run-nightly` / `watch` 不依赖 LLM；LLM 只在显式 `run-ask`、universal `drop` planner、可选 distill synthesizer 等受控入口。
- **Backend 显式选择**：`AIWIKI_LLM_BACKEND` 必须显式设置；无隐式 cross-backend / model fallback。
- **Receipt 闭环**：会改 `wiki/` 或规则面的动作必须产生 execution receipt 与 audit trail；金丹 promote/revert/demote 同理。
- **Runtime 不生成语义判断**：判断结论由 human 或显式 LLM 在报告 / judgment 页提供；runtime 只做结构性调度与落盘。

**非目标**：hosted service、multi-user sync、heavy RAG、fine-tuning、agent 自动改 `src/aiwiki/**` 或 schema 核心。

## 5. Agent loop（概念模型）

```
signal → planner → phase → feedback → learning → (re-enter as signal)
```

- **Signal**：`raw/` 变化、drift、review 反馈、schedule tick 等；标准化后进入 planner，不直接触发命令。
- **Planner**：路由为 ignore / enqueue / proposal / escalate-human；决策可审计。
- **Phase**：compile、lint、judge、distill、review 等；均映射到受控 CLI primitive。
- **Feedback**：receipt、audit、drift、review outcome → 重新进入 signal 流。
- **Learning**：只允许落到 L1 runtime state（`.aiwiki/state/*`）或 staging 候选；不自动写 `prompts/` / schema 核心。

内部 signal/planner 模块与 state 文件仍可能存在；**产品 CLI 不再暴露** `signals-*`、`planner-log-*` 等（W3 已删，见 §8）。

## 6. 金丹（一等资产）

金丹是与 judgment/decision 并列的复合知识资产：

- 候选：`.aiwiki/staging/elixirs/`（draft → distilling → candidate）
- 持久：`wiki/elixirs/`（`alchemy-promote` 产生 settled）
- 最小链：`alchemy-start` → `alchemy-distill` → `alchemy-finalize` → `alchemy-promote`（+ `revert` / `demote`）
- 必须 DAG 校验、provenance 锚定（`wiki/judgments/` 或 legacy `wiki/derived/`）

详见 [[docs/Furnace Evolution Mechanics|进化机制]] §7 与 [[docs/Furnace Elixir|金丹 thesis]]。

## 7. 单协议 runtime

- 唯一 slug：`general`；规则在 `schema/protocols/general/`。
- 已删：`protocol-set`、`protocol-learn-*`、ask `--load-learnings`。
- Backend 由 env / Shell settings 显式配置，不在 planner 决策范围内。

## 8. 历史 AgentOS 面（已删除）

2026-07-18 W3 起，下列能力**已从产品 CLI 物理删除**；state 文件（如 `signals.jsonl`、`planner-log.jsonl`）可能只读存在，但无对应 operator 命令：

- `signals-*`、`planner-log-*`、`audit-preview` / `audit-backfill`
- `alchemy auto|heavy|light|lane`、`alchemy judge|review|distill|propose`（scoped 变体）
- L3 `l3-proposal-create/generate`、`review proposals`、`apply/revert <proposal-id>`
- `apply-action`、`apply-rewrite`、`apply-archive`、`run-compile`、`run-lint`
- `auto_adopt.py`；`AIWIKI_NIGHTLY_AUTO_ADOPT_*` env 现为 legacy no-op

详细命令表与 milestone 史料见 `docs/archive/`（含 `AGOS-9-Execution-Plan.md`、W3–W8 plan 归档）。**不得**把上述 CLI 当作现行产品教学。

现行 nightly / watch / drop-auto：**仅 deterministic compile + lint**（W8）。

## 9. State loader 语义（摘要）

`.aiwiki/state/*.json` / `*.jsonl` 有两种读取契约：

- **Best-effort**（`load_json_document`）：损坏时 warning + 空默认值；用于 preview / telemetry。
- **Strict**（`load_json_document_strict`）：损坏时 `CorruptStateError`；用于 authoritative receipt / promote / revert 路径。

## 10. 文档关系

| 文档 | 角色 |
|---|---|
| 本文 | 架构边界与不变量 |
| [[docs/Furnace Evolution Mechanics\|进化机制]] | active corpus、金丹、现行 CLI 契约 |
| `docs/Furnace Runtime Operations.md` | 运维与自动化 |
| `docs/AGOS-9-Scorecard.md` | verify gate 与 release 评分 |
| `docs/archive/*` | 历史 AgentOS / Product Shell 史料 |

取代：`Alchemy Furnace.md`、`Furnace Ultimate Architecture.md`、`Furnace Protocols.md`（均已归档）。
