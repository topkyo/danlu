---
title: "Furnace Product Shell SoT"
kind: "spec"
status: "active"
updated_at: "2026-07-15"
---

# Furnace Product Shell SoT

*Obsidian 插件 UI 层事实源；炼丹炉"一个输入端 + 一个输出端"原则的可视化呈现*
*Status: Active SoT, decision points resolved (§10)*
*Last updated: 2026-07-14*

## Platform boundary（2026-07）

- **当前正式支持：Desktop Obsidian only**（Mac / Linux；Windows 同桌面模型）。`manifest.json` 中 `isDesktopOnly: true`。
- 插件通过 Node `child_process.spawn` 调用 vault-local / absolute `aiwiki-launcher.sh`，再进入 Python CLI；因此依赖本机 shell、文件系统绝对路径与 Python runtime。
- **iPad / iOS Obsidian：不支持全功能直移植。** 移动端无 Node/Electron/任意 shell，不能本地执行 aiwiki。若未来做移动端，只能是 thin client（只读 summary + 提交 queue/API），见 [Commercial Grade Cleanup Plan 2026-07 Out/Non-goals](./archive/Furnace%20Commercial%20Grade%20Cleanup%20Plan%202026-07.md)。
- 商业口径：Mac desktop 是主产品面；不要对外宣称“炼丹炉插件已支持 iPhone/iPad 全功能炼化”。

## 0. 第一性原理

本文档受 [`docs/Furnace Agent Architecture.md`](./Furnace%20Agent%20Architecture.md) §3 Stable Invariants and Non-Goals 约束。

炼丹炉 Product Shell 的 UI 第一性原理是：**用户面只暴露一个输入端 + 一个输出端，其他全部隐藏**。

- **一个输入端**：首屏只给用户一个 Universal Input；URL、文件拖拽、文本笔记和问题都从这里进入。
- **一个输出端**：首屏只呈现 Today Feed 中可交付的输出、需要确认的事项和非降级活动，不把运行态流水线当成用户目标。
- **其他全部隐藏**：System Status / LLM Health / Review Center / Execution Center / Repair Backlog / Recent Runs 等运维、状态、监控入口全部收纳到 Advanced / 更多工具抽屉。
- **用户心智最小化**：任何 UI 层新增卡片、按钮、状态或通知，都必须证明它没有扩大用户需要理解的概念数量。
- **通知只服务输出端**：外部 webhook 通知（飞书 / 企业微信）只提醒"有新报告需要看"，不把后台调度细节推给用户。
- **Advanced / 更多工具不是删除**：高级视图仍保留给操作者排障和治理，只是不占据默认首屏。
- **UI 不拥有 runtime state**：Product Shell 只通过 launcher CLI 与 `output/control/shell-summary.json` 读取 shell-facing contract。
- **UI 不新增 SoT 字段**：本文档不引入任何新的事实字段、schema 字段或 runtime contract。
- **不扩 `shell-summary`**：§6 已论证未读状态、按日分组和通知机制均可在插件本地 settings / 内存中闭环计算。
- **不隐式调度 backend**：UI 可以显示显式选择的 backend / model，但不得替用户自动切换。
- **不绕过审计闭环**：UI 层触发的执行仍必须走既有 CLI、receipt、review / apply / revert / audit 边界。

## 1. Executive Summary

- **核心范式 Gap**：旧 UI 是面向运维的"全量 Dashboard"，充斥系统状态、健康度、全量历史等；而用户需求是"极简输入端 + 输出端 + 外部 IM 通知提醒"，二者存在根本冲突。
- **当前方案**：采用 **Today Feed + Universal Input** 的默认面，配合 **飞书 / 企业微信 webhook 外部通知**。Advanced 默认隐藏，仅作为 operator diagnostics/history/Review Center/Execution Center 入口。
- **Furnace Product Shell M-PS.1 milestone candidate 实施代价估算**：
  - 修改/重写核心视图渲染相关文件（`plugin.js`, `render.js`, `views.js`, `styles.css`），新增 0 个文件（复用现有结构）。
  - 风险级别：**M (Medium)**，主要风险在于 Obsidian 视图注册兼容性与状态迁移。

## 2. 当前 UI 问题诊断

**用户不需要关心但占据首屏的元素（需降级/折叠）**：
- System status / LLM health / Graph Health（纯运维指标）
- Review Center / Execution Center（过程监控）
- Repair Backlog（非核心日常行动）
- Recent Runs（全量流水线历史）

**用户实际需要但被淹没/藏得深的元素（需提升）**：
- Today Feed 入口（当前可能与各类卡片混杂）
- 新 source 投喂入口（URL / PDF / Markdown / repo / question 统一进入 Universal Input）
- 报告产出通知机制（当前完全缺失，依赖用户手动打开 vault 才发现新报告，覆盖不到"用户离开屏幕"场景）。

**需要降级/折叠的视图清单**：
- `views.js` / `render.js` 中的运维仪表盘渲染逻辑（系统监控卡片、底层流水线列表等）。

## 3. 目标形态草图

### ASCII Wireframe

**桌面宽屏形态 (900px+)**
```text
+-------------------------------------------------------------------------+
|  Today Feed                                                             |
|  +-------------------------------------------------------------------+  |
|  | [Protocol] Report Title A                               [ Open ]  |  |
|  +-------------------------------------------------------------------+  |
|  | [Protocol] Report Title B                               [ Open ]  |  |
|  +-------------------------------------------------------------------+  |
|                                                                         |
| [ Universal Input: URL / PDF / Markdown / repo / question... ]           |
+-------------------------------------------------------------------------+
| > Advanced (operator diagnostics, hidden unless enabled)                 |
+-------------------------------------------------------------------------+
```

### 交互流图
- **通知流**：runtime 写出新报告 → Notifier 推送飞书 / 企业微信 webhook → 用户在 IM 中收到提醒 → 回到 vault 打开报告 Markdown → UI 内对应卡片按 `last_viewed_timestamp` 更新视觉态。
- **输入流**：用户在 Universal Input 输入问题或材料 → 提交 → 界面显示 running / received / done / failed / degraded 状态 → 完成后，可交付输出进入 Today Feed。
- **投喂流**：用户拖拽文件或粘贴 URL 到 Universal Input → runtime 识别类型并路由 → 进度提示 → 完成后进入输出列表。

### 组件清单
- **TodayFeed**：默认输出端，只展示可交付输出、确认项和非降级活动。
- **UniversalInput**：默认输入端，统一 URL / PDF / Markdown / repo / question。
- **ReportCard** (借鉴 Notion)：清晰的 block 卡片，带标题和状态小徽章，注重阅读舒缓感；未读项做轻量视觉区分（加粗 / 左侧圆点）。
- **AdvancedDrawer**：仅在 `showAdvancedCommands` 启用后出现，收纳 diagnostics/history、Recent Runs、Review Center、Execution Center 和 refresh。
- **Notifier**（非 UI 组件，运行态侧 / sidecar）：飞书 + 企业微信 webhook 推送抽象，订阅"新报告生成"事件。

### 状态机
- `has-unread`: Today's Reports 顶部未读卡片做加粗 / 圆点视觉区分。
- `all-read`: 界面安静，留白。
- `running`: Universal Input pending card 呈现温和的进度/呼吸态。
- `error-need-attention`: 仅当严重错误且需要用户干预时，展示在列表最上方（不弹 Notice，不发 webhook）。

## 4. 风格选择：Linear 骨架 + Raycast 输入 + Notion 报告

采用 **Linear 骨架 + Raycast 输入 + Notion 报告** 的 UI 组合（通知通道独立由飞书 / 企业微信 webhook 承担，见 §5）。

**判断：Agree (强烈赞同)**
此组合契合用户"极简输入输出"的需求，并且非常适合 Obsidian 插件的环境限制。
- **Linear 骨架**：暗色/亮色克制，利用 Obsidian 原生 theme tokens (`--background-primary`, `--interactive-accent`)，不硬编码品牌色，极其优雅。
- **Raycast 输入**：满足"简单的一个输入端"的诉求，直觉化。
- **Notion 报告**：列表展示舒缓，突出内容本身，符合日常阅读体验。

不推荐使用纯 Notion 风格作为全局结构，因为 Notion 过于注重文档构建结构，缺乏对"单极执行与反馈流"的聚焦。当前混合方案在动作输入和报告呈现上更胜一筹。

> 注：早期方案曾考虑借鉴 Superhuman 的 in-app 通知美学（红点 / Badge），最终因 §5 决策改用外部 IM webhook，UI 内部不再出现 Badge / Notice 元素。

## 5. 通知机制设计

**最终方案：外部 webhook 通知（飞书 + 企业微信群机器人）**

### 5.1 设计判断

炼丹炉的使用心智是"投料 → 后台慢跑 → 用户离开屏幕做别的事 → 报告生成后回头看"。Obsidian Notice 仅在 vault 打开时触达，Vault Badge 必须用户主动打开 vault 才看见，桌面系统通知跨平台不稳定且打扰强度难以拿捏。三者都不能解决"用户离开屏幕"这个核心场景。

外部 IM webhook（飞书 Custom Bot / 企业微信群机器人）的特点正好匹配：
- 用户本来就在 IM 里活动，触达可靠。
- webhook 是无状态推送，不需要鉴权服务器、不需要轮询，符合 local-first 边界。
- 飞书 / 企业微信都接受纯文本 JSON POST，实现成本极低。
- 多渠道并行不互斥，用户可在 settings 任填一个或两个 webhook URL。

### 5.2 触发时机

- **只在新报告生成时触发**：报告写入 `output/reports/` 完成后由 Notifier 推送一条消息。
- **不跟 audit stream 联动**：audit / review / proposal 等运行态事件不通过 webhook 暴露给用户。
- **不做待拍板通知**：review backlog / repair backlog 等治理项保留在 Advanced 抽屉，不主动推送。

### 5.3 消息格式

先做最简纯文本：`[Protocol] Report Title — generated at HH:MM`。不做富文本卡片、不做 button action、不做 @ mention，避免引入 IM 平台耦合。

### 5.4 失败处理

- webhook POST 失败时**不重试、不持久化失败队列**，只在本地 audit envelope 写一条 `notify_failed` 事件。
- 用户不感知失败：报告本身已落盘，下次打开 vault 仍能看到，webhook 只是冗余触达通道。
- 这是 KISS 选择：建持久化重试队列会引入新的状态机和故障模式。

### 5.5 弃用方案说明

以下方案曾被考虑，**最终全部不采用**：
- **Obsidian Notice API**：仅在 vault 打开时触达，覆盖不到"用户离开屏幕"场景。
- **Vault 内 Unread Badge**：需用户主动打开 vault 才看见，且 Badge 状态机会扩大 UI 概念数量。
- **系统桌面通知（Electron Notification）**：跨平台不稳定，Linux 权限坑多，打扰强度过强。

> Vault 内的"Today's Reports"列表本身已经隐式呈现了未读状态（按时间倒序、新报告置顶），不需要单独的 Badge 元素。

## 6. `shell-summary` contract 边界

为支持"通知+极简"范式，检视现有 contract 字段：
- `today_reports` 或近期的执行记录：**无需扩展**（现有执行历史/产出列表字段可通过插件端按日期截取和 Group By 实时计算）。
- `last_viewed_timestamp`：**存在插件本地 settings**，不入 runtime contract。用于在 UI 内对"Today's Reports"做未读视觉区分（如加粗 / 圆点），但**不弹任何 Badge 组件**。

**结论**：**严格守住底线，无需扩展 runtime `shell-summary` 字段**，符合 KISS 原则。所有按日分组逻辑均在插件 `render.js` / `views.js` 内存和本地 plugin settings 中闭环计算；外部通知由独立 Notifier 模块在 runtime 侧或 sidecar 触发，不污染 UI 层 contract。

## 7. 迁移路径

- **Phase A (纯 UI 改造)**：
  - 重写 `plugin.js`, `render.js`, `views.js`, `styles.css`。
  - 保留 `constants.js`, `helpers.js`, `modals.js`, `settings.js` 不做结构性破坏；`settings.js` 增加 webhook 配置字段（见 §9）。
  - 提取现有的 System Status、LLM Health 等渲染逻辑，包裹进一个 `<details>` / 折叠组件中，命名为 "Advanced"。
- **Phase B (Notifier 集成)**：
  - 引入飞书 / 企业微信 webhook Notifier 抽象，在新报告生成事件触发推送。
  - 失败时落 audit `notify_failed` 事件，不重试、不入持久化队列。
- **兼容性保障**：保留原来的 `view_type` id (如 `furnace-product-shell-view`)，确保用户在 Obsidian workspace 中的 pin 状态和布局不会丢。原有的 ribbon icons / command palette 命令全部保留，但可调整文字描述加上 `(Advanced)` 后缀。
- **不做 Onboarding**：升级后不弹任何引导提示。Advanced 抽屉自身的折叠标签（"Advanced"）已经足够自解释，老用户找一次即可定位。

## 8. 风险清单

- **迷失风险**：范式切换可能让老用户一打开发现全变了，找不到原有监控入口。
  - *缓解*：Advanced 抽屉始终展示在首屏底部，标签自解释；不引入一次性 Onboarding 提示（属于 UI 层 KISS 取舍）。
- **通知疲劳**：如果一天有多次报告生成，频繁推送 webhook 会引起反感。
  - *缓解*：先以"每报告一推"实现，**不预先做节流 / 合并**；如果实际使用中出现疲劳，再在 Notifier 层加节流策略，不在首版引入。
- **webhook URL 泄漏风险**：飞书 / 企业微信 webhook URL 等同于发送凭据。
  - *缓解*：仅存在插件本地 settings（即用户自己的 vault），不进入 audit envelope、不进入 receipts、不写入任何 raw/wiki/output 路径。
- **DOM 测试破坏**：现有 `.obsidian/plugins/furnace-product-shell/` 下如果存在 UI 强相关的测试用例，可能会失败。
  - *缓解*：如果存在测试，需同步更新 selector。

## 9. 实施建议

- 推荐作为单一 milestone (**M-PS.1**) 一次性落地 Phase A + Phase B，避免 UI 改造和通知机制拆分。因为通知和极简布局是强耦合的产品整体，拆分会导致用户感知撕裂。
- 预计修改文件：`plugin.js` / `render.js` / `views.js` / `styles.css` / `settings.js` / `README.md`，预估 delta 代码量约 800–1000 行。
- 新增 settings schema 字段（仅本地）：
  - `feishu_webhook_url: string`（可空）
  - `wecom_webhook_url: string`（可空）
  - `enabled_channels: ("feishu" | "wecom")[]`
  - `last_viewed_timestamp: string`（ISO8601，UI 内部用）
- 测试验证重点：主题切换下的色彩令牌（token）表现、新旧报告列表的读取与渲染、Advanced 抽屉的折叠展开、webhook 推送成功 / 失败两种路径下的 audit 事件落地。

## 10. 已拍板决策（2026-04-27）

> **实施状态（2026-05-24）**：M-PS.1 之后的 AgentOS 收敛已完成默认面更新：首屏为 Today Feed + Universal Input；AskBox / DropZone 已吸收到 Universal Input，Advanced 仅在 `showAdvancedCommands` 下作为 diagnostics/history/Review/Execution surface 出现。Phase B 的飞书 / 企业微信 webhook Notifier、插件 env bridge、`run-ask` report hook 和 notifier tests 继续保留。

以下决策点已闭环，本文档其余章节均已与决策对齐：

1. **通知机制：飞书 + 企业微信 webhook 外部推送**
   - 弃用 Obsidian Notice、Vault Unread Badge、桌面系统通知三条路径。
   - 理由：用户离开屏幕场景下只有 IM 推送可靠触达；webhook 实现 KISS。
   - 详见 §5。

2. **未读状态存储：本地 settings `last_viewed_timestamp`**
   - 不扩展 runtime `shell-summary` contract。
   - UI 内对未读报告做轻量视觉区分（加粗 / 圆点），不引入 Badge 组件。
   - 详见 §6 / §9。

3. **不做老用户 Onboarding 引导**
   - 升级后不弹一次性提示框。
   - Advanced 抽屉的折叠标签自解释，足够定位。
   - 详见 §7 / §8。

4. **UI 重写 + 通知集成合并为单 milestone (M-PS.1)**
   - Phase A (UI) 与 Phase B (Notifier) 在同一 milestone 内顺序落地，不拆成两个独立 milestone。
   - 理由：通知与极简 UI 是产品体验整体，拆分会导致用户感知撕裂。
   - 详见 §9。

## 11. 与 SoT 的对齐说明

M-PS.1 实施后，Product Shell 仍只作为 surface / trigger 运行；Notifier 是 runtime 边界上的显式 webhook 出口，仅在报告生成后发送提醒，失败写可审计 `notify_failed` 记录且不污染 report / receipt / shell-summary。

本文档与 [`docs/Furnace Agent Architecture.md`](./Furnace%20Agent%20Architecture.md) §3 的全部不变量兼容。

- **Single writer / many readers**：Product Shell 仍是 reader / trigger surface，不拥有并发写入权。
- **`raw/` 不可写**：UI 只提供投料入口，事实输入仍进入 `raw/`，派生层不得覆盖原始材料。
- **Provenance**：报告、简报和输出卡片只展示已有 provenance 的 runtime 产出，不制造无来源结论。
- **Deterministic baseline**：UI 重写不改变 backend / model selection；Notifier 只接 report-generated hook，成功无审计副作用，失败仅追加 `notify_failed` audit，不改变 report generation exit code。
- **Backend 显式手动选择**：UI 不做 hidden backend routing；backend / model 切换仍由操作者显式选择。
- **Review-apply-revert-audit**：Advanced 抽屉中的治理入口继续走既有可审计、可回滚路径。
- **Advanced 抽屉不删除能力**：System Status / LLM Health / Review Center / Execution Center / Repair Backlog / Recent Runs 都不会被删除，只是从首屏降级。
- **同步审查要求**：当 `docs/Furnace Agent Architecture.md` §3 的不变量发生变化时，本文档必须同步审查。

## 12. UX Follow-up Status（2026-04-29）

M-UX.1 ~ M-UX.6 之后，Product Shell 的实际产品面继续向“一个输入端 + 一个输出端”收敛：

- 默认 Obsidian workspace 进入主区 Product Shell，左侧仅文件列表/书签，右侧仅大纲/反链，并默认折叠左右侧栏。
- new-vault 与 dogfood vault 的 CSS snippet 把普通用户文件树收敛为报告视图：隐藏 `raw/wiki/schema/scripts/prompts`，`output/` 下默认只露出 `reports/`。
- Advanced 抽屉在中文界面显示为“更多工具”，摘要显示“待审 / 待执行 / 运行记录”，避免把 operator 机制放进首屏。
- Today feed 的可见 target 不再默认展示 `output/...` / `wiki/...` runtime path，而以“报告 / 判断页 / 决策页 / 提案页 / 关系图谱”等产品标签呈现；真实路径仍由按钮动作持有。
- 报告卡和 Today 报告动作使用 “Open report / 打开报告”，而不是泛化的 “Open / 打开”，让报告入口成为明确输出端。
- 关系图谱 HTML 已从 `component / slug / wiki 页面 / Hub / rewrite` 口吻收敛到“关系组 / 关键词或来源编号 / 详情页 / 核心概念 / 核心来源 / 改写提案”。
- **2026-07-18（freeform ask + Today 动作修复）**：Ask / Universal Input 提问只走 `run-ask` → `output/reports/*.md`（无 format 选择 UI、无 `--direct`）；Today 报告卡「打开报告 / 审阅 / 稍后」按钮已接线到 `openWorkspacePath`、review center 与 `runTodaySnoozeCommand`。

这些变更不扩展 `shell-summary`，不新增 settings schema，不移动 runtime 目录，也不删除 CLI/operator 能力。
