---
title: "炼丹炉 Product Shell Plugin"
kind: "architecture"
status: "active"
---

# 炼丹炉 Product Shell Plugin

这份文档回答的是：

**如果要把炼丹炉的 `Product Shell` 真正落成 Obsidian 内的工作台插件，它应该怎么分层、怎么调用 `aiwiki`、以及哪些边界不能打穿。**

它不是在重写 `aiwiki` runtime，而是在定义：

- Obsidian 内的人用工作台
- `aiwiki CLI` 之上的桌面壳层
- 当前 markdown/html 控制面的原生插件化升级路径

对应关系：

- 基线架构：[[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- 终局架构：[[wiki/indexes/Furnace Ultimate Architecture|炼丹炉最终极形态]]
- runtime 实施计划：[[wiki/indexes/Furnace Product Shell Runtime Plan|Product Shell Runtime Plan]]
- 当前这份：`Product Shell` 的实现级设计稿

## 一句话定义

`Furnace Product Shell Plugin` 是一个 **desktop-only 的 Obsidian 插件壳层**：

- `aiwiki` 继续做 runtime / CLI / state owner
- Obsidian 插件负责统一入口、状态展示、命令调度和结果跳转
- 人通过插件面板与炼丹炉交互，而不是记大量命令和在多个页面间跳转

## 当前实现状态

截至当前仓库状态，Phase 1 已开始落地到：

- `.obsidian/plugins/furnace-product-shell/manifest.json`
- `.obsidian/plugins/furnace-product-shell/main.js`
- `.obsidian/plugins/furnace-product-shell/styles.css`

当前已经实现的最小 desktop shell：

- `Furnace Center`
- `Recent Runs`
- `Review Center`
- `Execution Center`
- `Refresh Furnace Shell / Compile / Ask / Nightly / Set Protocol`
- `File Back / Review Page / Review Rewrite / Apply Rewrite`
- `Retire Concept / Reactivate Concept`
- `Apply Archive / Revert Archive`
- `Review Action / Apply Action / Revert Action`
- 通用受限表单 modal
- `Review Center / Execution Center` 内的动作按钮

还没有实现：

- TypeScript/build toolchain
- 更细的 action-specific context picker / item-level inline action

## 为什么要单独做这层

当前炼丹炉已经有：

- `furnace-center`
- `review-center`
- `execution-center`
- `execution-audit`
- `graph-view`
- 各类 lifecycle / protocol / machine-memory 状态页

但它们现在仍以：

- markdown index 页
- 本地 HTML 控制面
- `aiwiki CLI` 命令

三种入口并存。

这说明 runtime 已经具备很多能力，但 `Product Shell` 还没有长成真正的一体化桌面工作台。

插件层要解决的，不是“能力缺失”，而是：

- 入口分散
- 命令记忆成本高
- 状态页和动作入口分离
- `ask / compile / nightly / review` 结果缺少统一回显

## 设计目标

- 把当前分散的控制面统一成 Obsidian 内的一个工作台
- 保持 `aiwiki CLI` 作为唯一正式 runtime 接口
- 让常用动作从命令行记忆负担变成面板操作和命令面板动作
- 把 `review / lifecycle / protocol / output` 收进统一可见的导航和状态摘要
- 保持 local-first、single-writer、可审计、可回滚

## 非目标

- 不把炼丹炉 runtime 重写成 Obsidian 插件
- 不让插件直接拥有 `material-state` 或 `knowledge-lifecycle` 的真相
- 不把 `compile / ask / review / archive / apply / revert` 的核心规则搬到 TypeScript 里重写
- 不依赖 hosted service、后端进程常驻服务或数据库
- 不优先考虑 mobile；第一版默认 `desktop-only`

## 分层原则

### 1. `aiwiki` 是炉心

仍由 `aiwiki` 负责：

- `raw -> compile -> wiki -> ask -> output -> file-back -> review / nightly`
- protocol runtime
- machine memory state
- knowledge lifecycle state
- execution / apply / revert / audit

### 2. Obsidian 插件是炉壳

由插件负责：

- 统一入口
- 命令分发
- 状态摘要展示
- 结果面板
- 页面/产物/日志跳转

### 3. GUI 和 CLI 不抢真相

插件不直接成为事实层写手。

状态变更默认只能通过：

- `aiwiki CLI`
- `aiwiki` 生成的 state / output / receipt

来完成。

## 插件边界

### 插件可以做

- 调用 `aiwiki` 子命令并展示结果
- 读取插件专用 summary 和可见 output 做工作台摘要
- 打开 `wiki/indexes/*`、`wiki/derived/*`、`output/*`
- 提供命令面板、侧栏、ribbon、状态栏入口
- 维护插件自己的 UI 偏好设置

### 插件不能做

- 直接改 `.aiwiki/state/*`
- 绕过 `aiwiki` 直接推进 lifecycle / review / archive / execution 状态
- 直接手改 compile 生成的 index 页
- 直接把派生结论写回 `raw/`
- 自己维护第二套 protocol / review / execution 规则

## 总体结构

```text
Obsidian App
    └── Furnace Product Shell Plugin
          ├── Command Palette / Ribbon / Status Bar
          ├── Sidebar Views
          │     ├── Furnace Center
          │     ├── Review Center
          │     ├── Execution Center
          │     ├── Graph / Memory Summary
          │     └── Recent Runs
          ├── Aiwiki Runner
          │     ├── spawn aiwiki CLI
          │     ├── parse JSON stdout
          │     ├── stream logs / status
          │     └── map outputs to deep links
          ├── State Readers
          │     ├── output/control/shell-summary.json
          │     ├── wiki/indexes/*.md
          │     ├── output/**/*.html
          │     └── output/**/*.md
          └── Navigation Layer
                ├── open note
                ├── open HTML panel
                ├── open output artifact
                └── reveal receipt / audit page
```

## 与 `aiwiki CLI` 的契约

当前 `aiwiki CLI` 已经适合作为插件后端接口：

- 所有命令都通过统一 parser 暴露
- 命令结果以 JSON 打到 stdout
- `--root` 已经允许插件显式绑定 vault 根目录

这意味着插件不需要发明 RPC 协议；第一版直接把 CLI 当本地 runtime adapter 即可。

推荐接入的命令优先级如下。

## Plugin-facing Contract

插件不要把 `.aiwiki/state/*` 直接升级成公共 UI 接口。

第一版应由 `aiwiki` 提供一个显式 shell-facing contract：

- `output/control/shell-summary.json`
- `aiwiki shell-status`
- repo-local launcher

### 1. `output/control/shell-summary.json`

这是插件默认读取的主摘要文件。

建议至少包含：

- `contract_version`
- `generated_at`
- `active_protocol`
- `llm_status`
- `review_backlog_counts`
- `aging_summary`
- `recent_outputs`
- `recent_receipts`
- `recent_runs`
- `links`
- `capabilities`

原则：

- 只放 Product Shell 真正要展示的摘要
- 不把 runtime 内部 state 文件名暴露成长期前端契约
- 如果内部状态模型变化，优先由 `aiwiki` 重组 summary，而不是让插件跟着内部 state 漂移

### 2. `aiwiki shell-status`

插件需要一个显式的“刷新并返回最新 shell 摘要”的命令，而不是自己推断应该读哪些内部文件。

建议语义：

- 刷新 `output/control/shell-summary.json`
- stdout 返回同结构 JSON
- 不推进任何 review / archive / execution 状态
- 只负责面向 Product Shell 的只读摘要

### 3. Repo-local launcher

第一版先明确按“本 repo 专用 desktop plugin”设计，不直接假设全局安装形态。

插件不应该自己拼：

`PYTHONPATH=src python -m aiwiki.cli --root <vault>`

而应该优先调用 repo 内显式 launcher，例如：

- `scripts/aiwiki-launcher.sh`
- 或 `bin/aiwiki`

这样：

- Python 路径、`PYTHONPATH` 和启动细节由 repo 侧维护
- 插件只负责传命令和参数
- 后续如果要支持全局安装，再扩展成 `configured command -> repo-local launcher -> PATH aiwiki` 的 fallback 链

## MVP 命令面

### P0: 必须接入

- `compile`
- `ask`
- `run-ask`
- `nightly`
- `protocol-status`
- `protocol-set`
- `llm-check`

### P1: 很快需要

- `run-compile`
- `run-nightly`
- `file-back`
- `review-page`
- `review-rewrite`
- `apply-rewrite`
- `retire-concept`
- `reactivate-concept`
- `apply-archive`
- `revert-archive`

### P2: 进入执行面后再接

- `review-action`
- `apply-action`
- `revert-action`
- `watch`
- `auto-once`

## MVP 视图

### 1. Furnace Center View

统一首页，至少显示：

- active protocol
- 最近一次 compile / ask / nightly 结果
- pending review 数
- overdue / escalation 数
- 最近 outputs
- 常用动作按钮

### 2. Review Center View

聚焦治理：

- review backlog
- aging / revisit summary
- concept rewrite summary
- machine-memory repair backlog

### 3. Execution Center View

聚焦低风险执行：

- ready actions
- dry-run / apply / revert 入口
- 最近 execution receipts
- 最近 execution audit 链接

### 4. Recent Runs View

统一命令回显：

- 最近一次命令
- 运行中状态
- stdout/stderr 摘要
- 产物路径 / receipt 路径 / 失败原因

## 导航设计

插件不应该只展示摘要，还应该是统一跳板。

第一版至少要支持：

- 打开 `wiki/indexes/furnace-center.md`
- 打开 `wiki/indexes/review-center.md`
- 打开 `wiki/indexes/execution-center.md`
- 打开 `wiki/indexes/domain-pilots.md`
- 打开 `wiki/indexes/output-packs.md`
- 打开 `output/control/*.html`
- 打开最新 report / slides / figure
- 打开最新 receipt / audit 页面

## 运行模型

### 命令执行

- 插件通过 repo-local launcher 调用 `aiwiki CLI`
- stdout 按 JSON 解析
- stderr 保留给用户排错
- 长任务要有 running / success / failed 三态
- 第一版默认要求 vault 根目录就是 `aiwiki` repo 根目录
- 启动时应显式检查 repo 结构是否成立，再决定是否启用 Product Shell

推荐检查：

- `src/aiwiki/cli.py`
- `raw/`
- `wiki/`
- `schema/`

### 状态读取

插件默认只读：

- `output/control/shell-summary.json`
- `wiki/indexes/*.md`
- `output/**/*.html`
- `output/**/*.md`

如果 `shell-summary.json` 不存在，插件要降级：

- 显示 “未生成”
- 提示用户先运行 `aiwiki shell-status`、`compile` 或 `nightly`
- 不自行造状态

只有在后续明确接受 `Adapter API` 方案时，才考虑直接读取 hidden `.aiwiki/state/*`。

## 刷新模型

Product Shell 必须显式定义“什么时候刷新”，否则 cockpit 很容易 stale。

第一版建议固定成：

- 插件启动时读取一次 `shell-summary.json`
- 插件触发任一 `aiwiki` 命令后，命令结束时强制刷新一次 summary
- 提供显式 `Refresh Furnace Shell` 命令
- 只监听可见路径变化：
  - `output/control/shell-summary.json`
  - `output/`
  - `wiki/indexes/`

第一版不监听 hidden `.aiwiki/state/*`。

## 安全与一致性

### 必须遵守

- `raw/` 是唯一事实输入层
- `single writer, many readers`
- 派生输出不能覆盖 source truth
- lifecycle / archive / execution 必须保留 receipt / audit

### 插件侧约束

- 所有写动作都通过 `aiwiki CLI`
- 所有高风险动作都要显式确认
- 默认不做后台自动 apply
- 默认不引入常驻 daemon
- 插件设置只存 UI 偏好，不存系统真相

## 桌面限定

第一版明确按 `desktop-only` 设计。

原因：

- 需要稳定调用 repo-local `aiwiki` launcher
- 需要打开本地 HTML panel 和 output artifact
- 需要读取本地 vault / state / output 结构
- mobile 端不适合承担本地 runtime 壳层

## 信息架构

建议插件左侧导航至少有这几组：

- Home
  - Furnace Center
  - Recent Runs
- Governance
  - Review Center
  - Aging Summary
  - Repair Backlog
- Runtime
  - Protocol
  - Machine Memory
  - Graph Summary
- Outputs
  - Recent Reports
  - Output Packs
  - Receipts / Audit

## MVP 交互流

### 1. Compile 流

- 用户点击 `Compile`
- 插件启动 `aiwiki compile`
- Recent Runs 显示运行中
- 完成后刷新 `shell-summary.json`
- Furnace Center、Review Center 等视图基于新 summary 刷新
- 提供跳转到 `compile-status`、`furnace-center`、最近 source/concept 页

### 2. Ask 流

- 用户输入问题和 format / protocol
- 插件运行 `aiwiki ask` 或 `run-ask`
- 完成后展示 artifact 路径
- P0 先提供 `Open output`
- `File back` 按钮留到 P1，和显式表单一起接入

### 3. Review 流

- 用户在页面侧边打开 Review Center
- 看到 pending / overdue / escalation
- 选中当前 decision/judgment 页后，通过表单收集 `status / note / confidence`
- 通过显式校验后再触发 `review-page`
- 完成后刷新 review summary 和当前页面状态

### 4. Protocol 流

- 用户在 Furnace Center 查看 active protocol
- 从下拉框切到 `investing / research / product / ops`
- 插件运行 `protocol-set`
- 完成后刷新 protocol summary、domain pilots 和相关 hints

## 插件设置

建议只有少量设置：

- `aiwiki root`
- `aiwiki launcher` 路径
- 是否默认使用 `run-ask` / `run-compile`
- Recent Runs 保留条数
- 是否显示 HTML panel 快捷入口

不建议在插件设置里维护：

- protocol schema
- review policy
- archive policy
- lifecycle mapping

## 迭代顺序

### Phase 1

- Command Palette + Ribbon
- Furnace Center View
- Recent Runs View
- `compile / ask / nightly / protocol-set` 接线

### Phase 2

- Review Center / Execution Center
- `file-back / review-page / review-rewrite / archive / apply-*` 接线
- 输出和 receipt 深链接
- 已完成

### Phase 3

- 更细的 lifecycle summary
- domain-pilots / agent-workbench / output-packs 集成
- 更好的 long-running task UX

## 替代方案与取舍

### 方案 A：只保留 markdown/html 页面

优点：

- 实现最轻

缺点：

- 入口分散
- 交互弱
- 结果回显差

### 方案 B：把 runtime 搬进插件

优点：

- 看上去“一体化”

缺点：

- 分层被打穿
- TypeScript 和 Python 双实现会漂移
- protocol / lifecycle / execution 规则更难保持一致

### 方案 C：Product Shell Plugin + `aiwiki CLI`

优点：

- 分层清晰
- 升级路径自然
- 复用现有 runtime

缺点：

- 需要维护一层桌面壳
- 需要处理子进程、日志和错误 UX

当前推荐明确是方案 C。

## 开放问题

- 是否给 `aiwiki CLI` 增加更稳定的 `machine-readable` 子命令返回约定，而不是只靠通用 JSON 输出
- 是否为长任务补更细的进度事件文件
- 是否把 HTML control panel 的一部分直接迁入原生插件 view
- 是否在插件中内建“最近产物”和“最近 receipt”的 quick picker

## 当前建议

如果开始做，第一步不要碰 runtime。

先做一个最小可用的 `Product Shell Plugin`：

- 只调 `aiwiki CLI`
- 只读 `shell-summary.json`、可见 index 和 output
- 不在 P0 接 `file-back / review-page / apply-*`
- 先把 `furnace-center + recent-runs + compile/ask/nightly/protocol-set`
  跑通

这样能最快把炼丹炉从“强 runtime + 薄前台”推进到“真正可天天用的工作台”。
