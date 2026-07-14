# Product Shell 插件 UI 重构 (EP-024) 评估报告

> **本文档已于 2026-04-27 提升为 active SoT，新位置：[`docs/Furnace Product Shell.md`](../Furnace%20Product%20Shell.md)。本副本保留作为历史快照，不再更新。**

*Product Shell 插件 UI v3 极简重构评估与决策基础*
*Date: 2026-04-23*

## 1. Executive Summary

- **核心范式 Gap**：当前 UI 是面向运维的"全量 Dashboard"，充斥系统状态、健康度、全量历史等；而用户需求是"极简输入端 + 报告输出端 + 通知提醒"，二者存在根本冲突。
- **推荐方案**：采用 **"Linear骨架 + Raycast输入 + Superhuman通知 + Notion报告"** 混合风格，以单一入口和通知驱动为核心，原有运维视图降级为"Advanced"折叠抽屉。
- **实施代价估算**：
  - 修改/重写核心视图渲染相关文件（`plugin.js`, `render.js`, `views.js`, `styles.css`），新增 0 个文件（复用现有结构）。
  - 风险级别：**M (Medium)**，主要风险在于 Obsidian 视图注册兼容性与状态迁移。
  - 预估轮次：1-2 轮 closed loop。

## 2. 当前 UI 问题诊断

**用户不需要关心但占据首屏的元素（需降级/折叠）**：
- System status / LLM health / Graph Health（纯运维指标）
- Review Center / Execution Center（过程监控）
- Repair Backlog（非核心日常行动）
- Recent Runs（全量流水线历史）

**用户实际需要但被淹没/藏得深的元素（需提升）**：
- Today's Reports 入口（当前可能与各类卡片混杂）
- 新 source 投喂入口（Drop/Ask，当前多在 command palette 或单独的 Ribbon 按钮中，缺少直观的统一界面）
- 报告产出通知机制（当前可能依赖手动刷新或查看列表）

**需要降级/折叠的视图清单**：
- `views.js` / `render.js` 中的运维仪表盘渲染逻辑（系统监控卡片、底层流水线列表等）。

## 3. 目标形态草图

### ASCII Wireframe

**桌面宽屏形态 (900px+)**
```text
+-------------------------------------------------------------------------+
| [ Ask / Command... ] (Raycast style input)                 [1] Unread   |
+-------------------------------------------------------------------------+
|                                                                         |
|  Today's Reports                                                        |
|  +-------------------------------------------------------------------+  |
|  | [Protocol] Report Title A                               [ Open ]  |  |
|  +-------------------------------------------------------------------+  |
|  | [Protocol] Report Title B                               [ Open ]  |  |
|  +-------------------------------------------------------------------+  |
|                                                                         |
|  Previous Reports (grouped by date)                                     |
|  - ...                                                                  |
|                                                                         |
|                                                                         |
| +---------------------------------------------------------------------+ |
| |                    Drop URL / PDF / Image / Repo                    | |
| +---------------------------------------------------------------------+ |
|                                                                         |
| > Advanced (Collapsed)                                                  |
+-------------------------------------------------------------------------+
```

### 交互流图
- **通知流**：用户打开 vault → 插件读 `shell-summary` → 发现今日新报告未读 → 触发 Notice + UI 亮起 Unread badge → 用户点击报告打开 Markdown → 完。
- **输入流**：用户问问题 (Ask box) → 提交 → 界面显示 running 状态 → 完成后，新报告平滑插入 Today's Reports 顶部。
- **投喂流**：用户拖拽 URL/PDF 到下方 Drop zone → 识别类型触发对应协议跑流 → 进度提示 → 完成后进入报告列表。

### 组件清单
- **AskBox** (借鉴 Raycast)：置顶的单行大输入框，极简，高亮。
- **ReportCard** (借鉴 Notion)：清晰的 block 卡片，带 serif 标题和状态小徽章，注重阅读舒缓感。
- **NotificationBadge** (借鉴 Superhuman)：醒目、克制的红点/主色点，聚焦"下一件需要看的事"。
- **DropZone**：大面积虚线框/微底色区域，支持四合一拖拽输入。
- **AdvancedDrawer**：底部/侧边的折叠面板，收纳所有遗留的 Dashboard 视图。

### 状态机
- `has-unread`: 醒目展示，引导点击。
- `all-read`: 界面安静，留白。
- `running`: AskBox 或 DropZone 呈现温和的进度/呼吸态。
- `error-need-attention`: 仅当严重错误且需要用户干预时，展示在列表最上方或发 Notice。

## 4. 3 风格 + 推荐对比

**Librarian 推荐策略：Linear骨架 + Raycast输入 + Superhuman通知 + Notion报告**

**判断：Agree (强烈赞同)**
此组合完美契合用户"极简输入输出+通知"的需求，并且非常适合 Obsidian 插件的环境限制。
- **Linear 骨架**：暗色/亮色克制，利用 Obsidian 原生 theme tokens (`--background-primary`, `--interactive-accent`)，不硬编码品牌色，极其优雅。
- **Raycast 输入**：满足"简单的一个输入端"的诉求，直觉化。
- **Superhuman 通知**：满足"报告出来就通知"的诉求，不打扰但绝对不会漏掉。
- **Notion 报告**：列表展示舒缓，突出内容本身，符合日常阅读体验。

不推荐使用纯 Notion 风格作为全局结构，因为 Notion 过于注重文档构建结构，缺乏对"单极执行与反馈流"的聚焦。当前混合方案在动作输入和状态通知上更胜一筹。

## 5. 通知机制设计

**候选 1：Obsidian Notice API**
- 优势：原生，轻量，极易实现（`new Notice()`），符合用户心智。
- 劣势：生命周期短（随会话结束消失），如果用户不在屏幕前容易错过。

**候选 2：Vault 内 Unread Badge (UI 状态)**
- 优势：持久化，直观，完美符合"每日一读"心智，离线绝对可用。
- 劣势：需与 `shell-summary` 或本地插件状态做联动。

**候选 3：系统通知 (Electron Notification API)**
- 优势：全局触达，强打扰。
- 劣势：需请求系统权限，Linux 环境下可能有坑，可能打破应用边界引起反感。

**评估与推荐**
推荐使用 **"Notice + Vault 徽标 (Badge)" 双通道组合**。
当后台数据更新且界面处于打开状态时，轻量弹一个 Obsidian Notice；同时在主界面的右上角点亮一个醒目的 Unread Badge，直到用户点击查看该报告。坚决不用系统通知以保持克制和跨平台稳定性。

## 6. `shell-summary` Contract 扩展需求评估

为支持"通知+极简"范式，检视现有 contract 字段：
- `today_reports` 或近期的执行记录：**无需扩展**（现有执行历史/产出列表字段可通过插件端按日期截取和 Group By 实时计算）。
- `unread_reports_since` / `last_viewed_at`：**可不扩 runtime**（优先建议在插件设置侧或本地临时文件存储 `last_viewed_timestamp`，对比 `shell-summary` 中的报告生成时间计算未读状态）。

**结论**：**严格守住底线，无需扩展 runtime `shell-summary` 字段**。所有通知机制和按日分组逻辑均可以在插件 `render.js` / `views.js` 内存和本地 plugin settings 中闭环计算。

## 7. 迁移路径（新旧过渡）

- **Phase A (纯 UI 改造)**：
  - 重写 `plugin.js`, `render.js`, `views.js`, `styles.css`。
  - 保留 `constants.js`, `helpers.js`, `modals.js`, `settings.js` 不做结构性破坏。
  - 提取现有的 System Status、LLM Health 等渲染逻辑，包裹进一个 `<details>` / 折叠组件中，命名为 "Advanced"。
- **兼容性保障**：保留原来的 `view_type` id (如 `furnace-product-shell-view`)，确保用户在 Obsidian workspace 中的 pin 状态和布局不会丢。原有的 ribbon icons / command palette 命令全部保留，但可调整文字描述加上 `(Advanced)` 后缀。

## 8. 风险清单

- **迷失风险**：范式切换可能让老用户一打开发现全变了，找不到原有监控入口。
  - *缓解*：首次升级后，弹出一次持久化 Notice 或显示一个醒目的 Onboarding 提示框："Dashboard view has moved to the 'Advanced' section at the bottom."
- **通知疲劳**：如果一天有多次报告生成，频繁弹 Notice 会引起反感。
  - *缓解*：Notice 仅做弱提示或做节流处理，Badge 作为核心未读承载。
- **DOM 测试破坏**：现有 `.obsidian/plugins/furnace-product-shell/` 下如果存在 UI 强相关的测试用例，可能会失败。
  - *缓解*：如果存在测试，需同步更新 selector。

## 9. 实施建议（按 harness 闭环）

- 推荐 **合并实施**：EP-024-A（UI 重写） + EP-024-B（基于本地设置的通知机制）合并为一轮实施。因为通知和极简布局是强耦合的视觉整体，拆分会导致开发撕裂。
- 预计修改文件：`plugin.js` / `render.js` / `views.js` / `styles.css` / `README.md`，预估 delta 代码量约 800 行。
- 测试验证重点：主题切换下的色彩令牌（token）表现、新旧报告列表的读取与渲染、Advanced 抽屉的折叠展开、未读 badge 的点亮与消除。

## 10. 待用户拍板的决策点

1. **通知机制**：确认采用 "Obsidian Notice + UI 内部 Badge" 双通道方案，不采用桌面系统级强通知？
2. **状态存储**：同意在插件本地 settings 中记录 `last_viewed_timestamp` 以计算未读状态，从而保持 runtime `shell-summary` 契约不变？
3. **老用户引导**：首次升级后，是否需要展示一次性 Onboarding Notice 指引 "Advanced 抽屉"的位置？
4. **实施节奏**：是否同意将极简 UI 重写和通知机制合并为单一阶段 (Phase A+B) 进行落地闭环？

---
*Authors: @designer (via orchestrator) + @librarian (reference research) + @explorer (runtime fact check)*
*Status: Draft, awaiting user approval*
