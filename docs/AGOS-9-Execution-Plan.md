# Engineering Plan — AGOS 9.0 Long-Term AgentOS Support

## Goal

把炼丹炉从当前约 7.8/10 的强 local-first runtime，推进到可长期支持、可现场复算、可受控自治的 9.0/10 AgentOS。核心路径是先建立证据门槛和 dogfood proof，再稳定 Product Shell 与文档 SoT，随后定向降低 runtime 复杂度，并让 signal/planner/LLM telemetry 真正支撑长期自治。

## Architecture Inputs

- `README.md`：当前炼丹炉 runtime 主线、CLI taxonomy、五层文件模型和开发者模块图。
- `PROGRESS.md`：2026-05-20 当前 dogfood、Product Shell、LLM fallback、graph、harness 与验证状态。
- `.codex/contracts/active.md`：当前 contract 已完成 dogfood shell context、run-ask fallback removal、本地事实统计、direct note context retrieval。
- `docs/Furnace Agent Architecture.md`：炼丹炉最终形态 active SoT，定义 local-first single-writer AgentOS、不变量、非目标和 `signal -> planner -> phase -> feedback -> learning`。
- `docs/Furnace Evolution Mechanics.md`：signal taxonomy、planner-log、heavy/light alchemy、active corpus、elixir、L2/L3 proposal 机制。
- `docs/Furnace Runtime Operations.md`：watcher/nightly/systemd/LLM backend 操作口径。
- `docs/Furnace Next Direction Post-P4.md`：当前真实差距校准，尤其 clean dogfood vault proof、投资 PDF、多周自然运行和 backend 重测。
- `docs/Furnace Elixir.md`：金丹终局 thesis；需在后续 milestone 中处理历史口径与当前实现差异。
- Local release baseline：`v0.3.0-agentos-baseline`，在进入本计划前标记当前 HEAD，作为后续 9 分路线的回溯基线。

## Global Context

- 当前项目已经不是概念原型：`raw -> compile -> wiki -> memory -> output -> receipt/audit/review/nightly` 主链路存在，测试和治理面较强。
- 当前主要短板不是缺机制，而是缺当前 clean dogfood 可复算 proof、Product Shell 稳定 gate、planner 实质调度证据、backend telemetry 和文档 SoT 收敛。
- 当前代码规模较大：`src/aiwiki` 约 66k 行，`tests` 约 60k 行，Product Shell source JS 约 12.8k 行；后续必须 targeted-first，不能 broad refactor。
- 项目默认使用 `.codex` harness artifact root；本计划可由 `HARNESS_DIR=.codex bash scripts/run_plan.sh --plan-file .codex/plans/active.md` 推进。

## Global Constraints

- 不引入 hosted service、multi-user sync、heavy RAG infra、fine-tuning 或隐式跨 backend routing。
- 保持 `raw/` 是唯一事实输入层；派生输出不得污染 source truth。
- 保持 single-writer runtime lock、provenance、receipt、audit、revert、kill switch。
- LLM 只允许在显式 `run-*`、受控 nightly 或明确 operator 路径中介入；失败必须显式暴露，不能伪造成功。
- 不默认读取、打印或提交凭据；不自动 push、远端 release、远端部署或共享环境改动。
- Dogfood runtime 可使用 `/home/tim/danlu/炼丹炉` 作为 `--root`，但不得删除或伪造 dogfood 数据。
- 每个 milestone 必须可独立 materialize 为 `.codex/contracts/active.md`，并通过对应验证后才能推进下一轮。
- Standard tier 默认要求 qa-review；需要 live dogfood/runtime 证据的 milestone 同时要求 qa-runtime。

## Milestone Index

- `AGOS-001-SCORECARD`: 建立 9.0 AgentOS 评分卡与 release gate
- `AGOS-002-DOGFOOD-PROOF`: 重建当前 clean dogfood 可复算 proof
- `AGOS-003-SHELL-STABILITY`: Product Shell 稳定化与 bundle/source drift gate
- `AGOS-004-DOCS-SOT`: 文档 SoT 收敛与历史口径隔离
- `AGOS-005-RUNTIME-SLIM`: Runtime legacy hub 定向瘦身
- `AGOS-006-PLANNER-ROUTING`: Planner / signal routing 实质化
- `AGOS-007-LLM-TELEMETRY`: Backend telemetry 与 LLM 可靠性硬化
- `AGOS-008-LONG-RUN`: 长期运行、恢复和保留策略硬化
- `AGOS-009-RELEASE-GATE`: 9.0 AgentOS release gate 与最终收口

## Milestone: AGOS-001-SCORECARD

- `title`: 建立 9.0 AgentOS 评分卡与 release gate
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前“7.8/10 -> 9.0/10”仍是综合判断，缺少可执行评分卡。
- 后续 dogfood、Product Shell、planner、telemetry、docs、maintainability 都需要统一 PASS/FAIL 口径，否则容易继续堆机制但无法证明 9 分。
- 必须先定义 evidence gate，再开始大规模修补。

### Success Criteria

- [x] 新增或更新一份 AgentOS 9.0 scorecard，覆盖 dogfood、Product Shell、runtime、planner、LLM、governance、maintainability、docs 八个维度。
- [x] 每个评分维度都有明确 PASS/FAIL 条件、证据路径、验证命令或 artifact。
- [x] 9.0 release gate 明确要求 clean dogfood proof、Product Shell drift gate、LLM telemetry、planner receipt、docs consistency、qa-review。
- [x] `README.md` 或 active architecture doc 能指向 scorecard，避免评分口径散落在对话中。
- [x] 不改变 runtime 行为，只建立评分与证据 contract。

### Constraints / Dependencies

- 只能改文档、scorecard、可选轻量 verify metadata；不改 runtime 逻辑。
- Scorecard 不能把未来未实现能力标为 PASS。
- 评分必须区分历史 PASS、当前可复算 PASS、fixture/replay PASS、live dogfood PASS。

### Questions / Assumptions

- 假设 9.0 不要求 hosted/multi-user/cloud 能力，仍坚持 local-first single-writer。
- 假设当前 release baseline `v0.3.0-agentos-baseline` 是后续评分对照基线。

### Chosen Approach

- 新增 `docs/AGOS-9-Scorecard.md` 作为统一评分卡。
- 在 scorecard 中定义每个维度的 weight、minimum bar、evidence source、blocking fail gate。
- 在 `docs/Furnace Agent Architecture.md` 或 `README.md` 增加短引用，不复制大段内容。

### Alternatives Rejected

- 直接开始 dogfood 或重构：拒绝，缺少统一 PASS/FAIL 口径。
- 只在 `PROGRESS.md` 记录评分：拒绝，动态状态不适合作长期 gate SoT。
- 把 9.0 定义写死为主观分数：拒绝，必须 evidence-driven。

### Execution Plan

1. 新增 `docs/AGOS-9-Scorecard.md`，定义八维评分、权重和最低 PASS 条件。
2. 把当前 7.8 baseline 和 `v0.3.0-agentos-baseline` 写入 scorecard 的 baseline section。
3. 明确 9.0 release gate 所需命令、artifact 和 fail gate。
4. 在 `README.md` 或 `docs/Furnace Agent Architecture.md` 增加指向 scorecard 的短链接。
5. 运行 docs/static 相关验证。

### Stop Conditions

- 需要改变产品终局定义或非目标边界。
- 需要远端 release、push、PR 或共享环境操作。
- 用户要求调整 9.0 评分目标或权重。

### In Scope

- `docs/AGOS-9-Scorecard.md`
- `README.md` 或 `docs/Furnace Agent Architecture.md` 的短引用
- `PROGRESS.md` 的一条动态记录

### Out Of Scope

- Runtime 行为修改
- Dogfood vault 写操作
- Product Shell 实现修改
- Backend 配置或凭据修改

### Affected Files / Modules

- `docs/AGOS-9-Scorecard.md`
- `README.md`
- `docs/Furnace Agent Architecture.md`
- `PROGRESS.md`

### Verification Plan

- `bash scripts/verify.sh scripts`
- `bash scripts/verify.sh python-static` if doc references touch Python-facing docs only indirectly not required, but acceptable as targeted safety
- qa-review for scoring/gate completeness

### Fail Gate

- Scorecard 没有可验证证据路径。
- Scorecard 把当前不可复算 dogfood proof 标成 PASS。
- 文档与 active architecture 非目标冲突。

### Residual Risks

- Scorecard 只能定义 gate，不能替代后续 live dogfood 证据。
- 评分权重仍有产品判断成分，后续可能需要校准。

## Milestone: AGOS-002-DOGFOOD-PROOF

- `title`: 重建当前 clean dogfood 可复算 proof
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 历史 dogfood maturity PASS 和 P1 compounding proof 有记录，但当前 `/home/tim/danlu/炼丹炉` 已清仓，旧 receipt/snapshot 不在现场。
- 9.0 不能依赖历史口头证明，必须能在当前 dogfood vault 重新复算。

### Success Criteria

- [ ] 当前 dogfood vault 重新生成 maturity proof artifact，并能 `collect` / `summarize`。
- [ ] 覆盖至少三类真实输入：PDF、URL、note 或 repo。
- [ ] 至少 3 次连续 nightly 或等价 replay PASS，且没有 failed/blocked maturity run。
- [ ] 生成 raw -> wiki -> output -> receipt/audit 的完整 provenance。
- [ ] 至少一个 judgment/decision/elixir/report path 证明知识复利链路。
- [ ] LLM 失败路径显式失败，不写 placeholder 或伪成功。

### Constraints / Dependencies

- 允许以 `/home/tim/danlu/炼丹炉` 作为 dogfood `--root` 运行 runtime。
- 不删除 dogfood 数据，不覆盖用户真实材料，不读取或打印凭据。
- 如果外部 LLM/backend 不可用，记录 blocker 和 failed receipt，不伪造 PASS。

### Questions / Assumptions

- 假设 dogfood vault 可用于本地验证写操作。
- 假设真实投资 PDF 可由用户或现有 dogfood raw/inbox 提供；若没有材料，停下要求用户提供或确认替代材料。

### Chosen Approach

- 先用 maturity gate 的 `collect` 建立 before snapshot。
- 再通过 controlled nightly/profile 生成 proof。
- 最后用 `summarize` 和 scorecard 映射证据。

### Alternatives Rejected

- 复用旧 proof：拒绝，当前 clean vault 不可复算。
- 用 fixture acceptance 代替 dogfood：拒绝，9.0 要 live proof。
- LLM 不可用时写 deterministic 替代结论：拒绝，会污染 proof。

### Execution Plan

1. 检查 dogfood vault layout 和现有 maturity artifacts。
2. 采集 before snapshot：`python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 collect`。
3. 准备或确认真实输入材料，覆盖 PDF/URL/note 或 repo。
4. 运行 controlled nightly 或 maturity gate run，保留 receipt。
5. 重复直到满足连续 proof 要求，或明确记录 backend/material blocker。
6. 运行 summarize 并把证据映射到 scorecard。
7. 更新 `PROGRESS.md` 和相关 dogfood proof 文档。

### Stop Conditions

- 需要用户提供真实材料但当前没有材料。
- LLM backend 凭据缺失、quota/timeout 持续阻断，且没有明确 operator fallback 授权。
- 任何命令可能删除或迁移 dogfood 数据。
- 连续 3 轮 runtime debug 不收敛。

### In Scope

- `scripts/dogfood_maturity_gate.py`
- `scripts/run_nightly.sh`
- Dogfood vault proof artifacts
- `PROGRESS.md`
- Scorecard evidence update

### Out Of Scope

- 改变 maturity 阈值来通过 gate
- 删除历史 dogfood artifacts
- 后台 systemd installation 或 timer 变更
- 远端上传 proof

### Affected Files / Modules

- `scripts/dogfood_maturity_gate.py`
- `scripts/run_nightly.sh`
- `src/aiwiki/runner/workflows.py` only if proof exposes real bug
- `src/aiwiki/execution/receipts.py` only if proof exposes receipt bug
- `/home/tim/danlu/炼丹炉/output/control/maturity-gate/*`
- `PROGRESS.md`

### Verification Plan

- `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 collect`
- `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --recent 3`
- `bash scripts/verify.sh python-static`
- targeted pytest for changed runtime scripts/modules, if any
- qa-runtime required

### Fail Gate

- Maturity summarize cannot prove current clean dogfood path.
- Any proof contains placeholder LLM success.
- Receipt/audit provenance missing for accepted semantic output.
- Dogfood operation mutates unintended user data.

### Residual Risks

- 3-run proof is not the same as multi-week natural operation.
- Backend availability may vary after the proof window.

## Milestone: AGOS-003-SHELL-STABILITY

- `title`: Product Shell 稳定化与 bundle/source drift gate
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- Product Shell 已可用，但 `main.js` 是生成物且也被加载/测试，`src/` 与 bundle 存在 drift 风险。
- 部分 `src/bridge`、`src/state` 模块可能未纳入 `build.sh`，维护者容易误改不生效文件。
- 9.0 要求 Product Shell 成为稳定日常入口，而非只靠 CLI。

### Success Criteria

- [ ] `src/` 改动未 rebuild `main.js` 时 verify 能失败。
- [ ] 未纳入 build 的 `src/bridge` / `src/state` 模块被接入、删除或明确标记 deprecated。
- [ ] Universal Input、Ctrl+Enter、pending card、report open、raw navigation、Advanced 隔离有测试或 contract 覆盖。
- [ ] `scripts/verify.sh product-shell-static` 覆盖 bundle drift，不只 `node --check`。
- [ ] Product Shell 默认用户面仍只强调 `drop` 和 `today`，operator 能力保持 Advanced。

### Constraints / Dependencies

- 不改变 runtime CLI 语义。
- 不把 API key/webhook 写入 repo。
- 不引入 heavy frontend framework；保持当前 Obsidian plugin 架构。

### Questions / Assumptions

- 假设当前单文件 bundle 仍是短期可接受方案；本 milestone 不改成 webpack/esbuild。
- 假设 Obsidian 真机 e2e 暂时可用 Jest/contract/static gate 近似覆盖。

### Chosen Approach

- 给 `build.sh` / generated `main.js` 增加 deterministic drift check。
- 清理或纳入未打包模块。
- 扩展 Product Shell tests，并把关键测试纳入 verify target。

### Alternatives Rejected

- 引入大型 bundler：拒绝，当前风险可用 drift gate 先控制。
- 重写 Product Shell：拒绝，当前已可用，应稳定化而非重来。

### Execution Plan

1. 比对 `build.sh` 拼接列表和 `src/` 文件列表。
2. 增加 bundle drift check 命令或脚本。
3. 清理未纳入 build 的死模块或接入 build。
4. 补 Product Shell targeted tests。
5. 更新 `scripts/verify.sh product-shell-static`。
6. 运行 Product Shell Jest/static 和 Python tests。

### Stop Conditions

- 需要 Obsidian GUI 自动化或浏览器/Electron 操作才能证明，且当前工具链不可用。
- 需要读取或修改本地 plugin secrets。
- Drift check 与现有 build 机制冲突且连续 3 轮无法收敛。

### In Scope

- `.obsidian/plugins/furnace-product-shell/build.sh`
- `.obsidian/plugins/furnace-product-shell/src/*`
- `.obsidian/plugins/furnace-product-shell/main.js`
- `.obsidian/plugins/furnace-product-shell/package.json`
- Product Shell tests
- `scripts/verify.sh`

### Out Of Scope

- Obsidian plugin marketplace packaging
- UI redesign
- Runtime backend strategy change
- External notification provider changes

### Affected Files / Modules

- `.obsidian/plugins/furnace-product-shell/build.sh`
- `.obsidian/plugins/furnace-product-shell/src/plugin.js`
- `.obsidian/plugins/furnace-product-shell/src/render_input.js`
- `.obsidian/plugins/furnace-product-shell/src/render_today.js`
- `.obsidian/plugins/furnace-product-shell/main.js`
- `.obsidian/plugins/furnace-product-shell/tests/*`
- `tests/test_product_shell*.py`
- `scripts/verify.sh`

### Verification Plan

- `bash scripts/verify.sh product-shell-static`
- Product Shell Jest command from plugin package, if available
- `PYTHONPATH=src python -m pytest tests/test_product_shell*.py -q`
- `bash scripts/verify.sh scripts`
- qa-runtime if launcher/dogfood shell path changes

### Fail Gate

- `src/` and `main.js` can drift without gate failure.
- Obsidian-loaded `main.js` behavior differs from tested source path.
- User-facing default surface exposes operator complexity.

### Residual Risks

- Static/Jest still cannot fully replace real Obsidian DOM/visual testing.
- Single-file bundle remains a maintainability compromise.

## Milestone: AGOS-004-DOCS-SOT

- `title`: 文档 SoT 收敛与历史口径隔离
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- `Architecture`、`Evolution Mechanics`、`Runtime Operations` 当前较新，但 `Elixir`、`Next Direction` 存在历史叠层。
- L3 auto-adopt、nightly 默认、backend fallback、not-yet gap 等口径容易误导后续开发。

### Success Criteria

- [ ] 明确 active SoT 文档集合和历史 thesis 文档边界。
- [ ] `Furnace Elixir.md` 标注历史语境或补当前实现差异。
- [ ] `Furnace Next Direction Post-P4.md` 顶部有当前有效结论摘要。
- [ ] backend、L3 auto-adopt、nightly profile、fallback 口径一致。
- [ ] README 模块图与当前实际 owner/facade 状态不冲突。

### Constraints / Dependencies

- 不改 runtime 行为。
- 不删除有历史价值的 thesis 文档，除非用户明确要求。
- 文档更新必须区分 current fact、target state、historical note。

### Questions / Assumptions

- 假设 `docs/Furnace Agent Architecture.md` 仍是最高层 active SoT。
- 假设 `docs/Furnace Elixir.md` 保留为 thesis，而非强制改成 runtime spec。

### Chosen Approach

- 加当前状态摘要和文档状态标签。
- 修正明显漂移路径和过期断言。
- 增加 docs consistency grep checklist。

### Alternatives Rejected

- 删除旧文档：拒绝，历史设计仍有价值。
- 把所有文档合并成一个巨文档：拒绝，会降低可维护性。

### Execution Plan

1. 扫描 `never automatically`、`fallback`、`auto-adopt`、`not-yet`、`implemented/partial` 等冲突关键词。
2. 给文档加 status/current-effective-summary。
3. 修正 README 中明显路径/owner drift。
4. 更新 scorecard docs evidence。
5. 跑 docs/static 相关验证。

### Stop Conditions

- 发现产品终局定义本身需要重定。
- 文档修改会改变安全边界或 runtime 默认策略。

### In Scope

- `README.md`
- `docs/Furnace Agent Architecture.md`
- `docs/Furnace Evolution Mechanics.md`
- `docs/Furnace Runtime Operations.md`
- `docs/Furnace Elixir.md`
- `docs/Furnace Next Direction Post-P4.md`
- `docs/AGOS-9-Scorecard.md`

### Out Of Scope

- Runtime 实现修改
- Backend 删除或新增
- Dogfood proof 重新运行

### Affected Files / Modules

- `README.md`
- `docs/*.md`
- `PROGRESS.md`

### Verification Plan

- docs consistency grep checklist
- `bash scripts/verify.sh scripts`
- `bash scripts/verify.sh python-static` if README examples touch CLI strings
- qa-review for contradiction scan

### Fail Gate

- 文档仍对 fallback、L3 auto-adopt、nightly 默认或 current gap 给出互相冲突口径。
- README 模块图继续指向不存在或错误 owner。

### Residual Risks

- 文档会继续随 runtime 演化漂移，需要后续 release gate 持续扫描。

## Milestone: AGOS-005-RUNTIME-SLIM

- `title`: Runtime legacy hub 定向瘦身
- `status`: done
- `qa-review`: required
- `qa-runtime`: not-required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- `runner/workflows.py`、`app_surfaces.py`、`app_lifecycle.py`、`app_memory.py`、`app_protocol.py`、`app_compile.py` 仍是高复杂度 hub。
- 9.0 长期支持要求 owner 边界清楚、facade 不新增逻辑、render/business 不继续混杂。

### Success Criteria

- [ ] 为高风险 hub 建立 targeted slimming map，按 ROI 和 blast radius 排序。
- [ ] 至少完成一个低风险 owner extraction，并保持行为不变。
- [ ] Facade 文件新增 guard comment 或 test，防止新业务逻辑继续进入 facade。
- [ ] `CompileContext` 新字段增长规则被文档化。
- [ ] Focused tests 和 full/targeted verify PASS。

### Constraints / Dependencies

- 不做 broad refactor。
- 每轮只拆一个明确 seam。
- 保持旧 import 兼容，除非已有证据表明 private dead code 可删。
- 不改变 signal/schema/protocol/receipt 语义。

### Questions / Assumptions

- 假设第一轮优先从 `runner/workflows.py` 或 `app_surfaces.py` 的低风险 helper extraction 开始，而不是动 `app_protocol.py`。
- 假设行数下降不是唯一目标，owner 清晰和测试稳定更重要。

### Chosen Approach

- 先写 seam map，再 materialize 单 seam contract。
- 使用 characterization tests 锁行为。
- 小步 extraction，避免跨模块循环 import。

### Alternatives Rejected

- 一次性拆大 hub：拒绝，风险过高。
- 只加注释不拆：拒绝，无法提升长期支持性。
- 删除 compatibility facade：拒绝，外部/test import 仍可能依赖。

### Execution Plan

1. 生成 hub seam map，列出 candidate extraction、caller、tests、risk。
2. 选择一个低风险 seam materialize contract。
3. 添加 characterization tests。
4. 执行 extraction，保持 public behavior。
5. 跑 targeted tests、verify、qa-review。
6. 更新 scorecard maintainability evidence。

### Stop Conditions

- 需要改变 public API 或 persisted state。
- 循环 import 风险无法小步解决。
- Focused tests 表明行为变化无法解释。

### In Scope

- One targeted seam extraction
- Tests for extracted seam
- Maintainability scorecard evidence

### Out Of Scope

- Full runtime rewrite
- Protocol schema migration
- Product Shell rewrite
- Planner autonomy expansion

### Affected Files / Modules

- `src/aiwiki/runner/workflows.py`
- `src/aiwiki/app_surfaces.py`
- `src/aiwiki/app_lifecycle.py`
- `src/aiwiki/app_memory.py`
- `src/aiwiki/app_protocol.py`
- `src/aiwiki/app_compile.py`
- Relevant tests

### Verification Plan

- Focused pytest for selected seam
- `bash scripts/verify.sh python-static`
- `bash scripts/verify.sh unit` or resolver-selected target
- qa-review

### Fail Gate

- Public behavior changes unintentionally.
- Import compatibility breaks.
- Extraction increases coupling or duplicates logic.

### Residual Risks

- One seam does not eliminate all hub complexity.
- Legacy compatibility will remain until external import risk is lower.

## Milestone: AGOS-006-PLANNER-ROUTING

- `title`: Planner / signal routing 实质化
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前 signal/planner/alchemy 机制存在，但 planner 仍偏 rule dispatch + preview。
- 9.0 AgentOS 需要 signal severity、budget_hint、trace_id 真正影响 light/heavy/proposal/human escalation routing。

### Success Criteria

- [ ] `signal severity`、`budget_hint`、`trace_id` 被 planner decision 明确消费并记录原因。
- [ ] observe-only 与 execute-mode side effect 边界清楚。
- [ ] planner-log rollback marker 被 downstream consumer 正确识别。
- [ ] 任何 planner side effect 都必须有 receipt/audit。
- [ ] Acceptance 覆盖 severity/budget routing 和 rollback marker。

### Constraints / Dependencies

- 不允许 planner 直接越权修改 `src/aiwiki/**`。
- execute-mode 默认仍受 kill switch、receipt 和 review gate 限制。
- 不把 LLM 判断塞进 deterministic planner，除非显式 external model path。

### Questions / Assumptions

- 假设第一轮只提升 deterministic routing，不引入新 LLM planner。
- 假设 severity/budget 的初始规则可保守实现。

### Chosen Approach

- 扩展 planner decision reason schema 或现有 metadata。
- 增加 severity/budget routing table。
- 强化 rollback marker consumer tests。

### Alternatives Rejected

- 直接让 LLM 当 planner：拒绝，不符合 deterministic baseline。
- 默认开启 heavy autonomous execution：拒绝，证据不足。

### Execution Plan

1. 梳理现有 signal schema、planner-log schema 和 alchemy lane consumer。
2. 定义 severity/budget routing matrix。
3. 实现 deterministic routing 变更。
4. 添加 replay/acceptance fixtures。
5. 验证 execute-mode 无越权 side effect。
6. 更新 Evolution Mechanics 和 scorecard evidence。

### Stop Conditions

- 需要 schema migration 或历史 planner-log 迁移。
- Existing receipts 无法支撑 side effect audit。
- Routing 规则与安全边界冲突。

### In Scope

- Signals planner routing
- Planner-log reason/evidence
- Rollback marker consumption
- Acceptance fixtures

### Out Of Scope

- LLM planner
- Full autonomous source-code modification
- New hosted scheduler

### Affected Files / Modules

- `src/aiwiki/signals/*`
- `src/aiwiki/planner/*`
- `src/aiwiki/runner/alchemy.py`
- `src/aiwiki/agent_loop.py`
- `tests/test_planner_log.py`
- `tests/test_signals_collector.py`
- `tests/fixtures/acceptance/*`

### Verification Plan

- `PYTHONPATH=src python -m pytest tests/test_signals_collector.py tests/test_planner_log.py -q`
- Acceptance replay target
- `bash scripts/verify.sh python-static`
- qa-runtime if execute-mode behavior changes

### Fail Gate

- Planner side effect lacks receipt/audit.
- observe-only starts mutating state unexpectedly.
- rollback marker ignored by downstream consumer.

### Residual Risks

- Deterministic routing improves control but still is not full intelligent planning.
- Multi-week natural operation still needs AGOS-008/009 evidence。

## Milestone: AGOS-007-LLM-TELEMETRY

- `title`: Backend telemetry 与 LLM 可靠性硬化
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- Backend 状态现在部分依赖经验和少量 receipt；9.0 需要用 telemetry 决定 backend/model 策略。
- LLM raw response、timeout、quota、fallback_stage、model fallback 需要可聚合、可解释、可清理。

### Success Criteria

- [ ] LLM receipts 可聚合 backend、model、latency、timeout、quota、error_class、fallback_stage。
- [ ] `llm-check --probe` 与真实 run telemetry 分开展示。
- [ ] raw response retention / cleanup 策略明确。
- [ ] 不恢复隐藏 cross-backend fallback；backend fallback 只在显式 operator path。
- [ ] 能输出过去 N 次 backend/model 成功率和失败原因。

### Constraints / Dependencies

- 不打印 API key 或敏感 raw prompt。
- 不新增外部 telemetry service，只写本地文件。
- 不改变默认主路由 `opencode-api/deepseek-v4-pro`，除非 scorecard/telemetry 后续明确支持。

### Questions / Assumptions

- 假设当前 `.aiwiki/logs/llm-receipts.jsonl` 是主要 telemetry source。
- 假设 raw response cleanup 可按 age/count 本地策略实现。

### Chosen Approach

- 增加本地 metrics/report helper，从现有 receipt 聚合。
- 扩展 receipt 字段时保持 backward-compatible reader。
- 在 docs 中明确 telemetry 与 backend decision 流程。

### Alternatives Rejected

- 外部 observability SaaS：拒绝，违背 local-first。
- 自动跨 backend retry：拒绝，违背显式 backend 选择。

### Execution Plan

1. 审计现有 LLM receipt 字段和 metrics reader。
2. 补齐缺失 telemetry 字段或 reader fallback。
3. 增加 CLI/report surface 展示 N 次聚合。
4. 增加 raw response retention 策略。
5. 补 tests 和 docs。
6. 用 dogfood receipts 验证聚合。

### Stop Conditions

- 需要读取或迁移敏感 raw responses。
- 需要改变 backend auth 或外部服务配置。
- Historical receipt 兼容性无法保持。

### In Scope

- LLM receipt aggregation
- Local telemetry report
- Raw response retention policy
- Docs update

### Out Of Scope

- New remote telemetry service
- Hidden backend auto routing
- API key management redesign

### Affected Files / Modules

- `src/aiwiki/llm.py`
- `src/aiwiki/config.py`
- `src/aiwiki/runner/clients.py`
- `src/aiwiki/runner/receipts.py`
- `src/aiwiki/metrics*`
- `docs/Furnace Runtime Operations.md`
- Relevant tests

### Verification Plan

- LLM receipt focused tests
- Metrics/report focused tests
- `bash scripts/verify.sh python-static`
- dogfood telemetry read-only aggregation
- qa-runtime if live receipt used

### Fail Gate

- Telemetry leaks secrets.
- Hidden cross-backend fallback reappears.
- Historical receipts break reader.

### Residual Risks

- Telemetry cannot guarantee future backend availability.
- Live backend quality still depends on external providers.

## Milestone: AGOS-008-LONG-RUN

- `title`: 长期运行、恢复和保留策略硬化
- `status`: done
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 9.0 AgentOS 要长期 unattended local runtime，而不只是一次性 PASS。
- watcher、nightly、receipt、planner-log、LLM response、corrupt state、runtime lock 都需要恢复演练和 retention 策略。

### Success Criteria

- [ ] watcher deterministic-only 边界有 test/doc evidence。
- [ ] nightly auto flags 有 profile 文档、kill switch 和 receipt evidence。
- [ ] corrupt JSON/JSONL、partial receipt、locked runtime、LLM timeout 有恢复演练。
- [ ] execution receipt、planner-log、LLM receipt、raw response 有 retention/archive policy。
- [ ] systemd service/timer docs 与 scripts 一致。

### Constraints / Dependencies

- 不默认安装或修改 user systemd service，除非用户明确确认。
- 不删除历史 receipt；retention 必须 archive-first 或 explicit cleanup。
- 不把 watcher 改成默认 LLM path。

### Questions / Assumptions

- 假设长期运行硬化可以先用 scripted fault injection，而不是实际等待多周。
- 假设真实 systemd install/update 需要用户确认。

### Chosen Approach

- 先实现 local fault injection/recovery tests。
- 文档化 retention 和 kill switch。
- 只在用户确认后做真实 systemd 操作。

### Alternatives Rejected

- 直接打开全自动长期运行：拒绝，需要先有恢复演练。
- 删除旧 logs 解决膨胀：拒绝，破坏 audit。

### Execution Plan

1. 列出长期运行 failure mode。
2. 为 corrupt state、partial receipt、lock contention、LLM timeout 增加 recovery tests。
3. 定义 retention/archive policy。
4. 更新 runtime operations 文档。
5. 运行 targeted tests 和 qa-runtime。

### Stop Conditions

- 需要修改真实 user systemd service。
- Retention policy 可能删除用户仍需要的审计证据。
- Recovery path 需要 schema migration。

### In Scope

- Recovery tests
- Retention/archive policy
- Runtime operations docs
- Local scripts only if reversible

### Out Of Scope

- Remote deployment
- Shared environment operation
- Default enabling of new automation flags

### Affected Files / Modules

- `scripts/run_nightly.sh`
- `scripts/*systemd*`
- `src/aiwiki/app_state.py`
- `src/aiwiki/app_utils.py`
- `src/aiwiki/execution/*`
- `src/aiwiki/runner/background.py`
- `docs/Furnace Runtime Operations.md`
- Relevant tests

### Verification Plan

- Fault-injection focused tests
- `bash scripts/verify.sh python-static`
- `bash scripts/verify.sh unit` or resolver-selected target
- qa-runtime recovery checklist

### Fail Gate

- Failure mode is silently swallowed.
- Recovery loses audit/provenance.
- Watcher starts calling LLM by default.

### Residual Risks

- Scripted recovery is weaker than multi-week real unattended proof。
- Systemd behavior may vary by host environment。

## Milestone: AGOS-009-RELEASE-GATE

- `title`: 9.0 AgentOS release gate 与最终收口
- `status`: audit-completed-release-blocked
- `execution_status`: done
- `release_status`: blocked
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 前面 milestones 会分别补证据、稳定 shell、收敛文档、降低复杂度、强化 planner 和 LLM telemetry。
- 最终必须用统一 release gate 判断是否达到 9.0，而不是凭感觉宣布。

### Success Criteria

- [ ] `docs/AGOS-9-Scorecard.md` 总分 >= 9.0，且没有 blocking fail gate。
- [ ] Full verify PASS。
- [ ] Product Shell static/Jest/drift gate PASS。
- [ ] Acceptance replay PASS。
- [ ] Current dogfood maturity summarize PASS。
- [ ] Backend telemetry report 可解释最近 N 次成功/失败。
- [ ] Docs consistency scan PASS。
- [ ] qa-review 和 qa-runtime PASS。
- [ ] 创建本地 final release tag，是否 push/GitHub Release 需用户另行确认。

Release gate audit completed on 2026-05-21, but release remains blocked by live dogfood 3-day proof and knowledge compounding proof. This milestone is not a 9.0 release success.

### Constraints / Dependencies

- 不自动 push tag 或创建远端 GitHub Release。
- Release tag 前必须确认工作区状态、diff、log、scorecard evidence。
- 不把未验证 dogfood proof 标为 release evidence。

### Questions / Assumptions

- 假设最终 tag 名称后续按实际版本选择，例如 `v0.4.0-agentos-9` 或用户指定版本。
- 假设 remote release/push 是单独显式授权动作。

### Chosen Approach

- 用 scorecard gate 汇总所有证据。
- 先本地 tag，再由用户决定是否 push / GitHub Release。
- Release notes 明确 residual risks。

### Alternatives Rejected

- 只跑 tests 不跑 dogfood：拒绝，9.0 要现场 proof。
- 只做 Git tag 不做 evidence gate：拒绝，无法证明 9.0。
- 自动 push：拒绝，需要明确授权。

### Execution Plan

1. 运行 full verify 和 Product Shell gate。
2. 运行 dogfood maturity summarize。
3. 生成 backend telemetry report。
4. 跑 docs consistency scan。
5. 完成 qa-review / qa-runtime。
6. 更新 scorecard 和 release notes。
7. 检查 `git status`、`git diff`、`git log`。
8. 若上述 gate 全部通过，再创建本地 annotated release tag；当前因 blocking gate 未通过而跳过。
9. 汇报证据路径、blocked 状态和后续 proof 要求。

### Stop Conditions

- 任一 blocking fail gate 未通过。
- Dogfood proof 不可复算。
- 用户要求远端 push/release 但凭据或权限不明确。
- 工作区存在无关或敏感改动。

### In Scope

- Final scorecard update
- Release notes
- Explicitly skipping local annotated tag while release gate remains blocked
- Verification evidence summary

### Out Of Scope

- Remote push
- GitHub Release
- Deployment
- Systemd service installation

### Affected Files / Modules

- `docs/AGOS-9-Scorecard.md`
- `docs/releases/*` if release notes path is added
- `PROGRESS.md`
- No Git tag metadata in this blocked release-gate audit

### Verification Plan

- `bash scripts/verify.sh`
- Product Shell Jest/static target
- `python3 scripts/dogfood_maturity_gate.py --root /home/tim/danlu/炼丹炉 summarize --recent 3`
- Backend telemetry command from AGOS-007
- Docs consistency checklist
- qa-review + qa-runtime

### Fail Gate

- Scorecard < 9.0。
- Any blocking gate fails。
- Local release tag would include unintended or sensitive changes。

### Residual Risks

- 9.0 release 仍是 local-first AgentOS，不代表 hosted/multi-user/cloud product maturity。
- Long-term external LLM provider reliability remains outside repo control。

## Materialization

自动推进当前与下一 milestone：优先调用 `/run_plan` 或底层命令：

```bash
HARNESS_DIR=.codex bash scripts/run_plan.sh \
  --plan-file .codex/plans/active.md \
  --verify-auto
```

需要强制物化当前第一轮时：

```bash
HARNESS_DIR=.codex bash scripts/materialize_contract.sh \
  --plan-file .codex/plans/active.md \
  --contract-file .codex/contracts/active.md \
  --milestone AGOS-001-SCORECARD
```
