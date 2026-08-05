# Facade Zero (`app_shell` / `app_linting`) — Implementation Plan

> **For agentic workers:** Load `executing-plans` or inline（本计划 ≤3 task，可 inline）。

**Goal:** 删除 `_CompatModule` 重 facade；调用方与 acceptance mock 直引 owner；`__init__.py` 仅文档。
**Spec:** `docs/plans/2026-08-05-structural-debt-resolution.md` §5.1；AGENTS「纯 facade 一轮做干净」。
**Out:** hub 拆分、corpus 再扩、Commercial。

---

## Task 1: 迁 app_shell 调用方 + 解 meta 注入环

**Depends on:** none

- [x] `execution/ask.py`、`runtime_surfaces.py`、`compile/output_step.py`、`runner/workflows_ask_receipts.py` → `from ..app_shell.summary import build_shell_summary` + `from ..app_shell.meta import write_shell_summary`
- [x] `cli/dispatch.py` → `from ..app_shell.controls import rewrite_followup_payload_for_paths`
- [x] `app_shell/meta.py`：去掉 `build_shell_summary`/`render_product_shell_html` 模块级注入；函数内 lazy import
- [x] `tests/acceptance/case_runner.py`：`setattr("aiwiki.app_shell.summary.utc_now", ...)`
- [x] `app_shell/__init__.py` → docstring only（无 re-export、无 `_CompatModule`）
- [x] **Verify:** `bash scripts/verify.sh python-static unit acceptance`

## Task 2: 迁 app_linting mock + 清空 __init__

**Depends on:** none（可与 Task 1 同波；文件不重叠）

- [x] `tests/acceptance/case_runner.py`：`setattr("aiwiki.app_linting.core.datetime", _FixedDateTime)`
- [x] `app_linting/__init__.py` → docstring only
- [x] **Verify:** `bash scripts/verify.sh acceptance`（时钟 seam）

## Task 3: 门禁 + SoT + final verify

**Depends on:** Task 1, Task 2

- [x] `docs_consistency` 或 library 测：`__init__.py` 无 `_CompatModule`；可选钉「无 from aiwiki.app_shell import X」生产代码（allowlist 空）
- [x] DEVELOPER / PROGRESS 一句
- [x] `bash scripts/verify.sh all`

**Done:** 两包 `__init__` 无 facade；acceptance 绿；verify all 绿。
