# aiwiki

`aiwiki` 是一套 local-first 的知识复利操作系统：它把网页、PDF、图片、repo 和本地笔记等原料持续编译成可追溯的 `wiki`、`machine memory`、`decision/judgment` 与可回流输出，并通过 `review`、`lint`、`nightly` 持续维护知识质量；它不是静态笔记库，也不是一次性 RAG 问答器，而是一套让知识能够持续沉淀、审阅和修复的运行时。

架构基线见 [Alchemy Furnace.md](<./wiki/indexes/Alchemy Furnace.md>)。
从当前版本继续提升到上限的路线，见 [Furnace Ceiling Roadmap.md](<./wiki/indexes/Furnace Ceiling Roadmap.md>)。
最终极形态草图见 [Furnace Ultimate Architecture.md](<./wiki/indexes/Furnace Ultimate Architecture.md>)。
日常在 Obsidian 里使用时，入口是 [HOME.md](./HOME.md)。
统一产品壳入口见 [furnace-center.md](<./wiki/indexes/furnace-center.md>)；本地 HTML 控制面板在 `output/control/furnace-center.html`。
执行工作区入口见 [execution-center.md](<./wiki/indexes/execution-center.md>)；本地执行面板在 `output/control/execution-center.html`，机器可读 bundle 会落在 `output/control/execution-bundles/`。
safe execution receipt 会落在 `output/control/execution-receipts/`。
执行审计入口见 [execution-audit.md](<./wiki/indexes/execution-audit.md>)；本地审计面板在 `output/control/execution-audit.html`。
多 agent 工作单入口见 [agent-workbench.md](<./wiki/indexes/agent-workbench.md>)；compile 会把角色 pack 写到 `output/agents/`。
认知历史入口见 [cognitive-history.md](<./wiki/indexes/cognitive-history.md>)；这里会汇总 reviewed judgment 的 citation drift、snapshot 缺口和复审轨迹。
输出 pack 入口见 [output-packs.md](<./wiki/indexes/output-packs.md>)；compile 会把 `review packs / decision memos / SOP drafts` 写到 `output/packs/`。
关于“一个统一炉子，多个领域协议”的原则，见 [Furnace Protocols.md](<./wiki/indexes/Furnace Protocols.md>)。
协议运行时入口见 [protocols.md](<./wiki/indexes/protocols.md>)；当前 starter library 提供 `general / investing / research / product / ops` 五套协议。
当前协议不只是 metadata：它已经会改变 `decision / judgment` 的默认 review window、`file-back` 模板、recurring promotion 的标题与分类语义、`review / nightly / repair` 的优先级焦点，以及 `ask / output / execution proposal` 的策略偏置。

## 它是什么

`aiwiki` 的核心不是聊天，而是闭环：

`raw -> compile -> wiki -> ask -> output -> file-back -> review/lint/nightly`

其中：
- `raw/` 放原料和最早证据
- `wiki/` 放编译后的知识层
- `.aiwiki/` 放 machine memory、状态和缓存
- `output/` 放查询产物
- `schema/` 放运行时规则
- `schema/protocols/` 放领域协议覆盖层
- `file-back` 完成后会立即刷新本地索引和 review queue，不需要再手动补一次 `compile`

Obsidian 是前端/IDE，`aiwiki` 才是编译器和自动化 runtime。

## 人用视角

如果只从“人怎么用”来理解，记住这一句就够了：

`raw/` 输入，`output/` 输出，`wiki/` 沉淀。

更具体的工作台说明在 [HOME.md](./HOME.md)。

## 快速开始

1. 进入仓库：

```bash
cd /home/tim/ai-wiki
```

2. 检查 LLM 后端：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

3. 查看或切换 active protocol：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set investing
```

4. 投一份原料：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
```

5. 编译或直接让 watcher 接管：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
```

6. 提问并生成产物：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare A and B" --format report
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report --protocol investing
```

## 日常工作流

### 1. 投料

把材料送进系统：
- 直接丢文件到 `raw/inbox/`
- 或用 `drop-url`、`drop-pdf`、`drop-image`、`drop-repo`

### 2. 编译

把材料整理成知识层：
- `compile` 维护 `wiki/sources/`、`wiki/concepts/`、`wiki/indexes/`
- `run-compile` 用 LLM 补来源摘要、占位概念摘要，并继续重写高优先级弱概念页

### 2.5 协议

统一炉子里可以切不同协议：
- `protocol-status`：看当前 active protocol
- `protocol-set <slug>`：切换后续 ask / file-back / nightly 默认使用的协议
- `ask --protocol <slug>`：只对单次查询覆盖协议，不改全局 active protocol

当前已经生效的协议化行为：
- `decision / judgment` 的默认 `revisit_after / escalate_after` 会按协议变化
- `file-back` 生成的 `decision / judgment` 页面结构会按协议变化
- recurring promotion 的标题前缀和分类提示会按协议变化
- `review-queue`、`review-center`、`repair-backlog` 和 machine-memory action queue 会按 active protocol 调整排序与焦点
- `ask` 在 source / concept 排序时会按 active protocol 增加领域相关性权重
- `report / slides / figure` 输出模板会带协议化输出偏置，约束最终回答组织方式
- machine-memory repair execution proposal 会按 active protocol 增加领域化修复提示

### 3. 查询

把知识层转成可消费产物：
- `ask` / `run-ask`
- 输出会落到 `output/reports/`、`output/slides/`、`output/figures/`

### 4. 回流

把高价值结果沉回系统：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . file-back output/reports/xxx.md
```

高阶沉淀可进入：
- `wiki/derived/`
- `wiki/decisions/`
- `wiki/judgments/`

### 5. 审阅与巡检

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/example.md --status approved --note "Approved after source review."
PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-latency --status accepted --note "Queue for concept split."
PYTHONPATH=src python3 -m aiwiki.cli --root . lint
PYTHONPATH=src python3 -m aiwiki.cli --root . nightly
```

`nightly` / `run-nightly` 现在还会扫描重复出现的 report / figure 输出，并把足够明确的决策型、判断型问题自动晋升到 `wiki/decisions/` 或 `wiki/judgments/`；这些页面仍然会进入审阅队列，不会被当成已批准结论。

nightly 也会继续跟踪 `decision / judgment` 的 aging：
- pending 页面默认带 `revisit_after` / `escalate_after`
- `review-queue.md` 会标出“已到期待复审”和“需要升级处理”
- `aging-report.md` 会集中列出这些页面
- `repair-backlog.md` 会把它们抬进优先队列
- `machine-memory-actions.md` 会把图谱修复动作沉成稳定队列，并展示状态分布、已到期、已升级、最近清除
- `machine-memory-repair-plan.md` 会把 accepted / proposed / deferred 动作整理成可执行批次、页级执行提案、page-level patch plan 和下一步命令提示
- `execution-center.md` 会把 safe apply、execution proposal 和 proposal 页面统一收敛成执行工作区
- `execution-audit.md` 会把 apply / revert 历史、policy bands、protocol breakdown 和 action audit 收拢成统一审计入口
- execution audit 现在还会显示 `action state / receipt / manual-link state` 的 consistency signals
- `concept-quality.md` 会把弱概念页、占位概念、概念合并候选、冲突信号、证据缺口和重写优先级集中列出来
- `rewrite-proposals.md` 会把高优先级弱概念页的 rewrite proposal、状态和 apply 入口集中列出来
- `judgment-assets.md` 会盘点 `decision / judgment` 的判断资产完整度、反证、失效条件、下一信号和复审历史缺口
- `cognitive-history.md` 会把 reviewed `decision / judgment` 的 citation drift、snapshot gap 和长历史页面集中收拢出来
- `agent-workbench.md` 会把 `ingest / concept / judgment / review / repair-planner / execution / nightly` 角色 pack 收到一个地方，agent 具体工作单会落在 `output/agents/`
- `output-packs.md` 会把 `review packs / decision memos / SOP drafts` 收到统一入口，具体 pack 会落在 `output/packs/`

machine-memory action 现在也有显式 lifecycle：
- `proposed`：新发现、待处理
- `accepted`：已接受，进入修复队列
- `deferred`：确认存在，但延后处理
- `resolved`：已解决
- `rejected`：确认无需处理

concept rewrite 现在也有显式 gate：
- `run-compile` 会把高优先级弱概念页先生成 `rewrite proposal`
- `review-rewrite` 用来接受 / 暂缓 / 拒绝提案
- `apply-rewrite` 只会对已接受、且 source signature 仍匹配的提案执行

safe execution layer 现在也已经接上：
- `review-action` 负责把 repair action 推进到 `accepted / deferred / resolved / rejected`
- `apply-action` 只会处理 allowlist 内的低风险动作
- `apply-action --dry-run` 会先返回 execution bundle 和 safe-apply preview，不写入状态文件
- 真正 `apply-action` 时会消费并校验 execution bundle；bundle 缺失或陈旧时会拒绝执行
- `revert-action` 会基于最近一次 apply receipt 回滚 low-risk safe apply，并把动作放回待处理
- 成功 `apply-action` 后会写 execution receipt，保留最近一次执行回执
- action queue 现在会暴露显式 `execution_band` / capability 标签，区分 `review-first / manual-repair / bundle-safe-apply / deferred / closed / history-only`
- 当前低风险动作会通过 `.aiwiki/state/manual-links.json` 写入可审、可重编译的 manual link state，而不是静默覆盖事实层

关键状态页：
- [review-queue.md](./wiki/indexes/review-queue.md)
- [aging-report.md](./wiki/indexes/aging-report.md)
- [concept-quality.md](./wiki/indexes/concept-quality.md)
- [rewrite-proposals.md](./wiki/indexes/rewrite-proposals.md)
- [machine-memory-topology.md](./wiki/indexes/machine-memory-topology.md)
- [machine-memory-actions.md](./wiki/indexes/machine-memory-actions.md)
- [machine-memory-repair-plan.md](./wiki/indexes/machine-memory-repair-plan.md)
- [repair-backlog.md](./wiki/indexes/repair-backlog.md)
- [graph-health.md](./wiki/indexes/graph-health.md)
- [machine-memory.md](./wiki/indexes/machine-memory.md)
- [cognitive-history.md](./wiki/indexes/cognitive-history.md)
- [agent-workbench.md](./wiki/indexes/agent-workbench.md)
- [output-packs.md](./wiki/indexes/output-packs.md)

## 当前入口

### 人的入口

- Obsidian：默认前端/IDE
- [HOME.md](./HOME.md)：日常工作台
- [Wiki Hub.md](<./wiki/indexes/Wiki Hub.md>)：知识中枢
- [protocols.md](./wiki/indexes/protocols.md)：协议入口和 active protocol 状态
- [furnace-center.md](<./wiki/indexes/furnace-center.md>)：统一工作台入口；本地控制面板在 `output/control/furnace-center.html`
- [execution-center.md](./wiki/indexes/execution-center.md)：执行工作区入口；本地执行面板在 `output/control/execution-center.html`
- [execution-audit.md](./wiki/indexes/execution-audit.md)：执行审计入口；本地审计面板在 `output/control/execution-audit.html`
- [review-center.md](./wiki/indexes/review-center.md)：统一审阅/修复入口；本地审阅面板在 `output/review/review-center.html`
- [output-packs.md](./wiki/indexes/output-packs.md)：输出 pack 入口；deterministic packs 会落在 `output/packs/`
- [judgment-assets.md](./wiki/indexes/judgment-assets.md)：判断资产盘点入口
- [graph-view.md](./wiki/indexes/graph-view.md)：统一图谱入口；本地图谱产物在 `output/graph/machine-memory.html`，现在带搜索、分量过滤、节点详情和 safe-apply 摘要

### 原料入口

- `drop-url`
- `drop-pdf`
- `drop-image`
- `drop-repo`
- 直接写入 `raw/inbox/`

### 自动化入口

- `watch`
- `auto-once`
- `nightly`
- `run-nightly`
- `systemd --user` watcher + nightly timer

### LLM 入口

支持 3 类 backend：
- `codex-cli`
- `claude-cli`
- `openai-api`

检查当前解析结果：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

常用变量：

```bash
export AIWIKI_LLM_BACKEND="codex-cli"        # auto | codex-cli | claude-cli | openai-api
export AIWIKI_LLM_MODEL="gpt-4.1-mini"       # openai-api 必填；CLI backend 可选
export AIWIKI_LLM_TIMEOUT="120"
export AIWIKI_LLM_MAX_CONTEXT_CHARS="24000"
```

## 目录分工

```text
raw/       原料、附件、capture notes
wiki/      编译后的知识层
output/    报告、图表、幻灯片、pack、lint 结果
.aiwiki/   machine memory、状态、缓存
schema/    运行时规则
schema/protocols/ 领域协议规则
prompts/   LLM 提示词模板
```

如果你想看更细的五层模型，直接读 [Alchemy Furnace.md](<./wiki/indexes/Alchemy Furnace.md>)。

## 边界

这些东西不建议改：
- 目录名
- CLI 命令名
- frontmatter key
- 稳定 path / id

这些东西可以持续演进：
- `HOME.md`、`README.md`、`schema/*.md`
- compile/nightly 生成的用户可见看板
- Obsidian 导航方式

这套系统的基本原则是：
- 原始证据留在 `raw/`
- 综合知识留在 `wiki/`
- 机读加速层留在 `.aiwiki/`
- 产物先落 `output/`，再选择性回流

## 自动化模式

如果你想接近“只投原料”的使用方式：

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . watch --interval 5
PYTHONPATH=src python3 -m aiwiki.cli --root . nightly
```

仓库里也带了 user service 安装脚本：

```bash
bash scripts/install_user_service.sh
```

## 验证

```bash
bash scripts/verify.sh
```

## 开发说明

`open-harness` / `.codex/` 只服务这个仓库的开发治理，不属于 `aiwiki` runtime 本体。
runtime 架构以 [Alchemy Furnace.md](<./wiki/indexes/Alchemy Furnace.md>) 为准。
