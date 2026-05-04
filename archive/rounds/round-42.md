# Round 42 — Batch Review Hint Surface

status: 完成
commit: 

Round 42 — Batch Review Hint Surface — 完成
- **目的**: 把 review-queue 同 kind ≥3 候选的批量入口（`review-page --all-pending` / `review-action --all-pending --kind <kind>` / `apply-action --all-accepted-low-risk`）surface 到 `today` 与 `shell-status` 的 `suggested_next_actions`，让用户从首屏一条命令完成 closure，符合 §1.1 用户面契约「sensible default 替用户做掉」
- **提交基线**:
  - `5dbfdef`（Round 40 baseline）
- **实现内容**:
  - `src/aiwiki/app_shell/surfaces.py` 新增 `_BATCH_HINT_THRESHOLD=3` / `_BATCH_HINT_MAX=3` 模块常量 + `_collect_batch_hints(review_controls, execution_controls)` helper
  - helper 按 `page.kind`、`(action.kind, execution_band='review-first', status='proposed')`、`can_apply=true` 三类聚合；分别 emit `review-page --all-pending`、`review-action --all-pending --kind <kind> --status accepted`、`apply-action --all-accepted-low-risk --dry-run` batch hint
  - `shell_suggested_next_actions` 末尾把 batch hints 前置，并通过 `hint_commands` filter 去掉与 batch 同命令的单条 hint，整体 surface 上限仍 8；dashboard `[:6]` 自然带上前置 batch hint
  - 命令 string 全部是已存在 CLI 形式，未引入新 flag、新 schema 或新 mutation 路径
  - 阈值 3 写死在模块常量；不暴露 env override（contract Constraints）
- **测试**:
  - `tests/test_app_shell_surfaces_batch_hints.py` 新增 7 个 unit test：
    - `test_batch_hint_emits_for_pages_at_threshold`
    - `test_batch_hint_skips_pages_below_threshold`
    - `test_batch_hint_emits_per_action_kind_when_review_first_proposed`
    - `test_batch_hint_ignores_non_review_first_or_non_proposed_actions`
    - `test_batch_hint_emits_apply_when_can_apply_meets_threshold`
    - `test_shell_suggested_next_actions_prepends_batch_hints_and_dedupes_singletons`
    - `test_shell_suggested_next_actions_falls_back_to_singletons_when_no_batch`
  - 全部 pass；`tests/test_app.py + test_today_feed.py + test_cli.py + test_app_shell_summary.py` 422/422 回归通过
- **dogfood 验证**:
  - dogfood vault `today --json` 与 `shell-status --json` 现在 surface 3 条 batch hints：
    - `批量审阅 9 个待审 decision/judgment 页` → `review-page --all-pending`
    - `批量审阅 8 个 add-source-concept-link 候选` → `review-action --all-pending --kind add-source-concept-link --status accepted`
    - `批量审阅 6 个 split-overloaded-concept 候选` → `review-action --all-pending --kind split-overloaded-concept --status accepted`
  - 23 个候选被 3 个 batch 入口覆盖；单条 hint 仍保留 5 条作为兜底，命令未重复
  - dashboard `suggested_next_actions[:6]` 自然带上 3 batch + 3 single
- **验证**:
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1539 unit + 13 acceptance pass，coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；本轮 patch 仅触 `app_shell/surfaces.py` 与新增 test，无独立 reviewer session
- **当前评估 / 终局贡献**:
  - 已对终局对比表中"批量入口 surface 到 today"差距（Round 40 列出）形成可量化收口：用户首屏从「逐条 review-page / review-action」变为「3 条 batch + 5 条单条」
  - 未触动 §3 不变量（deterministic baseline、receipt/audit 闭环、single writer 都没变）；不静默触发 batch（仍需人工复制 cmd 跑），符合 L2 显式 gate
  - 终局形态依赖的「review_closure_rate 多周稳定」需要时间累积；本轮把首屏 UX 收敛对其有正面贡献，但本身不能替代时间常量
- **监控**: watcher / nightly timer 闭环结束后已恢复 active
