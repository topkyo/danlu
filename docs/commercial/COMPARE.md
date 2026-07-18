---
title: "炼丹炉竞品对比"
kind: "commercial"
status: "active"
updated_at: "2026-07-14"
related_docs:
  - `docs/archive/Furnace Market Scan 2026Q2.md`
  - docs/commercial/PRICING.md
---

# 炼丹炉竞品对比

> 本页面向潜在客户，说明炼丹炉与常见 local-first / AI 知识产品的差异。只讲差异化，不暴露弱项、不做 stars 对比、不评论单人项目规模。

## 1. 对比维度

| 维度 | 炼丹炉 | 典型 RAG/AI 笔记产品 | 典型 LLM-Wiki 轻量实现 |
|------|--------|----------------------|------------------------|
| **知识复利 vs RAG 问答** | 把原料持续编译成可追溯的判断资产；不是一次性问答。 | 多为单次 RAG 问答或检索增强写作。 | 多为 agent/skill 直接改 markdown wiki。 |
| **Production runtime** | Deterministic baseline + 显式 LLM；receipt / revert / L3 红线。 | 通常 chat-first，无业务级 receipt。 | 常依赖单一 coding agent；缺独立 verify/CI 契约。 |
| **Provenance 可追溯** | 每个派生结论都能回溯到 `raw/` 与 `wiki/sources/` 中的原始材料。 | 通常只有 source citation，无文件级全链路 provenance。 | 有分层意识，但治理深度不一。 |
| **Receipt 可审计** | 所有 LLM 触发的写入都生成 execution receipt，可回滚、可审计。 | 通常只有消息日志或运行记录，无业务级 receipt。 | 少见等价物。 |
| **金丹跨周期** | 支持 `draft → distilling → candidate → settled → superseded` 的跨周期知识资产。 | 多数产品没有显式的 cross-cycle distillation 生命周期。 | 通常停在 entity/concept 页。 |
| **单 runtime 协议** | 一份 `general` 编译 substrate + schema 扩展；不再售卖多 protocol 切换面。 | 多为通用模板或自定义 agent，非 substrate 级复用。 | 多为单 schema 文档。 |
| **Local-first 离线** | Deterministic baseline 不依赖 LLM 也能维护知识库；数据默认本地。 | 多数产品关闭模型后功能大幅受限或为 chat-first。 | 视实现而定。 |

> 对 2026「LLM Wiki」浪潮：炼丹炉对齐同一模式原点，差异在 **可验证 runtime + 治理**，而不是插件安装速度或 skill 体积。

## 2. 与主要对手的关系

### Reor — `reorproject/reor`
- **形态**：Electron 桌面 PKM，本地 markdown + Ollama + LanceDB 向量库，自动语义连边 + RAG Q&A。
- **一句话关系**：Reor 更像"Obsidian + 本地 RAG"；炼丹炉是"raw → wiki → output 的可审计知识 compiler"。
- **炼丹炉差异**：严格分层、provenance、receipt、金丹生命周期。

### Khoj — `khoj-ai/khoj`
- **形态**：Self-hostable AI second brain，索引本地 markdown/PDF/repo，支持自定义 agent、schedule automation、deep research。
- **一句话关系**：Khoj 是"私人版 NotebookLM + agent"；炼丹炉强制 provenance / receipt / 金丹复利。
- **炼丹炉差异**：
  - 派生层不覆盖原始事实层；
  - receipt / revert / hash gate；
  - L3 proposal-only 红线；
  - 金丹跨周期资产生命周期。

### Obsidian Copilot — `logancyang/obsidian-copilot`
- **形态**：Obsidian 插件，vault chat、project mode、PDF/image/URL context。
- **一句话关系**：Copilot 是优秀的前端 AI 插件层；炼丹炉是底层 runtime + 治理链。
- **炼丹炉差异**：提供文件级编译、治理、审计、revert 等插件不具备的工程化护栏。

### Smart Connections — `brianpetro/obsidian-smart-connections`
- **形态**：Obsidian 插件，embedding-based 语义搜索 + 关联笔记。
- **一句话关系**：Smart Connections 擅长"在写作时实时 surface 相关笔记"；炼丹炉擅长"长期知识资产的沉淀与复审"。
- **炼丹炉差异**：批处理编译、判断资产、receipt、跨周期 revisit。

## 3. 炼丹炉独有价值

1. **知识 compiler**：`raw → wiki/sources → wiki/derived → output` 的强分层，派生不可覆盖原始 source。
2. **Receipt + revert + universal audit stream**：所有写入可审计、可回滚。
3. **Deterministic baseline**：不依赖 LLM 也能跑 `compile / lint / nightly`。
4. **Protocol multiplexing**：一份 substrate 支持多领域协议。
5. **金丹（Elixir）**：跨周期 distillation 的复合知识资产，有独立生命周期。

## 4. 不包含

本页不讨论：

- 炼丹炉的弱项自评；
- 各项目 stars 数量或社区规模对比；
- 单人项目与团队项目的规模对比；
- 投资回报或性能排名。

> 详细市场对标与客观弱项分析见 [`docs/archive/Furnace Market Scan 2026Q2.md`](<../archive/Furnace Market Scan 2026Q2.md>)（内部 SoT，不对外销售使用；该 doc 已 archive）。

## 5. 变更记录

- 2026-07-15：补充 vs LLM-Wiki 轻量实现列；明确 production runtime 定位。
- 2026-07-14：初版，对外销售口径，只讲差异化。
