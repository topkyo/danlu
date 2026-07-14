# Furnace Product Shell — UX Plan v2

> 生成时间：2026-05-03
> 前置 SoT：`docs/Furnace Agent Architecture.md` §1.1、"一个输入端 + 一个输出端"第一性原理
> 参考插件：Obsidian Kanban（mgmeyers/obsidian-kanban）— ItemView 注册、模块化 render、设置持久化、CSS 变量
> 测试方案：Jest + jsdom + `__mocks__/obsidian.ts`

---

## 1. 当前代码问题诊断

### 架构问题

| 问题 | 现状 | 影响 |
|---|---|---|
| `plugin.js` 2710 行单体 | 所有逻辑（View 注册、命令注册、渲染、状态管理、CLI 调用）在一个 class | 不可测试、改动风险高 |
| 0 个 JS 单元测试 | 7614 行源文件，完全依赖 Python 集成测试 | 渲染逻辑、feed 构建、状态管理无回归保护 |
| render 函数直接操作 DOM | `render_*.js` 创建 Obsidian DOM 元素但不返回纯数据 | 无法在 jsdom 外测试 |
| CSS 1027 行无组件分层 | 所有样式在一个文件 | 改一个组件可能影响其他 |

### UX 问题

| 问题 | 现状 |
|---|---|
| Today Feed 分组不稳定 | 5 个分组（Reports/Automation/Needs Confirmation/Completed/Suggested Actions）排序逻辑分散在 render + feed builder |
| Advanced 抽屉折叠无动画 | `<details>` 原生折叠，无过渡 |
| 输入区与报告区间距过大 | Universal Input → Today Feed 中间无视觉锚定 |
| 设置面板暴露过多内部选项 | `showAdvancedCommands` 等 flag 对普通用户无意义 |

---

## 2. 目标架构

### 文件拆分

```
src/
├── main.js                    # Plugin 入口 (<100行)
│   ├── onload/onunload
│   ├── registerView × 4
│   ├── addCommand × 8
│   └── addRibbonIcon
│
├── views/                     # ItemView 子类
│   ├── furnace-center.js
│   ├── recent-runs.js
│   ├── review-center.js
│   └── execution-center.js
│
├── render/                    # 纯渲染函数 (可测试)
│   ├── home.js                # renderFurnaceCenter 入口
│   ├── input.js               # Universal Input (AskBox + DropZone)
│   ├── today.js               # Today Feed (5 类卡片)
│   ├── advanced.js            # Advanced 抽屉
│   ├── status.js              # System Status 摘要
│   └── cards.js               # 可复用卡片组件
│
├── feed/                      # 数据构建 (纯函数, 优先测试)
│   ├── today-feed.js          # buildTodayFeed (已从 Python mirror)
│   ├── snooze.js              # snooze 过滤
│   └── actions.js             # action 解析
│
├── state/                     # 插件状态管理
│   ├── shell-state.js         # shellSummary 加载/缓存/刷新
│   ├── repo-state.js          # repoState 检测
│   └── settings.js            # 设置持久化
│
├── modals/                    # Modal 子类
│   ├── ask.js
│   ├── drop.js
│   ├── search.js
│   └── protocol.js
│
├── bridge/                    # CLI 桥接
│   └── launcher.js            # runCli, runUniversalInput, shellSummary 加载
│
├── constants.js               # VIEW_TYPE, PRIORITY, LABELS
├── helpers.js                 # i18n, DOM helpers
└── styles.css                 # 按组件分节
```

### 数据流

```
shell-summary.json (runtime)
  └→ shell-state.js (cache + refresh)
       └→ feed/today-feed.js (data transform)
            └→ render/today.js (DOM render)
                 └→ main.js (view registration)
```

---

## 3. UI 布局规划

### 首屏 (FurnaceCenter View)

```
┌──────────────────────────────────────────────┐
│  ┌────────────────────────────────────────┐  │
│  │  🔍  Ask anything, drop URL/PDF/note…  │  │  ← AskBox (auto-height textarea)
│  │                              [ Submit ] │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌─ Today ─────────────────────────────────┐ │
│  │                                         │ │
│  │  📊 Reports (2)                         │ │  ← 按 protocol 着色左侧边条
│  │  ┌─────────────────────────────────┐    │ │
│  │  │ ● [Research] Report Title      │    │ │  ← 未读圆点
│  │  │   generated 2h ago     [ Open ]│    │ │
│  │  └─────────────────────────────────┘    │ │
│  │  ┌─────────────────────────────────┐    │ │
│  │  │   [Investing] Report Title     │    │ │
│  │  │   generated yesterday  [ Open ]│    │ │
│  │  └─────────────────────────────────┘    │ │
│  │                                         │ │
│  │  🤖 Automation                          │ │  ← 自动化状态卡
│  │  ┌─────────────────────────────────┐    │ │
│  │  │ ✓ 已自动维护 — 12:00 nightly   │    │ │
│  │  └─────────────────────────────────┘    │ │
│  │                                         │ │
│  │  ⚡ Needs Your Confirmation (1)         │ │
│  │  ┌─────────────────────────────────┐    │ │
│  │  │ ⚠ Counter-evidence: 3 sources  │    │ │
│  │  │   may rebut judgment X   [ Rev ]│    │ │
│  │  └─────────────────────────────────┘    │ │
│  │                                         │ │
│  │  ✅ Completed (1)                       │ │
│  │  ┌─────────────────────────────────┐    │ │
│  │  │ ✓ Elixir: NVDA Thesis settled  │    │ │
│  │  └─────────────────────────────────┘    │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ▶ 更多工具 (Advanced)                       │  ← 折叠抽屉
│    ┌──────────────────────────────────────┐  │
│    │ System Status · Review Center · …   │  │
│    └──────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 协议色方案

| Protocol | 色标 | CSS Variable |
|---|---|---|
| investing | green | `--furnace-protocol-investing` |
| research | blue | `--furnace-protocol-research` |
| product | purple | `--furnace-protocol-product` |
| ops | orange | `--furnace-protocol-ops` |
| general | gray | `--furnace-protocol-general` |

### 状态机

```
idle → running (submit Ask/Drop)
     → done (new report in Today list, with unread dot)
     → all-read (no unread dots)

error → show inline error in AskBox area (not Notice popup)
     → dismiss on next submit
```

---

## 4. 测试架构

### 框架

```
jest + ts-jest + jest-environment-jsdom
```

### 文件

```
__mocks__/obsidian.js       # Mock Plugin/App/Vault/Notice/Setting/Modal等
src/__tests__/
  feed/today-feed.test.js   # 最高优先: 纯函数, 数据变换
  feed/snooze.test.js
  feed/actions.test.js
  state/shell-state.test.js
  render/home.test.js       # DOM 渲染 (jsdom)
  render/today.test.js
  render/cards.test.js
```

### Mock 策略

- Mock Obsidian namespace (`obsidian` module)
- 每个测试按需 mock 碰到的 API
- 只测自己的逻辑，不测 Obsidian 本身

### 测试金字塔

```
        /\
       /E2E\       Python integration tests (已有)
      /──────\
     /  Render\    jsdom DOM tests (新增)
    /──────────\
   /   Feed     \  纯函数 unit tests (新增, 优先)
  /──────────────\
```

---

## 5. 实现计划

### Phase A: 基础设施 (本 milestone)

1. 搭建 Jest + jsdom + Obsidian mock
2. 拆分 `today_feed.js` → `feed/today-feed.js` (纯函数，与 Python mirror 同步契约)
3. 拆分 `constants.js` / `helpers.js`
4. 写 `feed/today-feed.test.js` (覆盖 buildTodayFeed, applySnoozeFilter, compareEntries)
5. 写 `feed/snooze.test.js`
6. 写 `render/cards.test.js` (覆盖 ReportCard, ConfirmationCard dom 输出)

### Phase B: 模块化重构 (下一 milestone)

1. 拆分 `plugin.js` → `main.js` + `views/*.js` + `bridge/*.js` + `state/*.js`
2. 拆分 `render_*.js` → `render/*.js`
3. 重构 CSS 按组件分节

### Phase C: UX polish (下一 milestone)

1. 协议色左侧条
2. Advanced 抽屉过渡动画
3. 设置面板简化

---

## 6. 构建与调试

### Build

```bash
cd .obsidian/plugins/furnace-product-shell
bash build.sh          # esbuild → main.js
```

### 测试

```bash
cd .obsidian/plugins/furnace-product-shell
npx jest               # 运行所有测试
npx jest --watch       # watch 模式
```

### 调试

```
1. npm run dev (watch build)
2. Obsidian → Ctrl+Shift+I (DevTools)
3. 修改代码 → 自动 rebuild → Obsidian "Reload without saving"
4. console.log / breakpoints in DevTools Sources tab
```

---

## 7. 验收标准

- [ ] Jest 测试框架可用，至少 1 个 mock + 1 个 test 通过
- [ ] `feed/today-feed.js` 拆分完成，与 Python mirror 契约一致
- [ ] `feed/today-feed.test.js` ≥ 10 个 test case
- [ ] `render/cards.test.js` ≥ 3 个 test case（jsdom）
- [ ] `build.sh` 成功，main.js 无 regression
- [ ] `bash scripts/verify.sh` 通过（Python 集成测试不受影响）
