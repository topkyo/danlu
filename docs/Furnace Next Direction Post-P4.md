# 炼丹炉 Next Direction — Post-P4 / Post-Round 52

> **当前有效结论（2026-05-20）**：AGOS-9 路线已启动；评分 SoT 见 [AGOS-9-Scorecard.md](./AGOS-9-Scorecard.md)。**live dogfood** 在清仓 vault 上需重新建立 proof（见 AGOS-002）；历史 2026-05-13~19 dogfood/P1 pass 以 git/`PROGRESS.md` 为 `historical` 证据。下文 D 系列与 gap 表保留方向上下文，执行以 `.codex/plans/active.md` / AGOS milestones 为准。

> 生成时间：2026-04-30，承接 Round 52 收口（commit `6b0770a` Relationship Graph UI Polish）。
> 来源：基于全量 SoT 重新评估（`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md` + `docs/Furnace Product Shell.md`）+ git log + 代码实测校准实际落地状态。
> 性质：**方向决策**，不是路线图；具体 milestone 走 `.codex/contracts/active.md` + harness 流程。
> SoT 关系：补丁历史现已归档到 `docs/archive/Furnace Next Direction P0-P3.md` 与 `docs/archive/Furnace Next Direction P4.md`，反映 P0/P1/P3/P4-1~15 已落地后的剩余事实 gap。

> **二次校准（2026-04-30 写完 D-1 后）**：初次评估把 P0 / P1 / P3 / 部分 P4 都误列为 gap，实测后发现：
>
> - P0 today 信号融合（counter-evidence / drift / metrics_history / agent_loop）已通过 Round 5/21/27/45 + M8.1 落地（`PROGRESS.md` line 1253）
> - P1 trace evidence chain 已通过 M8.2 落地（line 1235）
> - P3 drift / aging signal 已通过 M8.3 落地（line 1209）：`drift_scan` 把 `judgment-stale / evidence-changed / elixir-dependency-break` 写入 `aging_state.warnings` → `shell_drift_warnings()` 合并 → `today_feed._build_drift_entries()` 浮出 today
> - P4-1/2/3/4/5/6/9/11/15 全部已 close
>
> 因此本文档下面 **D-3 / D-6 已删除**，剩余真实 gap 重新编号。

> **三次校准（2026-05-20）**：git/`PROGRESS.md` 复核确认，2026-05-13~15 的三天 unattended dogfood maturity 已真实 `PASS`，2026-05-19 的 P1 dogfood compounding proof 也已补齐 `knowledge_compounding_proof.status=pass` 与非空 `compounding_sample`。当前 `/home/tim/danlu/炼丹炉` 已被清仓恢复为干净初始 vault，所以旧 `output/control/maturity-gate/*` receipt/snapshot 文件不再存在；当前 summarize 读到 `0 receipts/not-yet` 只反映清仓后的文件状态，不推翻历史 pass。本文后续凡提到 AOS-004 `not-yet`，均应按历史阶段性缺口理解，已被 2026-05-19 P1 收口 supersede。

---

## 0. 视角校准

| 状态 | 内容 |
|---|---|
| 已落地 | M0-M9 / M-PS / M-UX / M6 系列 / Round 1-52；P0 信号融合（Round 5/21/27/45）；P4-1~15 dogfood F-fix；user-surface roadmap 全部 |
| 当前评分基线 | oracle ≥ 8.6；coverage 92%；1500+ unit tests / 13 acceptance |
| 真实 critical path | 不再是 “机制完备”；是 **“实战 dogfood 是否能跑通端到端复利”** |

**判断标准变化**：从 “补 9.5 dogfood 阻塞” 变成 “证明炼丹炉对单人投资/研究真的产生知识复利”。这需要的不是更多机制，是少数几条端到端 fixture / acceptance + 长尾保养。

---

## 1. 真实 Gap（评估 2026-04-30 二次校准后）

| 维度 | 当前事实 | Gap | 优先级 |
|---|---|---|---|
| 金丹 Stage 3 复利 | DAG / wiki/derived 锚定 / counter_evidence gate 已强制；unit test 覆盖 `include_elixir_ids` 拒绝 candidate（`tests/test_alchemy.py:376`） | **acceptance fixture 缺 “新丹 derived_from 含旧丹 + wiki/derived anchor 同时通过校验 + trace 反查复利链” 的端到端** | P1 |
| Investing protocol 端到端 | 5 protocol schema 全在；research / general / ops 有 dogfood receipt | **investing 路径从未跑通过完整 drop 研报 → judgment → distill → ask 复用金丹 → L3 改 prompt** | P1（外部 LLM 依赖） |
| LLM backend 可用性 | P4-1 系列已落 4-state probe + receipt 注入 + preflight warning | **当前真实可跑的本地 backend 仍只有 nvidia-nim-api**；codex-cli/gpt-5.x 与 copilot-cli 在 dogfood receipt 中仍间歇失败 | P2（外部依赖） |
| PROGRESS / plans 体量 | 287KB / 6013 行 | pre-Round 1 内容（M0-M9 / M-PS / M-UX / M6 / P0~P4）与当前世代失联；`.codex/plans/active.md` 含废弃 EP-001~021 | P2 |
| Signal 闭环“执行驱动” | observe-only / execute-mode 都已落地；scheduler 可消费 deterministic primitives | **signal severity / budget_hint 实质参与 routing 决策的密度仍低**；典型 “生产 signal 但无下游 lane apply” 局面 | P3（待 P2 dogfood 后再判断是否值得动） |

> **2026-05-26 校准**：D-3 金丹 Stage-3 compounding acceptance 已存在于 `tests/fixtures/acceptance/D3/case_elixir_stage3_compounding/`，覆盖 `alchemy-start → distill → finalize → promote → trace up`；上表中的 D-3 gap 是历史缺口。当前剩余重点转为 release proof 收紧、signal 默认 light-lane 闭环和文档口径收敛。

> **AOS-004 proof gate update（2026-05-18）**：`scripts/dogfood_maturity_gate.py` 已新增 `knowledge_compounding_proof`，把复利证明拆成可复算指标与 trace/provenance-backed sample。首版 gate 保守：真实 dogfood vault 当前能复算出 `raw_to_wiki_count`、judgment/elixir reuse、`output_file_back_rate`、receipt-backed actions 与 human-required exceptions，但缺少能把 output reuse 精确回链到同一 artifact receipt 的 sample，因此输出 `not-yet` 而不是 pass。这是符合本文 critical path 的校准：机制存在不等于复利已被证明，后续应优先补 trace-backed dogfood sample/acceptance，而不是继续堆自治机制。

> **AOS-004 closure update（2026-05-19/20 复核）**：上述 2026-05-18 `not-yet` 是首版 gate 的诚实中间态，已在 2026-05-19 P1 dogfood compounding proof 中补齐。实现通过 `ask_question()`/`run-ask` 保留 runtime-owned curated judgment refs 到 output frontmatter，并用成功 execution receipt 精确匹配同一 artifact；真实 dogfood sample 写入 `output/control/maturity-gate/snapshot-20260518T220253Z.json`，`knowledge_compounding_proof.status=pass`、`compounding_sample != null`。当前 clean dogfood vault 不再保留该 snapshot；历史 pass 以 git/`PROGRESS.md` 固化记录为准。

不再列入本轮的（已落地或非目标）：
- ~~Today actionability / 信号融合~~ → P0 / M8.1 已 close（`PROGRESS.md` line 1253）
- ~~Trace concept layer~~ → P4-3 已 close
- ~~LLM compatibility gate~~ → P4-1 系列已 close
- ~~LLM observability receipt~~ → P4-2 已 close
- ~~Drift / aging signal 浮出~~ → P3 / M8.3 已 close（`elixir_dependency_break` 通过 `aging_state.warnings` → `shell_drift_warnings` → `today` 已通）
- HTML / Web UI / multi-user / hosted service / fine-tuning（沿用 SoT 非目标）

---

## 2. D 系列方向清单

### D-1 Direction SoT（本文档）

**目的**：把当前 gap 与下一阶段方向固化为 SoT；旧 P0-P3 / P4 文档不删除（保留为 partial-coverage 历史参考），但执行优先序以本文档为准。

**完成判据**：本文件落盘 + `.codex/plans/active.md` 末尾追加 D 系列 milestone index。

**Size**：S。**状态**：本轮在做。

---

### D-2 Active Files Hygiene

**问题**：`PROGRESS.md` 287KB / `.codex/plans/active.md` 6013 行包含废弃 EP-001~021 与 pre-Round 1 全部世代历史，污染 active surface，搜索/上手成本高。

**目标**：
- 把 `PROGRESS.md` 中 **pre-Round 1**（即旧 EP-029 / M0–M9 / M-PS / M-UX / M6 / P4-1~15 收口段）切到 `archive/PROGRESS-pre-round1.md`（项目根新建 `archive/`）。
- 把 `.codex/plans/active.md` 中的 **EP-001~EP-021 / EP-PLAN-001 / EP-002~M2.11 / M3.x / M5.x / M9-Px** 旧 milestone 切到 `.codex/plans/archive/pre-furnace-and-furnace-rollout.md`。
- `PROGRESS.md` 与 `.codex/plans/active.md` 只保留 Round 1+ / D 系列 / 当前 active 内容。
- 在两文件顶部加 archive 索引指针，git 历史是唯一不可抹除审计源。

**Size**：S。**依赖**：D-1。**Stop**：不动 git history；不删旧文件；不破坏 cross-file ref。

**完成判据**：
- `PROGRESS.md` ≤ 30KB；`.codex/plans/active.md` ≤ 60KB
- `bash scripts/verify.sh` pass（不应受影响）
- `archive/PROGRESS-pre-round1.md` 与 `.codex/plans/archive/pre-furnace-and-furnace-rollout.md` 存在
- 本文件指向 archive 的 link 可用

---

### D-3 Elixir Stage-3 Compounding Acceptance

**问题**：金丹 thesis 阶段 3 “新丹引用旧丹 + 锚定 wiki/derived 底层证据” 在 unit test 已覆盖（`tests/test_alchemy.py:376` 验证 `include_elixir_ids` 拒绝 candidate），但 **acceptance 缺一份端到端 fixture**（promote 旧丹 → 创建新丹引用旧丹 → DAG/anchor 校验通过 → promote 新丹 → trace 反查能看到引用链）。

**目标（最小切片）**：
1. 新 acceptance case `tests/fixtures/acceptance/D3/case_elixir_stage3_compounding/`：
   - input: 已有 settled `elixir-old`，corpus 含 `wiki/derived/...md` anchor
   - flow: alchemy-start → distill (含 `--include-elixir elixir-old`) → finalize → promote
   - expected: 新 elixir frontmatter 通过 DAG / wiki/derived anchor / counter_evidence gate；promote receipt clean；trace `elixir-new --depth 3` 能向上看到 `elixir-old`
2. 不引入新 CLI 命令；只用现有 `alchemy-start/distill/finalize/promote/alchemy-revert` chain。

**Size**：M。**依赖**：D-1。
**Stop**：不改 elixir schema；不放松 DAG / anchor / counter_evidence gate。

**完成判据**：
- 新 acceptance 通过
- `bash scripts/run_acceptance.sh -v` 显示 +1
- promote receipt 含 `derived_from = [elixir-old, wiki/derived/...]`
- trace 输出包含旧丹引用边

---

### D-4 Investing Dogfood Entry Contract（contract-only）

> **历史状态更新（2026-05-20）**：本节是当时的 entry contract。后续 `docs/Furnace Investing Dogfood Plan.md` 已转为 receipt index，v0/v1/v2/v2.1 investing dogfood 均已有实跑记录；这里的 `pending(blocked-on-llm)` 只保留为 P4 当时完成判据，不代表当前状态。

**问题**：5 protocol 中 `investing` 唯一未跑通端到端，是炼丹炉 thesis（“给单人投资研究做知识复利”）的 critical proof。

**目标（本文档只 contract 化，不实跑）**：
- 写一份 `docs/Furnace Investing Dogfood Plan.md`，明确：
  - 输入素材类型（A 股研报 / 美股年报 / 行业访谈纪要）
  - 6 步 flow（drop → compile → judgment → distill → ask 复用 → L3 改 prompt）
  - 验收：摩擦报告（receipt 引用）+ 至少 1 个 settled investing elixir + 至少 1 条 `investing` protocol L3 proposal
  - 显式记录 backend、cost、token usage
- **不在本 session 实跑**（依赖外部 LLM backend 可用；P4-1 receipt 已经能识别 unavailable 状态，但 codex-cli quota 仍是阻塞）。

**Size**：S（contract）；L（实跑，多 session）。
**依赖**：D-1；外部 LLM backend ready。
**Stop**：不在本 session 跑；不为 dogfood 修改 runtime 行为。

**完成判据**：
- `docs/Furnace Investing Dogfood Plan.md` 落盘
- `.codex/plans/active.md` D-4 milestone 标 `pending(blocked-on-llm)`

---

## 3. 执行顺序（本 session）

1. **D-1**（写本文档） ✓
2. **D-2**（archive 收口） — 纯文档，先收
3. **D-3**（Stage-3 compounding acceptance） — 物化为 active contract，跑实现 + verify + commit
4. **D-4**（Investing dogfood plan 文档） — 物化文档，contract 标 pending

D-3 是本 session 真正写代码 / 加 fixture 的一轮；D-2 / D-4 是文档与归档操作。

## 3.1 D 系列实际收口（2026-05-01 更新）

| ID | 状态 | commit / 落地 |
|---|---|---|
| **D-1** Direction SoT 文档 | done | commit `b880359` |
| **D-2** PROGRESS / plans archive sweep | done | commit `b880359` |
| **D-3** Stage-3 Compounding acceptance（unit-level） | done | commit `c012839` |
| **D-3 R1** Stage-3 复利 real run（dogfood vault） | done | commit `7225554`（首个跨周期复利 settled elixir）|
| **D-4** Investing Dogfood Plan contract 文档 | done | commit `20c2460` |
| **D-4 实跑 v0** Investing 协议端到端 dogfood | done | commit `65710f4`（dogfood-receipt-investing-v0） |
| **D-4 实跑 v1** PDF + 双 backend smoke | done | commit `0b4dabe`（dogfood-receipt-investing-v1） |

后续 P4-INV follow-up 也已收口（commit `0b4dabe`，Round 59）：

- **P4-INV-1** `run-compile --paths` 显式 source 过滤 — done
- **P4-INV-2** concept extractor 季度 token 噪声过滤 — done（commit `8bd33f5`）
- **P4-INV-3** investing protocol-specific judgment frontmatter slots — done
- **P4-INV-4** alchemy-finalize 强制写 protocol-aware `review_after` — done

剩余真实 gap（不在 D 系列范畴）：

- 真实投资研报 PDF 多份 dogfood（用户提供）
- 多周自然运行验证 review_after expiration 触发 drift
- copilot-cli rate limit 重置后再测能否进 fallback 池

---

## 4. 非目标（明确不做）

- 不重写 `today_feed.py` 主排序契约（KISS）。
- 不引入 `aging_state` 新字段；只消费现有 signal stream。
- 不为 D-3 引入第三方依赖。
- 不在本 session 跑 investing dogfood（外部 backend 依赖未 ready）。
- 不改 review/apply/revert/audit 状态机。
- 不破坏 9+ feasibility contract（observe-before-schedule / manual-first / scoped-only / kill-switch / no-hidden-backend / compatibility-adapters）。

---

## 5. 闭环规约

- 每个 D-x 单独物化为 `.codex/contracts/active.md`，跑 focused tests + `bash scripts/verify.sh` + dogfood-surface-check + commit + 回写 `PROGRESS.md`。
- D-3 写 fixture 的轮次按 acceptance 驱动，不放走没 fixture 锁定的行为。
- D-4 只生成文档与 contract entry，不动 src。
- watcher / nightly timer 必须在每轮结束时 active。
- ask_policy = blockers-only；execution_mode = autonomous-closed-loop。
- stop lines：连续 2 轮 verify 失败 / acceptance golden 大面积漂移（>20%）/ 触动非目标边界 → 升级。

---

## 6. SoT 引用关系

- 上层 SoT：`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md` + `docs/Furnace Product Shell.md` + `docs/Furnace Elixir.md`
- 历史方向（partial coverage，作为参考）：`docs/archive/Furnace Next Direction P0-P3.md` + `docs/archive/Furnace Next Direction P4.md`
- 执行入口：`.codex/contracts/active.md` + `.codex/plans/active.md`
- 状态文件：`PROGRESS.md`（active 世代）+ `archive/PROGRESS-pre-round1.md`（历史世代，D-2 后落地）
