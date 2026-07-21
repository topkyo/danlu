# Report Provenance Scrub + gc-orphans Implementation Plan

> **For agentic workers:** Load `executing-plans`. Then review + multi-agent score. Checkboxes track progress.

**Goal:** 落地已批 KISS spec `docs/specs/2026-07-20-report-delete-provenance-gc.md` 剩余两项（①′ HTML 停写已完成）。  
**Architecture:** compile 被动 scrub + 单一 `advanced gc-orphans`；计数进 shell-summary；不隐式 compile、不级联删报告默认。  
**Tech stack:** Python 3.10+ stdlib；acceptance fixture。

---

## File structure

| Path | Responsibility |
|------|----------------|
| Create `src/aiwiki/lifecycle/provenance_scrub.py` | 共享：死 report 路径检测、ok/degraded/broken、改写 FM |
| Create `src/aiwiki/compile/provenance_step.py` | compile phase：扫 judgments/derived/elixirs，写 status + 计数到 context |
| Create `src/aiwiki/execution/gc_orphans.py` | dry-run/apply：broken(+force-degraded)、noise-concepts、misdrops + receipt |
| Modify `src/aiwiki/compile/pipeline.py` | content → **provenance** → runtime |
| Modify `src/aiwiki/compile/context.py` | `provenance_degraded` / `provenance_broken` ints |
| Modify `src/aiwiki/app_shell/summary.py` | `review_backlog_counts` 合并两计数 |
| Modify `src/aiwiki/cli/parsers.py` + `dispatch.py` + `dispatch_helpers.py` | 注册 `gc-orphans` |
| Modify `src/aiwiki/protocol/templates.py` | graph-view 文案若未齐则补一句 |
| Modify `tests/test_acceptance_loop.py` + fixture | spec 验收 1–4 |

---

### Task 1: Provenance scrub library + compile step

**Depends on:** none

- [x] 实现 `lifecycle/provenance_scrub.py`：剥离不存在的 `output/reports/...`；设 `provenance_status`
- [x] 实现 `compile/provenance_step.py`；接入 pipeline（content 后、runtime 前）
- [x] context 计数；`build_shell_summary` → `review_backlog_counts.provenance_degraded|broken`
- [x] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(compile): scrub dead report provenance and mark status`

---

### Task 2: `advanced gc-orphans` CLI

**Depends on:** Task 1（读 `provenance_status` / 可复用 scrub helpers）

- [x] `execution/gc_orphans.py`：默认 dry-run；`--apply` + receipt；flags 按 spec
- [x] noise：词表 ∪ singleton；白名单 hub；misdrops：vphone 指纹
- [x] parsers/dispatch 接线
- [x] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cli): add advanced gc-orphans dry-run/apply`

---

### Task 3: Acceptance + graph-view 文案 + docs 指针

**Depends on:** Task 1, Task 2

- [x] acceptance：broken / degraded / GC force-degraded / noise+misdrop（可合并 1–2 fixture）
- [x] 确认 graph-view ①′ 文案；DEVELOPER/USER 一句指针可选
- [x] **Verify:** `bash scripts/verify.sh acceptance` 然后 `all`

**Commit:** `test+docs: provenance scrub and gc-orphans acceptance`

---

### Task 4: Dogfood 清炉（可选、需 vault）

**Depends on:** Task 3

- [ ] 对 iCloud「炼丹炉」：`compile` → `gc-orphans … --dry-run` → 用户确认后 `--apply` → `compile`
- [ ] 若未授权写 vault：只在报告里给命令，不自动 `--apply`

---

## Final verify

`bash scripts/verify.sh all`

## Done when

- 删报告后 FM 无死 `output/reports` 路径；status 正确  
- 一个 `gc-orphans` 能清 broken / force-degraded / noise / misdrops  
- HTML 仍非交付增强；无新 Shell GC UI  
- review 无 Critical；多 agent 审计打分落地  
