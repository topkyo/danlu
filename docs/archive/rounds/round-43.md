# Round 43 — Batch Adoption Surface UX (B + C + D)

status: 完成
commit: 

Round 43 — Batch Adoption Surface UX (B + C + D) — 完成
- **目的**: 把 Round 42 的 batch hint 从「读 cmd 字符串 → 复制粘贴」推进到三个最终形态可达入口——CLI 一键 alias（B）、Obsidian 按钮（C）、CLI 交互式 review-next（D）；不破坏 §3「Runtime 不生成语义判断」与 §8/§9 L2/L3 红线，所有写回仍由用户显式触发
- **提交基线**:
  - `8a1d28c`（Round 42 baseline）
- **Stage B — CLI `batch-review` 一键 alias（实现完成）**:
  - `src/aiwiki/cli/parsers.py` 新增 `batch-review <pages|action|apply-low-risk>` 子命令，`--note` 必填
  - `src/aiwiki/cli/dispatch.py` 新增 `_handle_batch_review_alias`：内部完全复用现有 `review_pages_batch / review_machine_memory_actions_batch / apply_machine_memory_actions_batch`，不引入新 mutation 路径
  - 写回 result 强制 stamp `triggered_by="batch-alias"` + `alias_target` + note 加 `[batch-alias]` 前缀，便于审计区分单条 vs 批量入口
  - 5 个 unit test：`note` 必填 SystemExit / `pages` 路由 / `action` `--kind` 必填 / `action` review-first 过滤 / `apply-low-risk` dry-run 路由
- **Stage C — Obsidian "Run batch" 按钮（实现完成）**:
  - `.obsidian/plugins/furnace-product-shell/src/render_primitives.js` 新增 `resolveBatchHintInvocation`：识别 `kind ∈ {batch-review, batch-apply}` + 命令字符串模式，路由到已有 `openReviewBatchSuggestionPicker / runApplyAllAcceptedLowRiskCommand` picker
  - `renderSuggestedNextActionsBlock` 在 batch hint entry 上前置渲染 `mod-cta "Run batch"` 按钮，保留 "Open" / "Copy command" 作为 fallback
  - `bash build.sh` rebuild `main.js`（7484 → 7525 lines），新 symbol 出现在 line 2645
  - 不改 picker 实现、不改 manifest 版本号；点击 button 走与终端 cmd 相同的人工最终决策路径
- **Stage D — CLI `review-next` 交互式 review workflow（实现完成）**:
  - `src/aiwiki/cli/parsers.py` 新增 `review-next` 子命令，`--limit N` (default 1) / `--non-interactive` / `--note`
  - `src/aiwiki/cli/dispatch.py` 新增 `_handle_review_next`：从 `shell_summary.review_controls.pages` 取 `can_review=true` 列表，逐条把 path/kind/reasons/default/allowed surface 到 stderr（避免污染 stdout JSON），prompt `[a]ccept / [r]eject / [t]rack / [s]kip / [q]uit`，按下后调 `review_page` 落盘 receipt，自动进下一条
  - 选择映射：`a/A → accepted`、`r/R → rejected`、`t/T → tracking`、`s/S → skip`、`q/Q → quit`；空字符串等同 `s`；未知字符 fallback 到 `default_transition`
  - `--non-interactive` 只 surface 不读 stdin、不写 receipt（CI / preview 模式）
  - 落盘 receipt 强制 stamp `triggered_by="review-next"`，note 加 `[review-next]` 前缀
  - 3 个 unit test：non-interactive 不写 / interactive 单条 accept 落盘 / quit 立即停（surfaced_count=1）
- **dogfood 端到端验证**:
  - `review-next --limit 1 --non-interactive`：成功 surface V3.6 amend decision（`triggered_by=review-next` / `non_interactive=true` / `surfaced_count=1`）
  - `batch-review action --kind monitor-bridge-concept --note ...`：正确报错 "No proposed machine-memory actions match kind='monitor-bridge-concept' execution_band='review-first'"（Round 41 已关闭 5 个 review-first candidate，剩下 19 个是 history-only）
  - `batch-review apply-low-risk --dry-run --note ...`：正确报错 "No accepted low-risk actions are ready for batch apply"（dogfood 当前没有 can_apply candidate，符合 contract）
  - 错误路径与 surface 路径都有意义、都不破坏现有状态
- **验证**:
  - `pytest tests/test_cli_batch_review_alias.py -v`：8/8 pass
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1540 unit + 13 acceptance pass，coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；本轮 patch 触 cli/parsers + cli/dispatch + 新 test file + 插件 src + 插件 main.js（build 产物），无 review/apply 状态机或 receipt schema 改动；contract sha=`37a08843`
- **L2/L3 红线复审**:
  - **runtime 静默 batch adopt = 永远禁止**（`docs/Furnace Agent Architecture.md §3 / §8 / §9`）
  - 本轮三个新入口（B alias / C button / D review-next）都是「让用户的显式触发更轻」，不是「让 runtime 自动决定」：
    - B 必填 `--note` 强制人工写下 batch 决策的语义责任
    - C button 点击 = 用户在 UI 显式 accept，等价于在 terminal 跑 cmd
    - D review-next 仍逐条让用户键入 a/r/t/s/q，未键入不落盘
  - 所有路径仍走 `review_page / review_machine_memory_actions_batch / apply_machine_memory_actions_batch` 三条已审 primitive，不引入新 mutation 路径、不绕过 receipt/audit
- **当前评估 / Round 40 终局对比表更新**:
  - Round 40 列出的「批量入口未 surface 到 today」（Round 42 已收口）+「review workflow 未做」（D 已收口最小骨架）+「按钮 vs cmd」（C 已收口）三件 UX 短板，本轮一次性物化
  - 剩余两件仍是时间常量，不是工程动作：
    - codex-cli quota ~17:10 自然恢复 + 跑剩 4 条 source summaries enrichment + judgment metadata 收敛
    - 多周自然运行下 review_closure_rate / proposal_acceptance_rate / judgment_revisit_rate 趋势观察
  - 结论：炼丹炉的「最终形态用户面 UX 骨架」本轮已收齐；下一阶段是**让骨架真正在多周自然运行下被人用、被语义债持续清掉**，不需要新工程动作
- **监控**: `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 持续 active
