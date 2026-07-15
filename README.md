# 炼丹炉

**为投资研究和技术研发，把原料炼成可复审的判断资产。**

炼丹炉是一套面向投资研究、技术研发和高价值判断场景的 `local-first` 知识复利操作系统。它把网页、PDF、图片、repo、会议纪要和本地笔记等原料，持续编译成可追溯的 `wiki`、`machine memory`、`decision / judgment` 和可回流输出；它不是静态笔记库，也不是一次性 RAG 问答器，而是一个帮助你长期积累 thesis、研究结论、技术判断和复审历史的认知系统。

仓库、CLI 和底层 runtime 仍然叫 `aiwiki`；`aiwiki` 是炼丹炉的实现内核。

## 一句话理解

`raw -> compile -> wiki -> ask -> output -> file-back -> review / nightly`

- `raw/`：输入
- `wiki/`：沉淀
- `output/`：输出
- `schema/`：规则
- `.aiwiki/`：machine memory、状态、缓存

## 它是什么

- 五层主线：`raw / wiki / machine memory / schema / outputs`
- 治理链：`review / aging / escalation / repair / nightly`
- 判断层：`decision / judgment`
- 协议层：`general / investing / research / product / ops`
- 执行层：`dry-run / bundle / apply / receipt / revert / audit`

Obsidian 是前端；炼丹炉是整个系统；`aiwiki` 是底层 runtime。Product Shell **仅正式支持 Desktop Obsidian**。

## 更适合谁

- 投资研究者：财报、电话会、访谈、赛道资料与判断复审。
- 技术研发者：论文、repo、实验、benchmark 与架构权衡。

## 快速开始

1. 安装与 LLM 配置：[docs/INSTALL.md](./docs/INSTALL.md)
2. 日常投料 / 提问 / 审阅：[docs/USER_GUIDE.md](./docs/USER_GUIDE.md)
3. 新建 vault（在已克隆的 runtime 仓库内）：

```bash
./scripts/aiwiki-launcher.sh advanced new-vault ../demo-furnace-vault
cd ../demo-furnace-vault
./scripts/aiwiki-launcher.sh advanced shell-status
./scripts/aiwiki-launcher.sh advanced compile
```

日常入口推荐：

- Obsidian Product Shell：投料、提问、看 Today
- `scripts/aiwiki-launcher.sh`：脚本化入口；完整治理能力在 `advanced ...`

两边共享同一 vault 的 `.aiwiki/state` 与 `raw/wiki/output`，遵守 `single writer, many readers`。

## 最小工作流

```bash
./scripts/aiwiki-launcher.sh drop markdown --title "Morning material" --text "Capture the latest signal."
./scripts/aiwiki-launcher.sh advanced compile
./scripts/aiwiki-launcher.sh advanced run-ask "Compare A and B on thesis, catalyst, risk" --format report
./scripts/aiwiki-launcher.sh advanced file-back output/reports/xxx.md
./scripts/aiwiki-launcher.sh advanced nightly
```

更多命令与失败三态见 [USER_GUIDE.md](./docs/USER_GUIDE.md)。

## 文档入口

- 安装：[INSTALL.md](./docs/INSTALL.md)
- 用户指南：[USER_GUIDE.md](./docs/USER_GUIDE.md)
- 开发者指南（owner map / verify / LLM 细节）：[docs/DEVELOPER.md](./docs/DEVELOPER.md)
- 商业文档：[docs/commercial/](./docs/commercial/) · [LICENSE](./LICENSE) · [CHANGELOG.md](./CHANGELOG.md)
- 架构 SoT：[Furnace Agent Architecture](./docs/Furnace%20Agent%20Architecture.md) · [Evolution Mechanics](./docs/Furnace%20Evolution%20Mechanics.md)
- 运行手册：[Runtime Operations](./docs/Furnace%20Runtime%20Operations.md)
- 当前清理计划：[Commercial Grade Cleanup Plan 2026-07](./docs/Furnace%20Commercial%20Grade%20Cleanup%20Plan%202026-07.md)
- Obsidian 工作台：[HOME.md](./HOME.md)
- 文档索引：[docs/README.md](./docs/README.md)

## 控制台与索引页

`wiki/indexes/*.md`（除手写策略页 [wiki/indexes/README.md](./wiki/indexes/README.md)）是 **compile 生成的派生索引**，不入库。在 vault 内先 `compile`，再打开：

- Obsidian：炉心 / 审阅 / 图谱等索引页（由 compile 写入 `wiki/indexes/`）
- 本地 HTML：`output/control/furnace-center.html`、`output/control/execution-center.html`、`output/graph/machine-memory.html` 等

## 协议与边界

协议：`general` / `investing` / `research` / `product` / `ops`。切换见 USER_GUIDE。

硬边界：

- `raw/` 是唯一事实输入层；派生输出不能覆盖它
- `wiki/sources/` 与 derived / decisions / judgments 严格分层
- safe execution 只开放低风险动作；mutation 必须 receipt / 可审计 / 可回滚
- 运行模型：`single writer, many readers`
- LLM 失败 fail-closed，不伪装 deterministic 成功；不隐式跨 backend fallback

## 验证

```bash
bash scripts/verify.sh
```

按改动路径选 target、coverage、acceptance 等细节见 [docs/DEVELOPER.md](./docs/DEVELOPER.md)。
