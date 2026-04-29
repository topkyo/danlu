---
title: "炼丹炉 Product UX 评估"
kind: "product-review"
status: "draft"
owner: "tim"
created_at: 2026-04-29
related_docs:
  - docs/Furnace Product Shell.md
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
---

# 炼丹炉 Product UX 评估

## 结论

从产品经理和普通用户角度看，炼丹炉的底层能力已经很强，但 Obsidian 插件和默认工作区仍偏“operator 控制台”，还没有完全变成“用户每天只管投料、提问、看结果”的产品壳。

当前方向是对的：Product Shell 已经在实现“一个输入端 + 一个输出端”。但默认布局、Today feed 的可操作性、左侧导航的信息密度，还会让普通用户感到系统概念过多。

建议把下一步收敛为一个小 milestone：`M-UX.1`，只改插件体验和默认 workspace，不改 runtime。

## 当前评价

| 维度 | 评价 |
| --- | --- |
| 产品定位 | 清晰：local-first 研究/判断资产系统 |
| 插件首屏 | 方向正确，但输出项不够可操作 |
| 左侧导航 | 对 operator 有用，对普通用户信息过载 |
| 右侧布局 | 炉心面板放右侧会削弱“主入口”感 |
| 新用户易用性 | 能摸索，但第一眼不知道“现在只该做哪件事” |
| UI 视觉 | 克制、贴合 Obsidian，但层级和行动按钮不足 |

## 关键发现

### 1. Today feed 不够可操作

`render_home.js` 已按正确顺序渲染：输入、Today、Advanced。

对应实现：`.obsidian/plugins/furnace-product-shell/src/render_home.js`

但 `render_today.js` 目前主要把 `target` 渲染成文本。用户看到了“该做什么”，但不能顺手完成。

应该让每条 Today item 都成为可操作卡片：

- report：`Open`
- review item：`Open page`
- action：`Copy command` 或受控 `Run`
- proposal：`Open proposal` / `Reject` / `Apply` 仅在安全边界允许时出现

### 2. 左侧导航暴露了太多 runtime 层

repo workspace 左侧默认包含文件列表、raw/wiki/output/schema 四个搜索页签、书签。

对应文件：`.obsidian/workspace.json`

dogfood vault 里也类似，而且多个搜索页签标题都叫“搜索”。这对 operator 有效率，但普通用户会被迫理解 `raw/wiki/output/schema` 的 runtime 分层。

普通用户默认不应该先理解目录分层，才能开始使用炼丹炉。

### 3. 炉心面板被放在右侧，不像主入口

插件打开视图时优先使用 right leaf。

对应实现：`.obsidian/plugins/furnace-product-shell/src/plugin.js`

这对辅助面板合理，但 Product Shell 是核心入口，应默认出现在主工作区，而不是右侧窄栏。右侧更适合 outline、backlinks、recent runs、debug surface。

### 4. HOME 仍是索引页，不是产品首页

repo 的 `HOME.md` 暴露大量入口。dogfood vault 的 `HOME.md` 已收敛很多，但仍让用户先看 wiki/source/concept/graph/furnace-center。

产品心智应该是：先打开炼丹炉；其他路径只是详情。

### 5. 本地插件数据存在凭据落盘风险

`.obsidian/plugins/furnace-product-shell/data.json` 中存在本地 LLM key 字段和值。该文件目前未被 git 跟踪，且 `.gitignore` 已忽略 `data.json`，但凭据仍是明文落盘。

建议：

- 确认这些 key 是否真实有效。
- 如果有效，进行轮换。
- 优先使用环境变量或系统 keychain。
- 插件设置页保留输入能力，但文档明确“不提交、不共享、不截图”。

本评估不记录任何具体密钥值。

## 左侧导航评估

当前左侧导航不建议作为普通用户主导航。

更合理的默认布局：

| 区域 | 默认展示 |
| --- | --- |
| 主区 | 炼丹炉 Product Shell |
| 左侧 | 文件列表 + 书签 |
| 左侧书签 | 今日、收件箱、报告、判断、金丹、README |
| 右侧 | 默认折叠，或只保留 Outline / Backlinks |
| Advanced | Review、Execution、Recent Runs、schema、audit、raw/wiki/output 搜索 |

如果保留搜索页签，至少要明确命名：

- `原料 raw`
- `知识 wiki`
- `输出 output`
- `规则 schema`

不要都叫“搜索”。

## 产品经理视角

炼丹炉的核心价值不是“能跑很多命令”，而是让用户形成习惯：

1. 投料。
2. 等报告。
3. 看 Today。
4. 审一个关键判断。
5. 把高价值结果沉淀成判断或金丹。

所以 UI 不该默认展示 execution、repair、schema、metrics、recent runs。它们是信任系统的一部分，但不是用户日常路径。

产品壳的默认目标应该是：降低用户必须理解的概念数量，而不是展示系统能力完整性。

## 普通用户视角

第一次打开时，用户最容易有三个困惑：

1. “我应该在 HOME、炉心面板、左侧文件树还是命令面板开始？”
2. “Today 里这条 target / command 是让我复制，还是点开，还是运行？”
3. “raw / wiki / output / schema 是我需要管理的东西，还是系统内部结构？”

这些困惑说明当前产品壳还差一层“行动翻译”：把 runtime 语言翻译成用户语言。

## 最高 ROI 改进：M-UX.1

建议开一个小 milestone：`M-UX.1 Product Shell Daily Usability`。

### 范围

- 不改 runtime。
- 不改 schema。
- 不改 review/apply/revert/audit 边界。
- 只改插件 UI、默认 workspace 和 HOME 文案。

### 验收标准

- 用户打开 vault 后，主区默认就是 Product Shell。
- 首屏只有一个输入框、一个 Today 输出区和一个 Advanced 折叠区。
- Today item 至少支持 `Open` 或 `Copy command`。
- 左侧默认不再暴露四个 runtime 搜索页签。
- Advanced 中仍保留 Review / Execution / Recent Runs / Metrics / LLM health。
- 本地凭据不进入 git，不在文档、receipt、audit 中泄漏。

### 建议改动

1. Today feed 每条变成可点击卡片。
2. 默认打开 Furnace Center 到主 pane，而不是右侧 pane。
3. 左侧默认只保留文件列表和书签，raw/wiki/output/schema 搜索移到 Advanced。
4. 输入框下加短提示：`投 URL / 文件 / 图片，或直接问一个问题。Ctrl+Enter 提交。`
5. Advanced summary 加说明和计数：`高级：审阅 4 · 执行 0 · 最近运行 2`。
6. HOME 改成产品入口说明，不再承担全量索引职责。

## 风险

- 老用户可能找不到原来的控制台入口。缓解方式：Advanced 保留，并在 summary 中展示“审阅 / 执行 / 最近运行”。
- workspace 改动可能影响个人 Obsidian 布局。缓解方式：只改 starter/new-vault 默认布局；已有 vault 不做隐式迁移。
- Today 直接执行命令可能越过安全边界。缓解方式：首版只做 `Open` 和 `Copy command`，真实 `Run` 只对已明确 low-risk 且有 dry-run/receipt 语义的动作开放。

## 一句话判断

炼丹炉的 runtime 已经像一台复杂但可靠的炉子；Product Shell 下一步要做的是把炉门、投料口和出丹口打磨成用户一眼能懂、每天愿意打开的入口。
