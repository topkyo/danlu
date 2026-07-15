# B — Slimdown Plan 下一轮目标推演（AOS-005 候选）

> Historical: 历史分析，LOC/状态可能过期；执行以 Cleanup Plan + Scorecard 为准。
> 只读推演。基于 C 文档（AOS-004 翻盘缺口）和 D 文档（ROI 排序）的结论。
> SoT：`docs/archive/Furnace Agent OS Slimdown Plan.md`、`docs/archive/Furnace Next Direction Post-P4.md`。
> **状态更新（2026-05-20）**：本文写作时 AOS-004 仍是 `not-yet`。后续 2026-05-19 P1 dogfood compounding proof 已将 `knowledge_compounding_proof` 跑到 `pass`，并有非空 `compounding_sample`。因此本文的 AOS-005 候选分析可继续作为下一轮减法/后端收敛参考，但“不应立即启动、仍被 AOS-004 阻塞”的前提已 superseded。

## 1. 推演前提

AOS-001~003 已收口；AOS-004 的工程 gate 写作时已能跑出保守结果，但当时 active contract 仍是 `AOS-004 Knowledge compounding proof gate`，真实 dogfood verdict 仍为 `not-yet`，缺口是 `trace_provenance_backed_compounding_sample`。该缺口后来已由 2026-05-19 P1 dogfood compounding proof 补齐。

因此本文档原本只能作为 **AOS-004 收口之后** 的下一轮推演。现在 AOS-004 已历史收口，本文仍不是执行授权；真正启动 AOS-005 仍需新的 active contract。

下一轮（暂称 AOS-005）有两个互相独立的候选方向：

- **AOS-005a — 受控的 hub/facade 削薄**：把 D 文档修订后识别出的 ROI ≥ 12 候选落地，但排除 README/PROGRESS 明确要求保留的 `app.py`。
- **AOS-005b — LLM backend 收敛**：从 8 个 backend 砍到 dogfood 实际使用的 2-3 个。

两个方向都有合理性。本文档分析"先做哪个"。

## 2. AOS-005a — Hub/Facade 削薄

### 范围
基于 D 文档修订后的 ROI 候选：

1. `app_surfaces.py` (1846 行 / 9 decl) — 巨函数级拆分
2. `app_content.py` (262 行) — 调用面迁移后退役 facade
3. `app_memory_surfaces.py` (77 行) — 调用面迁移后退役 facade

明确排除：`app.py` (554 行) 是 README 承诺保留的 `aiwiki.app` 外部兼容 shim，AOS-003 审计也已判定不能删；它只能进入长期 deprecation plan，不能列入 AOS-005a delete-now。

### 预期收益
- 直接减少最多 ~339 行纯 re-export 噪音（不含 `app.py`）
- 降低 `app_surfaces.py` 的巨函数 review 复杂度
- 消除 facade-on-facade 路径
- 让 `aiwiki.content.* / aiwiki.memory.* / aiwiki.compile.*` 成为唯一 owner

### 风险
- **中等**。`app_content.py` / `app_memory_surfaces.py` 仍有 runtime/tests 调用与 patch seam，需要同步改 patch target——这是 AOS-003 当时选择保守路线的根本原因。
- 需要先做 `grep -r "app_content\|app_memory_surfaces\|app_surfaces" src tests scripts` 统计真实调用面。

### 前置条件
- 已有 92% coverage + 2200+ unit tests + 17 acceptance，足以兜底
- AOS-003 已经成功下线 2 个 private re-export，证明工具链可行

### 时间估算
- 调用面调查：1 day
- 3 个候选分批迁移 + tests 同步：3-5 day
- closed-loop + qa-review：1-2 day
- **总计：~1 周**

## 3. AOS-005b — LLM Backend 收敛

### 范围
当前 8 个 backend：`codex-cli / copilot-cli / claude-cli / opencode-api / nvidia-nim-api / openrouter-api / anthropic-api / openai-api`。

实际单人 dogfood 使用面（基于近期 receipt 推测）：
- 主用：`nvidia-nim-api`（免费/低成本，长文本）
- 副用：`opencode-api`（当前 agent session 自带）
- 偶用：`anthropic-api` / `openai-api`（特定场景）
- **死代码嫌疑**：`codex-cli`（quota 不稳）、`copilot-cli`（seat 问题）、`claude-cli`、`openrouter-api`

### 预期收益
- `llm.py` 减约 30-50%（1016 行 → ~500-700 行）
- probe 失败/健康检查噪音减少
- 配置面简化（`config.py` 中的 backend 选项减少）

### 风险
- **较高**。删 backend 会影响 dogfood vault 中可能仍在用的历史 receipt 回放。
- 删 backend 不是 facade 下线，会破坏向后兼容；需要 deprecation path（先 warn，再 hide，最后 delete）。
- 用户选择面变窄可能影响应急场景。

### 前置条件
- 需要先统计 dogfood vault 近 3 个月 `execution-receipts.jsonl` 各 backend 的实际使用比例
- 若某 backend 使用率 < 1%，才有删除justification

### 时间估算
- backend 使用率统计：1 day
- 选择 deprecation candidates + warn 期：1 day
- 实际下线：2-3 day
- **总计：~1 周**

## 4. 应该先做哪个？

### 决策矩阵

| 维度 | AOS-005a (Hub 削薄) | AOS-005b (Backend 收敛) |
|---|---|---|
| 与 AOS-004 是否关联 | ❌ 独立 | ❌ 独立 |
| 可逆性 | ✅ facade 下线易回滚 | ⚠️ 删 backend 难回滚 |
| 对 acceptance 风险 | 中（tests/runtime patch seam）| 中-高（backend option 与历史 receipt 兼容面）|
| 对用户的可见度 | 几乎不可见 | 可见（CLI options 变化）|
| 是否触碰 freeze ledger | ❌ 不触碰 | ⚠️ 触碰"不新增 backend"，但反向（删除）应该允许，需 plan 明确 |
| 验证难度 | 中（test patch target 改造）| 中（probe + integration + deprecation 兼容）|

### 推荐：**先 AOS-005a，后 AOS-005b**

理由：

1. **AOS-005a 是 AOS-003 的自然延续**——AOS-003 当时已经识别出这些 facade，只是出于保守只动了 2 个 private symbol。AOS-004 收口后，可以推进剩余高 ROI 候选，但不应删除 `app.py`。

2. **AOS-005a 风险更可控**。facade 下线是机械的 import 迁移，不改 runtime 行为；backend 删除会改 CLI 选项面，需要 deprecation 周期。

3. **AOS-005b 真实收益依赖使用率数据**。在没有跑统计前推进 b，可能误删某个 dogfood 中真正在用的 backend。

4. **AOS-005a 完成后，`src/aiwiki/` 顶层兼容 facade 会减少，但主要收益是 review 复杂度下降**，不是大规模 LoC 删除。

## 5. AOS-005a 提案 milestone 草案

> 仅推演，不作为正式 plan。

```yaml
title: Facade retirement and surface ownership consolidation
status: proposed
qa-review: required
qa-runtime: required
execution_mode: autonomous-closed-loop
ask_policy: blockers-only
max_debug_rounds: 3

success_criteria:
  - aiwiki.app remains stable external compatibility shim; no deletion in this milestone
  - aiwiki.app_content facade call sites audited and migrated where safe; facade retired only if no public/test seam remains
  - aiwiki.app_memory_surfaces facade call sites audited and migrated where safe; facade retired only if no public/test seam remains
  - aiwiki.app_surfaces 拆分至少 3 个内聚 sub-render helper（同文件内或独立 module）
  - tests 中相关 patch target 同步迁移，不留下 broken compat seam
  - 2200+ unit tests 全 PASS，coverage 不降
  - 17+ acceptance 全 PASS
  - bash scripts/verify.sh PASS
  - closed_loop PASS

out_of_scope:
  - app.py / app_protocol / app_lifecycle / drop / app_state 不动
  - LLM backend 不动（留给 AOS-005b）
  - 新增任何 facade / re-export 层
  - 改 CLI / Product Shell 任何 surface
```

## 6. 单句结论

> **收口复核（2026-05-20）**：AOS-004 proof 已在 2026-05-19 P1 dogfood compounding proof 中翻为 pass，AOS-005a 也已按本建议做受控 hub/facade 削薄；本文保留为当时“为什么不越过 proof gate、为什么先做 app_surfaces/app_memory_surfaces/app_content 审计”的决策依据。后续 backend 收敛仍必须先做真实 dogfood usage telemetry，不应凭静态枚举删除 backend。

## 6.1 执行状态（2026-05-19）

AOS-005a 已按 harness 物化为受控削薄，而不是一次性删除 facade：

- `app_surfaces.py`：已抽出 `_compile_state_string_list`、`_compile_phase_lines`、`_source_link_lines`、`_concept_link_lines`，降低 `render_compile_status` 的局部 review 复杂度；同时把该文件的 owner import 从 `app_content` / `app_memory` facade 迁到直接 owner module。
- `app_memory_surfaces.py`：`src/aiwiki` 内直接 `from app_memory_surfaces import ...` runtime 依赖已清零；facade 仍保留，服务外部/public/test patch seam。
- `app_content.py`：已迁移一批 owner 明确、低风险的 runtime import；但 app shell、compile/lint legacy 面和 `content.*` 内部 patch seam 仍存在，因此本轮不退役 facade。
- `app.py`：未触碰，继续作为 README 承诺的 `aiwiki.app` external compatibility shim。

修订后的执行结论：AOS-005a 的第一段收益来自 `app_surfaces.py` review complexity 降低和 `app_memory_surfaces.py` runtime 依赖移除；`app_content.py` 仍是实际 compat/test seam facade，不能在本轮强删。

## 7. 触发条件

启动 AOS-005a 的前置 gate（历史复核）：
- [x] AOS-004 verdict 已经跑过至少 1 次，并在 2026-05-19 P1 proof 中翻为 pass。
- [x] AOS-004 active contract 已收口，未与 proof gate milestone 并行抢占。
- [x] `bash scripts/verify.sh` 在 AOS-005a 执行记录中 PASS。
- [x] AOS-005a 已按单独 active contract/harness milestone 执行。
- [x] qa-review 已 approve AOS-005a 执行结果。
