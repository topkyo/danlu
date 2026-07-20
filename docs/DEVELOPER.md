---
title: "炼丹炉开发者指南"
kind: "guide"
status: "active"
updated_at: "2026-07-20"
related_docs:
  - README.md
  - docs/INSTALL.md
  - AGENTS.md
---

# 炼丹炉开发者指南

面向贡献者与 operator。用户安装与日常使用见根 [README.md](../README.md)、[INSTALL.md](./INSTALL.md)、[USER_GUIDE.md](./USER_GUIDE.md)。

## 当前 runtime 实现（repo 视角）

当前 `aiwiki` runtime 按 **owner 分包** 组织；顶层 `app_*.py` hub 文件已在 P2-9（2026-07-18）归零。纯 re-export facade（`app.py` / `app_content` / `app_render` / `app_surfaces` / `app_memory_surfaces` / `app_memory.py` 等）更早删除。新增逻辑必须直引 owner 模块，禁止再引入 facade 或顶层 hub 文件。

- `src/aiwiki/utils/`：底层 primitives（`io` / `security` / `markdown` / `text` / `hash` / `time` / `path` / `json_utils` / `audit`）；原子写、runtime write lock、`safe_fetch` / `safe_resolve_within`、frontmatter、slugify / tokenize（CJK Lucene-style bigram；拉丁不变）、sha256、`utc_now`、`relative_path` 等。
- `src/aiwiki/state/` + owner 子包：持久化状态 I/O（`io` / `constants` / `manifest` / `cache`）+ 按域分布的 `compile/state` / `compile/build` / `content/material` / `content/archive` / `content/rewrite` / `execution/history` / `memory/action_state` / `memory/state` / `planner/state` 等；路径常量分散在各域 `paths.py`（原顶层 paths 常量 hub 已拆）。
- `src/aiwiki/protocol/`：单 runtime layout、schema scaffolding、protocol state、review windows、focus scoring、runtime config / descriptors。
- `src/aiwiki/lifecycle/`：`knowledge.py` / `status.py` — judgment / decision lifecycle、aging、review queue、knowledge lifecycle governance。
- `src/aiwiki/cli/`：CLI parser / dispatch / product-first command surface；普通入口固定为 `drop` / `today` / `advanced`；operator 命令（含 `metrics`）只注册在 `advanced` 下，旧顶层名靠 argv rewrite compat。
- `src/aiwiki/drop/`：`common` / `url` / `pdf` / `image` / `repo` / `note` — raw materialization owner（`drop-url` / `drop-pdf` / `drop-image` / `drop-repo` / `drop-note`）；用户入口推荐 `drop markdown`。
- `src/aiwiki/input_planner.py` + `src/aiwiki/executor.py`：universal `drop <payload>` 的 **plan/execute 分流**——LLM planner 只产出 Plan（`fetch_raw` / `fetch_page` / `read_local_repo` / `read_local_note` / `ask`），绝不写 `raw/`；deterministic executor 经 `safe_fetch` 原样落盘并带 provenance。CLI 另有 `drop plan <payload>`；`AIWIKI_LLM_PLANNER=0` 可退回 `input_router.classify_universal_input`。
- `src/aiwiki/compile/`：compile pipeline phase owner（content/runtime/output/persist）+ `ranking.py`（ranking 全家桶）。
- `src/aiwiki/content/`：source / concept / derived / material / archive / rewrite / `io.py` owner；`content/memory.py` 仅保留 2 个 A 域辅助函数（M/P/T/R 已拆到 `memory/action_core` + `execution/policy` + `execution/patch_plan` + `execution/repair_plan`）。
- `src/aiwiki/render/`：views / packs / pilots / protocols / judgment asset render owner（当前热点：`packs.py` ~1388、`views.py` ~1222）。
- `src/aiwiki/memory/`：machine memory graph（`graph_render` / `graph_anchors` / `graph_query` / `graph_transition` / `graph_builder`）、`query_routes.py`、execution surfaces、trace/recall/batch。
- `src/aiwiki/execution/`：execution bundles、receipts、apply/revert/audit、alchemy proposal mutation、L3 proposals（`receipts.py` / `history.py` / `l3_proposals.py` / `machine_memory_actions.py` 等）；`execution/alchemy*.py` 已拆为 `alchemy.py` + `alchemy_helpers` / `alchemy_receipts` / `alchemy_migration` / `alchemy_cleanup`。
- `src/aiwiki/runner/`：`workflows.py`（compile/lint/nightly）+ `workflows_ask*.py`（run-ask 已拆为 context/frontmatter/status/receipts 子模块）+ `alchemy.py` lane 编排 + `watch` / nightly 等 high-level workflow；AgentOS 膨胀面（`run-compile`、signals/planner CLI）已在 W3 删除。
- `src/aiwiki/planner/` 与 `src/aiwiki/signals/`：planner dry-run / log / safe primitive policy，以及 review / repair / aging / escalation signal source。
- `src/aiwiki/cache/`：cache core / sync / query / status / paths（原 `app_cache.py` 已删）。
- `src/aiwiki/vault/`：new-vault scaffold 与 Obsidian bootstrap（原 `app_vault.py` 已删）。
- 金丹主链路已落地：`alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 覆盖 candidate plane、settled plane、DAG/provenance gate、promote/revert/demote receipt、Stage-3 compounding acceptance 与 maturity gate 的 `elixir_quality_proof`；剩余 planned 只指显式 LLM/human contract 下的 semantic distillation。
- `src/aiwiki/app_shell/`：Product Shell summary、controls、status、HTML/surface assembly（带逻辑的 runtime 包，不是已删 facade）；Obsidian 插件源码在 `.obsidian/plugins/furnace-product-shell/src/`，它是用户 surface，不拥有 runtime SoT。
- `src/aiwiki/app_linting/`：lint phases、repair backlog、nightly health write helpers（带逻辑的 runtime 包）。

后续新增逻辑优先进入明确 owner package；`runner/alchemy.py`、`render/packs.py`、`execution/machine_memory_actions.py` 与 Product Shell `plugin.js` 继续按 seam map 小步削薄，不做 broad rewrite。禁止再引入纯 re-export facade 或顶层 `app_*.py` hub。

### CLI command taxonomy

`aiwiki` 顶层只保留 primary surface；operator 命令只注册在 `advanced` 下。旧顶层调用（如 `compile`、`drop-url`、`run-ask`）仍可通过 argv rewrite 兼容，并打印 `[deprecated]`，脚本应尽快改成 primary / `advanced`：

| Layer | Commands | Purpose |
| --- | --- | --- |
| `primary` | `drop`, `today`, `advanced` | 日常投料、今日简报，以及进入 operator 面（compile / lint / metrics / review-page 等）。`drop` 下含 `url / pdf / image / repo / markdown / plan`；无子命令的 `drop <payload>` 默认走 LLM planner（可 `AIWIKI_LLM_PLANNER=0` 关闭）。 |
| `advanced` | `aiwiki advanced ...` | 治理、编译、执行、审计、协议、LLM 和调试；完整列表见 `aiwiki advanced --help`。 |
| `compat` | 旧顶层名（rewrite only） | 不在 argparse 顶层注册；`drop-*` → `drop <kind>`，其余 → `advanced <cmd>`（含 legacy `metrics` / `compile` 等）。 |

### 当前 P1-P5 稳定化清单（2026-05-24）

本轮稳定化不扩大 AgentOS 半径，只把已经暴露的高风险边界固化为可验证契约：

| Priority | 当前处理 | 边界 |
| --- | --- | --- |
| P1 Hub slimming | 继续用 seam map / owner map 约束大 hub；`runner/alchemy.py` 与 Product Shell `plugin.js` 保持 deferred residual hotspots。 | 不做 broad rewrite；每轮只削一个有测试的 owner seam。 |
| P2 `run-ask` receipt matrix | 所有 `run-ask` success execution receipts 统一带 `receipt_matrix_version`、`run_ask_path`、`artifact_status`。 | LLM failure / degraded 仍不伪造 success execution receipt。 |
| P3 CLI product-first | 顶层只注册 `drop` / `today` / `advanced`；旧顶层名靠 rewrite compat。 | operator 命令仍在 `advanced` 下，避免破坏脚本与 dogfood。 |
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

LLM enrichment 仍然是炼丹炉主路径，但放在受控 worker 入口：`run-ask`（以及 operator 显式调用的 alchemy / review 等）。W3 已删除 `run-compile` / `run-lint` 与 AgentOS governance CLI；W8 产品 `run-nightly` / nightly timer / drop-auto 只做 deterministic `compile` + `lint`（无 agent-loop / signals / debt LLM 消化）。保留 `compile` / `lint` / `nightly` 确定性链路与 `alchemy-start/distill/finalize/promote/revert/demote`。

默认 unattended 路径按“**等待投料 → 炼丹 → 产出 → 回馈 → 受控学习**”运行：watcher 负责等待投料和最低可用 compile；成功 `drop` 默认触发 deterministic compile+lint；nightly 负责每天确定性炼化与健康写入；产物写到 `wiki/`、`output/`、receipt / audit；所有会改写系统行为的学习都必须保留 receipt、可审计、可回滚，不允许覆盖 `raw/` 或隐式切 backend。

图谱分两种视图，不要混用。**证据关系图**（Obsidian 侧边栏 Graph）是用户默认视图：只展示报告、来源、原料笔记与可选判断（`output/reports` → `wiki/sources` → `raw/inbox`），打开 Graph 即可，**不需要手动筛选**；默认隐藏未解析链接与孤儿节点，且不含 `raw/assets` / 概念 / 金丹 / derived / indexes。`compile` / 打开 vault 会自动恢复 `.obsidian/graph.json`。**机器记忆图谱**（`output/graph/machine-memory.html`）供维护与深挖：含 `source / concept / judgment / elixir(金丹)` 等完整关系。说明见 [wiki/indexes/README.md](../wiki/indexes/README.md)（indexes 由 compile 生成）。

治理债的目标是自动消化，符合炼丹炉"人只看异常"的设计哲学。分层按**影响范围 × 可逆性**定义（**W8 产品路径**：nightly / drop-auto / watch 只跑 deterministic compile+lint）。

> **Legacy / unused（2026-07-18）**：`src/aiwiki/runner/auto_adopt.py` 已删除；产品 `nightly` / `run-nightly` / timer 仅 deterministic `compile` + `lint` + health write，**不再**读取或执行 L1–L3 / judgment auto-adopt。下列 `AIWIKI_NIGHTLY_AUTO_ADOPT_*` / `AIWIKI_NIGHTLY_AUTO_APPLY_*` env 与 `.aiwiki/state/autonomy-policy.json` 中对应字段名**仅为旧 state / installer 兼容保留**，设为 `1` **不会**触发无人值守采纳；operator 需通过 `advanced` CLI（review / apply / alchemy 等）显式执行写回。

- **维护层（现行）**：compile / lint / nightly / 陈旧状态清理 / 派生索引 refresh — 只读或可逆的操作；产品 nightly 固定跑此层。
- **债务自消化层（legacy）**：source summary backlog / weak concepts / rewrite candidates / judgment metadata debt / machine-memory actions — 内部模块与 acceptance helper 仍可 inventory/preview；**产品 nightly 不再调用** debt_autopilot LLM 消化或 agent-loop。
- **治理层（legacy）**：concept backlog / revisit / source-concept links / concept splits — 结构性变更，可逆且有 receipt；历史曾由 `AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1` + `AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1` 驱动，**现已 no-op**。
- **判断层（legacy）**：counter-evidence / judgment review — LLM 驱动的语义复核；历史曾由 `AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=1` 驱动，**现已 no-op**。
- **策略层（legacy）**：L3 proposal / prompt 变更 / schema 变更 — 写回核心 prompt/policy/schema 前必须 `review proposal <id> --status accepted` 人工确认，再手动 `apply <proposal-id>` hash-gated 写 receipt；`AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3` 等 flag **不再**驱动 nightly。

`autonomy_policy` 仍解析 `autonomy_profile=agentic` 与上述 flag 字段以保持旧 state / receipt 口径可读；新安装 systemd nightly env 可能仍写入 `AIWIKI_AUTONOMY_PROFILE=agentic` 与 `AIWIKI_NIGHTLY_AUTO_ADOPT_*=0`，但均为 **legacy no-op**。watcher 仍 deterministic-only，不再配置跨 backend unattended fallback。

> 2026-07-15 scripts 清理：本节早先引用的 `scripts/dogfood_maturity_gate.py summarize --days 3` 等 heuristic 已删除。当前以 **manual 仅异常审计** 为成熟度观察口径：人盯 `.aiwiki/state/execution-receipts/` 与 `output/control/llm-receipts.jsonl` 中的异常事件；不依赖自动 3-day verdict 给出"成熟"宣称。

## LLM 后端

**产品默认（B44 product lock）：** 炼丹炉产品面只锁定 `opencode-api/deepseek-v4-pro` 一条主路由；Shell、CLI 与安装脚本均以此为准，runtime **不会**自动 cross-backend fallback。`deepseek-api`、`openai-api`、`anthropic-api` 仍作为开发者 escape hatch 保留，需显式设置 `AIWIKI_LLM_BACKEND` 切换。

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
- `run-ask` / `ask` 只产出 `output/reports/*.md` 自由 Markdown 报告；CLI `--format` 仅 `report`（缺省即 report）；旧值 `note|slides|figure|decision-memo|sop` 与 `--direct` 已硬删，argparse 直接拒绝
- `run-ask` 现在会先用 balanced prompt；如果碰到 timeout，会自动再试一次 lean prompt；失败时写出可审计失败说明和 receipt，不再伪装为 deterministic fallback 成功
- `run-ask` 现在也支持显式 `--lean` 与 `--timeout <seconds>`，用于直接选择稳优先 prompt 或覆盖单次调用 timeout，而不改动全局环境变量
- universal `drop <payload>` 默认走 LLM `input_planner`（`AIWIKI_LLM_PLANNER=0|false|no|off` 关闭，退回确定性分类器）；alchemy distill 可选 LLM body synthesizer（`AIWIKI_LLM_DISTILL=0|…` 关闭，退回 deterministic seed）
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
bash scripts/verify.sh [scripts|smoke|python-static|acceptance|llm-integration|cli-smoke|product-shell-static|all]
```

### Developer Guide

本地开发最常用的入口只有三条：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -q
bash scripts/verify.sh llm-integration
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced shell-status
```

新增能力时，优先沿下面这张模块边界图落位，而不是继续往巨石文件里堆：

```text
cli/                       命令入口；product-first surface + legacy argv rewrite compat
drop/                      raw materialization（common / url / pdf / image / repo / note）
input_planner.py           universal drop LLM Plan（不写 raw/）；AIWIKI_LLM_PLANNER kill-switch
executor.py                deterministic Plan 执行（safe_fetch / provenance / rollback）
runner/                    workflows（compile/lint/nightly）+ workflows_ask*（run-ask 子模块）
                           + alchemy lane 编排（含可选 distill synthesizer）+ watch / nightly
planner/                   dry-run / log / safe primitive policy
signals/                   review / repair / aging / escalation 信号源

protocol/                  layout / schema / protocol state / review windows / runtime config
lifecycle/                 knowledge + status（judgment/decision/aging/review queue）
compile/                   pipeline phases（content / runtime / output / persist）+ ranking
content/                   source / concept / material / archive / rewrite / io
render/                    views / packs / pilots / protocols（热点 packs ~1388, views ~1222）
memory/                    graph_* 子模块 + query_routes + trace/recall/execution surfaces
execution/                 receipts / history / apply / revert / audit / l3_proposals / alchemy_*
                           硬边界：所有 mutation 必须 receipt + hash + revert（M9-P0.1）
cache/                     cache core / sync / query / status / paths
vault/                     new-vault scaffold / Obsidian bootstrap

utils/                     底层 primitives（io / security / markdown / text(CJK tokenize) / hash …）
state/                     持久化状态 I/O + 各域 paths（best-effort + strict 双语义，M9-P0.4）
app_shell/                 Product Shell runtime surfaces（summary / controls / status / HTML）
app_linting/               lint phases / repair backlog / nightly health helpers

（顶层 app_*.py = 0；原 protocol / compile / state / drop 等顶层 hub 已删并下沉到上表 owner 包）
```

约定：

- `raw/` 是唯一事实输入层；不要把结论直接写回 source 层。
- `wiki/sources/` 与 `wiki/judgments|decisions|concepts/` 必须分层，派生产物保留 provenance；`wiki/derived/` 仅为 legacy 锚点（无现行 writer）。
- 新 CLI 命令优先放 `cli/` + owner module，不要在 shim 或 shell surface 上偷接逻辑。
- 协议规则只维护 `schema/protocols/general/` 单 runtime；不要重新引入多 slug 切换或 per-protocol scaffold。
- 事实层 mutation 必须走 `execution/`，receipt 写失败必须 rollback（不允许半写）。
- 持久化状态读取必须显式选 best-effort 还是 strict（见 `docs/Furnace Agent Architecture.md` §11.1）。
