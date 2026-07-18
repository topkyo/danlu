# Freeform Ask Markdown Only — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Use `subteam` / reviewer after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** Ask 只产出自由 Markdown 报告；硬删多 format / 六段校验 / `--direct`；零兼容；修好 Today 打开报告/审阅；收工同步 Active 文档。  
**Spec:** `docs/specs/2026-07-18-freeform-ask-markdown-only.md`  
**Architecture:** 单一 `output/reports/*.md` 管线；thin seed + soft prompt；最小校验（frontmatter / 非空 / 无 `_LLM:`）；CLI 仅 `report`。  
**Tech stack:** Python 3.10+ stdlib, Product Shell JS, `bash scripts/verify.sh`

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `src/aiwiki/default_prompts/ask.md` | modify | 自由 md prompt |
| `prompts/ask.md` | modify | 与 default 同步（vault/L3 目标） |
| `src/aiwiki/app_queries.py` | modify | `render_report` 去骨架；删仅 Ask 用的 render_* |
| `src/aiwiki/runner/prompts.py` | modify | 删 `_validate_report_sections`；收缩校验 |
| `src/aiwiki/execution/ask.py` | modify | 仅 report 分支 |
| `src/aiwiki/cli/parsers.py` | modify | `--format` 仅 report；删 `--direct` |
| `src/aiwiki/runner/workflows_ask.py` | modify | 删 note/direct 路径 |
| `.obsidian/plugins/furnace-product-shell/src/command_specs.js` | modify | 清 `--direct` 死代码 |
| `.obsidian/plugins/furnace-product-shell/src/render/cards.js` | modify | 接线 open/review/snooze |
| `.obsidian/plugins/furnace-product-shell/src/plugin.js` | modify | 实现缺失方法（若 cards 调用） |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | `bash build.sh` |
| `docs/USER_GUIDE.md` / `docs/DEVELOPER.md` / `docs/Furnace Product Shell.md` / `docs/Furnace Evolution Mechanics.md` / `PROGRESS.md` / `README.md`（若有 Ask format 表述） | modify | Active 文档同步 |
| acceptance fixtures（仅当断言六段硬失败时） | modify | 改最小自由 md 契约 |

---

## Task 1: Freeform prompt + report seed + validator

**Depends on:** none

**Files:**
- Modify: `src/aiwiki/default_prompts/ask.md`
- Modify: `prompts/ask.md`（与 default 内容一致）
- Modify: `src/aiwiki/app_queries.py` — `render_report`
- Modify: `src/aiwiki/runner/prompts.py` — 删除 `_REPORT_*` / `_validate_report_sections`；`_validate_output_markdown` 仅：report 需 frontmatter；正文非空（去 frontmatter 后）；fence 外无 `_LLM:`；**不再**要求 `wiki/sources/` 硬存在、不再要求六段

- [ ] **Step 1:** 重写 `ask.md`：删除 `format: note` 段与 `## Required Sections`；改为自由 Markdown 指引（直接回答、尽量引用 `wiki/sources/*.md`、标不确定、保留 frontmatter）。
- [ ] **Step 2:** `render_report`：输出 frontmatter + `# {title}` + 可选参考块（协议偏置 / 优先来源 / 优先概念 / 机器记忆提示）；**禁止**注入六段 H2 与 `_LLM:` 占位行。
- [ ] **Step 3:** 删除 `_validate_report_sections` 及其常量/helpers（若仅被其使用）；更新所有 callers。
- [ ] **Verify:** `PYTHONPATH=src python3 -c "from aiwiki.app_queries import render_report"` 可 import；`rg '_validate_report_sections|_REPORT_REQUIRED_SECTIONS' src/aiwiki` 无匹配；`bash scripts/verify.sh python-static`

**Commit:** `feat(ask): freeform markdown prompt and drop six-section validator`

---

## Task 2: Hard-delete Ask multi-format + `--direct`

**Depends on:** Task 1

**Files:**
- Modify: `src/aiwiki/execution/ask.py`
- Modify: `src/aiwiki/cli/parsers.py`（`ask` / `run-ask` / `run-ask-submit`；**不要**动 `drop --kind note`）
- Modify: `src/aiwiki/runner/workflows_ask.py`
- Modify: `src/aiwiki/app_queries.py` — 删除 `render_note_answer` / `render_slides` / `render_figure_brief` / `render_decision_memo_query` / `render_sop_query`（确认无非 Ask caller 后删除）

- [ ] **Step 1:** `ask.py`：仅 `report` 分支；未知 format → `ValueError`；清空 `OUTPUT_FORMAT_FILENAME_SUFFIXES` 非 report 项（可删整个 dict 若无用）。
- [ ] **Step 2:** parsers：`--format choices=("report",)`；删除 `run-ask` 的 `--direct` 参数及帮助文案。
- [ ] **Step 3:** `workflows_ask.py`：删除 `_is_simple_direct_ask` / `_is_material_hint_note_ask` 及所有 `format == "note"` / `direct` 分支；统一 report 填充。
- [ ] **Step 4:** 删除仅 Ask 使用的 render helpers；清理 import。
- [ ] **Verify:** `PYTHONPATH=src python3 -m aiwiki.cli --help` 中 ask/run-ask 无 note/slides；`PYTHONPATH=src python3 -m aiwiki.cli --root /tmp ask "x" --format note` 非 0（可用临时空 vault 或 `-h` 验证 choices）；`rg 'render_note_answer|render_slides\(|--direct' src/aiwiki` 无 Ask 路径残留；`bash scripts/verify.sh python-static`

**Commit:** `feat(ask): remove non-report formats and --direct`

---

## Task 3: Product Shell — format cleanup + Today 按钮修复

**Depends on:** Task 2

**Files:**
- Modify: `.obsidian/plugins/furnace-product-shell/src/command_specs.js` — 删除 `--direct` 死代码块
- Modify: `.obsidian/plugins/furnace-product-shell/src/render/cards.js` — `goToReport` → `openWorkspacePath`；review/snooze 接真实 API
- Modify: `.obsidian/plugins/furnace-product-shell/src/plugin.js`（若选择在 plugin 上实现薄封装方法）
- Modify: 相关 Jest（`src/__tests__/render/cards.test.js` 等）
- Rebuild: `bash .obsidian/plugins/furnace-product-shell/build.sh` 或仓库惯用 `bash build.sh`

- [ ] **Step 1:** cards：打开报告 `plugin.openWorkspacePath(entry.target)`；审阅 `plugin.openReviewCenterView()` 或按 target 打开；snooze `plugin.runTodaySnoozeCommand(entry.target)`。也可在 `plugin.js` 实现同名方法做薄封装，二选一，**禁止**保留未定义调用。
- [ ] **Step 2:** 清 `command_specs.js` 中 `canUseDirect` / `--direct`。
- [ ] **Step 3:** 重建 `main.js`；更新 Jest。
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`

**Commit:** `fix(shell): wire today report/review actions; drop --direct`

---

## Task 4: Acceptance / fixture 对齐 + final verify

**Depends on:** Task 2, Task 3

**Files:**
- Modify only if gates fail: `tests/fixtures/acceptance/**`、`tests/test_acceptance_loop.py`

- [ ] **Step 1:** 跑 `bash scripts/verify.sh all`（或 `scripts` + `python-static` + `product-shell-static` + `acceptance` + `cli-smoke` + `smoke`）。
- [ ] **Step 2:** 若 fixture 因硬编码六段校验失败而红：把断言改为「自由 md + frontmatter」；**不要**为通过测试恢复六段 validator。旧 fixture 正文含六段可保留（仍是合法自由 md）。
- [ ] **Verify:** `bash scripts/verify.sh all` PASS

**Commit:** `test: align acceptance with freeform ask reports`（仅有改动时）

---

## Task 5: Active 文档同步

**Depends on:** Task 4

**Files:**
- Modify: `PROGRESS.md`（本轮结论）
- Modify: `docs/USER_GUIDE.md`、`docs/DEVELOPER.md`、`docs/Furnace Product Shell.md`、`docs/Furnace Evolution Mechanics.md`（Ask 多 format / slides/figures 产物表述 → 仅 `output/reports/*.md` 自由报告）
- Modify: `README.md` 若仍写 ask format 列表
- **不要**改 `docs/archive/**` 历史保真文

- [x] **Step 1:** Active 文档去掉「六段骨架 / note format / ask slides|figure|decision-memo|sop」为现行能力的表述。
- [x] **Step 2:** `PROGRESS.md` 记：freeform ask + hard-delete formats + shell 按钮修复。
- [x] **Verify:** `bash scripts/docs_consistency_check.sh`（若存在且适用）；人工确认无「现行六段」矛盾

**Commit:** `docs: sync active docs for freeform ask-only markdown`

---

## Final verify

`bash scripts/verify.sh all`

---

## Execution notes

- Branch / worktree: `feat/freeform-ask-markdown-only`
- No alias / deprecation warnings for old formats — argparse reject only
- Preserve `drop --kind note` and review `note` fields
