# Changelog

All notable changes to 炼丹炉 / aiwiki will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a scorecard-aligned versioning policy:
major milestones map to AgentOS scorecard gates (e.g., `v0.4.0-agentos-9`),
while patch-level increments reflect商业化清理、文档补充与安全加固。

## [Unreleased]

### Fixed
- Product Shell 纯投料成功显示「已收料」，不再误用「排队生成报告 / 生成被阻断」；reconcile 对纯投料只匹配 raw/receipts。
- Obsidian GUI PATH 命中 Apple Python 3.9 时，`zip(..., strict=)` 导致 drop 后 auto-compile 崩、Shell 显示「生成被阻断」：去掉 `strict=`；`aiwiki-launcher.sh` 显式挑选 ≥3.10；vault launcher 改为转发 runtime launcher。
- Rescan P1 ingest/governance：死 CLI hint → `advanced review-queue`；CJK overlapping bigram 不再拼乱码短语；确定性 GitHub raw/blob/tree rewrite；路径 fail-loud 不再误伤裸目录 / 中文 `A/B…`；`run-ask`/`run-ask-resume` LLM 移出写锁；alchemy lane receipt 失败不再谎称 mutation rolled back；local target 须派生自 original payload（拒 vault 内部无关路径）。

### Added
- URL 投料幂等：`normalize_ingest_url` + manifest 短路；同规范化 URL 默认 `reused` 不新建 `-N`；`drop url|plan --refresh` 覆盖同 path。
- Universal drop **plan/execute**：`src/aiwiki/input_planner.py`（LLM 分类 Plan，不写 `raw/`）+ `src/aiwiki/executor.py`（deterministic 原样落盘 + SSRF `safe_fetch` + 事务回滚）；CLI `drop plan <payload>`；默认 `drop <payload>` 走 planner（`AIWIKI_LLM_PLANNER=0` 关闭）。
- Alchemy distill 可选 LLM body synthesizer（`runner/alchemy.py` 编排层注入；mutation 层仍 deterministic；`AIWIKI_LLM_DISTILL=0` 关闭）。
- `tests/test_llm_integration.py`：现行 **85** 条（含 ingest 幂等 / refresh、plan/execute、CJK、path containment、distill synthesizer、safe_fetch 重定向）；历史起点为 42 条。
- `.pre-commit-config.yaml`：pre-commit hook（ruff check + ruff-format check + check-merge-conflict / check-yaml / check-added-large-files 500KB），轻量 gate；完整验证仍靠 `bash scripts/verify.sh`。
- `src/aiwiki/utils/` 子包：`io` / `security` / `markdown` / `text` / `hash` / `time` / `path` / `json_utils` / `audit`（原 `app_utils.py` 下沉）。
- `src/aiwiki/state/` + owner 子包：`io` / `constants` / `manifest` / `cache` / `compile/state` / `compile/build` / `content/material` / `content/archive` / `content/rewrite` / `execution/history` / `memory/action_state` / `memory/state` / `planner/state`（原 `app_state.py` 下沉）。
- `src/aiwiki/memory/action_core.py`、`src/aiwiki/execution/policy.py`、`src/aiwiki/execution/patch_plan.py`、`src/aiwiki/execution/repair_plan.py`（原 `content/memory.py` 按域拆分）。
- `src/aiwiki/compile/ranking.py`：10 个 ranking 函数从 `app_compile.py` 迁入。

### Changed
- `utils/text.tokenize`：CJK Lucene-style bigram 切分（拉丁不变），修复中文检索/concept ranking 静默失效。
- `drop/repo` / `drop/url` / `protocol/runtime_config.CONFLICT_SIGNAL_PAIRS`：扩后缀、正文选择器与中英冲突信号对。
- Hub decomposition（用户显式覆盖原 AGENTS.md 「legacy hub 另一条搬迁线」定案）：`app_utils.py` / `app_state.py` / `app_compile.py` 删除，函数体原样下沉到 `utils/` + `state/` + owner 子包；`content/memory.py` 1350 行拆到 4 个 owner 模块，缩为仅含 2 个 A 域辅助函数；原 `app_compile` ranking 迁至 `compile/ranking.py`。约 165 文件 import 更新，测试 patch target 同步迁移。无 re-export compat 保留。
- `compile/__init__.py` 改惰性 `__getattr__` 暴露 `compile_wiki`，解决 hub 下沉后的循环 import。
- `AGENTS.md` L115 CLI 入口描述修复：顶层仅 `drop/today/advanced`；`metrics` / `file-back` / `review-page` / `compile` 等 operator 命令仅经 `advanced` 子命令（非顶层）。
- `src/aiwiki/trace.py` docstring 资产种类数 `6 类` → `9 类`。
- `execution/{archive,lifecycle,ask,runtime_surfaces,concept_rewrite}.py` stale docstring 修复：删除对已移除 `_LAZY_OWNERS` / `app_compile.utc_now` 的引用。
- verify 现行口径：acceptance **24** + llm-integration **85** + unit **72** + Jest **203**（coverage **64%** informational；历史 16/17/18/25、42/65/76/78/79、174/189/206 等为沿革快照）。
- Capability follow-up：CJK concept/slug/stopwords；`fetch_raw` fail-loud；local-path fail-loud + containment；distill LLM outside write lock + `llm_invoked` receipt；GitHub blob/tree planner few-shot。
- Rescan follow-up：见 Fixed；verify llm-integration 沿革曾为 **79**，现行 **85**。

### Removed
- `src/aiwiki/app_utils.py`：已下沉到 `utils/` 子包（1200 行/52 符号/89 文件引用）。
- `src/aiwiki/app_state.py`：已下沉到 `state/` + owner 子包（1200 行/70 函数/60 文件引用）。
- `src/aiwiki/dogfood_maturity.py`：死代码（全仓库零 import 引用，40 行）。

### Removed
- Per-action `output/control/execution-receipts/*.json`：迁到 `.aiwiki/state/execution-receipts/`（Obsidian 不可见）；历史流仍为 `execution-receipts.jsonl`。
- `output/lint/` lint 报告：迁到 `.aiwiki/lint/`（Obsidian 不可见）；`semantic-lint-*.md` 与 `lint-*.md` 仍共用保留最近 10 份轮转。
- `output/control/execution-bundles/` 执行包与 dry-run preview：迁到 `.aiwiki/state/execution-bundles/`；dry-run 保留最近 20 份。
- `output/control/execution-batches/` batch receipt：迁到 `.aiwiki/state/execution-batches/`。
- `output/control/runs/*/thinking.md` run notes：`write_run_notes` no-op；Product Shell 去掉「打开进度笔记」入口。进度看气泡状态，审计看报告/receipt。
- `wiki/indexes/log.md` Obsidian-visible operation log：`append_wiki_log` / `ensure_wiki_log` 改为 no-op；不再写入 vault。权威历史仍为 `.aiwiki/state/runtime-history.jsonl` + receipts/audit（大 `log.md` 会拖死 Obsidian 索引）。
- `output/control/plugin-runs/*.md`：Product Shell 不再落盘 Obsidian 可见 run log；`persistProductShellRunLog` no-op。权威仍为 `.aiwiki/logs/runs.jsonl` + 内存 recentRuns。
- Judgment/Decision 页内无界 `## Review History` append：`append_review_history_entry` 与 auto-adopt 页内 mutate 改为 no-op；审阅仍更新 Review Status/Notes，权威事件进 runtime-history / receipts。

### Added
- Commercial Go-Live：`docs/commercial/EULA.md`；Product Shell `package.json` / Jest hard-gate；`src/aiwiki/default_prompts/` 随包分发；Demo Pack 对外 checklist + `assets/README.md`。

### Changed
- Obsidian dump P1：lint / execution-bundles / execution-batches 迁入 `.aiwiki`；planner lane `apply_contract` write_surfaces 同步；dry-run 保留最近 20 份。
- Obsidian dump P2 staging：`output/_candidates/elixirs/` → `.aiwiki/staging/elixirs/`；`output/_proposals/{prompt,policy,judge}/` → `.aiwiki/staging/proposals/{prompt,policy,judge}/`；`LAYOUT_DIRS`、`app_vault` ignore/hidden 列表与 vault README 同步；dry-run `write_surfaces` 与 acceptance golden 已更新。
- Obsidian dump P3 derived：`output/agents|packs|pilots` → `.aiwiki/derived/{agents,packs,pilots}`；rewrite-proposals 清理 state 外孤儿页。
- `.aiwiki/lint/` 下 `semantic-lint-*.md` 与 `lint-*.md` 共用保留最近 10 份轮转（`_rotate_lint_reports`）。
- Commercial Go-Live WS1–WS5：商务邮箱→`topkyoxp@gmail.com`；首发仅询价；`pip install -e .` 预览路径与 v0.4.0；launcher 优先 `aiwiki` console script；alchemy materialize 改 `atomic_write_text`；README/COMPARE 明确 LLM-Wiki production runtime 定位。

### Removed
- `scripts/`：删除耗时 / niche 脚本 16 个 — `cache_benchmark.py`、`compile_benchmark.py`、`long_window_proof_probe.py`、`dogfood_maturity_gate.py`、`run_dogfood_maturity.sh`、`agos9_release_audit.sh`、`agos9_dogfood_proof_status.sh`、`backend_probe_matrix.sh`、`investing_dogfood_preflight.sh`、`product_shell_smoke.sh`、`run_product_shell_tests.sh`、`check_product_shell_bundle.sh`、`configure_local_worktree.sh`、`stop_line_audit.sh`、`stop_line_audit.py`、`refresh_acceptance_fixture.py`，仅保留 `verify.sh` / `verify_target_rules.sh` / `docs_consistency_check.sh` / `aiwiki-launcher.sh` / install/uninstall + scheduler + `run_acceptance.sh` / `__init__.py` 核心。
- `systemd/`：删除 `aiwiki-dogfood-maturity.service.template` 与 `.timer.template`。
- `tests/`：删除 `test_compile_benchmark_smoke.py` / `test_long_window_proof_probe.py` / `test_local_worktree.py` / `test_product_shell_smoke.py` / `test_dogfood_maturity_gate.py` / `test_cache_benchmark_script_outputs_status_and_timings`；`test_app_runtime.py` / `test_app_misc.py` / `test_deploy_defaults.py` 同步剪除 dogfood maturity / product shell smoke 相关断言。
- `tests/fixtures/acceptance/M6.1b/README.md`：refresh 工具条目从「脚本调用」改为「手动 hash 重命名」，因为 refresh 脚本已删除。
- `scripts/verify.sh` 整个 `unit` target（含 `verify_unit()` 函数 + dispatch case + usage help 一行）删除；与 `all` 唯一差别是 coverage overhead，`unit` 是 `all` 的"裸测版本"，被证实为冗余单独入口。
- `scripts/verify.sh` 中 `all|full)` 后串行落点里 `coverage erase + coverage run pytest + coverage report` 三段（约 12 min）一并删除；`.coveragerc` 同步删，`pyproject.toml` 中 `coverage>=7.6,<8` dev 依赖同步移除。`verify.sh all` 退化为 `scripts + product-shell-static + cli-smoke + smoke + python-static + acceptance + llm-integration`（无 coverage gate；**acceptance 17** 为 2026-07-15 historical 口径；现行见 Unreleased：**24** / llm-integration **85** / unit **72** / Jest **203**）。
- `scripts/verify_target_rules.sh`：`.coveragerc` 路径 case 一并删除（文件已无）。
- `tests/` 收缩到 acceptance-only + llm-integration：删除 118 个顶层 `tests/test_*.py`（除 `tests/test_acceptance_loop.py` / `tests/test_llm_integration.py`） + 26 个 `tests/unit/test_*.py`，合计 144 个 pytest 单元测试文件 / 约 56k LOC 退役。`tests/` 现含 `tests/test_acceptance_loop.py` + `tests/test_llm_integration.py` + `tests/acceptance/` + `tests/fixtures/`，由 `bash scripts/verify.sh all` 默认跑 acceptance replay + llm-integration（**17** 为 2026-07-15 historical；**18**/llm-integration **78**/Jest **189** 等为中间快照；现行见 Unreleased：**24** + llm-integration **85** + unit **72** + Jest **203**）。`tests/unit/` 整目录也从 git 跟踪中清空。
- `scripts/archive/` 整目录删除（5 文件：`dogfood-watch.sh` / `p0_operational_setup.sh` / `p1_p2_gate_review.sh` / `extract_rounds.py` + `README.md`）：它们没有 live 调用者，只在 `docs/archive/` 与 `archive/rounds/` 历史文档中作为 runbook evidence 出现，README 自白为 "new automation should not depend on archived scripts"。
- **[Round 7 cross-review]**: `tests/fixtures/{planner_log, signals, signals_collector}/` 三个孤立目录共 42 文件（307 LOC）：acceptance/case_runner.py 与 `tests/test_acceptance_loop.py` 全部 case 均不引用此 fixtures，pure 孤立 cleanup，零风险（**17** case 为 historical 口径；现行 **24** acceptance）。

### Changed
- `scripts/install_user_service.sh` / `scripts/uninstall_user_service.sh`：删除所有 `AIWIKI_INSTALL_DOGFOOD_MATURITY` / `run_dogfood_maturity.sh` 分支，仅保留 `watch` + `nightly`；升级路径上对已存在 `aiwiki-dogfood-maturity.*` unit 做清理兜底。
- `scripts/verify.sh`：`product-shell-static` 不再调 `check_product_shell_bundle.sh` / `run_product_shell_tests.sh`，只跑 `node --check main.js`。
- `scripts/verify_target_rules.sh`：删除对应被删脚本路径的 case 分支；移除 `unit` 在 `.coveragerc` / `schema/*.json` / `scripts/*.py` / `src/aiwiki/cli*.py` / `src/aiwiki/*.py` / `tests/*.py` 的推荐（这些路径单独改动不再自动触发全量 pytest）。
- `scripts/run_launchd_watch.sh`：`watch …` argv 改写为 `advanced watch …`，消除 watcher 启动后 stderr `[deprecated] aiwiki watch is a legacy top-level entry` 噪音行（`run_launchd_nightly.sh` 早已用 `advanced run-nightly`，未动）。
- `AGENTS.md` 验证入口：`scripts` 段补「daily / release」边界说明 + 删除 `unit`（pytest，无 coverage）条目；常用 target 列为 `scripts` / `smoke` / `python-static` / `acceptance` / `cli-smoke` / `product-shell-static` / `all`。
- `AGENTS.md`：把 "tests/ 下 2509 单元测试作为契约保留" 一段重写为 "tests/ 收缩到 acceptance-only（test_acceptance_loop.py + tests/acceptance/ + tests/fixtures/）"，与 commit 2 的 changes 一致。
- `docs/`：5 个 Furnace legacy docs → `docs/archive/`（git 自动 rename 100%）：`Market Scan 2026Q2.md` / `Product Shell UX Test Checklist.md` / `Investing Dogfood Plan.md` / `RuntimeClient Mobile Companion Design.md` / `Agentic Debt Autopilot.md`。活跃 docs 从 14 → 9。
- `.gitignore`：删除 `.agentstack/` 与 `.agents/skills/agentstack-*/` defensive ignore（AGENTS.md 已禁止 agentstack 引入）；保留 `.codegraph/` 与 `.coverage`（本机仍在生成此类 local scratch）。
- `docs/Furnace-Optional-Deps-Matrix.md` → `docs/archive/Furnace-Optional-Deps-Matrix.md`：可选包矩阵的 SoT 角色已被 acceptance-only verify 与 `tests/fixtures/` 的 byte-stable 兑现弱化；文档 / 测试矩阵单表过气。
- `docs/README.md` "Active" / "Delivered specs" / "Reading order" / "关系图" 四段同步剪切：移除已 archive 的 7 个 doc（AGOS-9-Dogfood-Proof-Runbook / AGOS-9-Investing-Preflight-Runbook / Furnace Investing Dogfood Plan / Furnace Product Shell UX Test Checklist / Furnace Agentic Debt Autopilot / Furnace Market Scan 2026Q2 / Furnace RuntimeClient Mobile Companion Design）+ Optional-Deps-Matrix；剩 Active 16 entry（不含商业 5 项与 License/Changelog）。
- `docs/archive/README.md`：列表加入上 8 个新 archive 项（含 Furnace-Optional-Deps-Matrix），指明每个原 doc 被 [ARCHIVED] → [ACTIVE replacement] 的替代关系。
- `PROGRESS.md` head：删除 R68 结构 v2 备注（`结构 v2` 自 2026-07 cross-review 后已无实际约束）+ `archive/rounds/` round 文档指针（archive/rounds/ 不再作为新 round 落点）+ `archive/rounds/index.json` 机器索引指针（同步失效）+ `archive/PROGRESS-pre-round1.md` 切档历史指针（已 sink）。只保留 `PROGRESS.md 是 SoT` 的明示 + `## SoT 引用` 段。
- `docs/DEVELOPER.md` / `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` / `docs/AGOS-9-Scorecard.md` / `docs/Furnace-Optional-Deps-Matrix.md` / `docs/Furnace Product Shell UX Test Checklist.md`：同步移除对已删脚本的引用，明确 release gate 不再依赖被移除的 release-evidence / maturity pipeline。
- `docs/AGOS-9-Dogfood-Proof-Runbook.md` / `docs/AGOS-9-Investing-Preflight-Runbook.md`：移入 `docs/archive/`，标记 superseded。
- `verify.sh all`（release 用）不再跑 pytest unit / coverage gate；现行为 7 步（scripts + product-shell-static + cli-smoke + smoke + python-static + acceptance + llm-integration，见 Unreleased 现行口径 **24** / **85** / **72** / **203**）。
- **[Round 7 cross-review]**: `docs/AGOS-9-Scorecard.md`：在 2026-05-24 AOS-C8 frozen evidence 段顶部加 banner 说明 "post-2026-07-15 verify.sh all 不再走 pytest/coverage"；在所有 `tests/test_*.py` 与 `dogfood_maturity_gate.py` / `agos9_*.sh` 引用行加 `[AOS-C8 frozen 2026-05-24]` / `[已删]` inline 注；保留 scorecard 的 AOS-C8 milestone frozen 史料价值。约 12 行改写。
- **[Round 7 cross-review]**: `AGENTS.md` Cursor Cloud 段：删除 `coverage` / `unittest discover` stale lines（3 处）；dev deps 改写为 `ruff + pytest + beautifulsoup4`；历史 `test_obsidian_workspace.test_workspace_defaults_open_home_and_furnace_center` 与 `test_drop.test_fetch_url_raises_when_no_text_can_be_recovered` 改为 "历史（已删）" 说明并指向对应 src module 自检路径。
- **[Round 7 cross-review]**: `docs/DEVELOPER.md` verify target list：`bash scripts/verify.sh [scripts|smoke|python-static|unit|...]` 删除 `unit|` 一行。
- **[Round 7 cross-review]**: `docs/Furnace Runtime Operations.md:318` + `docs/commercial/COMPARE.md:7,69` 三处 stale path：`docs/Furnace Market Scan 2026Q2.md` → `docs/archive/Furnace Market Scan 2026Q2.md`。
- **[Round 7 cross-review]**: `src/aiwiki/` 8 处 stale docstring / comment 提及已删 `tests/test_app.py` / `tests/test_metrics.py`：重写为 "acceptance tests + downstream suites" 描述并保留 lazy-import patch seam 语义。`src/aiwiki/execution/__init__.py` 移除 stale `_LAZY_OWNERS` PEP 562 seam 描述（该 seam 已不存在），指向 AGENTS.md 架构清理定案段。
- **[Round 7 cross-review]**: `PROGRESS.md` 历史 (verify.sh all 不再跑 pytest+coverage) 条目尾部追加 `[superseded · commit a76fa66]` 标记，说明 144 pytest 文件 + 2509 单元测试随之退役，与本轮顶部 "cross-review 进一步瘦身" 条目指向同一迁移轨迹。
- Commercial Grade Cleanup Plan 归档为 `executed-reviewed-pass`；AGENTS/PROGRESS 当前计划指针清空。
- `README.md` 改为用户向入口；`PROGRESS.md` 指向当前 Commercial Grade Cleanup Plan。
- `verify.sh all` 恢复 deterministic `smoke` + `cli-smoke`；Product Shell Jest runner 在插件目录解析依赖。
- `atomic_append_jsonl` 失败时 truncate 回滚；CLI bulk action 对腐坏 state fail-closed。
- `docs_consistency_check.sh` 扩展 D4 / commercial pack / indexes 死链 / `/home/` 门禁。
- Cleanup Plan §1.6 再评估评分卡（综合 ~7.6）；Phase 5 明确 go-live 延期项。

### Added
- 商业化清理计划落地并已归档：`docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md`。
- 对外商业化文档集合：
  - `docs/commercial/PRICING.md` — 产品包装、定价 tier、包含/不包含矩阵、不可宣称清单。
  - `docs/commercial/BOUNDARIES.md` — 开源版与商业版边界、明确不卖清单。
  - `docs/commercial/PRIVACY.md` — local-first 数据流、LLM 数据流、不收集声明。
  - `docs/commercial/SUPPORT.md` — 支持渠道、响应 tier、不支持范围。
  - `docs/commercial/COMPARE.md` — 对外竞品对比页，强调差异化价值。
- 新增 `CHANGELOG.md`（本文件）。
- `LICENSE` copyright + dual-license 获取说明；`docs/README.md` Active 表纳入 INSTALL / USER_GUIDE / commercial 文档。
- `docs/DEVELOPER.md`：从 README 拆出的开发者 SoT（owner map / verify / LLM / 自动化）。

### Fixed
- 刷新 M6.1b acceptance `prompt_hash` golden（`case_happy_run_ask` / `case_backend_failure`）。
- （与商业化清理 Wave B/C 同步）脚本硬编码路径、失败测试、凭据 repr 防护等详见 `docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md`。
- 交叉审查后续：断链、`alchemy-status` 虚构命令、`CLAUDE.md` 残留引用、`AIWIKI_LLM_TIMEOUT` 变量名、systemd 含空格 vault 路径渲染。

## [0.4.0-agentos-9] - 2026-05-24

### Added
- AOS-C8 release gate PASS：本地 scorecard 约 9.05。
- P1-P5 stabilization：
  - `run-ask` success receipt matrix v1 覆盖 report / background / direct / local 路径。
  - planner-log 新增向后兼容的 optional `phase` proof。
  - CLI legacy top-level 口径收敛为 compat，顶层只注册 `drop / today / metrics / advanced`。
  - 14/30-day natural run proof 明确标记为 `not-yet`。

### Changed
- `run-ask` 失败时写出可审计失败说明与 run notes，不再伪装为 deterministic fallback 成功。
- backend fallback 链默认为空，不再做隐式跨 backend fallback。

## [0.3.1] - 2026-05-23

### Added
- AOS-C3 receipt coverage：direct / local `run-ask` success paths 现在写入 execution receipt。
- `dogfood_maturity_gate.py collect` 暴露 warn-only `receipt_coverage` 字段，解释 missing / legacy / background / degraded / deterministic-baseline 情况。

### Changed
- report / direct / local success receipt 顺序改为 rollback-safe。

## [0.3.0-agentos-baseline] - 2026-05-20

### Added
- AgentOS 9.0 scorecard 初版；baseline 综合分 7.8。
- AGOS-001 baseline 建立：八维评分、release gate、proof 分层规则。
- AGOS-002 live Day1 proof；3-day / compounding proof 进入 pending。
- AGOS-003~007 机制收口：Product Shell、Docs、Maintainability、Planner、LLM reliability。

### Changed
- runtime 进入 AgentOS 路线前的回溯点 tag：`v0.3.0-agentos-baseline`。

## 历史版本

更早的变更记录见 git log 与 `docs/archive/` 中的历史计划文档。
