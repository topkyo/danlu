---
title: "AgentOS 9.0 Scorecard"
kind: "scorecard"
status: "active"
updated_at: "2026-07-15"
---

# AgentOS 9.0 Scorecard

> **SoT**：本文件是炼丹炉从 7.8/10 推进到 9.0/10 的统一评分与 release gate。
> **执行计划史料**：[AGOS-9-Execution-Plan.md](./archive/AGOS-9-Execution-Plan.md)
> **基线 tag**：`v0.3.0-agentos-baseline`（进入 AGOS 路线前的回溯点）

## 评分原则

1. **Evidence-driven**：每个维度必须有可检查的 artifact 或命令；主观分数只作汇总，不作 gate。
2. **Proof 分层**：必须区分四类证据，不得混标 PASS：
   - `historical`：git / `PROGRESS.md` 固化的历史 pass，当前 vault 可能不可复算
   - `fixture`：repo tests / acceptance replay，不证明 live dogfood
   - `replay`：maturity gate replay / scripted recovery，弱于多周 natural run
   - `live`：当前 dogfood vault `--root $AIWIKI_DOGFOOD_VAULT` 现场可复算
   - 当前 3-day live release proof 可支撑本地 release gate；14/30-day natural run 是更强的长期运行证据，未自然发生前不得标成 PASS。
3. **Blocking fail**：任一 blocking gate 失败，总分不得宣称 ≥ 9.0。
4. **非目标不变**：hosted service、multi-user sync、heavy RAG、fine-tuning、隐式跨 backend routing 仍为非目标。

## Baseline（2026-05-20）

| 项 | 值 |
|---|---|
| 综合分（加权） | **7.8 / 10** |
| Release baseline | `v0.3.0-agentos-baseline` |
| Runtime LOC | `src/aiwiki` ~66.5k |
| 测试 LOC | `tests/` ~60k |
| 历史 dogfood maturity | 2026-05-13~15 三天 PASS（`historical`） |
| 历史 compounding proof | 2026-05-19 P1 PASS（`historical`） |
| 当前 clean dogfood vault | 已清仓；`live` summarize = 0 receipts / not-yet |

## 八维评分

| 维度 | 权重 | 当前分 | 9.0 最低分 | Blocking |
|------|------|--------|------------|----------|
| Dogfood / live proof | 20% | 9.3 | 9.0 | yes |
| Product Shell | 12% | 9.1 | 9.0 | yes |
| Runtime correctness | 15% | 9.2 | 8.5 | no |
| Planner / signal | 10% | 8.8 | 8.5 | no |
| LLM reliability | 12% | 8.8 | 8.5 | no |
| Governance | 13% | 9.2 | 9.0 | yes |
| Maintainability | 8% | 8.5 | 7.5 | no |
| Docs SoT | 10% | 9.1 | 9.0 | yes |
| **加权综合** | 100% | **~9.05**（2026-05-24 AOS-C8 local release gate PASS） | **≥ 9.0** | — |

### 2026-05-24 Release Gate 说明

AOS-C1~C8 已按 harness 顺序完成本地 release gate。当前本地 release evidence：`bash scripts/verify.sh` PASS（2439 unit tests、coverage 92%、acceptance 17 passed）；`bash scripts/agos9_release_audit.sh` PASS；`bash scripts/agos9_dogfood_proof_status.sh` PASS（会执行 local dogfood `collect --write` 写入最新 snapshot，不删除数据、不读/打印凭据）；`bash scripts/docs_consistency_check.sh` PASS；C8 `qa-review` / `qa-runtime` PASS，`run_plan` closed-loop PASS。Dogfood latest 3-day live window 覆盖 2026-05-21/22/23，`operational_maturity.status=pass`、`receipt_integrity.status=pass`、`knowledge_compounding_proof.status=pass`、`semantic_path_observed=true`、`effective_l3_candidates=0`、`budget_violations=[]`。AOS-C3 legacy direct-note missing execution receipts 已由 warn-only `receipt_coverage` 明确解释，不作为当前 release blocker；新增 direct/local success path 已写 execution receipt；2026-05-24 P1-P5 stabilization 进一步把 report/background/direct/local success receipts 统一到 `receipt_matrix_version=1` + `run_ask_path` + `artifact_status`。AOS-C7 使 `backend-telemetry` 同时聚合 execution receipts 和 LLM failure classifications，并让 failed/unmatched `run-nightly` 不污染 success proof。14/30-day natural run 仍是后续更强 proof，不在本地 release gate 中伪装完成。

---

## 1. Dogfood / live proof（权重 20%）

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
| Execution receipts | `.../output/control/execution-receipts/*.json` | live |
| 历史记录 | git log + `PROGRESS.md` | historical |

### 验证命令

```bash
python3 scripts/dogfood_maturity_gate.py --root $AIWIKI_DOGFOOD_VAULT collect
python3 scripts/dogfood_maturity_gate.py --root $AIWIKI_DOGFOOD_VAULT summarize --days 3
```

### Fail gate（blocking）

- 把 `historical` PASS 标为当前 `live` PASS
- Maturity summarize 无法证明 clean vault 路径
- Proof 含 `delivery_mode=deterministic-fallback` 占位成功或缺失 receipt

### 当前状态：**PASS live**（2026-05-23）

| 项 | 状态 | 证据 |
|---|---|---|
| 三类输入 | live PASS | AOS-C2 note + URL + remote repo drops |
| raw → wiki → output → receipt | live PASS | run-ask reports + file-back judgment + execution receipts |
| compounding | live PASS | `knowledge_compounding_proof.status=pass`; sample reuses `wiki/judgments/judgment-aos-c2-dogfood-live-proof-judgment.md` |
| receipt-backed actions | live PASS | `receipt_backed_actions=25`, `output_file_back_rate=0.3333`, `judgment_or_elixir_reuse_count=2` |
| semantic review path | live PASS | `review-page-judgment-aos-c2-dogfood-live-proof-judgment-2.json`, `semantic_path_observed=true`, `judgment_review_processed_delta=1` |
| current-day maturity run | live PASS | `run-20260523T100035Z.json` |
| summarize --days 3 | live PASS | sees `2026-05-21/22/23`, `consecutive_days=true`, `status_counts.pass=3` |
| receipt integrity | live PASS | `deterministic_only_runs=[]`, `failed_runs=[]`, `prompt_hash_changed_runs=[]` |
| operational maturity | live PASS | `operational_maturity.status=pass`, `budget_violations=[]`, `effective_l3_candidates=0` |
| agentic non-core autonomy | live gate | `agentic_autonomy_report.status=pass` now requires `llm_governed_apply_count > 0`, `non_core_human_required_count=0`, and `core_auto_apply_count=0` |
| LLM failure handling | live explicit | timeout receipts are `blocked/failed`, not fake success |
| receipt coverage explainability | repo targeted/unit/acceptance PASS | AOS-C3 adds `receipt_coverage` snapshot field; direct/local `run-ask` success paths now write execution receipts; failure-after-run-notes paths do not leave success receipts |
| long-run natural proof | not-yet | 3-day live release proof is PASS; 14/30-day natural window must wait for wall-clock evidence |

Historical PASS（2026-05-13~19）不当作当前 live PASS。

---

## 2. Product Shell（权重 12%）

### 9.0 PASS 条件

- [ ] `scripts/check_product_shell_bundle.sh` 能发现 `src/` 与 `main.js` bundle drift
- [ ] Universal Input、Ctrl+Enter、pending card、report open、raw 导航有 contract 测试
- [ ] `bash scripts/verify.sh product-shell-static` 封装 bundle drift check，不只 `node --check`
- [ ] 默认用户面只强调 drop + today；operator 能力在 Advanced

### 证据路径

| 证据 | 路径 |
|------|------|
| Bundle | `.obsidian/plugins/furnace-product-shell/main.js` |
| Source | `.obsidian/plugins/furnace-product-shell/src/` |
| Build | `.obsidian/plugins/furnace-product-shell/build.sh` |
| Tests | `tests/test_product_shell*.py` + plugin Jest |

### 验证命令

```bash
bash scripts/verify.sh product-shell-static
cd .obsidian/plugins/furnace-product-shell && npm test  # 若 node_modules 可用
PYTHONPATH=src python -m pytest tests/test_product_shell*.py -q
```

### Fail gate（blocking）

- src 与 main.js 可漂移且无 gate 失败
- Obsidian 加载的 main.js 与测试路径行为不一致

### 当前状态：**PASS**（`product-shell-static` 调用 `scripts/check_product_shell_bundle.sh`）

---

## 3. Runtime correctness（权重 15%）

### 9.0 PASS 条件

- [ ] 五层平面分层不被破坏：`raw/` 唯一事实输入
- [ ] single-writer lock、provenance、receipt 在 run-ask / file-back / compile 路径成立
- [ ] 无隐式跨 backend fallback；LLM 失败显式暴露
- [ ] `bash scripts/verify.sh` unit + acceptance PASS

### 证据路径

| 证据 | 路径 |
|------|------|
| Compile pipeline | `src/aiwiki/compile/pipeline.py` |
| Run-ask | `src/aiwiki/runner/workflows.py` |
| Receipts | `src/aiwiki/execution/receipts.py` |
| Tests | `tests/` acceptance + unit |

### 验证命令

```bash
bash scripts/verify.sh
bash scripts/verify.sh python-static
```

### Fail gate

- 派生层覆盖 raw source truth
- run-ask 伪造 LLM 成功

### 当前状态：**PASS**（fixture/replay；live 依赖 AGOS-002；P1-P5 stabilization adds `run-ask` receipt matrix v1 across report/background/direct/local success paths）

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
| Tests | `tests/test_planner_log.py`, `tests/test_signals_collector.py` |

### 验证命令

```bash
PYTHONPATH=src python -m pytest tests/test_signals_collector.py tests/test_planner_log.py -q
bash scripts/run_acceptance.sh  # 含 planner/signal replay
```

### Fail gate

- execute-mode 无 receipt 的 side effect
- rollback marker 被 downstream 忽略

### 当前状态：**PASS**（`budget_hint` 消费于 `planner/log_writer.py`；schema 接受 `budget_used.max_pages/max_tokens`；new planner-log records include decision-derived optional `phase` = `observe/light/heavy/proposal/human` while old v1 records without `phase` remain valid; tests 覆盖真实写入路径）

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
PYTHONPATH=src python -m pytest tests/test_llm.py tests/test_config.py -q
# AGOS-007 完成后：telemetry report CLI
```

### Fail gate（blocking if reintroduced）

- Telemetry 泄漏 API key 或完整 prompt
- 隐藏 cross-backend fallback 回归

### 当前状态：**PASS**（`aiwiki llm-telemetry --limit N` 聚合 LLM receipts；`aiwiki backend-telemetry --limit N` 聚合 execution receipts + LLM receipt failure classifications，区分 quota/timeout/unavailable/error_class；probe 结果继续与 run telemetry 分开展示）

---

## 6. Governance（权重 13%）

### 9.0 PASS 条件

- [ ] review / receipt / audit / revert / kill switch 全链路可测
- [ ] L3 hash-gated apply/revert
- [ ] dogfood maturity gate 不误报成熟
- [ ] decision/judgment/elixir 层可审计

### 证据路径

| 证据 | 路径 |
|------|------|
| Maturity gate | `scripts/dogfood_maturity_gate.py` |
| L3 | `src/aiwiki/execution/l3_proposals.py` |
| Autonomy | `src/aiwiki/autonomy_policy.py` |

### 验证命令

```bash
PYTHONPATH=src python -m pytest tests/test_dogfood_maturity_gate.py tests/test_l3_proposals.py -q
bash scripts/verify.sh
```

### 当前状态：**PASS**

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
| `runner/workflows.py` | ~1425 | compile/lint/nightly 编排（ask → `workflows_ask.py`） |
| `runner/workflows_ask.py` | ~1320 | 已抽出 run-ask 路径 |
| `runner/local_stats.py` | ~243 | 已抽出本地统计 intent |
| `runner/workflow_shared.py` | ~45 | ask/compile 共享 helper |
| `runner/alchemy.py` | ~917 | 待 slim（deferred；单 seam 优先） |
| `app_protocol.py` | ~442 | library 已抽出 |
| AOS-003/005/006 slim 记录 | `docs/archive/analysis/`, `PROGRESS.md` | local_stats + workflows_ask 完成 |

P1 当前口径：hub slimming 是持续 seam enforcement，不是一次性大拆；`runner/alchemy.py` 与 Product Shell `plugin.js` 只按最高 ROI、单 hotspot、测试先行方式继续削薄。

### 验证命令

```bash
bash scripts/verify.sh python-static
PYTHONPATH=src python -m pytest tests/test_post_agos_risk.py -q
```

### 当前状态：**PASS**（seam map + ≥2 extractions：local_stats、workflows_ask）

---

## 8. Docs SoT（权重 10%）

### 9.0 PASS 条件

- [ ] active SoT 集合明确；历史 thesis 有 status 标签
- [ ] backend、L3 auto-adopt、nightly、fallback 口径一致
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

### 当前状态：**PASS**（active SoT 标签 + Elixir/Next Direction 校准；持续扫描）

---

## 9.0 Release Gate（AGOS-009）

全部满足方可宣称 **AgentOS 9.0**：

| # | Gate | 命令 / artifact |
|---|------|-----------------|
| 1 | 本 scorecard 加权 ≥ 9.0 | 人工汇总 + 各维 PASS |
| 2 | 无 blocking fail gate | 见上表 |
| 3 | Full verify | `bash scripts/verify.sh` |
| 4 | Product Shell static + drift | `bash scripts/verify.sh product-shell-static` |
| 5 | Acceptance replay | `bash scripts/run_acceptance.sh` |
| 6 | Live dogfood maturity | `dogfood_maturity_gate.py summarize --days 3` → pass |
| 7 | LLM telemetry report | AGOS-007 CLI/report |
| 8 | Docs consistency | AGOS-004 checklist |
| 9 | qa-review | `.codex/gates/qa-review.md` |
| 10 | qa-runtime | `.codex/gates/qa-runtime.md`（`runtime_result: warn` 时 release blocking） |

**不自动执行**：`git push`、GitHub Release、systemd 安装、凭据配置。

建议本地 tag（需用户确认后 push）：`v0.4.0-agentos-9` 或用户指定版本。

### AOS-C8 本地证据（2026-05-24）

| Gate | 结果 |
|---|---|
| Full verify | PASS：`bash scripts/verify.sh`，2439 unit tests，coverage 92%，acceptance 17 passed |
| Product Shell static/drift | PASS：bundle matches `build.sh` output |
| Live dogfood maturity | PASS：`summarize --days 3` days 2026-05-21/22/23，`consecutive_days=true` |
| Knowledge compounding | PASS：sample reuses `wiki/judgments/judgment-aos-c2-dogfood-live-proof-judgment.md` with `run-ask` execution receipt |
| LLM/backend telemetry | PASS：`llm-telemetry` + `backend-telemetry` expose recent N backend/model/status and failure classes |
| Docs consistency | PASS：`bash scripts/docs_consistency_check.sh` |
| Release audit | PASS：`bash scripts/agos9_release_audit.sh` |
| Dogfood proof status | PASS：`bash scripts/agos9_dogfood_proof_status.sh`（会写 local dogfood snapshot via `collect --write`） |
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
- 2026-07-15：hub 行数刷新（`runner/alchemy.py` ~917、`app_protocol.py` ~442）；下一波执行计划见 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`（不改变 9.0 local release 口径）。
