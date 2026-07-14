---
title: "Furnace Investing Demo Pack Spec"
kind: "spec"
status: "draft"
updated_at: 2026-07-14
---

# Furnace Investing Demo Pack Spec

## Goal

用 10 分钟讲清炼丹炉的 **知识复利**：一份投资材料进入 `raw/` 后，如何被编译成可追溯 source page、沉淀为 judgment，并在跨周期复盘中升级或反证为 elixir / 失效条件，而不是展示“AI 给答案”。

本文件只定义 Demo Pack 规格，不包含真实 vault 数据，不声称已有公开可售案例。

## 最小素材

Demo Pack 使用脱敏材料，至少覆盖 3 类输入：

1. **公司周期材料**：年报 / 季报 / earnings transcript 的脱敏摘录，用于建立原始 thesis 与关键假设。
2. **产业与竞争材料**：行业报告 / 竞品变化 / 渠道访谈的脱敏摘录，用于补充驱动因素和外部对照。
3. **反证或风险材料**：监管变化 / 价格战 / 财务异常 / 管理层口径变化的脱敏摘录，用于触发 judgment review、invalidation 或 elixir 降级。

素材要求：

- 保留来源类型、日期、主题和引用关系。
- 删除公司敏感名、未公开数据、个人信息和任何可反推出客户身份的信息。
- 不补造“真实收益”“真实持仓”“真实交易结果”。

## Thesis 跨周期故事结构

10 分钟 demo 建议按 5 幕组织：

1. **投入材料**：展示 3 类脱敏材料进入 `raw/inbox/` 或 `raw/assets/`。
2. **编译成证据**：展示 `wiki/sources/` 中保留 provenance 的 source page，以及与 thesis 相关的概念 / 引用。
3. **形成 judgment**：展示 `wiki/judgments/*.md` 如何记录 thesis、catalyst、risk、invalidation 与 review cadence。
4. **跨周期复盘**：用第二期材料展示 judgment 被复审，哪些假设增强、哪些变弱、哪些进入待审或失效。
5. **知识复利**：展示 settled elixir 或 candidate elixir 如何复用旧 judgment / source，而不是重新从零问 LLM。

## 必须露出的路径类型

Demo 截图或视频中必须露出路径类型，但不得露出敏感内容：

| 类型 | 路径示例 | 目的 |
|---|---|---|
| Source provenance | `wiki/sources/*.md` | 证明结论可追溯到脱敏原料 |
| Judgment asset | `wiki/judgments/*.md` | 展示 thesis / risk / invalidation 的结构化沉淀 |
| Elixir asset | `wiki/elixirs/*.md` 或 `output/_candidates/elixirs/*.md` | 展示可复用判断资产或待升级候选 |
| Execution receipt | `output/control/execution-receipts/*.json` | 证明一次生成 / promote / review 有可审计 receipt |
| Run output | `output/reports/*.md` 或相关 `output/control/*.json` | 展示 Product Shell 可打开的结果入口 |

## 合规话术

Demo Pack 必须显式出现以下口径：

- **非投资建议**：炼丹炉展示的是研究材料组织、判断资产沉淀和复盘流程；不提供买卖建议、收益承诺、组合优化、行情、回测或自动交易。
- **LLM 数据流**：用户配置的 LLM provider 会接收为当前任务构造的 prompt / context；API key 存在本机配置中，但被发送给第三方模型的内容取决于运行任务和 provider。敏感材料进入 demo 前必须脱敏。
- **local-first 不等于离线**：vault、receipt、wiki 和 output 默认在本地文件系统；但 LLM provider、网页抓取、通知 webhook 等能力可能访问网络。离线只能支持不依赖外部模型 / 网络的本地读写与 deterministic 检查。
- **长期 proof 不伪造**：14/30-day natural proof 只能等待真实 wall-clock 运行窗口；当前 Demo Pack 不得把尚未自然发生的长期窗口标为 PASS。

## 交付物清单

规格级 Demo Pack 至少包含：

1. **截图脚本**
   - Product Shell 输入端：投料 / ask / today。
   - `wiki/sources/` provenance。
   - `wiki/judgments/` thesis 与 review 状态。
   - `wiki/elixirs/` 或 `output/_candidates/elixirs/` 的复用关系。
   - `output/control/execution-receipts/` 的 receipt 索引或单条脱敏 receipt。
2. **10 分钟视频脚本**
   - 0:00-2:00 投入材料与 source provenance。
   - 2:00-4:00 thesis / catalyst / risk / invalidation。
   - 4:00-6:00 第二周期材料触发复审。
   - 6:00-8:00 receipt / judgment / elixir 链路。
   - 8:00-10:00 合规边界与 local-first 数据流。
3. **脱敏 vault 结构清单**
   - 只需目录树和示例文件名。
   - 不需要真实 vault 数据。
   - 示例树必须区分 `raw/`、`wiki/sources/`、`wiki/judgments/`、`wiki/elixirs/`、`output/control/`。
4. **讲解 README**
   - 说明素材来源类型、脱敏规则、演示顺序和禁止宣称项。
   - 标明 Demo Pack 是规格或模板，不是 14/30-day natural proof。
