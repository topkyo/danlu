# 炼丹炉 Furnace

> 本仓库是定期导出的展示树（不含内部计划、`docs/archive/`、`PROGRESS.md`）。不接受外部 PR。安全披露见 [SECURITY.md](./SECURITY.md)。


**为投资研究和技术研发，把原料炼成可复审的判断资产。**
**Turn raw material into reviewable judgment assets for investment research and technical R&D.**

[AGPL-3.0](./LICENSE) · [Contributing](./CONTRIBUTING.md) · [Security](./SECURITY.md) · [中文](#中文) · [English](#english)

硬边界：macOS / Linux · Desktop Obsidian · 不是投资建议。`new-vault` / `compile` / `today` **不需要** API key；Ask 与万能 `drop` planner 需要。

---

## 中文

炼丹炉是一套面向投资研究、技术研发和高价值判断场景的 `local-first` 知识复利操作系统。它把网页、PDF、图片、repo、会议纪要和本地笔记等原料，持续编译成可追溯的 `wiki`、`machine memory`、`decision / judgment` 和可回流输出；它不是静态笔记库，也不是一次性 RAG 问答器，而是一个帮助你长期积累 thesis、研究结论、技术判断和复审历史的认知系统。

仓库、CLI 和底层 runtime 仍然叫 `aiwiki`；`aiwiki` 是炼丹炉的实现内核。

> **品类定位**：炼丹炉是 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 模式的 **production runtime**——`raw → wiki → schema` 编译复利，外加 deterministic baseline、execution receipt / revert、单 runtime 协议（`general`）与 Desktop Obsidian Product Shell。它不是「又一个 RAG 聊天插件」，也不是仅靠 `AGENTS.md` 驱动的 skill 包。

| 角色 | 名字 |
|------|------|
| 对外产品名 | 炼丹炉 / Furnace |
| 包 / CLI | `aiwiki` |
| GitHub 仓库 | `topkyo/danlu` |
| Obsidian 插件 | `furnace-product-shell` |

### 一句话理解

`raw -> compile -> wiki -> ask -> output -> file-back -> review / nightly`（层名 shorthand；CLI 是 `drop` / `today` / `advanced …`）

- `raw/`：输入
- `wiki/`：沉淀
- `output/`：输出
- `schema/`：规则
- `.aiwiki/`：machine memory、状态、缓存

### 它是什么

- 五层主线：`raw / wiki / machine memory / schema / outputs`
- 治理链：`review / aging / escalation / repair / nightly`
- 判断层：`decision / judgment`
- 协议层：单 runtime `general`（领域差异通过 schema / 概念 / judgment 扩展）
- 执行层：显式 LLM（`run-ask` / universal `drop` planner）+ deterministic `compile`/`lint` + receipt/audit 闭环

Obsidian 是前端；炼丹炉是整个系统；`aiwiki` 是底层 runtime。Product Shell **仅正式支持 Desktop Obsidian**。

### 更适合谁

- 投资研究者：财报、电话会、访谈、赛道资料与判断复审。
- 技术研发者：论文、repo、实验、benchmark 与架构权衡。

### 快速开始

```bash
git clone https://github.com/topkyo/danlu.git aiwiki
cd aiwiki
pip install -e . --break-system-packages   # 获得 aiwiki console script（需 Python ≥3.10；无 PEP 668 可去掉 flag）
aiwiki advanced new-vault ../demo-furnace-vault
cd ../demo-furnace-vault
aiwiki advanced shell-status
aiwiki advanced compile
```

然后用 Obsidian 打开 `../demo-furnace-vault`，启用 **Furnace Product Shell**。上面四条命令不需要 LLM key。

入口约定：

- **日常唯一入口：Obsidian Product Shell**——投料、提问、看 Today、打开报告。
- **终端 / 自动化：`aiwiki` console script**——`aiwiki drop ...`、`aiwiki advanced ...`；完整治理能力在 `advanced ...`。
- 两边共享同一 vault 的 `.aiwiki/state` 与 `raw/wiki/output`，遵守 `single writer, many readers`。

产品默认 LLM 路由为 `deepseek-api` + `deepseek-v4-flash`（Ask 可经 DeepSeek Responses `web_search` 联网调研）；`deepseek-v4-pro` 可选手动切换（V1 无提供商联网）。详细安装与 LLM 配置见 [docs/INSTALL.md](./docs/INSTALL.md)。

### 最小工作流

```bash
aiwiki drop markdown --title "Morning material" --text "Capture the latest signal."
aiwiki advanced compile
aiwiki advanced run-ask "Compare A and B on thesis, catalyst, risk"
aiwiki advanced file-back output/reports/xxx.md
aiwiki advanced run-nightly
```

更多命令与失败三态见 [USER_GUIDE.md](./docs/USER_GUIDE.md)。

### 文档入口

- 安装：[INSTALL.md](./docs/INSTALL.md)
- 用户指南：[USER_GUIDE.md](./docs/USER_GUIDE.md)
- 贡献 / 安全：[CONTRIBUTING.md](./CONTRIBUTING.md) · [SECURITY.md](./SECURITY.md)
- 开发者指南（owner map / verify / LLM 细节）：[docs/DEVELOPER.md](./docs/DEVELOPER.md)
- 商业文档：[docs/commercial/](./docs/commercial/) · [LICENSE](./LICENSE) · [CHANGELOG.md](./CHANGELOG.md)
- 架构 SoT：[Furnace Agent Architecture](./docs/Furnace%20Agent%20Architecture.md) · [Evolution Mechanics](./docs/Furnace%20Evolution%20Mechanics.md)
- 运行手册：[Runtime Operations](./docs/Furnace%20Runtime%20Operations.md)
- Obsidian 工作台：[HOME.md](./HOME.md)
- 文档索引：[docs/README.md](./docs/README.md)

### 控制台与索引页

`wiki/indexes/*.md`（除手写策略页 [wiki/indexes/README.md](./wiki/indexes/README.md)）是 **compile 生成的派生索引**，不入库。在 vault 内先 `compile`，再打开。页面分三层：

- **首屏**：`furnace-center.md`（炉心面板）——今天做什么 / 最近输出 / 快速跳转，Obsidian 里唯一的日常入口。
- **治理细节**：`review-center.md`（审阅中心）、`repair-backlog.md`（修复待办）、`review-queue.md`、`compile-status.md`、`machine-memory.md`、`protocols.md`——炉心面板只做摘要与跳转，细节看这些页。
- **全量索引**：`index.md` 主索引 + `sources/concepts/decisions/judgments/judgment-assets` 分类索引；`graph-view.md` 看证据链邻接。

机器记忆邻接 JSON：`.aiwiki/cache/machine-memory-graph.json`（compile 写入；**HTML 控制面已停写**）。在生/退役页面的完整清单与 writer 对照见 [wiki/indexes/README.md](./wiki/indexes/README.md)。

### 协议与边界

协议：只有一个 runtime `general`。旧 vault 中非 `general` 的 state 会在加载时一次性迁移；不再提供多 protocol 切换 CLI。详见 [USER_GUIDE.md](./docs/USER_GUIDE.md)。

硬边界：

- `raw/` 是唯一事实输入层；派生输出不能覆盖它
- `wiki/sources/` 与 derived / decisions / judgments 严格分层
- safe execution 只开放低风险动作；mutation 必须 receipt / 可审计 / 可回滚
- 运行模型：`single writer, many readers`
- LLM 失败 fail-closed，不伪装 deterministic 成功；不隐式跨 backend 切换
- POSIX only（macOS / Linux）；Product Shell 仅 Desktop Obsidian；不是投资建议

### 验证

```bash
bash scripts/verify.sh
```

按改动路径选 target、acceptance / llm-integration 等细节见 [docs/DEVELOPER.md](./docs/DEVELOPER.md)。

---

## English

Furnace is a `local-first` knowledge-compounding system for investment research, technical R&D, and high-value judgment work. It continuously compiles raw material (web pages, PDFs, images, repos, meeting notes, local notes) into traceable `wiki`, `machine memory`, `decision / judgment` pages, and reviewable outputs. It is not a static note archive and not a one-shot RAG chatbot; it is a cognitive system for accumulating theses, research conclusions, technical judgments, and review history over time.

The repo, CLI, and underlying runtime are still called `aiwiki`; `aiwiki` is the implementation kernel of Furnace.

> **Category**: Furnace is the **production runtime** of the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern — `raw → wiki → schema` compile compounding, plus a deterministic baseline, execution receipts / revert, a single runtime protocol (`general`), and a Desktop Obsidian Product Shell. It is not "yet another RAG chat plugin".

| Role | Name |
|------|------|
| Product | 炼丹炉 / Furnace |
| Package / CLI | `aiwiki` |
| GitHub | `topkyo/danlu` |
| Obsidian plugin | `furnace-product-shell` |

### The loop in one line

`raw -> compile -> wiki -> ask -> output -> file-back -> review / nightly` (layer names, not CLI argv; use `drop` / `today` / `advanced …`)

### Who it is for

- Investment researchers: filings, earnings calls, interviews, sector material, and judgment review.
- Technical R&D: papers, repos, experiments, benchmarks, and architecture trade-offs.

### Quick start

```bash
git clone https://github.com/topkyo/danlu.git aiwiki
cd aiwiki
pip install -e . --break-system-packages   # installs the aiwiki console script (Python >=3.10)
aiwiki advanced new-vault ../demo-furnace-vault
cd ../demo-furnace-vault
aiwiki advanced shell-status
aiwiki advanced compile
```

Then open `../demo-furnace-vault` in Obsidian and enable **Furnace Product Shell**. The commands above do not need an LLM API key.

Entry points:

- **Daily driver: the Obsidian Product Shell** — drop material, ask questions, read Today, open reports.
- **Terminal / automation: the `aiwiki` console script** — `aiwiki drop ...`, `aiwiki advanced ...`.
- Both share the same vault state under `single writer, many readers`.

The default LLM route is DeepSeek's official API (`deepseek-api` + `deepseek-v4-flash`), which enables provider-side `web_search` for Ask; `deepseek-v4-pro` remains an optional manual choice without V1 web search. Configure in plugin settings or via env; other backends stay available as explicit escape hatches. See [docs/INSTALL.md](./docs/INSTALL.md).

### Documentation

- Install: [INSTALL.md](./docs/INSTALL.md) · User guide: [USER_GUIDE.md](./docs/USER_GUIDE.md) · Contributing: [CONTRIBUTING.md](./CONTRIBUTING.md) · Security: [SECURITY.md](./SECURITY.md) · Developer: [docs/DEVELOPER.md](./docs/DEVELOPER.md)
- Architecture SoT: [Furnace Agent Architecture](./docs/Furnace%20Agent%20Architecture.md) · [Evolution Mechanics](./docs/Furnace%20Evolution%20Mechanics.md) · Ops: [Runtime Operations](./docs/Furnace%20Runtime%20Operations.md)
- Commercial: [docs/commercial/](./docs/commercial/) · [LICENSE](./LICENSE) · [CHANGELOG.md](./CHANGELOG.md) · Docs index: [docs/README.md](./docs/README.md)

### Hard boundaries

- `raw/` is the only source-of-truth input layer; derived outputs never overwrite it.
- `wiki/sources/` is strictly layered from derived / decisions / judgments.
- Mutations must be receipted, auditable, and revertable; the runtime model is `single writer, many readers`.
- LLM failures are fail-closed; the runtime never pretends a degraded run succeeded and never silently switches backends.
- POSIX only (macOS / Linux). Product Shell is Desktop Obsidian only. This is a research compiler, not investment advice.

### Verify

```bash
bash scripts/verify.sh
```
