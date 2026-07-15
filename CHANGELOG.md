# Changelog

All notable changes to 炼丹炉 / aiwiki will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a scorecard-aligned versioning policy:
major milestones map to AgentOS scorecard gates (e.g., `v0.4.0-agentos-9`),
while patch-level increments reflect商业化清理、文档补充与安全加固。

## [Unreleased]

### Removed
- `scripts/`：删除耗时 / niche 脚本 16 个 — `cache_benchmark.py`、`compile_benchmark.py`、`long_window_proof_probe.py`、`dogfood_maturity_gate.py`、`run_dogfood_maturity.sh`、`agos9_release_audit.sh`、`agos9_dogfood_proof_status.sh`、`backend_probe_matrix.sh`、`investing_dogfood_preflight.sh`、`product_shell_smoke.sh`、`run_product_shell_tests.sh`、`check_product_shell_bundle.sh`、`configure_local_worktree.sh`、`stop_line_audit.sh`、`stop_line_audit.py`、`refresh_acceptance_fixture.py`，仅保留 `verify.sh` / `verify_target_rules.sh` / `docs_consistency_check.sh` / `aiwiki-launcher.sh` / install/uninstall + scheduler + `run_acceptance.sh` / `__init__.py` 核心。
- `systemd/`：删除 `aiwiki-dogfood-maturity.service.template` 与 `.timer.template`。
- `tests/`：删除 `test_compile_benchmark_smoke.py` / `test_long_window_proof_probe.py` / `test_local_worktree.py` / `test_product_shell_smoke.py` / `test_dogfood_maturity_gate.py` / `test_cache_benchmark_script_outputs_status_and_timings`；`test_app_runtime.py` / `test_app_misc.py` / `test_deploy_defaults.py` 同步剪除 dogfood maturity / product shell smoke 相关断言。
- `tests/fixtures/acceptance/M6.1b/README.md`：refresh 工具条目从「脚本调用」改为「手动 hash 重命名」，因为 refresh 脚本已删除。

### Changed
- `scripts/install_user_service.sh` / `scripts/uninstall_user_service.sh`：删除所有 `AIWIKI_INSTALL_DOGFOOD_MATURITY` / `run_dogfood_maturity.sh` 分支，仅保留 `watch` + `nightly`；升级路径上对已存在 `aiwiki-dogfood-maturity.*` unit 做清理兜底。
- `scripts/verify.sh`：`product-shell-static` 不再调 `check_product_shell_bundle.sh` / `run_product_shell_tests.sh`，只跑 `node --check main.js`。
- `scripts/verify_target_rules.sh`：删除对应被删脚本路径的 case 分支。
- `AGENTS.md` 验证入口：`scripts` 段补「daily / release」边界说明。
- `docs/DEVELOPER.md` / `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` / `docs/AGOS-9-Scorecard.md` / `docs/Furnace-Optional-Deps-Matrix.md` / `docs/Furnace Product Shell UX Test Checklist.md`：同步移除对已删脚本的引用，明确 release gate 不再依赖被移除的 release-evidence / maturity pipeline。
- `docs/AGOS-9-Dogfood-Proof-Runbook.md` / `docs/AGOS-9-Investing-Preflight-Runbook.md`：移入 `docs/archive/`，标记 superseded。
- `verify.sh all`（仅 release 用）行为不变，仍按 `coverage erase + coverage run pytest + coverage report + acceptance` 跑出 ~13 min 周期；只是被依赖的辅助脚本集已精简。

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

### Changed
- Commercial Grade Cleanup Plan 归档为 `executed-reviewed-pass`；AGENTS/PROGRESS 当前计划指针清空。
- `README.md` 改为用户向入口；`PROGRESS.md` 指向当前 Commercial Grade Cleanup Plan。
- `verify.sh all` 恢复 deterministic `smoke` + `cli-smoke`；Product Shell Jest runner 在插件目录解析依赖。
- `atomic_append_jsonl` 失败时 truncate 回滚；CLI bulk action 对腐坏 state fail-closed。
- `docs_consistency_check.sh` 扩展 D4 / commercial pack / indexes 死链 / `/home/` 门禁。
- Cleanup Plan §1.6 再评估评分卡（综合 ~7.6）；Phase 5 明确 go-live 延期项。

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
