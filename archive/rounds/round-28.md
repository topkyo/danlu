# Round 28 — Dogfood Eva Robot Batch B + Monitoring Closed Loop

status: 完成
commit: 

Round 28 — Dogfood Eva Robot Batch B + Monitoring Closed Loop — 完成
- **目的**: 开启炼丹炉 dogfood vault 监控，继续投入 eva_robot 先前准备的增量设计文档，并用真实投料暴露 runtime、LLM、metrics、review 与文档回写状态
- **入口修复**:
  - `scripts/run_watch.sh` / `scripts/run_nightly.sh` / `scripts/aiwiki-launcher.sh` 改为默认项目根，但存在 `AIWIKI_VAULT` 时指向目标 vault；避免 systemd 和 repo launcher 误写 `/home/tim/ai-wiki`
  - `scripts/run_nightly.sh` 补执行位，修复 user systemd `status=203/EXEC`
  - 本机 `/home/tim/.config/aiwiki/aiwiki-watch.env` 与 `aiwiki-nightly.env` 已指向 `AIWIKI_VAULT=/home/tim/danlu/炼丹炉`
- **监控状态**:
  - `aiwiki-watch.service` 已启动，实际命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch ... --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-04-30 00:00:00 CST`
  - 首次 LLM watcher probe 在 30s 超时，120s 后 fallback deterministic；为遵守 single-writer 和避免常驻 LLM 子进程占用，watcher 已切为 deterministic-only
- **Batch B 投料**:
  - `/home/tim/eva_robot/docs/plans/2026-03-11-fast-lio2-integration.md`
  - `/home/tim/eva_robot/docs/plans/2026-03-11-navigation-capability-ceiling-analysis.md`
  - `/home/tim/eva_robot/docs/plans/Robot-lite_V3.3.4_VLM深度激活方案.md`
  - 编译后新增 3 个 source page：`discovered-20260429131222-eva-robot-batch-b-fast-lio2`、`discovered-20260429131222-eva-robot-batch-b`、`discovered-20260429131222-eva-robot-batch-b-robot-lite-v3-3-4-vlm`
- **闭环结果**:
  - `metrics --json`: source sample 15 → 18；`provenance_completeness=1.0`、`stale_ratio=0.0`、`review_closure_rate=1.0`、`proposal_acceptance_rate=1.0`、`judgment_revisit_rate=1.0`、`elixir_reuse_count=1`
  - `output_file_back_rate=0.6667`，原因是 `run-ask --lean --timeout 180` 对大上下文超时后生成了低价值 deterministic skeleton report；本轮不把该 fallback 报告强行 file-back
  - `dogfood-receipt-v2.md` 已写入 `output/reports/`，并 file-back 到 `wiki/judgments/judgment-20260429-132055-dogfood-receipt-v2-eva-robot-batch-b.md`，状态 confirmed
- **eva_robot 评估结论**:
  - V3.6 不应继续表述为“纯无图语义导航替代 SLAM”；更稳妥定位是 hybrid：FAST-LIO2/回环承担几何一致性，HMSG/HSTG/VLM 承担语义搜索和决策节点判断
  - 关键缺口顺序：长时间导航缺回环检测；目标未知时缺主动探索策略；V3.3.3 已写好的 VLM 管道未接入主链路
  - 下一步最小验证闭环：FAST-LIO2 vs FAST-LIO2+loop closure drift bench；V3.3.4 Phase A 只接 ContextManager/reasoning；语义前沿探索先跑 classic frontier baseline 再接 BGE/VLM 评分
- **验证**:
  - focused script tests: `PYTHONPATH=src python3 -m pytest tests/test_app.py -k 'run_watch_script or run_nightly_script or aiwiki_launcher_script'`，3/3
  - `llm-check --probe-all`: `codex-cli/gpt-5.5` 单独探测 OK，12.2s；但大 corpus synthesis 仍会 180s timeout
  - `bash scripts/verify.sh` exit 0；1506 unit + 13 acceptance；coverage 92%
- **当前评估**: 炼丹炉 file-based ingestion、provenance、deterministic compile、metrics、review 和 systemd baseline 可用；真正薄弱点是大上下文 LLM synthesis、常驻 watcher 的 LLM 默认策略，以及 Batch label / 泛词进入 concept graph 的治理噪声
