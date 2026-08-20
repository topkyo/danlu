# Ask Sync Chat（删除 submit/resume）

**Date:** 2026-07-22  
**Status:** approved (chat)  
**Owner:** Product Shell + runtime ask

## Goal

炼丹炉 Ask 与 LLM chat 对齐：**一问一答、同步阻塞、单飞**。删除 `run-ask-submit` / `run-ask-resume` 与 background-jobs 子系统，去掉骨架 pending、poller、env 分裂等故障面。

## Decisions

1. **默认路径**：Product Shell 提问一律 `advanced run-ask`（经 launcher，阻塞至完成）。
2. **单飞**：存在进行中的 ask（pending `running`/`received` 且为提问类）时，拒绝新提问并 Notice；**drop 投料仍允许**。
3. **删除**：CLI `run-ask-submit` / `run-ask-resume`、`runner/background.py`、Shell `longRunning`/`backgroundSubmit`/longRunning poller/`jobId`。
4. **保留**：同步 `run-ask`、`_mark_run_ask_artifact_degraded`、`pending_submissions`（投料与同步 ask 卡片）、`shell-status`、对历史 `background_status ∈ {submitted,running}` 的 **读侧过滤**（dogfood 僵尸兼容）。
5. **非本轮**：改 iCloud dogfood vault 文件；删除读侧 `background_*` 过滤（vault 清干净后另开）；pending UX 大重构。

## Success criteria

- Shell 提问不再出现「长程报告生成中 / 已接收后台任务」。
- 无新写入 `background_job_id` / `background-pending` / `.aiwiki/state/background-jobs/`。
- `bash scripts/verify.sh product-shell-static llm-integration` PASS；建议再跑 `all`。
- vault 模板与 USER_GUIDE 均只教 `run-ask`。

## Non-goals

- 关 Obsidian 后继续生成（不做 detach worker）。
- 删 `pending_submissions` 整套。
- 改 alchemy / watch / drop 语义。
