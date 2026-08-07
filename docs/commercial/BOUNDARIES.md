---
title: "炼丹炉开源版与商业版边界"
kind: "commercial"
status: "active"
updated_at: "2026-07-15"
related_docs:
  - docs/commercial/PRICING.md
  - docs/commercial/EULA.md
  - docs/commercial/PRIVACY.md
  - docs/commercial/SUPPORT.md
  - AGENTS.md
---

# 炼丹炉开源版与商业版边界

> 本文明确炼丹炉开源版与商业版各自包含什么、不卖什么，与 `AGENTS.md`「稳定约束 / 非目标」对齐。

## 1. 开源版（AGPL-3.0）包含

开源版是完整的 local-first runtime，不阉割核心功能：

- **Runtime CLI**：`aiwiki` 全部命令，包括 `drop`、`today`、`advanced` 及其下全部 operator 命令（含 `metrics` / `compile` / `review-page` 等）。
- **Product Shell 插件**：Obsidian 插件源码与 release bundle，见 `.obsidian/plugins/furnace-product-shell/`。
- **五层主线**：`raw / wiki / machine memory / schema / outputs` 完整编译与治理链路。
- **单 runtime 协议**：`general` only；旧 vault 非 `general` state 一次性迁移，不再提供多 protocol 切换 CLI。
- **治理链**：`review-page` / `file-back` / `run-nightly` 与 aging / escalation / repair；L3 `apply` / `revert` 等产品 CLI 已删，审计走 library receipt。
- **金丹机制**：`advanced alchemy start|distill|finalize|promote`（compat：`alchemy-*`）及 elixir 生命周期管理。
- **Deterministic baseline**：不依赖 LLM 也能运行的 `compile`、`lint`、本地统计等路径。
- **Receipt / revert / hash gate**：所有事实层 mutation 必须写 receipt、可审计、可回滚。

> 开源版功能完整，但需遵守 AGPL-3.0 的 copyleft 义务。

## 2. 商业版增量

商业版在开源版基础上增加**授权、模板、服务与未来行业 pack**，不增加核心 runtime 独占功能：

| 增量项 | 说明 |
|--------|------|
| **商业 license** | 免 copyleft，允许闭源/商业使用。 |
| **Investing Demo Pack 模板** | 虚构脱敏的投研 fixture，演示完整工作流。见 `demos/investing-demo-pack/`。 |
| **行业 protocol pack（未来）** | 针对特定行业（如生物医药、半导体、能源）的 schema / prompt / judgment 模板。 |
| **安装陪跑服务** | 单次服务，帮助完成 vault 搭建、Obsidian 配置、LLM 配置与首次 dogfood。 |
| **优先 LLM 配置支持** | Pro 用户获得 24h 邮件响应与 provider 配置指导。 |

> 不存在"商业版独占 runtime 功能"。所有代码级能力均开源；商业版卖的是 license、模板、服务与响应速度。

## 3. 明确不卖

以下产品形态**不在炼丹炉路线图上，也不接受定制开发报价**：

| 不卖 | 说明 |
|------|------|
| **Hosted service / SaaS** | 炼丹炉是 local-first、用户自托管的 runtime。 |
| **Multi-user sync / 协作** | 运行模型是 `single writer, many readers`，不支持多人实时协同。 |
| **投资建议 / 投顾服务** | 不提供 buy/sell/hold、仓位、择时、组合配置建议。 |
| **自动交易 / 信号服务** | 不连接交易所、不产生交易信号、不执行任何金融操作。 |
| **移动端全功能** | Product Shell 支持 Desktop Obsidian only；iPad/iOS 不做全功能直移植。 |
| **14/30-day proof 承诺** | 长期自然运行证明只能由真实 wall-clock 证据产生，不可销售或预售。 |
| **Heavy RAG infra / 向量数据库托管** | 技术栈保持 stdlib-first、markdown + JSON manifest，不引入重型 RAG 基础设施。 |
| **Fine-tuning / 模型训练服务** | 不收集用户数据用于模型训练，也不提供 fine-tuning 服务。 |

## 4. 与 AGENTS.md「稳定约束 / 非目标」对齐

`AGENTS.md` 中的稳定约束同样构成商业版边界：

- 技术栈：Python 3.10+, stdlib-first, markdown + JSON manifest。
- 运行模型：`single writer, many readers`。
- `raw/` 是唯一事实输入层；`wiki/sources/` 与派生层（`wiki/judgments/` 等）严格分层。产品回流默认 judgment；`wiki/derived/` 无现行 runtime writer（legacy 只读锚点）。
- 派生输出不能覆盖原始 source pages；所有结论都应保留 provenance。
- `decision / judgment / execution` 层必须保持可审计、可回滚、可追溯。
- 非目标：hosted service, multi-user sync, heavy RAG infra, fine-tuning。

商业版不会为付费用户突破以上约束。定制开发仅限于：
- 行业 protocol pack（schema / prompt / judgment 模板）；
- 私有部署脚本适配；
- 与企业现有 Obsidian 工作流的集成咨询。

## 5. 商业 license 获取方式

商业 license **不**写在本仓库 `LICENSE` 文件的 AGPL 正文里；开源默认条款始终是 AGPL-3.0。条款草案与流程指针见 `docs/commercial/EULA.md`。

获取流程：

1. 邮件联系 `topkyoxp@gmail.com`，说明用途、用户数、是否需要行业 pack。
2. 收到报价与商业许可草案后，签署书面协议（首发仅询价、无公开标价，见 `PRICING.md`）。
3. 持有生效商业许可期间，可按该协议使用本软件，而不受 AGPL copyleft 约束。
4. 未签署商业许可前，必须遵守仓库 `LICENSE` 中的 AGPL-3.0。

- 个人/小团队授权：同上邮件通道。
- 企业批量授权：邮件询价，提供预期用户数量与使用场景。
- 开源合规使用：直接遵循仓库 `LICENSE` 文件（AGPL-3.0）。

## 6. 变更记录

- 2026-07-15：§5 指向 `docs/commercial/EULA.md` 与真实邮箱 `topkyoxp@gmail.com`；去掉占位符表述。
- 2026-07-15：补充商业 license 获取流程与 `LICENSE` copyright / dual-license 头说明。
- 2026-07-14：初版，明确开源版功能完整、商业版增量为 license / 模板 / 服务。
