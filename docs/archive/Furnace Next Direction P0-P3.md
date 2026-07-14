# 炼丹炉 Next Direction — P0..P3 (post-M7)

> **Archive note (2026-05-01)**：P0-P3 已完成并被 `docs/Furnace Next Direction Post-P4.md` 取代；本文只保留为历史方向和验收背景。

> 生成时间：2026-04-28，承接 M7 闭环（commit `ddd6faf`，9+ Contract 8.83/10）。
> SoT：`docs/Furnace Agent Architecture.md` + `Furnace Evolution Mechanics.md` + `Furnace Product Shell.md`。
> 本文件不是路线图，是**方向决策**。具体 milestone 实现走 `.codex/contracts/active.md` + harness 流程。

---

## 0. 视角校准

M7 落地的是**机制层**：4 kill switch / metrics / scope receipt / strict model / autonomy CLI。
P0~P3 落地的是**用户体感层**：让单人用户每天打开 vault 就能感受到"知识在复利"。

**不再追求工程指标提分**（9+ Contract 已 8.83/10 实质达标）。
**不背技术债**：不为旧实现兜底，重构阶段直接最优解。
**最终目的**：让你（单人）通过持续投喂，沉淀出会自我增值的私人知识库，证据可追、判断可审、金丹可用、提示词回流。

---

## 1. P0 — Today 视图变成真正的 daily driver（最高优先级）

**问题**：M7 落了大量 metrics / signal / planner-log / review queue / l3 proposals，但 `aiwiki today` 是 stub。所有底层机制需要在**一屏**汇聚才能产生产品价值。

**目标**：`aiwiki today` 输出"现在做什么最有价值"的优先列表，把以下信号融合并按 actionability 排序：

- counter-evidence 命中（判断被反驳）
- stale judgments / drift 触发（证据变了）
- ready-to-promote candidates（金丹可升级）
- 待 review 的 L3 proposals（提示词改进建议）
- metrics 7d/30d delta 关键变化
- planner 待人工决策的 decisions

**成功标准**：单人用户从 0 改造 vault → 每天 `aiwiki today` 看完这一屏就知道下一步。  
**不做**：HTML / web UI / 实时刷新。仍是 CLI text + `--json`。  
**风险**：Today 是 acceptance 重灾区？派 explorer 摸过；找最低摩擦切入点。

---

## 2. P1 — Evidence Chain 可视化

**问题**：任何金丹 / 判断 / 提示词的"为什么这么说"目前散在各 receipt / audit 里，没有整合视图。这是炼丹炉信任的**根基**——知识库可信前提是能一键追到原始证据。

**目标**：`aiwiki advanced trace <id>` 输出
```
elixir-investing-001
├── built from candidate-…
│   ├── distilled from judgment-…
│   │   ├── derived from raw/inbox/2025-research-XX.pdf
│   │   └── derived from raw/inbox/url-2025-…
│   └── distilled from judgment-…
└── used by L3-proposal-…
```

**成功标准**：任何 wiki / output 资产，3 秒内拿到完整 provenance 树。  
**依赖**：M7 的 universal audit stream + 各 receipt。  
**不做**：图形化（保持 text tree）。

---

## 3. P2 — 一个 Protocol 走通端到端（Investing）

**问题**：当前 5 protocol 都是 schema 上的存在，没人证明过任何一个能从"投喂研报"完整跑到"用金丹回答新问题"。这是从"机制完备"到"产品有用"的**唯一通道**。

**目标**：选 `investing` protocol（与当前分支名一致），完成一次端到端实跑：
1. drop-pdf 投喂 3-5 份研报 / 公司财报
2. 自动 / 半自动出 judgments
3. 累积到阈值后蒸馏出 1-2 个真正的金丹
4. 用金丹回答一个新问题（`aiwiki ask`）
5. 根据回答质量改进 prompt（L3 proposal）
6. **把过程中遇到的所有摩擦点写进 PROGRESS / 后续 milestone**

**成功标准**：流程跑通 + 一份"摩擦点报告"指出下一步具体修什么。  
**这不是新功能，是 dogfood**——它的产出是"接下来该修哪些 P/M"的优先级排序。

---

## 4. P3 — Drift / Aging 自动信号

**问题**：判断会过期，证据会被 archive，金丹会因新证据变得不准。系统需要**主动**喊"这条 6 个月没复核 / 这条的 3 个证据 raw 已变"，而不是等用户发现。

**目标**：
- nightly job 扫描 `wiki/judgments/` 与 `wiki/elixirs/`，发现：
  - >180 天未复核的 judgment
  - 引用的 raw 已 archive / hash 变化
  - 金丹的 underlying judgment 被 demote
- 把信号写进 normalized signal stream
- P0 的 `aiwiki today` 自动浮出这些信号

**成功标准**：让炼丹炉具备**自我维护**能力——不投喂也会提醒你回来看老知识。  
**依赖**：P0 完成（today 是浮出口）。

---

## 5. 执行顺序与依赖

```
P0 (today 实化)
 ├── 直接独立做
 └── 是 P3 的浮出层
P1 (evidence chain)
 └── 独立做，与 P0 不冲突
P2 (investing 端到端)
 └── 应在 P0 完成后做（P0 是日常入口，否则 dogfood 不真实）
P3 (drift signals)
 └── 依赖 P0
```

**推荐顺序**：P0 → P1 → P2 → P3。

P1 可与 P2 并行（不同代码区）。

---

## 6. 非目标（明确不做）

- M8 "Compatibility adapters 套件"：经 explorer 摸查，已有 `_read_elixir_anywhere` + `legacy-migration` CLI + 测试覆盖；纯刷分，不做
- HTML / Web UI / 多用户协作 / hosted service / fine-tuning（沿用 SoT 非目标列表）
- 任何为旧实现兜底的代码：重构阶段直接最优解
- 任何评分驱动而非用户价值驱动的 milestone

---

## 7. 闭环规约（沿用 M7）

- 每个 P/M 走 harness：读 SoT → `.codex/contracts/active.md` → 实现 → `bash scripts/verify.sh` → 5x 稳定 → 归档 contract → 回写 PROGRESS → commit
- ask_policy = blockers-only
- execution_mode = autonomous-closed-loop
- stop lines：连续 3 轮 verify 失败 / acceptance golden 大面积漂移（>20%）/ 触动非目标边界 → 升级
