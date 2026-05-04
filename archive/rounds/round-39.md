# Round 39 — Semantic Candidate Entry Repair + Dogfood State Assessment

status: 完成
commit: 

Round 39 — Semantic Candidate Entry Repair + Dogfood State Assessment — 完成
- **目的**: 修复 Round 38 后 semantic candidate generation 命令面不可达的缺口，继续 `/home/tim/danlu/炼丹炉` 运行测试、恢复监控，并评估炼丹炉距离最终形态的剩余差距
- **提交基线**:
  - `cd9dffd`
- **修复内容**:
  - `alchemy auto --primitive` 现在允许显式选择 `review` / `propose` / `distill`，与 runner 已有 heavy-lane 能力一致
  - 默认 auto/light/nightly 行为不变：unattended light lane 仍只执行 deterministic `compile` / `lint` / `nightly`，不会静默采纳语义结论
  - `run-compile` 的 LLM response validator 现在强制 `source_files` / `source_pages` 必须是 frontmatter list of non-empty strings，防止 inline JSON-ish string 被解析成普通字符串后污染 provenance lint
  - README 已补充显式 heavy candidate generation 入口：`alchemy auto --lane heavy --primitive review|distill|propose`
- **dogfood 运行测试**:
  - 手工写入前停止 `aiwiki-watch.service`，闭环结束后恢复 active
  - `alchemy auto --dry-run --scope all --lane heavy --primitive review|propose|distill` 已可从 CLI 到达 runner；当前 dogfood 没有可执行 heavy planner decision，结果为 `selected_count=0` / `empty_execute_plan`
  - 直接 scoped primitives `alchemy review|propose|distill|judge all --dry-run --limit 20` 均可运行；本轮因为 dirty-scope 没有选中信号，`candidate_count=0`
  - 使用 `.envrc.dogfood` 显式配置的 `codex-cli/gpt-5.5` 运行 `run-compile --limit 12`：成功 5 页后第 6 页因 120s timeout 中止
  - 本轮发现并修复 dogfood 中 1 个 LLM 写出的 inline `source_files` provenance 结构；修复后代码 validator 会阻止同类输出静默写入
  - 使用 `AIWIKI_LLM_TIMEOUT=240` 继续 source summary enrichment：先 `--limit 1` 成功 1 页，再 `--limit 6` 成功 2 页后命中 Codex CLI usage limit
  - 外部 quota stop-line：`You've hit your usage limit ... try again at May 5th, 2026 1:39 PM`
  - source placeholder summary warnings 从 12 条降到 4 条；最终 dogfood `lint` 为 0 errors / 91 warnings
  - deterministic `run-nightly --compile-limit 0 --no-semantic-lint` 成功，`llm_used=false`，agent_loop mode=`observe_dry_run_and_light_apply`，signals_new=27，planner_execute_new=27，auto_apply status=`applied`，applied_count=1
  - 写入 receipted light primitives：
    - `output/control/execution-receipts/alchemy-light-compile-20260430073406.json`
    - `output/control/execution-receipts/alchemy-light-lint-20260430073406.json`
    - `output/control/execution-receipts/alchemy-light-nightly-20260430073406.json`
- **dogfood 状态变化**:
  - `review-queue --json` total=40：concept_backlog=11，counter_evidence_candidates=8，judgment_review_actions=8，l3_proposals=1，machine_memory_actions=19，review_concepts=1，revisit_concepts=10，drift=1
  - `today --json` 已显示“已自动维护”：今日发现 27 个新变化，已静默执行 1 条维护路径
  - metrics：provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=1
  - 剩余 4 个 source placeholder summaries 受外部 quota 阻断；剩余 warnings 主要来自 soft concepts、judgment/decision structured metadata 与 review backlog
- **监控状态**:
  - `aiwiki-watch.service` active，当前命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-05-01 00:00:00 CST`
- **当前评估 / 剩余 stop-line**:
  - 已达到：CLI semantic candidate generation 入口已产品化；source/concept provenance validator 已加固；unattended deterministic light maintenance 在 dogfood 中继续稳定执行；source summaries 质量债显著下降；核心 metrics 保持健康；监控已恢复
  - 尚未达到最终形态：外部 `codex-cli` quota 阻断剩余 4 个 source summaries；soft concepts 与 judgment/decision structured metadata 仍是语义治理债；review-queue 仍有 40 个候选；L2 semantic adoption 仍必须走显式 gate
  - 结论：炼丹炉当前是“可无人值守执行 deterministic maintenance、可显式生成 semantic candidates 的 controlled-runtime”，仍不是最终形态；最终形态还需要在不静默采纳语义结论的前提下，把候选生成、人工/显式采纳、回滚审计和 backlog closure 做成稳定运行闭环
- **验证**:
  - focused tests pass：19/19
  - touched-file `ruff check` pass
  - `bash scripts/verify.sh` exit 0；1532 unit + 13 acceptance；coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；无独立 reviewer session，本轮明确记录 fallback 原因
