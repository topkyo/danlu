# Round 58 — R1 Stage 3 复利 real run + R3 counter-evidence 出口修复 + 市场对标调研

status: 完成
commit: 8bd33f5

Round 58 — R1 Stage 3 复利 real run + R3 counter-evidence 出口修复 + 市场对标调研 — 完成
- **目的**: 把炼丹炉从"机制完备"推进到"实战层 9.0+"，本轮聚焦两件事：(R1) 让金丹 thesis Stage 3 在真实 vault 跑通至少 1 例；(R3) 修复 counter-evidence today 出口的 schema 漂移
- **方向 SoT**: `docs/Furnace Next Direction Post-P4.md` §D-3 / §D-4 follow-up
- **R1 Stage 3 复利 real run（dogfood vault）**:
  - 投料：1 条 demo Q1'26 update note（Blackwell 爬坡 + 推理 SKU 占比 45% + GM 73.6%）
  - run-ask（codex-cli/gpt-5.5）输出 HOLD 判断 + 完整 invalidation 框架对照旧 elixir + 提议加 "毛利率 squeeze 二级 risk"
  - file-back judgment + promote derived → `alchemy-start --include-elixir elixir-nvda-4-thesis-invalidation-8fa6db3f` → distill → finalize → promote
  - **首个跨周期复利 settled elixir** `elixir-nvda-q1-26-thesis-squeeze-risk-b157a58a`，frontmatter `derived_from` 同时含旧丹（`wiki/elixirs/...`）+ 新 derived（`wiki/derived/...`），通过 DAG / wiki/derived anchor / counter_evidence gate
  - `aiwiki trace` 反向能看到完整 4 跳引用链 `新丹 → derived(Q1) → 旧丹 → derived(Q4)`
  - **Stage 3 复利从 unit test 锁定（D-3）推进到 real vault 验证（R1）**
- **R3 counter-evidence 出口修复（真实 P0 bug）**:
  - 投料：1 条 ALERT note（AWS Trainium2 Q1'26 关键 traction 信号，反 NVDA thesis 二级 trigger）
  - compile 后实测 `machine-memory.json` 真实包含 22 candidates / 11 pages（`counter_evidence_scan` 已正确命中 ALERT → NVDA judgment）
  - 但 `aiwiki today` 与 `shell-status.counter_evidence_pages` 仍 = 0
  - **真因**: `app_shell/summary.py::_counter_evidence_pages_from_memory` 用 `path / subject / summary` schema 读，但 scan writer (`compile/runtime_step.py:152`) 写的是 `page_path / page_title / candidate_count` schema；mismatch 静默丢弃所有 entry — 是 P0 信号融合的 silent breakage
  - 修：reader 同时认两套 schema（scan writer schema 优先，旧 `path` schema 作 back-compat fallback），summary 自动从 candidate_count 派生 "N 条新证据可能反驳此判断"，detected_at fallback 到 scan generated_at
  - 修后实测：`today` 的 Needs Review 浮出 8 条反证候选（含 NVDA Q1'26 judgment + 7 条 research dogfood 历史 judgment），完整端到端可见
- **市场对标调研（subagent 输出，对话内返回）**:
  - 调研同质 / 部分相似 / 易被混淆三类共 ~20 个产品（Reor、Khoj、Letta、Smart Connections、Copilot for Obsidian、AnythingLLM、OpenWebUI、PrivateGPT、Mem.ai、Tana、CrewAI 等）
  - 综合判断：市面**没有 1:1 对手**；最像形态的是 Reor + Obsidian Copilot 组合，最像 thesis 的是 Khoj，最像 runtime 抽象的是 Letta；炼丹炉独有"知识 compiler + receipt + protocol multiplexing + 金丹"组合在 2026 Q2 仍是空位
  - 弱项：检索/语义关联体验、生态/GUI、多模态自动捕获、多 backend 抽象成熟度、社区规模
- **Tests**:
  - 新 `tests/test_app_shell_summary.py` 3 个 R3 回归：scan-writer schema / 旧 schema back-compat / pathless 过滤
  - 总测试 1563 → 1566（+3 unit；R3 fix 锁定）
- **指标**:
  - dogfood vault 实测 metrics：provenance=1.0 / stale=0.0 / review_closure=1.0 / **elixir_reuse=1**
  - dogfood vault state 增量：sources +2、judgments +1、derived +1、**elixirs +1（settled，首个跨周期复利）**、execution-receipts +1（29→30）
  - ai-wiki repo verify：1566 unit + 13 acceptance / 92% coverage / `--fail-under=92` gate / `All checks passed!`
- **Stop Lines**: 0 review/apply/revert 状态机改动；不放松 DAG / counter_evidence / hash anchor gate；watcher / nightly 在 R1+R3 实跑期间停服，跑完恢复 active
- **评估升级**:
  - Round 56 升至 Investing 7-8/10；本轮：**金丹 Stage 3 thesis 7/10 → 9/10**（real vault 跨周期复利 + counter-evidence 真触发 + DAG/anchor 全过）
  - 加权综合 8.6 → **8.95 / 10**（机制层稳定 + dogfood 实战 2 protocol、Stage 3 复利 + counter-evidence 真闭环）

- **Round 57 R4 P4-INV-2 — filter quarter tokens**: 见 `archive/rounds/round-57-r4.md`（commit `8bd33f5`，与本轮一同收口）。
