# aiwiki

`aiwiki` 是一套 local-first 的知识复利操作系统：它把网页、PDF、图片、repo 和本地笔记等原料持续编译成可追溯的 `wiki`、`machine memory`、`decision/judgment` 与可回流输出，并通过 `review`、`lint`、`nightly` 持续维护知识质量；它不是静态笔记库，也不是一次性 RAG 问答器，而是一套让知识能够持续沉淀、审阅和修复的运行时。

架构基线见 [Alchemy Furnace.md](<./wiki/indexes/Alchemy Furnace.md>)。
日常在 Obsidian 里使用时，入口是 [HOME.md](./HOME.md)。

## 它是什么

`aiwiki` 的核心不是聊天，而是闭环：

`raw -> compile -> wiki -> ask -> output -> file-back -> review/lint/nightly`

其中：
- `raw/` 放原料和最早证据
- `wiki/` 放编译后的知识层
- `.aiwiki/` 放 machine memory、状态和缓存
- `output/` 放查询产物
- `schema/` 放运行时规则

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

3. 投一份原料：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
```

4. 编译或直接让 watcher 接管：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
```

5. 提问并生成产物：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare A and B" --format report
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
- `machine-memory-repair-plan.md` 会把 accepted / proposed / deferred 动作整理成可执行批次、页级执行提案和下一步命令提示
- `concept-quality.md` 会把弱概念页、占位概念、概念合并候选、冲突信号、证据缺口和重写优先级集中列出来

machine-memory action 现在也有显式 lifecycle：
- `proposed`：新发现、待处理
- `accepted`：已接受，进入修复队列
- `deferred`：确认存在，但延后处理
- `resolved`：已解决
- `rejected`：确认无需处理

关键状态页：
- [review-queue.md](./wiki/indexes/review-queue.md)
- [aging-report.md](./wiki/indexes/aging-report.md)
- [concept-quality.md](./wiki/indexes/concept-quality.md)
- [machine-memory-topology.md](./wiki/indexes/machine-memory-topology.md)
- [machine-memory-actions.md](./wiki/indexes/machine-memory-actions.md)
- [machine-memory-repair-plan.md](./wiki/indexes/machine-memory-repair-plan.md)
- [repair-backlog.md](./wiki/indexes/repair-backlog.md)
- [graph-health.md](./wiki/indexes/graph-health.md)
- [machine-memory.md](./wiki/indexes/machine-memory.md)

## 当前入口

### 人的入口

- Obsidian：默认前端/IDE
- [HOME.md](./HOME.md)：日常工作台
- [Wiki Hub.md](<./wiki/indexes/Wiki Hub.md>)：知识中枢
- [review-center.md](./wiki/indexes/review-center.md)：统一审阅/修复入口；本地审阅面板在 `output/review/review-center.html`
- [graph-view.md](./wiki/indexes/graph-view.md)：统一图谱入口；本地图谱产物在 `output/graph/machine-memory.html`

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
output/    报告、图表、幻灯片、lint 结果
.aiwiki/   machine memory、状态、缓存
schema/    运行时规则
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
