# Round 56 — D-4 Investing Protocol End-to-End Dogfood (实跑) + Model Default Drift Fix

status: 完成
commit: 

Round 56 — D-4 Investing Protocol End-to-End Dogfood (实跑) + Model Default Drift Fix — 完成
- **目的**: 把 D-4 contract（`docs/Furnace Investing Dogfood Plan.md`）从 `pending(blocked-on-llm)` 推进到首次端到端实跑；同时修复评估识别的 P1 漂移（`DEFAULT_CODEX_MODEL=gpt-5.4` 与现实 5.5 不同步）
- **方向 SoT**: `docs/Furnace Next Direction Post-P4.md` §D-4；`docs/Furnace Investing Dogfood Plan.md` §2 七步 flow
- **Backend 决策**: 实测 `llm-check --probe-all` 后 codex-cli/gpt-5.5 是唯一 compatible；copilot-cli/auto degraded（`●` 装饰前缀，frontmatter 不兼容，不能作 compile fallback）；copilot-cli/gpt-5.4-mini unavailable（rate limit 5/4 重置）；claude-cli requires_credential；nvidia-nim-api 无 key。本轮全程使用 codex-cli/gpt-5.5
- **D-4 实跑（dogfood vault `/home/tim/danlu/炼丹炉`）**:
  - 投料：3 条 demo investing note（NVDA Q4 thesis / 推理芯片格局 / TSMC CoWoS 供给）通过 `drop note --text` 落 raw/inbox
  - Compile：deterministic compile 3/3；run-compile --limit 3 完成 3/3 但优先处理 placeholder 旧 page，新投料未被 LLM 改写（**F-INV-1 摩擦**）
  - Ask：run-ask 生成 141 行结构化投资判断报告（thesis / Bull/Bear evidence / catalyst / invalidation / 跟踪框架）
  - Judgment：file-back judgment → review-page 走完 `tentative → tracking → confirmed` 三态
  - Distill：promote derived → alchemy-start → alchemy-distill（含 invalidation 阈值追问）
  - Promote：alchemy-finalize → alchemy-promote 产出**首个 investing settled elixir** `elixir-nvda-4-thesis-invalidation-8fa6db3f`，counter_evidence=NONE_FOUND/confidence=low（M2.3 gate 通过）
  - L3 proposal：`l3-proposal-create prompt_proposal` → `review proposal --status rejected`（dogfood evidence_count=1 不达 contract §10.1 N=5 阈值，闭环成立但显式拒绝写回）
  - Receipt：`output/reports/dogfood-receipt-investing-v0.md` 落盘，含 19 条 F-INV-* 摩擦点状态 + 4 条 P4-INV-1~4 follow-up（队列优先级 / concept noise / judgment schema / review_after default）
- **Model default drift fix**:
  - `src/aiwiki/config.py` `DEFAULT_CODEX_MODEL` 从 `gpt-5.4` 改为 `gpt-5.5`，与 `.envrc.dogfood` 真实使用对齐
  - `src/aiwiki/app_vault.py` new-vault README 模板 + `scripts/install_user_service.sh` systemd template 同步
  - 三处 test 同步：`tests/test_app.py` / `tests/test_vault.py` 的 default-model assertion 从 5.4 改 5.5
  - 不改 explicit-model 测试（`tests/test_config.py:159` / `tests/test_runner.py` / `tests/test_llm.py` 等显式构造 5.4 fixture 保留作为 explicit-model behavior coverage）
- **Stop Lines**: 0 review/apply/revert 状态机改动；0 schema mutation；不破坏 9+ feasibility contract；watcher / nightly timer 在跑 D-4 期间显式 stop，跑完恢复 active
- **指标**:
  - dogfood vault 实测 metrics：provenance=1.0 / stale=0.0 / review_closure=1.0 / output_file_back=0.667 / elixir_reuse=1
  - dogfood vault state 增量：sources +3、judgments +1、derived +1、elixirs +1（settled，首个 investing）、L3 proposals +1（rejected）、execution-receipts +1（28→29）、audit +59（477→536）
  - ai-wiki repo verify：1563 unit + 13 acceptance / 92% coverage / `--fail-under=92` gate / `All checks passed!`
- **评估升级**: 评估文档 §4 给的 "Investing 协议端到端 4/10" 应升至 **7-8/10**（仍非满分；剩余 P4-INV-1~4 + 真实 PDF 投料 + 多周自然运行验证）
