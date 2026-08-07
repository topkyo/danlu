# 入口面残留清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans. Steps use checkbox (`- [x]`) syntax.

**Goal:** 关闭 `docs/plans/2026-08-07-entry-surfaces-residue-scan.md` 中 P0/P1 同类尾巴（不含 C-9 empty telemetry 另案）。

**Architecture:** 快刀修状态/文档 → 补齐 Shell thin-summary 契约 → 一轮删死 path/no-op log → 清兼容 façade。禁止半迁移。

**Tech Stack:** Python stdlib runtime、Product Shell JS、Obsidian workspace JSON、markdown SoT。

---

### Task 1: Workspace + 文档卫生

**Depends on:** none

- [x] 清 repo `.obsidian/workspace.json` 的 `Outputs.md`、`execution-center.md`
- [x] 清 dogfood vault `.obsidian/workspace.json` 的 `Outputs.md`、`output-packs.md`、`domain-pilots.md`
- [x] 修 `docs/Furnace Elixir.md`：死链 Outputs、CLI 加 `advanced`、nightly aging 口径
- [x] 修 `PROGRESS.md` 头条 Jest 203→204、llm 85→84
- [x] 修 `schema/review.md` 去掉 aging-report
- [x] Post-Cleanup §8/D5/D14/checklist Jest 203→204；CHANGELOG Removed「现行见」矛盾
- [x] commercial BOUNDARIES/PRICING + INSTALL 裸 operator → `advanced …`（必要处）
- [x] `wiki/indexes/README.md` `aiwiki compile` → `advanced compile`
- [x] `docs_consistency_check.sh` regex 去掉 execution-center 白名单（若仍是负向允许列表则按扫描意图修正）
- [x] plugin `src/README.md` apply/revert 补「已删」语境
- [x] Verify: `bash scripts/docs_consistency_check.sh`

### Task 2: Shell `curated_page_roots` 契约 + 死键收窄

**Depends on:** none（可与 Task 1 并行文件不冲突时）

- [x] 将 `curated_page_roots` 纳入 `thin_shell_summary_for_persist`（功能在用，补落盘）
- [x] 收窄 `shell_links` / `shell_capabilities.views` 到真实 consumer（或删无 reader 构造）
- [x] 补 Python 和/或 Jest 契约测（thin round-trip 含 curated_page_roots）
- [x] 重建 `main.js` 若改了 src（本任务若只改 Python 则不必）
- [x] Verify: `bash scripts/verify.sh unit product-shell-static`

### Task 3: 死 path helper + no-op wiki log

**Depends on:** Task 1（避免同轮文档冲突即可；代码独立）

- [x] 删 `render/paths.py` 9 个零调用 helper（保留仍在生的 `*_detailed` 等）
- [x] 删除 15 处 `append_wiki_log` 与 `ensure_wiki_log` 调用后删函数
- [x] Verify: `bash scripts/verify.sh python-static unit acceptance`

### Task 4: 兼容 façade 清零

**Depends on:** Task 3

- [x] 清空 `runner/__init__.py` re-export（保留包）
- [x] `content/rewrite.py` 调用方改 `corpus.link_state` 后删 façade
- [x] `execution_surfaces` 的 consistency signal 改直引 `execution_audit_surfaces`
- [x] Verify: `bash scripts/verify.sh python-static unit`；收口 `bash scripts/verify.sh all`

### Task 5: 收口

- [x] 更新 residue scan / PROGRESS 头条记本轮清理
- [x] 汇总 verify 证据

### Task 6: C-9 compile 空状态 telemetry（续）

**Depends on:** Task 3–5

- [x] 删 `compile/build.py` output-pack / domain-pilot load/save/default
- [x] 删 `compile/paths` 两 path；`CompileContext` 字段与 `write_*_artifact`
- [x] `output_step` 不再填空壳；`persist_step` 去掉两 phase 与 result 键；删死 `_compile_log_details`
- [x] `compile_status` / `COMPILE_STATE_*` / lint `expected_*` 同步
- [x] Verify: `python-static` + `unit` + `acceptance` + `llm-integration` + `smoke`
