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

## 当前 runtime 实现（repo 视角）

当前 `aiwiki` runtime 已完成一轮更彻底的边界重构，仓库里的实现骨架现在是：

- `src/aiwiki/app.py`：**静态兼容 shim**，继续保留 `aiwiki.app` import surface，但不再承担动态 sync facade
- `src/aiwiki/app_utils.py`：runtime lock、hash、frontmatter、markdown / JSON helpers
- `src/aiwiki/app_state.py`：path / state / json-document primitives
- `src/aiwiki/app_protocol.py`：protocol runtime、schema scaffolding、review windows
- `src/aiwiki/app_content.py`：source / concept compile core，以及对 lifecycle / render owner modules 的兼容导出
- `src/aiwiki/app_lifecycle.py`：judgment / decision lifecycle、aging、review queue、knowledge lifecycle governance
- `src/aiwiki/app_render.py`：index / dashboard / output pack / domain pilot / judgment asset render
- `src/aiwiki/app_memory.py`：machine memory graph core，以及对 routing / query surface owner modules 的兼容导出
- `src/aiwiki/app_routing.py`：material routing、archive candidate、active corpus and temperature 逻辑
- `src/aiwiki/app_memory_surfaces.py`：machine memory query / topology / execution surface render
- `src/aiwiki/app_shell.py`：shell summary、review/execution controls、shell-facing contract assembly
- `src/aiwiki/app_surfaces.py`：dashboard / HTML / shell surface render exports
- `src/aiwiki/app_compile.py`：compile / ask / file-back / review / nightly orchestration，以及对 compile helper modules 的兼容导出
- `src/aiwiki/app_compile_ops.py`：protocol switch / recurring promotion / agent-pack helpers
- `src/aiwiki/app_queries.py`：ranking / report / slides / decision-memo / sop query helpers
- `src/aiwiki/app_linting.py`：lint / repair backlog / nightly write helpers
- `src/aiwiki/app_types.py`：稳定 TypedDict contracts（如 `ManifestEntry` / `CompileState` / `ShellSummary`）

这次重构没有改变 CLI 或 `aiwiki.app` 的外部使用方式，但已经把 runtime 从“动态 facade + 隐式跨模块注入”推进成“静态 shim + 明确 owner 模块 + phase orchestration”的结构。更上层的系统分层和长期目标，仍以基线 / 终局架构文档为准。

## 更适合谁

- 投资研究者：想把财报、电话会、访谈、赛道资料、判断变化和复审记录放进同一个炉子。
- 技术研发者：想把论文、repo、实验、benchmark、设计权衡和技术判断沉淀成长期资产。

如果你更关心通用产品入口，而不是投资/研发场景，可以回到 `main` 分支。

## 创建新的 vault

如果你想基于当前 runtime 快速起一个新的 Obsidian 炼丹炉工作区：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . new-vault ../demo-furnace-vault
cd ../demo-furnace-vault
./scripts/aiwiki-launcher.sh shell-status
./scripts/aiwiki-launcher.sh compile
```

它会一次性生成：

- `raw / wiki / schema / output / .aiwiki`
- `HOME.md` + `README.md`
- `.obsidian/` 基础工作台配置
- `Furnace Product Shell` 插件文件
- `scripts/aiwiki-launcher.sh`

这个新 vault **不需要复制** `src/aiwiki/`；launcher 会把 vault 当成 `--root`，再回到当前 runtime root 执行 `aiwiki CLI`。

当前推荐把它理解成**两个入口、同一 runtime**：

- Obsidian Product Shell：极简工作台，首屏暴露交互（Ask）、原料投入（投网址 / 投文件 / 投图片 / 记笔记）、最新产出和今日简报；高级操作（Review、Execution、Protocol）折叠在面板底部，命令面板默认只注册 8 个核心命令；界面默认中文，可切到 English
- `scripts/aiwiki-launcher.sh` / `aiwiki CLI`：完整命令入口，负责全量 `drop-*`、批量操作和脚本化调用
- 两边共享同一个 `.aiwiki/state` 与 `raw/wiki/output`，所以写命令遵守 `single writer, many readers`

## 最小工作流

1. 投料

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-note --title "Morning note" --text "Capture the latest signal."
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
```

Obsidian Product Shell 已内置投网址（Drop URL）、投文件（Drop File）、投图片（Drop Image）和记笔记（Capture Note）四种投料入口；也可以把材料直接放进 `raw/inbox/`。`drop-repo` 仍以 launcher CLI 为主。

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
- 当前能力快照：[Furnace Capability Map.md](<./wiki/indexes/Furnace Capability Map.md>)
- 增量编译计划：[Furnace Incremental Compile Plan.md](<./wiki/indexes/Furnace Incremental Compile Plan.md>)
- Product Shell 插件设计：[Furnace Product Shell Plugin.md](<./wiki/indexes/Furnace Product Shell Plugin.md>)
- 大规模原料处理设计：[Furnace Material Scaling.md](<./wiki/indexes/Furnace Material Scaling.md>)
- 统一炉子 + 多协议：[Furnace Protocols.md](<./wiki/indexes/Furnace Protocols.md>)

日常使用时，Obsidian 与 CLI 共享同一个 runtime；不要同时在两边各跑一个 `compile / nightly / apply / revert`。

### 控制台

主入口（极简面板）：
- 炉心面板：[furnace-center.md](<./wiki/indexes/furnace-center.md>)

高级控制台（折叠在面板底部或通过命令面板打开）：
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
- `nvidia-nim-api`
- `copilot-cli`
- `claude-cli`

当前语义：
- `AIWIKI_LLM_BACKEND` 现在必须显式设置；runtime 不再做 `auto` 解析
- 如果 backend 是 `codex-cli` 且没有显式设置 `AIWIKI_LLM_MODEL`，effective model 默认是 `gpt-5.4`
- 如果 backend 是 `nvidia-nim-api` 且没有显式设置 `AIWIKI_LLM_MODEL`，effective model 默认首选是 `moonshotai/kimi-k2.5`
- `codex-cli` 默认会附带 `AIWIKI_CODEX_REASONING_EFFORT=medium`，避免非交互 `run-ask` / `run-compile` / `run-lint` 被 CLI 默认的高推理档位拖慢
- `llm-check`、`shell-summary.json`、Product Shell 会同时显示 requested/effective backend/model，以及 usage 可见性/计费口径
- 默认 `llm-check` 只做静态路由检查；显式加 `--probe` 后才会发一个极小真实请求，区分“backend 能解析出来”和“当前账号真能跑”
- CLI 路径当前都无法给出精确 token usage，`usage_visibility` 会显示 `opaque-cli`；`nvidia-nim-api` 会直接返回 usage
- `run-ask` 现在会先用 balanced prompt；如果碰到 timeout，会自动再试一次 lean prompt，只有 lean retry 也失败时，外层 Product Shell 才会做 deterministic fallback
- `run-ask` 现在也支持显式 `--lean` 与 `--timeout <seconds>`，用于直接选择稳优先 prompt 或覆盖单次调用 timeout，而不改动全局环境变量
- `nvidia-nim-api` 在模型留空时会按 `moonshotai/kimi-k2.5 -> z-ai/glm-5.1 -> minimaxai/minimax-m2.7` 依次尝试；不仅 API/timeout 类错误会切下一模型，`run-ask / run-compile / run-lint` 的产物校验失败也会切下一模型

常见配置：

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=nvidia-nim-api AIWIKI_NVIDIA_NIM_API_KEY=nvapi-... PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=copilot-cli PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=claude-cli PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

检查当前后端：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check --probe
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check --probe-all --probe-timeout 20
```

认证说明：

- `codex-cli`：走 `codex login` 的本地会话；当前环境可用 `codex login status` 查看状态
- `codex-cli`：可以通过 `AIWIKI_CODEX_REASONING_EFFORT=medium|high|xhigh` 调节非交互推理档位；当前默认是 `medium`
- `nvidia-nim-api`：走 `AIWIKI_NVIDIA_NIM_API_KEY` 或 `NVIDIA_NIM_API_KEY`；base URL 默认 `https://integrate.api.nvidia.com/v1`
- `nvidia-nim-api`：当前按 OpenAI-compatible `/v1/chat/completions` 接入；模型留空会按 `moonshotai/kimi-k2.5 -> z-ai/glm-5.1 -> minimaxai/minimax-m2.7` 依次尝试
- `nvidia-nim-api`：如果你要钉死某个模型，直接显式设置 `AIWIKI_LLM_MODEL=moonshotai/kimi-k2.5` 或 `AIWIKI_LLM_MODEL=minimaxai/minimax-m2.7`
- `copilot-cli`：官方推荐 `copilot login` 的浏览器设备码 OAuth；也支持 `COPILOT_GITHUB_TOKEN -> GH_TOKEN -> GITHUB_TOKEN -> stored OAuth token -> gh auth token` 的优先链
- `copilot-cli` 的 GitHub OAuth 路径“可行”不等于“当前账号可用”；seat / org policy / quota 不足时，probe 仍会失败
- 当前这台机器上的真实结论是：`copilot-cli` 仍可能返回 `402 no quota`；如果你要稳定跑 API 路，优先显式切到 `nvidia-nim-api`

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

### Developer Guide

本地开发最常用的入口只有三条：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status
```

新增能力时，优先沿下面这张模块边界图落位，而不是继续往巨石文件里堆：

```text
cli
├─ drop / runner
├─ app_compile
│  ├─ app_compile_ops
│  ├─ app_queries
│  └─ app_linting
├─ app_content
│  ├─ app_lifecycle
│  └─ app_render
└─ app_memory
   ├─ app_routing
   └─ app_memory_surfaces
```

约定：

- `raw/` 是唯一事实输入层；不要把结论直接写回 source 层。
- `wiki/sources/` 与 `wiki/derived|decisions|judgments/` 必须分层，派生产物保留 provenance。
- 新 CLI 命令优先放 `cli.py` + owner module，不要在 shim 或 shell surface 上偷接逻辑。
- 新协议能力先落 `schema/protocols/*`，再让 runtime 消费；不要反过来让代码先漂移。
