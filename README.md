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

当前 `aiwiki` runtime 已完成一轮更彻底的边界重构。当前 owner map 按代码现实分为 **core hubs / owner packages / compatibility facades / residual hotspots**：

- `src/aiwiki/app.py`：**静态兼容 shim**，继续保留 `aiwiki.app` import surface；不要在这里新增逻辑。
- `src/aiwiki/app_utils.py`：runtime write lock、hash、frontmatter、markdown / JSON helpers、`safe_fetch` 等底层 primitives。
- `src/aiwiki/app_state.py`：**legacy central hub**，path / state / json-document primitives 的单点入口；改动半径大，需额外谨慎。
- `src/aiwiki/app_protocol.py`：**legacy central hub**，layout、schema scaffolding、protocol runtime、review windows 和默认 runtime 规则。
- `src/aiwiki/cli/`：CLI parser / dispatch / product-first command surface；普通入口固定为 `drop` / `today` / `metrics` / `advanced`，legacy top-level 命令只保留兼容。
- `src/aiwiki/drop.py`：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo` / `drop-note` 的 raw materialization owner。
- `src/aiwiki/compile/`：compile pipeline phase owner（content/runtime/output/persist）；`app_compile.py` 仍是 legacy orchestration / compat hotspot，新逻辑优先下沉到 `compile/*` 或明确 owner module。
- `src/aiwiki/content/`：source / concept / derived / memory output 的主要 owner；`app_content.py` 是 compatibility facade，保留旧 import / patch seam，不新增业务逻辑。
- `src/aiwiki/app_lifecycle.py`：judgment / decision lifecycle、aging、review queue、knowledge lifecycle governance 的 residual owner。
- `src/aiwiki/render/`：index / dashboard / output pack / domain pilot / judgment asset render owner；`app_render.py` 是 compatibility facade。
- `src/aiwiki/memory/`：machine memory graph、execution surfaces、trace/recall/batch 相关 owner；`app_memory.py` 仍是 legacy residual hotspot，`app_memory_query.py` / `app_memory_surfaces.py` 保留 query / surface seam。
- `src/aiwiki/execution/`：execution bundles、receipts、apply/revert/audit、alchemy proposal mutation 的事实层 owner；`app_execution.py` 保留 receipt / bundle assembly 的兼容入口。
- `src/aiwiki/runner/`：`run-compile` / `run-ask` / `nightly` / `watch` / alchemy 等 high-level workflow owner；`runner/alchemy.py` 是 deferred residual hotspot。
- `src/aiwiki/planner/` 与 `src/aiwiki/signals/`：planner dry-run / log / safe primitive policy，以及 review / repair / aging / escalation signal source。
- 金丹主链路已落地：`alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 覆盖 candidate plane、settled plane、DAG/provenance gate、promote/revert/demote receipt、Stage-3 compounding acceptance 与 maturity gate 的 `elixir_quality_proof`；剩余 planned 只指显式 LLM/human contract 下的 semantic distillation。
- `src/aiwiki/app_shell/`：Product Shell summary、controls、status、HTML/surface assembly；Obsidian 插件源码在 `.obsidian/plugins/furnace-product-shell/src/`，它是用户 surface，不拥有 runtime SoT。
- `src/aiwiki/app_routing.py`：material routing、archive candidate、active corpus and temperature 逻辑。
- `src/aiwiki/app_queries.py`：ranking / report / slides / decision-memo / sop query helpers。
- `src/aiwiki/app_linting/`：lint phases、repair backlog、nightly health write helpers。
- `src/aiwiki/app_vault.py`：new-vault scaffold 与 Obsidian bootstrap owner。
- `src/aiwiki/app_types.py`：稳定 TypedDict contracts（如 `ManifestEntry` / `CompileState` / `ShellSummary`）。

这次重构没有改变 CLI 或 `aiwiki.app` 的外部使用方式，但已经把 runtime 从“动态 facade + 隐式跨模块注入”推进成“静态 shim + owner packages + phase orchestration”的结构。后续新增逻辑优先进入明确 owner package；`app_state.py`、`app_protocol.py`、`app_compile.py`、`app_memory.py`、`runner/alchemy.py` 与 Product Shell `plugin.js` 继续按 seam map 小步削薄，不做 broad rewrite。

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

当前推荐把它理解成**两个日常入口、同一 runtime**：

- Obsidian Product Shell：极简工作台，首屏暴露交互（Ask 统一走 run-ask/LLM）、原料投入（投网址 / 投文件 / 投图片 / 记笔记）、最新产出和今日简报；更多工具折叠在面板底部，命令面板默认只注册核心投料/打开入口；界面默认中文，可切到 English
- `scripts/aiwiki-launcher.sh` / `aiwiki CLI`：脚本化入口，默认心智收敛为 `aiwiki drop ...` 投料与 `aiwiki today` 看产出；完整治理、执行、审计和调试能力保留在 `aiwiki advanced ...`
- 普通用户视图默认把文件树收敛到报告入口：`raw/wiki/schema` 与 `output/` 的控制面、审阅、图谱导出等 runtime/operator 层仍存在，但不作为日常导航心智
- 两边共享同一个 `.aiwiki/state` 与 `raw/wiki/output`，所以写命令遵守 `single writer, many readers`

### CLI command taxonomy

`aiwiki` 的命令面按产品心智分三层；AOS-002 只调整展示和文档，不删除旧命令、不新增 alias。2026-05-24 之后新增脚本或用户文档不得再推荐 legacy top-level operator 命令作为日常入口；需要 operator 能力时优先写成 `aiwiki advanced ...`，旧顶层只作为 compat seam 保留：

| Layer | Commands | Purpose |
| --- | --- | --- |
| `primary` | `drop`, `today` | 日常投料与读取产出；`drop` 下含 `url / pdf / image / repo / note`。 |
| `advanced` | `metrics`, `advanced ...` | 高级但仍可解释的健康度、治理、执行、审计、协议、LLM 和调试入口。 |
| `operator/internal` | legacy top-level commands such as `compile`, `run-nightly`, `planner-log-list`, `l3-proposal-generate` | 为脚本、测试、dogfood 和旧自动化保留；默认 help 不再把它们与 `drop/today` 同权展示，完整列表见 `aiwiki advanced --help` 或旧命令自身 `--help`。 |

### 当前 P1-P5 稳定化清单（2026-05-24）

本轮稳定化不扩大 AgentOS 半径，只把已经暴露的高风险边界固化为可验证契约：

| Priority | 当前处理 | 边界 |
| --- | --- | --- |
| P1 Hub slimming | 继续用 seam map / owner map 约束大 hub；`runner/alchemy.py` 与 Product Shell `plugin.js` 保持 deferred residual hotspots。 | 不做 broad rewrite；每轮只削一个有测试的 owner seam。 |
| P2 `run-ask` receipt matrix | 所有 `run-ask` success execution receipts 统一带 `receipt_matrix_version`、`run_ask_path`、`artifact_status`。 | LLM failure / degraded 仍不伪造 success execution receipt。 |
| P3 CLI product-first | 普通入口只推荐 `drop` / `today` / `metrics` / `advanced`；legacy top-level 是 compat。 | 不删除旧命令，避免破坏脚本、tests 和 dogfood 自动化。 |
| P4 Planner phase proof | 新 planner-log record 写入 decision-derived `phase`；旧无 `phase` 的 v1 records 仍可 replay。 | `phase` 只是可复算调度标签，不直接触发 side effect。 |
| P5 Long-run proof | 当前 release proof 是 3-day live window；14/30-day natural run 仍是后续观测目标。 | 不伪造尚未自然发生的长期窗口。 |

## 最小工作流

1. 投料

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . drop note --title "Morning note" --text "Capture the latest signal."
PYTHONPATH=src python3 -m aiwiki.cli --root . drop url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop repo https://github.com/user/repo.git
```

Obsidian Product Shell 已内置投网址（Drop URL）、投文件（Drop File）、投图片（Drop Image）和记笔记（Capture Note）四种投料入口；文本、Markdown、URL 抓取和 repo snapshot 进入 `raw/inbox/`，PDF/image 原件进入 `raw/assets/`，不要把二进制原件放进 `raw/inbox/` 或转成 wrapper markdown。`drop repo` 仍以 launcher CLI 为主。

2. 编译

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
```

3. 提问并出结果

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare company A and company B on thesis, catalyst, risk, and invalidation" --format report
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
- AgentOS 9.0 评分与 release gate：[AGOS-9-Scorecard.md](<./docs/AGOS-9-Scorecard.md>)（执行计划：[AGOS-9-Execution-Plan.md](<./docs/AGOS-9-Execution-Plan.md>)）
- 炼丹炉 Agent 架构（终局 SoT）：[Furnace Agent Architecture.md](<./docs/Furnace Agent Architecture.md>)
- 炼丹炉进化机制（实现契约 SoT）：[Furnace Evolution Mechanics.md](<./docs/Furnace Evolution Mechanics.md>)
- 运行机制与 nightly fallback：[Furnace Runtime Operations.md](<./docs/Furnace Runtime Operations.md>)
- 金丹机制 thesis：[Furnace Elixir.md](<./docs/Furnace Elixir.md>)
- Product Shell 插件设计史料：[Furnace Product Shell Plugin.md](<./docs/archive/Furnace Product Shell Plugin.md>)
- 归档文档索引：[docs/archive/](./docs/archive/)

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

默认本机服务只安装两条产品主线：`aiwiki-watch.service` 常驻等待投料，`aiwiki-nightly.timer` 每晚炼化。`dogfood maturity` timer 是成熟度验证 harness，不是默认产品服务；需要验证时显式 `AIWIKI_INSTALL_DOGFOOD_MATURITY=1 scripts/install_user_service.sh`，验证结束后用 `scripts/uninstall_user_service.sh --dogfood-maturity-only` 移除 unit，保留 vault 数据和 receipt。

常驻 `watch` 的默认职责是稳定入炉：发现 `raw/inbox` 变化后跑 deterministic compile / lint，保留 provenance、source page、concept graph 和 review queue 的最低可用状态。它默认不 inline 阻塞跑 LLM；如果确实要让 watcher 同步执行 LLM compile，可以显式设置 `AIWIKI_WATCH_DETERMINISTIC_ONLY=0`，但这会增加 single-writer lock 占用，不作为默认推荐。

LLM enrichment 仍然是炼丹炉主路径，但放在受控 worker 入口：`run-compile`、`run-ask`、`run-nightly` 和 nightly timer。Product Shell 对话框属于用户显式触发的 `run-ask` / 本地统计入口，可以跑 LLM 或确定性本地回答；它不是常驻 watcher。这样 watcher 不会长时间占用 single-writer lock，LLM 失败也不会阻断原料进入炉子。

默认 unattended 路径按“**等待投料 → 炼丹 → 产出 → 回馈 → 受控学习**”运行：watcher 负责等待投料和最低可用 compile；nightly 负责每天炼化、巡检、修复、回馈和学习；产物写到 `wiki/`、`output/`、receipt / audit；所有会改写系统行为的学习都必须保留 receipt、可审计、可回滚，不允许覆盖 `raw/` 或隐式切 backend。

图谱分两种视图，不要混用。**证据关系图**（Obsidian 侧边栏 Graph）是用户默认视图：只展示报告、来源、原料与可选判断（`output/reports` → `wiki/sources` → `raw/`），打开 Graph 即可，**不需要手动筛选**；`compile` / 打开 vault 会自动恢复 `.obsidian/graph.json`，概念页属于炉子内部维护，不进该图。**机器记忆图谱**（`output/graph/machine-memory.html`）供维护与深挖：含 `source / concept / judgment / elixir(金丹)` 等完整关系。说明见 [graph-view.md](<./wiki/indexes/graph-view.md>)。

治理债的目标是自动消化，符合炼丹炉"人只看异常"的设计哲学。分层按**影响范围 × 可逆性**定义：

- **维护层**：compile / lint / nightly / 陈旧状态清理 / 派生索引 refresh — 只读或可逆的操作，静默自动落盘。`AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1`。
- **治理层**：concept backlog / revisit / source-concept links / concept splits — 结构性变更，可逆且有 receipt，静默自动采纳。`AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1` + `AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1`。
- **判断层**：counter-evidence / judgment review — LLM 驱动的语义复核，自动分析反证、写出审阅结论。`AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=1`。
- **策略层**：L3 proposal / prompt 变更 / schema 变更 — 只能先生成 proposal plane；写回核心 prompt/policy/schema 前必须 `review proposal <id> --status accepted` 人工确认，再手动 `apply <proposal-id>` hash-gated 写 receipt。`AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1` 只会自动登记 `metadata_only` candidate，不会无人值守改核心 prompt/policy/schema。

runtime policy 缺省采用 `autonomy_profile=strong`：未写 `.aiwiki/state/autonomy-policy.json` 时，nightly 默认开启 `auto_apply_light / auto_adopt_l1 / auto_adopt_l2 / auto_adopt_judgments`，但 `auto_adopt_l3 / auto_apply_heavy_semantic / auto_adopt_core_l3` 默认关闭；新安装的 nightly env 仍可显式覆盖这些开关，watcher 仍 deterministic-only，`AIWIKI_NIGHTLY_FALLBACK_ENABLED` 仍默认关闭。需要跨 backend unattended fallback 或 heavy semantic apply 时必须显式开启并配置 repo 外凭据文件。是否已经达到“人只需事后审计 receipt 和异常”的成熟运行状态，仍以 `scripts/dogfood_maturity_gate.py summarize --days 3` 的 `operational_maturity.human_only_exceptions`、`elixir_quality_status` 和连续 receipt 为准。

## LLM 后端

支持：
- 常用 API provider：`opencode-api`、`nvidia-nim-api`、`openrouter-api`、`anthropic-api`
- 高级入口：`codex-cli`、`copilot-cli`、`claude-cli`、`openai-api`（自定义 OpenAI-compatible）

当前语义：
- 新安装默认 route 是 canonical interactive profile：`opencode-api/deepseek-v4-pro` primary；Shell 与 CLI 共用同一组 `AIWIKI_LLM_*` 环境变量
- `opencode-api` 默认 base URL 是 `https://opencode.ai/zen/go/v1`（DeepSeek V4 Pro 走 OpenCode Go endpoint，见 https://dev.opencode.ai/docs/go/ ），key 走 `AIWIKI_OPENCODE_API_KEY`，也可用通用 `AIWIKI_LLM_API_KEY`
- `nvidia-nim-api` 保留为可显式选择的 unattended route，默认模型 `openai/gpt-oss-120b`
- `openrouter-api` 默认 base URL 是 `https://openrouter.ai/api/v1`，key 走 `AIWIKI_OPENROUTER_API_KEY`
- `anthropic-api` 走 Anthropic Messages API，key 走 `AIWIKI_ANTHROPIC_API_KEY`
- `openai-api` 是高级自定义 OpenAI-compatible 入口，base URL 走 `AIWIKI_LLM_BASE_URL`，key 走 `AIWIKI_LLM_API_KEY`
- 如果 backend 是 `codex-cli` 且没有显式设置 `AIWIKI_LLM_MODEL`，effective model 默认是 `gpt-5.5`（旧 `gpt-5.4` 仍可显式选）
- `codex-cli` 默认会附带 `AIWIKI_CODEX_REASONING_EFFORT=medium`，避免非交互 `run-ask` / `run-compile` / `run-lint` 被 CLI 默认的高推理档位拖慢
- `llm-check`、`shell-summary.json`、Product Shell 会显示 requested/effective backend/model、model fallback 链，以及 usage 可见性/计费口径；backend fallback 链默认为空
- 默认 `llm-check` 只做静态路由检查；显式加 `--probe` 后才会发一个极小真实请求，区分“backend 能解析出来”和“当前账号真能跑”
- CLI 路径当前都无法给出精确 token usage，`usage_visibility` 会显示 `opaque-cli`；API provider 会尽量透传响应里的 usage
- `run-ask` 现在会先用 balanced prompt；如果碰到 timeout，会自动再试一次 lean prompt；失败时写出可审计失败说明和 run notes，不再伪装为 deterministic fallback 成功
- `run-ask` 现在也支持显式 `--lean` 与 `--timeout <seconds>`，用于直接选择稳优先 prompt 或覆盖单次调用 timeout，而不改动全局环境变量
- 默认不做隐式 model fallback；需要同 backend 多模型 fallback 时必须显式传 `--model-fallback model_a,model_b`（可重复）或设置 `AIWIKI_MODEL_FALLBACK=model_a,model_b`，CLI 参数优先于 env
- 默认不做跨 backend fallback；`AIWIKI_BACKEND_FALLBACK` / `AIWIKI_BACKEND_FALLBACK_MODEL` 不再驱动普通 CLI/runtime 的隐藏 backend routing。需要重跑到另一个 backend 时，显式设置 `AIWIKI_LLM_BACKEND` / `AIWIKI_LLM_MODEL` 后重新执行
- `scripts/run_nightly.sh` 仍保留 operator unattended fallback wrapper：primary 由 `AIWIKI_LLM_BACKEND` 指定；当 unattended nightly 失败时，若 `AIWIKI_NIGHTLY_FALLBACK_ENABLED=1` 且 `AIWIKI_NIGHTLY_FALLBACK_ENV` 指向可读的 repo 外 NIM key 文件，会自动用 `nvidia-nim-api/openai/gpt-oss-120b` 重跑一次

常见配置：

```bash
AIWIKI_OPENCODE_API_KEY=opencode-... PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=opencode-api AIWIKI_OPENCODE_API_KEY=opencode-... PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=nvidia-nim-api AIWIKI_NVIDIA_NIM_API_KEY=nvapi-... PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=openrouter-api AIWIKI_OPENROUTER_API_KEY=sk-or-... AIWIKI_LLM_MODEL=provider/model PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=anthropic-api AIWIKI_ANTHROPIC_API_KEY=sk-ant-... PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
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

- `opencode-api`：走 `AIWIKI_OPENCODE_API_KEY` 或 `AIWIKI_LLM_API_KEY`；模型默认 `deepseek-v4-pro`。如果账号不可用或模型不可用，`llm-check --probe` 必须显式失败并显示 provider/model/base URL，不会静默伪装成 NIM fallback 成功
- `codex-cli`：走 `codex login` 的本地会话；当前环境可用 `codex login status` 查看状态
- `codex-cli`：可以通过 `AIWIKI_CODEX_REASONING_EFFORT=medium|high|xhigh` 调节非交互推理档位；当前默认是 `medium`
- `nvidia-nim-api`：走 `AIWIKI_NVIDIA_NIM_API_KEY` 或 `NVIDIA_NIM_API_KEY`；base URL 默认 `https://integrate.api.nvidia.com/v1`
- `nvidia-nim-api`：当前按 OpenAI-compatible `/v1/chat/completions` 接入；模型留空默认使用 `openai/gpt-oss-120b`
- `nvidia-nim-api`：如需多模型重试，显式设置 `AIWIKI_LLM_MODEL` 并追加 `--model-fallback openai/gpt-oss-120b`（CLI 参数优先于 env）。注意 NIM 上多数 model 已 EOL 或装饰输出与 frontmatter 不兼容（如 `moonshotai/kimi-k2.5` 4-30 EOL、`meta/llama-3.3-70b-instruct` 输出装饰），先用 `llm-check --probe-all --format human` 确认目标 model `compatible` 再启用
- `openrouter-api`：走 OpenAI-compatible `/chat/completions`，key 走 `AIWIKI_OPENROUTER_API_KEY`；通常需要显式 `AIWIKI_LLM_MODEL=provider/model`
- `anthropic-api`：走 Anthropic Messages API；模型留空默认 `claude-sonnet-4-20250514`
- **本地凭据存放规范**：API key **不得**进入 README、测试 fixture、`.envrc.dogfood` 或任何 git-tracked 文件。Product Shell 里填写的 key 只落到本机未跟踪的插件 `data.json`；CLI/dogfood 推荐落到 `~/.aiwiki-secrets/<provider>.env`（mode 600 / 父目录 700）。nightly fallback 只保存 `AIWIKI_NIGHTLY_FALLBACK_ENV` 路径，运行时由 wrapper source，不把 key 写进 systemd unit 或 git-tracked 文件
- `copilot-cli`：官方推荐 `copilot login` 的浏览器设备码 OAuth；也支持 `COPILOT_GITHUB_TOKEN -> GH_TOKEN -> GITHUB_TOKEN -> stored OAuth token -> gh auth token` 的优先链
- `copilot-cli` 的 GitHub OAuth 路径"可行"不等于"当前账号可用"；seat / org policy / quota 不足时，probe 仍会失败

## 使用边界

- `raw/` 是事实输入层，派生输出不能覆盖它
- 高价值综合进入 `wiki/derived / decisions / judgments`
- safe execution 只开放低风险动作
- 当前运行模型是 `single writer, many readers`
- 这套系统最适合长期、高密度的研究/投资/产品/运营场景，不适合轻量随手记

## 验证

```bash
scripts/agentstack verify --target auto
```

## 开发说明

本仓库使用 AgentStack 作为 agent/tooling 协议和验证入口；它不属于 `aiwiki` runtime，也不改变 CLI/runtime 行为。当前安装平台是 `codex,claude,opencode`。

检查 AgentStack 安装健康：

```bash
scripts/agentstack doctor --platforms codex,claude,opencode
```

运行当前变更的 targeted verify：

```bash
scripts/agentstack verify --target auto
```

发布级或 broad-risk 变更再运行全量验证：

```bash
scripts/agentstack verify --full
```

底层项目验证仍可直接调用：

```bash
bash scripts/verify.sh [scripts|smoke|python-static|unit|acceptance|cli-smoke|product-shell-static|all]
```

### Developer Guide

本地开发最常用的入口只有三条：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status
```

新增能力时，优先沿下面这张模块边界图落位，而不是继续往巨石文件里堆：

```text
cli/                       命令入口；只做参数解析与 dispatch
├─ drop.py / input_router.py   外部投喂入口（drop url / drop pdf / drop image / drop repo / drop note）
├─ runner/                 lifecycle / alchemy / nightly 等 high-level 编排
└─ planner/                deterministic + LLM-assisted plan 生成

execution/                 事实层 mutation（promote / revert / demote / archive / proposals…）
                           硬边界：所有 mutation 必须 receipt + hash + revert（M9-P0.1）
runner/alchemy.py          lane / primitive 编排，含 scope-honesty receipt（M9-P0.2）

cli/                       product-first command surface + legacy compat dispatch
drop.py                    raw materialization owner（url / pdf / image / repo / note）

compile/                   compile pipeline phases（content / runtime / output / persist）
app_compile.py             legacy orchestration / compat hotspot；新逻辑优先下沉
app_compile_ops.py         protocol switch / recurring promotion / agent-pack helpers
app_queries.py             ranking / report / slides / decision-memo / sop query helpers
app_linting/               lint phases / repair backlog / nightly health helpers

content/                   source / concept / derived / memory output 物化 owner
app_content.py             compatibility facade；不要新增业务逻辑
app_lifecycle.py           judgments / decisions / aging / review queue governance

render/                    views / packs / pilots / judgment asset render owner
app_render.py              compatibility facade
app_surfaces.py            dashboard / HTML / shell surface render exports

memory/                    machine memory（graph / trace / recall / execution surfaces）
app_memory.py              legacy residual hotspot
app_memory_query.py        private query helpers
app_memory_surfaces.py     public/tested query / topology / execution surface facade

execution/                 execution bundles / receipts / apply / revert / audit owner
app_execution.py           receipt / bundle assembly compat entry
runner/                    run-compile / run-ask / nightly / watch / alchemy workflows
runner/alchemy.py          deferred residual hotspot
planner/                   dry-run / log / safe primitive policy
signals/                   review / repair / aging / escalation 信号源

app_state.py               持久化状态 I/O 单一入口
                           best-effort + strict 双语义；strict raise CorruptStateError（M9-P0.4）
app_protocol.py            协议 layout / schema / protocol runtime / review windows
app_utils.py               runtime lock / markdown / JSON / safe_fetch primitives
app_shell/                 product shell runtime surfaces（summary / controls / status / HTML）
app_vault.py               new-vault scaffold / Obsidian bootstrap
```

约定：

- `raw/` 是唯一事实输入层；不要把结论直接写回 source 层。
- `wiki/sources/` 与 `wiki/derived|decisions|judgments/` 必须分层，派生产物保留 provenance。
- 新 CLI 命令优先放 `cli/` + owner module，不要在 shim 或 shell surface 上偷接逻辑。
- 新协议能力先落 `schema/protocols/*`，再让 runtime 消费；不要反过来让代码先漂移。
- 事实层 mutation 必须走 `execution/`，receipt 写失败必须 rollback（不允许半写）。
- 持久化状态读取必须显式选 best-effort 还是 strict（见 `docs/Furnace Agent Architecture.md` §11.1）。
