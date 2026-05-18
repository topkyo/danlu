# B — Slimdown Plan 下一轮目标推演（AOS-005 候选）

> 只读推演。基于 C 文档（AOS-004 翻盘缺口）和 D 文档（ROI 排序）的结论。
> SoT：`docs/Furnace Agent OS Slimdown Plan.md`、`docs/Furnace Next Direction Post-P4.md`。

## 1. 推演前提

AOS-001~004 全部完成。AOS-004 跑出 `not-yet`，唯一缺口是 `trace_provenance_backed_compounding_sample`。

下一轮（暂称 AOS-005）有两个互相独立的候选方向：

- **AOS-005a — 受控的 hub/facade 削薄**：把 D 文档识别出的 ROI ≥ 12 的 4 个候选落地。
- **AOS-005b — LLM backend 收敛**：从 8 个 backend 砍到 dogfood 实际使用的 2-3 个。

两个方向都有合理性。本文档分析"先做哪个"。

## 2. AOS-005a — Hub/Facade 削薄

### 范围
基于 D 文档 ROI Top 4：

1. `app.py` (554 行) — 整模块 facade，下线
2. `app_content.py` (262 行) — facade，下线
3. `app_memory_surfaces.py` (77 行) — facade，下线
4. `app_surfaces.py` (1846 行 / 9 decl) — 巨函数级拆分

### 预期收益
- 减少 ~900 行纯 re-export 噪音
- 消除 facade-on-facade 路径
- 让 `aiwiki.content.* / aiwiki.memory.* / aiwiki.compile.*` 成为唯一 owner

### 风险
- **中等**。tests 中大量 `patch('aiwiki.app.<name>')` 需要同步改 patch target——这是 AOS-003 当时选择保守路线的根本原因。
- 需要先做 `grep -r "from aiwiki\.app\b\|patch('aiwiki\.app\." tests src` 统计真实调用面。

### 前置条件
- 已有 92% coverage + 2200+ unit tests + 17 acceptance，足以兜底
- AOS-003 已经成功下线 2 个 private re-export，证明工具链可行

### 时间估算
- 调用面调查：1 day
- 4 个候选分批迁移 + tests 同步：3-5 day
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
| 对 acceptance 风险 | 中（tests 大量 patch）| 低（backend 是 plug-in 结构）|
| 对用户的可见度 | 几乎不可见 | 可见（CLI options 变化）|
| 是否触碰 freeze ledger | ❌ 不触碰 | ⚠️ 触碰"不新增 backend"，但反向（删除）应该允许，需 plan 明确 |
| 验证难度 | 中（test patch target 改造）| 低（probe + integration test）|

### 推荐：**先 AOS-005a，后 AOS-005b**

理由：

1. **AOS-005a 是 AOS-003 的自然延续**——AOS-003 当时已经识别出这些 facade，只是出于保守只动了 2 个 private symbol。现在有 AOS-004 的数据基线和 92% coverage 兜底，可以推进剩余 ROI Top 4。

2. **AOS-005a 风险更可控**。facade 下线是机械的 import 迁移，不改 runtime 行为；backend 删除会改 CLI 选项面，需要 deprecation 周期。

3. **AOS-005b 真实收益依赖使用率数据**。在没有跑统计前推进 b，可能误删某个 dogfood 中真正在用的 backend。

4. **AOS-005a 完成后，`src/aiwiki/` 顶层文件数会从 19 个降到 16 个**，对新 contributor / agent review 的认知负担直接下降。

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
  - aiwiki.app facade module retired (file deleted or reduced to deprecation stub)
  - aiwiki.app_content facade module retired
  - aiwiki.app_memory_surfaces facade module retired
  - aiwiki.app_surfaces 拆分至少 3 个内聚 sub-render helper（同文件内或独立 module）
  - tests 中所有 patch('aiwiki.app.<name>') / patch('aiwiki.app_content.<name>') 同步迁移
  - 2200+ unit tests 全 PASS，coverage 不降
  - 17+ acceptance 全 PASS
  - bash scripts/verify.sh PASS
  - closed_loop PASS

out_of_scope:
  - app_protocol / app_lifecycle / drop / app_state 不动（D 文档 ROI < 12）
  - LLM backend 不动（留给 AOS-005b）
  - 新增任何 facade / re-export 层
  - 改 CLI / Product Shell 任何 surface
```

## 6. 单句结论

> **AOS-005 应该先做 hub/facade 削薄（AOS-005a），把 D 文档 ROI Top 4 的 ~900 行 facade 噪音清掉，并对 `app_surfaces.py` 1846 行做函数级拆分降低复杂度；backend 收敛（AOS-005b）等使用率统计跑出来再决定。同时 AOS-004 的翻盘（C 文档）应并行推进，不阻塞 AOS-005。**

## 7. 触发条件

启动 AOS-005a 的前置 gate：
- [ ] AOS-004 verdict 已经跑过至少 1 次（即使是 `not-yet`），证明 dogfood baseline 还活着
- [ ] `bash scripts/verify.sh` 当前 PASS
- [ ] 当前没有在飞 milestone（避免并行 plan handoff）
- [ ] 至少 1 轮 qa-review approve 本 plan
