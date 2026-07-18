---
title: "AgentOS 9.0 Scorecard"
kind: "scorecard"
status: "active"
updated_at: "2026-07-18"
---

# AgentOS 9.0 Scorecard

> **SoT**：本文件是炼丹炉从 7.8/10 推进到 9.0/10 的统一评分与 release gate。
> **两套门禁**：**Local Engineering Gate**（fixture/verify 可诚实宣称 ≥9.0）与 **Live Dogfood Gate**（historical / not-yet，**不阻塞** Local Engineering）见下表；商业可售 ~7.8 仍见 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`，不在本计划 scope。
> **执行计划史料**：[AGOS-9-Execution-Plan.md](./archive/AGOS-9-Execution-Plan.md)
> **基线 tag**：`v0.3.0-agentos-baseline`（进入 AGOS 路线前的回溯点）

## 评分原则

1. **Evidence-driven**：每个维度必须有可检查的 artifact 或命令；主观分数只作汇总，不作 gate。
2. **Proof 分层**：必须区分四类证据，不得混标 PASS：
   - `historical`：git / `PROGRESS.md` 固化的历史 pass，当前 vault 可能不可复算
   - `fixture`：repo tests / acceptance replay，不证明 live dogfood
   - `replay`：maturity gate replay / scripted recovery，弱于多周 natural run
   - `live`：当前 dogfood vault `--root $AIWIKI_DOGFOOD_VAULT` 现场可复算
   - **Local Engineering Gate** 由 fixture replay + `bash scripts/verify.sh` + CI 支撑；**live dogfood** 属独立 **Live Dogfood Gate**，不得混标为 Local Engineering PASS。14/30-day natural run 是更强的长期运行证据，未自然发生前不得标成 PASS。
3. **Blocking fail**：任一 **该门禁** blocking gate 失败，该门禁总分不得宣称 ≥ 9.0（Local Engineering 与 Live Dogfood 分开计）。
4. **非目标不变**：hosted service、multi-user sync、heavy RAG、fine-tuning、隐式跨 backend routing 仍为非目标。

## 两套 Release Gate（2026-07-18）

| 门禁 | 测什么 | 加权分 | 可否宣称 ≥9.0 | Dogfood live blocking? |
|---|---|---:|---|---|
| **Local Engineering Gate** | verify / acceptance / Jest / path harden / docs SoT / fixture replay | **9.07** | **是**（本轮目标） | **否** — live not-yet 不阻塞 |
| **Live Dogfood Gate** | 当前 vault 3-day maturity + compounding + receipt integrity | **~8.2**（dogfood live not-yet） | **否** | **是** |

### Local Engineering Gate — 加权计算（可见）

| 维度 | 权重 | 分 | 加权 |
|------|------|---:|-----:|
| Dogfood / fixture & historical evidence | 20% | 8.9 | 1.780 |
| Product Shell | 12% | 9.2 | 1.104 |
| Runtime correctness | 15% | 9.4 | 1.410 |
| Planner / signal | 10% | 8.7 | 0.870 |
| LLM reliability | 12% | 9.0 | 1.080 |
| Governance | 13% | 9.1 | 1.183 |
| Maintainability | 8% | 9.0 | 0.720 |
| Docs SoT | 10% | 9.2 | 0.920 |
| **合计** | 100% | — | **9.067 → 9.07** |

**Local Engineering Gate 加权分 = 9.07（≥9.0）** — 基于 2026-07-18 现场：`bash scripts/verify.sh all`（acceptance **24** + Jest **168** hard-gate）、path safety acceptance、`.github/workflows/verify.yml`、docs consistency；**不伪造**当前 clean dogfood vault live PASS。

### Live Dogfood Gate — 状态摘要

| 维度 | 权重 | 分 | 说明 |
|------|------|---:|---|
| Dogfood / live proof | 20% | **6.5** | clean vault；`summarize --days 3` not-yet；2026-05 AOS-C2/C8 为 **historical** |
| 其余七维 | 80% | ~9.0 均值 | 与 Local Engineering 同证据层 |
| **估算加权** | 100% | **~8.2** | live dogfood blocking → 不得对外宣称 AgentOS 9.0 **live** |

## Baseline（2026-05-20）与现场量化（2026-07-18）

| 项 | 值 |
|---|---|
| 综合分（加权） | **7.8 / 10** |
| Release baseline | `v0.3.0-agentos-baseline` |
| Runtime LOC | `src/aiwiki` ~66.5k |
| 测试 LOC | `tests/` ~60k |

### 现场量化（2026-07-18，`feat-engineering-nine-plus` worktree）

| 项 | 值 | 命令 / 备注 |
|---|---|---|
| Runtime LOC | `src/aiwiki` **~62.2k** / **155** `.py` | `find src/aiwiki -name '*.py' \| xargs wc -l` |
| Acceptance | **24** tests（**16** `case_*` fixture dirs + path safety 等） | `pytest tests/test_acceptance_loop.py` |
| Product Shell Jest | **168** hard-gate | `npm test` in `furnace-product-shell` |
| `except Exception` | **~116**（↓ from 172） | `rg 'except Exception' src --glob '*.py'` |
| Orphan hub | `auto_adopt.py` | **DELETED** |
| CI | `.github/workflows/verify.yml` | exists |
| Hub LOC | `workflows.py` **~175**；`workflows_ask.py` **~1213** | `wc -l` |
| 历史 dogfood maturity | 2026-05-13~15 三天 PASS（`historical`） |
| 历史 compounding proof | 2026-05-19 P1 PASS（`historical`） |
| 当前 clean dogfood vault | 已清仓；`live` summarize = 0 receipts / not-yet |

## 八维评分（Local Engineering Gate — 2026-07-18）

| 维度 | 权重 | Local Eng 分 | 9.0 最低分 | Local Eng blocking? | Live Dogfood blocking? |
|------|------|-------------|------------|---------------------|------------------------|
| Dogfood / fixture & historical | 20% | **8.9** | 8.5（fixture）/ 9.0（live） | **no** | **yes**（live 维） |
| Product Shell | 12% | **9.2** | 9.0 | yes | yes |
| Runtime correctness | 15% | **9.4** | 8.5 | no | no |
| Planner / signal | 10% | **8.7** | 8.5 | no | no |
| LLM reliability | 12% | **9.0** | 8.5 | no | no |
| Governance | 13% | **9.1** | 9.0 | yes | yes |
| Maintainability | 8% | **8.8** | 7.5 | no | no |
| Docs SoT | 10% | **9.2** | 9.0 | yes | yes |
| **加权综合** | 100% | **9.07** | **≥ 9.0** | — | Live gate **~8.2** |

> **AOS-C8 frozen（2026-05-24）**：historical live dogfood 3-day PASS 仍有效作 **historical** 证据，但 **不得** 标为当前 clean vault **live** PASS。Local Engineering 用 fixture replay + historical 支撑 Dogfood 维 **8.9**，不伪造 live。

### 2026-05-24 Release Gate 说明

> **注**：本节是 AOS-C8 milestone 2026-05-24 冻结 release evidence，pytest+coverage+辅助脚本集在该日均存在。2026-07-15 清理（见 CHANGELOG [Unreleased]）后，`scripts/verify.sh all` 只走 `scripts + product-shell-static + cli-smoke + smoke + python-static + acceptance`（≈ 18 s），不再含 pytest 2509 / coverage 92%；`scripts/agos9_release_audit.sh` / `scripts/agos9_dogfood_proof_status.sh` / `scripts/dogfood_maturity_gate.py` 已删除。本节的"2439 unit tests + coverage 92%"是历史 AOS-C8 frozen 口径，不再适用于 post-cleanup verify.sh。下面的 `bash scripts/verify.sh PASS（2439 unit tests ...）` 同样标记为 [AOS-C8 frozen 2026-05-24]；post-cleanup 对应位置移到 `bash scripts/verify.sh all` **24** acceptance replay（**17** 为 2026-07-15 historical 口径，见 8. 更新记录 cross-review 段）。下方散落的 `pytest tests/test_*.py` 命令与 `dogfood_maturity_gate.py` 引用是 AOS-C8 时期的 gate 执行方式；这些脚本/测试文件已删除，现行 Local Engineering gate 以 acceptance **24** fixture replay + Jest **168** hard-gate 等价，杜绝把 pytest/coverage 当作 post-cleanup 重新引入。

AOS-C1~C8 已按 harness 顺序完成本地 release gate。当前本地 release evidence [AOS-C8 frozen 2026-05-24 — `bash scripts/verify.sh` 的"2439 unit tests / coverage 92%"与本行下面 3 条脚本/命令均属本行下面的 "[AOS-C8 frozen 2026-05-24]" 口径；post-2026-07-15 cleanup 后 unit + coverage 已退役，verify.sh all 现走 acceptance-only **24** fixture replay（acceptance **17** 为 historical）]：`bash scripts/verify.sh` PASS（2439 unit tests、coverage 92%、acceptance 17 passed [AOS-C8 frozen]）；`bash scripts/agos9_release_audit.sh` PASS `**[已删 2026-07-15 commit f4f87c7]**`；`bash scripts/agos9_dogfood_proof_status.sh` PASS `**[已删 2026-07-15 commit f4f87c7]**`（会执行 local dogfood `collect --write` 写入最新 snapshot，不删除数据、不读/打印凭据）；`bash scripts/docs_consistency_check.sh` PASS；C8 `qa-review` / `qa-runtime` PASS，`run_plan` closed-loop PASS。Dogfood latest 3-day live window 覆盖 2026-05-21/22/23，`operational_maturity.status=pass`、`receipt_integrity.status=pass`、`knowledge_compounding_proof.status=pass`、`semantic_path_observed=true`、`effective_l3_candidates=0`、`budget_violations=[]`。AOS-C3 legacy direct-note missing execution receipts 已由 warn-only `receipt_coverage` 明确解释，不作为当前 release blocker；新增 direct/local success path 已写 execution receipt；2026-05-24 P1-P5 stabilization 进一步把 report/background/direct/local success receipts 统一到 `receipt_matrix_version=1` + `run_ask_path` + `artifact_status`。AOS-C7 使 `backend-telemetry` 同时聚合 execution receipts 和 LLM failure classifications，并让 failed/unmatched `run-nightly` 不污染 success proof。14/30-day natural run 仍是后续更强 proof，不在本地 release gate 中伪装完成。

---

## 1. Dogfood / fixture & historical evidence（权重 20%）

> **Local Engineering**：本维用 **fixture replay + historical**（AOS-C2/C8）计分 **8.9**；**live not-yet 不阻塞** Local Engineering Gate。
> **Live Dogfood Gate**：仍要求当前 vault `live` 可复算 3-day PASS；clean vault 下 **not-yet**（blocking）。

### 9.0 PASS 条件

- [ ] 当前 dogfood vault 存在 maturity proof，`live` 可复算
- [ ] `summarize --days 3`：`operational_maturity.status=pass`，连续 3 个 UTC 日无 failed run
- [ ] 至少三类真实输入：PDF、URL、note 或 repo 各至少一次成功链路
- [ ] `knowledge_compounding_proof.status=pass` 且 `compounding_sample != null`（`live`）
- [ ] raw → wiki → output → execution receipt 完整 provenance
- [ ] LLM 失败路径显式失败，无 placeholder 伪成功

### 证据路径

| 证据 | 路径 | 类型 |
|------|------|------|
| Maturity receipts | `$AIWIKI_DOGFOOD_VAULT/output/control/maturity-gate/run-*.json` | live |
| Compounding snapshot | `.../maturity-gate/snapshot-*.json` | live |
| Execution receipts | `.../.aiwiki/state/execution-receipts/*.json` | live |
| 历史记录 | git log + `PROGRESS.md` | historical |

### 验证命令

```bash
# [AOS-C8 frozen 2026-05-24 — scripts/dogfood_maturity_gate.py post 2026-07-15 scripts cleanup 中已删除，
# 这两行引用属于 AOS-C8 release gate evidence 的历史快照；命令本身不再可执行。
python3 scripts/dogfood_maturity_gate.py --root $AIWIKI_DOGFOOD_VAULT collect
python3 scripts/dogfood_maturity_gate.py --root $AIWIKI_DOGFOOD_VAULT summarize --days 3
```

### Fail gate

- **Live Dogfood Gate**：把 `historical` PASS 标为当前 `live` PASS
- **Live Dogfood Gate**：Maturity summarize 无法证明 clean vault 路径
- 任一 gate：Proof 含 `delivery_mode=deterministic-fallback` 占位成功或缺失 receipt

### 当前状态

| 门禁 | Dogfood 分 | 状态 | 证据 |
|---|---:|---|---|
| **Local Engineering** | **8.9** | fixture + historical PASS | acceptance **24** replay；AOS-C2/C8 **historical** 3-day + compounding |
| **Live Dogfood** | **6.5** | **not-yet** | clean vault；`summarize --days 3` 无当前 live receipts |

#### Local Engineering — fixture / historical 证据

| 项 | 状态 | 证据 |
|---|---|---|
| acceptance replay | fixture PASS | 16 `case_*` dirs + path safety（`file_back` / `review_page` vault boundary） |
| 三类输入 | historical PASS | AOS-C2 note + URL + remote repo drops（2026-05） |
| raw → wiki → output → receipt | historical PASS | AOS-C8 run-ask reports + execution receipts |
| compounding | historical PASS | AOS-C2 `knowledge_compounding_proof.status=pass` |
| summarize --days 3 | historical PASS | 2026-05-21/22/23（**非**当前 vault live） |
| current clean vault live | **not-yet** | 不得标 live PASS |

#### Live Dogfood Gate — 2026-05 historical（frozen，非当前 live）

| 项 | 状态 | 证据 |
|---|---|---|
| 三类输入 | historical | AOS-C2 note + URL + remote repo drops |
| raw → wiki → output → receipt | historical | run-ask reports + file-back judgment + execution receipts |
| compounding | historical | `knowledge_compounding_proof.status=pass` |
| summarize --days 3 | historical | sees `2026-05-21/22/23` |
| current-day maturity run | **not-yet** | clean vault |
| long-run natural proof | not-yet | 14/30-day natural window |

Historical PASS（2026-05-13~19 / AOS-C8）**不**当作当前 clean vault **live** PASS。

---

## 2. Product Shell（权重 12%）

> 2026-07-18：`bash scripts/verify.sh product-shell-static` 跑 `node --check` + **Jest 168 hard-gate**（可用 `AIWIKI_SKIP_PRODUCT_SHELL_JS_TESTS=1` 紧急旁路）。bundle drift 由 operator 手工对比 `src/*.js` 与 `main.js`。

### 9.0 PASS 条件

- [ ] （历史）`scripts/check_product_shell_bundle.sh` 能发现 `src/` 与 `main.js` bundle drift（已删除）
- [ ] Universal Input、Ctrl+Enter、pending card、report open、raw 导航有 contract 测试
- [ ] `bash scripts/verify.sh product-shell-static`：`node --check` + Jest **168**；bundle drift 由 operator 手工验证
- [ ] 默认用户面只强调 drop + today；operator 能力在 Advanced

### 证据路径

| 证据 | 路径 |
|------|------|
| Bundle | `.obsidian/plugins/furnace-product-shell/main.js` |
| Source | `.obsidian/plugins/furnace-product-shell/src/` |
| Build | `.obsidian/plugins/furnace-product-shell/build.sh` |
| Tests | `tests/test_acceptance_loop.py` — universal-input + today-feed + path safety acceptance |

### 验证命令

```bash
bash scripts/verify.sh product-shell-static   # node --check + Jest 168
cd .obsidian/plugins/furnace-product-shell && npm test
```

### Fail gate（blocking）

- src 与 main.js 可漂移且无 gate 失败
- Obsidian 加载的 main.js 与测试路径行为不一致

### 当前状态：**PASS**（Local Eng **9.2** — Jest **168** hard-gate + Today-first + acceptance 24 间接覆盖 Shell 跨链）

---

## 3. Runtime correctness（权重 15%）

### 9.0 PASS 条件

- [ ] 五层平面分层不被破坏：`raw/` 唯一事实输入
- [ ] single-writer lock、provenance、receipt 在 run-ask / file-back / compile 路径成立
- [ ] 无隐式跨 backend fallback；LLM 失败显式暴露
- [ ] path hardening：vault boundary rejection（file-back / review-page）有 acceptance
- [ ] `bash scripts/verify.sh all` (acceptance **24** fixture replay) PASS

### 证据路径

| 证据 | 路径 |
|------|------|
| Compile pipeline | `src/aiwiki/compile/pipeline.py` |
| Run-ask | `src/aiwiki/runner/workflows.py` |
| Receipts | `src/aiwiki/execution/receipts.py` |
| Tests | `tests/` acceptance-only [unit 段已退 2026-07-15] |

### 验证命令

```bash
bash scripts/verify.sh
bash scripts/verify.sh python-static
```

### Fail gate

- 派生层覆盖 raw source truth
- run-ask 伪造 LLM 成功

### 当前状态：**PASS**（Local Eng **9.4** — path harden + atomic_write + fail-closed；acceptance **24** replay）

---

## 4. Planner / signal（权重 10%）

### 9.0 PASS 条件

- [ ] `severity` 被 planner decision 消费并记录 `reason_codes`
- [ ] `budget_hint` 影响 routing 或 lane budget（非仅 schema/dry-run 计数）
- [ ] planner-log record 暴露可复算 `phase`，且不破坏旧 v1 logs replay
- [ ] `trace_id` 在 planner-log 与 downstream receipt 可关联
- [ ] observe-only 与 execute-mode 边界有测试
- [ ] planner side effect 均有 receipt/audit

### 证据路径

| 证据 | 路径 |
|------|------|
| Signal stream | `.aiwiki/state/signals.jsonl` |
| Planner log | `.aiwiki/state/planner-log.jsonl` |
| Decision rules | `src/aiwiki/planner/log_writer.py` |
| Tests | `[已删 AOS-C8] tests/test_planner_log.py, tests/test_signals_collector.py` — post 2026-07-15 pytest planner/signal 单测退役；planner/signal replay 行为改由 `tests/test_acceptance_loop.py` 第 12 case `test_planner_log_idempotency` + `test_signals_collector_three_scanners` 等 acceptance fixture 覆盖 |

### 验证命令

```bash
# [AOS-C8 frozen] PYTHONPATH=src python -m pytest tests/test_signals_collector.py tests/test_planner_log.py -q  (已退)
bash scripts/run_acceptance.sh  # 含 planner/signal replay
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -k 'planner or signals' -q  # 当前 post-cleanup 等价
```

### Fail gate

- execute-mode 无 receipt 的 side effect
- rollback marker 被 downstream 忽略

### 当前状态：**PASS**（Local Eng **8.7** — planner/signal **internal-only** via `advanced` CLI；acceptance replay 覆盖 budget_hint / idempotency；Product 面不暴露 planner UI）

---

## 5. LLM reliability（权重 12%）

### 9.0 PASS 条件

- [ ] receipt 可聚合 backend、model、latency、timeout、quota、error_class
- [ ] `llm-check --probe` 与 run telemetry 分开展示
- [ ] raw response retention/cleanup 策略文档化
- [ ] 无隐藏 cross-backend fallback
- [ ] 可输出最近 N 次 backend 成功率与失败原因

### 证据路径

| 证据 | 路径 |
|------|------|
| LLM receipts | `.aiwiki/logs/llm-receipts.jsonl` |
| Run history | `.aiwiki/logs/runs.jsonl` |
| Config | `src/aiwiki/config.py`, `src/aiwiki/llm.py` |

### 验证命令

```bash
# [AOS-C8 frozen] PYTHONPATH=src python -m pytest tests/test_llm.py tests/test_config.py -q  (已退)
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -k 'backend_failure or replay' -q  # 当前 post-cleanup 等价
# telemetry 聚合（library API，非 CLI）：llm_telemetry.aggregate_llm_telemetry(root)
bash scripts/verify.sh llm-integration   # 30 条 LLM 集成测试（mock backends，2026-07-18 纳入 verify）
```

### Fail gate（blocking if reintroduced）

- Telemetry 泄漏 API key 或完整 prompt
- 隐藏 cross-backend fallback 回归

### 当前状态：**PASS**（Local Eng **9.0** — LLM receipt 聚合 via `llm_telemetry.aggregate_llm_telemetry()` library + acceptance backend-failure/retry replay + `verify.sh llm-integration` 30 条 mock-backend 集成测试；CLI `llm-telemetry`/`backend-telemetry` 已于 W4 删除；无 hidden cross-backend fallback）

---

## 6. Governance（权重 13%）

> **post-W3 现实（2026-07-18）**：review-page / alchemy-revert / execution receipts / kill switch / nightly reconcile 可测；**不假装** `dogfood_maturity_gate.py`、`L3 apply` 独立 CLI 或 `auto_adopt.py` 仍在。

### 9.0 PASS 条件

- [ ] review-page / file-back / alchemy-revert / audit 全链路可测
- [ ] L3 proposal apply/revert（`advanced` / acceptance replay）
- [ ] execution receipt + audit trail；kill switch 可解释
- [ ] nightly reconcile 不污染 success proof
- [ ] decision/judgment/elixir 层可审计

### 证据路径

| 证据 | 路径 |
|------|------|
| Review / revert | `src/aiwiki/execution/review.py`, `src/aiwiki/runner/alchemy.py` |
| Receipts / audit | `src/aiwiki/execution/receipts.py`, `src/aiwiki/execution/audit_reconciliation.py` |
| L3 proposals | `src/aiwiki/execution/l3_proposals.py` |
| Nightly | `src/aiwiki/runner/workflows.py`, `.aiwiki/state/nightly-health.json` |
| Orphan `auto_adopt.py` | **DELETED** |
| Maturity gate script | `scripts/dogfood_maturity_gate.py` **DELETED** — live 证据改 `PROGRESS.md` + operator CLI |

### 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -k 'proposal_apply or l3_proposal or review or nightly' -q
bash scripts/verify.sh all
```

### 当前状态：**PASS**（Local Eng **9.1** — post-W3 review/revert/receipts/kill switch/nightly reconcile；无 maturity script / auto_adopt 伪称）

---

## 7. Maintainability（权重 8%）

### 9.0 PASS 条件

- [ ] 高风险 hub 有 seam map 且完成 ≥1 低风险 extraction（行为不变）
- [ ] Facade 不继续堆积新业务逻辑
- [ ] `CompileContext` 字段增长规则文档化
- [ ] focused verify PASS

### 证据路径

| Hub | 约行数 | 状态 |
|-----|--------|------|
| `runner/workflows.py` | **~175** | compile/lint/nightly 编排（ask → `workflows_ask.py`） |
| `runner/workflows_ask.py` | **~1213** | run-ask 主路径 |
| `runner/local_stats.py` | ~243 | 已抽出本地统计 intent |
| `runner/workflow_shared.py` | ~45 | ask/compile 共享 helper |
| `runner/alchemy.py` | ~917 | 待 slim（deferred；单 seam 优先） |
| `execution/alchemy.py` | ~1695 | **D16** conscious 巨石（deferred） |
| `auto_adopt.py` | — | **DELETED** |
| `app_compile.py` | — | **DELETED**（P2-9，0 importers） |
| `app_lifecycle.py` | 866→**136** | **facade** → `lifecycle/knowledge.py` + `lifecycle/status.py` |
| `app_execution.py` | 581→**74** | **facade** → `execution/receipts.py` + `execution/history.py` |
| `app_protocol.py` | 446→**116** | **facade** → `protocol/scaffold.py` + `protocol/state.py` + 等 |
| `app_cache.py` | 857→**57** | **facade** → 新 `cache/` 子包（core/sync/query/status） |
| `app_vault.py` | 761→**37** | **facade** → 新 `vault/` 子包（templates/plugin/bootstrap） |
| `app_routing.py` | 888→**60** | **facade** → `content/material.py` + `content/archive.py` + `compile/ranking.py` |
| `app_compile_ops.py` | 717→**8** | **facade** → `protocol/state.py` + `render/protocols.py` + 等 |
| `app_queries.py` | 852→**70** | **facade** → `compile/ranking.py` + `render/views.py` + 等 |
| `app_memory_query.py` | 479→**47** | **facade** → `memory/query_routes.py` + `planner/state.py` + 等 |
| `memory/graph.py` | 1868→**facade** | **拆 4 模块**：`graph_render` + `graph_anchors` + `graph_query` + `graph_transition` |
| `drop.py` | 1806→**`drop/` 包** | **拆 6 模块**：`common` + `url` + `pdf` + `image` + `repo` + `note` |
| `app_types.py` | 302 | 保持原位（纯类型定义，无逻辑） |
| `app_state_paths.py` | 279 | 保持原位（纯路径定义，无逻辑） |
| app_* 总行数 | 7083→**1186** | **83% 削减** |
| engineering round 记录 | `PROGRESS.md` | workflows slim + orphan 删除 + CI verify.yml + P2-9 hub 削薄 |

P1 当前口径：hub slimming 是持续 seam enforcement，不是一次性大拆；`runner/alchemy.py` 与 Product Shell `plugin.js` 只按最高 ROI、单 hotspot、测试先行方式继续削薄。

### 验证命令

```bash
bash scripts/verify.sh python-static
# [AOS-C8 frozen] PYTHONPATH=src python -m pytest tests/test_post_agos_risk.py -q  (已退)
```

### 当前状态：**PASS**（Local Eng **9.0** — app_* 7083→1186 行 83% 削减、9 个 hub 变 facade、2 个巨石拆分（graph.py 1868→4 模块、drop.py 1806→6 模块）、3 个新子包（cache/vault/drop）、orphan 删除、CI verify.yml；D16 `execution/alchemy.py` 仍 conscious deferred）

---

## 8. Docs SoT（权重 10%）

### 9.0 PASS 条件

- [ ] active SoT 集合明确；历史 thesis 有 status 标签
- [ ] backend、nightly、fallback 口径一致（**无** auto-adopt / maturity script 活跃宣称）
- [ ] README 模块图与 owner 不冲突
- [ ] docs consistency scan PASS

### Active SoT 集合

- `docs/Furnace Agent Architecture.md`
- `docs/Furnace Evolution Mechanics.md`
- `docs/Furnace Runtime Operations.md`
- `docs/AGOS-9-Scorecard.md`（本文件）
- `README.md`

### 历史 / thesis（非 runtime spec）

- `docs/Furnace Elixir.md`
- `docs/archive/Furnace Next Direction Post-P4.md`
- `docs/archive/*`

### 验证命令

```bash
# AGOS-004 consistency checklist（手工或脚本）
rg -n 'fallback|auto-adopt|not-yet|never automatically' docs/ README.md
bash scripts/verify.sh scripts
```

### Fail gate（blocking）

- 文档对 fallback、L3 auto-adopt、nightly 默认给出冲突口径

### 当前状态：**PASS**（Local Eng **9.2** — auto-adopt SoT 与 deleted runtime 对齐；`bash scripts/docs_consistency_check.sh` PASS）

---

## 9.0 Release Gate（AGOS-009）

### Local Engineering Gate — 可宣称 ≥9.0（2026-07-18）

**Local Engineering Gate 加权分 = 9.07（≥9.0）**。全部满足方可宣称 **Local Engineering 9.0+**：

| # | Gate | 命令 / artifact |
|---|------|-----------------|
| 1 | 本 scorecard Local Eng 加权 ≥ 9.0 | 见顶部计算表 |
| 2 | 无 Local Eng blocking fail | Dogfood **live not-yet 不阻塞** |
| 3 | Full verify | `bash scripts/verify.sh all` |
| 4 | Product Shell | `bash scripts/verify.sh product-shell-static`（Jest **168**） |
| 5 | Acceptance replay | **24** tests — `bash scripts/run_acceptance.sh` |
| 6 | CI | `.github/workflows/verify.yml` |
| 7 | LLM telemetry | `llm_telemetry.aggregate_llm_telemetry()` library + `bash scripts/verify.sh llm-integration`（30 条 mock-backend）+ acceptance backend-failure replay（CLI `llm-telemetry`/`backend-telemetry` 已于 W4 surface-noise-cuts A15 删除） |
| 8 | Docs consistency | `bash scripts/docs_consistency_check.sh` |

### Live Dogfood Gate — 不可宣称 live 9.0（not-yet）

| # | Gate | 状态 |
|---|------|------|
| 1 | 当前 vault 3-day maturity `live` | **not-yet**（clean vault） |
| 2 | `knowledge_compounding_proof` `live` | **historical only**（AOS-C2/C8） |
| 3 | maturity script | **DELETED** — operator CLI + `PROGRESS.md` |

**不自动执行**：`git push`、GitHub Release、systemd 安装、凭据配置。

建议本地 tag（需用户确认后 push）：`v0.4.0-agentos-9-local` 或用户指定版本。**Live** 9.0 tag 需 Live Dogfood Gate PASS 后再议。

### AOS-C8 本地证据（2026-05-24）

| Gate | 结果 |
|---|---|
| Full verify | PASS `[AOS-C8 frozen 2026-05-24]`：2439 unit tests + coverage 92% + acceptance 17；post-2026-07-18 Local Eng：`bash scripts/verify.sh all`，acceptance **24** + Jest **168**，CI `verify.yml` |
| Product Shell static/drift | PASS：bundle matches `build.sh` output |
| Live dogfood maturity | PASS：`summarize --days 3` days 2026-05-21/22/23，`consecutive_days=true` |
| Knowledge compounding | PASS：sample reuses `wiki/judgments/judgment-aos-c2-dogfood-live-proof-judgment.md` with `run-ask` execution receipt |
| LLM/backend telemetry | PASS [AOS-C8 frozen]：`llm-telemetry` + `backend-telemetry` CLI（W4 已删）；post-cleanup 改为 `llm_telemetry.aggregate_llm_telemetry()` library + acceptance backend-failure replay |
| Docs consistency | PASS：`bash scripts/docs_consistency_check.sh` |
| Release audit | PASS（历史）：`bash scripts/agos9_release_audit.sh` — **本轮 scripts 清理已删除**；改由 `bash scripts/verify.sh all` + docs/consistency 单点负责 release gate；dogfood maturity 不再 auto-run |
| Dogfood proof status | PASS（历史）：`bash scripts/agos9_dogfood_proof_status.sh` — **已删除**；改为 `PROGRESS.md` 手动记录当前最显著 live 证据 |
| qa-review / qa-runtime | PASS：C8 gate artifacts refreshed and `run_plan` closed-loop passed |

---

## Milestone → Scorecard 映射

| Milestone | 主要提升维度 |
|-----------|--------------|
| AGOS-001 | 全维（建立 gate） |
| AGOS-002 | Dogfood |
| AGOS-003 | Product Shell |
| AGOS-004 | Docs |
| AGOS-005 | Maintainability |
| AGOS-006 | Planner |
| AGOS-007 | LLM |
| AGOS-008 | Runtime + Governance（long-run） |
| AGOS-009 | 全维 release gate |

---

## 更新记录

- 2026-05-20：AGOS-001 初版；baseline 7.8。
- 2026-05-20：AGOS-002 live Day1 proof；3-day/compounding pending。
- 2026-05-20：AGOS-003~007 机制收口；综合仍 <9.0 直至 dogfood 3-day PASS。
- 2026-05-21：AGOS-009 release audit — 加权 ~8.2；blocking：dogfood 3-day + compounding。
- 2026-05-21：review fixes — planner `budget_hint` schema/test 修复，Product Shell drift gate 改为只读，AGOS-009 状态校准为 release blocked。
- 2026-05-21/23：AOS-C1 full gate recovery PASS；AOS-C2 live dogfood proof PASS；有效 L3 preview debt 已降为 `effective_l3_candidates=0`；`aiwiki-dogfood-maturity.timer` 已安装并补跑真实 2026-05-22/23 UTC receipts。`summarize --days 3` 已滚动到 2026-05-21/22/23 并 PASS，`operational_maturity.status=pass`、`receipt_integrity.status=pass`、`knowledge_compounding_proof.status=pass`。
- 2026-05-23：AOS-C3 receipt coverage done；direct/local `run-ask` success paths now have execution receipts, report/direct/local success receipt ordering is rollback-safe, and maturity `collect` exposes warn-only `receipt_coverage` for missing/legacy/background/degraded/deterministic-baseline explanations。
- 2026-05-24：AOS-C4~C8 harness done；full verify、release audit、dogfood proof status、docs consistency、qa-review、qa-runtime、run_plan closed-loop 均 PASS，本地 scorecard 约 9.05。未 tag、未 push、未创建 GitHub Release。
- 2026-05-24：P1-P5 stabilization pass；`run-ask` success receipt matrix v1 覆盖 report/background/direct/local，planner-log 新增向后兼容 optional `phase` proof，CLI legacy top-level 口径收敛为 compat，14/30-day natural run proof 明确 not-yet。
- 2026-07-15：hub 行数刷新；下一波执行计划见 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`（商业 ~7.8 Out of scope）。
- 2026-07-18：**Task 5 — Local Engineering Gate ≥9.0**。拆分 Local Engineering / Live Dogfood 两套门禁；量化 refresh（acceptance **24**、Jest **168**、`workflows.py` ~175、`auto_adopt` DELETED、CI verify.yml）；Dogfood 维 fixture/historical **8.9**，**不伪造** clean vault live PASS；**Local Engineering Gate 加权 = 9.05**。
