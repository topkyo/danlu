# Codex-Goal 质保循环 × 金丹/Nightly/治理成熟证明（2026-07-24）

> **For agentic workers:** 本切片把 `raw/inbox/codex-goal.md` 的五阶段质保循环收窄到 **金丹 + nightly + 治理 operator 面**；不做全 app 功能表。  
> 与工程四 Lane 验收并行：`docs/plans/2026-07-24-multi-agent-acceptance-loop.md`。

**Goal:** 用可重复的「故事表 → 测 → 记缺陷 → 修 → 再测」把金丹链与 nightly/治理从「机制在、settled 空」推到可审计成熟证明。  
**Vault:** `/Users/ht/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉`  
**Baseline:** `/tmp/furnace-acceptance-2026-07-24/maturity-baseline.md`

---

## 为何是多轮 dogfood（不是只靠 verify）

| 门 | 能证明什么 | 不能代替 |
|----|------------|----------|
| Local Eng (`verify.sh`) | 契约不回归 | live vault 状态、金丹 settled 真实性 |
| Shell CDP | 入口 UX | file-back / alchemy / nightly 副作用链 |
| **多轮 Dogfood（本切片）** | 真 vault 边界 + 金丹/治理闭环 | 商业 EULA/PyPI |
| Docs/Commercial | 可售叙事 | runtime 成熟 |

**结论：** 推进金丹/nightly/全治理成熟证明 = **以 codex-goal 循环驱动的多轮 dogfood（含边界条件）**，每轮仍用 A–D 四 Lane 收口；不是换一套流程，而是把 C 泳道加深到金丹链。

---

## Codex-Goal 五阶段（本切片映射）

| Phase | Codex-Goal | 本切片动作 |
|-------|------------|------------|
| 1 发现 | Feature ID + User Story | 下表 FEAT-ELX / NIT / GOV（冻结范围） |
| 2 用例 | happy / error / boundary | 每 FEAT ≥1 套；写入本文件 Test Cases |
| 3 执行 | 跑测 + Defect 表 | `/tmp/furnace-maturity-YYYY-MM-DD/` + vault 标签 `【maturity-…】` |
| 4 修复 | 最小安全修 + 本地 verify | 修后只重跑失败故事 + 对应 Lane |
| 5 回归 | 全故事再测 | Round N 绿后才抬 Scorecard Live Dogfood 叙事 |

退出（本切片）：settled `wiki/elixirs/` ≥1；promote→revert 可审计；nightly 近 3 日 success 仍绿；compound_suggest 至少一次可观察（或记为 known not-yet + 根因）。

---

## Feature 表（SoT，Phase 1 冻结）

| Feature ID | Name | User Story | Expected Behaviour | Edge Cases | Status | Defects | Last Tested |
|------------|------|------------|--------------------|------------|--------|---------|-------------|
| FEAT-ELX-01 | Ask→报告 | 用户提问得到可打开报告 | `output/reports/*.md` + receipt；`material_refs` 可审计 | 空问、无 LLM、sticky 追问 | **pass-r1** | 0 | 2026-07-24 |
| FEAT-ELX-02 | file-back | 从报告沉淀 judgment | `wiki/judgments/*.md` + file-back receipt | 重复 file-back、坏路径 | **pass-r3** | 0 (R2-01 fixed) | 2026-07-24 |
| FEAT-ELX-03 | review-page | 人工确认 judgment | status→confirmed；可追溯 | 非法状态迁移 | **pass-r1+r3** | 0 | 2026-07-24 |
| FEAT-ELX-04 | alchemy 全链 | start→distill→finalize→promote | settled 页进 `wiki/elixirs/`；promote receipt | staging 脏、gc 后断裂 | **pass-r1** | 1 (DEF-R1-02) | 2026-07-24 |
| FEAT-ELX-05 | alchemy revert | promote 可回滚 | settled→candidate；receipt | 无可 revert 时 fail-closed | **pass-r1** | 0 | 2026-07-24 |
| FEAT-NIT-01 | nightly 健康 | 无人值守维护 | run-nightly success；lint 无 error | watch 与 compile 并发 | **pass-r1** | 0 | 2026-07-24 |
| FEAT-GOV-01 | compound_suggest | Today 出现沉淀/凝丹 | shell-summary `compound_suggest` 可点 | 无 settled 时不可用 | **pass-r3** | 0 (R1-03 closed) | 2026-07-24 |
| FEAT-GOV-02 | Shell 再生成发现性 | Today 报告卡可再生成/编辑 | 气泡隐藏后卡上仍有 CTA | retryArgs 空时 sticky 回退 | **pass-r2-partial** | 0 | 2026-07-24 CDP |

### Round 2（边界）— 已执行 2026-07-24

证据：`/tmp/furnace-maturity-2026-07-24/round-2.md`

- [x] 坏路径 file-back / 不存在 promote / 不存在 revert
- [x] 重复 file-back（暴露 DEF-R2-01）
- [x] sticky 追问 + 同 corpus 二轮 ask → compound_suggest 点亮
- [x] Today 卡「引用此报告追问」+ 沉淀 CTA（CDP；插件需 reload）
- [x] DEF-R2-01 修复（Round 3 已合）

### Round 3（复利 + 修债）— 已执行 2026-07-24

证据：`/tmp/furnace-maturity-2026-07-24/round-3.md`

- [x] 修 DEF-R2-01（重复 file-back 保留 judgment/`derived` 锚点）
- [x] acceptance **18** + dogfood 重复 file-back 回归
- [x] FEAT-GOV-01 compound_suggest 回归；CDP 点击「沉淀」
- [x] 非法 review-page fail-closed
- [ ] 历史 orphan elixir 自动 heal（won't-fix；已有替代 settled）

---

## 硬规则

1. Ask 带 `【maturity-YYYY-MM-DD】` 标签。
2. vault 有 `watch` 时不并行 `compile` / 大范围 `run-nightly`（除非单测 nightly 故事）。
3. 不自动 `gc-orphans --apply`；不宣称 AgentOS 9 live。
4. 每轮写 `/tmp/furnace-maturity-YYYY-MM-DD/round-N.md`。

---

## 与「只狂测边界」的关系

- **要**：多轮 dogfood，每轮含快乐路径 + 若干边界（Phase 2/3）。
- **不要**：无 Feature 表的随机点测；或只跑 verify 就宣称金丹成熟。
