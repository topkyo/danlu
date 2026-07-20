# 炼丹炉用户指南

本指南面向使用炼丹炉做投研、研发或高价值判断的用户。只讲“你怎么用”，不讲 runtime 怎么实现。

## 一句话理解炼丹炉

炼丹炉只做一件事：**把散落的原料炼成可复审的判断资产**。

记住这条主线就够了：

```
raw → compile → wiki → ask → output → file-back → review
```

- **raw**：你扔进去的原料（网页、PDF、图片、repo、会议纪要、随笔）。
- **compile**：炼丹炉把原料整理成结构化的 source page、concept、provenance。
- **wiki**：炼化后的知识沉淀，分为 `wiki/sources/`（来源层）与派生层（`wiki/judgments/` 等）；产品回流默认写 judgment。`wiki/derived/` 若存在多为历史/legacy 锚点，不是现行 `file-back` 目标。
- **ask**：你向炉子提问，生成一篇自由 Markdown 报告（`output/reports/*.md`）；LLM 按问题组织内容，不再强制六段骨架或多 format 分叉。
- **output**：产出物，包括报告、仪表盘、审计 receipt。
- **file-back**：把高价值结论写回 wiki，形成可积累的判断资产。
- **review / nightly / judgment**：定期审阅、 aging、修复、沉淀金丹（跨周期复用的 thesis）。

## 两个日常入口

### 入口一：Obsidian Product Shell

打开 vault 后，左侧边栏的 **Furnace Product Shell** 是默认极简工作台。首屏只暴露最常用的动作：

- **投料**：Drop URL / Drop File / Drop Image / Drop Text
- **Ask**：输入问题，走 `run-ask`
- **今日简报**：today，看最新产出
- **更多工具**：折叠在面板底部，包含 compile、lint、review queue、执行审计等

Product Shell 适合日常快速投料和查看状态。复杂治理操作建议用 launcher / CLI。

### 入口二：CLI launcher

在 vault 根目录下使用 `scripts/aiwiki-launcher.sh`：

```bash
# 投料
./scripts/aiwiki-launcher.sh drop markdown --title "某券商会议纪要" --text "..."
./scripts/aiwiki-launcher.sh drop url https://example.com/article
./scripts/aiwiki-launcher.sh drop pdf /path/to/report.pdf
./scripts/aiwiki-launcher.sh drop image /path/to/chart.png
./scripts/aiwiki-launcher.sh drop repo https://github.com/org/repo.git
# 万能入口：一条 payload（URL / 本地路径 / 问题）→ 默认 LLM 计划再确定性执行
./scripts/aiwiki-launcher.sh drop https://github.com/org/repo
./scripts/aiwiki-launcher.sh drop plan https://github.com/org/repo   # 只看计划，不写 raw
# 关闭 planner、退回确定性分类：AIWIKI_LLM_PLANNER=0

# 看今日简报
./scripts/aiwiki-launcher.sh today

# 进入高级操作面
./scripts/aiwiki-launcher.sh advanced --help
```

> 日常默认记住两条命令：`aiwiki drop ...` 投料，`aiwiki today` 看产出。

## 投研场景 walkthrough（5 步）

下面以投资研究为例，演示一个完整循环。

### 第 1 步：投料

把研究过程中遇到的材料丢进炉子：

- 财报 PDF → `./scripts/aiwiki-launcher.sh drop pdf 2025q2-report.pdf`
- 赛道文章 URL → `./scripts/aiwiki-launcher.sh drop url https://...`
- 会议纪要文字 → `./scripts/aiwiki-launcher.sh drop markdown --title "某专家访谈" --text "..."`
- 产业链图 → `./scripts/aiwiki-launcher.sh drop image supply-chain.png`

文本、Markdown、URL 抓取和 repo snapshot 会进入 `raw/inbox/`；PDF、image 原件会进入 `raw/assets/`。不要把二进制原件手动放进 `raw/inbox/`。

成功投料后，runtime **默认**会跑一轮确定性 `compile` + `lint`（P8 投料即煅烧）；若只想入 raw 暂不炼化，加 `--no-auto`。  
万能 `drop <payload>` 默认先经 LLM planner 分类（github 仓库根 URL 会优先 `fetch_raw` README，而不是误走会触发阻断/空抓取的路径）；planner 失败或 `AIWIKI_LLM_PLANNER=0` 时回退确定性分类器。

同一规范化 URL（含 GitHub 仓库根与对应 raw README）再投一次时**默认复用**已有 `raw/` 条目，不新建 `-2/-3` 文件；需要重抓时加 `--refresh`。纯投料只入 raw / compile，**不会**自动写出 `output/reports`；要报告请再提问（或「材料 + 问题」一并提交）。

### 第 2 步：编译

投料默认已触发 compile；需要手动全量重炼时再跑：

```bash
./scripts/aiwiki-launcher.sh advanced compile
```

这会生成：

- `wiki/sources/`：每条原料对应的来源页，保留 provenance 和原文索引。
- `wiki/concepts/` 等：compile 派生概念与关系（人读索引）。
- `wiki/judgments/`：`file-back` 回流的判断页（金丹可锚定）。
- `output/control/`：状态摘要、review queue 等控制面（lint 报告在 `.aiwiki/lint/`）。

定时维护（watcher / nightly / `run-nightly`）只做确定性 `compile` + `lint` + nightly health 写入；LLM 仅通过 `run-ask` 等显式入口参与。

```bash
./scripts/aiwiki-launcher.sh advanced nightly
# 与 timer 同语义：
./scripts/aiwiki-launcher.sh advanced run-nightly
```

### 第 3 步：提问

基于已编译的 wiki 提问：

```bash
./scripts/aiwiki-launcher.sh advanced run-ask \
  "对比 A 公司与 B 公司在 thesis、catalyst、risk、invalidation 四个维度"
```

Ask 只产出 `output/reports/*.md` 自由 Markdown 报告（CLI 仅接受 `--format report`，旧 format 如 `note` / `slides` 会立即失败）。失败时会写 receipt 与可审计失败说明，**不会假装成功**。

### 第 4 步：回流

看到值得长期保留的结论，把它写回 wiki（默认写 judgment 页，进入薄审阅流程）：

```bash
./scripts/aiwiki-launcher.sh advanced file-back output/reports/xxx.md
```

产品面 `file-back` **只写 judgment**（CLI 可省略 `--kind`，或显式 `--kind judgment`）；`--kind derived|decision` 已删除。

### 第 5 步：复盘与金丹

周期结束后，回头看判断是否正确。审阅状态机已收敛为薄三态：**待审** / **已确认** / **废弃**（CLI 可用 transition token `pending-review` / `confirmed` / `discarded`，或 canonical status）：

```bash
# 确认 judgment（薄 transition → confirmed）
./scripts/aiwiki-launcher.sh advanced review-page wiki/judgments/xxx.md --status confirmed --note "..."

# 废弃
./scripts/aiwiki-launcher.sh advanced review-page wiki/judgments/xxx.md --status discarded --note "..."
```

`review-page` 只支持单页薄三态；`--batch` / `--next` / `--all-pending` 等产品批量入口已删除。

沉淀下来的 reusable thesis 会变成 `wiki/elixirs/` 中的金丹，供下一轮研究引用：

```bash
# 每晚自动巡检（确定性 compile + lint）
./scripts/aiwiki-launcher.sh advanced nightly

# 启动 / 蒸馏 / 定稿金丹（跨周期 reusable thesis）
./scripts/aiwiki-launcher.sh advanced alchemy-start --help
./scripts/aiwiki-launcher.sh advanced alchemy-distill --help
./scripts/aiwiki-launcher.sh advanced alchemy-finalize --help
```

## 单 runtime 协议

炼丹炉只有一个协议 runtime：`general`。领域差异通过概念、判断和 schema 扩展表达，不再提供多 protocol 切换或 `--protocol` 覆盖。

- 规则层见 vault 内 `schema/protocols/general/`。
- 旧 vault 若 state 里仍写着 `investing` / `research` 等非 `general` slug，runtime 会在加载时一次性迁移到 `general` 并重写 `.aiwiki/state/protocol.json`。
- `protocol-set`、`protocol-status`、`protocol-learn-*` 等历史 CLI 已删除；Product Shell 也不再提供协议选择器。

## 失败处理三态

炼丹炉不会把 LLM 失败伪装成成功。你通常只会遇到三种状态：

### 1. 未配置 LLM

表现：`run-ask` 提示没有可用的 LLM backend。

处理：配置 key，然后跑 `./scripts/aiwiki-launcher.sh advanced llm-check --probe`。不影响确定性链路（投料、compile、today、lint）。

### 2. 生成中 / 超时

表现：命令卡住或 timeout。

处理：`run-ask` 默认会在 timeout 后自动尝试一次 lean prompt；你也可以手动加 `--lean` 或 `--timeout <秒数>`。如果还是失败，会写失败 receipt，稍后重跑即可。

### 3. 需处理

表现：`output/control/shell-summary.json` 显示异常，或 `review-queue.md`、`repair-backlog.md` 有内容。

处理：先跑 `./scripts/aiwiki-launcher.sh advanced lint` 定位问题；再看 `.aiwiki/state/execution-receipts/` 找到失败命令；必要时手动修复原料或配置后重跑。

## 治理面板怎么看

炼丹炉的治理面板不是给每个人天天看的，而是“人只看异常”：

- **review-queue.md**：需要人工审阅的 judgment / decision / proposal。
- **aging-report.md**：长时间未 revisit 的判断资产，提示是否该更新或归档。
- **repair-backlog.md**：lint 或 nightly 发现的结构性问题，待修复。

打开方式：

```bash
# 在 Obsidian 中直接打开 wiki/indexes/review-queue.md
# 或用 launcher
./scripts/aiwiki-launcher.sh advanced review-queue
```

## 你不需关心的事

以下内容是开发者或 operator 才需要看的，普通用户可以跳过：

- owner map、模块边界图、seam map
- P1-P5 稳定化清单
- `PYTHONPATH=src python3 -m aiwiki.cli ...` 这类开发命令（vault 内用 launcher 即可）
- `.aiwiki/state` 内部结构

## 下一步

- 刚安装：先看 `HOME.md`，再跑一遍 5 分钟验证链路。
- 日常用：Product Shell 投料 + `today` 看产出。
- 做深度研究：按“投料 → 编译 → 提问 → 回流 → 复盘”循环跑。
- 遇到问题：先查 `output/control/shell-summary.json` 和 `.aiwiki/state/execution-receipts/`，再跑 `advanced lint`。
