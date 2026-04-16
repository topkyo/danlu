---
title: "炼丹炉最终极形态"
kind: "architecture"
status: "active"
---

# 炼丹炉最终极形态

这份文档回答的不是“现在已经做到了什么”，也不是“从现在到上限怎么走”，而是：

**如果这套炼丹炉被持续打磨到极致，它最终会长成什么样。**

对应关系：

- 基线架构：[[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- 最终形态：当前这份文档

## 核心定义

炼丹炉最终不该只是：

- 笔记软件
- 普通 `llm-wiki`
- 一次性 RAG 问答器
- 只会整理文档的 agent workflow

它最终应该是：

**单人优先、可多 agent 协作、可审计、可回滚的认知操作系统。**

它的价值不在“存了多少资料”，而在：

- 证据能被持续编译成概念
- 概念能被持续编译成判断
- 判断能被持续拉回复审、修复、执行和回滚
- 整个系统能形成长期复利

## 形态边界

默认形态不是多人类团队平台，而是：

- 一个 `Human Owner`
- 一个统一炉子
- 多个可分工的 agent

也就是：

- **单人本地炉子** 是默认形态
- **多 agent 协作** 是高阶形态
- **多人类团队共享** 只是远期可选扩展，不是当前默认目标

## 总体架构

为了和 [[wiki/indexes/Alchemy Furnace|炼丹炉架构]] 保持一致，这份终局草图继续显式保留：

- `Schema / Protocol` 作为独立的运行时层
- `Outputs` 作为独立的产物层

其中：

- `Schema / Protocol` 是跨层约束，不只是某一步的附属配置
- `Outputs` 是人和 agent 的可消费产物，不只是临时副作用

```text
                 ┌──────────────────────────┐
                 │       Human Owner        │
                 │ 投料 / 提问 / 审阅 / 裁决 │
                 └────────────┬─────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 1. Evidence Fabric                                       │
│ raw sources / attachments / captures / transcripts       │
│ 唯一事实输入层，不被派生结论静默覆盖                      │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 2. Knowledge Compiler                                    │
│ ingest / compile / summarize / concept synthesis         │
│ 把证据编译成 sources / concepts / indexes / derived      │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 3. Judgment System                                       │
│ decisions / judgments / confidence / invalidation        │
│ 把知识继续沉淀成可复审的判断资产                          │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 4. Machine Memory                                        │
│ graph / retrieval / topology / planner / action queue    │
│ 给 agent 用的机读层，不替代 wiki                         │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 5. Schema / Protocol Layer                               │
│ schema / prompts / protocols / policy                    │
│ 作为跨层运行时约束，塑造 compile/judgment/review/execute │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 6. Governance Layer                                      │
│ review / aging / escalation / drift / lint / repair      │
│ 负责长期一致性、复审和知识卫生                            │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 7. Execution Layer                                       │
│ dry-run / bundle / apply / receipt / revert / audit      │
│ 只安全执行低风险动作，高风险永远停在人类边界外            │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 8. Outputs Layer                                         │
│ reports / slides / figures / bundles / receipts / packs  │
│ 人和 agent 的可消费产物层，同时也是高价值回流入口          │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 9. Product Shell                                         │
│ furnace-center / review-center / execution-center        │
│ graph-view / execution-audit                             │
│ 人通过统一工作台和系统交互                                │
└───────────────────────────────────────────────────────────┘
```

## 九层解释

### 1. Evidence Fabric

职责：

- 收住所有原料和最早证据
- 保留原始附件、capture notes、转录和快照
- 做所有后续推理和判断的事实底座

要求：

- `raw` 永远不被派生结论静默覆盖
- 所有 capture artifact 必须回指原文件、原 URL 或原上下文
- 这里是事实输入层，不是结论层

### 2. Knowledge Compiler

职责：

- 把原料编译成 `sources / concepts / indexes / derived`
- 让“资料堆”变成“结构化知识层”

要求：

- deterministic compile 作为底座
- LLM 负责高层综合，不负责破坏事实边界
- concepts 不只是摘要集合，而是横跨多个 source 的共识层

### 3. Judgment System

职责：

- 把知识继续炼成 `judgment / decision`
- 让系统沉淀的不只是信息，而是可复审判断

判断资产至少要带：

- `citations`
- `confidence`
- `counter-evidence`
- `invalidation`
- `revisit_after`
- `escalate_after`

这是系统最值钱的一层，因为真正复利的不是 note，而是判断。

### 4. Machine Memory

职责：

- 给 agent 一个高密度、可计算、可图谱化的机读层
- 加速查询、修复、提案和执行规划

这里应该存在：

- source / concept graph
- topology
- retrieval routes
- planner state
- action queue
- execution proposals

但它永远不替代人读的 wiki。

### 5. Schema / Protocol Layer

职责：

- 定义系统如何 ingest、compile、cite、review、lint、write back
- 把“一个统一炉子，多套协议”真正落成 runtime 规则
- 决定不同领域下 query、judgment、review、nightly、execution 的偏置

这里至少应该存在：

- `schema/`
- `schema/protocols/`
- prompts / policy / taxonomy
- review 和 execution 的策略约束

这层不是静态文档，而是运行时的规则平面。

### 6. Governance Layer

职责：

- 维护长期一致性
- 让旧判断被复审
- 让冲突和漂移被看到
- 让低质量概念和待修复关系进入工作流

它的意义是把系统从“会长内容”变成“会维护知识质量”。

### 7. Execution Layer

职责：

- 把低风险修复从建议推进到安全执行
- 提供 `dry-run / apply / revert / audit`

要求：

- 必须有 bundle
- 必须有 receipt
- 必须可回滚
- 必须可审计
- 高风险动作默认不能自动执行

最终这层不是“自动化越多越好”，而是：

**只在安全边界内自动化。**

### 8. Outputs Layer

职责：

- 把知识层、判断层和执行层转成可消费产物
- 为人、agent 和后续回流提供稳定 artifact

这里至少应该包括：

- reports
- slides
- figures
- execution bundles
- execution receipts
- review packs / decision memo / SOP 草案

这层必须显式存在，因为它决定系统如何把内部结构变成外部可用结果。

### 9. Product Shell

职责：

- 把分散的能力统一成一个人真正愿意天天用的工作台

**默认工作台是 Obsidian**：

- Obsidian 是 Product Shell 的第一工作面——投料、查询、审阅、修复、图谱、执行、审计全部从 Obsidian 插件面板进入
- HTML 控制台（`furnace-center.html`、`execution-center.html`、`review-center.html`、`machine-memory.html`）作为**备用**，给不开 Obsidian 时的轻量检查用
- `aiwiki CLI` 是底层 runtime 入口，Obsidian 插件通过 CLI 调度，不直接操作 state 文件
- 现在可以用 `aiwiki new-vault <target>` 直接起一个新的炼丹炉 Obsidian vault；vault 内 launcher 回指 runtime root，不要求 vault 自己包含源码

实现级设计可见：

- [[wiki/indexes/Furnace Product Shell Plugin|炼丹炉 Product Shell Plugin]]

最终理想状态：

- 投料
- 查询
- 审阅
- 修复
- 图谱
- 执行中心
- 执行
- 审计

都可以从 Obsidian 内的统一面板进入，而不是靠记命令和跳多个页面。

## 自动化角色（非多 agent）

炼丹炉的运行模型是 **single writer, many readers**，不是多 agent 协作系统。

当前的"角色"不是独立 agent，而是**同一个 `aiwiki` runtime 内的自动化阶段**——它们共享同一把运行锁、同一份 state、同一套 CLI，只是在不同时机被触发：

典型自动化角色：

- `ingest phase`
  - 整理原料、补元数据、建 source page（`drop-*` / `ingest`）
- `compile phase`
  - 编译 source → concept → index → derived（`compile` / `run-compile`）
- `judgment phase`
  - 高价值 output 经 `file-back` 晋升为 `decision / judgment`
- `review phase`
  - 复审待审、过期、冲突、失效判断（`review-page` / `review-rewrite`）
- `repair phase`
  - 生成 repair action、patch plan、execution bundle（`lint` / `run-lint`）
- `execution phase`
  - 只执行被允许的低风险动作（`apply-action` / `apply-archive`）
- `nightly phase`
  - 夜间巡检、复审、回流、漂移检查（`nightly` / `run-nightly`）

这些阶段共享同一个：

- `raw`
- `wiki`
- `machine memory`
- `decision / judgment`

它们不是独立进程，也不各自维护私有真相。

### 为什么不用多 agent

- 炼丹炉是单人本地系统，不存在需要多 agent 并发协商的场景
- `single writer` 模型下，所有写入都经过同一把锁，多 agent 不会带来吞吐收益
- 当前所有"角色"已经通过 CLI 子命令 + systemd timer 覆盖，不需要 agent 间通信协议
- 引入真正的多 agent 会增加 coordination overhead，但炼丹炉的价值在判断质量而非并发处理量
- 如果未来出现需要并行处理大规模原料的场景，优先考虑 `worker pool + shared state` 而非 `autonomous agent swarm`

## 最终闭环

最终极形态下，系统的闭环应该是：

`evidence -> compile -> concept -> judgment -> review -> repair -> execute -> receipt -> revisit`

这比常见的：

`document -> summary -> search -> answer`

高了一层，因为它不仅回答问题，还管理：

- 判断是如何形成的
- 判断如何被修正
- 行动如何被执行
- 执行如何被回执与回滚
- 旧结论何时应被重新审视

## 最终资产

真正会长期复利的，不是“很多 markdown 文件”，而是 4 类资产：

### 1. Hard Concepts

- 硬概念库
- 稳定术语、因果、结构性关系
- 能承受冲突、复审和重写

### 2. Judgment Assets

- thesis
- tradeoff
- risk frame
- invalidation rule
- decision memo

### 3. Execution Playbooks

- 可治理、可复盘的低风险行动剧本
- 明确什么能自动做，什么必须停在人手里

### 4. Cognitive History

- 判断是怎么形成、推翻、修正的历史
- 系统不只是记住结论，还记住判断演化过程

## 最终硬边界

再强的炼丹炉，也不能越过这些边界：

- 人永远保留最终判断权
- `raw` 永远是事实底座
- 高风险动作不能自动执行
- 所有结论都必须可追溯
- 所有执行都必须可审计、可回滚
- 协议层可以变化，但统一炉子不能分裂成多个私有真相

## 演化路线

从当前版本到最终形态，分三个阶段。每个阶段解决一个结构性问题。

### Phase A — 治理消化 + 执行闭合

> 核心命题：**证明系统不只会发现问题，还会解决问题。**

当前系统的治理层（review / aging / repair / lint）非常擅长发现问题：39 lint warnings、25 rewrite proposals、8 execution proposals——但几乎没有一个被真正闭合。30 个 concepts 全标"待回看"，25 个 rewrite proposals 全 pending，8 个 execution proposals 全 proposed。

如果不解决这个"治理只产不消"的问题，系统会陷入"越跑越多 warning"的死循环，治理层从资产变成负债。

这个阶段的目标是：

- 清零 lint warnings
- Apply 至少 3 个 rewrite proposals，证明概念修复链可闭合
- 消费 ≥ 3 个 execution proposals（覆盖 ≥ 2 种 action 类型），证明执行层不只是 citation-refresh
- 激活 planner 自动消费循环（nightly 扫描 → low-risk accepted → auto bundle）
- dry-run 产出结构化 JSON artifact
- 触发至少 1 次真实 escalation → review → resolve 全链路

完成后，系统从"管线能跑"推进到"管线能自维护"。

### Phase B — 内容密实 + 判断资产化

> 核心命题：**从"管线能跑"推进到"管线产出有价值的知识"。**

Phase A 解决的是工程问题；Phase B 解决的是内容问题——需要真实使用系统，不是写代码能完成的。

当前 30 个 concepts 全部 soft、judgment 建在弱概念上、judgment 间关联稀疏（仅 2 条 j→j 边）。终极形态要求"judgment 是系统最值钱的一层"，但现在这一层的资产密度不足以支撑这个定位。

这个阶段的目标是：

- Hard concepts 从 5 → 15，concept_causal 边从 12 → 30+
- Judgments 从 6 → 12，覆盖 research / investing / product 三个 protocol
- Judgment→judgment + judgment→decision 关联边 ≥ 6 条
- 30 concepts "待回看" 状态清零（review 通过或 retire）
- Evidence 补强：raw 46 → 80+，sources 16 → 30+，高 hardness concept 至少 3 source 支撑
- Escalation 被真实压力测试并成功 resolve

完成后，系统从"基建完善的原型"推进到"有真实知识价值的认知系统"。

### Phase C — 产品收敛 + 日常可用

> 核心命题：**让炼丹炉真正成为"每天想打开的工具"而非"每天需要维护的系统"。**

这个阶段是产品打磨，不改变系统能力边界，但大幅提升日常使用体验。

目标包括：

- 交互式知识图谱（vis.js / d3-force，节点可点击、按 kind 过滤、按 protocol 着色）
- Context 自动推断（模糊匹配 action/entry、suggested_next_actions、active note awareness）
- First-run onboarding（new-vault 首次打开的引导面板）
- Output 密度（figures ≥ 6 / slides ≥ 6 / reports ≥ 15，高价值产物 > lint 产物）
- 测试 93%+

完成后，系统从"能用"推进到"好用"。

### 阶段边界

```text
Phase A（治理消化 + 执行闭合）
  │  全部是代码 + 操作，最有确定性
  │  综合 8.0 → 8.6
  ▼
Phase B（内容密实 + 判断资产化）
  │  需要真实使用系统，持续投料/提问/审阅
  │  综合 8.6 → 9.0
  ▼
Phase C（产品收敛 + 日常可用）
  │  产品打磨 + 体验优化
  │  综合 9.0 → 9.3
```

**关键判断**：Phase A 确定能做、Phase B 需要持续使用、Phase C 需要产品设计。三阶段全闭合才能稳到终极形态。

## 与当前版本的关系

当前版本（2026-04-16 评估，综合 **8.0/10**）已经具备：

- 九层架构全部存在且功能闭环
- 25 个 owner module / 33,416 行 Python / 314 tests / 92% coverage
- Obsidian 插件工作台（Product Shell v0.2.0）+ HTML 控制台备用
- 多协议 runtime（5 套协议 × 8 模板真正驱动 compile/query/review/nightly）
- judgment layer + 因果网络 + judgment 关联图谱
- safe execution layer（apply/revert/receipt/audit，3 receipts 已证明）
- 增量编译 8 阶段 dirty/clean + compile-state 持久化
- 自动化角色通过 CLI + systemd timer 覆盖

**基建完成度 8.5 / 内容牵引力 6.9。**

基建已经到了同类项目的天花板；瓶颈不在管线，在于管线还没有产出足够密度的真实知识、治理链还没有从"发现"走到"解决"。

所以这份文档不是说"现在已经做到"，而是定义：

**炼丹炉真正值得追求的最终形态，以及从现在到那里的三个阶段。**

## 一句话总结

炼丹炉最终不该只是一个会整理知识的 AI 工具，而应该是：

**一个把证据持续炼成概念、把概念持续炼成判断、把判断持续炼成可治理行动的认知操作系统。**
