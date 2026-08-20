---
title: "炼丹炉架构文档索引"
kind: "index"
status: "active"
updated_at: 2026-08-20
---

# 炼丹炉架构文档索引

本展示树不含内部执行计划、`docs/archive/` 史料和 `PROGRESS.md`。

## Active（当前 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) | **架构边界 SoT**：五层平面、single writer、provenance、drop/today/advanced 用户面 |
| [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) | **实现契约 SoT**：active corpus、金丹生命周期、现行 operator CLI |
| [Furnace Product Shell](<./Furnace Product Shell.md>) | **Obsidian Product Shell SoT**：一个输入端 + 一个输出端 + Advanced 抽屉；**Desktop-only** |
| [Furnace Runtime Operations](<./Furnace Runtime Operations.md>) | **运行手册 SoT**：watcher、确定性 nightly、显式 LLM ask、universal drop plan/execute、四 API 后端与 fail-closed 策略 |
| [AGOS-9-Scorecard](<./AGOS-9-Scorecard.md>) | **AgentOS 评分与 release gate SoT**：证据分层、blocking gate、本地 release 口径 |
| [Furnace Elixir](<./Furnace Elixir.md>) | 金丹机制产品思路 thesis（accepted） |
| [INSTALL](<./INSTALL.md>) | **安装指南**：源码安装 + `pip install -e .` 预览路径；PyPI 正式发布待定 |
| [CONTRIBUTING](<../CONTRIBUTING.md>) | **本展示仓**：可克隆使用，不接受外部 PR |
| [SECURITY](<../SECURITY.md>) | **安全披露**：私下邮件；勿在公开 issue 贴密钥 |
| [USER_GUIDE](<./USER_GUIDE.md>) | **用户指南**：日常 drop（含 plan/万能 payload）/ compile / ask / review 路径 |
| [DEVELOPER](<./DEVELOPER.md>) | **开发者指南**：owner map、verify targets、LLM/自动化细节 |
| [commercial/PRICING](<./commercial/PRICING.md>) | 商业定价与 SKU（首发仅询价、无公开标价） |
| [commercial/EULA](<./commercial/EULA.md>) | 商业许可条款草案与书面流程指针 |
| [commercial/BOUNDARIES](<./commercial/BOUNDARIES.md>) | 开源版 vs 商业版边界 + 商业 license 获取 |
| [commercial/PRIVACY](<./commercial/PRIVACY.md>) | local-first 隐私与 egress 声明 |
| [commercial/SUPPORT](<./commercial/SUPPORT.md>) | 支持通道与响应预期 |
| [commercial/COMPARE](<./commercial/COMPARE.md>) | 与常见知识工具对照 |
| [LICENSE](<../LICENSE>) | AGPL-3.0 / Commercial Dual License |
| [CHANGELOG](<../CHANGELOG.md>) | 版本变更记录 |

## 阅读顺序

1. 先看 [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) 建立世界观。
2. 再看 [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) 建立契约与实现边界。
3. 需要操作本机自动化时看 [Furnace Runtime Operations](<./Furnace Runtime Operations.md>)。
4. 当前评分 / release gate 看 [AGOS-9-Scorecard](<./AGOS-9-Scorecard.md>)。
5. 商业 demo 讲法看 [Furnace Investing Demo Pack Spec](<./Furnace Investing Demo Pack Spec.md>)。
6. 需要看 Product Shell 时再看 [Furnace Product Shell](<./Furnace Product Shell.md>)（Desktop-only；iPad/iOS 不支持全功能）。
