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

## 与当前版本的关系

当前版本已经具备：

- 五层主线
- Obsidian 插件工作台（Product Shell 默认入口）+ HTML 控制台（备用）
- 多协议 runtime（5 套协议真正驱动 compile/query/review/nightly）
- judgment layer + 因果网络 + judgment 关联图谱
- safe execution layer（apply/revert/receipt/audit）
- 自动化角色通过 CLI + systemd timer 覆盖

但距离这份“最终极形态”还差的是：

- 更硬的概念层（更多 hard concepts + 更密集的因果网络）
- 更资产化的判断层（judgment 数量和关联密度）
- 更成熟的执行治理（更多真实 receipt 积累）
- 更完善的 Obsidian 工作台（batch 操作 + context 自动推断）
- 真实高密度场景的长期压实

所以这份文档不是说“现在已经做到”，而是定义：

**炼丹炉真正值得追求的最终形态。**

## 一句话总结

炼丹炉最终不该只是一个会整理知识的 AI 工具，而应该是：

**一个把证据持续炼成概念、把概念持续炼成判断、把判断持续炼成可治理行动的认知操作系统。**
