# Ask Sync Chat Implementation Plan

> **For agentic workers:** Load `executing-plans`. Use `subteam` after substantive tasks. Then `finishing`.

**Goal:** Delete submit/resume; Shell Ask = sync `run-ask` + single-flight.  
**Spec:** `docs/specs/2026-07-22-ask-sync-chat.md`  
**Architecture:** One blocking CLI path; no background job manifests; drop stays parallel.

---

## Files touched

| File | Action |
|------|--------|
| `.obsidian/plugins/furnace-product-shell/src/command_specs.js` | modify |
| `src/render_input.js`, `render_today.js`, `plugin_actions.js`, `plugin_run_pipeline.js`, `run_state.js`, `pending_runtime.js`, `pending_state.js`, `plugin.js`, `constants.js`, `bridge/runtime_client.js` | modify |
| rebuild `main.js` if repo has a build step | modify |
| `src/aiwiki/runner/background.py` | delete |
| `workflows_ask.py`, `workflows_ask_status.py`, `workflows.py`, `cli/parsers.py`, `cli/dispatch.py`, `app_shell/meta.py` | modify |
| `content/io.py`, `today_feed.py` | keep read filters; stop new writes |
| `vault/templates.py` | modify |
| `tests/test_llm_integration.py` | delete §8b |
| Product Shell Jest tests | modify |
| `PROGRESS.md`, `scripts/verify.sh` counts if needed | modify |

## Task 1: Product Shell sync ask + single-flight

**Depends on:** none

- [x] `buildAskCommandSpec`: always `run-ask`; remove `longRunning` / `backgroundSubmit`
- [x] Remove poller (`start/stop/updateLongRunningPoller`, timer fields)
- [x] Remove `backgroundSubmit` branch in `plugin_run_pipeline.js`; remove `buildProductShellBackgroundRunUpdates` if unused
- [x] Strip `jobId` / `longRunning` from pending retryArgs where only for background
- [x] Single-flight: before ask submit, if active ask pending → Notice + return; drop unaffected
- [x] Update i18n / progress copy away from「长程报告」
- [x] Fix Jest; rebuild `main.js` if required by repo
- [x] **Verify:** `bash scripts/verify.sh product-shell-static`

## Task 2: Delete Python submit/resume/background

**Depends on:** none（可与 Task 1 并行）

- [x] Delete `src/aiwiki/runner/background.py`
- [x] Remove `run_ask_submit` / `run_ask_resume` from workflows + CLI parsers/dispatch + re-exports + meta
- [x] Remove `_mark_run_ask_background_*` and callers; keep `_mark_run_ask_artifact_degraded`
- [x] Stop writing `background_*` / `background-pending` on new artifacts; **keep** read filters in `content/io.py` / `today_feed.py`
- [x] Delete llm-integration §8b (4 tests); adjust verify.sh count
- [x] **Verify:** `bash scripts/verify.sh llm-integration python-static`

## Task 3: Templates, docs, final gate

**Depends on:** Task 1, Task 2

- [x] `vault/templates.py`: `run-ask-submit` → `run-ask`
- [x] `PROGRESS.md` 记一笔
- [x] Acceptance goldens：去掉 `background_job_id`；W2 call#2 `prompt_hash` → `910f1f751261f40b`
- [x] Fix P0 single-flight self-block (`excludePendingId` + pre-push ask-only guard)
- [x] Dogfood：清 background-jobs + 骨架报告；同步 vault plugin `main.js`
- [x] **Final verify:** `bash scripts/verify.sh all`

## Out of scope

- Dogfood vault 文件清理
- 删除 read-side `background_status` 过滤
