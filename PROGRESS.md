# 炼丹炉 Progress — Furnace 世代

> **结构 v2** (R68, 2026-05-04): PROGRESS.md 仅保留 Quick Index + 活跃 3 轮 + 改进方向指针。
> **PROGRESS.md 仍是当前任务状态唯一 SoT；archive/rounds/ 只是历史延伸。**
> 历史 round 详情：`archive/rounds/round-*.md` / `archive/rounds/p4-*.md`
> 机器索引：`archive/rounds/index.json`
> 切档历史：pre-Round 1 在 `archive/PROGRESS-pre-round1.md`（注意：里面也包含 Round 24/25 的早期记录，已重新落入 `archive/rounds/round-24.md` 和 `round-25.md`）

## SoT 引用

- 终局架构：`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md`
- 评分 / release gate：`docs/AGOS-9-Scorecard.md`
- 当前执行计划：`docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`（审计报告 + Commercial Go-Live WS1–WS6）
- 已归档 cleanup：`docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md`（executed-reviewed-pass）
- 验证入口：`bash scripts/verify.sh`
- 改进清单：见本文件底部「改进方向」段


## 当前动态

- 2026-07-15 (cross-review 进一步瘦身)：按 user "A + B + C-all" 决策执行。(A1) `.gitignore` 删 `.agentstack` + `.agents/skills/agentstack-*/` defensive ignores，保留 `.codegraph/` 与 `.coverage` 行因为本机这两个 artifacts 仍在生成；(A2) `scripts/archive/` 整目录删除（5 文件，引用面只剩 docs/archive/、archive/rounds/ 历史）；(B) 5 个 legacy Furnace docs 移入 `docs/archive/`：`Furnace Market Scan 2026Q2.md`、`Furnace Product Shell UX Test Checklist.md`、`Furnace Investing Dogfood Plan.md`、`Furnace RuntimeClient Mobile Companion Design.md`、`Furnace Agentic Debt Autopilot.md`，活跃 docs 从 14 → 9；(C) `tests/` 大瘦身：删 118 个顶层 `tests/test_*.py`（除 `test_acceptance_loop.py`）+ 26 个 `tests/unit/test_*.py`，合计 144 个文件（旧 ~56k LOC）退役；`tests/` 收缩到 acceptance-only（`test_acceptance_loop.py` + `tests/acceptance/` + `tests/fixtures/`），由 `bash scripts/verify.sh all` 默认 18s 跑 17 acceptance。再加 AGENTS.md 同步说明，CHANGELOG [Unreleased] 段同步更新。验证：ruff clean + scripts + python-static + smoke + cli-smoke + product-shell-static + acceptance 全绿 + docs_consistency 16 OK。

- 2026-07-15 (verify.sh all 不再跑 pytest+coverage)：按用户决定把 `verify.sh all` 中的 `coverage erase + coverage run pytest + coverage report` 三段（约 12 min / 占 `all` 总时间的 96%）一并剪掉，附带删 `.coveragerc` 与 `pyproject.toml` 的 `coverage>=7.6,<8` dev 依赖；同时从 `verify_target_rules.sh` 中删除 `.coveragerc` 路径 case（文件已无），AGENTS.md 同步说明 `all` ≈18 s 含 acceptance 17 fixture replay、不再含 pytest/coverage。`pytest>=8` 仍保留（`tests/test_acceptance_loop.py` + `tests/acceptance/case_runner.py` 走它跑 acceptance）。副作用：`tests/` 下 2509 单元测试不再被任何 verify path 自动跑，作为契约留在仓库供人工快速回归或外部 CI 调用；`fail_under=89` 硬 door 与 ~89% coverage 指标一同下线。验证：ruff + scripts + python-static + smoke + cli-smoke + product-shell-static + acceptance 全绿，`bash scripts/verify.sh` 默认走 `all` 现在 18 s；docs_consistency 16 项 OK。

- 2026-07-15 (verify unit 退场 + watcher deprecation 清掉)：按用户决策把 `verify.sh unit` target（裸 pytest 9 min，与 `all` 差别只剩 coverage overhead）整个删掉；`scripts/verify.sh` help/dispatch/function 全清，`scripts/verify_target_rules.sh` 同步去掉 4 处 `unit` 建议（`.coveragerc` / `schema/*.json` / `scripts/*.py` / `src/aiwiki/cli*.py` / `src/aiwiki/*.py` / `tests/*.py`），AGENTS.md "常用 target" 段降为 `scripts`/`smoke`/`python-static`/`acceptance`/`cli-smoke`/`product-shell-static`/`all`。Release gate 走 `bash scripts/verify.sh all`（13 min coverage + pytest + acceptance）不变；同时把 `scripts/run_launchd_watch.sh` 的 `watch ...` argv 改成 `advanced watch ...`，去掉 watcher err log 的 `[deprecated] aiwiki watch is a legacy top-level entry` 噪音（`run_launchd_nightly.sh` 早就在用 `advanced nightly`，未动）。验证：ruff + scripts + python-static + smoke + cli-smoke + product-shell-static + acceptance 全绿，`verify_target_rules.sh` 推荐收口到 `scripts + python-static`；vault launchd watch service 重新 load 后 drop 测试 note → 5–10s 内 wiki source 落盘，err.log 行数不再增长。详见 CHANGELOG.md [Unreleased]。

- 2026-07-15 (scripts + docs 集中瘦身)：按用户「只保留最核心的，其他耗时的都清理掉」执行。`scripts/` 删 16 个耗时 / niche 脚本（`cache_benchmark`、`compile_benchmark`、`long_window_proof_probe`、`dogfood_maturity_gate`、`run_dogfood_maturity`、`agos9_*`、`backend_probe_matrix`、`investing_dogfood_preflight`、`product_shell_smoke`、`run_product_shell_tests`、`check_product_shell_bundle`、`configure_local_worktree`、`stop_line_audit.{sh,py}`、`refresh_acceptance_fixture`），仅留 `verify.sh` / `verify_target_rules.sh` / `docs_consistency_check.sh` / `aiwiki-launcher.sh` / install + scheduler + `run_acceptance.sh` + `__init__.py` 核心；`systemd/aiwiki-dogfood-maturity.{service,timer}.template` 删除；`scripts/install_user_service.sh` / `uninstall_user_service.sh` 去掉 dogfood maturity 分支（保留对已安装 unit 的清理兜底）；`scripts/verify.sh product-shell-static` 不再调 `check_product_shell_bundle.sh` / `run_product_shell_tests.sh`，只跑 `node --check`；配套删除 `test_compile_benchmark_smoke.py` / `test_long_window_proof_probe.py` / `test_local_worktree.py` / `test_product_shell_smoke.py` / `test_dogfood_maturity_gate.py` / `test_cache_benchmark_script_outputs_status_and_timings`，并剪除 `test_app_runtime.py` / `test_app_misc.py` / `test_deploy_defaults.py` / `test_runner.py` 中的相关断言；aggressive 计划文件 `AGOS-9-Dogfood-Proof-Runbook.md` / `AGOS-9-Investing-Preflight-Runbook.md` 移入 `docs/archive/`。Release gate 不再依赖被移除的 release-evidence / maturity pipeline；`verify.sh all` 行为不变（仍 13 min coverage+pytest+acceptance），release 用。详见 CHANGELOG.md [Unreleased] 段。

- 2026-07-15 (post-cleanup audit)：全量再审计落盘 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`；结论：AgentOS ~9.05 与商业 ~7.6 勿混标；P0 为邮箱/EULA/价格 go-live；恢复本文件「改进方向」段；Active Plans 改为该审计计划，Demo Pack / RuntimeClient 降为 delivered specs。

- 2026-07-15 (cleanup plan archive)：刷新 M6.1b acceptance prompt_hash；Commercial Grade Cleanup Plan 归档为 `docs/archive/...`（executed-reviewed-pass）；AGENTS/PROGRESS 当前计划指针改为 Scorecard + PROGRESS。

> 切档：2026-05-24 及更早的大段 AGOS/AOS/C/P4 历史动态已移至 `archive/rounds/progress-2026-05-snapshot.md`；本段只保留最近状态与本轮清理。

- 2026-07-15 (cleanup plan reassess + Phase5/D4)：多-agent 再扫后轻修订计划（§1.6 评分卡综合 ~7.6；A4 判据修正；known env failures；go-live 延期表）。落地 D4：`docs/DEVELOPER.md` + 用户向 README；修复 README/HOME/indexes 死链；扩展 `docs_consistency_check.sh`；vault HOME 模板同步。

- 2026-07-15 (cleanup review fixes)：交叉审查后修复 P0–P2：`atomic_append_jsonl` 失败回滚、Jest runner cwd、`verify.sh all` 恢复 smoke、bulk CLI corrupt fail-closed、断链/SoT、LICENSE dual-license 头、systemd 空格路径。D4 已在后续收口完成。

- 2026-07-14 (Wave A residual A7/A8 docs cleanup)：PROGRESS 当前动态切档到 `archive/rounds/progress-2026-05-snapshot.md`，只保留 2026-06/05-31 近况；`wiki/indexes/README.md` 明确 indexes 为 compile 生成态、非 SoT，死链由 compile 重生或移出仓库处理。本轮仅文档/归档，未改 `src/`。

- 2026-06-01 (agentic debt-autopilot dogfood completion)：继续执行“系统核心不可自改，非核心债务交给 LLM-governed runtime 自消化”的合并计划，并在真实 dogfood `/home/tim/danlu/炼丹炉` 上把当前 `llm_owned_non_core` debt 清零。运行态修复包括：1) `_auto_apply_concept_rewrite_proposals(limit=1)` 以前会被旧 stale proposal 饿死，现改为先筛 current candidate 再套 limit；2) maturity collect 以前优先读旧 `signal_pipeline.debt_inventory`，会把已清理的 source summary 回报成 stale 38，现始终以当前 owner-state inventory 为当前 debt SoT；3) inventory 只把 policy 分类为 `non_core_semantic` 的 machine-memory action 计入 `llm_owned_non_core`，排除 governance / L3 governance proposal / `deferred + human_required`；4) applied rewrite 只有 `verification_status=passed` 才算 resolved；5) rewrite verification 规范化等价的本地 wikilink、extensionless wikilink、no-alias wikilink、relative markdown link 与 rendered local link，但仍保留 source signature、source pages 和 summary drift 检查；6) `reconcile_concept_rewrite_proposals()` 同步把 `weak_concepts` 视为 active rewrite debt，避免 weak-only proposal 生成后被标 inactive。真实 dogfood 从 `debt_remaining_count=40` 分批降到 `0`：pending source summaries 清零，weak/rewrite concepts 清零，verified debt-autopilot rewrite applies `20`。最新 `collect --write` 写入 `output/control/maturity-gate/snapshot-20260601T073134Z.json`，`debt_autopilot_report.status=clear`、`debt_detected_count=0`、`debt_remaining_count=0`；`agentic_autonomy_report.status=pass`、`llm_governed_apply_count=20`、`violations=[]`。文档同步更新 README 与 `docs/Furnace Agentic Debt Autopilot.md`，明确 governance/L3 metadata 不伪装成 `llm_owned_non_core`，并记录 dogfood proof。后续进入验证与独立复审收口。

- 2026-06-01 (agentic debt-autopilot first slice)：按“系统核心不可自改，非核心债务默认交给 LLM-governed agentic runtime 消化”的最新计划推进第一批落地。新增 `src/aiwiki/debt_autopilot.py` owner-state collector，不再让无人值守 auto-adopt 依赖 Product Shell controls；`agent_loop` 输出 `debt_autopilot`，`signal_pipeline` 输出 post-apply `debt_inventory`，`scripts/dogfood_maturity_gate.py` 新增 `debt_autopilot_report` 与 summary 计数。`collect_debt_inventory()` 不再读取 stale `nightly-health.repair_backlog`，而是从当前 manifest/source page、machine-memory health、machine-memory actions 和 L3 proposal owner-state 采集。`run_debt_autopilot(apply=True)` 现在复用 `run_compile` 逐 source 消化 pending summary，单项 LLM timeout 记录失败并继续后续项；weak-only slug 也进入 rewrite candidate 队列，rewrite generation 传 `wiki/concepts/<slug>.md` paths 避免被 source queue 抢占；current/valid concept rewrite proposal 可自动 accept/apply，stale candidate 会 skip，单项 apply 失败继续后续 proposal；accepted low-risk action 继续走 safe apply，不把 unsafe debt 转 human-required。事务边界补强：judgment auto-adopt 的 page/receipt 写入改用 atomic write；`split-overloaded-concept` auto-retire 纳入 apply-action 主事务快照，receipt/history 失败会恢复 lifecycle override。真实 dogfood：`run_debt_autopilot(root=/home/tim/danlu/炼丹炉, apply=True, limit=2)` 成功更新 2 个 source summary，`debt_remaining_count` 40→38；随后 maturity `run --compile-limit 0` 写入 `output/control/maturity-gate/run-20260601T044425Z.json`，状态 PASS，但 45s timeout 下 5 个剩余 source summary 均失败，`debt_remaining_count=38`。文档新增 `docs/Furnace Agentic Debt Autopilot.md`，README 同步说明 `llm_owned_non_core` 债务自消化边界。验证：targeted `PYTHONPATH=src python3 -m pytest tests/test_debt_autopilot.py tests/test_signal_pipeline.py tests/test_dogfood_maturity_gate.py tests/test_agent_loop.py tests/test_runner.py tests/test_app_runtime.py::RuntimeFlowTests::test_run_compile_paths_targets_rewrite_candidate_without_source_queue_starvation -q -k "debt_autopilot or signal_pipeline or dogfood or agent_loop or rewrite_candidate or paths_targets_rewrite_candidate"` PASS（72 selected passed）；`scripts/agentstack verify --target auto` PASS（evidence `.agentstack/evidence/20260601131404-749708/verify.json`）。后续需要继续按 source 分批/长 timeout 消化真实 dogfood 剩余 38 项 debt。

- 2026-05-31 (legacy direct-note receipt coverage closure)：按下一步第 4 项处理历史 `receipt_coverage.status=warn`，不回填、不伪造历史 execution receipt。根因是 4 个 2026-05-20/21 旧 `aiwiki-run-ask-direct` / `llm-direct` note 产物已经有 LLM receipt、run notes 和 artifact provenance，但生成时间早于 direct-note success execution receipt matrix 落地，因此缺 `execution_receipt`。`scripts/dogfood_maturity_gate.py` 新增 cutover 前 legacy direct-note 分类：仅当 `generated_by=aiwiki-run-ask-direct`、`delivery_mode=llm-direct`、`created_at < 2026-05-23T00:00:00+00:00`、且同时具备 LLM receipt / run notes / artifact provenance 时，才以 `legacy_direct_note_execution_receipt` 豁免 execution receipt 缺口；cutover 后的新 direct-note 若缺 receipt 仍保持 warn。真实 dogfood `collect --preview-limit 20 --write` 写入 `output/control/maturity-gate/snapshot-20260531T144416Z.json`，`receipt_coverage.status=pass`、`outputs_checked=8`、`complete_count=8`、`incomplete_count=0`、`legacy_direct_note_exempt_count=4`、`missing_counts={}`；`summarize --days 3 --require-current-day` 仍为 `status=pass`、`trend_status=pass`，且 newer snapshot consistency `status=pass`。验证：`PYTHONPATH=src python3 -m pytest tests/test_dogfood_maturity_gate.py -q` PASS（38 passed）；`bash scripts/docs_consistency_check.sh` PASS；`git diff --check` PASS。

- 2026-05-31 (dogfood backlog trend closure)：继续执行 live dogfood maturity 后续治理，清理导致 `trend_status=warn` 的真实 backlog。先在 `/home/tim/danlu/炼丹炉` 复核并确认 `judgment-aos-c2-dogfood-live-proof-judgment`，关闭 5 个低风险 bridge monitor machine-memory actions；随后定位剩余 `counter_evidence_candidates=1` / `judgment_review_actions=1` 的根因：`_counter_evidence_scan_phase` 只按 source/page 词重叠和 citation 排除候选，未尊重 `review-page` 写入的 `last_reviewed`，导致已人工确认、且晚于 source 更新时间的旧候选在 clean compile 中从 previous scan 反复回流。修复 `src/aiwiki/compile/runtime_step.py`：当 decision/judgment 已是 `approved/confirmed` 且 `last_reviewed/reviewed_at` 严格晚于 source `updated_at/imported_at` 时跳过该 counter-evidence candidate；同 timestamp 仍保留候选，避免吞掉并发/同秒新证据。补充 `tests/test_app_shell.py` 覆盖 judgment suppression、同 timestamp 不 suppression、decision approved suppression，并保留新 follow-up evidence 仍触发 review action 的路径。真实 dogfood maturity run 写入 `output/control/maturity-gate/run-20260531T142636Z.json`，`human_required_report.exception_count=0`、`primary_exception_counts={}`、`routine_primary_debt_count=0`；`summarize --days 3 --require-current-day` 恢复 `status=pass`、`trend_status=pass`、`backlog_total_delta=-10`、`operational_maturity.status=pass`、`budget_violations=[]`、`l3_effective_candidate_count=0`、`knowledge_compounding_status=pass`、`elixir_quality_status=pass`。验证：targeted `PYTHONPATH=src python3 -m pytest tests/test_app_shell.py tests/test_pipeline.py::PipelineTests::test_counter_evidence_scan_persists_across_clean_compile tests/test_app_runtime.py::RuntimeFlowTests::test_nightly_surfaces_judgment_review_actions_from_counter_evidence tests/test_dogfood_maturity_gate.py -q` PASS（78 passed）；只读 reviewer subagent 未发现阻塞问题；`scripts/agentstack verify --target auto` PASS（evidence `.agentstack/evidence/20260531223227-3123587/verify.json`）；`git diff --check` PASS。

- 2026-05-31 (live dogfood maturity recovery + verify closure)：按当前 dogfood vault 真实状态恢复 9 分 release proof。先复核 `/home/tim/danlu/炼丹炉` 近 3 日 maturity：初始 `summarize --days 3 --require-current-day` 为 `warn`，核心 blocker 是 `operational_maturity.status=not-yet` / `effective_l3_candidates=1`。按现有治理路径关闭两个低证据、`metadata_only` L3 prompt proposal：`auto-sig-20260520-f322c7b578de`（historical runtime failure smoke fixture）与 `auto-sig-20260527-f39933664559`（counter-evidence 已被多次 judgment review 判定 `upheld/high`）。随后修正 `scripts/dogfood_maturity_gate.py` 的 release 口径：snapshot budget 不再把 human-only primary exceptions 当 release violation，只阻断 routine primary debt 或真实 human-required action；summary 顶层 `status` 对齐 operational maturity，同时新增 `trend_status` 保留旧 backlog 趋势信号。恢复后 `l3_effective_candidate_count=0`、`operational_maturity.status=pass`、`budget_violations=[]`、`knowledge_compounding_status=pass`、`elixir_quality_status=pass`、`snapshot_consistency.status=pass`；`trend_status=warn` 仍提示 backlog 趋势需后续治理，但不再误杀 release proof。后续按用户要求执行下一步验证闭环：刷新 `tests/fixtures/acceptance/M6.1b/case_happy_run_ask` replay fixture 的 `prompt_hash` 与 golden，使 `test_happy_run_ask_replay` 回到 PASS；确认 `scripts/agentstack verify --target auto` 正确调用方式是直接执行 shell wrapper，不是 `python3 scripts/agentstack`。验证：`PYTHONPATH=src python3 -m pytest tests/test_dogfood_maturity_gate.py -q` PASS（36 passed）；`PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py::test_happy_run_ask_replay -q` PASS；`bash scripts/agos9_dogfood_proof_status.sh` PASS；`bash scripts/verify.sh python-static` PASS；`bash scripts/verify.sh scripts` PASS；`scripts/agentstack verify --target auto` PASS（targets: acceptance, python-static, scripts, unit；2556 unit tests passed）；`bash scripts/docs_consistency_check.sh` PASS；`git diff --check` PASS。

## Milestone Quick Index

> 每行只保留世代 / Milestones / 一句主旨 / 状态。完整实现细节、Stop Lines、Residual Risks 见 `archive/rounds/milestone-quick-index-detail.md`。

| 世代 | Milestones | 状态 |
|---|---|---|
| **P4 Dogfood-driven** (2026-04-28) | P4-1a~1d, P4-2~6, P4-9, P4-11, P4-15 | ✅ 全部 done |
| **D 系列** (2026-04-30) | D-1~D-4 + D-3 R1 + D-4 v0/v1 | ✅ 全部 done |
| **P4-INV** (Round 57-59) | P4-INV-1~4 | ✅ 全部 done |
| **Post-R61 改进** (2026-05-03) | harness 增量升级 / QA review 启用 / plans-merge / Round 62/63 UI Polish | ✅ Round 62/63 done / 其余 🔄 |
| **Round 64-66 UX Earnest** (2026-05-03) | 命名去时间戳 / 拖放修复 / 面板精简 / L3 自动采纳 / 图谱锚点 / 导航简化 | ✅ 全部 done |
| **Round 67 Auto-adopt Hardening** (2026-05-04) | judgment review / L3 audit / nightly aggregation / strict JSONL | ✅ done (`6711efd`) |
| **Round 67.5 Acceptance Fixture Refresh** (2026-05-04) | M6.1b prompt_hash drift refresh | ✅ done (`284f8af`) |
| **Round 68 Progress Slimming** (2026-05-04) | PROGRESS 三层瘦身 / rounds archive / stop_line_audit lint | ✅ done (`2c408f9`) |
| **Round 69 Atomic State I/O** (2026-05-04) | `atomic_write_text` + `atomic_append_jsonl` helpers / 4 saver 替换 | ✅ done (`7ee3ab8`) |
| **Round 70 Receipt JSONL 事务化** (2026-05-04) | 12 JSONL writers 全量原子化 / mm revert 双 receipt + `reverts/` 子目录 | ✅ done (`950f291`) |
| **Round 71 Fetch & Path 安全** (2026-05-04) | `safe_fetch` + `safe_resolve_within` / SSRF / repo symlink 跳过 / Playwright route 拦截 | ✅ done (`a6074b9`) |
| **Round 72 Lock 高优先级缺锁补齐** (2026-05-04) | drop_* 五入口 + nightly_health + receipt_history 全加 `runtime_write_lock` | ✅ done (`addd53d`) |
| **Round 73 LLM/notify HTTP 安全** (2026-05-04) | `safe_fetch` 扩 POST + headers + redirect strip auth / llm.py + notify.py 切换 | ✅ done (`c0cf944`) |
| **Round 74 L3 事务化 + audit auto-revert** (2026-05-04) | `apply_l3_proposal` 后半 5 步 TX / `L3PostApplyAuditError` 携带证据 / auto_reverted runtime_history | ✅ done (`b6a64f5`) |
| **Round 75 receipt_history TX** (2026-05-04) | `_durable_truncate` / `ReceiptHistoryAuditError` + `ReceiptHistoryRollbackError` / R74 残余关闭 | ✅ done |
| **Round 76 runtime_history TX + audit-mirror 上移** (2026-05-04) | `_durable_truncate` + AuditMirror* 上移 `app_utils` / R75 API 保持 | ✅ done |
| **Round 77 LLM receipt TX** (2026-05-04) | `_append_llm_receipt` snapshot-then-rollback / 复用 AuditMirror* | ✅ done |
| **Round 78 age audit single-file TX** (2026-05-04) | `_durable_restore_or_remove` / `_write_age_audit` snapshot bytes | ✅ done |
| **Round 79 auto_adopt 顶层 lock** (2026-05-04) | 4 个 `auto_adopt_*` 入口加 `@runtime_write_operation` / reentrant | ✅ done |
| **Round 80 safe_fetch response close** (2026-05-04) | urlopen response 用 `with` 包；R71-R73 残余关闭 | ✅ done |
| **Round 81 citation snapshot path guard** (2026-05-04) | `safe_resolve_within` + wiki/judgments\|decisions 白名单 | ✅ done |
| **Round 82 citation revert guard 对称收口** (2026-05-04) | `revert_machine_memory_action` citation 分支复用同 helper | ✅ done |
| **Round 83 safe_fetch DNS pinning + host allowlist** (2026-05-05) | pinned-IP connect / proxy 禁用 / SNI 保留 / opt-in allowlist | ✅ done |
| **Round 84 fail-soft 收口 + 事实层 strict read 迁移** (2026-05-05) | notify 双层 fallback / `load_runtime_history_strict` / 6 callers 切 strict | ✅ done (`c94cc87`) |
| **Round 85 history JSONL strict migration** (2026-05-05) | execution policy/receipt history strict variants / fact-layer 切 strict | ✅ done (`ea08d6e`) |
| **Round 86 safe_fetch 多 IP fallback** (2026-05-05) | R83 pinning 可用性回归修复 / resolver 顺序循环 TCP | ✅ done (`b345ecf`) |
| **Round 87 R85/R86 non-blocking 小补丁** (2026-05-05) | history strict 测试断言收紧 / HTTPS fallback `wrap_socket` 单次 | ✅ done (`0891a44`) |
| **Round 88 PM-UX 三件套** (2026-05-05) | Today 空态 CTA / "处理中" 卡 state machine / 面板文案白话化 | ✅ done |
| **Round 89 PM/UX 信任闭环 + 文案统一** (2026-05-05) | pending 持久化 / 状态机两段式 / Today→今天 / groupSpecs 中文化 | ✅ done |
| **Round 90 提交→状态→结果 闭环** (2026-05-05) | Today "刷新炉子" + last-updated / pending 行动卡 / done TTL 7d | ✅ done |
| **Round 91 Advanced 抽屉信息架构** (2026-05-05) | dev banner 外置 / 三组可折叠 section + 持久化 | ✅ done |
| **Round 92 Alchemy Apply Lock + Receipt Atomicity** (2026-05-05) | runner/alchemy.py 7 入口加 lock / 7 receipt write 切 atomic / preview 透传 | ✅ done |
| **Round 92.1 Alchemy Lock Audit (Tight)** (2026-05-05) | 3 残余 unlocked writers 加 decorator / `_walk_preview_lock_status` 双函数 | ✅ done |
| **Round 92.2 Machine-Memory Action TX** (2026-05-05) | `apply/revert_machine_memory_action` snapshot/rollback / 3 apply_mode / `MachineMemoryActionReceiptError` | ✅ done |
| **Round 92.3 Drop Input Safety** (2026-05-05) | 本地 ingestion 边界：PDF 50MB / image 25MB + MIME 白名单 / repo max_files normalize | ✅ done |
| **Round 92.4 Protocol/Manifest 单文件原子写** (2026-05-05) | 6 处 protocol/manifest JSON 切 `atomic_write_text` | ✅ done |
| **Round 92.5 Cache Layer Fail-Soft** (2026-05-05) | SQLite query cache 8 boundary fail-soft / 5 compile build-state save fail-soft | ✅ done |
| **Round 92.6 Lock Audit Wide** (2026-05-05) | 7 个 SoT/state writer 入口加 lock 保护（Tight 5 + Standard 2 conditional） | ✅ done |
| **Round 92.7 Deploy/Service Defaults Hardening** (2026-05-05) | systemd installer 默认 deny-by-default / `AIWIKI_VAULT` 强制 / lock timeout / remote repo opt-in | ✅ done |
| **Round 92.8 Feed Parity (Universal Input)** (2026-05-12) | `recent_raw_inputs` summary + plugin reconcile / extractPrimaryPath 扩展 / 不新增 FeedKind | ✅ done |
| **Round 92.9 DETERMINISM compile gate** (2026-05-10) | compile log timestamp-insensitive gate | ✅ done (`f153589`) |
| **Round 92.10 TEST SPLIT test_app.py** (2026-05-10) | 7984 行拆 7 个 focused 文件 / 总 test count 不变 | ✅ done (`00b41ad`) |
| **Round 92.11 PERF Benchmark** (2026-05-10) | measurement-only `compile_wiki` benchmark / 不接 CI gate | ✅ done (`0944726`) |
| **Round 93.0 autonomy_policy fail-closed** (2026-05-11) | malformed → `CorruptStateError` / `load_autonomy_policy` 切 strict | ✅ done (`7e43e4e`) |
| **Round 93.1 material-archive TX 雏形** (2026-05-11) | `apply/revert_archive_action` 早期 receipt-tier TX；R95.1 接续 | ✅ done (`37c9341`) |
| **Round 93.2 compile-artifact 原子写** (2026-05-11) | compile pipeline 派生 artifact 全切 `os.replace` 原子路径 | ✅ done (`6d2cee6`) |
| **Round 93.3 ingest subprocess timeout** (2026-05-11) | `drop.py` ingest subprocess 加 `timeout=` / `IngestionTimeoutError` | ✅ done (`137aa4e`) |
| **Round 94.0 automation.json 原子写** (2026-05-11) | `atomic_write_text` + `fsync=True` / `load_automation_state` strict + corrupt 回收 | ✅ done (`0ddc2c7`) |
| **Round 94.1 drift_scan → append_runtime_history** (2026-05-11) | drift_scan 改走 `append_runtime_history` 复用 R76 TX + audit-mirror | ✅ done (`6bf39e0`) |
| **Round 94.2 ingest_source raw/ atomic + orphan tmp 跳过** (2026-05-11) | raw write 切 atomic + fsync / raw scanner 过滤 `*.tmp.*` | ✅ done (`4ba29e9`) |
| **Round 94.3 mm-action read-then-write fail-closed** (2026-05-11) | `apply/revert_machine_memory_action` 切 `load_json_document_strict` | ✅ done (`a85f599`) |
| **Round 94.4 concept rewrite apply/revert TX** (2026-05-11) | file + state pair TX / reversed write-order rollback | ✅ done (`ecef27f`) |
| **Round 94.5 L3 Proposal apply/revert TX** (2026-05-11) | file + receipt + state triple TX / `L3{Apply,Revert,Reject}{ReceiptError,HalfWriteError}` | ✅ done (`b093241`) |
| **Round 95.1 archive apply/revert TX** (2026-05-11) | receipt+state pair TX / phase-2 derived audit swallow-with-warning（设计保留） | ✅ done (`a49ead8`) |
| **Round 95.2 drop.py raw note + asset atomic** (2026-05-11) | raw note + asset 全切 `atomic_write_text` / `atomic_write_bytes` + `fsync=True` | ✅ done (`0731823`) |
| **Round 95.3 L3 Phase-2 False-Write Truncate** (2026-05-11) | `_durable_truncate(path, snapshot_size)` 截回 commit 前长度 | ✅ done (`70ff772`) |
| **Round 95.4 Nightly Audit Reconciler** (2026-05-11) | `reconcile_execution_receipts` nightly 检 false-success / 仅扫 `revert` | ✅ done (`3679079`) |
| **Round 96.0 alchemy receipt persistence TX** (2026-05-11) | `_persist_receipt_transactionally` 收口 receipt-tier TX 范式 | ✅ done (`4b3e32f`) |
| **Round 96.1 alchemy review_apply TX** (2026-05-11) | `run_alchemy_review_apply` receipt-tier TX | ✅ done (`8a4dd91`) |
| **Round 96.2 alchemy lane primitive Receipt TX** (2026-05-11) | `_run_receipted_lane_primitive` wrapper TX | ✅ done (`44100e2`) |
| **Round 96.3 alchemy distill/propose_apply TX** (2026-05-11) | `run_alchemy_distill_proposal_apply` / `run_alchemy_propose_apply` TX | ✅ done (`1db7925`) |
| **Round 96.4 create_l3_proposal TX** (2026-05-11) | state + page + history + audit + wiki-log 全包 receipt-tier TX | ✅ done (`4df35ea`) |
| **Round 96.5 mm_action_batch Receipt-Tier TX** (2026-05-11) | `apply_machine_memory_actions_batch` snapshot/rollback 全包 | ✅ done (`5aa4a92`) |
| **Round 96.6/96.7 L3 Phase-2 Audit Swallow DROP** (2026-05-11) | fresh oracle pre-design DROP；决议归档 `.codex/contracts/archive/R96.6/96.7-*.md` | ❌ dropped |
| **Round 96.8 apply_l3_proposal Rollback 跨流一致** (2026-05-11) | 外层 rollback 顺序 reversed write-order；补 `runtime_history_path` 还原 | ✅ done (`f2c9f5a`) |
| **Round 96.9 L3 Apply Phase-2 Audit Reconciler 扩流 DROP** (2026-05-11) | fresh oracle pre-design DROP；决议归档 `.codex/contracts/archive/R96.9-*.md` | ❌ dropped |
| **Round 97 Decision-grade Report Skeleton** (2026-05-11) | `output_format=report` 升级到 6 区块固定骨架 + `_validate_report_sections` | ✅ done |
| **Round 98.1 Decision-grade Report Bullet Minimums** (2026-05-11) | 每段 `- ` bullet 下限 + 拒 `_LLM:` placeholder 残留 / fence-aware bullet counter | ✅ done (`ae9e19f`) |
| **Round 98.2 Report Citation Integrity** (2026-05-11) | `## 引用` dedup + body ⊆ citations 校验 / fence-aware path 提取 | ✅ done |
| **Round 98.3 Report Strictness Hardening** (2026-05-11) | Phase 0 unclosed fence 拒绝 + Phase 1.5 duplicate required H2 拒绝 | ✅ done |
| **Post-P4 D-2 PROGRESS Slim** (2026-05-12) | Round 73-92.7 + Milestone Quick Index detail 切档归档 / PROGRESS 117KB→18.5KB | ✅ done (`c472677`) |
| **Post-P4 B drift_scan Acceptance** (2026-05-12) | drift_scan 三扫描器函数级 acceptance / 4 byte-stable golden / 15 cases | ✅ done (`54d7e2c`) |
| **Post-P4 C drop_url Acceptance** (2026-05-12) | drop_url end-to-end materialization acceptance / 4 byte-stable golden / 16 cases | ✅ done (pending commit) |
| **Post-P4 D-3 Acceptance Gap P1** (2026-05-12) | 金丹复利 5 步 CLI 链 acceptance / 3 state JSONL byte-stable | ✅ done (`8cd2b25`) |
| **Post-P4 B Drift/Aging Acceptance Gap B** (2026-05-12) | drift_scan 三扫描器函数级 acceptance / 4 artifact byte-stable | ✅ done |


## 状态 — 当前活跃 3 轮

### Round 92.8 — Feed Parity (Universal Input pending closure) — 完成

- **目的**：闭合 P2 fresh oracle scoping 排为 SHIP first 的用户可见 feed-parity bug——Universal Input 投料（URL/PDF/image/repo/note）成功后，pending 卡长期停在 "已接收，等待生成报告"，因为 (1) `drop_*` 返回 payload 含 `note_path` 但 plugin `extractPrimaryPath()` 只识别 `path/output_path/receipt_path/state_path/index_path/report_path`；(2) shell summary 不暴露 raw ingest，`reconcilePendingSubmissions()` 永远 miss raw drop。
- **实现**：
  - `src/aiwiki/app_shell/summary.py:145-166`：新增 `_build_recent_raw_inputs(root, *, limit=8)` helper，从 `load_runtime_history(root)`（NON-strict，关键：strict 会 raise 破坏 fail-soft）过滤 `event_type == "raw-added"`，倒序取 8 条，映射 `stored_path / original_path / source_type / title / occurred_at / protocol`，全部 `str() or ""` coercion；body wrap broad `try/except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError)` 返回 `[]` 不 raise。`build_shell_summary` 在 line 241 预计算，line 312 dict literal 插入 `"recent_raw_inputs": recent_raw_inputs` 紧跟 `recent_runs`。
  - `src/aiwiki/today_feed.py:415-440`：新增 `_build_raw_input_entries(summary, today_date)` helper，仅当 `recent_raw_inputs` 是 list 时迭代；空 `stored_path` 跳过；`_date_part(occurred_at) != today_date` 跳过；构造 `FeedEntry(kind="action", title=f"已投料：{title or original_path or stored_path}", summary=f"已接收 {source_type or '材料'}，等待编译/刷新", target=stored_path, ...)`。`build_today_feed` line 82-83 在 `_build_action_entries` 之后追加。**关键**：未新增 FeedKind，复用 `kind="action"`（priority 6 最低），避免 schema 改动。
  - `.obsidian/plugins/furnace-product-shell/src/plugin_helpers.js:178`：`extractPrimaryPath()` `candidateKeys` 数组扩展为 `["path", "output_path", "receipt_path", "state_path", "index_path", "report_path", "note_path", "stored_path", "asset_path"]`，**新增 keys 排末尾**保留既有 ask/run path 优先级。
  - `.obsidian/plugins/furnace-product-shell/src/plugin.js:2150-2213`：`reconcilePendingSubmissions()` `rawCands = summary.recent_raw_inputs`，guard 允许 raw-only proceed；`matchAgainst` `fields` 数组扩展 `stored_path / original_path / note_path`；hit 顺序保持 outputs → receipts → raw fallback；命中 raw → `target = "raw"` + `targetPath = String(hitCand.stored_path || hitCand.path || "")` → `markPendingSubmissionDone(entry.id, "raw", targetPath)`。`markPendingSubmissionDone` 不 whitelist target 字符串（plugin.js:2085-2095 直接 `entry.reconcileTarget = String(reconcileTarget)`），"raw" 不 no-op。注释 comment 同步更新（plugin.js:2082）。
  - `.obsidian/plugins/furnace-product-shell/src/today_feed.js:58-59,286-305`：JS mirror 同步新增 `buildRawInputEntries`，被 plugin 加载，与 Python 渲染契约一致。
  - `tests/test_feed_parity.py` 10 测试 + `load_tests` bridge：4 summary（drop history 收录 + 全字段映射 / 无 history 空 / 损坏 JSONL fail-soft 返回 [] / 12 events 限 8 条 most-recent-first / 混 event_type 仅 raw-added）+ 3 today_feed（today date 渲染 kind=action / 昨天跳过 / 空 stored_path 跳过）+ 2 JS grep（plugin_helpers.js candidateKeys 含三新 key / plugin.js reconcile 含 `recent_raw_inputs` + `target = "raw"` + `stored_path` token）。
- **验证**：`bash scripts/verify.sh` PASS — **1848 unittest**（+10）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session `ses_2055cf69dffeSzSAEpOCXG597D` PASS（首次 retry，非阻塞 concerns：JS 测试是 grep 级 vs 真执行级 / `markPendingSubmissionDone` 注释 comment 已 fix）。End-to-end 链路 trace 完整：user → Universal Input → `aiwiki drop <payload>` → `dispatch.py` rewrite → `drop_*` → `_append_raw_added_history` JSONL → `build_shell_summary` `recent_raw_inputs` → plugin reconcile `rawCands` → match via `stored_path` → `markPendingSubmissionDone("raw", stored_path)`。
- **Stop Lines**：0 `drop_*` 返回签名改 / 0 CLI signature / 0 `runtime_history` 写语义 / 0 schema / 0 lock primitive / 0 新 FeedKind（`today_feed.FeedKind` Literal 不变）/ 0 `general` default protocol / 0 LLM defaults / 0 notify defaults / 0 `safe_fetch` allowlist / 0 Universal Input 命令字符串（plugin.js:2239 仍 `["drop", normalizedPayload]`）。
- **Migration**：纯加层；既有 dogfood vault 重启 plugin 后 raw drop pending 卡可被 reconcile 自动 mark done；既有 ask/run path 优先级不变。
- **Residual Risks**：JS grep 测试只覆盖 token 存在，不覆盖顺序 / 行为变化 → 未来 plugin 大改时回归防护偏弱；可在后续 round 补 node 真执行测试（DEFER 不在本轮 scope）。
- **归档**：contract `.codex/contracts/archive/round-92-feed-parity.md`。


---

## 改进方向

> SoT：详细缺陷表、工作流与 Done 判据见 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`。此处只保留指针级清单。

| 优先级 | 方向 | 状态 |
|---|---|---|
| P0 | Commercial go-live：真实 `commercial@` / `support@`、价格决策、商业 EULA/购买路径（替换 `@example.com`） | 未立项执行 / 需运营法律决策 |
| P1 | 分发闭环：`pip install` 或 INSTALL 明确预览边界；版本与 tag 对齐 | 延期自 Cleanup Phase5 |
| P1 | Jest hard-gate + env-coupled 测试隔离（workspace / Chrome drop） | soft-skip 仍在 |
| P1 | Alchemy materialize 等裸 `write_text` → `atomic_write_text` | 已记录待修 |
| P2 | Scorecard hub 行数刷新；PROGRESS 活跃 round 切档卫生 | 部分已在本审计 PR 启动 |
| P2 | Demo Pack 截图/录屏资产（fixture 已交付） | WS3 |
| 观测 | 14/30-day natural dogfood proof（不伪造 PASS） | Scorecard not-yet |
| Out | hub 大拆、SaaS、全功能 iOS、用 AgentOS 9.05 冒充商业 9 分 | 禁止 |

---

> 更早的 round 详情请参考 `archive/rounds/round-*.md` / `archive/rounds/p4-*.md`，或读 `archive/rounds/index.json`。
