# Round 31 — Dogfood Monitoring + Batch D Runtime Evidence + Final-shape Assessment

status: 完成
commit: 

Round 31 — Dogfood Monitoring + Batch D Runtime Evidence + Final-shape Assessment — 完成
- **目的**: 按用户要求开启/确认监控，继续 `/home/tim/danlu/炼丹炉` 试运行，投入 eva_robot 运行证据并评估炼丹炉当前状态、功能完整度和是否达到终局形态
- **监控状态**:
  - 投料前确认 `aiwiki-watch.service` active，实际命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-04-30 00:00:00 CST`
  - 为遵守 single-writer，Batch D 手工投料与 worker 写入期间短暂停止 watcher；闭环结束后已恢复 active
- **Batch D 投料**:
  - `/home/tim/eva_robot/Robot-lite-V3.0/v3.3.3_phase3B_progress_report.md`
  - `/home/tim/eva_robot/Robot-lite-V3.0/v3.3.3_phase3B_map_frame_plan.md`
  - `/home/tim/eva_robot/nav_test_log.md`
  - `/home/tim/eva_robot/probe_plan.md`
  - `/home/tim/eva_robot/probe_notes.md`
  - `/home/tim/eva_robot/Go2_Audit_Report.md`
  - 明确排除含凭据文件：`/home/tim/eva_robot/LIte3_Audit_Report.md`、`/home/tim/eva_robot/jetson_开发环境.md`
  - 编译后 source sample 23 → 29；新增 Batch D source page 均保留 `source_files` / `source_sha256`，Summary 保留 `Pending LLM summary` 与 deterministic preview
- **LLM worker 评估**:
  - 未设置 backend 时 `llm-check --probe-all` 正确 fail-fast，符合显式 backend 约束
  - `llm-check --probe-all` + `AIWIKI_LLM_BACKEND=codex-cli` / `AIWIKI_LLM_MODEL=gpt-5.5`: `codex-cli/gpt-5.5` OK，probe 约 9.1s；`copilot-cli` 20s timeout；`claude-cli` 因组织权限不可用
  - `run-ask --lean --timeout 240 --fallback-to-ask` 成功，`delivery_mode=llm`、`fallback_used=false`
  - LLM 报告写入 `output/reports/query-20260429-150804-eva-robot-batch-d-phase-3b-map-frame-hmsg-probe-.md`
  - 该报告已 file-back 为 `wiki/judgments/judgment-20260429-151034-eva-robot-batch-d-runtime-evidence-assessment.md`，状态 confirmed
- **闭环结果**:
  - `dogfood-receipt-v4.md` 已写入 `output/reports/`，并 file-back 到 `wiki/judgments/judgment-20260429-151143-dogfood-receipt-v4-batch-d-runtime-evidence-fina.md`，状态 confirmed
  - 最终 `metrics --json`: `provenance_completeness=1.0`、`stale_ratio=0.0`、`review_closure_rate=1.0`、`proposal_acceptance_rate=1.0`、`judgment_revisit_rate=0.3333`、`output_file_back_rate=0.8`、`elixir_reuse_count=1`
  - `review-queue --json` total=33；主要增长来自 Batch D 后的 concept backlog、judgment review actions 与反证候选；`machine_memory_actions=15` 仍是主要治理债
  - `today --json` 已显示 Batch D LLM 报告与 `dogfood-receipt-v4.md`
- **eva_robot 评估结论**:
  - `map frame + Nav2 + DWB + HMSG` 已有真实运行证据，不再只是纸面路线
  - Phase 3B 不应表述为完全验收；更准确边界是同 session 链路可跑，跨 session map/HMSG/posegraph 一致性仍未证明
  - HMSG 坐标必须绑定 posegraph/map fingerprint，否则旧 checkpoint 会把 Fast Path 导向不可达目标
  - FAST-LIO2 应继续 defer，直到 Go2 DDS timestamp discipline 与 canonical `/odom` 通过 gate
  - 下一步最小验证闭环是单物体 cold/warm 重启：发现静态目标、同 session 导航成功、保存 HMSG + posegraph、重启、校验 fingerprint、再次导航
- **炼丹炉最终形态评估**:
  - 已达到“可用 dogfood runtime”：`raw -> compile -> wiki -> metrics/review -> LLM synthesis -> output -> file-back -> review` 闭环真实成立，monitoring baseline 可运行
  - 尚未达到最终形态：Product Shell/CLI 仍泄漏 operator 语汇，`drop-note` deprecation 仍在 dogfood 路径，最新证据在 top ranked sources 中权重不足，概念治理 backlog 增长，默认缺少敏感输入预检，可用 LLM backend 单一且大上下文耗时
  - 当前阶段应定义为 strong controlled-runtime，而非 final-form agent/product
- **验证**:
  - `bash scripts/verify.sh` exit 0；1508 unit + 13 acceptance；coverage 92%
