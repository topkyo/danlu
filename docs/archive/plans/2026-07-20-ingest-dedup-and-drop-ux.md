# Ingest Dedup and Drop UX — Implementation Plan

> **For agentic workers:** Load `executing-plans` (4 tasks). Tasks 1 and 3 are independent (parallel worktrees OK). Task 2 depends on Task 1. Task 4 depends on 2+3. Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** URL 投料幂等复用（`--refresh` 才重抓）+ Product Shell 纯投料「已收料」语义，消除「等报告 / 生成被阻断」误导。  
**Spec:** `docs/specs/2026-07-20-ingest-dedup-and-drop-ux.md`  
**Architecture:** `normalize_ingest_url` + manifest 查找短路写盘；Shell 按 `retryArgs.kind` 分流 pending 文案与 reconcile。  
**Tech stack:** Python 3.10+ stdlib, Product Shell JS/Jest, `bash scripts/verify.sh`

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `src/aiwiki/drop/ingest_identity.py` | create | `normalize_ingest_url` + `find_manifest_entry_by_ingest_url` |
| `src/aiwiki/drop/url.py` | modify | 写盘前幂等；`--refresh` 覆盖同 path |
| `src/aiwiki/executor.py` | modify | `fetch_raw` 同样短路 / refresh |
| `src/aiwiki/cli/parsers.py` | modify | `drop url` / `drop plan` 加 `--refresh` |
| `src/aiwiki/cli/dispatch.py` | modify | 把 `refresh` 传入 drop/plan handlers |
| `tests/test_llm_integration.py` | modify | 幂等 / GitHub 双形态 / refresh 用例 |
| `.obsidian/plugins/furnace-product-shell/src/render_input.js` | modify | 纯投料不 `markPendingSubmissionReceived` |
| `.obsidian/plugins/furnace-product-shell/src/render_today.js` | modify | 文案分流；失败「投料失败」 |
| `.obsidian/plugins/furnace-product-shell/src/pending_state.js` | modify | reconcile 按 kind 限域 |
| `.obsidian/plugins/furnace-product-shell/src/today_feed.js` | modify | raw 卡「已收料」 |
| `.obsidian/plugins/furnace-product-shell/src/constants.js` | modify | 新文案键 |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | `bash .obsidian/plugins/furnace-product-shell/build.sh`（或仓库既有 build 入口） |
| `src/aiwiki/today_feed.py` | modify | Python feed 文案与 JS 对齐 |
| Jest tests under `src/__tests__/` | modify | 锁定纯投料 / 提问分流 |
| `CHANGELOG.md` / `PROGRESS.md` / `docs/USER_GUIDE.md`（一句） | modify | SoT 同步 |
| `scripts/verify.sh` | modify | 仅当 llm 计数变化时更新 help 文案 |

---

## Task 1: URL 规范化 + manifest 查找

**Depends on:** none

**Files:**
- Create: `src/aiwiki/drop/ingest_identity.py`
- Modify: none yet (pure library)

- [ ] **Step 1:** 实现 `normalize_ingest_url(url: str) -> str | None`：
  - 非 http(s) → `None`
  - `urlparse`；scheme/host 小写；去 fragment
  - 去掉常见 tracking query：`utm_*`, `fbclid`, `gclid`, `ref`, `source`（保留其它 query）
  - 若 `rewrite_github_raw_url(url)` 非空 → 规范化 **rewrite 结果**（保证 `github.com/o/r` ≡ `raw.githubusercontent.com/o/r/HEAD/README.md`）
  - 否则规范化原 URL（无尾斜杠，path 保留大小写除 host）
- [ ] **Step 2:** 实现 `find_manifest_entry_by_ingest_url(root: Path, url: str) -> dict | None`：
  - `load_manifest(root)`
  - 对每个 entry 收集候选字符串：`original_path`、`ingest_metadata.original_payload`、`ingest_metadata.targets[]`、常见 `final_url` / `original_url` 字段（按现有 drop_url / fetch_raw 实际写入键）
  - 任一候选 `normalize_ingest_url` 后等于目标 key → 返回该 entry
- [ ] **Step 3:** 单元级断言放进 `tests/test_llm_integration.py` 的轻量函数测（无需 vault IO）：`github.com/34306/vphone-aio` 与对应 raw README normalize 后相等。
- [ ] **Verify:** `PYTHONPATH=src python3 -m pytest tests/test_llm_integration.py -k 'normalize_ingest or ingest_identity' -q`（本步先加 normalize 测）；`bash scripts/verify.sh python-static`

**Commit:** `feat(drop): normalize ingest URL identity for dedup`

---

## Task 2: drop_url / fetch_raw 幂等短路 + `--refresh`

**Depends on:** Task 1 (ingest_identity API)

**Files:**
- Modify: `src/aiwiki/drop/url.py` — `drop_url(..., refresh: bool = False)`
- Modify: `src/aiwiki/executor.py` — `_execute_fetch_raw` / `execute_plan` 接受 refresh；`drop_url` 委托传 refresh
- Modify: `src/aiwiki/cli/parsers.py` — `_configure_drop_url_parser` / `_configure_drop_plan_parser` 加 `--refresh`
- Modify: `src/aiwiki/cli/dispatch.py` — `_handle_drop` / `_handle_drop_plan` 传 `refresh=bool(getattr(args, "refresh", False))`
- Modify: `tests/test_llm_integration.py`

- [ ] **Step 1:** `drop_url` 在 `_collect_url` **之前**（或 collect 前）：若 `not refresh` 且 `find_manifest_entry_by_ingest_url` 命中且 `stored_path` 文件存在 → 返回既有 payload，附加 `reused: True`、`duplicate_of: entry["id"]`、`path`/`stored_path`；**不** fetch、**不** `_unique_path`。
- [ ] **Step 2:** `refresh=True` 且命中：fetch 后写入 **同一** `stored_path`（覆盖），更新 manifest 同 id 的 sha/metadata；返回 `reused: False`、`refreshed: True`。
- [ ] **Step 3:** `_execute_fetch_raw`：对 `original_payload` 与 `plan.targets[0]` 做同样 lookup；命中且不 refresh → 短路；refresh → 覆盖已有 note。
- [ ] **Step 4:** CLI `--refresh` 接到 url 与 plan；`execute_plan(..., refresh=...)`。
- [ ] **Step 5:** 集成测（tmp_path + stub fetch 或预置 manifest+inbox 文件）：
  1. 两次 drop 同 URL → inbox 仅 1 文件，第二次 `reused is True`
  2. github 根 URL 与 raw README 互查命中
  3. `--refresh` 后仍 1 文件，`refreshed is True`，无 `-2`
- [ ] **Verify:** `PYTHONPATH=src python3 -m pytest tests/test_llm_integration.py -k 'ingest_dedup or normalize_ingest or refresh' -q`；`bash scripts/verify.sh python-static llm-integration`

**Commit:** `feat(drop): idempotent URL ingest with --refresh`

---

## Task 3: Product Shell 纯投料语义（可与 Task 1 并行）

**Depends on:** none

**Files:**
- Modify: `.obsidian/plugins/furnace-product-shell/src/render_input.js`
- Modify: `.obsidian/plugins/furnace-product-shell/src/render_today.js`
- Modify: `.obsidian/plugins/furnace-product-shell/src/pending_state.js`（及/或 `pending_runtime.js`）
- Modify: `.obsidian/plugins/furnace-product-shell/src/today_feed.js`
- Modify: `.obsidian/plugins/furnace-product-shell/src/constants.js`
- Modify: `src/aiwiki/today_feed.py`
- Modify: Jest under `.obsidian/plugins/furnace-product-shell/src/__tests__/`
- Rebuild: `main.js` via 现有 `build.sh`

- [ ] **Step 1:** `render_input.js`：纯投料成功路径只 `completePendingMaterialDrop`；**不要**再对同一 pendingId 调 `markPendingSubmissionReceived`。提问 / auto-ask 路径保留 received。
- [ ] **Step 2:** `pendingSubmissionStageLabel` / 失败卡：若 `retryArgs.kind` 为 `material`/`files` 且无 ask → 失败标题「投料失败」；成功 done(raw)「已收料」。`reused` 时副文「已存在，未重复入库」（读 CLI JSON 字段若已有）。
- [ ] **Step 3:** reconcile：material/files 无 question → candidate 源仅 `recent_raw_inputs`（+ receipts 可选）；禁止 outputs-first 误配。
- [ ] **Step 4:** Today feed raw summary →「已收料」类表述（JS + `today_feed.py` 对齐）。
- [ ] **Step 5:** placeholder/hint 拆开投料 vs 提问；Jest：纯 URL 投料不出现「排队生成报告」；提问路径仍可出现报告文案。
- [ ] **Step 6:** 跑 build 更新 `main.js`。
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`

**Commit:** `fix(shell): drop success is 已收料, not waiting for report`

---

## Task 4: Docs + final verify

**Depends on:** Task 2 (commit), Task 3 (commit)

**Files:**
- Modify: `CHANGELOG.md`, `PROGRESS.md`
- Modify: `docs/USER_GUIDE.md` — 一句：同 URL 默认不重复入库；`--refresh` 重抓；纯投料不出报告
- Modify: `scripts/verify.sh` — 仅当 llm-integration 计数变化时更新

- [ ] **Step 1:** 文档与 CHANGELOG Unreleased。
- [ ] **Step 2:** Final verify: `bash scripts/verify.sh all` — expect acceptance 25 + llm-integration（新计数）+ Jest 全绿。
- [ ] **Commit:** `docs: ingest dedup and drop UX notes`

---

## Final verify

```bash
bash scripts/verify.sh all
```

Expect: scripts + product-shell-static + cli-smoke + smoke + python-static + acceptance (25) + llm-integration（含本轮新测）PASS。

---

## Out of scope (do not implement)

- 清理历史 `vphone-aio-2/3/4`
- content-sha 去重；本地 `drop repo` 目录幂等
- Shell「强制重抓」按钮
- 改变材料+问题 auto-ask
