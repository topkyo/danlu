# Engineering Plan — Agent OS kernel slimming and proof-before-expansion

## Goal

把炼丹炉从“机制已经像 Agent OS，但复杂度开始长胖”的状态，收敛为更薄、更可信、更可长期维护的 `local-first / single-writer / receipt-gated` 知识 Agent Runtime：先冻结扩张，再收敛产品面，随后削薄内核，最后用 dogfood receipt 证明知识复利。

## Architecture Inputs

- `README.md`：炼丹炉 / `aiwiki` 的事实边界是 `raw -> compile -> wiki -> ask -> output -> file-back -> review/nightly`，运行模型为 `single writer, many readers`，核心平面包括 `raw / wiki / machine memory / schema / outputs`。
- `docs/Furnace Agent Architecture.md`：炼丹炉是 local-first、single-writer 的 agent 系统/引擎；正式 loop 为 `signal -> planner -> phase -> feedback -> learning`；非目标包括 hosted service、multi-user sync、heavy RAG infra、fine-tuning。
- `docs/Furnace Evolution Mechanics.md`：已有 signal schema、planner routing、heavy/light alchemy、active corpus、elixir lifecycle、L2 protocol-learning、L3 prompt/policy proposal，但部分能力仍是 target contract + 当前差距，不能把机制存在等同于成熟自治。
- `docs/Furnace Next Direction Post-P4.md`：critical path 已从“机制完备”转为“实战 dogfood 是否能端到端产生知识复利”；需要 acceptance/dogfood + 长尾保养，而不是继续堆机制。
- `docs/Furnace Product Shell.md`：用户面原则是“一个输入端 + 一个输出端，其余隐藏”；Product Shell 不拥有 runtime state，只通过 launcher CLI 与 control artifacts 读取事实。
- 当前代码规模评估：`src` 约 6.4 万行，`tests` 约 5.8 万行，`scripts` 约 1.0 万行，Product Shell JS source 约 1.17 万行；测试重对可写/可回滚自治系统合理，但 compat seam、大 hub、CLI 命令面和 process scripts 已经影响演化速度。
- 独立架构评估结论：炼丹炉已经是狭义、单机、文件系统型 Agent OS / Agent Runtime 内核；更准确的定位是“审计优先的 local-first knowledge agent runtime”，当前问题不是不够像 OS，而是已经像了但长胖了。

## Global Context

- 用户要求按推荐路线执行四件事：冻结扩张、产品面收敛、削薄内核、证明复利；先在 `docs/` 保存 plan 文档，再多轮 review，review 通过后按 harness 自动闭环推进每个 milestone。
- 本计划是下一阶段执行源；`docs/Furnace Agent OS Slimdown Plan.md` 是可读 SoT，`.codex/plans/active.md` 是 harness 消费副本，两者内容应保持同步。
- 当前 `.codex/contracts/active.md` 可能来自上一轮 Product Shell polish；启动本计划前必须用本 plan 重新 materialize milestone contract，避免 closed_loop 继续检查旧 contract。
- “Agent OS”身份不再通过新增自治层证明；后续成熟度只能通过 receipt、audit、revert、dogfood acceptance 和可复算指标证明。
- Product Shell / CLI 需要服务 `drop anything` + `today` 的产品心智；operator 面保留为 Advanced，但不再进入默认用户路径。

## Global Constraints

- 不放开 hosted service、multi-user sync、heavy RAG infra、fine-tuning 或隐式 backend routing。
- 不自动 apply 高风险、不可逆、外部副作用、凭据/权限相关或证据不足的动作。
- 不扩 L3 auto-adopt / self-editing 与 Judgment autonomy 范围；新增能力必须先证明 receipt/audit/revert 与 dogfood 价值。
- 不通过隐藏、删除或伪造 backlog 来制造“复杂度下降”；削薄必须保留 provenance 与可回滚路径。
- 保持 `raw/ -> wiki/ -> output/` 分层；派生输出不能覆盖原始 source pages。
- Product Shell 不拥有 runtime SoT；UI polish 不能引入 hidden CoT、隐式 thread memory 或真实 token streaming。
- 拆模块只在能删除旧 shim、减少调用路径或降低 review 成本时做；禁止“为了拆而再加一层 abstraction”。
- 每个 milestone 必须走 focused tests、`bash scripts/verify.sh`、qa-review、qa-runtime/closed-loop；如使用 same-context fallback，gate artifact 必须写明原因。

## Freeze Ledger

- 冻结：L3 auto-adopt / self-editing 扩张；允许的唯一动作是保持现有安全边界、review/revert/audit 与已计划的证明性 gate。
- 冻结：Judgment autonomy 扩权；不新增自动生成 judgment、不扩大自动采纳范围、不降低人工异常边界。
- 冻结：Product Shell 新交互能力；不新增视图、按钮、状态字段、pending/recent/output 行为语义、hidden CoT 展示、隐式 thread memory 或 true token streaming。
- 冻结：CLI 新命令、子命令、alias、operator lane；AOS-002 只允许 help/docs/grouping/排序/文案类收敛。
- 冻结：新 backend、隐式 backend routing、hosted/multi-user/heavy RAG/fine-tuning 路线。
- 允许例外：为降低用户心智复杂度而做的文档、help、默认入口排序、Advanced 分组、shell 文案收敛；这些例外不得改变 runtime 行为或增加新 surface。
- Stop/re-plan：若某 milestone 必须突破上述冻结项才能完成，则停止执行并重写 plan/contract，不在当前 milestone 内临时扩 scope。

## Milestone Index

- `AOS-001`: Expansion freeze and plan handoff
- `AOS-002`: Product surface convergence
- `AOS-003`: Kernel shim retirement and hub slimming
- `AOS-004`: Knowledge compounding proof gate

## Milestone: AOS-001

- `title`: Expansion freeze and plan handoff
- `status`: planned
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前项目已经具备 Agent OS 内核特征，但复杂度风险来自 L3/Judgment/Product Shell/CLI/process harness 的继续扩张。
- 后续执行需要一个明确的冻结边界和可被 harness 消费的 milestone plan，避免在削薄前继续添加新机制。
- 本 milestone 先固化 plan、冻结扩张约束、刷新 active contract 与状态记录；不做 runtime 行为改造。

### Success Criteria

- [ ] `docs/Furnace Agent OS Slimdown Plan.md` 存在，完整记录四阶段路线、冻结边界、风险和验证策略。
- [ ] `.codex/plans/active.md` 与 docs plan 同步，且 `materialize_contract.sh --contract-file /tmp/opencode/aos-001-contract.md --milestone AOS-001` 可成功解析。
- [ ] `PROGRESS.md` 记录本计划启动、review 结论、首个 milestone 的 scope 与 out-of-scope。
- [ ] Plan 明确冻结 L3 auto-adopt/self-editing、Judgment autonomy 扩权、Product Shell 新花样和新增 operator 命令/lane。
- [ ] 产出 freeze ledger，明确列出本阶段冻结项（L3 auto-adopt/self-editing、Judgment autonomy 扩权、Product Shell 新交互、CLI 新命令/alias/operator lane）以及允许的唯一例外（help/docs/grouping/排序/文案类收敛）。
- [ ] Plan 明确后续拆分原则：只有能删除 shim、缩短路径或降低 review 成本的拆分才允许。
- [ ] 多轮 review 后无 blocking findings；所有 blocker 必须折叠进 plan 后再 materialize contract。
- [ ] `bash scripts/verify.sh` PASS；qa-review 与 qa-runtime gate artifact 刷新后 closed-loop PASS。

### Constraints / Dependencies

- 本 milestone 不修改 runtime 行为，不删除 CLI 命令，不迁移数据，不改 prompt 或 maturity gate 阈值。
- 如果 review 认为某个 milestone scope 过大，先拆 plan，不直接进入 implementation。
- `docs/` plan 和 `.codex/plans/active.md` 必须同步；不能只更新 harness 副本。

### Questions / Assumptions

- 假设本阶段不需要用户重新确认“是否冻结扩张”，因为用户已要求按推荐路线执行。
- 假设首个 milestone 以 plan handoff + freeze policy 为交付物，后续 implementation 从 AOS-002 开始。

### Chosen Approach

- 采用 proof-before-expansion：先写可审计 plan 和冻结边界，再由独立 reviewer 多轮审查，最后让 harness materialize/closed-loop。
- 把四件事拆成四个 milestone，避免一次性同时改 CLI、runtime、compat shim 和 dogfood gate。
- 保留当前 Agent OS 内核，收缩扩张面；后续每一步都要求可复跑验证和 receipt/gate 证据。

### Alternatives Rejected

- 直接开始删代码：拒绝。当前兼容层和测试很重，未冻结 plan 前删除容易破坏 runtime 边界。
- 继续扩 Product Shell 或 L3：拒绝。当前问题是复杂度偏胖，不是机制不足。
- 只写 docs 不接 harness：拒绝。用户要求 review 通过后按 harness 自动闭环推进。

### Execution Plan

1. 写入 `docs/Furnace Agent OS Slimdown Plan.md`。
2. 同步 `.codex/plans/active.md`。
3. 用临时 contract 文件验证 `materialize_contract.sh` 可解析 plan，避免依赖当前环境不可用的 `/dev/stdout`。
4. 组织至少两轮 review；如有 blocker，修订 docs plan 与 active plan。
5. Review 通过后 materialize `AOS-001` contract。
6. 更新 `PROGRESS.md`。
7. 跑 `bash scripts/verify.sh`，刷新 gate artifacts，执行 closed-loop。

### Stop Conditions

- Reviewer 认为四个 milestone 顺序或 scope 会造成事实层污染、静默隐藏 debt 或高风险删改。
- Plan 不能被 harness 正确 materialize。
- 需要改 runtime 行为才能完成本 milestone。
- 连续 3 轮 review/验证仍无法收敛。

### In Scope

- 下一阶段工程 plan 文档。
- Harness active plan 同步。
- 扩张冻结边界与后续 milestone 验收标准。
- Freeze ledger：冻结项、允许例外、stop/re-plan 条件。
- `PROGRESS.md` 状态记录。

### Out Of Scope

- CLI 收敛实现。
- 删除 compat shim 或拆 hub。
- 新增 dogfood maturity 指标。
- Product Shell 新 UI 能力。
- L3/Judgment 自动化扩权。

### Affected Files / Modules

- `docs/Furnace Agent OS Slimdown Plan.md`
- `.codex/plans/active.md`
- `.codex/contracts/active.md`
- `.codex/gates/qa-review.md`
- `.codex/gates/qa-runtime.md`
- `PROGRESS.md`

### Verification Plan

- `HARNESS_DIR=.codex bash scripts/materialize_contract.sh --plan-file .codex/plans/active.md --contract-file /tmp/opencode/aos-001-contract.md --milestone AOS-001`
- Multi-round qa-review focused on architecture scope, risk, milestone ordering and harness compatibility.
- `bash scripts/verify.sh`
- `HARNESS_DIR=.codex bash scripts/closed_loop.sh --require-contract`

### Fail Gate

- Plan 未保存到 `docs/`。
- `.codex/plans/active.md` 与 docs plan 明显分叉。
- Plan 无法 materialize。
- Review 存在未折叠 blocker。
- Gate artifact 缺失、contract sha 不匹配或 closed-loop 失败。

### Residual Risks

- 本 milestone 只冻结路线和边界，不会立刻降低代码量。
- 后续 AOS-002/AOS-003 才会真正接触 CLI surface 与 shim/hub 复杂度。

## Milestone: AOS-002

- `title`: Product surface convergence
- `status`: planned
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 产品原则是“一个输入端 + 一个输出端，其余隐藏”，但当前 CLI surface 仍很宽，Product Shell/advanced/operator 面容易泄露内部机制心智。
- 目标不是删除能力，而是把默认用户路径收敛到 `drop` / `today`，其余进入明确的 `advanced` / operator 区域。

### Success Criteria

- [ ] 梳理 CLI command taxonomy，明确 `primary`、`advanced`、`operator/internal` 三层。
- [ ] 默认 help / docs / Product Shell 入口优先呈现 `drop` 与 `today`，高级命令不再与主路径同权展示。
- [ ] 不删除现有 operator 能力；只允许 help grouping、文档、默认入口排序和 shell 文案/分组收敛。
- [ ] 禁止新增 CLI alias、命令、子命令、Product Shell 视图、按钮、状态字段或交互能力。
- [ ] CLI text/JSON 行为不破坏现有 acceptance。
- [ ] Product Shell 不新增 UI-owned state，不绕过 audit，不隐式调度 backend。
- [ ] Focused tests 覆盖 help/surface 分层与 backward compatibility。
- [ ] `bash scripts/verify.sh` PASS；qa-review 与 closed-loop PASS。

### Constraints / Dependencies

- 不在本 milestone 删除命令；删除或硬 deprecation 留给后续有 telemetry/acceptance 证据的轮次。
- 不新增命令、子命令、alias、operator lane、Product Shell 视图、按钮、状态字段或新的 UX 能力。
- 若涉及 Product Shell，仅允许修改入口文案、排序、分组和 Advanced 显隐；不得新增 UI-owned state、命令注册、pending/recent/output 行为语义。
- 不改 `aiwiki` console script 名，不引入 `furnace` 新 binary。
- 不改变真实 pipeline、receipt schema、backend selection 或 maturity gate。

### Questions / Assumptions

- 假设产品表面先通过 help/docs/shell grouping 收敛，不需要破坏性 CLI 迁移。

### Chosen Approach

- 先做 taxonomy 和默认表面收敛，以最小行为变更降低用户心智复杂度。
- 将 operator 命令明确归入 Advanced，而不是直接删除。

### Alternatives Rejected

- 一次性删除大量 CLI 命令：拒绝，当前测试和 dogfood 仍依赖 operator path。
- 只改 Product Shell 隐藏入口：拒绝，CLI/docs 仍会暴露宽表面。

### Execution Plan

1. 审计 `src/aiwiki/cli/parsers.py` 与 `src/aiwiki/cli/dispatch.py` 命令分组。
2. 先定义 command taxonomy 文档；仅当现有代码已有合适入口时才复用代码常量，不新增抽象。
3. 调整 help/docs/shell surface，使默认路径只强调 `drop` / `today`。
4. 保持 advanced/operator 命令可用并补兼容测试。
5. 更新 README 或相关 docs 的用户入口表述。
6. 跑 focused tests、verify、qa-review、closed-loop。

### Stop Conditions

- 需要破坏既有 CLI 参数或 acceptance 才能达成收敛。
- Product Shell 需要新增 runtime SoT 才能展示分层。
- 发现某些 operator 命令仍是用户主路径必需，需重新定义 taxonomy。

### In Scope

- CLI/help/docs/Product Shell entrypoint 的产品表面分层。
- Backward-compatible grouping、labeling、sorting、wording。

### Out Of Scope

- 删除命令。
- 改 backend routing。
- 改 LLM/prompt/runtime pipeline。

### Affected Files / Modules

- `src/aiwiki/cli/parsers.py`
- `src/aiwiki/cli/dispatch.py`
- `README.md` 或相关 docs
- `src/aiwiki/app_shell/` 或 Product Shell entrypoint files（如需要）
- CLI/Product Shell tests
- `PROGRESS.md`

### Verification Plan

- Focused CLI help / parser tests。
- Product Shell surface tests（如涉及）。
- `bash scripts/verify.sh`
- qa-review + closed-loop。

### Fail Gate

- 现有 CLI 命令不可用或 acceptance 失败。
- 默认用户面仍把 operator backlog/命令与主路径同权展示。
- Product Shell 引入 UI-owned SoT 或隐式 backend routing。

### Residual Risks

- 本 milestone 先降低心智复杂度，不显著减少代码行数。
- 真正删除 legacy/compat 路径需要 AOS-003 的引用证明和回归验证。

## Milestone: AOS-003

- `title`: Kernel shim retirement and hub slimming
- `status`: planned
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前 `app.py`、`app_content.py`、`app_memory_surfaces.py`、`app_compile.py` 等 compat/facade seam 与多个超大 hub 文件增加 review 噪音和重构成本。
- 目标不是机械拆分，而是删除已经无必要的 shim、缩短调用路径、降低未来修改时的上下文负担。

### Success Criteria

- [ ] 生成 compat shim audit 清单，按 `delete-now`、`keep-stable`、`split-later` 分级，并明确首个删除候选。
- [ ] 至少删除或退役一个经引用证明安全、且非 acceptance / dogfood / Product Shell 主路径依赖的 compat shim 或 dead facade。
- [ ] 若审计后确认当前无安全删除项，则本 milestone 触发 stop + re-plan，不以 blocker write-up 视为完成。
- [ ] 对任一拆分/删除，必须减少旧入口或重复路径；不得只新增 wrapper。
- [ ] Owner module 边界更清晰，README/runtime module map 同步更新。
- [ ] 相关 tests 覆盖 import compatibility、CLI/runtime 行为和 removed path 的预期失败/替代路径。
- [ ] `bash scripts/verify.sh` PASS；qa-review 与 closed-loop PASS。

### Constraints / Dependencies

- 不破坏 public CLI、file layout、receipt/audit/revert schema。
- 不删除仍被 tests、acceptance、dogfood 或 Product Shell 使用的入口，除非同步迁移且有验证。
- 不用新抽象掩盖旧抽象；每次改动必须有净复杂度下降说明。
- 首轮 kernel slimming 禁止触碰 `src/aiwiki/runner/alchemy.py`、`src/aiwiki/app_protocol.py`、`src/aiwiki/app_lifecycle.py`、`src/aiwiki/app_surfaces.py` 等大 hub；仅允许处理 facade / shim / re-export path。

### Questions / Assumptions

- 假设可以先从最小、安全、引用清晰的 shim 入手，而不是一次性拆 `runner/alchemy.py` 等大文件。

### Chosen Approach

- 先审计再删除：用 grep/AST/引用搜索确认候选 shim 的调用者。
- 小步退役，优先移除 dead facade 或只剩内部引用的 compatibility seam。
- 大 hub 只做边界标注或低风险提取；没有删除收益时不拆。

### Alternatives Rejected

- 大规模重排目录：拒绝，风险高且会被测试结构锁死。
- 只按行数拆文件：拒绝，不能保证复杂度下降。

### Execution Plan

1. 审计 compat/shim/facade/legacy 标记与大文件 owner 边界。
2. 选出一个最低风险删除/退役候选。
3. 迁移引用或删除 dead path，并更新 module map/docs。
4. 增补 import/runtime 回归测试。
5. 跑 focused tests、verify、qa-review、closed-loop。

### Stop Conditions

- 找不到可安全删除的 shim，继续推进会变成高风险重构。
- 审计确认无安全删除项；此时必须 stop + re-plan，不能以纯 audit 视为 milestone 完成。
- 删除候选涉及外部用户兼容或 dogfood vault 未覆盖路径。
- 连续 3 轮测试不收敛。

### In Scope

- Compat seam audit。
- 一个小型、安全、可验证的 shim retirement 或 re-export path simplification。
- README/runtime module map 同步。

### Out Of Scope

- 大规模目录迁移。
- receipt/schema 文件格式迁移。
- Product Shell redesign。
- L3/Judgment 扩权。

### Affected Files / Modules

- `src/aiwiki/app.py`
- `src/aiwiki/app_content.py`
- `src/aiwiki/app_memory_surfaces.py`
- `src/aiwiki/app_compile.py`
- audit 指向的 facade / shim / re-export path
- README/docs module map
- tests for import/runtime compatibility
- `PROGRESS.md`

### Verification Plan

- Reference/import search evidence。
- Focused import/runtime tests。
- `bash scripts/verify.sh`
- qa-review + closed-loop。

### Fail Gate

- 删除后出现 import regression 或 CLI behavior drift。
- 净复杂度没有下降，只是新增 wrapper。
- README/module map 与实际代码不一致。

### Residual Risks

- 第一轮削薄可能主要是清理低风险 seam，不能一次性解决所有大文件问题。
- 部分 shim 可能仍需保留到后续 major cleanup。

## Milestone: AOS-004

- `title`: Knowledge compounding proof gate
- `status`: planned
- `qa-review`: required
- `qa-runtime`: required
- `execution_mode`: autonomous-closed-loop
- `ask_policy`: blockers-only
- `max_debug_rounds`: 3

### Problem / Context

- 当前文档已明确 critical path 是 dogfood 是否能端到端产生知识复利，而不是继续堆机制。
- 需要把“复利”转成可复跑 gate：材料进入、知识沉淀、判断/金丹复用、报告/file-back、review/receipt 闭环。

### Success Criteria

- [ ] 定义 knowledge compounding metrics：至少覆盖 `raw_to_wiki_count`、`judgment_or_elixir_reuse_count`、`output_file_back_rate`、`receipt_backed_actions`、`human_required_exception_count`。
- [ ] 指标从 existing manifests/receipts/summary 可复算，不依赖人工观察或不可追溯 UI 状态。
- [ ] 针对 investing 或 research dogfood 增加 fixture/acceptance 或 maturity summary，不降低既有阈值。
- [ ] Gate 能区分“机制存在”与“真实复利发生”；无证据时输出 warn/not-yet，而不是 pass。
- [ ] 除 count-based metrics 外，至少输出 1 条成功的 trace/provenance-backed compounding sample（例如 report/file-back 或 ask 结果明确复用既有 judgment/elixir，并可回链到 receipt/path）；若真实 dogfood 只能给出 not-yet，也必须输出可复算 not-yet verdict 与缺口，不伪造 pass。
- [ ] 生成一份 dogfood receipt/report，说明本轮是否证明复利、缺口是什么。
- [ ] `bash scripts/verify.sh` PASS；qa-review 与 closed-loop PASS。

### Constraints / Dependencies

- 不为了通过 gate 修改历史 receipt 或伪造 dogfood 数据。
- 不降低 maturity gate 阈值，不把 hidden routine debt 当作 resolved。
- 不引入外部付费服务或凭据要求。

### Questions / Assumptions

- 假设首版 proof gate 可以先接入 `scripts/dogfood_maturity_gate.py` 或新增旁路 summary，再逐步纳入 nightly。

### Chosen Approach

- 用 existing receipts/manifest/history 派生可复算指标，先证明或明确 not-yet。
- 首版 gate 宁可保守，不用虚假 pass 换取产品叙事。

### Alternatives Rejected

- 用主观报告宣称复利：拒绝，不可复跑。
- 用 UI 展示状态当成熟证据：拒绝，UI 不拥有 runtime SoT。
- 调低 gate 阈值：拒绝，会污染成熟度证明。

### Execution Plan

1. 定义 metrics schema 与数据来源。
2. 接入 maturity summary 或新增 proof gate 脚本。
3. 增加 fixtures/tests，覆盖 pass/warn/not-yet/fail path。
4. 对真实 dogfood vault 只读或安全运行一次，生成 receipt/report。
5. 更新 docs/PROGRESS。
6. 跑 focused tests、verify、qa-review、closed-loop。

### Stop Conditions

- 指标无法从当前 receipts/summary 可靠复算。
- 需要外部服务、凭据或高风险 vault 写操作。
- Gate 为了 pass 需要改历史数据或降低阈值。

### In Scope

- Knowledge compounding metrics/gate。
- Investing/research dogfood proof receipt/report。
- Tests and docs。

### Out Of Scope

- 新 LLM backend。
- prompt proposal auto-apply。
- hosted dashboard。
- 自动放开 Judgment/L3。

### Affected Files / Modules

- `scripts/dogfood_maturity_gate.py` 或新增 proof gate script
- `tests/test_dogfood_maturity_gate.py` 或新增 proof gate tests
- `docs/Furnace Next Direction Post-P4.md` 或本 plan 的 follow-up section
- `PROGRESS.md`

### Verification Plan

- Focused proof gate tests。
- Dogfood proof dry-run/collect receipt。
- `bash scripts/verify.sh`
- qa-review + closed-loop。

### Fail Gate

- 指标不可复算或依赖人工观察。
- Gate 把机制存在误判为复利发生。
- 历史 receipt 被修改或 maturity 阈值被降低。

### Residual Risks

- 首版 gate 可能输出 not-yet；这是可接受结果，说明复利证据不足而不是工程失败。
- 真实复利需要多轮 dogfood，不一定能在单个 milestone 中完全证明。

## Stop Conditions

- 需要共享环境、远端环境、凭据、付费服务或不可逆外部副作用。
- 为了降低表面复杂度而删除、隐藏或伪造治理事实。
- 需要改变 repo 事实分层规则或 raw/wiki/output 边界。
- 任何 milestone 触发 L3/Judgment 自动扩权诉求。
- 连续 3 轮 debug/review 仍无法收敛。
