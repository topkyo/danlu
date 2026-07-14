---
title: "炼丹炉市场对标调研 2026Q2"
kind: "market-scan"
status: "active"
owner: "tim"
created_at: 2026-04-30
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
  - docs/archive/Furnace Next Direction Post-P4.md
---

# 炼丹炉 / aiwiki 市场对标调研 2026Q2

> 范围：2024–2026 年仍活跃的 local-first 个人 AI 知识 / agent / RAG 类产品
> 调研口径：基于 GitHub README、官网、HN / Reddit / 技术博客；未下载、未安装、未调用任何 API
> 不可比维度统一标记为 `n/a`
> 这份文档是 Round 58 subagent 调研结果落档，作为长期 SoT 留存

## 0. 一句话结论

市面上**没有**与炼丹炉同形态的对手。最接近的同质方向是 **Reor**（local-first markdown + AI PKM）和 **Khoj**（self-hostable AI second brain），但二者都不做"知识编译 + receipt + protocol multiplexing + 金丹"的组合；agent runtime 方向最像 thesis 的是 **Letta (MemGPT)**，但它做的是 stateful agent 而不是知识库 compiler。给单人投资 / 技术研发用户，**当前最像炼丹炉外形**的是 Reor + Obsidian Copilot 的组合形态，但都缺 provenance / 多协议 / 可回滚的工程化护栏。

---

## 1. 同质度最高的 3–5 个对手（详细对比）

挑选标准：local-first、文件级、个人知识 / 长期记忆为核心、非 SaaS-only。

### 1.1 Reor — `reorproject/reor`
- 链接：<https://github.com/reorproject/reor>
- 形态：Electron 桌面 PKM，directory-of-markdown，Ollama 本地 LLM + LanceDB 本地向量库，自动语义连边 + RAG Q&A
- 一句话差异化："Reor 是 Obsidian 加本地 RAG"，炼丹炉是"raw → wiki → output 的可审计知识 compiler"

### 1.2 Khoj — `khoj-ai/khoj`（~34k stars）
- 链接：<https://github.com/khoj-ai/khoj> / <https://khoj.dev/>
- 形态：self-hostable AI second brain，可索引本地 markdown / PDF / repo，支持 Obsidian / Notion 集成，自定义 agent，schedule automation，deep research
- 一句话差异化：Khoj 是"私人版 NotebookLM + agent"，炼丹炉强制 provenance / receipt / 金丹复利，Khoj 是 RAG-first，没有派生层 hash gate 和 L3 红线

### 1.3 Letta（前 MemGPT）— `letta-ai/letta`（~22k stars）
- 链接：<https://github.com/letta-ai/letta> / <https://www.letta.com/>
- 形态：stateful agent runtime，分层记忆（Core / Recall / Archival），Letta Code CLI，支持 sleep-time compute
- 一句话差异化：Letta 是"给 agent 加持久记忆的 OS"，炼丹炉是"给人类知识工作加可审计编译流水线"，agent 对炼丹炉是工具，对 Letta 是主体

### 1.4 henrydaum/second-brain（~472 stars）
- 链接：<https://github.com/henrydaum/second-brain>
- 形态：agentic OS over local files，连续索引（text / OCR / embeddings），hybrid search（lexical / semantic / SQL），`memory.md` + SQLite 做 durable memory，runtime 插件生成
- 一句话差异化：思想最接近——"local file intelligence as runtime"——但更偏 agent + 多模态 messaging，没有炼丹炉的派生分层、receipt、revert、protocol 多协议化

### 1.5 coleam00/second-brain-starter（~467 stars）
- 链接：<https://github.com/coleam00/second-brain-starter>
- 形态：Claude Code skill 生成的 PRD + memory layer（`SOUL.md` / `USER.md` / `MEMORY.md`），proactive assistant 蓝图，集成 Gmail / Slack / GitHub
- 一句话差异化："在 Claude Code 上长出的 second brain"，思路上最接近"single writer + 多协议"，但实质是 prompt skill / blueprint 而不是 runtime；没有 deterministic baseline、receipt、hash gate

### 详细对比表

| 维度 | 炼丹炉 | Reor | Khoj | Letta | henrydaum/second-brain | coleam00/second-brain-starter |
|---|---|---|---|---|---|---|
| Local-first / single-user | ✓ | ✓ | ◐（self-host 可，但产品定位也面向团队） | ◐（runtime 可本地，但 platform 侧 cloud-first） | ✓ | ✓（基于 Claude Code） |
| 文件层严格分层（raw / wiki / output） | ✓ | × | × | × | ◐ | ◐ |
| Deterministic baseline（不靠 LLM 也能跑） | ✓ | × | × | × | × | ×（依赖 Claude） |
| Provenance 强制 + audit stream | ✓ | × | ×（有 source citation 但非强制全链路） | ◐（有 message log，无业务级 provenance） | × | × |
| Receipt + revert + hash gate | ✓ | × | × | × | × | × |
| 显式 backend 选择（无 hidden routing） | ✓ | ◐（选 Ollama 模型） | ◐ | ◐ | ◐ | ×（绑定 Claude） |
| 多协议（一个炉子多个 protocol） | ✓ | × | ◐（custom agents） | ◐（多 agent 可建） | ◐（plugin） | × |
| 复合知识资产（金丹 / cross-cycle distillation） | ✓ | × | × | ◐（archival memory 可视为弱形式） | × | × |
| L3 自主权红线（proposal-only） | ✓ | n/a | × | × | × | × |
| 用户面"一输入一输出"约束 | ✓ | ◐ | × | × | × | × |
| 投资研究 / 技术研发场景定位 | ✓ | ◐（通用 PKM） | ◐ | ×（通用 agent） | × | × |
| 是否 hosted-service / multi-user | × | × | ✓（也 hosted） | ✓（cloud platform） | × | × |
| 是否 fine-tuning / heavy RAG infra | × | RAG（轻） | RAG（重） | × | RAG（中） | × |
| 主要技术栈 | Python stdlib + markdown + JSON manifest | Electron / TS + Ollama + LanceDB | Python + Django + Ollama / API | Python + PostgreSQL（pgvector） | 未知 | Markdown + Claude Code |
| Stars / 活跃度 | local | ~9k 级（2025 仍维护） | ~34k，活跃 | ~22k，活跃 | ~0.5k，活跃 | ~0.5k，活跃 |

---

## 2. 部分相似（同方向但不完全对标）的 5–8 个产品

| 产品 | 链接 | 主要功能 | 与炼丹炉的关系 |
|---|---|---|---|
| **AnythingLLM** | <https://github.com/Mintplex-Labs/anything-llm>（~59k） | 一体化 RAG 生产力工具，多用户、agent builder、MCP | 同是"私人/团队知识底座"，但 multi-user / hosted / RAG-first，不是 single-writer + provenance |
| **OpenWebUI** | <https://github.com/open-webui/open-webui>（~80k） | 本地 LLM 前端 + 文档 RAG，支持 Ollama | 是 chat UI 层，不是知识 compiler；没有派生层、receipt 概念 |
| **Smart Connections (Obsidian)** | <https://github.com/brianpetro/obsidian-smart-connections>（~4.9k） | embedding-based 语义搜索 + 关联笔记 | 只做检索关联，没有 raw→wiki→output 编译流水线 |
| **Copilot for Obsidian** | <https://github.com/logancyang/obsidian-copilot>（~6.8k） | vault chat、project mode、PDF/image/URL context | 用户面前端可对标 Obsidian 插件层；不是 runtime |
| **Smart Second Brain (Obsidian)** | <https://github.com/your-papa/obsidian-Smart2Brain> | local AI assistant + vault Q&A | 仅插件级 RAG，不做编译/审计 |
| **PrivateGPT** | <https://github.com/zylon-ai/private-gpt>（~55k） | 本地 RAG 框架，离线文档问答 | 纯 RAG infra，不做知识资产化、不做 protocol 多协议 |
| **GPT4All** | <https://github.com/nomic-ai/gpt4all>（~75k） | 本地 LLM 桌面客户端 + LocalDocs | 偏 LLM runner + 简单 RAG；和炼丹炉不在一个层级 |
| **CrewAI / AutoGen** | <https://github.com/crewAIInc/crewAI>（~50k） / <https://github.com/microsoft/autogen> | 多 agent 编排框架 | 和"protocol runtime"思想有部分重合，但完全不管知识资产、文件分层、provenance |
| **CaviraOSS/OpenMemory** | <https://github.com/CaviraOSS/OpenMemory>（~3.4k） | 给 LLM 应用的 local persistent memory store | 替代 archival memory，但不做编译、不做派生输出 |
| **doobidoo/mcp-memory-service** | <https://github.com/doobidoo/mcp-memory-service>（~1.4k） | REST + 知识图谱 + 自动 consolidation 的 agent memory | 同上，是组件而非完整 runtime |

---

## 3. 完全不是对标但常被拿来比较的（澄清）

| 产品 | 链接 | 为什么常被混淆 | 实际差异 |
|---|---|---|---|
| **Aider** | <https://github.com/Aider-AI/aider>（~44k） | 都是"local-first + 终端 + AI 工程化" | Aider 是 AI pair programming，问题域是代码 diff，不是知识库 |
| **Continue.dev** | <https://github.com/continuedev/continue>（~33k） | 同样强调"source-controlled AI"、可审计 | Continue 现在定位是 CI 中的 AI checks（PR 质量门禁），完全不做个人知识沉淀 |
| **Open Interpreter** | <https://github.com/openinterpreter/open-interpreter> | 同样 local desktop agent | 是任务执行型 desktop agent（写代码、操作文件），不是知识 compiler |
| **Mem.ai / Tana / Reflect / Capacities** | mem.ai / tana.inc / reflect.app / capacities.io | 都喊"AI second brain" | hosted SaaS，闭源，no local-first，no provenance，无工程级护栏 |
| **Notesnook** | <https://notesnook.com/> | 有人当 Obsidian + 隐私替代 | E2EE 笔记，没有 AI knowledge runtime；与炼丹炉不在一个层级 |

---

## 4. 综合判断

### 4.1 炼丹炉的独特价值（市面上目前没看到的组合）

按重要性排序：

1. **知识 compiler 模型**：raw → wiki/sources → wiki/derived → output 的强分层 + 派生不可覆盖原始 source。市面 PKM/RAG 都没把"原料和派生结论"在文件级隔离，更没有 hash gate 把派生回溯锁死
2. **Receipt + revert + universal audit stream**：所有 LLM 触发的写入都有 receipt 可回滚，整条 stream 可审计。市面除 enterprise governance 工具（Latitude / Monitaur）外，个人侧没有人做这个
3. **Deterministic baseline**：compile / lint / nightly 不依赖 LLM 也能跑——这是"工程化稳定性"层面的根本差异。Reor、Khoj、Letta 关掉模型几乎全瘫，炼丹炉关掉模型仍然能维护知识库
4. **L1 / L2 / L3 自主权红线 + L3 proposal-only**：没看到任何 personal AI 产品把 prompt / policy 改动当作"必须人工 accept 的提案"来管。这是炼丹炉为长期可信度做的隔离
5. **多协议同炉**（general / investing / research / product / ops）：一份编译 substrate 上跑多个领域协议；CrewAI 等是 agent crew，不是知识 substrate 复用
6. **金丹（Elixir）**：跨周期 distillation 的复合知识资产，独立生命周期。市面最接近的是 Letta 的 archival memory 和 Khoj 的 deep research report，但都没有"draft → distilling → candidate → settled → superseded"的资产生命周期
7. **Heavy / Light alchemy 双 lane + 一输入一输出 UI 约束**：在产品形态上做了"事件驱动深炼 + 定时定额维护"+ 单入口单出口的克制；多数对手是堆 feature，不做这种节制

### 4.2 炼丹炉的弱项（对手做得更好的）

诚实给：

1. **检索 / 语义关联体验**：Smart Connections、Reor 在"在写作时实时 surface 相关笔记"上是产品级体验，炼丹炉目前是 batch 编译思路，实时关联不是核心
2. **生态与 GUI**：Khoj、AnythingLLM、OpenWebUI 有现成的 chat UI、移动端、浏览器扩展、Slack/Telegram 集成；炼丹炉用 Obsidian 做前端，扩展面窄
3. **多模态 / 语音 / 自动捕获**：Mem.ai 的 voice + meeting + clipper、Khoj 的 schedule automation、henrydaum/second-brain 的多渠道 ingestion——炼丹炉目前主要靠 drop-* 入口手动投喂
4. **多 backend 抽象成熟度**：LiteLLM / OpenWebUI / AnythingLLM 已经有非常成熟的 provider 池；炼丹炉是显式手动 backend（这是 thesis 选择，但体验上更重）
5. **stateful agent 能力**：Letta 在"agent 自我演进 + 长期 memory + sleep-time compute"上是研究级；炼丹炉目前不是 agent-first
6. **社区与 stars**：上述对手 stars 多在万级到十万级，炼丹炉是单人项目级别，生态网络效应基本为 0

### 4.3 是否有"完全打中同一个用户群"的对手？

**没有**，但有部分重合：

- **打中"local-first + 不愿被 SaaS 锁定 + 自己的笔记自己审计"**：Reor、Khoj（self-host）、Smart Connections + Obsidian Copilot 组合都是同一拨人，但他们追求的是"私有 RAG"，炼丹炉追求的是"可审计的长期复利"。两群人有重叠但 thesis 不同
- **打中"投资研究 / 技术研发的 power user"**：这一群目前几乎没有专门的产品。最接近的是用 Obsidian + Smart Connections + Copilot + 自己魔改 dataview 的 DIY 玩家，以及 Khoj 的 deep research 用户。**这是炼丹炉真正的空白市场**
- **打中"想要 stateful agent 但要数据自己控制"**：是 Letta + henrydaum/second-brain 的用户群，与炼丹炉部分重叠但偏 agent-first，不一定接受"deterministic baseline + 编译流水线"的克制

### 4.4 给单人投资研究 / 技术研发用户，最像炼丹炉的是哪个？

**单选**：没有完全像的；硬要选一个最接近 thesis 的，是 **Khoj**——它有"AI second brain + 自定义 agent + research + self-host"的全套，覆盖了"投研 + 技术研发"的检索面，是当前最容易让用户产生"和炼丹炉感觉接近"的产品

但要诚实指出 Khoj 与炼丹炉的根本差距：
- 没有 raw / derived 分层，派生结论可能覆盖原始事实层
- 没有 receipt / revert / hash gate
- 没有 L3 proposal-only 红线
- 没有金丹这种跨周期资产生命周期
- 偏 RAG-first，不是 "deterministic baseline + 显式 LLM run-*"

**外形最像**（但 thesis 不同）：**Reor**——markdown + Ollama + 本地向量库，零 SaaS，单用户，体验上离"个人本地知识库"最近

**思想最像**（但实现不同）：**henrydaum/second-brain**——也把"local file intelligence + durable memory"当作 OS 来做，是少数承认"知识库就是 runtime"的项目

**runtime 抽象最像**（但用途不同）：**Letta / MemGPT**——分层 memory + stateful runtime，是少数把"长期记忆"当一等公民的项目

> 综合：炼丹炉的"知识 compiler + receipt + protocol multiplexing + 金丹"组合在 2026 Q2 仍然是个空位，单人投研/研发用户目前要么选 Khoj 接受 RAG-first，要么自己用 Obsidian 拼配 Reor / Smart Connections / Copilot

---

## 5. 文档生命周期

- 当前版本基于 2026-04-30 公开信息汇总（subagent 调研）
- 应每 6-12 个月复评一次（可作为 Round X 任务）
- 当出现新的同质对手（满足 §1 5/13 维度以上重合）时，立刻补到本文档
- 不修改 §4.1 7 条独特价值，除非有真实对手挑战该维度
