---
title: "炼丹炉开发者指南"
kind: "guide"
status: "active"
updated_at: "2026-07-15"
related_docs:
  - README.md
  - docs/INSTALL.md
  - AGENTS.md
---

# 炼丹炉开发者指南

面向贡献者与 operator。用户安装与日常使用见根 [README.md](../README.md)、[INSTALL.md](./INSTALL.md)、[USER_GUIDE.md](./USER_GUIDE.md)。

## 当前 runtime 实现（repo 视角）

当前 `aiwiki` runtime owner map 按代码现实分为 **core hubs / owner packages / residual hotspots**。纯 re-export facade（`app.py` / `app_content` / `app_render` / `app_surfaces` / `app_memory_surfaces`）已按 `AGENTS.md` 定案删除；请直引 owner 模块。

- `src/aiwiki/app_utils.py`：runtime write lock、hash、frontmatter、markdown / JSON helpers、`safe_fetch` 等底层 primitives。
- `src/aiwiki/app_state.py`：**legacy central hub**，path / state / json-document primitives 的单点入口；改动半径大，需额外谨慎。
- `src/aiwiki/app_protocol.py`：**legacy central hub**，layout、schema scaffolding、protocol runtime、review windows 和默认 runtime 规则。
- `src/aiwiki/cli/`：CLI parser / dispatch / product-first command surface；普通入口固定为 `drop` / `today` / `metrics` / `advanced`，legacy top-level 命令只保留兼容。
- `src/aiwiki/drop.py`：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo` / `drop-note` 的 raw materialization owner；用户入口推荐 `drop markdown`。
- `src/aiwiki/compile/`：compile pipeline phase owner（content/runtime/output/persist）；`app_compile.py` 仍是 legacy orchestration hotspot，新逻辑优先下沉到 `compile/*` 或明确 owner module。
- `src/aiwiki/content/`：source / concept / derived / memory output 的主要 owner。
- `src/aiwiki/app_lifecycle.py`：judgment / decision lifecycle、aging、review queue、knowledge lifecycle governance 的 residual owner。
- `src/aiwiki/render/`：index / dashboard / output pack / domain pilot / judgment asset render owner。
- `src/aiwiki/memory/`：machine memory graph、execution surfaces、trace/recall/batch 相关 owner；legacy `app_memory.py` 已删除（Round 8），query helpers 在 `app_memory_query.py`。
- `src/aiwiki/execution/`：execution bundles、receipts、apply/revert/audit、alchemy proposal mutation 的事实层 owner；`app_execution.py` 保留 receipt / bundle assembly 入口。
- `src/aiwiki/runner/`：`run-compile` / `run-ask` / `nightly` / `watch` / alchemy 等 high-level workflow owner；`runner/alchemy.py` 是 deferred residual hotspot。
- `src/aiwiki/planner/` 与 `src/aiwiki/signals/`：planner dry-run / log / safe primitive policy，以及 review / repair / aging / escalation signal source。
- 金丹主链路已落地：`alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 覆盖 candidate plane、settled plane、DAG/provenance gate、promote/revert/demote receipt、Stage-3 compounding acceptance 与 maturity gate 的 `elixir_quality_proof`；剩余 planned 只指显式 LLM/human contract 下的 semantic distillation。
- `src/aiwiki/app_shell/`：Product Shell summary、controls、status、HTML/surface assembly；Obsidian 插件源码在 `.obsidian/plugins/furnace-product-shell/src/`，它是用户 surface，不拥有 runtime SoT。
- `src/aiwiki/app_routing.py`：material routing、archive candidate、active corpus and temperature 逻辑。
- `src/aiwiki/app_queries.py`：ranking / report / slides / decision-memo / sop query helpers。
- `src/aiwiki/app_linting/`：lint phases、repair backlog、nightly health write helpers。
- `src/aiwiki/app_vault.py`：new-vault scaffold 与 Obsidian bootstrap owner。
- `src/aiwiki/app_types.py`：稳定 TypedDict contracts（如 `ManifestEntry` / `CompileState` / `ShellSummary`）。

后续新增逻辑优先进入明确 owner package；`app_state.py`、`app_protocol.py`、`app_compile.py`、`runner/alchemy.py` 与 Product Shell `plugin.js` 继续按 seam map 小步削薄，不做 broad rewrite。`app_memory.py`（Round 8 已删）+ `app_content.py` / `app_render.py` / `app_surfaces.py` / `app_memory_surfaces.py`（prior rounds）从 "削薄 hotspot" 列表毕业，不再 active 维护。禁止再引入纯 re-export facade。

### CLI command taxonomy

`aiwiki` 顶层只保留 primary surface；operator 命令只注册在 `advanced` 下。旧顶层调用（如 `compile`、`drop-url`、`run-ask`）仍可通过 argv rewrite 兼容，并打印 `[deprecated]`，脚本应尽快改成 primary / `advanced`：

| Layer | Commands | Purpose |
| --- | --- | --- |
| `primary` | `drop`, `today`, `metrics`, `advanced` | 日常投料、今日简报、健康度，以及进入 operator 面。`drop` 下含 `url / pdf / image / repo / markdown`。 |
| `advanced` | `aiwiki advanced ...` | 治理、编译、执行、审计、协议、LLM 和调试；完整列表见 `aiwiki advanced --help`。 |
| `compat` | 旧顶层名（rewrite only） | 不在 argparse 顶层注册；`drop-*` → `drop <kind>`，其余 → `advanced <cmd>`。 |

### 当前 P1-P5 稳定化清单（2026-05-24）

本轮稳定化不扩大 AgentOS 半径，只把已经暴露的高风险边界固化为可验证契约：

| Priority | 当前处理 | 边界 |
| --- | --- | --- |
| P1 Hub slimming | 继续用 seam map / owner map 约束大 hub；`runner/alchemy.py` 与 Product Shell `plugin.js` 保持 deferred residual hotspots。 | 不做 broad rewrite；每轮只削一个有测试的 owner seam。 |
| P2 `run-ask` receipt matrix | 所有 `run-ask` success execution receipts 统一带 `receipt_matrix_version`、`run_ask_path`、`artifact_status`。 | LLM failure / degraded 仍不伪造 success execution receipt。 |
| P3 CLI product-first | 顶层只注册 `drop` / `today` / `metrics` / `advanced`；旧顶层名靠 rewrite compat。 | 不删除 advanced 下的 operator 命令，避免破坏脚本与 dogfood。 |
| P4 Planner phase proof | 新 planner-log record 写入 decision-derived `phase`；旧无 `phase` 的 v1 records 仍可 replay。 | `phase` 只是可复算调度标签，不直接触发 side effect。 |
| P5 Long-run proof | 当前 release proof 是 3-day live window；14/30-day natural run 仍是后续观测目标。 | 不伪造尚未自然发生的长期窗口。 |

## 自动化

- `watch`
- `auto-once`
- `nightly`
- `run-nightly`
- `systemd --user` watcher + nightly timer
- macOS `launchd` watcher + nightly calendar job

默认本机服务只安装两条产品主线：`aiwiki-watch.service` 常驻等待投料，`aiwiki-nightly.timer` 每晚炼化。安装 systemd 服务必须显式提供 vault：`AIWIKI_VAULT=/path/to/vault scripts/install_user_service.sh`，不会把代码仓库当默认 vault。服务安装/更新会把仓库中的 Product Shell release 文件同步到目标 vault，但保留本机插件 `data.json`。

> 2026-07-15 scripts 清理：历史 `dogfood maturity` timer 与 `AIWIKI_INSTALL_DOGFOOD_MATURITY=1` / `--dogfood-maturity-only` 路径已删除。`scripts/install_user_service.sh` 默认只安装 watcher + nightly timer；即使机器上残留旧 unit，install / uninstall 也会主动清理。

macOS 上没有 `systemd --user` 时，使用 launchd 安装同样的两条产品主线；launchd plist 只保存 vault 路径和运行参数，LLM key 仍由 vault launcher 从 Product Shell 本机 `data.json` 或当前环境读取，不写入 plist；安装/更新同样会同步 Product Shell release 文件：

```bash
AIWIKI_VAULT=/path/to/vault scripts/install_launchd_service.sh
scripts/uninstall_launchd_service.sh
```

常驻 `watch` 的默认职责是稳定入炉：发现 `raw/inbox` 变化后跑 deterministic compile / lint，保留 provenance、source page、concept graph 和 review queue 的最低可用状态。它默认不 inline 阻塞跑 LLM；如果确实要让 watcher 同步执行 LLM compile，可以显式设置 `AIWIKI_WATCH_DETERMINISTIC_ONLY=0`，但这会增加 single-writer lock 占用，不作为默认推荐。

LLM enrichment 仍然是炼丹炉主路径，但放在受控 worker 入口：`run-compile`、`run-ask`、`run-nightly` 和 nightly timer。Product Shell 对话框属于用户显式触发的 `run-ask` / 本地统计入口，可以跑 LLM 或确定性本地回答；它不是常驻 watcher。这样 watcher 不会长时间占用 single-writer lock，LLM 失败也不会阻断原料进入炉子。

默认 unattended 路径按“**等待投料 → 炼丹 → 产出 → 回馈 → 受控学习**”运行：watcher 负责等待投料和最低可用 compile；nightly 负责每天炼化、巡检、修复、回馈和学习；产物写到 `wiki/`、`output/`、receipt / audit；所有会改写系统行为的学习都必须保留 receipt、可审计、可回滚，不允许覆盖 `raw/` 或隐式切 backend。

图谱分两种视图，不要混用。**证据关系图**（Obsidian 侧边栏 Graph）是用户默认视图：只展示报告、来源、原料与可选判断（`output/reports` → `wiki/sources` → `raw/`），打开 Graph 即可，**不需要手动筛选**；`compile` / 打开 vault 会自动恢复 `.obsidian/graph.json`，概念页属于炉子内部维护，不进该图。**机器记忆图谱**（`output/graph/machine-memory.html`）供维护与深挖：含 `source / concept / judgment / elixir(金丹)` 等完整关系。说明见 [wiki/indexes/README.md](../wiki/indexes/README.md)（indexes 由 compile 生成）。

治理债的目标是自动消化，符合炼丹炉"人只看异常"的设计哲学。分层按**影响范围 × 可逆性**定义：

- **维护层**：compile / lint / nightly / 陈旧状态清理 / 派生索引 refresh — 只读或可逆的操作，可通过 `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1` 显式开启自动落盘；新安装的 systemd nightly env 默认写 `0`，避免安装即开始写入型自治。
- **债务自消化层**：source summary backlog / weak concepts / rewrite candidates / judgment metadata debt / machine-memory actions — 统一进入 `debt-autopilot`，由 owner-state collector 只把 policy 分类为 `non_core_semantic` 的项目计入 `llm_owned_non_core`，再交给 `run_compile` LLM 内容消化、current rewrite apply、safe action apply、revert 或 compensating receipt；L3 metadata/governance debt 不能伪装成 `llm_owned_non_core`。Product Shell 只能展示 debt-autopilot 的结果，不参与无人值守 apply 判定；单项 LLM timeout 只能记为该 debt 失败，不能阻塞整个队列。
- **治理层**：concept backlog / revisit / source-concept links / concept splits — 结构性变更，可逆且有 receipt；通过 `AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1` + `AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1` 显式开启无人值守采纳。
- **判断层**：counter-evidence / judgment review — LLM 驱动的语义复核，自动分析反证、写出审阅结论；judgment page、标准 execution receipt、execution history、audit stream 必须可互证，写失败回滚。通过 `AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=1` 显式开启。
- **策略层**：L3 proposal / prompt 变更 / schema 变更 — 非核心/metadata-only 学习默认由 agentic nightly 登记和消化；写回核心 prompt/policy/schema 前必须 `review proposal <id> --status accepted` 人工确认，再手动 `apply <proposal-id>` hash-gated 写 receipt。`AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3=0` 是核心自改红线，不允许无人值守改核心 prompt/policy/schema。

runtime policy 缺省采用 `autonomy_profile=agentic`：未写 `.aiwiki/state/autonomy-policy.json` 时，runtime 内部 profile 允许维护、治理、judgment review、metadata-only L3 和 heavy semantic 非核心自动化，但 `auto_adopt_core_l3` 默认关闭。新安装的 systemd nightly env 仍写入 `AIWIKI_AUTONOMY_PROFILE=agentic` 以保持 receipt 记账口径一致，但写入型 auto flags 默认写 `0`，必须由 operator 显式 opt-in；watcher 仍 deterministic-only，不再配置跨 backend unattended fallback。

> 2026-07-15 scripts 清理：本节早先引用的 `scripts/dogfood_maturity_gate.py summarize --days 3` 等 heuristic 已删除。当前以 **manual 仅异常审计** 为成熟度观察口径：人盯 `output/control/execution-receipts/` 与 `output/control/llm-receipts.jsonl` 中的异常事件；不依赖自动 3-day verdict 给出"成熟"宣称。

## LLM 后端

支持：
- API provider：`deepseek-api`、`opencode-api`、`openai-api`、`anthropic-api`

当前语义：
- 新安装默认 route 是 canonical interactive profile：`opencode-api/deepseek-v4-pro` primary；Shell 与 CLI 共用同一组 `AIWIKI_LLM_*` 环境变量
- `deepseek-api` 默认 base URL 是 `https://api.deepseek.com`，key 走 `AIWIKI_DEEPSEEK_API_KEY` 或 `DEEPSEEK_API_KEY`
- `opencode-api` 默认 base URL 是 `https://opencode.ai/zen/go/v1`（DeepSeek V4 Pro 走 OpenCode Go endpoint，见 https://dev.opencode.ai/docs/go/ ），key 走 `AIWIKI_OPENCODE_API_KEY`，也可用通用 `AIWIKI_LLM_API_KEY`
- `anthropic-api` 走 Anthropic Messages API，key 走 `AIWIKI_ANTHROPIC_API_KEY`
- `openai-api` 是 OpenAI / OpenAI-compatible 入口，base URL 走 `AIWIKI_LLM_BASE_URL`，key 走 `AIWIKI_LLM_API_KEY` 或 `OPENAI_API_KEY`
- `llm-check`、`shell-summary.json`、Product Shell 会显示 requested/effective backend/model、model fallback 链，以及 usage 可见性/计费口径；backend fallback 链默认为空
- 默认 `llm-check` 只做静态路由检查；显式加 `--probe` 后才会发一个极小真实请求，区分“backend 能解析出来”和“当前账号真能跑”
- API provider 会尽量透传响应里的 usage
- `run-ask` 现在会先用 balanced prompt；如果碰到 timeout，会自动再试一次 lean prompt；失败时写出可审计失败说明和 run notes，不再伪装为 deterministic fallback 成功
- `run-ask` 现在也支持显式 `--lean` 与 `--timeout <seconds>`，用于直接选择稳优先 prompt 或覆盖单次调用 timeout，而不改动全局环境变量
- 默认不做隐式 model fallback；需要同 backend 多模型 fallback 时必须显式传 `--model-fallback model_a,model_b`（可重复）或设置 `AIWIKI_MODEL_FALLBACK=model_a,model_b`，CLI 参数优先于 env
- 默认不做跨 backend fallback；`AIWIKI_BACKEND_FALLBACK` / `AIWIKI_BACKEND_FALLBACK_MODEL` 不再驱动普通 CLI/runtime 的隐藏 backend routing。需要重跑到另一个 backend 时，显式设置 `AIWIKI_LLM_BACKEND` / `AIWIKI_LLM_MODEL` 后重新执行
- `scripts/run_nightly.sh` 不再切换 fallback backend；已配置 LLM 执行失败后 fail closed，只有未配置 LLM 且未设置 `AIWIKI_NIGHTLY_REQUIRE_LLM=1` 时才跑 deterministic nightly

常见配置：

```bash
AIWIKI_LLM_BACKEND=deepseek-api AIWIKI_DEEPSEEK_API_KEY=sk-... PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
AIWIKI_OPENCODE_API_KEY=opencode-... PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
AIWIKI_LLM_BACKEND=opencode-api AIWIKI_OPENCODE_API_KEY=opencode-... PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
AIWIKI_LLM_BACKEND=openai-api AIWIKI_LLM_API_KEY=sk-... PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
AIWIKI_LLM_BACKEND=anthropic-api AIWIKI_ANTHROPIC_API_KEY=sk-ant-... PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
```

检查当前后端：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check --probe
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check --probe-all --probe-timeout 20
```

认证说明：

- `deepseek-api`：走 `AIWIKI_DEEPSEEK_API_KEY` 或 `DEEPSEEK_API_KEY`；模型默认 `deepseek-v4-pro`，base URL 默认 `https://api.deepseek.com`
- `opencode-api`：走 `AIWIKI_OPENCODE_API_KEY` 或 `AIWIKI_LLM_API_KEY`；模型默认 `deepseek-v4-pro`。如果账号不可用或模型不可用，`llm-check --probe` 必须显式失败并显示 provider/model/base URL，不会静默伪装成备用后端成功
- `anthropic-api`：走 Anthropic Messages API；模型留空默认 `claude-sonnet-4-20250514`
- `openai-api`：走 OpenAI-compatible `/chat/completions`，key 走 `AIWIKI_LLM_API_KEY` 或 `OPENAI_API_KEY`
- **本地凭据存放规范**：API key **不得**进入 README、测试 fixture、`.envrc.dogfood` 或任何 git-tracked 文件。Product Shell 里填写的 key 只落到本机未跟踪的插件 `data.json`；CLI/dogfood 推荐落到 `~/.aiwiki-secrets/<provider>.env`（mode 600 / 父目录 700）

## 开发说明

验证入口是项目自有 `scripts/verify.sh`，不属于 `aiwiki` runtime 行为本身。AgentStack 脚手架已从本仓库移除。

按改动路径建议 verify target：

```bash
bash scripts/verify_target_rules.sh
```

按 target 验证，或跑全量：

```bash
bash scripts/verify.sh [scripts|smoke|python-static|acceptance|cli-smoke|product-shell-static|all]
```

### Developer Guide

本地开发最常用的入口只有三条：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced protocol-status
```

新增能力时，优先沿下面这张模块边界图落位，而不是继续往巨石文件里堆：

```text
cli/                       命令入口；只做参数解析与 dispatch
├─ drop.py / input_router.py   外部投喂入口（drop url / drop pdf / drop image / drop repo / drop markdown）
├─ runner/                 lifecycle / alchemy / nightly 等 high-level 编排
└─ planner/                deterministic + LLM-assisted plan 生成

execution/                 事实层 mutation（promote / revert / demote / archive / proposals…）
                           硬边界：所有 mutation 必须 receipt + hash + revert（M9-P0.1）
runner/alchemy.py          lane / primitive 编排，含 scope-honesty receipt（M9-P0.2）

cli/                       product-first command surface + legacy compat dispatch
drop.py                    raw materialization owner（url / pdf / image / repo / markdown）

compile/                   compile pipeline phases（content / runtime / output / persist）
app_compile.py             legacy orchestration / compat hotspot；新逻辑优先下沉
app_compile_ops.py         protocol switch / recurring promotion / agent-pack helpers
app_queries.py             ranking / report / slides / decision-memo / sop query helpers
app_linting/               lint phases / repair backlog / nightly health helpers

content/                   source / concept / derived / memory output 物化 owner
app_lifecycle.py           judgments / decisions / aging / review queue governance

render/                    views / packs / pilots / judgment asset render owner

memory/                    machine memory（graph / trace / recall / execution surfaces）
app_memory_query.py        query helpers owner

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
