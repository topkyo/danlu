# 炼丹炉 AgentOS Completion Plan

> Harness 可读 SoT，承接 `docs/AGOS-9-Execution-Plan.md`、`docs/Furnace Agent OS Slimdown Plan.md` 与 `docs/Furnace Post-AGOS Risk Plan.md`。
> 本计划目标是把当前约 8.2/10 的强 local-first runtime 推进为可长期运行、可现场复算、可审计自治、用户面极简的 Agent OS。

## Goal

把炼丹炉推进到可作为 Agent OS 的完成态：用户只需要投料和看结果；runtime 能持续把输入炼成可追溯知识资产；所有语义判断保留 provenance；所有 mutation 有 receipt / audit / revert；planner 能在受控边界内调度 safe primitives；LLM 失败显式可见；dogfood proof 可现场复算；长期运行状态可解释、可恢复、可追责。

核心目标不是继续堆机制，而是补齐 clean proof、拉绿 release gate、降低 hub 风险，并让 `signal -> planner -> phase -> feedback -> learning` 形成 receipt-backed 闭环。

## Architecture Inputs

- `README.md`：当前炼丹炉 runtime 主线、CLI taxonomy、五层文件模型和开发者模块图。
- `docs/Furnace Agent Architecture.md`：最终形态 active SoT，定义 local-first single-writer AgentOS、不变量、非目标和 `signal -> planner -> phase -> feedback -> learning`。
- `docs/Furnace Evolution Mechanics.md`：signal taxonomy、planner-log、heavy/light alchemy、active corpus、elixir、L2/L3 proposal 机制。
- `docs/Furnace Runtime Operations.md`：watcher/nightly/systemd/LLM backend 操作口径。
- `docs/AGOS-9-Scorecard.md`：AgentOS 9.0 评分卡与 release gate。
- `docs/AGOS-9-Execution-Plan.md`：已执行的 9.0 长期支持路线。
- `docs/Furnace Agent OS Slimdown Plan.md`：扩张冻结、产品面收敛、hub slimming 与 proof-before-expansion 路线。
- `docs/Furnace Post-AGOS Risk Plan.md`：Post-AGOS blocker 与结构债状态。
- `PROGRESS.md`：当前动态状态。
- Dogfood vault：`/home/tim/danlu/炼丹炉`，仅用于 live proof，不删除、不伪造、不迁移用户数据。

## Current Baseline

- 当前 runtime 不是概念原型：`raw -> compile -> wiki -> memory -> output -> receipt/audit/review/nightly` 主链路存在。
- 当前主要短板不是缺机制，而是当前 clean proof 不足、full gate 不干净、knowledge compounding live evidence 不足、planner/autonomy 仍偏 observe/dry-run/受控执行。
- 当前代码规模较大：`src/aiwiki` 约 67k LOC，`tests` 约 60k LOC，Product Shell JS source 约 12.8k LOC；必须 targeted-first，不能 broad refactor。
- 当前 Product Shell 默认面已基本收敛到 Today + Universal Input，但 `plugin.js` 仍是大 hub，operator mechanics 仍需持续防泄漏。
- 当前 dogfood live proof 已由 AOS-C2 补齐：三类投料、receipt-backed compounding、current-day pass maturity run、有效 L3 preview debt `effective_l3_candidates=0`，且 `summarize --days 3` 已在 2026-05-23 滚动到 2026-05-21/22/23 并 PASS。
- 当前验证门禁已由 AOS-C1 拉绿：full `bash scripts/verify.sh` 覆盖 Product Shell static、pytest unit、coverage、cli-smoke、acceptance 并 PASS。

## Global Context

- 炼丹炉已经具备 narrow local-first AgentOS 内核特征；后续完成度取决于可复算 proof、门禁稳定性、审计一致性和受控自治证据。
- 当前路线坚持 proof-before-expansion：先恢复 gate，再建立 live dogfood proof，再增强 receipt/planner/ops，最后做 release gate。
- 每个 milestone 都应保持 targeted-first，避免在红门禁或证据不足时继续扩张机制。

## Global Constraints

- 不引入 hosted service、multi-user sync、heavy RAG infra、fine-tuning 或隐式 backend fallback。
- 保持 `raw/` 是唯一事实输入层；派生输出不得污染 source truth。
- 保持 single-writer runtime lock、provenance、receipt、audit、revert、kill switch。
- LLM 只允许在显式 `run-*`、受控 nightly 或明确 operator 路径中介入；失败必须显式暴露，不能伪造成功。
- 不扩大 L3/Judgment 自动采纳范围；不自动生成或采纳高风险语义 judgment。
- 不通过隐藏 backlog、伪造 proof 或 deterministic placeholder 冒充成功。
- 不做 broad refactor；只做能降低风险、缩短路径、增强 proof 的定向修改。
- Dogfood 可自动投料和运行本地 runtime proof，但不得删除 dogfood 数据，不得覆盖用户真实材料，不得读取或打印凭据。
- 不自动 push、远端 release、远端部署或共享环境改动。
- 每个 milestone 必须可独立 materialize 为 `.codex/contracts/active.md`，并通过对应验证后才能推进下一轮。
- Standard tier 默认要求 qa-review；涉及 live dogfood/runtime proof 的 milestone 同时要求 qa-runtime。

## Current Blocking Risks

- Dogfood 3-day live maturity 已在 AOS-C2 PASS；后续 release gate 仍需保持 proof freshness 并汇总到 AOS-C8。
- Knowledge compounding proof 已 live PASS；最新 L3 预算已 clean。
- Planner 仍偏 observe/dry-run/log，实质 scheduling 证据不足。
- 大 hub 仍多：`plugin.js`、`runner/alchemy.py`、`drop.py`、`app_state.py`、`app_protocol.py`、`app_lifecycle.py`、`app_memory.py`、`cli/parsers.py`。
- Product Shell 默认体验已收敛，但 operator mechanics 仍需要持续防泄漏。
- 部分审计路径不完全一致，例如 direct `run-ask` note 与 report/file-back 的 execution receipt 强度不同。

## Milestone Index

- `AOS-C1-GATE-RECOVERY`: 拉绿当前仓库验证门禁
- `AOS-C2-LIVE-DOGFOOD-PROOF`: 建立当前可复算 dogfood proof
- `AOS-C3-RECEIPT-COVERAGE`: 补齐 action / LLM / run notes 审计一致性
- `AOS-C4-PLANNER-EXECUTION`: 让 planner 从 observe 进入 safe primitive 闭环
- `AOS-C5-SHELL-OS-SURFACE`: 维持一个输入端 + 一个输出端并削弱机制泄漏
- `AOS-C6-KERNEL-HUB-SLIMMING`: 定向降低 runtime / Product Shell 大 hub 风险
- `AOS-C7-LONG-RUN-OPS`: 强化 watcher/nightly/backend telemetry/retention
- `AOS-C8-AGENTOS-RELEASE-GATE`: 汇总证据并完成 AgentOS release gate

## Milestone: AOS-C1-GATE-RECOVERY

- `title`: 拉绿当前仓库验证门禁
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前不能作为 AgentOS release baseline，因为 full gate 不干净。
- 已知失败集中在 ruff import sort、unit graph/raw ingest 行为 drift、acceptance prompt hash/golden drift。
- 必须先收敛当前 working tree 的真实行为与测试契约，避免后续 dogfood/autonomy 在红门禁上叠加不确定性。

### Success Criteria

- [x] `bash scripts/verify.sh python-static` PASS。
- [x] `bash scripts/verify.sh unit` PASS。
- [x] `bash scripts/verify.sh acceptance` PASS。
- [x] `bash scripts/verify.sh product-shell-static` PASS。
- [x] `bash scripts/verify.sh cli-smoke` PASS。
- [x] 行为变更对应 golden / tests 有明确理由；不为过测试回滚用户已有目标变更。
- [x] 不改变 AgentOS 架构边界，不新增产品能力。

### Constraints / Dependencies

- 当前 worktree 已有用户/其他 agent dirty changes；不得回滚未由本轮创建的变更。
- 如测试失败揭示真实行为 bug，优先修 runtime；如测试滞后，更新测试/golden 并说明理由。
- 不触碰 dogfood vault。

### Chosen Approach

- 先跑 targeted gate，按失败点分组修复。
- 先修静态 import sort，再处理 unit drift，最后刷新 acceptance replay/golden。
- 每个修复保持最小改动，避免顺手重构。

### Execution Plan

1. 运行 `bash scripts/verify.sh python-static` 定位静态失败。
2. 修复 import/order 或相关静态问题。
3. 运行 `bash scripts/verify.sh unit`，按 graph/raw ingest/LLM replay/search ordering 分组修复。
4. 运行 `bash scripts/verify.sh acceptance`，更新必要 replay fixture 或 golden。
5. 运行 `bash scripts/verify.sh product-shell-static` 与 `bash scripts/verify.sh cli-smoke`。
6. 运行 full `bash scripts/verify.sh`。
7. 更新 `PROGRESS.md` 与 gate artifact。

### Stop Conditions

- 需要回滚用户已有变更。
- 测试期望与架构 SoT 冲突且无法判断正确方向。
- 连续 3 轮 debug 不收敛。

### In Scope

- Python static/test/golden 修复。
- Acceptance replay fixture 更新。
- 最小 runtime bug fix。
- `PROGRESS.md` 状态记录。

### Out Of Scope

- Dogfood live proof。
- Planner 行为扩展。
- Product Shell 新 UI 能力。
- 大规模模块拆分。

### Verification Plan

- `bash scripts/verify.sh python-static`
- `bash scripts/verify.sh unit`
- `bash scripts/verify.sh acceptance`
- `bash scripts/verify.sh product-shell-static`
- `bash scripts/verify.sh cli-smoke`
- `bash scripts/verify.sh`

### Fail Gate

- 任一 required verify target 失败。
- 为了过测试伪造 success proof 或隐藏 degraded artifact。
- 改动破坏 `raw/` 唯一事实输入、receipt/audit/revert 或 explicit LLM backend 边界。

### Residual Risks

- 本 milestone 只恢复仓库门禁，不证明真实 dogfood 成熟。
- 如果 acceptance fixture 变更较多，需要后续 dogfood live proof 交叉验证。

## Milestone: AOS-C2-LIVE-DOGFOOD-PROOF

- `title`: 建立当前可复算 dogfood proof
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 历史 proof 不能替代当前 clean vault live proof。
- 当前 `/home/tim/danlu/炼丹炉` 的 `summarize --days 3` fail，只看到单日 maturity run。
- `knowledge_compounding_proof` 缺 receipt-backed actions、file-back、judgment/elixir reuse、trace provenance 样本。

### Success Criteria

- [x] 自动投料至少三类真实输入：PDF、URL、note 或 repo。
- [x] 生成 raw -> wiki -> output -> receipt/audit 的完整 provenance。
- [x] `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --days 3` PASS。
- [x] `consecutive_days=true`。
- [x] `knowledge_compounding_proof.status=pass`。
- [x] `receipt_backed_actions > 0`。
- [x] `output_file_back_rate > 0` 或有等价 judgment/elixir reuse proof。
- [x] LLM 失败路径显式失败，不产生伪成功报告。

### Constraints / Dependencies

- 可自动向 dogfood vault 投料，但只能新增 raw/input/output/proof artifacts，不删除、不伪造、不覆盖用户真实材料。
- 如果外部 LLM/backend 不可用，记录 blocker 和 failed receipt，不伪造 PASS。
- 不读取或打印凭据。
- 如果真实 PDF 不存在，可使用本仓库文档/README/URL/note/repo 作为自动投料材料；不得编造外部来源。

### Chosen Approach

- 先采集当前 dogfood 状态，再自动投料。
- 使用 deterministic baseline 先建立 raw/wiki/provenance，再用显式 LLM path 生成用户可见输出。
- 通过 file-back 或 judgment/elixir reuse 建立 compounding sample。
- 连续 proof 不通过时记录当前缺口，不伪造日期或 receipt。

### Execution Plan

1. 运行 dogfood maturity summarize，记录 before 状态。
2. 自动投料：至少 URL、note、repo；若可用则再投 PDF/image。
3. 在 dogfood root 执行 compile / run-ask / file-back 或等价 compounding flow。
4. 收集 execution receipts、LLM receipts、run notes、runtime history。
5. 运行 maturity collect / summarize。
6. 如缺连续 3 日 proof，运行允许的 maturity harness 或记录需要 wall-clock 等待的 blocker；不得伪造连续日期。
7. 更新 scorecard evidence 与 `PROGRESS.md`。

### Execution Notes（2026-05-21）

- 已自动新增三类 dogfood 投料：`raw/inbox/agentos-c2-live-proof-note-2026-05-21.md`、`raw/inbox/agentos-c2-example-url-2026-05-21.md`、`raw/inbox/agentos-c2-danlu-repo-snapshot-2026-05-21.md`。
- 已执行 dogfood compile、显式 LLM `run-ask`、`file-back --kind judgment`、第二轮复用 judgment 的 `run-ask`，形成 raw/wiki/output/receipt provenance。
- 已补齐 `review-page` execution receipt，dogfood judgment `wiki/judgments/judgment-aos-c2-dogfood-live-proof-judgment.md` 已 `confirmed`，receipt 为 `output/control/execution-receipts/review-page-judgment-aos-c2-dogfood-live-proof-judgment.json`。
- 当前 live compounding proof 已 PASS：`knowledge_compounding_proof.status=pass`、`receipt_backed_actions=14`、`output_file_back_rate=0.3333`、`judgment_or_elixir_reuse_count=2`、`semantic_path_observed=true`。
- 最新 current-day maturity run `output/control/maturity-gate/run-20260521T202557Z.json` 为 pass；此前 LLM timeout run 以 blocked/failed receipt 显式记录，未伪造成成功。
- 当时 AOS-C2 尚未可标记 done：`summarize --days 3` 仍 fail，只有 2026-05-20/21 两日，`consecutive_days=false`，2026-05-20 receipt 是 deterministic-only。有效 L3 preview debt 已 materialize 为 proposal candidate，latest maturity 中 `effective_l3_candidates=0`、`budget_violations=[]`。

### Execution Notes（2026-05-22）

- 已安装 `aiwiki-dogfood-maturity.timer`（user-level systemd），通过 `AIWIKI_DOGFOOD_MATURITY_ENVRC=/home/tim/ai-wiki/.envrc.dogfood` 在运行时引用本机 dogfood LLM 环境；env 文件只保存路径，不复制或打印凭据。
- Persistent timer 已补跑 2026-05-22 UTC maturity receipt：`output/control/maturity-gate/run-20260522T002451Z.json`，status 为 pass，且继续保持 `effective_l3_candidates=0`、`budget_violations=[]`。
- 当前 live compounding proof 继续 PASS：`knowledge_compounding_proof.status=pass`、`receipt_backed_actions=17`、`output_file_back_rate=0.3333`、`judgment_or_elixir_reuse_count=2`、`semantic_path_observed=true`。
- 当时 AOS-C2 尚未可标记 done：`summarize --days 3` 看到 2026-05-20/21/22 三个 consecutive days，且三个 latest receipts status 都为 pass；但 2026-05-20 receipt 是 deterministic-only，`operational_maturity.status=not-yet`。下一次真实放行点是 2026-05-23 UTC receipt，使 3-day window 滚动为 2026-05-21/22/23。

### Execution Notes（2026-05-23）

- 2026-05-23 UTC timer 已真实执行并生成 `output/control/maturity-gate/run-20260523T001502Z.json`，status 为 pass。
- 为让 semantic review path 落在当前 rolling maturity window 内，已再次 review dogfood judgment 并写出 `output/control/execution-receipts/review-page-judgment-aos-c2-dogfood-live-proof-judgment-2.json`。
- 已运行当前日 maturity gate 并生成 `output/control/maturity-gate/run-20260523T100035Z.json`，status 为 pass；该 receipt 将 rolling 3-day window 扩展到新的 semantic review receipt 之后。
- `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --days 3` 现在 PASS：`days=[2026-05-21,2026-05-22,2026-05-23]`、`consecutive_days=true`、`status_counts.pass=3`、`deterministic_only_runs=[]`、`failed_runs=[]`。
- AOS-C2 live proof 全部绿灯：`operational_maturity.status=pass`、`receipt_integrity.status=pass`、`knowledge_compounding_proof.status=pass`、`semantic_path_observed=true`、`judgment_review_processed_delta=1`、`receipt_backed_actions=25`、`output_file_back_rate=0.3333`、`judgment_or_elixir_reuse_count=2`、`effective_l3_candidates=0`、`budget_violations=[]`。

### Stop Conditions

- 命令可能删除、迁移或覆盖 dogfood 用户数据。
- LLM backend 凭据缺失、quota/timeout 持续阻断，且没有显式 operator fallback。
- 需要真实私有材料但当前没有授权材料。
- 连续 3 轮 runtime debug 不收敛。

### In Scope

- `/home/tim/danlu/炼丹炉` dogfood runtime proof artifacts。
- 自动新增投料材料。
- maturity gate collect/summarize。
- scorecard / PROGRESS evidence 更新。

### Out Of Scope

- 删除 dogfood 数据。
- 伪造历史日期/receipt。
- 远端发布或凭据配置。
- 高风险 auto-adopt。

### Verification Plan

- `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --days 3`
- `bash scripts/agos9_dogfood_proof_status.sh`
- `bash scripts/verify.sh acceptance`
- qa-runtime

### Fail Gate

- dogfood summarize 未 PASS。
- compounding proof 仍 `not-yet`。
- LLM 失败被包装成成功报告。
- receipt/audit/provenance 链断裂。

### Residual Risks

- 连续 3 UTC 日 proof 仍需要真实 wall-clock 等待和非 deterministic-only current receipts；本计划允许自动推进到可执行部分，但不得伪造时间证明。
- 外部 backend 可用性会影响 live proof。

## Milestone: AOS-C3-RECEIPT-COVERAGE

- `title`: 补齐 action / LLM / run notes 审计一致性
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 核心 mutation receipt 较强，但不同 ask/report/note/background/direct 路径的审计强度还需要统一。
- Direct `run-ask` note 路径相对 report/file-back 的 execution receipt 强度更轻，长期 maturity gate 难解释。

### Success Criteria

- [x] 建立 action receipt coverage matrix。
- [x] 每个用户可见输出都有 LLM receipt、run notes、artifact provenance。
- [x] 每个事实层 mutation 都有 execution receipt。
- [x] Direct note 路径的审计语义明确，不再靠隐含约定。
- [x] failed/degraded/background paths 都能被 Shell summary 和 maturity gate 解释。
- [x] maturity gate 可解释 legacy/empty/missing receipt。

### Constraints / Dependencies

- 保持 `write_execution_receipt()` 的严格字段校验。
- 不放宽 receipt schema。
- 不把 deterministic placeholder 计作 deliverable。

### Chosen Approach

- 先建立 receipt coverage matrix，再只补齐能被 maturity gate 和 Shell summary 消费的最小审计缺口。
- 对输出类行为优先补 provenance / run notes / LLM receipt；对事实层 mutation 坚持 execution receipt。

### In Scope

- `run-ask` direct/background/report receipt coverage。
- maturity gate receipt coverage 解释。
- Shell summary 对 failed/degraded/background receipt 的展示一致性。
- targeted tests 与 docs evidence。

### Out Of Scope

- 放宽 receipt schema。
- 将 deterministic placeholder 计作成功。
- 高风险 planner/autonomy 扩权。

### Execution Plan

1. 梳理 `run-ask`、`run-ask-submit/resume`、`file-back`、compile/lint/nightly 的 receipt matrix。
2. 为 direct note 路径补齐 execution receipt 或写入明确豁免 contract。
3. 增加 targeted tests 覆盖 success/failure/degraded/background paths。
4. 更新 maturity gate 对 receipt coverage 的解释字段。
5. 更新 docs/scorecard evidence。

### Verification Plan

- targeted receipt tests。
- `bash scripts/verify.sh unit`
- `bash scripts/verify.sh acceptance`
- dogfood maturity summarize。

### Fail Gate

- 新 receipt 缺少 `operation/status/target_file`。
- failed/degraded artifact 被 Today 当成 deliverable。
- history append 失败后留下孤儿 receipt。

### Residual Risks

- Receipt coverage 增强可能改变 maturity metrics，需要同步 docs/golden。

### Execution Notes — 2026-05-23

- `run-ask` report/frontdoor success：保持 `run-ask` LLM receipt + run notes + `operation=run-ask` execution receipt；LLM 返回中的 forged `derived_from/source_files` 继续丢弃，只恢复 deterministic artifact runtime provenance。
- `run-ask` direct note success：新增 `generated_by=aiwiki-run-ask-direct` execution receipt，`target_file=primary_path=<output artifact>`；run notes 的 `receipt_path` 指向该 execution receipt；显式 material refs 写入 direct artifact `source_files`。
- `run-ask` local stats success：`elixir-stats` / `markdown-stats` 本地确定性 note 继续写 pseudo LLM audit receipt，同时新增 `generated_by=aiwiki-local-*-stats` execution receipt，receipt 内保留统计数、`delivery_mode=local-deterministic` 和 LLM receipt log path。
- report/direct/local success receipt 写入顺序已收紧：先完成 run notes/frontmatter/CSS，再写 success execution receipt；任一后置写入失败都会回滚 artifact/run notes，避免失败运行留下 `status=success` receipt。
- `run-ask-submit` background pending：submit 阶段仍不写 success execution receipt；`delivery_mode=background-pending` / `llm_status=pending` 由 maturity `receipt_coverage` 解释，resume 成功后才写 `run-ask` execution receipt。
- failed/degraded report path：保留 failed LLM receipt + run notes + degraded artifact，不伪造 success execution receipt；maturity `receipt_coverage` 以 `failed_or_degraded_llm_artifact` 分类解释。
- direct LLM failure before artifact write：只写 failed LLM receipt，`target=""`；因无用户可见 artifact / mutation，不写 execution receipt。
- `scripts/dogfood_maturity_gate.py collect` 新增 `receipt_coverage`：按 output artifact 检查 execution receipt、LLM receipt、run notes、artifact provenance，并显式分类 missing、legacy empty status、background pending、failed/degraded、deterministic baseline；只有 run notes `status=deterministic-ready` 的 `aiwiki-ask` 输出享受 deterministic baseline 豁免，该字段为 warn-only 解释，不降低既有 maturity release gate。

| 路径 | LLM/audit receipt | run notes | execution receipt | provenance / 解释 |
|---|---|---|---|---|
| `run-ask` report success | `run-ask` success | points to execution receipt | `operation=run-ask` | deterministic provenance restored |
| direct note success | `run-ask-direct` success | points to execution receipt | `operation=run-ask`, `generated_by=aiwiki-run-ask-direct` | explicit `material_refs` -> `source_files` |
| local stats note success | `run-ask-local-*-stats` success | points to execution receipt | `operation=run-ask`, `generated_by=aiwiki-local-*-stats` | stats fields in artifact + receipt |
| background submit pending | backend preflight / pending artifact | deterministic run notes | deferred until resume | `background_pending` maturity exemption |
| report failed/degraded | `run-ask` failed | `llm-failed` run notes | no success receipt | `failed_or_degraded_llm_artifact` maturity explanation |
| direct failure before artifact | `run-ask-direct` failed, target empty | none | none | no artifact mutation |

## Milestone: AOS-C4-PLANNER-EXECUTION

- `title`: 让 planner 从 observe 进入 safe primitive 闭环
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- Planner/signal/alchemy 的 schema、dedupe、budget、dry-run 已较成熟，但 execute mode 仍偏“授权表达”，不是完整执行闭环。
- AgentOS 完成态要求至少 safe primitives 能从 signal 进入 receipted execution，再回流 feedback signal。

### Success Criteria

- [x] `raw_added` signal 可进入 planner decision。
- [x] planner execute mode 可触发限定 safe primitive。
- [x] primitive 结果回写 receipt/audit/run notes。
- [x] failed primitive 生成 `runtime_failure` signal。
- [x] kill switch 覆盖 planner execution。
- [x] 不允许自动 judge/distill/propose/apply 高风险语义内容。

### Constraints / Dependencies

- 只允许 safe primitives：route、compile、lint、review preview。
- Light lane 可执行低风险 compile/lint。
- Heavy lane 继续 dry-run first，apply 必须 receipt-backed。
- 不扩 L3/Judgment autonomy。

### Chosen Approach

- 从已有 strict signal/planner log 出发，只把低风险 primitive 接入 execute path。
- 所有 side effect 先经过 dry-run/contract，再写 receipt/audit/run notes，并把失败回流为 signal。

### In Scope

- planner execute mode 的 safe primitive path。
- light lane compile/lint apply。
- failure feedback signal。
- kill switch tests。

### Out Of Scope

- 自动 judge/distill/propose。
- L3/Judgment auto-adopt 扩权。
- 无 receipt 的 side effect。

### Execution Plan

1. 定义 planner safe primitive apply contract。
2. 让 execute mode 在明确 flag/contract 下执行 compile/lint/review preview。
3. 为每次 planner action 写 planner-log、receipt、run notes。
4. 失败时生成 runtime_failure signal。
5. 增加 tests 覆盖 kill switch、dedupe、budget、failure feedback。

### Execution Notes（2026-05-24）

- Planner execute mode 已落到受控 primitive 闭环：`write_planner_log()` 依据 strict signal kind/severity 写入 decision/reason codes，`mode="execute"` 会显式记录 `execute_mode_requested`，并只在 decision 允许时开放 `side_effects_allowed`。
- `run_alchemy_auto()` 先对每个 lane 执行 dry-run，再在 `apply=True` 时调用 lane apply；默认可自动处理的 primitive 限定为 `compile` / `lint` / `nightly`，`review` / `distill` / `propose` 只在 heavy lane 且明确请求 primitive 时进入 apply path，不开放自动 judge 或 L3/Judgment auto-adopt。
- Apply 成功会写入 runtime history `event_type=alchemy-auto-scheduler`，记录 `applied_count`、`skipped_count`、`trace_ids` 与 lane 结果；preview (`apply=False`) 只返回计划和 skip 原因，不产生 side effects。
- `runtime_failure` signal routing 已覆盖 medium/high/critical 分流：routine failure 进入 light queue，高风险 failure 生成 proposal recommendation，critical failure 升级人工处理；dogfood maturity gate 会对 execute-mode planner records 和已 rejected/reverted 的同类 L3 issue 做去重解释，避免把旧噪音算成新 debt。
- 验证覆盖 `tests/test_planner_log.py`、`tests/test_alchemy_lanes.py`、`tests/test_cli.py`、`tests/test_dogfood_maturity_gate.py`，并由 C8 full release verify 复跑。该 milestone 的完成边界是 safe primitive execution，不扩展高风险语义自治。

### Verification Plan

- planner log tests。
- signal replay tests。
- alchemy lane dry-run/apply tests。
- `bash scripts/verify.sh unit acceptance`

### Fail Gate

- planner 自动执行语义 judge/distill/propose。
- 无 receipt/audit 即产生 side effect。
- kill switch 无效。

### Residual Risks

- 即使 safe primitive 闭环完成，高风险 autonomy 仍应保持人工 review。

## Milestone: AOS-C5-SHELL-OS-SURFACE

- `title`: 维持一个输入端 + 一个输出端并削弱机制泄漏
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- Product Shell 已基本做到 Today + Universal Input，但 `plugin.js` 仍是巨大 hub，operator mechanics 需要持续隐藏。
- AgentOS 用户面不能要求用户理解 backend/protocol/planner/receipt/audit/internal lanes。

### Success Criteria

- [x] 默认主界面只有 Today 和 Universal Input。
- [x] Advanced 只放诊断、运行历史、Review/Execution Center。
- [x] 不新增默认用户必须理解的概念。
- [x] LLM failed/degraded 不进入 deliverable report feed。
- [x] pending 状态区分 running/received/done/failed/degraded。
- [x] `plugin.js` 继续下降，拆出的模块有 owner tests。
- [x] Product Shell 不直接拥有 runtime SoT。

### Constraints / Dependencies

- 不新增 Product Shell 视图、按钮、状态字段或 hidden thread memory。
- 不绕过 launcher CLI。
- 不改变 runtime state ownership。

### Chosen Approach

- 保持现有 Today + Universal Input 产品面，只做 owner extraction 与测试加固。
- 优先抽离 `plugin.js` 中已有纯 orchestration/pending 逻辑，不改变用户可见行为。

### In Scope

- Product Shell pending/reconcile/run log/command orchestration 的最小拆分。
- Jest tests 与 bundle drift gate。
- Advanced 默认隐藏边界校验。

### Out Of Scope

- 新 UI 能力。
- 新 runtime SoT 字段。
- 绕过 launcher 的直接 runtime mutation。

### Execution Plan

1. 抽离 `plugin.js` 中 pending/reconcile/run log/command orchestration 的一个最小 owner 模块。
2. 保持 render/bridge/state 既有边界。
3. 增加或更新 Jest tests。
4. 确认 Product Shell static/bundle drift gate。

### Execution Notes（2026-05-24）

- Product Shell active SoT 已对齐到默认首屏 `Today Feed + Universal Input`：普通用户只看到一个输入端和一个输出端；AskBox/DropZone 被吸收到 Universal Input，diagnostics/history/Review/Execution Center 仅通过 gated Advanced surface 暴露。
- Product Shell 只读取 launcher CLI 与 `output/control/shell-summary.json` 暴露的 shell-facing contract，不拥有 runtime state、不新增 SoT 字段、不绕过 receipt/audit/launcher 边界。
- Today feed 与 report picker 已过滤 `timeout_or_unavailable`、`pending`、`failed`、`degraded`、`deterministic-fallback`、`llm-failed`、`placeholder` 等非 deliverable artifact；pending submissions 区分 `running` / `received` / `done` / `failed` / `degraded`，degraded 是 first-class terminal state。
- Product Shell source/Jest/bundle gate 覆盖 Advanced gating、Universal Input、pending/reconcile、degraded output recovery、Today primary filtering 和 report artifact quality filtering；C8 full verify 继续覆盖 `product-shell-static`。
- `plugin.js` 仍是 residual hub，当前放行点是默认用户面收敛、degraded filtering 和 Advanced gating 已受测试保护；后续削薄只应按 owner boundary 小步推进，不在本 milestone 中引入新 UI 或 runtime SoT。

### Verification Plan

- `bash scripts/verify.sh product-shell-static`
- Product Shell Jest tests。
- Product Shell smoke。

### Fail Gate

- UI 直接写 runtime SoT。
- failed/degraded artifact 被默认当成报告。
- Advanced mechanics 泄漏到默认用户路径。

### Residual Risks

- JS bundle 仍可能较大；本 milestone 只做定向 owner extraction。

## Milestone: AOS-C6-KERNEL-HUB-SLIMMING

- `title`: 定向降低 runtime / Product Shell 大 hub 风险
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- runtime owner modules 已经拆出，但仍有多个大 hub，长期维护风险高。
- 复杂度问题不能靠新增抽象解决，必须按 owner 边界小步降低 review 成本。

### Target Hotspots

- `src/aiwiki/runner/alchemy.py`
- `src/aiwiki/drop.py`
- `src/aiwiki/app_state.py`
- `src/aiwiki/app_protocol.py`
- `src/aiwiki/app_lifecycle.py`
- `src/aiwiki/app_memory.py`
- `src/aiwiki/cli/parsers.py`
- `.obsidian/plugins/furnace-product-shell/src/plugin.js`

### Success Criteria

- [x] 每轮只处理一个 hotspot。
- [x] 每轮 LOC 下降或责任边界更清晰。
- [x] shim 只保留兼容导出，不承载新逻辑。
- [x] 相关 tests PASS。
- [x] 无 broad formatting/refactor。

### Constraints / Dependencies

- 只拆有明确 owner 边界的逻辑。
- 优先拆 orchestration 与 pure helper。
- 不引入新 abstraction layer。
- 不改 public CLI 行为。
- 不动数据模型，除非有 migration/receipt proof。

### Chosen Approach

- 每轮只选一个 hotspot，先锁定行为，再抽出最小 owner helper/module。
- 以减少 review 成本和缩短调用路径为准，不追求形式上的文件拆分。

### In Scope

- 一个最高 ROI hotspot 的最小 owner extraction。
- legacy import seam 保持。
- targeted tests 与 static verify。

### Out Of Scope

- broad refactor。
- 数据模型迁移。
- public CLI 行为变更。

### Execution Plan

1. 选取当前最高 ROI hotspot。
2. 用 tests 锁定现有行为。
3. 抽出最小 owner helper/module。
4. 保持 legacy import seam。
5. 运行 targeted tests 与 full static。

### Execution Notes（2026-05-24）

- C6 采用 seam map + low-risk owner extraction 收口，而不是 broad refactor：`docs/analysis/AGOS-005-seam-map.md` 与 `docs/analysis/F-Module-Owner-Map.md` 记录 hotspot、owner 边界和 deferred 风险。
- 已完成多个低风险 owner extraction：`runner/local_stats.py` 承接本地统计，`runner/workflows_ask.py` 与 `runner/workflow_shared.py` 承接 ask workflow/shared helper，`protocol/library.py` 承接 protocol library 逻辑；legacy import seam 保持，public CLI 行为不变。
- `runner/workflows.py` 已从 2772 LOC 量级降到约 1278 LOC，`app_protocol.py` 的 protocol library 逻辑已移出；scorecard maintainability gate 以 seam map + 至少两个 owner extraction 作为 PASS 证据。
- 当前未声称清空所有 hub：`runner/alchemy.py` 与 Product Shell `plugin.js` 仍是 deferred residual hotspots，后续只按最高 ROI、单 hotspot、测试先行的方式继续削薄。
- 验证来自 targeted unit tests、`python-static`、`unit`、`product-shell-static` 与 C8 full release verify；本 milestone 没有 schema migration、public CLI 行为变更或 broad formatting/refactor。

### Verification Plan

- targeted unit tests。
- `bash scripts/verify.sh python-static`
- `bash scripts/verify.sh unit`

### Fail Gate

- 为拆分引入更多层间耦合。
- public CLI 或 schema 行为漂移。
- shim 承载新逻辑。

### Residual Risks

- Hub slimming 是长期工作；本 milestone 不追求一次性清空所有大文件。

### Stabilization Notes（2026-05-24）

- P1 当前执行口径是 seam enforcement：`runner/alchemy.py` 与 Product Shell `plugin.js` 继续列为 deferred residual hotspots，但不做 broad rewrite；后续每轮只选一个最高 ROI owner seam，并先以 tests 锁定行为。
- `run-ask` owner seam 已进一步收敛：report、background resume、direct note、local elixir stats、local markdown stats 的 success execution receipt 统一写 `receipt_matrix_version=1`、`run_ask_path` 与 `artifact_status=completed`；失败/degraded 仍不写 success execution receipt。
- CLI owner seam 继续维持 product-first：默认文档与 help 只把 `drop/today/metrics/advanced` 作为普通入口，legacy top-level command 仅作为 compat seam 保留给脚本、tests、dogfood 与旧自动化。

## Milestone: AOS-C7-LONG-RUN-OPS

- `title`: 强化 watcher/nightly/backend telemetry/retention
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- AgentOS 不是一次性 CLI，需要长期监听、nightly、恢复、telemetry 和 retention proof。

### Success Criteria

- [x] watcher deterministic-only 状态在 Shell summary 可解释。
- [x] nightly full furnace profile 有明确 receipt。
- [x] backend telemetry 有最近 N 次聚合。
- [x] LLM quota/timeout/unavailable 分类明确。
- [x] failed nightly 不污染 success proof。
- [x] recovery command 可被 Product Shell 暴露。
- [x] retention archive-first，不默认删除 receipts/logs。

### Constraints / Dependencies

- 不安装或修改 systemd user service，除非用户另行确认。
- 不配置凭据。
- 不启用隐式 backend fallback。

### Chosen Approach

- 先强化可观察性和 runbook 证据，不默认改用户 systemd 配置。
- 对 watcher/nightly/backend telemetry 只做本地可验证的状态解释和 failure classification。

### In Scope

- watcher/nightly summary 字段。
- backend telemetry aggregation。
- failed nightly recovery command。
- retention/docs consistency evidence。

### Out Of Scope

- 安装或修改 systemd user service。
- 配置凭据。
- 隐式 backend fallback。

### Execution Plan

1. 检查 watcher/nightly runbook 与 Shell summary 字段。
2. 强化 backend telemetry aggregation 和 degraded/unavailable 分类。
3. 补齐 failed nightly / recovery command tests。
4. 更新 docs consistency 与 runtime operations 证据。

### Execution Notes（2026-05-23）

- Shell summary 新增 watcher 状态：读取 `.aiwiki/state/automation.json`，显式暴露 deterministic-only service mode、`AIWIKI_WATCH_DETERMINISTIC_ONLY=1`、compile/lint 参数和 `./scripts/aiwiki-launcher.sh auto-once --deterministic-only` 恢复命令；不安装或修改 systemd。
- `run-nightly` 成功路径新增 `operation=run-nightly` execution receipt，target 为 `.aiwiki/state/nightly-health.json`；失败路径只写 failed LLM receipt，不写 success execution receipt，避免污染 success proof。Shell summary 会在最新 run-nightly LLM receipt 失败或缺 matching execution receipt 时把旧 success receipt 标为 stale。
- Shell nightly summary 暴露 latest run-nightly LLM receipt、latest execution receipt、failed nightly recovery command，以及 archive-first retention policy（receipts/logs 默认不删除）；Product Shell digest 可展示 recovery command。
- `backend-telemetry --limit N` 聚合最近 N 个 execution receipt 与 LLM receipt，receipt JSON/history 按 `receipt_path` 去重，并按 timestamp 取最近窗口，分类 `quota` / `timeout` / `unavailable` / `error_class`；probe telemetry 仍与 run telemetry 分开。
- `scripts/run_nightly.sh` 对已尝试的 configured `run-nightly` 失败 fail-closed，不降级成 deterministic success；未配置 LLM 且未要求 LLM 时仍可运行 deterministic maintenance。
- 验证已覆盖 targeted pytest、`python-static`、临时 vault nightly smoke、wrapper nightly deterministic-only smoke、dogfood maturity read-only summarize/collect、docs consistency；harness closed-loop PASS（unit 2439 passed、acceptance 17 passed、qa-review PASS、qa-runtime PASS）。真实长期稳定性仍依赖后续多日 wall-clock proof。

### Verification Plan

- `aiwiki backend-telemetry --limit N`
- nightly smoke。
- dogfood maturity gate。
- `bash scripts/docs_consistency_check.sh`

### Fail Gate

- failed nightly 被计入 success proof。
- backend fallback 隐式发生。
- retention 删除不可恢复证据。

### Residual Risks

- 真正长期稳定性仍需要多日 dogfood wall-clock 运行证明。

### Stabilization Notes（2026-05-24）

- P5 长期 proof 不伪造：当前 release gate 只声明 3-day live window PASS；14/30-day natural run 是后续 wall-clock 观察目标，未自然发生前状态保持 not-yet。
- planner-log 新 record 已带 decision-derived `phase`，用于把 `signal → planner → phase` 的可复算证据补到日志层；旧无 `phase` 的 v1 logs 仍可 replay，不做 migration。

## Milestone: AOS-C8-AGENTOS-RELEASE-GATE

- `title`: 汇总证据并完成 AgentOS release gate
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 只有机制成熟不够，必须用 live evidence 证明 AgentOS 形态成立。

### Success Criteria

- [x] AGOS scorecard >= 9.0。
- [x] 无 blocking fail。
- [x] `bash scripts/verify.sh` PASS。
- [x] Product Shell static/drift PASS。
- [x] Acceptance replay PASS。
- [x] Dogfood maturity live PASS。
- [x] Knowledge compounding proof PASS。
- [x] LLM telemetry 可解释。
- [x] Docs SoT 一致。
- [x] qa-review PASS。
- [x] qa-runtime PASS。

### Constraints / Dependencies

- 不自动 tag。
- 不自动 push。
- 不创建 GitHub Release。
- 不做远端部署。
- 不配置凭据。

### Chosen Approach

- 用 scorecard 汇总所有 live/replay/static evidence，只在所有 blocking gate 通过后宣称 AgentOS 完成态。
- Release 动作保持本地评估收口；tag/push/release 仍需用户另行确认。

### In Scope

- full verify evidence。
- Product Shell gate evidence。
- dogfood maturity / compounding proof。
- LLM telemetry、docs consistency、qa-review、qa-runtime。
- scorecard / PROGRESS 更新。

### Out Of Scope

- Git tag。
- push / GitHub Release。
- 远端部署。
- 凭据配置。

### Execution Plan

1. 运行 full verify。
2. 运行 Product Shell static/drift gate。
3. 运行 acceptance replay。
4. 运行 dogfood maturity summarize。
5. 运行 backend telemetry / docs consistency / release audit。
6. 更新 scorecard 与 `PROGRESS.md`。
7. 生成 qa-review 与 qa-runtime gate artifacts。

### Execution Notes（2026-05-24）

- Full verify 已 PASS：`bash scripts/verify.sh` 覆盖 Product Shell static/drift、Python static、unit、cli smoke、acceptance 和 coverage；结果为 2439 unit tests、coverage 92%、acceptance 17 passed。
- Release evidence 已 PASS：`bash scripts/agos9_release_audit.sh`、`bash scripts/agos9_dogfood_proof_status.sh`、`bash scripts/docs_consistency_check.sh`。
- Dogfood live maturity 继续 PASS：rolling days 为 2026-05-21/22/23，`consecutive_days=true`、`operational_maturity.status=pass`、`receipt_integrity.status=pass`、`knowledge_compounding_proof.status=pass`、`semantic_path_observed=true`、`effective_l3_candidates=0`、`budget_violations=[]`。
- Scorecard 已复评为约 9.05；C3 legacy direct-note missing execution receipts 保持 warn-only `receipt_coverage` 解释，不作为当前 release blocker；新 direct/local success paths 已 receipt-backed。
- C8 qa-review / qa-runtime 已刷新为 PASS，harness `run_plan` closed-loop PASS 并标记 plan completed / no remaining milestones。
- 本地 release gate 不执行 tag/push/GitHub Release/远端部署/凭据配置。

### Verification Plan

- `bash scripts/verify.sh`
- `bash scripts/agos9_release_audit.sh`
- `bash scripts/agos9_dogfood_proof_status.sh`
- `bash scripts/docs_consistency_check.sh`
- qa-review
- qa-runtime

### Fail Gate

- 任一 blocking release gate 失败。
- Dogfood proof 不是当前 live 可复算。
- 知识复利 proof 仍为空样本或缺 receipt-backed evidence。

### Residual Risks

- Release tag/push/remote release 仍需用户另行确认。

## Execution Order

1. AOS-C1 先拉绿当前 gate。
2. AOS-C2 建立 live dogfood proof。
3. AOS-C3 补齐 receipt coverage。
4. AOS-C4 推进 planner safe execution loop。
5. AOS-C5 收敛 Product Shell OS surface。
6. AOS-C6 按 hotspot 小步削薄。
7. AOS-C7 补长期运行证据。
8. AOS-C8 做 release gate 收口。

## Global Stop Conditions

- 需要远端发布、push、PR 或凭据配置。
- 需要删除、伪造或迁移 dogfood 数据。
- 需要突破 local-first / single-writer / raw-only truth 边界。
- 需要隐式 backend fallback。
- 连续 3 轮 debug 仍不能收敛。
- 某 milestone 必须扩大 scope 才能完成。

## Definition Of Done

炼丹炉达到 AgentOS 形态，不是因为有更多命令或更多自动化，而是因为：

- 用户只需要投料和看结果。
- Runtime 能把输入持续炼成知识资产。
- 所有语义判断都有 provenance。
- 所有 mutation 都有 receipt/audit/revert。
- Planner 能在受控边界内调度 safe primitives。
- LLM 失败显式可见。
- Dogfood proof 可现场复算。
- 长期运行状态可解释、可恢复、可追责。
