# 炼丹炉 Progress — Furnace 世代

> 本文件已于 2026-04-24 重置。历史 91 段（EP-001 ~ EP-029 / Step 1 ~ Step 91，P1A→EP-021 旧路线）已随 Furnace SoT 重构废弃，不再作为执行事实源；git 历史仍是唯一不可抹除的审计轨迹。
>
> 新世代以 `docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md` 为 SoT，按 §12.4 Rollout Gate Matrix 分 M0-M5 推进。

## 状态

- **M7.4b2 + M7.4b3 Kill Switch Hooks → Alchemy Auto + L3 Generate — 完成**
  - **目的**: 完成 M7.4 拆分序列剩余 2 个 hook，4 个 disable flag 全部接到唯一 chokepoint。
  - **核心做法**:
    - b2: `src/aiwiki/runner/alchemy.py:run_alchemy_propose_apply` 入口 hook `disable_alchemy_auto` → skipped dict
    - b3: `src/aiwiki/execution/l3_proposals.py:create_l3_proposal` 入口 hook `disable_l3_generate` → skipped dict（先于 ensure_layout / target validation：kill switch 胜过 validation）
  - **shape**: 与 M7.4b1 对称 — `{"status":"skipped","flag":...,"reason":...,<入口语义字段>}`。
  - **测试**: 加 2 cases（b2 / b3），各覆盖 disabled → skipped dict + 不写盘。
  - **Gates**: `bash scripts/verify.sh` 5/5 稳定 pass（1342 unit + 12 acceptance / 93% coverage）。
  - **Stop Lines**: 0 acceptance golden 漂移 / 0 receipt 字段改 / 0 success-path 字段改。
  - **价值**: 9+ Contract 第 6 条 "Kill switch by design" 4/4 hook 完整覆盖：8.5 → 9.0+。

- **M7.4b1 Kill Switch → Lane Apply Hook — 完成**
  - **目的**: M7.4 拆分序列第 2 步。把 `disable_lane_apply` 接到 `run_alchemy_lane_apply` 唯一 chokepoint。
  - **核心做法**: `src/aiwiki/runner/alchemy.py:run_alchemy_lane_apply` 函数最早处先调 `autonomy_policy.disabled_reason("disable_lane_apply")`；disabled → early-return `{"status":"skipped","flag":"disable_lane_apply","reason":...,"lane":...,"scope":...}` dict，不写 receipt / lane history / nightly artifact。
  - **shape 选择**: lane apply caller 期望 dict 返回（不像 LLM 入口期望异常），所以用 skipped dict 而非 `AutonomyDisabled` exception。`status` key 区别正常成功路径。
  - **测试**: `tests/test_autonomy_policy.py` 加 2 cases（disabled → skipped + 0 写盘 / 缺 policy 时 ValueError 仍正常抛）。
  - **Gates**: `bash scripts/verify.sh` 5/5 稳定 pass。
  - **Stop Lines**: 0 acceptance golden 漂移 / 0 receipt 字段改 / 0 success-path 字段改。

- **M7.4a Kill Switch Core (External LLM Hook) — 完成**
  - **目的**: 把 9+ Contract 第 6 条 "Kill switch by design" 从 "CLI discipline" 提升为 "runtime policy"。最小可信 slice：policy 文件 + global env override + 唯一 hook = external LLM。
  - **核心做法**: 新模块 `src/aiwiki/autonomy_policy.py`（~110 LOC，stdlib-only）：`AutonomyPolicy` dataclass / `load_policy(root)` / `is_disabled(root, flag, env=)` / `disabled_reason(...)`。Policy 文件位于 `.aiwiki/state/autonomy-policy.json`，缺失/损坏 → 全 enabled（向后 100% 兼容）。`AIWIKI_DISABLE_AUTOMATION=1` 全局 panic-button override。
  - **Hook**: `src/aiwiki/llm.py:create_backend_client` 入口先调 `disabled_reason("disable_external_llm")`；disabled → 抛新增的 `AutonomyDisabled(LLMError)` 子类异常。所有现有 caller 已捕 `LLMError`，无需修改 → 0 行为漂移。
  - **测试**: `tests/test_autonomy_policy.py` 10 cases（缺文件 / 文件存在 / 损坏 / 非 dict / 未知 flag / env override / env 严格仅 "1" 触发 / reason 区分 env 与 file / hook 抛异常 / 缺 policy 时默认路径不变）。
  - **Gates**: `bash scripts/verify.sh` 5/5 稳定 pass（1340 unit + 12 acceptance / 93% coverage）。
  - **Stop Lines**: 0 acceptance golden 漂移 / 0 receipt 字段改 / 0 shell summary 改 / 0 第三方依赖。
  - **拆分确认（oracle-validated）**: M7.4 拆为 a/b/c/d。本轮交付 a。M7.4b = 剩余 3 hook (lane apply / alchemy auto / l3 generate)；M7.4c = autonomy CLI surface；M7.4d = model policy。
  - **价值**: 9+ Contract 第 6 条 7.4 → 8.5+（剩 0.5 在 M7.4b 4 hook 全到位时补）。

- **M7.3.1 Stage B: Metrics History + Delta — 完成**
  - **目的**: 让 `aiwiki metrics` 不仅看当下 backlog（Stage A 已交付），还能看到趋势。9+ Contract 第 1 条 "Observe before schedule" 趋势维证据成立。
  - **核心做法**: 新增 `src/aiwiki/metrics_history.py`（薄模块，~120 LOC）：`append_snapshot` + `find_baseline` + `format_delta_block`。`aiwiki metrics` 每次执行 append 一条 JSONL 到 `.aiwiki/state/metrics-history.jsonl`，schema = `{"ts": ISO, "metrics": {<7 key>: float|null}}`。`--delta 7d/30d` 倒序扫描 jsonl 找 baseline，输出 trailing delta block；无 baseline 时打印 `# delta 7d: no baseline within window`。
  - **CLI**: `parsers.py` 加 `--delta` flag（choices `7d`/`30d`）；`dispatch.py` `metrics_command` 集成 history append + delta render。
  - **测试**: `tests/test_metrics_history.py`（8 cases，覆盖 append / append-only / 缺失文件 / window 边界 / 跳过 malformed / format with-without baseline）+ `tests/test_cli.py` 加 3 cases（append jsonl / `--delta 7d` no-baseline / `--delta 30d`）。
  - **Gates**: `bash scripts/verify.sh` 5/5 稳定 pass（1330 unit + 12 acceptance / 93% coverage）。
  - **Stop Lines**: 0 metric key 名 / 0 metric JSON schema / 0 shell summary 字段 / 0 acceptance golden 触动 / 0 第三方依赖。
  - **价值**: 9+ Contract 第 1 条证据从单点（当下 backlog）扩展到双点（当下 + 趋势）。

- **M7.3 Stage A: Real Review Counts — 完成**
  - **目的**: 实化 `metrics_io._read_review_counts` stub（之前 `return ()`），让 `review_closure_rate` metric 真实反映 backlog（之前 `pending_now=0` 导致 ratio 失真偏高）。
  - **核心做法**: `metrics_io._read_review_counts(root)` 复用 `app_lifecycle.collect_curated_pages` + `review_queue`，返回 `(("pending_decisions", n), ("pending_judgments", m))`；运行时容错 try/except 包裹保持 metrics 命令韧性；`tests/test_metrics_io.py` 新增 `test_review_counts_reads_pending_decisions_and_judgments` + 修正 empty-vault 断言（snapshot.review_counts 现在是 `{"pending_decisions":0,"pending_judgments":0}` 而非 `()`，更诚实）。
  - **Gates**: `bash scripts/verify.sh` 5/5 连续 pass。
  - **Stop Lines**: 0 metric key 名改动 / 0 metric JSON schema 改动 / 0 shell summary 既有字段改动 / 0 `compute_review_closure_rate` 公式改动 / 0 acceptance golden 触动。
  - **Stage B 后续**: metrics-history.jsonl + `--delta 7d/30d` 拆分为独立 M7.3.1（避免单轮改动过大）。
  - **价值**: 9+ Contract 第 1 条 "Observe before schedule" 证据真实化（review backlog 不再隐形为 0）。

- **M7.2 Product Surface Reconciliation — 完成**
  - **目的**: 通过 explorer + oracle 双检确认 first-screen surface 已 converged，把原路线图（缩 core commands / today single-feed）降级为"文档纠偏 + 防回归 contract test"，避免负收益破坏。
  - **核心做法**: `tests/test_product_shell_smoke.py` 新增 `ProductShellFirstScreenContract`（6 个断言：首屏只挂 Universal Input + Today + Advanced，不挂 AskBox / DropZone）；`docs/Furnace M7 Roadmap.md` §4 重写为"already converged" + 综合分目标下调为 8.6~9.0。
  - **Gates**: `bash scripts/verify.sh` pass。
  - **Stop Lines**: 0 core commands 改动 / 0 today 输出改动 / 0 legacy helper 删除 / 0 dispatch.py|parsers.py 改动。
  - **价值**: 防止未来首屏回退为 dashboard，避免基于错误前提做有害改动。9+ Contract 实质分数不变（M7.2 本就不在六条之列）。

- **M7.1 Scoped Lane Hardening (Level A) — 完成**
  - **目的**: 修正 9+ Contract 第 3 条 "Scoped primitives only"，让 lane primitive apply receipt 显式声明 scope 与 enforcement 状态，消除"scoped preview + global apply"名实不符。
  - **核心做法**: `runner/alchemy.py` lane primitive receipt 顶层新增 `scope_declared`(取自 plan.scope_preview)、`scope_enforced=false`、`scope_enforcement_reason="primitive_global_only:compile_lint_nightly_have_no_scope_filter"` 三字段；`tests/test_alchemy_lanes.py` 补 unit test 断言；2 个 acceptance golden（`case_light_primitives_compile_lint` / `case_light_primitives_nightly`）刷新含新字段。
  - **Gates**: `bash scripts/verify.sh` 5/5 连续 pass（unit + acceptance 12/12）。
  - **Stop Lines**: 0 既有 receipt 字段改动 / 0 `compile_wiki|lint_wiki|nightly_health` 签名改动 / 0 production 行为变化 / golden 触动 2 文件（在 stop-line 内）。
  - **价值**: 9+ Contract 第 3 条 7.0 → 8.0+。Level B（实质 scope filter）留作后续。

- **M7.0 Gate Unification — 完成**
  - **目的**: 让 `bash scripts/verify.sh` 真正代表 baseline，统一 unit + acceptance 主门。
  - **核心做法**: `scripts/verify.sh` 末尾追加 `bash scripts/run_acceptance.sh`，使 verify 一次性跑 ruff + compileall + coverage(unittest) + cli help + acceptance(pytest 12 cases)。
  - **Gates**: `bash scripts/verify.sh` 5/5 连续 pass（1322 unit tests / 93% coverage / 12 acceptance pass）。
  - **Stop Lines**: 0 acceptance test 修改 / 0 receipt|audit|shell-summary schema 改动 / 0 production code 改动。
  - **价值**: 消除 oracle 评估指出的"verify pass ≠ acceptance pass"短板，9+ Contract 系列后续 milestone 的 gate 可信度提升到真实状态。
  - **目的**: 让 `bash scripts/verify.sh` 真正代表 baseline，统一 unit + acceptance 主门。
  - **核心做法**: `scripts/verify.sh` 末尾追加 `bash scripts/run_acceptance.sh`，使 verify 一次性跑 ruff + compileall + coverage(unittest) + cli help + acceptance(pytest 12 cases)。
  - **Gates**: `bash scripts/verify.sh` 5/5 连续 pass（1322 unit tests / 93% coverage / 12 acceptance pass）。
  - **Stop Lines**: 0 acceptance test 修改 / 0 receipt|audit|shell-summary schema 改动 / 0 production code 改动。
  - **价值**: 消除 oracle 评估指出的"verify pass ≠ acceptance pass"短板，9+ Contract 系列后续 milestone 的 gate 可信度提升到真实状态。

- **M6.7.6 LLM receipt single entry — 完成（commit `1ea5321`）**
  - **目的**: 消除 `build_llm_attempt_receipt / classify_fallback_stage / append_receipt_and_audit` 在 runner 多处重复样板，建立单一入口。
  - **核心做法**: `src/aiwiki/runner/receipts.py` 新增 `record_llm_attempt(payload, *, runs_log, audit_log)` 封装三步；`runner/workflows.py` 18 处 caller 改为调用该 helper（共 23 处 `record_llm_attempt` 引用）；`runner/__init__.py` re-export；`_append_llm_receipt_and_log` 保留为 thin compat。三 primitive owner 仍在 `runner/receipts.py`，0 outside-owner 直接调用。
  - **Gates**: `scripts/verify.sh` exit=0（1322 tests，coverage 93%）；`scripts/run_acceptance.sh -v` 12/12 pass。
  - **Stop Lines**: 0 receipt schema / 0 audit schema / 0 `runs.jsonl` event 改动 / 0 acceptance golden 触动。

- **M6.7.7 remove input_router.js — 完成（commit `6943512`）**
  - **目的**: 删除 Universal Input 早期前端路由镜像，前端 input 仅走 inline pill (M6.7.4) → renderUniversalInput → backend `aiwiki.cli` universal drop。
  - **核心做法**: `input_router.js` 已在 M6.7.5 commit `230a4a1` 中被 designer 越权删除（详见下文协调事故）；本 commit 完成其余清理 — `main.js` 重 build、`src/plugin.js` `runUniversalInputCommand` 直调 backend drop、`src/render_input.js` submit 不再调用 `classifyUniversalInput`、`build.sh` 移除 `input_router`、`tests/test_product_shell_universal_input.py` router-mirror 测试改写为 backend drop-router 契约测试。
  - **Gates**: `node --check main.js` exit=0；`scripts/verify.sh` exit=0（1322 tests）；`scripts/run_acceptance.sh -v` 12/12 pass。
  - **Stop Lines**: 0 acceptance golden / 0 attachment pill 行为改动 / 0 modal 行为改动 / `grep -rn "input_router" .obsidian/plugins/` 返回空。

- **M6.7.5 typography token + Today Feed visual weight — 完成（commit `230a4a1`）**
  - **目的**: 兑现 SoT 视觉意图——Today Feed 信息层级（title/body/meta/timestamp）通过 typography token 体现，不再依赖硬编码 font-size/font-weight。
  - **核心做法**: `.obsidian/plugins/furnace-product-shell/styles.css` 新增 `--furnace-type-{display,title,body,meta,mono}` + `--furnace-weight-{bold,normal}` 7 个 token（共 10 处 `furnace-type-` 引用）；Today Feed `.furnace-today-feed-*` 替换硬编码值为 `var(--furnace-type-*)`；`tests/test_product_shell_smoke.py` 新增 5 个 contract tests（token 存在 / Today Feed 用法 / 无新色板 / class 保持 / 与 attachment pill 无冲突）。
  - **Gates**: `node --check main.js` exit=0；`scripts/verify.sh` 5/5 pass；`scripts/run_acceptance.sh -v` 5/5 pass (12/12)。
  - **Stop Lines**: 0 acceptance golden 触动 / 0 新色板 / 0 DOM 结构改动 / 0 class 名改动。
  - **协调事故记录**: 该 commit 越权删除了 `input_router.js`（属于 M6.7.7 scope），导致 commit 落地时 verify 实际处于失败状态（router mirror tests `FileNotFoundError`），但 designer 报告的 5x verify pass 是失实的。Wave2 三任务并行写共享 worktree 引发交叉污染：M6.7.6 fixer 看到的 worktree 缺 router 文件，M6.7.7 fixer 看到的 worktree 含 M6.7.5 的 typography contract tests 但缺 token CSS。事后由 orchestrator 在共享 worktree 中拆分剩余改动为 M6.7.7 (`6943512`)→M6.7.6 (`1ea5321`)，每步本地验证 verify+acceptance pass 后 commit。教训：写盘类 specialist 不应在共享 worktree 中并行；下次 Wave 须串行或为每 specialist 准备隔离 worktree。

- **M6.7.4 Universal Input attachment pill — 完成（commit `af09c70`）**
  - **目的**: 兑现 SoT 视觉意图——input 区粘贴/拖入文件应在输入框下方显示紧凑 pill（filename + remove ×），而非弹出 DropFileModal 作唯一反馈；Modal 仍保留供其他 call site。
  - **改动面**: `.obsidian/plugins/furnace-product-shell/main.js` (+92/-)、`src/plugin.js` (+14/-)、`src/render_input.js` (+78/-)、`styles.css` (+37) 引入 `furnace-input-attachment` token；`tests/test_product_shell_smoke.py` 新增 5 个 contract tests（pill DOM / remove × / 多附件 / 空状态 / modal 隔离）。
  - **Gates**: `node --check main.js` exit=0；`scripts/verify.sh` 5/5 pass（1322 tests，coverage 93%）；`scripts/run_acceptance.sh -v` 5/5 pass (12/12)。
  - **Stop Lines**: 0 acceptance golden change；0 新色板（沿用 `--furnace-*` token）；DropFileModal 仍保留供非 input call site；contract 已归档到 `.codex/contracts/archive/M6.7.4-attachment-pill.md`。
  - **协调修复**: 本 milestone 首次提交因并行 agent 误执行 `git reset` 丢失（M6.7.3 commit `431dde1` 也被同操作回退），通过 reflog `git reset --hard 431dde1` 恢复 M6.7.3 后由 designer 在严格 git 约束下重做 M6.7.4，最终 commit `af09c70b9d4ada1a30e55e1939428975c560f902`。

- **M6.7.3 silent fail observability — 完成**
  - **目的**: 将 AGENTS.md “不得静默吞错”落到 6 条降级路径；主流程继续 non-blocking，但失败通过 `runs.jsonl` 事件或返回 sentinel / `auto_failed` 可观测。
  - **核心做法**: `ask.py` / `notify.py` / `drop.py` / `runtime_surfaces.py` 复用 `runner.receipts._append_log` 写 `.aiwiki/logs/runs.jsonl`；`summary.py` metrics 异常返回 `_metrics_unavailable` sentinel；nightly auto-consume per-item 失败返回 `auto_failed`。
  - **测试**: 新增/扩展失败路径单测覆盖 notify outer guard、notify audit fallback、ask notify dispatch、metrics sentinel、nightly per-item + outer、URL image skip。
  - **Gates**: `scripts/verify.sh` 5/5 pass（1320 tests，coverage 93%，"All checks passed!"）；`scripts/run_acceptance.sh -v` 5/5 pass（12/12）；focused failure-path tests 14 pass。
  - **Stop Lines**: 0 acceptance golden change；0 receipt/audit/core shell-summary schema change；主流程不新增 RuntimeError；contract 已归档到 `.codex/contracts/archive/M6.7.3-silent-fail-observability.md`。

- **M6.7.2 cli.py subpackage split — 完成（literal move + import rewire，本地待 push）**
  - **现状**: `src/aiwiki/cli.py` 1955 LOC 巨石已删除，替换为 `src/aiwiki/cli/` subpackage：`__init__.py` 41 LOC、`__main__.py` 8 LOC、`dispatch.py` 1045 LOC、`parsers.py` 915 LOC
  - **目的**: 在不改变 CLI 行为、stdout/JSON/exit-code、schema 的前提下，把 argparse 注册与 main dispatch 拆开，为后续 command-group 拆分降低风险
  - **批次**: `parsers.py` 承接 `build_parser`、legacy/top-level/drop parser registration 和 parser helper；`dispatch.py` 承接 `main()`、universal drop rewrite、today/metrics/text formatter、resolve helpers；`__init__.py` re-export 原 `aiwiki.cli` public/import surface，并同步 patch seam 到 owner module；`__main__.py` 保持 `python -m aiwiki.cli` 入口
  - **指标**: 0 command schema 改动；0 stdout/JSON/exit-code 预期改动；`from aiwiki.cli import main, build_parser` smoke pass；`PYTHONPATH=src python3 -m aiwiki.cli --help` pass；`tests/test_cli.py` 84 pass；`scripts/run_acceptance.sh -v` 5/5 次 12/12 pass；`scripts/verify.sh` 5/5 次 exit=0 且 "All checks passed!"；coverage 93%（1320 tests）
  - **Stop Lines**: 未新增 command-group 文件；未改 dispatch 分支语义；未改 receipt/audit/shell schema；未保留 `src/aiwiki/cli.py` 文件；public surface 经 `__init__.py` re-export 保持；vault launcher/runtime-root check 同步从 `cli.py` 改为 `cli/__main__.py`
  - **Critical Notes**: `app_vault.py` 的 runtime-root 验证/launcher guard 必须跟随 `cli.py` 删除调整，否则 new-vault smoke 会误判 runtime root；`dispatch.py` 避免从 `aiwiki.runner` façade 导入，改为 sibling owner imports，避免 `app_compile.ask_question` lazy import 与 runner façade 形成环；contract 已归档到 `.codex/contracts/archive/M6.7.2-cli-subpackage-split.md`
  - **路线图**: M6.7.3 silent fail 收口 → M6.7.4 Universal Input attachment pill → M6.7.5 typography token + Today Feed 视觉权重 → M6.7.6 LLM receipt 单一入口 → M6.7.7 移除 input_router.js 前端镜像（详见 `docs/Furnace M6.7 Roadmap.md`）

- **M6.7.1 Acceptance Determinism — 完成（test-only normalization，本地待 push）**
  - **目的**: 修复 `tests/test_acceptance_loop.py::test_happy_run_ask_replay` 在 `scripts/verify.sh` 中 byte-flaky 失败（`duration_ms` 1 vs 0），恢复 acceptance gate 可信度，移除真实动态字段对 byte-frozen golden 比较的污染
  - **背景**: oracle 评审（task `ses_230d4bc9fffeqJ5yl2LLbLfMp1`）+ designer 评审（task `ses_230d472d8ffeyb0q2lSo7J1w3w`）综合得出 M6.7 路线图（`docs/Furnace M6.7 Roadmap.md`），M6.7.1 为最高 ROI 首发
  - **核心做法**: 在 `tests/test_acceptance_loop.py` 新增 `_normalize_jsonl_dynamic_fields` + `_should_normalize`；`_assert_files_byte_equal` 对 `.aiwiki/logs/llm-receipts.jsonl` / `.aiwiki/logs/runs.jsonl` 走 normalization（top-level `duration_ms` 替换为 `0`）后 byte compare；REFRESH 路径同步走 normalization 保证对称；其他文件保持原 byte compare 不变
  - **指标**: tests/test_acceptance_loop.py 67 行 +66/-1；0 production 代码改动；0 schema/receipt/audit 改动；5 次 `scripts/run_acceptance.sh -v` 12/12 全 pass；5 次 `scripts/verify.sh` 全 pass exit=0（"All checks passed!"）；coverage 维持 93%（1761 missed / 35815 lines）
  - **Stop Lines**: 0 production code 改动（仅 `tests/test_acceptance_loop.py`）；0 receipt/audit/shell-summary schema 改动；不删除已有 byte-frozen golden；不在 production 伪造 `duration_ms`（仍由 real elapsed time 计算）；`response_id`/`usage`/`model_final`/`backend_effective`/`status`/`event` 仍 strict
  - **Critical Notes**: 当前只 normalize top-level 字段；嵌套 dict 内的动态值（若未来引入）需扩展递归；只覆盖 `duration_ms`，未来若新增 `latency_p95_ms` 等需扩 `_DYNAMIC_RECEIPT_FIELDS`；contract 已归档到 `.codex/contracts/archive/M6.7.1-acceptance-determinism.md`
  - **路线图**: M6.7.2 cli.py 拆分 → M6.7.3 silent fail 收口 → M6.7.4 Universal Input attachment pill → M6.7.5 typography token + Today Feed 视觉权重 → M6.7.6 LLM receipt 单一入口 → M6.7.7 移除 input_router.js 前端镜像（详见 `docs/Furnace M6.7 Roadmap.md`）

- **M6.6.4 app_shell subpackage split — 完成**
  - **实现**: `src/aiwiki/app_shell.py`（1836 LOC）拆为 `src/aiwiki/app_shell/`：`__init__.py` 105 LOC、`helpers.py` 153 LOC、`surfaces.py` 579 LOC、`controls.py` 586 LOC、`meta.py` 217 LOC、`summary.py` 305 LOC、`rendering.py` 411 LOC；原单文件已删除
  - **兼容性**: 6 个外部 importer 0 修改；`aiwiki.app_shell` 通过 façade re-export 保持 33 个顶级 def（含 `_` internals）import surface
  - **Mock seam**: 保留 `aiwiki.app_shell.utc_now` 与 `aiwiki.app_shell.load_llm_receipt_history`；`load_llm_receipt_history` 实际源模块为 `aiwiki.app_state`
  - **Gates**: import/mock seam smoke pass；focused pytest 374 pass；`bash scripts/verify.sh` pass（1314 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` 12 pass；acceptance 稳定性 5/5 pass
  - **Stop Lines**: 函数 AST body 未变化；protected importer diff 为空；ShellSummary acceptance golden 未变化；contract 已归档到 `.codex/contracts/archive/M6.6.4-app-shell-subpackage.md`

- **M6.6.3 app_linting subpackage split — 完成**
  - **实现**: `src/aiwiki/app_linting.py`（2001 LOC）拆为 `src/aiwiki/app_linting/`：`__init__.py` 61 LOC、`core.py` 410 LOC、`phases.py` 1029 LOC、`repair.py` 717 LOC、`nightly.py` 757 LOC；原单文件已删除
  - **兼容性**: 4 个外部 importer 0 修改；`aiwiki.app_linting` 通过 `__init__.py` re-export 保持 `Finding/lint_wiki/nightly` 与 `_` internals import surface
  - **Mock seam**: 保留并补齐 `aiwiki.app_linting.datetime` monkeypatch seam，同步转发到 `core.datetime`，acceptance 固定时钟恢复通过
  - **Gates**: import 兼容 smoke pass；`tests/test_linting.py -v` 8 pass；`bash scripts/verify.sh` pass（1314 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` 12 pass；acceptance 稳定性 5/5 pass
  - **Stop Lines**: 函数 body 未做行为改写（仅模块级 import / re-export / compat seam）；protected importer diff 为空；contract 已归档到 `.codex/contracts/archive/M6.6.3-app-linting-subpackage.md`

- **M0 Baseline Freeze（已完成，4 commit 未 push）**
  - `83eff68` Furnace SoT 首轮重构（docs 归并到两份 SoT + 物理归档 7 份旧设计）
  - `6f1016f` `e3df4fb` SoT 再加固（§2.1 Current Implementation Map / §2.2 9+ Feasibility Contract / §12.3 scoped primitive 保护清单 / §12.4 Rollout Gate Matrix / §12.5 Stop Lines）
  - `30a6a66` 代码 docstring 对齐（`src/aiwiki/execution/__init__.py` + `src/aiwiki/app_compile.py` 更新为 EP-018B 已完成事实 + scoped primitives 保护说明；修正过期 EP-018A placeholder / self-reference 语义）
  - `b2eec74` 文档归档（`docs/product_shell_ui_v3_review.md` → `docs/archive/`）
  - baseline：`bash scripts/verify.sh` 全绿，543 tests / 93% coverage
  - 严格三重删除判据（SoT 无 slot + 非 scoped primitive + 无 CLI/runtime/test 依赖）下全源码无删除候选；execution owner 11 份齐全、compile deterministic baseline 完整

- **M0.6 Furnace SoT Status Reconciliation — 完成（commit `353dbf4`，本地未 push）**
  - **实现**: 修正两份 SoT 的实现状态描述，明确 planner-log observe-only decision log、L3 manual baseline + blocked preview、`output/_candidates/elixirs/` candidate 主路径已落地
  - **安全边界**: 仅文档状态对齐；不宣称 automatic scheduler、automatic L3 proposal generation、universal audit stream 已默认可用
  - **SoT 对齐**: 过期的 “planner-log 未落地 / L3 当前 planned / elixir candidate plane planned” 局部表述已收敛为 partial/deferred 边界
  - **测试**: focused stale phrase scan 无旧 planner/L3/candidate 状态表述；`bash scripts/verify.sh` pass
  - **Gates**: `bash scripts/verify.sh` pass（1043 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M1 Signal Observability — EP-M1.1 完成**
  - **SoT §2 Signal Taxonomy 已冻结**（§2.1 Field spec / §2.2 Canonical JSON / §2.3 Dedupe / §2.4 trace_id / §2.5 Fail-fast / §2.6 Evolution）
  - **实现**: `src/aiwiki/signals/schema.py`（484 LOC，纯函数 + dataclass + 7 项 public API）+ `src/aiwiki/signals/__init__.py`（21 LOC 收窄）
  - **Fixtures**: 5 份 `tests/fixtures/signals/*.jsonl`（valid / dedupe_replay / bad_missing / bad_unknown_version / trace_backlink_chain）
  - **Tests**: `tests/test_signals_schema.py`（563 LOC, 70 tests；包括 12 个攻击向量 + canonical JSON 幂等 + dedupe/trace 语义）
  - **指标**: 543 → 613 tests / coverage 93%→93% / schema.py 97%
  - **Gates**: qa-review pass（oracle 2 轮，ses `ses_240eb35cdffeyKhCazoYJ2tI16`）/ qa-runtime pass / closed_loop PASS

- **M1 Signal Observability — EP-M1.2 完成（本地未 push）**
  - **实现**: `src/aiwiki/signals/collector.py`（161 LOC, replay 编排 / runtime_write_lock / dedupe set / append+fsync）+ `src/aiwiki/signals/adapters.py`（187 LOC, 3 source adapter + archive noop）+ CLI `signals-replay` 子命令
  - **Schema Step 2 deferred 执行**: `source_event_ref` validator 放宽连字符 + `:<row_or_id>` 收紧为仅 `protocol_learning_event` 允许 + absolute path with allowed substring 拒绝
  - **Kind 映射**: `runtime_history.review → review_feedback` / `runtime_history.nightly → schedule_tick` / `llm_receipt.status=failed+protocol → runtime_failure`；其他 event_type 全 unmapped（非 invalid）
  - **Observe-only 固化**: AST allowlist（stdlib + `aiwiki.signals.*` + `aiwiki.app_utils`）+ FileSystemDiff 断言
  - **Idempotency**: 全量 replay + in-memory set；dedupe_key（内容身份）与 trace_id（批次标识）解耦；仅"文件内部同 dedupe 不同 trace" HARD FAIL（corrupt 语义）
  - **Tests**: `tests/test_signals_collector.py`（64 methods）+ `tests/test_signals_schema.py` 扩充 + 4 组 repo-shaped fixture（case_basic / case_idempotent / case_trace_conflict / case_bad_event）
  - **指标**: 613 → 701 tests / coverage 93% / collector 90% / adapters 100% / schema 98%
  - **Gates**: qa-review pass（oracle 2 轮：`ses_2405b1840ffeZhRnNuy5nBYJN1` Round 1 must-fix → `ses_24040bbbfffe25KME1rRgxaq69` Round 2 pass）/ qa-runtime pass / closed_loop PASS
  - **QA 轮次**: Round 1 must-fix（默认 trace_id replay 非幂等 + AST denylist 漏洞 + 无 golden payload）→ Round 2 pass
  - **Deferred 到 M1.3**: archive adapter 真实接入（需 `archive_event` path validator 收紧）+ `planner-log.jsonl` / `review-outcome.jsonl` writer + `raw_added` / `learning_threshold` / `run_log` 信号种类

- **M3.5 Delete alchemy-seal CLI alias — 完成（commit `ad9109e`）**
  - **实现**: 删除 `alchemy-seal` argparse 子命令、`run_alchemy_seal` runner 包装、`seal_elixir` Python API 兼容层，并清理 `src/aiwiki/execution/__init__.py` owner docstring
  - **测试清理**: 删除 6 个 seal alias 专项测试和 `tests/test_cli.py` dispatch case；不新增 promote 等价测试（promote 自身已有覆盖）
  - **SoT 清理**: `docs/Furnace Agent Architecture.md` 与 `docs/Furnace Evolution Mechanics.md` 不再描述 `alchemy-seal` 为 `alchemy-promote` 兼容别名
  - **残留扫描**: `src/ tests/ docs/` 中 `alchemy-seal` / `alchemy_seal` / `seal_elixir` / `run_alchemy_seal` 均 0 命中；`alchemy-seal` CLI 已由 argparse 报 `invalid choice`
  - **Gates**: `bash scripts/verify.sh` pass（970 tests / 93% coverage / `alchemy.py` 95% / `cli.py` 94%）；`closed_loop.sh --artifacts-only --require-contract` PASS
  - **QA 说明**: qa-review 记录为 same-context fallback；本会话未启动独立 reviewer（当前 agent policy 仅在用户显式要求 sub-agent 时允许），artifact 已写明 fallback reason

- **M4 Heavy/Light Dry-run Wrapper — 完成（commit `d36dee8`）**
  - **实现**: 新增 `src/aiwiki/planner/dry_run.py` read-only preview；新增 `run_alchemy_lane_dry_run`；新增 CLI `aiwiki alchemy heavy|light <scope> --dry-run`
  - **语义边界**: heavy 只消费 `enqueue-heavy`；light 只消费 `enqueue-light`；`generate-proposal` 不被 M4 heavy/light wrapper 消费；未提供 `--apply`
  - **Preview 内容**: stable `scope_preview`、可复现 `primitive_plan`、budget limit/used/exceeded reason、runtime lock availability；lock conflict 返回 `skipped` 不等待
  - **测试**: 新增 `tests/test_alchemy_lanes.py` 覆盖 lane filtering、scope 稳定排序、预算超限、锁冲突、缺文件空计划、read-only diff、CLI parser/dispatch/error path；`tests/test_cli.py` dispatch 表补 M4 入口
  - **Gates**: `bash scripts/verify.sh` pass（980 tests / 93% coverage）；manual smoke `PYTHONPATH=src python3 -m aiwiki.cli --root . alchemy light all --dry-run` pass；qa-review 按 calibration note 为 not-required；qa-runtime pass

- **M5.1 Controlled Alchemy Lane Apply Bridge — 完成（commit `6e593ac`）**
  - **实现**: `aiwiki alchemy heavy|light <scope> --apply --action-id <id>` 显式桥接到既有 `apply_machine_memory_actions_batch(..., dry_run=False)`
  - **安全边界**: `--dry-run` / `--apply` 互斥；`--apply` 必须先得到 `status=ok` 且 `selected_count>0` 的 M4 preview；必须显式传 `--action-id`；不自动选择 action；不执行 compile/lint/nightly/review/distill/propose/LLM
  - **Receipt 边界**: apply 路径只使用既有 low-risk action batch apply，它会先生成 per-action dry-run/bundle，再写 per-action receipt + batch receipt
  - **测试**: 覆盖 missing action ids、empty dry-run plan 拒绝、dry-run/apply 冲突、非空 preview 后 dispatch 到 receipted batch apply、CLI dispatch
  - **Gates**: `bash scripts/verify.sh` pass（984 tests / 93% coverage）；manual smoke `alchemy light all --apply --action-id demo` 在空 plan 下拒绝执行；qa-review not-required；qa-runtime pass

- **M5.2 Receipted Deterministic Lane Primitives — 完成（commit `0dd2e6b`）**
  - **实现**: `aiwiki alchemy heavy|light <scope> --apply --primitive compile|lint|nightly`；每个 deterministic primitive 执行后写 `output/control/execution-receipts/<action-id>.json` + `.aiwiki/state/execution-receipts.jsonl`
  - **安全边界**: 仍要求 M4 preview `status=ok` 且 `selected_count>0`；只允许执行当前 lane dry-run plan 中出现的 primitive；`nightly` 仅 light lane plan 可用；不调用 LLM-backed `run-compile/run-lint/run-nightly`
  - **Receipt 边界**: primitive receipt 标记 `generated_by=aiwiki-alchemy-lane`、`operation=alchemy-lane-primitive`、`subject_kind=alchemy_lane_primitive`、`revert_supported=false`，并保留 source plan/result summary
  - **测试**: 覆盖 deterministic primitive receipt 写入、history append、lane-plan gate、缺 action/primitive 拒绝、CLI primitive dispatch；M5.1 action bridge 保持
  - **Gates**: `bash scripts/verify.sh` pass（986 tests / 93% coverage）；manual smoke `alchemy light all --apply --primitive compile` 在空 plan 下拒绝执行；qa-review not-required；qa-runtime pass

- **M5.3 Deferred High-risk Lane Primitives — 完成（commit `724260b`）**
  - **实现**: heavy/light dry-run `primitive_plan` 每步新增 `apply_supported` / `apply_blocker`；新增 `deferred_primitives` 显式列出 `judge/distill/review/propose`
  - **安全边界**: `judge/distill/review/propose` 不进入 `--apply --primitive` 白名单；runner 直接调用同样拒绝 unsupported deferred primitives；light lane 标记为 `not_allowed_for_light_lane`
  - **评估结论**: `judge/distill/review/propose` 在拥有独立 scoped dry-run、receipt、audit 和 revert/不可回滚声明前，不得纳入 lane `--apply`
  - **测试**: 覆盖 dry-run apply eligibility metadata、deferred primitive records、runner rejection 和 CLI parser rejection
  - **Gates**: `bash scripts/verify.sh` pass（989 tests / 93% coverage）；manual smoke `alchemy heavy all --dry-run` pass；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M5.4 Lane Primitive Trace and Audit Metadata — 完成（commit `5d2069a`）**
  - **实现**: lane primitive execution receipt 顶层新增 planner `trace_id` / `trace_ids`，以及 `audit_stream=execution_receipts`、`audit_event=execution_receipt_history_append`、`audit_path=.aiwiki/state/execution-receipts.jsonl`
  - **返回值**: `primitive_results[]` 现在返回 `trace_id` 与 `audit_path`，便于调用方直接追溯本次 primitive apply
  - **边界**: 不新建通用 `.aiwiki/state/audit.jsonl`，不改造 action/archive/elixir receipts，不扩大 lane apply 白名单
  - **测试**: 覆盖 receipt JSON、history append 和 primitive result 的 trace/audit 字段
  - **Gates**: `bash scripts/verify.sh` pass（989 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M5.5 Enforce Dry-run Apply-supported Gate — 完成（commit `57b826d`）**
  - **实现**: runner 执行 lane primitive 前会定位当前 dry-run `primitive_plan` step，并要求 `apply_supported=true`
  - **安全边界**: step 不存在时保持现有 dry-run plan 缺失错误；step 存在但 `apply_supported=false` 时拒绝执行并暴露 `apply_blocker`
  - **回归**: `compile/lint/nightly` 合法路径保持；`judge/distill/review/propose` deferred rejection 保持；不扩大 primitive 白名单
  - **测试**: 覆盖 `apply_supported=false` 拦截且不会调用 primitive implementation
  - **Gates**: `bash scripts/verify.sh` pass（990 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.3 Tighten Archive Event Source References — 完成（commit `59a5b03`）**
  - **实现**: `archive_event` 的 `source_event_ref` validator 收紧为只接受 `execution-receipts` / `execution_receipts` 路径
  - **安全边界**: 不再接受泛化的 `wiki/archives/...#L<n>` archive substring；继续拒绝 row id、绝对路径和 `..`
  - **事实对齐**: 当前 archive adapter 的真实读取源是 `.aiwiki/state/execution-receipts.jsonl`，schema 现在与该 source path 对齐
  - **测试**: 覆盖 execution receipt ref 仍有效、archive page path 被拒绝、archive collector fixture 仍通过
  - **Gates**: `bash scripts/verify.sh` pass（990 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.4 Tighten Review Outcome Source References — 完成（commit `d4b49d5`）**
  - **实现**: `review_outcome` 的 `source_event_ref` validator 收紧为只接受 `review-outcome(s)` / `review_outcome(s)` event log path
  - **安全边界**: 不新增 `.aiwiki/state/review-outcome.jsonl` writer，不改造 `review_page`，不制造第二套 review 事实流
  - **事实对齐**: 当前 review 事件仍通过 `.aiwiki/state/runtime-history.jsonl` 映射为 `review_feedback`
  - **测试**: 覆盖 future review outcome event log path 有效、`wiki/reviews/...` page path 被拒绝、runtime_history collector 回归
  - **Gates**: `bash scripts/verify.sh` pass（993 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.5 Raw Added Observe-only Signals — 完成（commit `cfbdd51`）**
  - **实现**: `ingest_source` 与 `drop-url/drop-pdf/drop-image/drop-repo/drop-note` 写入 `event_type=raw-added` runtime history；collector 映射为 `kind=raw_added`
  - **安全边界**: 不直接扫描 `raw/`，不把 mtime 作为 dedupe identity，不触发 planner phase；`signals-replay` 仍 observe-only
  - **Dedupe**: raw_added dedupe identity 使用稳定 `stored_path`
  - **测试**: 覆盖 raw-added adapter mapping、collector replay、缺 stored path invalid、drop-note 和 ingest_source 的 runtime history writeback
  - **Gates**: `bash scripts/verify.sh` pass（997 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.6 Learning Threshold Observe-only Signals — 完成（commit `0878a00`）**
  - **实现**: `age_learnings(apply=True)` 在确有 aged learning 时按 protocol 分组写入 `event_type=learning-threshold` runtime history；collector 映射为 `kind=learning_threshold`
  - **安全边界**: 不直接扫描 `wiki/protocol-learnings/`，dry-run 不写 runtime history，不触发 planner phase；`signals-replay` 仍 observe-only
  - **Dedupe**: learning_threshold dedupe identity 使用稳定 `protocol + threshold_days + aged learning ids`
  - **测试**: 覆盖 aging writeback、dry-run no-write、adapter mapping、collector replay、缺 learning ids invalid
  - **Gates**: `bash scripts/verify.sh` pass（1002 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.7 Learning Threshold Planner-log Routing — 完成（commit `a4fba13`）**
  - **实现**: `write_planner_log` 识别 `kind=learning_threshold`；medium 产生 `generate-proposal` observe-only decision，high/critical 产生 `enqueue-heavy` observe-only decision，low routine ignore
  - **安全边界**: 只写 `.aiwiki/state/planner-log.jsonl`，保持 `mode=observe_only` 与 `side_effects_allowed=false`；不触发 proposal generation、phase 或 lane apply
  - **Reason codes**: 新增 `learning_threshold_observed`、`proposal_recommended`、`heavy_lane_recommended`、`learning_threshold_routine`
  - **测试**: 覆盖 severity routing 与 end-to-end planner-log writeback，确认不再产生 `unmapped_kind`
  - **Gates**: `bash scripts/verify.sh` pass（1007 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.8 Signal Source Boundary Guardrails — 完成（commit `4fc5ae6`）**
  - **实现**: 用测试冻结 `signals-replay` v1 source 白名单为 `runtime_history / llm_receipt / archive`；`run_log` 与 `review_outcome` source 明确报 unsupported
  - **安全边界**: 不新增 `run_log` source_kind / schema version，不新增 review-outcome writer，不把 runs log 伪装成现有 source_kind
  - **SoT 对齐**: source_kind 文案补齐 `execution_receipt`；明确 `.aiwiki/logs/runs.jsonl` 当前只是 runner health/logging artifact
  - **测试**: 覆盖 source whitelist 与 unsupported source 拒绝
  - **Gates**: `bash scripts/verify.sh` pass（1010 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.9 Counter Evidence Observe-only Signals — 完成（commit `550c986`）**
  - **实现**: compile runtime 在 `counter_evidence_scan` 发现 dirty source 触发的 candidate 时写入 `event_type=counter-evidence` runtime history；collector 映射为 `kind=counter_evidence`
  - **安全边界**: 不直接扫描 judgment / decision pages 作为 signal source；clean compile 复用旧 scan 时不重复写事件；不触发 planner phase
  - **Dedupe**: counter_evidence dedupe identity 使用稳定 `candidate_id`
  - **测试**: 覆盖 compile runtime writeback、adapter mapping、collector replay、缺 source ids invalid
  - **Gates**: `bash scripts/verify.sh` pass（1013 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.10 Counter Evidence Planner-log Routing — 完成（commit `5a7fa00`）**
  - **实现**: `write_planner_log` 识别 `kind=counter_evidence`；high 产生 `generate-proposal` observe-only decision，critical 产生 `enqueue-heavy` observe-only decision，low/medium routine ignore
  - **安全边界**: 只写 `.aiwiki/state/planner-log.jsonl`，保持 `mode=observe_only` 与 `side_effects_allowed=false`；不触发 proposal generation、phase 或 lane apply
  - **Reason codes**: 新增 `counter_evidence_observed`、`proposal_recommended`、`heavy_lane_recommended`、`counter_evidence_routine`
  - **测试**: 覆盖 severity routing 与 end-to-end planner-log writeback，确认不再产生 `unmapped_kind`
  - **Gates**: `bash scripts/verify.sh` pass（1017 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.11 Raw Added Planner-log Routing — 完成（commit `512112a`）**
  - **实现**: `write_planner_log` 识别 `kind=raw_added`；medium/high/critical 产生 `enqueue-light` observe-only decision，low routine ignore
  - **安全边界**: 只写 `.aiwiki/state/planner-log.jsonl`，保持 `mode=observe_only` 与 `side_effects_allowed=false`；不触发 compile、phase 或 lane apply
  - **Reason codes**: 新增 `raw_added_observed`、`raw_added_routine`；fixture 中 `unmapped_kind` 保留给真正未知 kind
  - **测试**: 覆盖 severity routing、end-to-end planner-log writeback、unknown kind fallback
  - **Gates**: `bash scripts/verify.sh` pass（1020 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.12 Planner Routing Coverage Guardrail — 完成（commit `c3084c5`）**
  - **实现**: planner-log tests 直接遍历 `aiwiki.signals.schema.KINDS`，要求每个 v1 signal kind 至少存在一条非 `unmapped_kind` routing
  - **安全边界**: 不新增 signal source/kind，不改变 routing 语义，不触发 compile/apply
  - **SoT 对齐**: 标明当前所有 v1 signal kind 均已有 observe-only planner routing；未实现的是 dry-run/execute 自动化
  - **测试**: 覆盖所有 v1 kind routing guardrail 与未知 kind fallback
  - **Gates**: `bash scripts/verify.sh` pass（1021 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M1.13 Nightly Schedule Tick Runtime History — 完成（commit `64b66d6`，本地未 push）**
  - **实现**: `write_nightly_health` 的 runtime-history `event_type=nightly` 事件支持追加 runner metadata；`run_nightly` 传入 `compile_limit / semantic_lint / llm_used`，并复用既有单条 nightly tick
  - **安全边界**: 不新增第二条 nightly event，不自动调用 `signals-replay` / `planner-log-replay`，不触发 scheduler 或 lane apply
  - **SoT 对齐**: `schedule_tick` 的真实 source 继续是 runtime-history nightly event；该 event 现在可回链 `state_path` / `repair_backlog` 并携带 run_nightly 关键参数
  - **测试**: `tests/test_runner.py` 覆盖 run_nightly 成功后只产生一条 nightly runtime-history event，且包含 protocol、compile_limit、semantic_lint、llm_used、state_path、repair_backlog
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_runner.RunnerTests.test_run_nightly_returns_top_level_audit_summary` pass；`bash scripts/verify.sh` pass（1043 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.1 Candidate Counter-evidence Defaults Guardrail — 完成（commit `ba5f452`）**
  - **实现**: 补充 `alchemy-distill` 保留 `counter_evidence: [NONE_FOUND]` 与 `confidence_level: low` 的 candidate rewrite guardrail
  - **安全边界**: 不改变 promote gate；不迁移旧 `wiki/elixirs/` 直写文件；只覆盖新 candidate plane
  - **SoT 对齐**: 明确 M2.1 默认字段覆盖 `alchemy-start` 与 `alchemy-distill` rewrite path
  - **测试**: `tests/test_alchemy.py` 覆盖 distill 后默认字段仍存在
  - **Gates**: `bash scripts/verify.sh` pass（1022 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.2 Finalize Validation No Half-write Guardrail — 完成（commit `9343cad`）**
  - **实现**: 补充 finalize provenance/anchor validation failure 后 candidate 文件保持不变的 guardrail
  - **安全边界**: 不改变 promote gate；finalize 仍只做结构校验且不强制 `counter_evidence` 非空
  - **SoT 对齐**: 明确 M2.2 校验失败不得半写 candidate 状态
  - **测试**: `tests/test_alchemy.py` 覆盖 missing promoted source validation 失败不改写文件
  - **Gates**: `bash scripts/verify.sh` pass（1022 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.3 Promote Gate Receipt Evidence Guardrail — 完成（commit `969f760`）**
  - **实现**: promotion receipt `bundle` 记录当次 promote gate 通过的 `counter_evidence` 与 `confidence_level`
  - **安全边界**: 不改变 promote gate 规则；gate 失败仍在任何 settled/tombstone/receipt 写入前停止
  - **SoT 对齐**: 明确 M2.3 起 execution receipt history 可直接审计 promote evidence
  - **测试**: `tests/test_alchemy.py` 覆盖 promotion receipt 记录 counter-evidence gate fields
  - **Gates**: `bash scripts/verify.sh` pass（1023 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.4 Revert/Demote Receipt Transition Evidence Guardrail — 完成（commit `7ae2c7d`）**
  - **实现**: `elixir_revert` / `elixir_demotion` receipt `bundle` 记录状态迁移和 candidate/wiki 双平面路径
  - **安全边界**: 不改变 revert/demote 写盘顺序、hash stale guard、dependency break 语义或 rollback 行为
  - **SoT 对齐**: 明确 M2.4 起 revert/demote receipt 可直接审计 transition evidence
  - **测试**: `tests/test_alchemy.py` 覆盖 revert/demote receipt bundle 的 state transition 与 path evidence
  - **Gates**: `bash scripts/verify.sh` pass（1023 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.5 Legacy Seal Alias Absence Guardrail — 完成（commit `50e970e`）**
  - **实现**: CLI parser、runner wrapper、alchemy API 层面补充 legacy seal alias/API absence guardrail
  - **安全边界**: 不恢复旧 alias；不改变 `alchemy-promote` / revert / demote 语义
  - **SoT 对齐**: 明确旧 seal alias/API 保持删除，candidate 进入 settled 只走 `alchemy-promote`
  - **测试**: `tests/test_cli.py` 覆盖 parser choices 与 runner/alchemy symbol absence；残留扫描 `src/ tests/ docs/ README.md` 无旧符号命中
  - **Gates**: `bash scripts/verify.sh` pass（1024 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.6 Elixir Receipt Action ID Collision Guardrail — 完成（commit `35aff81`）**
  - **实现**: 补充 `elixir_revert` / `elixir_demotion` action id collision fallback 防回归测试
  - **安全边界**: 不改变 action id 格式、hash stale validation 或 receipt 存储路径
  - **SoT 对齐**: 明确 elixir lifecycle receipt 使用事件级 `elixir-<op>-<slug>-<epoch_ms>` id，冲突时追加数字后缀
  - **测试**: `tests/test_alchemy.py` 覆盖 revert/demote 同毫秒 receipt 文件已存在时 fallback 到 `-2`
  - **Gates**: `bash scripts/verify.sh` pass（1026 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M2.7 Elixir Superseded Tombstone Status Guardrail — 完成（commit `58a8653`，本地未 push）**
  - **实现**: 补充 promote 后 candidate tombstone `promoted_at` 非空断言，并把 SoT §7.3 中 `superseded` tombstone 从 planned 改为当前已实现
  - **安全边界**: 不改变 promote/revert/demote 写盘行为，不迁移旧 `wiki/elixirs/`，不删除 candidate tombstone
  - **SoT 对齐**: candidate promote 成功后原地墓碑化为 `elixir_state=superseded`、`superseded_by=wiki/elixirs/<id>.md`、`promoted_at=<iso>` 已作为当前事实
  - **测试**: `tests/test_alchemy.py` 精确覆盖 promote 写 settled 与 superseded tombstone frontmatter
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy.AlchemyCandidatePlaneTests.test_promote_writes_settled_and_tombstone` pass；`bash scripts/verify.sh` pass（1043 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.8 Legacy Elixir Migration Preview — 完成（commit `458eb45`，本地未 push）**
  - **实现**: 新增 `preview_legacy_elixir_migration(root, limit=...)` 与 CLI `aiwiki alchemy legacy-migration --dry-run`，只读盘点 legacy settled elixir 的 candidate tombstone 状态
  - **状态分类**: preview 返回 `legacy_missing_tombstone`、`current_tombstone`、`candidate_conflict`、`non_settled` 计数和记录；malformed candidate tombstone 归为 `candidate_conflict`
  - **安全边界**: 不创建 tombstone、不写 execution receipt、不修改或删除 `wiki/elixirs/`；actual migration / cleanup 继续 deferred
  - **SoT 对齐**: `docs/Furnace Evolution Mechanics.md` 记录 legacy migration preview 是当前可用的只读盘点入口
  - **测试**: 覆盖 legacy/current/conflict 盘点、read-only side effects、CLI dispatch 与 nested alchemy parser choices
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneCLITests.test_parser_registers_nested_alchemy_commands tests.test_alchemy.AlchemyCandidatePlaneTests.test_legacy_migration_preview_is_read_only tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1044 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.9 Legacy Elixir Migration Apply Baseline — 完成（commit `9dc86cc`，本地未 push）**
  - **实现**: 新增 `apply_legacy_elixir_migration(root, limit=..., note=...)` 与 CLI `aiwiki alchemy legacy-migration --apply`，只为 preview 中 `migration_required=true` 的 legacy settled elixir 创建缺失 candidate tombstone
  - **写入语义**: candidate tombstone 写入 `elixir_state=superseded`、`superseded_by=wiki/elixirs/<id>.md`、`promoted_at`；settled `wiki/elixirs/*.md` 不修改、不删除
  - **安全边界**: conflict candidate、non-settled wiki elixir 不迁移；不做 superseded cleanup、不自动跑 migration、不提供 revert tombstone 删除
  - **审计**: apply 写 execution receipt + execution receipt history，并通过 M5.9 direct audit append 进入 universal audit stream
  - **SoT 对齐**: 两份 SoT 标明 legacy migration 已有 read-only preview 与显式 apply baseline，superseded cleanup 仍 deferred
  - **测试**: `tests/test_alchemy.py` 覆盖 tombstone 创建、settled no-mutate、conflict skip、receipt/history/audit；`tests/test_cli.py` 覆盖 CLI dispatch
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy.AlchemyCandidatePlaneTests.test_legacy_migration_apply_creates_tombstone_and_receipt tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1057 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.10 Superseded Elixir Cleanup Preview — 完成（commit `fd64c71`，本地未 push）**
  - **实现**: 新增 `preview_superseded_elixir_cleanup(root, limit=...)` 与 CLI `aiwiki alchemy superseded-cleanup --dry-run`
  - **语义边界**: 只读扫描 candidate plane 中的 tombstone 状态，返回 `cleanup_candidate / missing_superseded_target / non_settled_target / candidate_conflict / non_superseded` 计数与记录
  - **安全边界**: 不删除 tombstone、不修改 candidate 或 settled 文件、不改变 revert semantics；deletion apply 继续 deferred
  - **SoT 对齐**: 两份 SoT 标明 legacy superseded cleanup 当前已有 read-only preview，deletion apply 尚未开放
  - **测试**: `tests/test_alchemy.py` 覆盖 cleanup 状态分类与 read-only no-mutate；`tests/test_cli.py` / `tests/test_alchemy_lanes.py` 覆盖 CLI dispatch 与 nested parser choices
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy.AlchemyCandidatePlaneTests.test_superseded_cleanup_preview_is_read_only tests.test_cli.CLITests.test_main_dispatches_command_handlers tests.test_alchemy_lanes.AlchemyLaneCLITests.test_parser_registers_nested_alchemy_commands` pass；`bash scripts/verify.sh` pass（1058 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.1 Elixir Dependency Break Reason Guardrail — 完成（commit `2454956`）**
  - **实现**: `dependency_breaks[].break_reason` 在 collector 与 adapter 层按闭集 `source_demoted / source_reverted` 校验
  - **安全边界**: 不改变 signal kind、planner routing、demote/revert receipt writer 或 schema version
  - **SoT 对齐**: 明确非法 break reason 不得进入 `elixir_dependency_break` signal
  - **测试**: `tests/test_signals_collector.py` 覆盖非法 break reason 被 invalid skip，且不写 signals.jsonl
  - **Gates**: `bash scripts/verify.sh` pass（1027 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M3.2 Planner Inspection CLI Validation Guardrail — 完成（commit `6f188f4`）**
  - **实现**: `planner-log-list` 补齐 invalid `--since` / `--limit` CLI 级失败防回归测试
  - **安全边界**: 不改变 inspection reader/filter 语义，不改变 JSON/text 输出结构
  - **SoT 对齐**: 明确 `signals-list/show` 与 `planner-log-list` 为只读 inspection，`--since`/`--limit` 共享校验边界
  - **测试**: `tests/test_cli.py` 覆盖 `planner-log-list --since not-a-datetime` 与 `--limit 0` 非零退出
  - **Gates**: `bash scripts/verify.sh` pass（1029 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M3.3 Generate-Proposal Reason Order Guardrail — 完成（commit `a111576`）**
  - **实现**: 修正 `runtime_failure` high 的 `generate-proposal` reason order 为 `runtime_failure_observed` → `proposal_recommended`
  - **Schema 边界**: planner-log reason_codes 不再强制字典序排序；改为去重且保留语义顺序，canonical dump 同步保序去重
  - **SoT 对齐**: 明确 `generate-proposal` 先记录 `<kind>_observed`，再记录 `proposal_recommended`
  - **测试**: `tests/test_planner_log.py` 精确断言 reason order；fixture expected planner-log 同步 observed-first
  - **Gates**: `bash scripts/verify.sh` pass（1029 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M3.4 Revert Hash-only Guardrail — 完成（commit `daf854e`）**
  - **实现**: 补充 hash anchors 完整但 promotion receipt `applied_at` 被改坏时仍可 revert 的 guardrail
  - **安全边界**: 不改变 revert 实现；只锁定旧 mtime/promoted_at fallback 已移除后的 hash-only 行为
  - **SoT 对齐**: 明确 `alchemy-revert` clean/stale 判定只依赖 settled/tombstone sha256 anchors
  - **测试**: `tests/test_alchemy.py` 覆盖 receipt applied_at mismatch 不影响 hash-based revert
  - **Gates**: `bash scripts/verify.sh` pass（1030 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M3.5 Removed Settled Alias Parse Guardrail — 完成（commit `b40e3f6`）**
  - **实现**: 补充旧 settled alias 在 argparse 层被拒绝的 parse-level 防回归测试
  - **安全边界**: 不恢复旧 alias；不改变 promote/revert/demote 行为；测试自身不引入旧符号连续字符串残留
  - **残留扫描**: `rg -n "alchemy-seal|alchemy_seal|seal_elixir|run_alchemy_seal" src tests docs README.md` 0 命中
  - **测试**: `tests/test_cli.py` 覆盖旧命令 parse_args 非零退出
  - **Gates**: `bash scripts/verify.sh` pass（1031 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M3.6 L3 Manual Prompt/Policy Proposal Baseline — 完成（commit `80bf77e`，本地未 push）**
  - **实现**: 新增 `src/aiwiki/execution/l3_proposals.py`，支持 `prompt_proposal / policy_proposal` 手工/fixture 创建、只读列队、hash-gated apply 与 receipt-gated revert
  - **CLI**: 新增 `l3-proposal-create`、`review proposals`、`apply <proposal-id>`、`revert <receipt-id>`；runner wrapper 与 `app_compile` lazy compat seam 同步补齐
  - **安全边界**: `apply` 仅允许写 `prompts/*.md` / `schema/policies/*`；`before_hash` mismatch 转 `stale` 且不半写；`revert` 要求 `after_hash` 匹配，否则转 `revert_conflict` 并写 `human_merge_required` hint
  - **Out of scope 固化**: 不自动生成 proposal、不调用 LLM、不接 scheduler、不写 `src/aiwiki/**`、不写 schema core / `schema/protocols/*`、不新增通用 `.aiwiki/state/audit.jsonl`
  - **SoT 对齐**: 两份 SoT 状态说明更新为 L3 manual baseline partial；自动 proposal generation 仍 planned/deferred
  - **测试**: 新增 `tests/test_l3_proposals.py` 覆盖 create/list、target allowlist、stale apply、clean revert、revert conflict；`tests/test_cli.py` 和 `tests/test_execution_compat.py` 补 CLI/compat guardrail
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals tests.test_cli` pass；`bash scripts/verify.sh` pass（1038 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.7 L3 Manual Proposal Reject Workflow — 完成（commit `ba0b96a`，本地未 push）**
  - **实现**: `reject_l3_proposal` owner API + runner wrapper + `app_compile` lazy compat seam；`review proposal <proposal-id> --status rejected` 显式否决 candidate L3 proposal
  - **安全边界**: reject 仅允许 `candidate` 状态；只更新 `.aiwiki/state/l3-proposals.json`、proposal page、runtime history 和 wiki log；不写 target file、不生成 execution receipt
  - **SoT 对齐**: L3 审批流程的 `no -> rejected` 分支从 planned/deferred 收口到 manual baseline；自动 proposal generation 仍 planned
  - **测试**: `tests/test_l3_proposals.py` 覆盖 reject 成功与非 candidate 拒绝；`tests/test_cli.py` 覆盖 CLI dispatch；`tests/test_execution_compat.py` 更新 compat guardrail
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals tests.test_cli tests.test_execution_compat` pass；`bash scripts/verify.sh` pass（1040 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.8 L3 Proposal Shell Review Surfacing — 完成（commit `08bed6e`，本地未 push）**
  - **实现**: `build_shell_summary(...).review_controls.l3_proposals` 暴露 L3 proposal controls；`review_backlog_counts` 新增 `l3_proposals` 与 `l3_proposal_attention`
  - **Surface 字段**: control 包含 `proposal_id / kind / state / target_file / proposal_path / can_reject / can_apply / can_revert / needs_attention / command_hints`
  - **安全边界**: shell 只读 state 并生成 command hints；不执行 apply/reject/revert，不写 target file
  - **SoT 对齐**: L3 proposal 从 CLI-only inspection 收口到 Product Shell review surface；自动 proposal generation 仍 planned
  - **测试**: `tests/test_l3_proposals.py` 覆盖 candidate、accepted、revert_conflict 在 shell summary 中的控制状态和 backlog counts
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals` pass；`bash scripts/verify.sh` pass（1041 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.9 L3 Proposal Receipt Audit Metadata — 完成（commit `207af70`，本地未 push）**
  - **实现**: L3 apply/revert execution receipt 顶层新增 `audit_stream=execution_receipts`、`audit_event=execution_receipt_history_append`、`audit_path=.aiwiki/state/execution-receipts.jsonl`
  - **返回值**: `apply <proposal-id>` 与 `revert <receipt-id>` 返回 payload 暴露 `audit_path`，便于 shell/CLI 调用方追溯
  - **安全边界**: 不新增通用 `.aiwiki/state/audit.jsonl`，不改变 apply/revert hash gate，不改 execution receipt history 全局 schema
  - **SoT 对齐**: L3 manual baseline 的 receipt 可审计性与 lane primitive receipt metadata 对齐；自动 proposal generation 仍 planned
  - **测试**: `tests/test_l3_proposals.py` 覆盖 apply/revert receipt JSON、history append 和 result payload 的 audit metadata
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals` pass；`bash scripts/verify.sh` pass（1041 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.10 L3 Policy Target Layout Guardrail — 完成（commit `b856f77`，本地未 push）**
  - **实现**: `ensure_layout` 与新 vault bootstrap 默认创建 `schema/policies/`，并在 schema index / vault snippet 中显式标注该目录
  - **安全边界**: 不生成默认 policy 文件，不扩大 L3 proposal target allowlist，不改变 `schema/protocols/*` 与 schema core 禁写规则
  - **SoT 对齐**: L3 policy proposal 的唯一 policy 写回目标目录现在有 layout 层保障，避免手工创建目录成为隐式前提
  - **测试**: `tests/test_app.py` 覆盖 layout bootstrap 与 schema index；`tests/test_vault.py` 覆盖 Obsidian folder label
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_app.AiwikiFlowTests.test_ensure_layout_bootstraps_runtime_schema_files tests.test_vault` pass；`bash scripts/verify.sh` pass（1041 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.11 Planner Heavy Lane Reason Order Guardrail — 完成（commit `ef9246c`，本地未 push）**
  - **实现**: `learning_threshold` high/critical 的 planner decision 保持 `enqueue-heavy` 不变，但 `reason_codes` 调整为 `learning_threshold_observed` → `heavy_lane_recommended`
  - **安全边界**: 不改变 planner-log schema，不开启 scheduler / proposal generation / lane apply，不扩大 heavy/light primitive 白名单
  - **SoT 对齐**: 带 `<kind>_observed` 的 planner reason codes 统一先记录原始观测事实，再记录建议动作，避免审计语义倒置
  - **测试**: `tests/test_planner_log.py` 对 learning_threshold heavy lane reason order 使用精确列表断言
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_planner_log` pass（109 tests）；`bash scripts/verify.sh` pass（1041 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.12 L3 Proposal Generation Preview Guardrail — 完成（commit `e407e35`，本地未 push）**
  - **实现**: 新增 `preview_l3_proposal_generation` owner API、runner wrapper 与 CLI `review proposal-generation`，只读列出 planner-log 中 `decision=generate-proposal` 且含 `proposal_recommended` 的 blocked candidates
  - **安全边界**: 固定返回 `automatic_generation_enabled=false` / `side_effects_allowed=false`；不写 `.aiwiki/state/l3-proposals.json`、不写 `output/_proposals/*`、不调用 LLM、不改变 planner-log schema
  - **SoT 对齐**: planner 的 `generate-proposal` decision 现在可被 L3 侧 inspection，但仍不等价于 proposal 文件生成；自动 generation 继续 deferred
  - **测试**: `tests/test_l3_proposals.py` 覆盖 preview payload 与无写盘副作用；`tests/test_cli.py` 覆盖 CLI dispatch；`tests/test_execution_compat.py` 覆盖 lazy compat seam
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals tests.test_cli tests.test_execution_compat` pass（96 tests）；`bash scripts/verify.sh` pass（1043 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.13 Planner-log Rollback Preview — 完成（commit `a01b086`，本地未 push）**
  - **实现**: 新增 `preview_planner_log_rollback(root, signal_id=None, trace_id=None, limit=...)` 与 CLI `aiwiki planner-log-rollback --dry-run`
  - **语义边界**: planner-log 保持 append-only；preview 只返回 future rollback marker 计划，明确 `delete_supported=false / rollback_strategy=append_marker / marker_planned=true`
  - **安全边界**: 不删除、不重写 `.aiwiki/state/planner-log.jsonl`，不写 rollback marker，不写 audit，不改变 planner-log schema
  - **SoT 对齐**: 两份 SoT 标明 planner-log rollback 当前为 read-only marker preview；真实 marker 写入仍 deferred
  - **测试**: `tests/test_planner_log.py` 覆盖 trace 过滤、limit 与 read-only no-mutate；`tests/test_cli.py` 覆盖 CLI dispatch
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_planner_log.TestPlannerLogRollbackPreview tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1051 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.14 Planner-log Rollback Marker Apply — 完成（commit `a313f44`，本地未 push）**
  - **实现**: `apply_planner_log_rollback_marker(root, signal_id=None, trace_id=None, limit=..., apply=False)` 与 CLI `aiwiki planner-log-rollback --dry-run|--apply`
  - **写入语义**: `--dry-run` 只读；`--apply` append 缺失 marker 到 `.aiwiki/state/planner-log-rollback.jsonl`，按稳定 `rollback_marker_id` 幂等跳过已有 marker
  - **安全边界**: 不删除、不重写 `.aiwiki/state/planner-log.jsonl`，不改变 planner-log schema，不自动执行 rollback
  - **SoT 对齐**: 两份 SoT 标明 planner-log rollback 当前为独立 marker stream baseline；planner-log 本体仍 append-only observe-only decision log
  - **测试**: `tests/test_planner_log.py` 覆盖 marker apply、二次幂等、dry-run no-write、planner-log no-mutate；`tests/test_cli.py` 覆盖 CLI dispatch
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_planner_log.TestPlannerLogRollbackPreview tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1052 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M4.1 Generate-Proposal Dry-run Lane Guardrail — 完成（commit `503d083`）**
  - **实现**: 补充 heavy lane 仅遇到 `generate-proposal` planner decision 时不选中任何 signal 的防回归测试
  - **安全边界**: 不改变 dry-run 实现；不启用 proposal generation；不让 heavy/light lane 消费 `generate-proposal`
  - **SoT 对齐**: 明确 `generate-proposal` 只进入 proposal / inspection 路径，不被 heavy/light dry-run lanes 消费
  - **测试**: `tests/test_alchemy_lanes.py` 覆盖 `selected_count=0`、`skipped_count=1`、scope 与 primitive plan 均为空 signal
  - **Gates**: `bash scripts/verify.sh` pass（1032 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M5.6 Non-OK Dry-run Apply Abort Guardrail — 完成（commit `69da1bb`）**
  - **实现**: 补充 `budget_exceeded` preview 下 `run_alchemy_lane_apply` 必须在 action bridge 和 deterministic primitive implementation 前失败的防回归测试
  - **安全边界**: 不改变 apply 实现；不新增 primitive；不启用 deferred `judge/distill/review/propose`
  - **SoT 对齐**: 明确任一 `--apply` 必须先得到 `status=ok` 且 `selected_count>0`，非 `ok` preview 会在写路径前 abort
  - **测试**: `tests/test_alchemy_lanes.py` 覆盖 action batch 和 `compile_wiki` 均 `assert_not_called`
  - **Gates**: `bash scripts/verify.sh` pass（1033 tests / 93% coverage）；qa-review not-required；qa-runtime pass；closed_loop PASS

- **M5.7 Universal Audit Stream Preview — 完成（commit `934ac35`，本地未 push）**
  - **实现**: 新增 `preview_universal_audit_stream(root, limit=...)` 与 CLI `aiwiki audit-preview --dry-run`，只读归一化现有分散审计来源
  - **来源覆盖**: execution receipt history、LLM receipt log、runtime history、protocol-learning aging audit；record 输出稳定 `audit_event_id / source_stream / source_ref / event_type / occurred_at / trace_id / subject / revert_supported`
  - **安全边界**: 不创建 `.aiwiki/state/audit.jsonl`，不改造 existing writer，不修改 source artifact；目标 append-only audit stream 写入继续 deferred
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 当前已有 read-only preview，append-only 写入仍 planned
  - **测试**: `tests/test_audit_preview.py` 覆盖多来源归一化、limit、deterministic id、read-only side effects；`tests/test_cli.py` 覆盖 CLI dispatch
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_audit_preview tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1047 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.8 Universal Audit Stream Append-only Backfill — 完成（commit `4086f23`，本地未 push）**
  - **实现**: 新增 `backfill_universal_audit_stream(root, limit=..., apply=False)` 与 CLI `aiwiki audit-backfill --dry-run|--apply`
  - **写入语义**: `--dry-run` 复用 M5.7 preview 且不写盘；`--apply` 只 append 缺失的 `audit_event_id` 到 `.aiwiki/state/audit.jsonl`，已有 id 幂等跳过
  - **安全边界**: 不自动运行 backfill，不改造 existing source writers，不修改 execution receipts / LLM receipts / runtime history / protocol-learning aging audit
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 当前已有显式 append-only backfill baseline；source writers 直接写 universal audit stream 仍未启用
  - **测试**: `tests/test_audit_preview.py` 覆盖 apply 写入、二次 apply 幂等、dry-run no-write 与 source no-mutate；`tests/test_cli.py` 覆盖 CLI dispatch
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_audit_preview tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1048 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.9 Execution Receipt Direct Audit Append — 完成（commit `1fcc567`，本地未 push）**
  - **实现**: `append_execution_receipt_history(root, receipt)` 写 execution receipt history 后同步 append universal audit record 到 `.aiwiki/state/audit.jsonl`
  - **写入语义**: audit record 复用 M5.7 字段与稳定 id；按 `audit_event_id` 跳过已存在记录；source_ref 指向 execution receipt history 具体行
  - **安全边界**: 不改变 receipt schema，不改变 `.aiwiki/state/execution-receipts.jsonl` 格式；LLM receipts、runtime history、protocol-learning aging audit writer 暂不直接双写
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 已接入 execution receipt writer direct append，其它 source writer 仍由 backfill 覆盖
  - **测试**: `tests/test_app.py` 覆盖 direct audit append、receipt history 仍追加、audit source_ref/event/subject/revert_supported
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_app.AiwikiFlowTests.test_append_execution_receipt_history_writes_universal_audit` pass；`bash scripts/verify.sh` pass（1053 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.10 Runtime History Direct Audit Append — 完成（commit `6d7c14d`，本地未 push）**
  - **实现**: `append_runtime_history(root, event)` 写 runtime history 后同步 append universal audit record 到 `.aiwiki/state/audit.jsonl`
  - **写入语义**: audit record 复用 M5.7 字段与稳定 id；source_ref 指向 runtime history 具体行，重复 event 仍按不同行号生成不同 audit event
  - **安全边界**: 不改变 runtime-history schema，不改变 `.aiwiki/state/runtime-history.jsonl` 写入格式；LLM receipts 与 protocol-learning aging audit writer 暂不直接双写
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 已接入 execution receipt 与 runtime history writer direct append，其它 source writer 仍由 backfill 覆盖
  - **测试**: `tests/test_state_utils.py` 覆盖 direct audit append、source_ref 行号、runtime history no-mutate
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_state_utils.AppStateTests.test_append_runtime_history_writes_universal_audit` pass；`bash scripts/verify.sh` pass（1054 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.11 LLM Receipt Direct Audit Append — 完成（commit `4ac78f1`，本地未 push）**
  - **实现**: `_append_llm_receipt(root, event)` 写 LLM receipt log 后同步 append universal audit record 到 `.aiwiki/state/audit.jsonl`
  - **写入语义**: audit record 复用 M5.7 字段与稳定 id；source_ref 指向 LLM receipt log 具体行，实际写入 payload 的 `created_at` 会进入 audit `occurred_at`
  - **安全边界**: 不改变 LLM receipt event schema，不改变 `.aiwiki/logs/llm-receipts.jsonl` 写入格式，不改变 backend selection / model fallback 语义；protocol-learning aging audit writer 暂不直接双写
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 已接入 execution receipt、runtime history 与 LLM receipt writer direct append，剩余 protocol-learning aging writer 仍由 backfill 覆盖
  - **测试**: `tests/test_runner.py` 覆盖 direct audit append、source_ref 行号、LLM receipt log no-mutate
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_runner.RunnerTests.test_append_llm_receipt_writes_universal_audit` pass；`bash scripts/verify.sh` pass（1055 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.12 Protocol Learning Aging Direct Audit Append — 完成（commit `fe9f0fb`，本地未 push）**
  - **实现**: `age_learnings(root, apply=True, ...)` 写 protocol-learning aging audit JSON 后同步 append universal audit record 到 `.aiwiki/state/audit.jsonl`
  - **写入语义**: audit record 复用 M5.7 字段与稳定 id；由于 aging audit 是覆盖写 JSON snapshot，source_ref 使用 `run_at` fragment 区分多次 run
  - **安全边界**: 不改变 protocol-learning aging result schema、learning page schema 或 lifecycle state transition；不做历史 aging audit backfill
  - **SoT 对齐**: 两份 SoT 标明 universal audit stream 已接入 execution receipt、runtime history、LLM receipt 与 protocol-learning aging writer direct append
  - **测试**: `tests/test_execution.py` 覆盖 direct audit append、source_ref run_at fragment、source audit JSON no-mutate，并确认 runtime history audit 仍独立写入
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_execution.ProtocolLearningsLifecycleTests.test_age_apply_writes_universal_audit` pass；`bash scripts/verify.sh` pass（1056 tests / 93% coverage）；qa-review not-required（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.13 Universal Audit Direct Append / Backfill Dedupe Guardrail — 完成（本地未 commit）**
  - **实现**: 补充 direct audit append 与 `audit-backfill --apply` 的 dedupe parity 防回归测试，冻结同一 source event 的 `audit_event_id` 必须一致
  - **安全边界**: 不改变 `.aiwiki/state/audit.jsonl` schema，不新增 source writer，不自动运行 backfill，不修改 source artifact
  - **SoT 对齐**: 两份 SoT 标明 backfill 对 direct append 已写入的同一 source event 幂等跳过
  - **测试**: `tests/test_audit_preview.py` 覆盖 direct append 后 preview/backfill 复用同一 audit id、backfill `skipped_existing_count=1`、source no-mutate
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_audit_preview.AuditPreviewTests.test_backfill_skips_records_already_written_by_direct_append` pass；`bash scripts/verify.sh` pass（1059 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.14 Heavy/Light Lane Apply Runtime History Audit Events — 完成（本地未 commit）**
  - **实现**: `run_alchemy_lane_apply` 在显式 apply dry-run gate 通过后写 `alchemy-lane-started`，成功完成后写 `alchemy-lane-completed`
  - **审计边界**: lane start/complete 走 runtime-history direct append 进入 universal audit stream；primitive/action receipt 边界保持不变
  - **安全边界**: 不启用 scheduler / execute mode，不扩大 `compile/lint/nightly` primitive 白名单，不执行 LLM-backed `judge/distill/review/propose`
  - **SoT 对齐**: 两份 SoT 标明 heavy/light 显式 apply start/complete audit events 已落地；budget_exceeded 仍只由 dry-run status 表达
  - **测试**: `tests/test_alchemy_lanes.py` 覆盖成功 apply 写 start/complete runtime history + universal audit，以及空请求 / 非 ok preview 等 preflight 失败 no-write
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests.test_apply_writes_lane_runtime_history_audit_events tests.test_alchemy_lanes.AlchemyLaneDryRunTests.test_apply_preflight_failures_do_not_write_lane_runtime_history` pass；`bash scripts/verify.sh` pass（1061 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.15 L3 Accept Revert Audit / Status Reconciliation — 完成（本地未 commit）**
  - **实现**: 补充 L3 clean revert guardrail，确认 receipt-gated revert 同时写 execution receipt history、runtime history 与 universal audit
  - **安全边界**: 不改变 L3 target allowlist，不改变 `after_hash` clean gate / revert conflict 行为，不启用 automatic proposal generation
  - **SoT 对齐**: §12.2 不再把 L3 accept revert 标为 planned；Agent Architecture 标明 clean revert 写 runtime-history / universal audit
  - **测试**: `tests/test_l3_proposals.py` 覆盖 clean revert runtime history event、execution receipt audit records、runtime-history audit records
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals.L3ProposalTests.test_apply_and_clean_revert_write_receipts_and_audit_metadata` pass；`bash scripts/verify.sh` pass（1061 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.11 Elixir Promotion Revert Audit / Status Reconciliation — 完成（本地未 commit）**
  - **实现**: 补充 elixir revert receipt guardrail，确认 promotion revert 的 `elixir_revert` execution receipt 会进入 universal audit
  - **安全边界**: 不改变 promotion receipt hash anchors，不改变 tombstone restore / settled deletion order，不新增 superseded cleanup deletion apply
  - **SoT 对齐**: §12.2 不再把 elixir promotion revert 标为 planned；Agent Architecture 标明 promotion revert 已按 receipt/hash gate 回到 candidate 并写 universal audit
  - **测试**: `tests/test_alchemy.py` 覆盖 revert receipt 的 source receipt metadata 与 universal audit record
  - **Gates**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy.AlchemyCandidatePlaneTests.test_revert_writes_receipt_with_source_receipt_applied_at` pass；`bash scripts/verify.sh` pass（1061 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.15 Universal Audit Stream Status Reconciliation — 完成（本地未 commit）**
  - **实现**: SoT 状态对齐；`universal audit stream` 在当前 documented source set（execution receipts / runtime history / LLM receipts / protocol-learning aging）下标为 implemented
  - **安全边界**: 不改 audit schema，不新增 source writer，不启用 scheduler / automatic backfill
  - **SoT 对齐**: Agent Architecture 表格从 partial 改为 implemented；Evolution Mechanics 顶部状态说明去掉 audit stream partial 语义
  - **测试**: 本轮为文档状态对齐，无 runtime 代码修改
  - **Gates**: `bash scripts/verify.sh` pass（1061 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.12 L2 Learning Activation Revert Baseline — 完成（本地未 commit）**
  - **实现**: `protocol-learn-verify` 对 `stale -> active` 写 activation metadata；新增 `protocol-learn-revert-activate` 显式回滚最近一次可支持 activation 到 `stale`
  - **安全边界**: 只支持本地显式命令；不启用 automatic proposal generation、scheduler execute mode、heavy/light 自动调度或 superseded cleanup deletion apply
  - **SoT 对齐**: 两份 SoT 标明 L2 activation revert baseline 已落地，且自动化 stop-line 项仍未完成
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_execution.ProtocolLearningsLifecycleTests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass
  - **Gates**: `bash scripts/verify.sh` pass（1064 tests / 93% coverage）；qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M2.13 Elixir Superseded Cleanup Deletion Apply — 完成（本地未 commit）**
  - **实现**: `alchemy superseded-cleanup --dry-run` 标明支持清理的 tombstone；新增 `--apply` 只删除仍指向现存 settled elixir 的 superseded candidate tombstone，并写 execution receipt / universal audit
  - **安全边界**: 不修改 `wiki/elixirs/` settled source；不删除 conflict、missing-target、non-settled-target 或 non-superseded tombstone；不启用 scheduler / automatic generation
  - **SoT 对齐**: 两份 SoT 标明 superseded cleanup deletion apply baseline 已落地，剩余自动化项仍未完成
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy.AlchemyCandidatePlaneTests.test_superseded_cleanup_preview_is_read_only tests.test_alchemy.AlchemyCandidatePlaneTests.test_superseded_cleanup_apply_deletes_supported_tombstones_and_writes_receipt tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1065 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M1.6 Signal Planner Execute-mode Decision Log — 完成（本地未 commit）**
  - **实现**: 新增 `planner-log-replay --execute`，写 `mode=execute` planner decisions；默认仍为 observe-only；execute/observe 用独立 dedupe identity
  - **安全边界**: execute-mode planner replay 只追加 planner-log，不直接运行 lane/apply/proposal；`ignore` / `escalate-human` 保持 `side_effects_allowed=false`
  - **SoT 对齐**: 两份 SoT 标明 planner execute-mode decision log 已落地，scheduler consumption / automatic generation 仍未完成
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_planner_log.TestGenerateProposalRouting tests.test_planner_log.TestCLI tests.test_planner_log.TestPublicContracts tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1070 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.16 Heavy/Light Alchemy Auto Scheduler Entry — 完成（本地未 commit）**
  - **实现**: 新增 `alchemy auto --dry-run|--apply`，只消费 `mode=execute` planner-log decisions，并只调度已有 apply-supported deterministic primitives
  - **安全边界**: 不消费 observe-only decisions；不启用 `judge/distill/review/propose`；不选择或调用 LLM backend；apply 写 `alchemy-auto-scheduler` runtime-history / universal audit
  - **SoT 对齐**: 两份 SoT 标明 heavy/light 自动执行调度入口 baseline 已落地，L3 automatic generation 仍未完成
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1073 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M3.16 L3 Proposal Automatic Generation Baseline — 完成（本地未 commit）**
  - **实现**: 新增 `l3-proposal-generate --dry-run|--apply`，只消费 `mode=execute` 且含 `proposal_recommended` 的 `generate-proposal` planner-log records，deterministic 创建 prompt proposal 候选
  - **安全边界**: observe-only records 只标为 blocked；生成只写 `output/_proposals/prompt/` 与 `.aiwiki/state/l3-proposals.json`，不写目标文件、不调用 LLM、不自动 accept
  - **SoT 对齐**: 两份 SoT 从 blocked preview / deferred 口径收敛为 execute-mode automatic candidate generation baseline；LLM-backed 内容生成与 auto-accept 仍不在默认可用边界
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_l3_proposals.L3ProposalTests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass；`bash scripts/verify.sh` pass（1075 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.17 Furnace SoT Remaining Deferred Status Reconciliation — 完成（commit `78bc7cf`，本地未 push）**
  - **实现**: 收敛两份 SoT 与 CLI help 的剩余 stale 状态文案，明确 deterministic `alchemy auto` / `l3-proposal-generate` 已承接 execute-mode scheduler/proposal baseline
  - **安全边界**: 不改变 runtime 行为；不让 heavy/light lane 消费 `generate-proposal`；不启用 LLM-backed `judge/distill/review/propose`；不自动 accept L3 proposal
  - **SoT 对齐**: 把剩余 deferred 明确限定为 high-risk lane primitives，需要独立 scoped dry-run / receipt / audit / revert 或不可回滚声明
  - **测试**: focused stale phrase scan pass；`bash scripts/verify.sh` pass（1075 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.18 Scoped Judge Primitive Dry-run Preview — 完成（commit `a97ed33`，本地未 push）**
  - **实现**: 新增 `preview_judge_primitive(...)` / runner wrapper / CLI `aiwiki alchemy judge <scope> --dry-run`，复用 heavy lane planner/signal scope selection，只读产出 judgment refresh candidate preview
  - **安全边界**: 不调用 LLM，不写 judgment/decision、receipt、audit、runtime history、proposal 或 elixir；`judge` 仍不在 lane `--apply --primitive` 白名单中
  - **SoT 对齐**: 两份 SoT 标明 `judge` 仅有 scoped dry-run preview；`judge` apply 与 `distill/review/propose` 仍需独立 receipt/audit/revert 或不可回滚声明
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（31 tests）；`bash scripts/verify.sh` pass（1078 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.19 Scoped Distill Primitive Dry-run Preview — 完成（commit `0ef9b15`，本地未 push）**
  - **实现**: 新增 `preview_distill_primitive(...)` / runner wrapper / CLI `aiwiki alchemy distill <scope> --dry-run`，复用 heavy lane planner/signal scope selection，只读产出 elixir refresh candidate preview
  - **安全边界**: 不调用 LLM，不写 elixir candidate / settled elixir、receipt、audit、runtime history、proposal、judgment 或 decision；`distill` 仍不在 lane `--apply --primitive` 白名单中
  - **SoT 对齐**: 两份 SoT 标明 `distill` 仅有 scoped dry-run preview；`judge/distill` apply 与 `review/propose` 仍需独立 receipt/audit/revert 或不可回滚声明
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（34 tests）；`bash scripts/verify.sh` pass（1081 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.20 Scoped Review Primitive Dry-run Preview — 完成（commit `9f48ce8`，本地未 push）**
  - **实现**: 新增 `preview_review_primitive(...)` / runner wrapper / CLI `aiwiki alchemy review <scope> --dry-run`，复用 heavy lane planner/signal scope selection，只读产出 review enqueue candidate preview
  - **安全边界**: 不调用 LLM，不写 review queue、receipt、audit、runtime history、proposal、judgment、decision 或 elixir；`review` 仍不在 lane `--apply --primitive` 白名单中
  - **SoT 对齐**: 两份 SoT 标明 `review` 仅有 scoped dry-run preview；`judge/distill/review` apply 与 `propose` 仍需独立 receipt/audit/revert 或不可回滚声明
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（37 tests）；`bash scripts/verify.sh` pass（1084 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.21 Scoped Propose Primitive Dry-run Preview — 完成（commit `6b1403e`，本地未 push）**
  - **实现**: 新增 `preview_propose_primitive(...)` / runner wrapper / CLI `aiwiki alchemy propose <scope> --dry-run`，复用 heavy lane planner/signal scope selection，只读产出 proposal opportunity preview
  - **安全边界**: 不调用 LLM，不写 proposal plane、receipt、audit、runtime history、review queue、judgment、decision 或 elixir；`propose` 仍不在 lane `--apply --primitive` 白名单中；不消费 `generate-proposal` decisions
  - **SoT 对齐**: 两份 SoT 标明 `propose` 仅有 scoped dry-run preview；`judge/distill/review/propose` apply 仍需独立 receipt/audit/revert 或不可回滚声明
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（39 tests）；`bash scripts/verify.sh` pass（1086 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.22 Deferred Lane Apply Contract Metadata — 完成（commit `a004d9a`，本地未 push）**
  - **实现**: `judge/distill/review/propose` scoped preview 与 lane `deferred_primitives` 暴露 deferred `apply_contract` metadata，覆盖 write surfaces、receipt schema、audit schema、revert policy、idempotency key 与 backend policy
  - **安全边界**: 不启用 lane apply，不扩大 `compile/lint/nightly` primitive 白名单，不调用 LLM，不写 judgment/decision、elixir candidate、review queue、proposal plane、receipt、runtime history 或 audit
  - **SoT 对齐**: 两份 SoT 标明四个高风险 primitive 已有 deferred apply contract metadata，但必须等 contract 进入 executable 状态后才能加入 lane apply
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（39 tests）；`bash scripts/verify.sh` pass（1086 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.23 Scoped Review Enqueue Apply Baseline — 完成（commit `7aafd53`，本地未 push）**
  - **实现**: 新增直接 `aiwiki alchemy review <scope> --apply` baseline，只写 review queue managed section，并写 execution receipt / runtime history / universal audit
  - **安全边界**: 不加入 heavy/light lane `--primitive` 白名单，不启用 `alchemy auto` review 调度，不调用 LLM，不写 judgment/decision、elixir candidate 或 proposal plane
  - **SoT 对齐**: 两份 SoT 已从 `review` deferred metadata 更新为 direct scoped apply executable；`judge/distill/propose` 仍保持 deferred
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（41 tests）；`bash scripts/verify.sh` pass（1088 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.24 Explicit Heavy Lane Review Primitive Apply — 完成（commit `509f9b8`，本地未 push）**
  - **实现**: 把已 receipt 化的 direct `review` apply 接入显式 heavy lane `--apply --primitive review`
  - **安全边界**: 不接入 light lane；不让 `alchemy auto` 选择或执行 `review`；不调用 LLM；不启用 `judge/distill/propose`
  - **SoT 对齐**: 两份 SoT 已更新为 `review` 支持 direct scoped apply 与 explicit heavy lane primitive apply，但自动调度仍 deferred
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（43 tests）；`bash scripts/verify.sh` pass（1090 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.25 Explicit Auto Review Primitive Opt-in — 完成（commit `8025a3d`，本地未 push）**
  - **实现**: 允许 `alchemy auto --lane heavy --primitive review` 显式 opt-in 调度 review，默认 auto 仍不选择 `review`
  - **安全边界**: 不接入 light lane；不启用默认 auto review；不调用 LLM；不启用 `judge/distill/propose`
  - **SoT 对齐**: 两份 SoT 已更新为 `review` 支持 explicit auto opt-in，但默认调度仍 deterministic-only
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（45 tests）；`bash scripts/verify.sh` pass（1092 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.26 Scoped Propose Apply Baseline — 完成（commit `1f580f8`，本地未 push）**
  - **实现**: 新增 direct `aiwiki alchemy propose <scope> --apply`，从 scoped dirty preview deterministic 生成 L3 prompt proposal 候选，并写 execution receipt / runtime history / universal audit
  - **安全边界**: 不写 `prompts/*` 或 `schema/policies/*` 目标文件；不自动 accept proposal；不接入 heavy/light lane `--primitive propose`；不接入 `alchemy auto`；不调用 LLM；不启用 `judge/distill`
  - **SoT 对齐**: 两份 SoT 已更新为 `propose` 支持 direct scoped proposal-plane apply baseline，但 lane/auto 仍 deferred
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（47 tests）；`bash scripts/verify.sh` pass（1094 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.27 Explicit Heavy Lane Propose Primitive Apply — 完成（commit `61f6900`，本地未 push）**
  - **实现**: 把已 receipt 化的 direct `propose` apply 接入显式 heavy lane `--apply --primitive propose`
  - **安全边界**: 不接入 light lane；不接入默认或显式 auto propose；不调用 LLM；不写 prompt/policy 目标文件；不启用 `judge/distill`
  - **SoT 对齐**: 两份 SoT 已更新为 `propose` 支持 explicit heavy lane primitive apply，但 auto 仍 deferred
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（50 tests）；`bash scripts/verify.sh` pass（1097 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.28 Explicit Auto Propose Primitive Opt-in — 完成（commit `10d245e`，本地未 push）**
  - **实现**: 允许 `alchemy auto --lane heavy --primitive propose` 显式 opt-in 调度 propose，默认 auto 仍不选择 `propose`
  - **安全边界**: 不接入 light lane；不启用默认 auto propose；不调用 LLM；不写 prompt/policy 目标文件；不启用 `judge/distill`
  - **SoT 对齐**: 两份 SoT 已更新为 `propose` 支持 explicit auto opt-in，但默认调度仍 deterministic-only
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（52 tests）；`bash scripts/verify.sh` pass（1099 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.29 Scoped Distill Apply Baseline — 完成（commit `2769aca`，本地未 push）**
  - **实现**: 新增 direct `aiwiki alchemy distill <scope> --apply`，只刷新 scoped preview 中已有 `elixir_refs` 对应的 candidate plane 文件，并写 execution receipt / runtime history / universal audit
  - **安全边界**: 不创建 scope-only 新 elixir；不 finalize/promote；不写 `wiki/elixirs/`；不接入 heavy/light lane `--primitive distill`；不接入 `alchemy auto`；不调用 LLM；不启用 `judge`
  - **幂等**: apply 使用 deterministic scoped refresh question；同一 candidate 已有相同 distill history 时跳过，并仍写 receipt 记录 skipped reason
  - **SoT 对齐**: 两份 SoT 已更新为 `distill` 支持 direct scoped candidate-refresh apply baseline，但 lane/auto 仍 deferred
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（54 tests）；`bash scripts/verify.sh` pass（1101 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.30 Explicit Heavy Lane Distill Primitive Apply — 完成（commit `6388122`，本地未 push）**
  - **实现**: 把已 receipt 化的 direct `distill` apply 接入显式 heavy lane `--apply --primitive distill`
  - **安全边界**: 不接入 light lane；不接入默认或显式 auto distill；不调用 LLM；不创建 scope-only 新 elixir；不 finalize/promote；不写 `wiki/elixirs/`；不启用 `judge`
  - **SoT 对齐**: 两份 SoT 已更新为 `distill` 支持 explicit heavy lane primitive apply，但 auto 仍不调度 distill
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（55 tests）；`bash scripts/verify.sh` pass（1102 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.31 Explicit Auto Distill Primitive Opt-in — 完成（commit `fe68a25`，本地未 push）**
  - **实现**: 允许 `alchemy auto --lane heavy --primitive distill` 显式 opt-in 调度 distill，默认 auto 仍不选择 `distill`
  - **安全边界**: 不接入 light lane；不启用默认 auto distill；不调用 LLM；不创建 scope-only 新 elixir；不 finalize/promote；不写 `wiki/elixirs/`；不启用 `judge`
  - **SoT 对齐**: 两份 SoT 已更新为 `distill` 支持 explicit auto opt-in，但默认调度仍 deterministic-only
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（58 tests）；`bash scripts/verify.sh` pass（1105 tests / 93% coverage）
  - **Gates**: qa-review pass（same-context fallback）；qa-runtime pass；closed_loop PASS

- **M5.32 Scoped Judge Apply Baseline — 完成（commit `c140ed1`，本地未 push）**
  - **实现**: 新增 direct `aiwiki alchemy judge <scope> --apply`，只给 scoped preview 中已有 `judgment_refs` / `decision_refs` 对应页面写 deterministic managed refresh marker，并写 execution receipt / runtime history / universal audit
  - **安全边界**: 不生成或改写 judgment 结论；不改变 status/confidence/review lifecycle；不创建 scope-only judgment/decision 页面；不接入 heavy/light lane `--primitive judge`；不接入 `alchemy auto`；不调用 LLM/backend
  - **幂等**: marker section 使用稳定候选/trace/source/concept 摘要；重复 apply 在 marker 未变化时不改目标页，并仍通过 receipt 记录 refreshed/skipped 结果
  - **SoT 对齐**: 两份 SoT 已更新为 `judge` 支持 direct scoped refresh-marker apply baseline；semantic judge refresh、lane judge 与 auto judge 仍需显式 LLM/human contract
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（60 tests）；`bash scripts/verify.sh` pass（1107 tests / 93% coverage）
  - **Gates**: qa-review not-required（calibration downgrade：14 consecutive zero-hit rounds）；qa-runtime pass；closed_loop PASS

- **M5.33 Semantic Judge Proposal Preview — 完成（commit `c31aac7`，本地未 push）**
  - **实现**: 新增 direct `aiwiki alchemy judge <scope> --propose`，只给 scoped preview 中已有 `judgment_refs` / `decision_refs` 对应页面生成 `output/_proposals/judge/` semantic refresh proposal-preview artifact，并写 execution receipt / runtime history / universal audit
  - **安全边界**: 不生成语义判断内容；不修改 judgment/decision target page；不改变 status/confidence/review lifecycle；不创建 scope-only judgment/decision 页面；不接入 heavy/light lane `--primitive judge`；不接入 `alchemy auto`；不调用 LLM/backend
  - **Proposal metadata**: artifact 记录 target path、before hash、candidate/signal/trace provenance、`llm_invoked=false`、`semantic_content_generated=false` 与 human/model accepted-proposal requirement
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（62 tests）；`bash scripts/verify.sh` pass（1109 tests / 93% coverage）
  - **Gates**: qa-review not-required（calibration note）；qa-runtime pass；closed_loop PASS

- **M5.34 Accepted Judge Proposal Apply — 完成（commit `a4c2448`，本地未 push）**
  - **实现**: 新增 `aiwiki alchemy judge-proposal <proposal> --apply`，只应用 `kind=alchemy-judge-proposal`、`state=accepted`、target `before_hash` 匹配且包含 explicit accepted refresh block 的 proposal
  - **安全边界**: 不生成语义判断内容；不调用 LLM/backend；target stale、缺 accepted block、非 accepted state 都在 target write 前失败；不改变 status/confidence/review lifecycle frontmatter；不创建 scope-only judgment/decision 页面；不接入 heavy/light lane `--primitive judge` 或 `alchemy auto`
  - **写入语义**: 只把 proposal accepted block 写入 target managed section，并在成功后把 proposal artifact 标记为 `state=applied`，同时写 execution receipt / runtime history / universal audit
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_alchemy_lanes.AlchemyLaneDryRunTests tests.test_alchemy_lanes.AlchemyLaneCLITests tests.test_cli.CLITests.test_main_dispatches_command_handlers` pass（66 tests）；`bash scripts/verify.sh` pass（1113 tests / 93% coverage）
  - **Gates**: qa-review not-required（calibration note）；qa-runtime pass；closed_loop PASS

- **M-PS.1 Batch A5 Advanced 抽屉折叠 — 完成（本地未 push）**
  - **实现**: Furnace Center 首屏保持 AskBox → Today's Reports / Previous Reports → DropZone → collapsed Advanced；Advanced `<details>` 内收纳 System Status / LLM Health / Review/Execution shortcuts / Recent Runs / Refresh / Compile / Nightly / Protocol 等原 dashboard 运维项
  - **安全边界**: 不删除任何旧 view / command / ribbon；不修改 `VIEW_TYPE_*` 字符串；不修改 `showAdvancedCommands` settings 语义；不扩 `ShellSummary`
  - **测试**: `bash .obsidian/plugins/furnace-product-shell/build.sh` pass；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass；`bash scripts/verify.sh` pass（1146 tests / 93% coverage）

- **M-PS.1 Batch B1 settings webhook 字段 — 完成（本地未 push）**
  - **实现**: Product Shell settings defaults 新增 `feishuWebhookUrl` / `wecomWebhookUrl` / `enabledChannels`；setting tab 新增 Notifications (webhook) 区块，包含 2 个 URL 输入和 Feishu/WeCom 2 个 channel toggle
  - **迁移**: `loadPluginState()` 兼容 camelCase / snake_case webhook 字段与 `enabled_channels`，并将 `enabledChannels` 过滤为 `feishu` / `wecom` 子集；A4 的 `lastViewedTimestamp` 迁移保持
  - **安全边界**: 纯 settings 数据层；不改 `execLauncher()` env bridge；不调用 webhook；不修改 Python runtime、ShellSummary、receipts 或 audit schema
  - **测试**: `bash .obsidian/plugins/furnace-product-shell/build.sh` pass；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass；`bash scripts/verify.sh` pass（1146 tests / 93% coverage）

- **M-PS.1 Product Shell + Notifier — 完成（Phase A + Phase B，全量收口，本地未 push）**
  - **实现**: A1-A6 已完成 AskBox / Today's Reports / DropZone / Advanced 抽屉与主题 polish；B1-B4 已完成 settings、env bridge、Python notifier 与 `run-ask` report hook；B5 新增 `tests/test_notify.py` 覆盖 notifier 7 个 contract case
  - **通知边界**: 飞书 / 企业微信 webhook 只由 env bridge 注入 runtime；成功 POST 不写 audit；失败仅写 `notify_failed` 到 `.aiwiki/state/audit.jsonl`，不向调用方 raise，不泄漏 webhook URL/token
  - **安全边界**: 不扩 `ShellSummary`；不修改 receipts / runner / shell-status schema；不引入第三方依赖；不真实发送 webhook；不 push
  - **测试**: focused `PYTHONPATH=src python3 -m unittest tests.test_notify -v` pass（7 tests）；`bash scripts/verify.sh` pass（1153 tests / 93% coverage）

- **M-E.1 B2 Extract interfaces / clients / receipts — 完成（本地未 commit）**
  - **实现**: 新增 `src/aiwiki/runner/interfaces.py`（`SupportsComplete`）、`clients.py`（LLM status/probe/client/model fallback helpers）、`receipts.py`（run log / LLM receipt / audit helpers）；`runner/__init__.py` 改为绝对 import re-export 并保持现有调用名
  - **兼容边界**: `SupportsComplete` 与 `_fallback_to_next_model(client, operation, exc)` 签名未变；LLM receipt/audit/run-log schema 字段集合未变；子模块不 import parent `aiwiki.runner`
  - **测试调整**: 仅 4 个 monkeypatch target 从 `aiwiki.runner.*` 调整为 owner module `aiwiki.runner.clients.*`
  - **指标**: `runner/__init__.py` 4883 → 4631 LOC；`interfaces.py` 12 LOC / `clients.py` 102 LOC / `receipts.py` 195 LOC
  - **Gates**: smoke import pass；focused B2 tests pass；`tests.test_runner` pass；`bash scripts/verify.sh` pass（1160 tests / 93% coverage）

- **M-E.1 B7 Final runner façade — 完成（本地未 commit）**
  - **实现**: `alchemy.py` 承接 lane dry-run/apply、auto scheduler 与 lane/auto helper；新增 `automation.py` 承接 `auto_process_once` / `watch_inbox` / `inbox_snapshot` / automation state helpers；`runner/__init__.py` 收敛为 import-only compatibility façade
  - **兼容边界**: public `from aiwiki.runner import ...` 继续可用；`SupportsComplete` / `_fallback_to_next_model` / `advance_client_model` 签名未变；receipt/audit/shell-summary/runner JSON schema 字段未改；子模块不 import parent `aiwiki.runner`
  - **测试调整**: B7 单批 7 个 monkeypatch target 从 façade 调整到 owner module `aiwiki.runner.alchemy.*`
  - **指标**: `runner/__init__.py` 915 → 151 LOC；新增 `automation.py` 180 LOC；runner package 总 LOC 4581
  - **Gates**: import boundary smoke pass；focused `tests.test_alchemy_lanes tests.test_app tests.test_runner` pass；`bash scripts/verify.sh` pass（1160 tests / 93% coverage）

- **M-C.1 NVIDIA NIM hardcoded fallback chain 移除 — 完成（commit `e169338`，本地未 push）**
  - **实现**: 删除 `DEFAULT_NVIDIA_NIM_FALLBACK_MODEL` / `DEFAULT_NVIDIA_NIM_LAST_RESORT_MODEL` / `DEFAULT_NVIDIA_NIM_MODEL_CHAIN`；新增 `--model-fallback`（repeatable + 逗号分隔）CLI flag 与 `AIWIKI_MODEL_FALLBACK` env，CLI 优先 env；`_default_model_chain` 不再隐式扩展 NVIDIA backend；`advance_client_model` 单项 chain 直接 False
  - **不变量加固**: 显式 backend 不变量延伸到显式 model fallback；fallback chain 只来自 `LLMConfig.model_fallback_chain`；effective chain = `(model, *fallback)` 去重保序
  - **README**: 替换「过渡行为」段为 `--model-fallback` 显式用法
  - **测试**: 新增 `tests/test_config.py` / `tests/test_cli.py` / `tests/test_llm.py` fallback 覆盖；`bash scripts/verify.sh` pass（1160 tests / 93% coverage）

- **M-E.1 runner.py 7 批拆分 — 完成（本地未 push，B1-B7 共 7 commits）**
  - **目标**: 把 4883 行的 `src/aiwiki/runner.py` 拆成 runner package；`runner/__init__.py` 收敛为 ≤ 300 LOC 的 import-only compatibility façade
  - **批次**:
    - B1 `2762bbb` package conversion（`git mv runner.py runner/__init__.py`，86 个 `from .xxx` → `from aiwiki.xxx`，4883 LOC）
    - B2 `2792b1b` 抽出 `interfaces.py` (12) / `clients.py` (102) / `receipts.py` (195)，4883→4631
    - B3 `c8006cf` 抽出 `prompts.py` (866)，4631→3824
    - B4 `b933cf3` 新增 `commands.py` (256) + `alchemy.py` lifecycle (81)，3824→3537
    - B5 `41b72c3` 抽出 `workflows.py` (1139)，3537→2480
    - B6 `cfafa9e` `alchemy.py` 扩展 scoped primitives，2480→915（`alchemy.py` 81→1682）
    - B7 `fa05054` `alchemy.py` 扩展 lane/auto + 新增 `automation.py` (180) + 收口 façade，915→151（`alchemy.py` 1682→2260）
  - **不变量**: receipt/audit/shell-summary/runner JSON schema 字段全程不动；`SupportsComplete` / `_fallback_to_next_model` / `advance_client_model` 签名不动；子模块全部 sibling 绝对导入，禁止 `from aiwiki.runner import ...`；外部 `from aiwiki.runner import ...` 继续可用
  - **最终结构**: `__init__.py` 151 + `interfaces.py` 12 + `clients.py` 102 + `receipts.py` 195 + `prompts.py` 866 + `commands.py` 256 + `alchemy.py` 2260 + `workflows.py` 1139 + `automation.py` 180 = 5161 LOC（runner package 总）
  - **测试 patch 调整累计**: B2 4 + B3 2 + B4 0 + B5 21 + B6 0 + B7 7 = 34 处，全部指向 owner module
  - **Gates**: 全程 `bash scripts/verify.sh` pass（1160 tests / 93% coverage 不变）；7 批未触发任何 Stop Condition；contract 已归档到 `.codex/contracts/archive/M-E.1-runner-decomposition.md`

- **M-PS.2 Today Output Surface Reconciliation — 完成（commit `a666439`，本地未 push）**
  - **实现**: 在 Furnace Product Shell 首屏 AskBox 与 Today's Reports 之间新增 `Needs your decision` 顶区段；`renderNeedsDecisionSection` 只读消费 `suggested_next_actions` / `drift_warnings` / `rewrite_recovery_actions` / `review_backlog_counts`；全空整段不渲染；最多 5 个可见项 + `+N more in Advanced` overflow hint
  - **安全边界**: 不改 `src/aiwiki/**`；不扩 `ShellSummary` schema；不改 runtime / receipts / audit / shell-summary writer；不新增 webhook / Notice / Badge；不引入第三方 npm 依赖；首屏新增 LOC 中 `L3 / lane / receipt / audit / proposal / candidate / planner / signal` 术语 0 命中；Advanced 抽屉零删除
  - **指标**: `render.js` 1792 → 1871；`styles.css` 790 → 817；build pass；`node --check main.js` pass；`bash scripts/verify.sh` pass（1160 tests / 93% coverage 不变）
  - **Gates**: 术语扫描 0 命中；7 项 Stop Line 全部未触发；contract 已归档到 `.codex/contracts/archive/M-PS.2-needs-your-decision.md`

- **M6.1 Deterministic Loop Acceptance Pack — 完成（5 commits 本地未 push）**
  - **目的**: 在不依赖 LLM / 网络 / 真实 vault 的前提下，把 `signals-replay → planner-log-replay --execute → alchemy auto --dry-run → explicit deterministic primitive apply → receipt/audit byte-level backchain → today/shell-summary read-only` 整链路冻结为 hermetic byte-level acceptance
  - **B1 (`232e964`)**: execute-mode dry-run acceptance；新增 `tests/test_acceptance_loop.py` + `case_auto_dry_run/`；contract 例外条款授权新增 `src/aiwiki/clock.py` 单一集中 UTC clock helper（9 LOC）+ `signals/collector.py:336` + `planner/log_writer.py:68` 各 1 处替换为 `clock.utc_now()`，零行为变化；测试通过 monkeypatch `aiwiki.clock.utc_now` 实现固定时钟；539 insertions / 3 deletions
  - **B2a (`a067005`)**: light primitive (compile+lint) receipt/audit acceptance；audit envelope 实际为 `alchemy-lane-started → alchemy-lane-primitive(light:all:compile) → alchemy-lane-primitive(light:all:lint) → alchemy-lane-completed`；532 insertions / 10 deletions
  - **B2b (`da5cfc8`)**: light primitive (nightly) receipt/audit acceptance + B2a/B2b 合并等价断言；nightly 比 compile/lint 多一层自有 audit 事件，envelope 为 `alchemy-lane-started → nightly → alchemy-lane-primitive(light:all:nightly) → alchemy-lane-completed`；502 insertions / 7 deletions
  - **B3 (`f86cbd2`)**: heavy primitive (review/distill/propose) receipt/audit acceptance；heavy primitives 与 light 设计差异：每个 primitive 有独立 `generated_by` / `operation`（`aiwiki-alchemy-review` / `alchemy-review-enqueue` 等），不统一为 `aiwiki-alchemy-lane`；audit envelope 9 事件包含 `l3-proposal-create` 入队事件（不是 L3 auto-accept；`l3-proposal-apply` / `l3-proposal-accept` 0 命中）；prompt 目标 byte-identical 已确认；580 insertions
  - **B4 (`a183fcd`)**: replay idempotency + `today` read-only presentation acceptance + `scripts/run_acceptance.sh` 一键入口；二次 replay/planner/auto/today 全 byte-equal；`today` 不 mutate `output/control/shell-summary.json` 或任何 state；69 个文件 1714 insertions（脚本 4 + test 62 + golden + seed schema/index 副本）
  - **安全边界**: 严守 contract Stop Lines；除 B1 例外条款授权的 3 处 src 修改外，0 处 src 改动；无 LLM、无网络；无 lane judge / auto judge / runtime semantic judgment / L3 auto-accept / hidden backend；无 schema/receipt/audit 字段变更
  - **指标**: 1160 tests baseline 不变 / 93% coverage 不变 / 5 acceptance tests 全部 pass / `bash scripts/run_acceptance.sh -v` pass / `bash scripts/verify.sh` pass
  - **Gates**: contract 期间 3 次 invariant 修正（B2b nightly 多 1 层 audit / B3 heavy per-primitive 字段 / B4 commit 收口）；contract 已归档到 `.codex/contracts/archive/M6.1-deterministic-loop-acceptance.md`

- **M6.1b LLM Golden Loop — 完成（4 commits 本地未 push）**
  - **目的**: 用 Hybrid Record-Replay 把 LLM-backed 黄金路径（`run-ask`）与 LLM-origin artifact 下游 deterministic primitive 行为冻结为 hermetic byte-level acceptance；不依赖真实 LLM / 网络，但 prompt_hash 严格校验、Stop Lines guardrail 0 命中
  - **B1 (`9d4ceba`)**: 测试专用 `tests/acceptance/llm_replay.py`（109 LOC, `compute_prompt_hash` / `ReplayBackend` / `RecordingBackend` / `inject_{replay,recording}_client`，不进生产 registry）+ `tests/test_llm_replay_harness.py` 11 单元测试；canonical backend = `codex-cli`；同时 patch `runner.clients.create_client` + `runner.workflows.create_client`；为 ReplayBackend 注入 `LLMConfig` metadata；0 src diff
  - **B2 (`ef83ea2`)**: `case_happy_run_ask` canonical run-ask replay；`_copy_case_and_fix_clock_from(group, ...)` helper；调试中定位并消除 `aiwiki.render.paths.utc_now` 漏 monkeypatch（影响 `wiki/indexes/log.md` query log timestamp 进 prompt），删除 `allow_prompt_drift` 字段与代码分支，prompt_hash 严格校验恢复；receipt / runs log / audit byte-frozen，shell-summary mtime jitter 走 schema-only
  - **B3 (`0b29440`)**: `case_heavy_after_llm` invariant boundary 检查；上游 `wiki/derived/source-b3.md` frontmatter 标 `llm_invoked=true` + backend/model/response_id/prompt_hash provenance；下游 heavy review/distill/propose deterministic primitive 跑出与 M6.1 B3 byte-equal 的 9-event audit envelope 和 receipt 序列，证明 LLM provenance 不污染 deterministic 路径；heavy primitive receipt 仍 `llm_invoked=false`（不传染）；不需要 ReplayBackend
  - **B4 (`93b909a`)**: `case_backend_failure` ReplayBackend 注入 `LLMError`（`response_text='' + failure='simulated backend timeout'`）；run-ask 失败路径写出 `status=failed` receipt（含 error 字段），shell-summary / today 不崩；`duration_ms` 是 wall-clock 副产品在 failure path 抖动，schema-only 断言；新增 `test_acceptance_no_stop_line_violations` 全套 acceptance goldens 扫描 SoT §12.5 forbidden 关键词（`lane_judge` / `auto_judge` / `l3-proposal-accept` / `l3-proposal-apply` / `hidden_backend`）0 命中
  - **安全边界**: 全程 0 src diff（B1 已在 M6.1 例外条款覆盖范围内，B2/B3/B4 src 改动 0）；无第三方依赖；canonical backend `codex-cli` + `stub-model`，未触达真实 LLM / 网络；alchemy heavy primitive 仍 deterministic（review/distill/propose `llm_invoked=false`），未把 lane judge 引入到 LLM-backed 路径
  - **指标**: 1160 → 1171 unittest baseline tests（B1 +11 unit）/ 92% coverage（test_acceptance_loop.py 自身 22% 是 unittest discoverer 与 pytest fixture 风格 mismatch 的结构性产物，src/ 覆盖未退步）/ acceptance suite 5 (M6.1) + 4 (M6.1b) = 9 passed / `bash scripts/run_acceptance.sh -v` pass / `bash scripts/verify.sh` pass
  - **Gates**: contract 期间一次 prompt_hash drift 修复（render.paths.utc_now monkeypatch）+ 一次 frontmatter 侵入性降低（B3 标记从 candidate 移到 source-b3）；contract 已归档到 `.codex/contracts/archive/M6.1b-llm-replay-acceptance.md`

- **M6.2 Universal Input — 完成（4 commits，本地待 push）**
  - **目的**: 把 CLI `aiwiki drop <payload>` 与 Product Shell 首屏输入收敛到 deterministic Universal Input；typed subcommands / legacy commands 零删除、零行为变化
  - **批次**: B1 `e1b0563` router pure classifier；B2 `f33c7a0` CLI bare drop dispatcher；B3 `735aa29` Product Shell Universal Input UI；B4 acceptance + DOM contract + 收口（本 commit）
  - **Acceptance**: 新增 `tests/fixtures/acceptance/M6.2/case_universal_input/` 与 `test_universal_input_routing`；实际 acceptance smoke 覆盖 `note:` bare drop → typed `drop note` 等价，URL/PDF/image/repo/ask 继续由 B2 mock-based unit tests 覆盖
  - **Product Shell 契约**: 新增 3 个 DOM/string contract tests，冻结 built `main.js` universal input markers、JS router mirror route names、CSS marker，并保留 AskBox/DropZone regression guard
  - **指标**: `scripts/run_acceptance.sh -v` 10 passed（M6.1 5 + M6.1b 4 + M6.2 1）；`bash scripts/verify.sh` pass（1210 tests / 93% coverage）；Product Shell build + `node --check main.js` pass
  - **Stop Lines**: 0 `src/aiwiki/*` 改动；无 LLM / 网络 acceptance 依赖；无第三方依赖；typed/legacy drop 命令未删除；contract 已归档到 `.codex/contracts/archive/M6.2-universal-input.md`

- **M6.3 Single Today Feed — 完成（4 commits，本地待 push）**
  - **目的**: 将 CLI `aiwiki today` 与 Product Shell 首屏收敛到同一 Today feed contract，保留 5 个用户向 section，同时首屏不暴露机制词
  - **批次**: B1 `0696a5f` today_feed.py pure builder（244 LOC / 100% cov）；B2 `8e88c39` CLI today 接 feed（cli.py -89 LOC）；B3 `84c160c` Product Shell renderTodayFeed + `src/today_feed.js` mirror；B4 acceptance + DOM/string contract + flaky 修复 + 收口（本 commit）
  - **Acceptance / Product Shell**: 新增 `tests/fixtures/acceptance/M6.3/case_today_feed/` 与 `test_today_feed_contract`（空 vault smoke：5 section heading + 5 empty placeholders + Advanced 提示 + 机制词 0 泄漏）；新增 `tests/test_product_shell_today_feed.py` 5 个 DOM/string contract tests，冻结 built `main.js` feed markers、旧 helper、JS mirror、CSS marker 与 t() 机制词 guard
  - **Critical Notes**: `test_universal_input_routing` flaky 根因是 `_copy_case_and_fix_clock_from` 未 patch `aiwiki.drop.utc_now`，两次 drop 仍使用真实 wall-clock，导致 `Captured at` timestamp 偶发不同；B4 在 helper 中补 `monkeypatch.setattr("aiwiki.drop.utc_now", ...)`，修后 focused 10/10 pass，全 acceptance 10/10 pass
  - **指标**: acceptance 10 → 11；`bash scripts/verify.sh` pass（1247 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` 11 passed；`PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -v` 11 passed；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass
  - **Stop Lines**: 0 `src/aiwiki/*` 改动；未改 `ShellSummary` / receipt / audit / planner-log / signal schema；无第三方依赖；未删 Advanced 入口或 typed CLI 命令；baseline / M6.1 / M6.1b / M6.2 acceptance 无回归；contract 已归档到 `.codex/contracts/archive/M6.3-single-today-feed.md`

- **M6.4 Knowledge Compounding Metrics — 完成（4 commits，本地待 push）**
  - **目的**: 提供本地即时计算的 7 个知识复利指标，只作为 CLI / ShellSummary / Advanced 抽屉观测报告，不作为自动调度、lane judge 或 proposal auto-accept 输入
  - **批次**: B1 `220d2c5` `metrics.py` pure builder + 4 simple metrics（197 LOC / 100% cov）；B2 `6c9c659` `metrics_io.py` + 剩余 3 指标 + CLI `aiwiki metrics [--json]` + `ShellSummary.metrics`；B3 `ac3de9b` Product Shell Advanced Metrics panel；B4 acceptance + DOM contract + 收口（本 commit）
  - **Acceptance / Product Shell**: 新增 `tests/fixtures/acceptance/M6.4/case_metrics_report/`（`README.md` + `.aiwiki/state/manifest.json` 空 vault smoke）与 `test_metrics_report`，断言 text 输出含 7 个 key、JSON 输出 7 条且 `value/unit/reason/sample_size` 合法；新增 `tests/test_product_shell_metrics.py` 5 个 DOM/style contract tests，冻结 built `main.js` metrics panel、unit handling、CSS marker、Today feed 不暴露 metrics、Advanced drawer 调用 panel
  - **新增模块 / contract 字段**: `src/aiwiki/metrics.py`、`src/aiwiki/metrics_io.py`；`aiwiki metrics [--json]` 新命令；`build_shell_summary` 只新增向后兼容字段 `metrics`，未删除或改动既有 ShellSummary 字段；B3 未新增 `today_feed.js` mirror
  - **Critical Notes**: 最简 fixture 下 7 个指标均可产出；数据不足时允许 `value=None`，但必须带非空 `reason`，有值时 `reason==""`；`review_closure_rate` 等历史不足指标不静默 fallback 为 0
  - **指标**: acceptance 11 → 12；`bash scripts/verify.sh` pass（1298 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` 12 passed；`PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -v` 12 passed；`PYTHONPATH=src python3 -m pytest tests/test_product_shell_metrics.py -v` 5 passed；5 次 acceptance 稳定性 5/5 pass；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass
  - **Stop Lines**: 0 `src/aiwiki/*` B4 改动；未改 receipt / audit / planner-log / signal schema；未改 ShellSummary 既有字段 schema；指标未接入自动调度 / lane judge / auto-accept；无指标 DB / 时序服务 / LLM / 网络 / 第三方依赖；baseline / 既有 acceptance 无回归；contract 已归档到 `.codex/contracts/archive/M6.4-knowledge-compounding-metrics.md`

- **M6.5 Product Shell UI Smoke Tests — 完成（2 commits，本地待 push）**
  - **目的**: 用 stdlib string/regex contract tests 冻结 Product Shell 首屏 5 维度（empty state / 按钮 / 长文本 / responsive / Advanced collapse），防止首屏退化为 dashboard；不引入浏览器自动化或第三方依赖
  - **批次**: B1 `b5069be` 现状冻结 12 个 smoke contract tests（empty state / 主要按钮 / 长文本）；B2+B3 本次扩 4 个 tests（responsive media/max-width + Advanced details/summary collapse）并收口归档
  - **探查结论**: Product Shell 现状已完整覆盖 contract 5 维度，已有 `@media (max-width: 900px/640px)` 与 `details/summary` Advanced 折叠机制，无需补实现
  - **指标**: smoke tests 12 → 16；baseline 1298 → 1314 tests / 93% coverage；`PYTHONPATH=src python3 -m pytest tests/test_product_shell_smoke.py -v` 16 passed；`bash scripts/verify.sh` pass（1314 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` 12 passed；5 次 acceptance 稳定性 5/5 pass
  - **Stop Lines**: 0 src / plugin implementation 改动；未改 `render.js` / `styles.css` / `plugin.js` / `main.js`；未改 ShellSummary / receipt / audit / planner-log / signal schema；无第三方依赖；acceptance 12/12 无回归；contract 已归档到 `.codex/contracts/archive/M6.5-product-shell-ui-smoke.md`
  - **Critical Notes**: B2 没补 `src` / plugin 实现，因为 B1 探查发现 5 维度均已存在；本批只增加 contract 覆盖与归档状态

- **M6.6.1 Module Size Reduction — render.js — 完成（B3 本次收口）**
  - **批次**: B1 `46ede13`（28 函数 → primitives/input/today，`render.js` 2084→1078）；B2 `0067727`（8 函数 → advanced/runs/home，`render.js` 1078→687）；B3 本次（2 函数 → review/execution，`render.js` 687→0/删除 + contract 收口）
  - **指标**: `render_review.js` 363 LOC；`render_execution.js` 324 LOC；`render.js` 已删除；`main.js` 7201→7226 LOC；verify 1314 tests 不变；acceptance 12 不变；5 次 acceptance 稳定性 5/5 pass
  - **Stop Lines**: 函数实现字面 ownership 移动；0 schema / stdout / ShellSummary / DOM contract 改动；`node --check main.js` pass；29 product_shell contract tests pass；verify tests 未低于 1314；5/5 稳定
  - **Critical Notes**: 新增 8 个 render 子模块 + 1 次 `build.sh` concat 顺序最终化；B1 test 路径引用 metrics→`render_today`，B2 metrics→`render_advanced`，B3 未调整 test 路径引用；contract 已归档到 `.codex/contracts/archive/M6.6.1-render-js-split.md`
  - **Gates**: `bash .obsidian/plugins/furnace-product-shell/build.sh` pass；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass；product_shell 29 passed；`bash scripts/verify.sh` pass（1314 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` pass（12 passed）；5 次 acceptance 12/12 passed

- **M6.6.2 Module Size Reduction — plugin.js pure helpers — 完成（本地待 push）**
  - **抽离清单**: `trimDiagnosticText`(10) / `isLlmRelevantRecord`(7) / `parseTimestampMs`(4) / `launcherIsExecutable`(11) / `appendOptionalArg`(8) / `parseLineList`(10) / `normalizeRelativePathList`(10) / `normalizeRewriteProposalObject`(30) / `normalizeRewriteRecoveryAction`(33) / `uniqueContextOptions`(14) / `inferActionIdFromReceipt`(6) / `runLogRelativePath`(3) / `extractPrimaryPath`(13) / `llmBackendUnavailable`(15) / `appendRunEvent`(14)；oracle 中含 `this.` 的 aggregate/extract wrapper 保留在 class 内
  - **指标**: 新增 `src/plugin_helpers.js` 219 LOC；`plugin.js` 2896→2693，净减 203 LOC；`main.js` 7226→7245，+19 LOC；收益判定 ≥200 LOC，继续收口
  - **Gates**: build pass；`node --check main.js` pass；product_shell 29 passed；`bash scripts/verify.sh` pass（1314 tests / 93% coverage）；`bash scripts/run_acceptance.sh -v` pass（12 passed）；5 次 acceptance 稳定性 5/5 pass
  - **Stop Lines**: helper 内 `this.` 0 命中；抽离函数调用 `this.fn(...)` 0 残留；未引入 mixin / prototype assign / module.exports；保持 class 单一身份与 concat 全局函数 KISS
  - **Critical Notes**: 拒绝 mixin；仅做字面移动和调用点 `this.fn`→`fn`；`normalizeRewriteProposalObjects` / `normalizeRewriteRecoveryActions` / `extractRewrite*` / `rewriteProposal*FromObjects` 因 body 含 `this.` 未抽离

## Next Steps

> 后续执行入口已固化到 `docs/Furnace Next Execution Plan.md`。下一轮默认先物化 M6.1 Deterministic Loop Acceptance Pack 到 `.codex/contracts/active.md`，再按该文档继续；M6.1 通过后优先进入 M6.1b LLM Golden Loop，用 GPT / Claude / 显式 backend 验证真实产品黄金闭环。

1. 当前本地可安全闭环的 SoT guardrails 已推进到：L3 manual lifecycle / reject / shell surfacing / receipt audit / policy layout / automatic candidate generation、planner reason order、schedule_tick runtime-history source、heavy/light auto scheduler、superseded cleanup deletion apply、SoT 状态对齐、`judge/distill/review/propose` scoped dry-run preview、deferred apply contract metadata、`review` direct scoped apply baseline、explicit heavy lane apply、explicit auto opt-in、`propose` direct proposal-plane apply baseline、explicit heavy lane propose apply、explicit auto propose opt-in、`distill` direct scoped candidate-refresh apply baseline、explicit heavy lane distill apply、explicit auto distill opt-in、`judge` direct scoped refresh-marker apply baseline、`judge` semantic proposal-preview artifact baseline 与 accepted judge proposal apply baseline
2. 剩余 `judge` 相关 SoT 目标属于 runtime 生成语义判断内容 / lane judge / auto judge，需要显式 LLM/human contract 后才能继续；当前默认闭环不跨过 hidden backend 与 semantic judgment stop line
3. **Product Shell M-PS.1 已完整闭环**：Phase A UI 重写 + Phase B Notifier 集成与 notifier tests 全部完成；飞书 + 企业微信 webhook 通知 / 本地 `last_viewed_timestamp` / 不做 Onboarding / UI + Notifier 合并为单 milestone；详见 `docs/Furnace Product Shell.md` §10/§11
4. **B 阶段（M-PS.B CLI 收敛）已完整落地**：B1 handler_command 分发 (3657442) → B2 advanced 抽屉 + 69 命令双挂 (553f979) → B3 drop 输入端 + 5 个 drop-* deprecation warning (5097a98) → B4 today 输出端 (5b2d2cb)。1146 tests / 93% / 旧命令零删除、runtime 语义零变化、stdout/JSON contract 零变化。Contract 已归档到 `.codex/contracts/archive/M-PS.B-cli-consolidation.md`。
5. **剩余阶段顺序**：~~D (Product Shell M-PS.1)~~ ✅ → ~~C (M-C.1 NVIDIA fallback)~~ ✅ → ~~E (M-E.1 runner.py 7 批拆分)~~ ✅ → ~~M-PS.2 Today output surface~~ ✅ → ~~M6.1 Deterministic Loop Acceptance Pack~~ ✅ → ~~M6.1b LLM Golden Loop~~ ✅ → ~~M6.2 Universal Input~~ ✅
6. M-PS.B (4) + M-PS.1 (11) + M-C.1 (1) + M-E.1 (7) 已 push 到 `origin/investing-research`（120 commits，HEAD `fa05054`）；M-PS.2 (`a666439`) + M6.1 (5 commits, HEAD `a183fcd`) + M6.1b (4 commits, HEAD `93b909a`) + M6.2 (4 commits, B4 本 commit) 本地待 push

## Key Decisions（本世代硬约束）

- SoT = `docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md` + `docs/Furnace Product Shell.md`（Product Shell UI 层事实源）
- M0-M5 推进由 §12.4 Rollout Gate Matrix 定义，§12.5 Stop Lines 为硬停止条件
- M1 只能 `observe_only`、M3 核心环节禁止自动化、M4 默认不 execute、M5 禁止 hidden backend choice
- 每个 milestone 内部走 harness 闭环（contract → fixer → verify → qa-review → 本地 commit），milestone 之间的 gate 由人做
- 不 push 未授权；不新增 hosted service / daemon / multi-user sync / heavy RAG infra / fine-tuning

## Critical Context

- `investing-research` 分支领先 origin 93 个 commit 未推送
- `.codex/plans/active.md` 当前 2928 行仍保留旧路线图（EP-001 ~ EP-021），作为历史记忆不删；新世代 M0-M5 将 append 到 Milestone Index 末尾
- Oracle 可行性评估结论（ses_241268474ffeuvU2CisBfxUJtC / ses_24120afd7ffewDc54gV9DUz2Nr）：M1/M4 = B（可高比例自动）、M2/M5 = C（schema 需人先定）、M3 = D（SoT 禁自动化核心）
