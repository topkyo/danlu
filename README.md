# 炼丹炉

**为投资研究和技术研发，把原料炼成可复审的判断资产。**

炼丹炉是一套面向投资研究、技术研发和高价值判断场景的 `local-first` 知识复利操作系统。它把网页、PDF、图片、repo、会议纪要和本地笔记等原料，持续编译成可追溯的 `wiki`、`machine memory`、`decision / judgment` 和可回流输出；它不是静态笔记库，也不是一次性 RAG 问答器，而是一个帮助你长期积累 thesis、研究结论、技术判断和复审历史的认知系统。

仓库、CLI 和底层 runtime 仍然叫 `aiwiki`；`aiwiki` 是炼丹炉的实现内核。

这条分支是炼丹炉的“投资/研发版 README”，文案会更偏：
- 公司 / 赛道 / thesis / catalyst / risk / invalidation
- paper / repo / benchmark / experiment / architecture decision
- report -> judgment -> review -> revisit 这条长期研究链

## 一句话理解

只记住这条链就够了：

`raw -> compile -> wiki -> ask -> output -> file-back -> review / nightly`

其中：
- `raw/`：输入
- `wiki/`：沉淀
- `output/`：输出
- `schema/`：规则
- `.aiwiki/`：machine memory、状态、缓存

## 它是什么

炼丹炉现在已经有这些底座，底层 runtime 由 `aiwiki` 提供：
- 五层主线：`raw / wiki / machine memory / schema / outputs`
- 治理链：`review / aging / escalation / repair / nightly`
- 判断层：`decision / judgment`
- 协议层：`general / investing / research / product / ops`
- 执行层：`dry-run / bundle / apply / receipt / revert / audit`

Obsidian 是前端/IDE；炼丹炉是整个系统；`aiwiki` 是底层 runtime。

## 更适合谁

- 投资研究者：想把财报、电话会、访谈、赛道资料、判断变化和复审记录放进同一个炉子。
- 技术研发者：想把论文、repo、实验、benchmark、设计权衡和技术判断沉淀成长期资产。

如果你更关心通用产品入口，而不是投资/研发场景，可以回到 `main` 分支。

## 最小工作流

1. 投料

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
```

2. 编译

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
```

3. 提问并出结果

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare company A and company B on thesis, catalyst, risk, and invalidation" --format report
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare paper A and repo B on architecture tradeoffs and benchmark evidence" --format report
```

4. 回流高价值结果

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . file-back output/reports/xxx.md
```

5. 审阅与巡检

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/example.md --status approved --note "Reviewed."
PYTHONPATH=src python3 -m aiwiki.cli --root . lint
PYTHONPATH=src python3 -m aiwiki.cli --root . nightly
```

## 日常入口

- Obsidian 工作台：[HOME.md](./HOME.md)
- 炼丹炉基线架构：[Alchemy Furnace.md](<./wiki/indexes/Alchemy Furnace.md>)
- 最终极形态：[Furnace Ultimate Architecture.md](<./wiki/indexes/Furnace Ultimate Architecture.md>)
- 当前能力地图与下一轮 Product Shell contract：[Furnace Capability Map.md](<./wiki/indexes/Furnace Capability Map.md>)
- 增量编译计划：[Furnace Incremental Compile Plan.md](<./wiki/indexes/Furnace Incremental Compile Plan.md>)
- Product Shell 插件设计：[Furnace Product Shell Plugin.md](<./wiki/indexes/Furnace Product Shell Plugin.md>)
- 大规模原料处理设计：[Furnace Material Scaling.md](<./wiki/indexes/Furnace Material Scaling.md>)
- 统一炉子 + 多协议：[Furnace Protocols.md](<./wiki/indexes/Furnace Protocols.md>)

### 控制台

- 炉心面板：[furnace-center.md](<./wiki/indexes/furnace-center.md>)
- 执行中心：[execution-center.md](<./wiki/indexes/execution-center.md>)
- 执行审计：[execution-audit.md](<./wiki/indexes/execution-audit.md>)
- 审阅中心：[review-center.md](<./wiki/indexes/review-center.md>)
- 图谱视图：[graph-view.md](<./wiki/indexes/graph-view.md>)

本地 HTML 面板：
- `output/control/furnace-center.html`
- `output/control/execution-center.html`
- `output/control/execution-audit.html`
- `output/graph/machine-memory.html`
- `output/review/review-center.html`

### 运行状态页

- [protocols.md](<./wiki/indexes/protocols.md>)
- [review-queue.md](<./wiki/indexes/review-queue.md>)
- [aging-report.md](<./wiki/indexes/aging-report.md>)
- [repair-backlog.md](<./wiki/indexes/repair-backlog.md>)
- [rewrite-proposals.md](<./wiki/indexes/rewrite-proposals.md>)
- [machine-memory.md](<./wiki/indexes/machine-memory.md>)
- [machine-memory-actions.md](<./wiki/indexes/machine-memory-actions.md>)
- [machine-memory-repair-plan.md](<./wiki/indexes/machine-memory-repair-plan.md>)
- [cognitive-history.md](<./wiki/indexes/cognitive-history.md>)
- [judgment-assets.md](<./wiki/indexes/judgment-assets.md>)
- [output-packs.md](<./wiki/indexes/output-packs.md>)
- [domain-pilots.md](<./wiki/indexes/domain-pilots.md>)
- [agent-workbench.md](<./wiki/indexes/agent-workbench.md>)

## 协议

当前 starter protocol：
- `general`
- `investing`
- `research`
- `product`
- `ops`

查看和切换：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set investing
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report --protocol research
```

当前协议已经会影响：
- `decision / judgment` 的 review window
- `file-back` 模板
- recurring promotion 语义
- `review / nightly / repair` 的优先级焦点
- `ask` 的排序偏好
- `report / slides / figure` 的输出组织
- execution proposal 的领域化提示

## 自动化

- `watch`
- `auto-once`
- `nightly`
- `run-nightly`
- `systemd --user` watcher + nightly timer

## LLM 后端

支持：
- `codex-cli`
- `claude-cli`
- `openai-api`

检查当前后端：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

## 使用边界

- `raw/` 是事实输入层，派生输出不能覆盖它
- 高价值综合进入 `wiki/derived / decisions / judgments`
- safe execution 只开放低风险动作
- 当前运行模型是 `single writer, many readers`
- 这套系统最适合长期、高密度的研究/投资/产品/运营场景，不适合轻量随手记

## 验证

```bash
bash scripts/verify.sh
```

## 开发说明

`open-harness` 只负责本仓库的工程闭环和质量护栏，不属于 `aiwiki` runtime 本身。
