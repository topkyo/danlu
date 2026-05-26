---
kind: thesis
status: historical-thesis
owner: tim
doc_role: thesis-not-runtime-spec
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
  - docs/Outputs.md
---

# Furnace Elixir (金丹机制)

> **文档状态（2026-05-20）**：本文件保留金丹终局 thesis 与历史设计动机；**当前 runtime 行为以** [Furnace Agent Architecture.md](./Furnace%20Agent%20Architecture.md) **与** [Furnace Evolution Mechanics.md](./Furnace%20Evolution%20Mechanics.md) **为准**。CLI 已实现 `alchemy-start/distill/finalize/promote` 最小链路，不等同于本文全部愿景已落地。

> **当前实现校准（2026-05-26）**：金丹最小主链路已经实现并有 acceptance 覆盖：`output/_candidates/elixirs/` 候选平面、`wiki/elixirs/` settled 平面、DAG/provenance gate、promote/revert/demote receipt，以及 Stage-3 “新丹引用旧丹 + wiki/derived anchor + trace up” 复利验证。本文剩余愿景主要指 LLM-backed semantic distillation、更高自治的金丹演化和长期自然运行 proof，不应再把基础金丹机制理解为纯计划态。

## 背景与设计动机 (Why)

在“炼丹炉”的日常运转中，复杂的知识构建（如推演一个 VLA 机器人架构、沉淀一套长期的投资逻辑）往往无法通过单轮 `ask` 或单篇 `raw` 文档完成。用户需要在一个主题下进行多轮提问、补充资料（Vault/URL/PDF），并与 LLM 共同反复迭代。

当前的抽象中，`judgment` 和 `decision` 能够刻画单一的判断或定案，但缺乏一种“高度凝练、可跨上下文复用、代表某一阶段性终极共识”的复合资产。我们需要一种机制，将散落在多轮会话和临时语料库（`active_corpus`）中的中间态，提纯为真正的长期复利节点。这就是“金丹”（Elixir）。

本说明文档作为长期 Source of Truth (SoT) 级别的 thesis，规范金丹的设计边界、实现归属与演进路线。所有金丹相关的具体机制设计（EP）均需符合本文档的约束。

## 什么是金丹 (What)

金丹（Elixir）是由用户与炼丹炉共同炼化出的**高度凝练的 decision / architecture / judgment 资产**。

它是什么：
- **真正的知识复利节点**：金丹本身可以被后续的炼化流程引用（新丹引用旧丹），形成知识杠杆。
- **确定的产物层凝结物**：带有完整推演来源（provenance）、置信度与反证（counter-evidence）。

它不是什么：
- **不是状态机的中间态**：它不是任务的进度记录，也不是会话本身。
- **不是对现有原子资产的替代**：它不是用来替换单页的 `judgment` 或 `decision`，而是它们的“高阶综合体”。
- **不是运行态的 Working Set**：`active_corpus` 只是金丹诞生过程中的 runtime 容器，金丹一旦凝结即归档于持久化层。

## 核心架构决策与实现归属 (Where)

遵守 Single Writer 与 Deterministic Baseline 约束，金丹的存储、沉淀和流转必须保持完全的文件系统可审计性。

### 独立存储路径：`wiki/elixirs/`
金丹的产物直接归属于 `wiki/elixirs/` 目录。
- 拒绝将其设计为 `judgment` 的一种附加状态（避免资产等级与生命周期混淆）。
- 拒绝将 `active_corpus` 原地升格（明确运行时状态与长期事实层的物理隔离）。
- 底层完全复用现有的 `file_back()` 机制、引证关系（citation）、YAML frontmatter，以及 review-apply-revert-audit 治理生命周期。

### Frontmatter Schema 草案
Elixir 的头部需要包含最小化的生命周期与血缘标记：
- `elixir_state`: `draft | distilling | settled | superseded`
- `provenance_corpus`: 关联的 `active_corpus` ID
- `derived_from`: 依赖的原始文档或前置金丹引用链
- `confidence_level`: 置信度评估

## 炼化工作流与 UX (How)

炼化流程本质上是：**用户提主题 → 挂载资料与 LLM 反复迭代 → 候选区评估 → 最终凝丹与晋升**。

标准的 CLI 命令序列如下：

```bash
# 1. 开启炼化主题，初始化 active_corpus
aiwiki alchemy start "主题"

# 2. 多轮迭代（自动串联前轮 output/elixir）
aiwiki ask "首问" --corpus <id>
aiwiki ask "追问1" --corpus <id>
aiwiki ask "追问2" --corpus <id>

# 3. 中途评估与资料补充
aiwiki review candidates --corpus <id>
aiwiki drop-url <url> 
aiwiki drop-pdf <file>
aiwiki ask "补料后重炼" --corpus <id>

# 4. 显式凝丹（生成 elixir candidate）
aiwiki alchemy distill <id>

# 5. 人工确认与晋升（入库 wiki/elixirs/）
aiwiki promote <elixir-id>

# 6. 跨周期复利（新丹引用旧丹）
aiwiki ask "新主题" --elixir <old-elixir-id>
```

## 进化与反哺机制 (Evolution & Feedback)

炼丹炉的演进分为三个层级，本 Thesis 明确各层级的系统边界：

1. **半自动反哺 (Q1)**
   - 所有的产出（无论是多轮问答的 output 还是提纯后的 elixir candidate）默认只进入 `output/_candidates/` 候选区。
   - **绝不自动写入 wiki**。必须经过用户的人工 review 或 nightly process 的显式评估后，通过 `aiwiki promote` 才能正式进入 `wiki/` 目录。
   - nightly 的角色从“自动晋升者”降级为“候选区管理员”（负责老化、降级、淘汰 candidate，将值得关注的候选推给人工）。

2. **自我进化边界 (Q2)**
   - **L1 知识自维护**：复用现有的 wiki 内部链接维护、摘要更新与冲突检测。
   - **L2 协议/Prompt 沉淀**：用户的 review 和纠正信号将被总结并沉淀到 `wiki/protocol-learnings/` 目录。后续相似主题的任务可以显式加载这些 learnings（作为 hint）。**系统绝不会自动修改底层的 schema 或系统级 prompt**，防止隐式漂移。
   - **L3 炉子能力自升级**：明确不在范围。保持代码/框架的决定论（deterministic baseline），不引入自我改写逻辑代码的危险机制。

## 演进路线图 (Roadmap)

金丹机制的实现分为三个严格递进的阶段：

### 阶段 1：串主题 (Chaining)
- **目标**：同主题多轮 `ask` 自动串联上下文，统一输出进 candidate queue。
- **验收标准**：第二轮 `ask` 能够无缝读取到前轮的 output；全程没有任何内容被自动写入 `wiki/` 层。

### 阶段 2：凝金丹 (Distillation)
- **目标**：从 candidate 链条中显式执行 `distill` 并 `promote` 出长期资产。
- **验收标准**：至少成功生成一个 `elixir` 文件，包含完整的 provenance；并且能够正确走完 promote / demote / revert 的完整生命周期（借鉴 concept_rewrite proposal 的状态机）。

### 阶段 3：L2 复利 (Compounding)
- **目标**：协议学习机制生效，金丹之间实现合规的引用。
- **验收标准**：同协议的 `ask` 能够显式加载 `protocol-learnings`；新生成的金丹能够引用旧金丹，且机制保证不会形成无限自循环的死锁。

## 核心风险与缓解策略

1. **运行态与知识层混淆**
   - *风险*：高频迭代时的状态数据污染了长期知识库。
   - *缓解*：`active_corpus` 及其游标只存在于 `.aiwiki/state/` 中，`promote` 命令是跨越运行态与持久态的唯一合法桥梁。

2. **LLM 幻觉污染 Wiki**
   - *风险*：LLM 生成看似合理实则谬误的“伪共识”。
   - *缓解*：强制启用 `output/_candidates/` 缓冲；晋升必须通过显式人审或 nightly 的高阈值复审；要求所有的 elixir 必须保留 citations 和 counter-evidence。

3. **金丹自循环 (Circular Reference)**
   - *风险*：新丹引用旧丹，旧丹的推演基础已被证伪，导致“空中楼阁”式的知识坍塌。
   - *缓解*：引用链必须是严格的有向无环图 (DAG)；新丹的推导不能仅仅依靠旧丹的结论，必须继续锚定底层的 `raw/` 或 `wiki/` 原始证据作为支撑。
   - *来源边界*：corpus candidate plane 由 `aiwiki promote` 维护；`file-back --kind derived` 是另一条独立路径，二者不互相注册。如需进入金丹链路，应先 promote 输出候选，再由 derived 锚定。

4. **协议学习变隐式 Prompt 漂移**
   - *风险*：过多的 learning 积累导致 LLM 行为难以预测，破坏 deterministic baseline。
   - *缓解*：只在 `wiki/protocol-learnings/` 记录经验，绝对不自动更新核心 schema 或系统 prompt；协议经验的采用必须是条件触发或显式挂载的。

5. **候选区堆积失控**
   - *风险*：由于半自动机制，`output/_candidates/` 中积累大量无人过问的废弃物。
   - *缓解*：赋权 nightly process 进行 aging 处理，定期降级、淘汰或归档过期 candidate。

## 非目标 (Non-Goals)

- **不做 L3 的系统级自动演化**：不让大模型去自动重构 aiwiki 的代码或改写核心 prompt 架构。
- **不做多端同步或 Hosted Service**：坚守 local-first、基于本地文件系统的单写入者（single writer）模式。
- **不引入 Heavy RAG Infra 或微调**：纯依赖 markdown 的高信噪比与文件结构进行上下文组装，不引入向量数据库集群或复杂的知识图谱中间件。

---

**TL;DR**: 金丹 (Elixir) 是炼丹炉基于单点事实层与半自动候选机制，将多轮人机交互提纯为长期复利资产的最终形态，它归属于 `wiki/elixirs/` 并驱动 L2 级别的系统进化。
