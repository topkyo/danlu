# Changelog

All notable changes to 炼丹炉 / aiwiki will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a scorecard-aligned versioning policy:
major milestones map to AgentOS scorecard gates (e.g., `v0.4.0-agentos-9`),
while patch-level increments reflect商业化清理、文档补充与安全加固。

## [Unreleased]

### Added
- 商业化清理计划落地：`docs/Furnace Commercial Grade Cleanup Plan 2026-07.md`。
- 对外商业化文档集合：
  - `docs/commercial/PRICING.md` — 产品包装、定价 tier、包含/不包含矩阵、不可宣称清单。
  - `docs/commercial/BOUNDARIES.md` — 开源版与商业版边界、明确不卖清单。
  - `docs/commercial/PRIVACY.md` — local-first 数据流、LLM 数据流、不收集声明。
  - `docs/commercial/SUPPORT.md` — 支持渠道、响应 tier、不支持范围。
  - `docs/commercial/COMPARE.md` — 对外竞品对比页，强调差异化价值。
- 新增 `CHANGELOG.md`（本文件）。
- `LICENSE` copyright + dual-license 获取说明；`docs/README.md` Active 表纳入 INSTALL / USER_GUIDE / commercial 文档。

### Changed
- `README.md` / `PROGRESS.md` 指向当前 Commercial Grade Cleanup Plan；商业入口链到 `docs/commercial/`。
- `verify.sh all` 恢复 deterministic `smoke` + `cli-smoke`；Product Shell Jest runner 在插件目录解析依赖。
- `atomic_append_jsonl` 失败时 truncate 回滚；CLI bulk action 对腐坏 state fail-closed。

### Fixed
- （与商业化清理 Wave B/C 同步）脚本硬编码路径、失败测试、凭据 repr 防护等详见 `docs/Furnace Commercial Grade Cleanup Plan 2026-07.md`。
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
