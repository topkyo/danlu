# Ask Sync Follow-ups Implementation Plan

> **For agentic workers:** Load `executing-plans`. Then `finishing`.

**Goal:** 收口 Ask sync-chat 后的 4 项：dogfood 体感、删读侧 background 过滤 + jobId、sync ask 软提示、对齐 Go-Live SoT。  
**Parent commit:** `312e702`  
**Architecture:** 不恢复 background/submit/resume；只做同步 ask 卫生与 UX。

---

## Task 1: Dogfood 体感基线

**Depends on:** none  
**Files:** vault ops only（iCloud 炼丹炉）；写报告到 `/tmp/ask-dogfood-baseline.md`

- [x] 确认 vault 无 `background_status ∈ {submitted,running}`（已预检：reports 无；仅 `分析下内容-2` 为 `completed`）
- [x] 用 launcher 对 vault 跑：短 ask → 第二 ask 应被 Shell 单飞挡住（若仅 CLI 则串行两次记耗时）→ 中途 `drop` 投料仍成功
- [x] 记录每次 wall time、exit、产物路径、是否 degraded
- [x] 勿打印 API key；无凭据则 BLOCKED 并写清缺什么

**Verify:** 报告文件存在且含耗时表

## Task 2: 清读侧 background 过滤 + 去掉 jobId

**Depends on:** Task 1 vault 确认（或预检已通过）  
**Files:** `src/aiwiki/content/io.py`, `src/aiwiki/today_feed.py`, `.obsidian/plugins/furnace-product-shell/src/today_feed.js`, `pending_state.js`, 相关 Jest/tests；rebuild `main.js`

- [x] 删除对 `background_status ∈ {submitted,running}` 的隐藏/跳过逻辑（Python + Shell today_feed）
- [x] 评估：`background-pending` / `llm_status=pending` 骨架是否仍需过滤——若仅历史 submit 产物，一并收紧或删除；保留 `degraded`/`llm-failed` 展示逻辑
- [x] `workflows_ask_context.py` 若仅 scrub prompt 字段可保留
- [x] 去掉 pending schema 的 `jobId`（serialize/hydrate/create/reset/tests）
- [x] vault：可从 `分析下内容-2.md` frontmatter 去掉已无用的 `background_*`（可选，dogfood）
- [x] **Verify:** `bash scripts/verify.sh product-shell-static python-static acceptance`

## Task 3: Sync ask UX 软提示

**Depends on:** none（可与 Task 2 并行，避免同文件冲突；若冲突则等 Task 2）  
**Files:** `render_today.js`, `constants.js`（i18n）, Jest；rebuild `main.js`

- [x] `running`/`received` ask 卡：超过 ~15s 显示「仍在生成，请稍候」类软提示（不引入 longRunning/poller/jobId）
- [x] 确认 failed/degraded 重试按钮仍走 `run-ask` + `excludePendingId`
- [x] **Verify:** `bash scripts/verify.sh product-shell-static`

## Task 4: 对齐 Post-Cleanup / Go-Live SoT

**Depends on:** none  
**Files:** `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`, `PROGRESS.md`（必要时 `docs/README.md` Active 一句）

- [x] 记一笔：`run-ask-submit/resume` + `background.py` 已退役（Ask sync-chat）
- [x] 刷新过期计数（acceptance/Jest）若本文件快照仍写旧值
- [x] 明确下一步仍是 WS 商业化/打磨，不扩后台任务
- [x] **Verify:** `bash scripts/docs_consistency_check.sh`（若触及）或人工 diff 自检

## Out of scope

- 恢复任何 background job
- push / PyPI / EULA 法律签收
- CHANGELOG 历史行改写
