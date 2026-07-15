# Round 40 — Monitoring Runtime Dogfood Assessment

status: 完成
commit: 

Round 40 — Monitoring Runtime Dogfood Assessment — 完成
- **目的**: 用户明确要求“开启监控、继续炼丹炉的运行测试、分析评估炼丹炉状态和功能、是否达到最终形态”；本轮以 `/home/tim/danlu/炼丹炉` dogfood vault 实测证据为准重新评估终局差距
- **提交基线**:
  - `832d1ad`（runtime 无变更，本轮只新增 PROGRESS / contract / dogfood receipts）
- **监控状态**（开工时已 active，本轮确认未中断）:
  - `aiwiki-watch.service` active 46+ min；命令 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active waiting；下一次触发 `2026-05-01 00:00:00 CST`
  - `/home/tim/.config/aiwiki/aiwiki-nightly.env` 已包含 `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1`
  - tmux session `danlu-dogfood` 4 panes 仍在跑 trace*；最近 file-write trace 来自 Round 39 闭环（`output/lint/lint-20260430-073439.md` / `output/control/product-shell.html` 等）
- **dogfood 运行测试（只读 + 可逆 deterministic）**:
  - `protocol-status`：active=`research`；available=`general / investing / ops / product / research`
  - `llm-check`（静态）：backend=`codex-cli`、effective_model=`gpt-5.5`、auth_mode=`cli-session`、reasoning_effort=`medium`；本轮未 `--probe`，外部 quota 阻塞既有事实未变
  - `lint`：0 errors / 91 warnings，分布以语义债为主：
    - 30×soft concept hardness（concept lifecycle hardening 未完成）
    - 8×6 = 48×judgment 缺失结构化 `counter_evidence / next_signals / invalidation_rule` metadata 与 `## Judgment / ## Signals` section、placeholder Invalidation
    - 4×source placeholder summary（外部 codex-cli quota 阻塞剩余 source summaries enrichment）
    - 5×decision metadata 缺失/placeholder（counter_evidence / next_signals / invalidation_rule / Counter Evidence / Invalidation）
    - 1×source 无 compiled concept links；2×judgment 缺 `citations`；1×judgment 缺 `citation_snapshots`
    - lint report：`output/lint/lint-20260430-082229.md`
  - `review-queue`：total=40（concept_backlog=11、counter_evidence_candidates=8、judgment_review_actions=8、l3_proposals=1、machine_memory_actions=19、review_concepts=1、revisit_concepts=10、drift=1）
  - `today --json`：仍展示“已自动维护：今日发现 27 个新变化，已静默执行 1 条维护路径”，并继续 surface 8 项 needs_review + planner-next-action 候选
  - `metrics`：provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=1
  - `shell-status`：knowledge_stats={concept_nodes:30, source_nodes:32, judgment_nodes:9, decisions:1, edge_total:292, term_index:2187}；planner={blocked:14, executed_actions:8, pending_proposals:16, unblocked:2}；llm_health.reason=`Recent run-ask succeeded.`；drift_warnings 仅 `judgment-20260428-054243-v3-6-vs-v3-5-slam-dogfood-judgment` 1 条 stale
- **unattended light maintenance 复测（本轮新跑）**:
  - `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1 ... run-nightly --compile-limit 0 --no-semantic-lint`
  - `agent_loop.mode=observe_dry_run_and_light_apply`，`auto_apply.status=applied`，`applied_count=1`，`llm_used=false`
  - 写入 receipted light primitives：
    - `output/control/execution-receipts/alchemy-light-compile-20260430082324.json`
    - `output/control/execution-receipts/alchemy-light-lint-20260430082324.json`
    - `output/control/execution-receipts/alchemy-light-nightly-20260430082325.json`
  - light nightly receipt：`scope_enforced=true`、`scope_enforcement_reason=primitive_global_only:executed_globally`、`subject_id=light:all:nightly`、覆盖 47 个 signal_id 与 30 个 source_id、`revert_supported=false`、双 trace_id 完整记录
- **验证**:
  - 干净 env（`env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`）：1532 unit + 13 acceptance pass，coverage 92%
  - 已知边界：在 shell 已 `source .envrc.dogfood` 的会话里直接跑 `bash scripts/verify.sh` 会因 `AIWIKI_LLM_BACKEND=codex-cli` 等 env 泄露导致 3 个 test 假阳性 fail（`test_drift_scan.test_evidence_drifted_emits_high_signal` / `test_evidence_unchanged_no_drift`、`test_vault.test_bootstrap_new_vault_launcher_inherits_plugin_llm_settings`）；与炼丹炉自身行为无关，记录为 dogfood envrc 的副作用
  - QA review gate `.codex/gates/qa-review.md`：本轮无代码 diff（仅 PROGRESS / contract / dogfood receipts），按 contract 允许 self-review fallback；fallback 原因：runtime 无 mutation，独立 reviewer session 不可用
- **当前评估 / 五层 + 治理 + 执行 功能状态**:
  - 五层主线（raw / wiki / machine memory / schema / outputs）：dogfood vault 上完整存在并稳定派生（30 concept + 32 source + 9 judgment + 1 decision + 8 judgment_assets + receipts）
  - 治理链（review / aging / escalation / repair / nightly）：review-queue + drift + 4 类 review backlog 全部可见；aging_summary 当前 0 escalated；nightly 既支持 deterministic 也支持 light-apply
  - 判断层（decision / judgment）：判断资产存在但 8/9 judgment 仍缺结构化 metadata，1 decision 缺反证 / next_signals / invalidation_rule，是当前最大语义债
  - 协议层（general / investing / research / product / ops）：5 协议齐备；dogfood active=research
  - 执行层（dry-run / bundle / apply / receipt / revert / audit）：light lane apply 路径已稳定 receipt 落盘；receipt 含 scope enforcement / trace 双向溯源；heavy lane 仍 `selected_count=0` 表示当前没有 deterministic 触发的 heavy primitive，符合 contract
- **是否达到最终形态**:
  - 已达到：
    - L0 deterministic hygiene 可静默 receipted apply（compile / lint / nightly），监控连续 active
    - L1 semantic candidate generation 命令面已产品化（`alchemy auto --primitive review|propose|distill`），不进入默认 unattended lane
    - core metrics 全部健康（provenance=1.0、stale=0.0、review_closure=1.0、proposal_acceptance=1.0）
    - shell / dashboard / today / planner / receipts / drift 全链 surface 可用
  - 尚未达到最终形态（剩余 stop line）:
    - **外部 quota 阻断**：4 条 source placeholder summary 受 `codex-cli` quota 阻塞（quota window 至 2026-05-05 13:39）；当前 backend chain 还没有显式 fallback 解耦此阻塞
    - **judgment / decision 结构化语义债**：48 warnings 表明 judgment/decision 的 `counter_evidence / next_signals / invalidation_rule / sections / placeholder` 仍未由 candidate pipeline 系统化收敛
    - **concept hardening 语义债**：30 个 soft concept 仍未推到 active/retired 终态
    - **review-queue backlog**：40 候选仍待显式人工/批量 adopt；review_closure 速率作为终局 KPI 还未稳定运行多周
    - **L2 meaning-changing adoption**：仍必须走显式 gate / 人工，并未变成“候选 -> 显式批量 review -> receipt -> revert”闭环 surface
  - 结论：炼丹炉当前是**“监控常驻 + 可无人值守 deterministic light maintenance + 显式 semantic candidate 入口 + 全链 receipt 审计”的 controlled runtime**；它已经具备最终形态的全部基础组件，但还不是最终形态本身。最终形态还差三件事可量化：
    1. 把 source / judgment / decision 的语义 enrichment 从单一外部 quota 解耦（多 backend 显式 fallback 或 nvidia-nim-api 主路径）
    2. 把 candidate -> adopt/revert 做成稳态批量 surface，让 review_closure_rate 在多周自然运行下持续 ≥0.8
    3. 把 soft concept hardening + judgment/decision 结构化 metadata 收敛进 candidate pipeline，使 lint warnings 在不阻断写入的前提下持续下降
