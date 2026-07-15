---
title: "炼丹炉产品定价与包装"
kind: "commercial"
status: "active"
updated_at: "2026-07-14"
related_docs:
  - docs/commercial/BOUNDARIES.md
  - docs/commercial/SUPPORT.md
  - docs/commercial/PRIVACY.md
  - docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md
---

# 炼丹炉产品定价与包装

> 本文件说明炼丹炉的 SKU 结构、license 边界与服务选项。具体价格以销售页面或邮件报价为准；本文只给出 tier 结构与包含/不包含矩阵。

## 1. 产品包装

| SKU | 形态 | 一句话说明 |
|-----|------|------------|
| **Desktop runtime license** | 主产品 | 在本地 Obsidian vault 上运行 `aiwiki` runtime 的商业 license。 |
| **Investing Demo Pack 模板** | 内容模板 | 虚构、脱敏的投研演示 fixture，展示 `raw → wiki → output → receipt` 完整链路。 |
| **安装陪跑** | 单次服务 | 帮助用户完成新 vault 搭建、Obsidian 配置、LLM provider 配置与首次 dogfood 运行。 |

> Demo Pack 中的所有公司、数据、日期均为虚构，仅用于演示产品工作流，不构成任何投资建议。详见 `demos/investing-demo-pack/COMPLIANCE.md`。

## 2. 首发 ICP

**单人/小团队 fundamental researcher**

典型画像：
- 需要长期跟踪公司、赛道、论文或技术决策；
- 希望把碎片资料沉淀成可追溯的判断资产；
- 愿意维护本地 vault，接受 Obsidian + CLI 的工作方式；
- 对 RAG 问答不满足，需要 provenance、receipt 和跨周期复审能力。

## 3. 定价 Tier 结构（不给具体数字）

### Free — 开源 AGPL-3.0
- 费用：免费
- License：AGPL-3.0
- 包含：完整 runtime CLI、Product Shell 插件、五层主线、五协议、治理链、金丹机制
- 支持：GitHub issues 社区支持
- 适用：愿意开源合规、自行维护的个人开发者或研究者

### Personal — 商业 license
- 费用：一次性或年度订阅（具体见销售页）
- License：商业 license，免 copyleft 约束
- 包含：Free 版全部功能 + 商业 license 授权
- 支持：邮件支持，48 小时响应
- 适用：个人用户，需要闭源/商业使用场景

### Pro — 商业 license + 优先支持 + Demo Pack 模板
- 费用：年度订阅（具体见销售页）
- License：商业 license
- 包含：Personal 版全部权益 + Investing Demo Pack 模板 + 邮件 24 小时响应 + 优先 LLM 配置支持
- 适用：需要快速上手投研工作流、需要模板参考的小团队或专业个人

### 陪跑服务 — 安装配置 + dogfood 陪跑
- 费用：按次计费（具体见销售页或邮件询价）
- 内容：
  - 新 vault 搭建与 Obsidian 基础配置
  - LLM provider（deepseek-api / opencode-api / openai-api / anthropic-api）配置指导
  - 第一次 `drop` / `compile` / `run-ask` / `nightly` 陪跑
  - 常见问题排查
- 交付：一次线上 60–90 分钟会话 + 书面配置摘要
- 适用：非技术用户或团队首次落地

## 4. 包含 / 不包含矩阵

| 能力 | Free | Personal | Pro | 陪跑服务 |
|------|:----:|:--------:|:---:|:--------:|
| `aiwiki` runtime CLI 全部功能 | ✓ | ✓ | ✓ | — |
| Product Shell Obsidian 插件 | ✓ | ✓ | ✓ | — |
| 五层主线（raw / wiki / machine memory / schema / outputs） | ✓ | ✓ | ✓ | — |
| 五协议（general / investing / research / product / ops） | ✓ | ✓ | ✓ | — |
| 治理链（review / aging / escalation / repair / nightly） | ✓ | ✓ | ✓ | — |
| 金丹机制（alchemy / elixir / promote / revert） | ✓ | ✓ | ✓ | — |
| 商业 license（免 copyleft） | × | ✓ | ✓ | — |
| Investing Demo Pack 模板 | × | × | ✓ | ✓（可选购） |
| 邮件支持 48h | × | ✓ | — | — |
| 邮件支持 24h | × | × | ✓ | — |
| 安装配置 + 首次 dogfood 陪跑 | × | × | × | ✓ |
| 后续升级、定制开发、行业 protocol pack | × | × | × | 另行询价 |

说明：
- "—" 表示该 tier 不直接对应此项，或服务项本身需单独购买。
- 所有版本均依赖用户自行配置 LLM provider 与 API key；炼丹炉不托管模型、不代调用。

## 5. 不可宣称清单

以下能力或承诺**任何 tier 均不包含**，销售、演示、文档中均不得宣称：

| 不可宣称项 | 原因 / 正确口径 |
|---|---|
| **投资建议** | 炼丹炉是研究资料组织、provenance、judgment 与 review 工作流，不提供 buy / sell / hold / 仓位 / 择时建议。 |
| **自动交易** | 不连接交易所、不生成交易信号、不执行任何买卖操作。 |
| **14-day / 30-day proof** | 长期自然运行证明需要真实 wall-clock 证据，未发生时不得宣称已通过。当前 release gate 为 3-day live proof。 |
| **移动端全功能** | Product Shell 正式支持 Desktop Obsidian only；iPad/iOS 不做全功能直移植。 |
| **hosted service / multi-user sync** | 炼丹炉是 local-first 单用户 runtime，不提供托管服务或多人实时同步。 |
| **离线全功能** | Local-first 不等于 offline-only；LLM provider、web fetching（`drop-url`）、notification webhook 等需要网络。 |
| **确定性收益或性能承诺** | 不承诺研究产出数量、判断准确率或任何可量化的投资/研发回报。 |

> 以上清单从 `docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md` §2.5 及 `demos/investing-demo-pack/COMPLIANCE.md` 迁入，是商业化沟通的底线。

## 6. 购买路径

- 开源版：直接克隆仓库，遵守 AGPL-3.0。
- 商业 license / Pro / 陪跑服务：邮件联系 `commercial@example.com`（占位符，待替换为真实地址）。
- 企业批量授权或行业 protocol pack 定制：邮件询价。

## 7. 变更记录

- 2026-07-14：初版，与商业化清理计划同步落盘。
