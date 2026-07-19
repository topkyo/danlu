---
title: "Audit Remediation 2026-07-19"
kind: "plan"
status: "active"
updated_at: "2026-07-19"
based_on:
  - ".aiwiki-audit/2026-07-19-full-scan/00-cross-review-score.md"
---

# Audit Remediation Plan（2026-07-19）

> 来源：全量扫描交叉评审建议下一刀。用户已批准执行。
> 非目标：EULA 法律签收、PyPI 发布、Demo 媒体录制（需人类/外部）。

## Task 1 — 去掉 stale `--protocol` 与不可执行 quick commands

**Depends on:** none  
**Files:** `src/aiwiki/render/views.py`, `src/aiwiki/app_shell/helpers.py`, 必要时补 acceptance/单元式契约测

Steps:
1. `furnace_quick_commands`：删除 `--protocol`；命令改为 `advanced ask|compile|nightly|review-queue`（与现行 CLI 一致）。
2. `_build_llm_rerun_command`：删除 `--protocol` 拼接；`run-ask`/`compile`/`lint`/`run-nightly` 经 launcher 的路径改为 `advanced …`（或确认 legacy rewrite 后至少去掉 `--protocol`）。
3. 加窄测：生成的命令字符串不得含 `--protocol`；对 `ask`/`run-ask` 做 argparse 可解析冒烟（临时 root 或 parser 级）。

**Verify:** `PYTHONPATH=src python3 -c` 调用 helpers + `bash scripts/verify.sh python-static`（或 acceptance 相关子集）

## Task 2 — Chromium CLI SSRF：默认关闭 unguarded browser CLI

**Depends on:** none  
**Files:** `src/aiwiki/drop/url.py`（+ 可选 llm-integration/acceptance 若有 drop-url browser 测）

最优解：Playwright 带 route guard 保留；**默认不再走** `_render_url_with_browser_cli`；仅当显式 env（如 `AIWIKI_ALLOW_UNGUARDED_BROWSER_CLI=1`）才启用，并在失败信息中说明 SSRF 风险。`--no-sandbox` 仍保持现有独立 env 门禁。

**Verify:** `bash scripts/verify.sh python-static` + 相关 drop/llm 测若有

## Task 3 — Docs SoT：DEVELOPER owner map + Scorecard §7 + 计数

**Depends on:** none  
**Files:** `docs/DEVELOPER.md`, `docs/AGOS-9-Scorecard.md`, 必要时 `CHANGELOG.md` / `PROGRESS` 指针级、`docs/README` Jest 169

Steps:
1. 重写 DEVELOPER owner map / ASCII 树为 P2-9 后包结构；删 `unittest discover`；补 `llm-integration`。
2. Scorecard §7：改为「app_* hub 已删 / owner 包」当前快照；刷新关键 LOC；Docs 维注明需本轮后复评或同步本轮分数说明。
3. 统一 acceptance=24、Jest=169、Local Eng 勿再写与磁盘矛盾的 facade 表。

**Verify:** `bash scripts/docs_consistency_check.sh`

## Task 4 — Hygiene：graph facade、manifest、docs_consistency gate、轻量僵尸

**Depends on:** Task 3（docs_consistency 扩展可与 Task 3 同 PR 波，但实现上可并行若文件不冲突；本计划串行）

Steps:
1. 删除零 importer 的 `src/aiwiki/memory/graph.py`（确认无 import 后删）。
2. Product Shell `manifest.json` version → `0.4.0`（与 package/runtime 对齐）。
3. `scripts/docs_consistency_check.sh` 增加：active docs 禁止把 `src/aiwiki/app_*.py` / 顶层 `drop.py` 写成现行 owner（archive 除外）。
4. 轻量：`execution/__init__.py` 去掉 app_compile 僵尸 docstring；`_build_llm_rerun_command` 中 `run-compile-summary` → `advanced compile`（若 Task 1 未覆盖）。

**Verify:** `bash scripts/docs_consistency_check.sh` + `python-static`

## Task 5 — 全量 verify 收口

**Depends on:** Task 1–4  
**Verify:** `bash scripts/verify.sh all`

## Out

- EULA 法律签署、PyPI upload、Demo PNG/MP4
- hub 大拆、WS6 伪造 live PASS
