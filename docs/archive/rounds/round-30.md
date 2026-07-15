# Round 30 — Eva Robot Batch C Dogfood + LLM Worker Assessment

status: 完成
commit: 

Round 30 — Eva Robot Batch C Dogfood + LLM Worker Assessment — 完成
- **目的**: 继续把 eva_robot 先前准备分批进入炼丹炉的设计/实施/部署文档投入 dogfood vault，并验证 Round 29 后 watcher deterministic ingest 与受控 LLM worker 的分工是否成立
- **监控状态**:
  - 投料前确认 `aiwiki-watch.service` active，实际命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-04-30 00:00:00 CST`
  - 为遵守 single-writer，Batch C 手工投料期间短暂停止 watcher；闭环结束后已恢复 active
- **Batch C 投料**:
  - `/home/tim/eva_robot/.worktrees/v3.6/docs/plans/2026-03-15-v3.6-implementation.md`
  - `/home/tim/eva_robot/.worktrees/v3.6/docs/plans/2026-03-23-li-init-integration-plan.md`
  - `/home/tim/eva_robot/.worktrees/v3.6/docs/plans/2026-03-24-stage-review-and-progress.md`
  - `/home/tim/eva_robot/.worktrees/v3.6/docs/plans/fastlio-fork-contract.md`
  - `/home/tim/eva_robot/deployment/jetson/README.md`
  - 编译后 source sample 18 → 23；新增 Batch C source page 均保留 `source_files` / `source_sha256`，Summary 保留 `Pending LLM summary` 并带 deterministic preview
- **LLM worker 评估**:
  - `llm-check --probe-all`: `codex-cli/gpt-5.5` OK，probe 约 6.7s；`copilot-cli` 20s timeout；`claude-cli` 因组织权限不可用；`nvidia-nim-api` endpoint 404
  - `run-ask --lean --timeout 240 --fallback-to-ask` 成功，`delivery_mode=llm`、`fallback_used=false`
  - LLM 报告写入 `output/reports/query-20260429-141548-eva-robot-batch-c-v3-6-lidar-imu-init-fast-lio2-.md`
  - 该报告已 file-back 为 `wiki/judgments/judgment-20260429-141818-eva-robot-batch-c.md`，状态 confirmed
- **闭环结果**:
  - `dogfood-receipt-v3.md` 已写入 `output/reports/`，并 file-back 到 `wiki/judgments/judgment-20260429-141919-dogfood-receipt-v3-eva-robot-batch-c.md`，状态 confirmed
  - 最终 `metrics --json`: `provenance_completeness=1.0`、`stale_ratio=0.0`、`review_closure_rate=1.0`、`proposal_acceptance_rate=1.0`、`judgment_revisit_rate=0.5`、`output_file_back_rate=0.75`、`elixir_reuse_count=1`
  - `judgment_revisit_rate` 下降是新增 Batch C judgment 和 receipt judgment 只有初次确认、尚无后续 revisit 的真实生命周期信号
  - `review-queue --json` total=29；其中 `machine_memory_actions=15`，主要是 `Eva` / `Robot` / `Lio2` 等过载/桥接概念治理
- **eva_robot 评估结论**:
  - Batch C 强化而不是推翻 hybrid 路线：FAST-LIO2 仍应作为几何主链和 canonical `odom` 来源
  - LiDAR_IMU_Init 当前只能作为离线/半在线标定工具；三次不收敛前不应回填 FAST-LIO runtime config，也不应成为运行主链 gate
  - 语义导航应收窄为 Semantic Resident Mode 下的 session-local 局部语义导航；不应继续暗示跨 session 持久语义地图已成立
  - cuVSLAM 近期应保持 diagnostic / special-mode，不进入默认常驻
  - Jetson Orin NX 16GB、ROS1/ROS2 隔离、D435i USB 直连、timestamp discipline、FAST-LIO 坏态恢复都是架构约束，不是部署细节
  - 下一步最小验证闭环：startup gate、静止 odom 稳定、重复 1m 前进、方向扰动、局部语义目标、FAST-LIO 坏态恢复
- **当前评估**: 炼丹炉已经能完成真实 `raw -> compile -> LLM synthesis -> output -> file-back -> review` 闭环；watcher 默认 deterministic-only 是正确运行边界，LLM 并未关闭，而是应留在 `run-ask` / `run-compile` / `run-nightly` worker 路径。薄弱点收敛为大上下文耗时、可用后端单一、concept governance backlog、`drop-note` deprecation 体验债。
