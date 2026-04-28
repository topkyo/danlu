# 炼丹炉 9-Standard Closure — P0..P2

> 生成时间：2026-04-28，承接 oracle 独立评估（session `ses_22eaafe24ffeXPmGLs8GsyjxON`，评分 8.1/10）。
> SoT：`docs/Furnace Agent Architecture.md` + `Furnace Evolution Mechanics.md` + `AGENTS.md` 9 分硬约束。
> 本文件不是路线图，是**收口决策**。具体 milestone 实现走 `.codex/plans/active.md` + harness 流程。

---

## 0. 视角校准

oracle 当前评估为 **8.1/10**，未达 9/10。主要差距集中在**事实层一致性**与**关键不变量执行**两个维度，而不是缺功能。

不再追求新功能。本轮目标是**把 9 分边界守住**：可审计、可回滚、不静默吞错、scoped 名实一致、SoT 单一。

完成 P0 后，oracle 复评应至少 8.7+；P0 + P1 完成后应可达 9/10。

不背技术债：所有修复直接走最优解，不为旧实现兜底。

---

## 1. 当前差距清单（按重要性，oracle 报告原文）

1. **scoped primitive 仍名实不符** — `runner/alchemy.py:2150-2194` 中 `compile/lint/nightly` 在 lane apply 中直接全局执行，receipt 用 `scope_enforced=false` 自我承认
2. **部分关键 mutation 可在 receipt/audit 写失败后"成功"** — `execution/alchemy.py:1052-1091,1196-1201` promote/revert receipt 写失败只 logging
3. **事实层 / 工程 contract 漂移** — `.codex/contracts/active.md` 缺失；`.codex/plans/active.md` 与 PROGRESS / docs 状态混杂
4. **planner / heavy / light / L3 仍 partial** — 架构文档自己标注（`docs/Furnace Agent Architecture.md:127-130`）；非 9 分阻塞但需在 P2 后续承接
5. **错误处理仍有静默吞错路径** — `app_state.py:279-305` `load_json_document` 坏 JSON 返回 `{}`，`load_jsonl_documents` 坏行直接 `continue`
6. **acceptance 覆盖关键不变量不足** — 缺 receipt 写失败、corrupt state、并发 writer、scope enforcement、investing E2E 等关键路径 case
7. **模块体积 / facade 债务** — `app.py` re-export、`app_compile.py` 汇聚、`runner/alchemy.py` 仍是巨石；非 9 分阻塞，留 P2 持续

---

## 2. P0 — 9 分阻塞项（必须做）

### P0.1 — Receipt / Audit 成为 mutation 的硬边界

**问题**：`promote_elixir` / `revert_elixir` 在 receipt 写失败时只 `logging.exception`，主 mutation 仍然返回成功。这违反 9 分核心约束"所有写回必须有 receipt + hash gate + revert"。比"没有 receipt"更危险，因为外部以为已审计。

**目标**：mutation 在 receipt / audit 写失败时**必须**显式失败：
- 优先选项：rollback 已写的 mutation（settled / candidate / state），返回 `status=failed` 抛出明确异常
- 次选项：接受 receipt 写失败但返回 `status=partial`，写 compensating audit event，并由上层 surfaces 显式标红
- **不允许**：mutation 成功 + receipt 缺失 + 调用者无感知

**范围**：
- `src/aiwiki/execution/alchemy.py` — `promote_elixir` (1052-1091)、`revert_elixir` (1196-1201, 1277-1283)
- 任何遵循同一 try/except + logging 套路的 mutation 入口（盘点时如果发现要一并修）

**成功标准**：
- 至少一个 unit test 模拟 receipt 写失败（monkeypatch `Path.write_text` 抛 OSError），断言 `promote_elixir` raise + 文件系统已 rollback / 标 partial
- 至少一个 acceptance fixture 覆盖 `promote → receipt fail → state 一致`
- 旧测试中类似 "does_not_rollback_when_receipt_write_fails" 的反向断言要被改正

**不做**：跨 process 的分布式事务；只做 single-writer 内的原子性。

---

### P0.2 — Scoped Lane Primitive 名实一致

**问题**：`runner/alchemy.py:2150-2194` 中 `compile/lint/nightly` 在 lane apply 模式下直接全局执行，receipt 写 `scope_enforced=false` + `scope_enforcement_reason="primitive_global_only:..."`。这是诚实标注，但不能算 9 分的 scoped execution。

**目标**：二选一，原则是 KISS：
- **方案 A（推荐）**：把 scoped apply 模式下的 `compile/lint/nightly` 显式禁掉，CLI 层报错或自动降级到 global mode，receipt 不再带"声明 scoped 但执行 global"的双语义
- 方案 B：真正实现 scope filter（成本高，本轮不做）

**范围**：
- `src/aiwiki/runner/alchemy.py:2150-2194`
- 相关 dry-run plan / apply lane 入口
- 测试 `tests/test_alchemy_lanes.py:752-757` 不再断言 `scope_enforced=false` 是 acceptable 终态

**成功标准**：
- 任何写出 receipt 的路径，要么 `scope_enforced=true`、要么不允许声明 scope
- 不存在 receipt 同时写 `scope=...` + `scope_enforced=false` 的产物
- 受影响 acceptance 的 golden 同步刷新（仅限新增/删除字段，不接受 receipt 语义变更）

**不做**：实现完整的 incremental scoped compile / lint（属于另一轮工程级目标，不是 9 分 gate）。

---

### P0.3 — 事实层 SoT 单一化

**问题**：
- `.codex/contracts/active.md` 不存在；AGENTS.md 把它列为本轮设计/范围 SoT
- `.codex/plans/active.md` 仍混杂 EP-001..EP-021 旧路线图 + Furnace M0-M5 + M-PS / M-C / M-E 等多个世代标记，与 PROGRESS.md / docs 状态不完全一致
- 阅读者必须人工判断"当前事实"

**目标**：
- 物化 `.codex/contracts/active.md`：本轮 9-Standard Closure P0..P2 milestone
- `.codex/plans/active.md` 追加 M9-P0..P2 子 milestone（不删除历史 EP / M0-M5 / M6 / M-PS / M-C / M-E 记忆，但当前活跃路线图要清晰可见）
- README / AGENTS / PROGRESS / docs / `.codex` 任意一个入口都能在 30 秒内回答"当前在做什么"

**范围**：
- `.codex/contracts/active.md`（新建）
- `.codex/plans/active.md`（在 Milestone Index 末尾追加 M9 系列）
- `docs/Furnace 9-Standard Closure P0-P2.md`（本文件）
- 必要时同步 `PROGRESS.md` Next Steps

**成功标准**：
- harness `bash scripts/run_plan.sh` 能从 plan 物化 contract 并执行
- 不存在两份事实源对当前 milestone 状态描述冲突

**不做**：归档历史路线图（保留为记忆即可）；这一项本身就是 P0.3 的执行结果，没有独立 P0 编号。

---

### P0.4 — 去除静默吞错

**问题**：
- `app_state.py:279-285` `load_json_document` 坏 JSON 默认返回 `{}`
- `app_state.py:293-308` `load_jsonl_documents` 坏行直接 `continue`
- 违反 AGENTS.md 9 分硬约束："不得静默吞错；边界层允许捕获、转换、记录并显式暴露失败"

**目标**：
- 底层加载函数返回 typed 结果（`(payload, errors)` 或抛 typed exception），不再静默吞
- 边界层（compile / lint / shell-summary / metrics 等）决定是否 fallback，并把 corrupt-state warning 暴露到 surfaces / receipt / log
- 至少在 `aiwiki shell-status` / `lint` 输出 corrupt-state 警告

**范围**：
- `src/aiwiki/app_state.py:279-308`
- 全部 callers（grep `load_json_document` / `load_jsonl_documents`）
- 新测试：坏 JSON / 坏 JSONL 行不再被静默吞

**不做**：扩展到 metrics / shell-summary 等已知 best-effort 层（属于 P2.1 文档化范围，不是 9 分阻塞）。

---

## 3. P1 — 可信度补强

### P1.1 — Verify 加硬阈值

**目标**：
- `scripts/verify.sh` 加 `coverage report --fail-under=<阈值>`（保守取当前 93% 减 1，即 92）
- ruff 规则扩展（至少加 `B` bugbear、`E`/`F` 已有，`UP` pyupgrade、`SIM` simplify）若不会引入大面积新告警

**范围**：`scripts/verify.sh`、`pyproject.toml`

**成功标准**：本地 `bash scripts/verify.sh` 仍 pass，且 coverage 跌破阈值会失败。

---

### P1.2 — Acceptance Failure-path 覆盖

**目标**：补受 P0.1 / P0.4 行为变更影响的 acceptance case：
- receipt write fail → status=failed
- audit append fail → compensating event
- corrupt JSON / JSONL → 显式 warning
- 至少一个并发 writer 拒绝场景（依托现有 lock）

**范围**：`tests/fixtures/acceptance/M9-*/`、`tests/test_acceptance_loop.py`

**不做**：完整 investing protocol E2E（属于 docs/Furnace Next Direction P0-P3 P2 范围，与本轮 P2 不重复）。

---

## 4. P2 — 9 分后整洁度

### P2.1 — Best-effort 策略统一文档

**目标**：在 `docs/Furnace Agent Architecture.md` 或独立文档中添加 "Best-effort surfaces" 一节，列出每个 best-effort 路径：触发条件、返回形态、可见位置、何时升级为错误。

**范围**：metrics_io、shell-summary、preview 渲染等当前显式 best-effort 的入口。

---

### P2.2 — README 模块图更新

**问题**：`README.md:322-344` 模块图已落后于实际 `compile/`、`execution/`、`runner/`、`signals/`、`planner/` 子包结构。

**目标**：把模块图刷新为真实 owner map，删除已废弃 / 重命名条目。

---

## 5. 执行顺序与依赖

```
P0.3 (active contract 物化)
 └── 必须先做：让 harness 后续 milestone 有 SoT 可读
P0.1 (receipt 硬边界)
 ├── 独立做
 └── 影响 P1.2 acceptance fixture 设计
P0.2 (scoped lane)
 └── 独立做
P0.4 (静默吞错)
 └── 独立做，但影响 P1.2 corrupt-state acceptance
P1.1 (verify 阈值)
 └── 必须在 P0 全部完成后做（否则阈值会拉警报）
P1.2 (acceptance failure-path)
 └── 依赖 P0.1 / P0.4 行为变更
P2.1 / P2.2
 └── 整洁度，独立做
```

**推荐顺序**：P0.3 → P0.1 → P0.2 → P0.4 → P1.1 → P1.2 → P2.1 → P2.2

---

## 6. 非目标（明确不做）

- 跨 process 分布式事务 / hosted service / multi-user sync / fine-tuning（沿用 SoT 非目标列表）
- planner / heavy / light / L3 partial → fully realized：属于 SoT 后续 contract，不在 9 分 gate 内
- 完整 incremental scoped compile：成本不匹配；本轮只做"名实一致"
- 任何为旧实现兜底的 shim：重构阶段直接最优解
- 大模块拆分（`app_compile.py` / `runner/alchemy.py` / `app_surfaces.py` 进一步切）：oracle 列为 P1 但属于"整洁度"而非"可信度补强"，本轮不强求；保留为 P2 后续候选

---

## 7. 闭环规约（沿用本世代）

- 每个 P/M 走 harness：`run_plan.sh` 自动物化 → 实现 → `bash scripts/verify.sh` → 归档 contract → 标记 done → 推进下一个
- ask_policy = blockers-only
- execution_mode = autonomous-closed-loop
- stop lines：连续 3 轮 verify 失败 / acceptance golden 大面积漂移（>20%）/ 触动非目标边界 / 必须破坏 public CLI surface 才能继续 → 升级
- 完成全部 P0..P2 后，由 oracle 复评，目标 ≥ 9.0
