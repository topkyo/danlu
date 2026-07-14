---
title: "炼丹炉支持服务说明"
kind: "commercial"
status: "active"
updated_at: "2026-07-14"
related_docs:
  - docs/commercial/PRICING.md
  - docs/commercial/BOUNDARIES.md
  - AGENTS.md
---

# 炼丹炉支持服务说明

> 本文说明不同 tier 用户的支持渠道、响应时间与不支持的边界。

## 1. 支持渠道

| 渠道 | 适用对象 | 说明 |
|------|----------|------|
| **GitHub issues** | 开源用户 | 仓库公开 issue tracker，用于 bug 报告、功能讨论与社区问答。 |
| **邮件支持** | Personal / Pro / 陪跑用户 | 联系 `support@example.com`（占位符，待替换为真实地址）。 |
| **陪跑专属会话** | 购买陪跑服务的用户 | 预约线上 60–90 分钟会话，含配置摘要。 |

## 2. 响应 Tier

| Tier | 对象 | 响应时间 | 支持范围 |
|------|------|----------|----------|
| **Free** | AGPL-3.0 开源用户 | 社区 best-effort，无 SLA | GitHub issues 社区互助 |
| **Personal** | 商业 license 个人用户 | 邮件 48 小时 | runtime 使用、license 问题、一般配置 |
| **Pro** | 年度订阅 Pro 用户 | 邮件 24 小时 | Personal 范围 + Demo Pack 模板 + 优先 LLM 配置支持 |
| **陪跑服务** | 购买单次陪跑用户 | 专属会话 + 会后 48 小时邮件跟进 | 安装配置、首次 dogfood、基础排错 |

> 响应时间指工作时间内首次回复时间，不含节假日。复杂问题可能需要多次往返。

## 3. 不支持范围

以下问题**不在支持服务范围内**，即使付费用户也不承诺解决：

| 不支持项 | 说明 |
|----------|------|
| **Hosted 部署** | 炼丹炉不提供托管服务，不支持代为部署到云服务器。 |
| **Multi-user 协作** | 运行模型是 `single writer, many readers`，不支持多人实时协同配置。 |
| **移动端全功能** | Product Shell 支持 Desktop Obsidian only；iPad/iOS 不做全功能直移植。 |
| **投资建议** | 不提供 buy/sell/hold、仓位、择时、组合配置建议。 |
| **自动交易集成** | 不连接交易所、不产生交易信号、不执行金融操作。 |
| **LLM provider 账号问题** | API key 开通、计费、额度、账号封禁等问题需联系对应 provider。 |
| **第三方 Obsidian 插件冲突** | 可尽力提供排查思路，但不保证与所有第三方插件兼容。 |
| **用户设备/操作系统底层故障** | 如系统权限、磁盘损坏、网络防火墙等超出产品范围的问题。 |

## 4. 已知环境耦合问题（用户视角）

以下测试/行为在特定环境下可能失败或超时，属于已知环境耦合问题，不影响产品核心功能：

| 问题 | 表现 | 说明 |
|------|------|------|
| Obsidian workspace 默认布局差异 | `test_obsidian_workspace.test_workspace_defaults_open_home_and_furnace_center` 可能与测试期望不一致 | `.obsidian/workspace.json` 是 Obsidian 保存过的真实布局，与默认模板可能不同。 |
| `drop-url` browser 渲染超时 | `test_drop.test_fetch_url_raises_when_no_text_can_be_recovered` 在无网环境下可能 ~45s 超时 | 环境安装了真实 Chrome 时会尝试渲染；依赖网络状态。 |

> 以上两项来自 `AGENTS.md` Cursor Cloud specific instructions，从开发者视角迁入为用户可见说明。

## 5. 问题提交建议

为提高支持效率，请提供：

1. 运行的完整命令（含 `--root` 路径可脱敏）。
2. `aiwiki` 版本或分支名。
3. 操作系统与 Python 版本。
4. 相关日志或 receipt 文件路径（注意脱敏 API key）。
5. 已尝试的排查步骤。

## 6. 变更记录

- 2026-07-14：初版，定义 Free/Personal/Pro/陪跑四级支持响应与不支持范围。
