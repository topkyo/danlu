# AgentOS 9.0 Scorecard

> **SoT**：本文件是炼丹炉从 7.8/10 推进到 9.0/10 的统一评分与 release gate。
> **执行计划**：[AGOS-9-Execution-Plan.md](./AGOS-9-Execution-Plan.md)
> **基线 tag**：`v0.3.0-agentos-baseline`（进入 AGOS 路线前的回溯点）

## 评分原则

1. **Evidence-driven**：每个维度必须有可检查的 artifact 或命令；主观分数只作汇总，不作 gate。
2. **Proof 分层**：必须区分四类证据，不得混标 PASS：
   - `historical`：git / `PROGRESS.md` 固化的历史 pass，当前 vault 可能不可复算
   - `fixture`：repo tests / acceptance replay，不证明 live dogfood
   - `replay`：maturity gate replay / scripted recovery，弱于多周 natural run
   - `live`：当前 dogfood vault `--root /home/tim/danlu/炼丹炉` 现场可复算
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
| Dogfood / live proof | 20% | 5.5 | 9.0 | yes |
| Product Shell | 12% | 7.5 | 9.0 | yes |
| Runtime correctness | 15% | 8.5 | 8.5 | no |
| Planner / signal | 10% | 7.0 | 8.5 | no |
| LLM reliability | 12% | 7.5 | 8.5 | no |
| Governance | 13% | 9.0 | 9.0 | yes |
| Maintainability | 8% | 6.5 | 7.5 | no |
| Docs SoT | 10% | 7.5 | 9.0 | yes |
| **加权综合** | 100% | **~8.2**（2026-05-21 复评） | **≥ 9.0** | — |

### 2026-05-21 复评说明

AGOS-001~008 机制已收口，但 **9.0 release gate 未达成**：dogfood 仅 Day1 live proof（`consecutive_days=false`），compounding `not-yet`，不得宣称 9.0。

---

## 1. Dogfood / live proof（权重 20%）

### 9.0 PASS 条件

- [ ] 当前 dogfood vault 存在 maturity proof，`live` 可复算
- [ ] `summarize --recent 3`：`operational_maturity.status=pass`，连续 3 天无 failed run
- [ ] 至少三类真实输入：PDF、URL、note 或 repo 各至少一次成功链路
- [ ] `knowledge_compounding_proof.status=pass` 且 `compounding_sample != null`（`live`）
- [ ] raw → wiki → output → execution receipt 完整 provenance
- [ ] LLM 失败路径显式失败，无 placeholder 伪成功

### 证据路径

| 证据 | 路径 | 类型 |
|------|------|------|
| Maturity receipts | `/home/tim/danlu/炼丹炉/output/control/maturity-gate/run-*.json` | live |
| Compounding snapshot | `.../maturity-gate/snapshot-*.json` | live |
| Execution receipts | `.../output/control/execution-receipts/*.json` | live |
| 历史记录 | git log + `PROGRESS.md` | historical |

### 验证命令

```bash
python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 collect
python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --recent 3
```

### Fail gate（blocking）

- 把 `historical` PASS 标为当前 `live` PASS
- Maturity summarize 无法证明 clean vault 路径
- Proof 含 `delivery_mode=deterministic-fallback` 占位成功或缺失 receipt

### 当前状态：**PARTIAL live**（2026-05-20）

| 项 | 状态 | 证据 |
|---|---|---|
| collect/summarize | live PASS path | `snapshot-20260520T155756Z.json` |
| 三类输入 | live | URL + note + repo drops |
| maturity run | live pass ×1 | `run-20260520T155837Z.json` |
| run-ask LLM | live success | `delivery_mode=llm-direct`, opencode-api |
| 连续 3 日 | **pending wall-clock** | `consecutive_days=false`, need Day2–3 receipts |
| compounding | **pending material** | no `wiki/judgments/` in clean vault |

Historical PASS（2026-05-13~19）不当作当前 live PASS。

---

## 2. Product Shell（权重 12%）

### 9.0 PASS 条件

- [ ] `src/` 改动未 rebuild `main.js` 时 verify 失败（bundle drift gate）
- [ ] Universal Input、Ctrl+Enter、pending card、report open、raw 导航有 contract 测试
- [ ] `bash scripts/verify.sh product-shell-static` 含 drift check，不只 `node --check`
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

### 当前状态：**PASS**（`scripts/check_product_shell_bundle.sh` in `product-shell-static`）

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

### 当前状态：**PASS**（fixture/replay；live 依赖 AGOS-002）

---

## 4. Planner / signal（权重 10%）

### 9.0 PASS 条件

- [ ] `severity` 被 planner decision 消费并记录 `reason_codes`
- [ ] `budget_hint` 影响 routing 或 lane budget（非仅 schema/dry-run 计数）
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

### 当前状态：**PASS**（`budget_hint` 消费于 `planner/log_writer.py`；schema 接受 `budget_used.max_pages/max_tokens`；tests 覆盖真实写入路径）

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

### 当前状态：**PASS**（`aiwiki llm-telemetry --limit N` 聚合 `.aiwiki/logs/llm-receipts.jsonl`）

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
| `runner/workflows.py` | 2772 | 待 slim |
| `runner/alchemy.py` | 2589 | 待 slim |
| `app_protocol.py` | 1999 | 稳定 |
| AOS-003/005/006 slim 记录 | `docs/analysis/`, `PROGRESS.md` | 部分完成 |

### 验证命令

```bash
# AGOS-005 后：focused pytest for extracted seam
bash scripts/verify.sh python-static
```

### 当前状态：**PARTIAL**

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
- `docs/Furnace Next Direction Post-P4.md`
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
| 6 | Live dogfood maturity | `dogfood_maturity_gate.py summarize --recent 3` → pass |
| 7 | LLM telemetry report | AGOS-007 CLI/report |
| 8 | Docs consistency | AGOS-004 checklist |
| 9 | qa-review | `.codex/gates/qa-review.md` |
| 10 | qa-runtime | `.codex/gates/qa-runtime.md`（`runtime_result: warn` 时 release blocking） |

**不自动执行**：`git push`、GitHub Release、systemd 安装、凭据配置。

建议本地 tag（需用户确认后 push）：`v0.4.0-agentos-9` 或用户指定版本。

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
