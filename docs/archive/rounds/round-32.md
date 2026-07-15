# Round 32 — Sensitive Note Guard + Batch E Semantic Navigation Dogfood

status: 完成
commit: 

Round 32 — Sensitive Note Guard + Batch E Semantic Navigation Dogfood — 完成
- **目的**: 修复 Round 31 暴露的直接问题：默认 note 投料缺少敏感内容预检、Product Shell / 文档 / smoke 路径仍推动 deprecated `drop-note`；随后继续 `/home/tim/danlu/炼丹炉` 试运行，投入 eva_robot Batch E 证据并评估炼丹炉是否达到最终形态
- **代码与入口修复**:
  - `drop note` / legacy `drop-note` 现在默认在写入 `raw/inbox` 前扫描明显 credential field、token/key/password 字段和 private key block；命中时抛出 `SensitiveContentError`，错误只暴露行号与 finding kind，不回显敏感值
  - 新增 `--allow-sensitive` 显式 override，用于有意的 local-only secret vault；默认 runtime 不做隐式降级
  - README、new-vault README、Product Shell source/build artifact 和 `scripts/product_shell_smoke.sh` 默认入口改为 `drop note` / `drop url` / `drop pdf` / `drop image` / `drop repo`
  - Product Shell runtime 调用已改为 `["drop", "note" ...]`、`["drop", "url" ...]`、`["drop", "pdf" ...]`、`["drop", "image" ...]`、`["drop", "repo" ...]`；legacy command 仅保留 CLI 兼容测试
- **监控状态**:
  - 投料前确认 `aiwiki-watch.service` active，实际命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-04-30 00:00:00 CST`
  - 为遵守 single-writer，Batch E 手工投料与 worker 写入期间短暂停止 watcher；闭环结束后已恢复 active running
- **敏感内容负向探针**:
  - `/home/tim/eva_robot/LIte3_Audit_Report.md` 使用默认 `drop note` 被拒绝，错误为 line 18 / line 19 `credential-field`
  - 该探针在 raw 写入前失败，未把敏感报告投入 dogfood vault
  - 当前 guard 覆盖 `drop note` / legacy `drop-note`；直接手工复制到 `raw/inbox` 或其他 ingest 类型仍是后续统一治理项
- **Batch E 投料**:
  - `/home/tim/eva_robot/Robot-lite-V3.0/archive/v3.3.3_nav2_debug_retrospective.md`
  - `/home/tim/eva_robot/Robot-lite-V3.0/archive/v3.3.3_M1_semantic_nav_report.md`
  - `/home/tim/eva_robot/Robot-lite-V3.0/archive/v3.3.3_nav_optimization_roadmap.md`
  - 编译后 source sample 29 → 32；首轮 compile changed_pages=55，新增概念包括 `nav2`、`nav`、`semantic`、`odom`、`target`
  - 最终 compile 清洁复用 machine memory core，sources=32，concepts=30，drift_warnings=[]
- **LLM worker 评估**:
  - `llm-check --probe-all` + `AIWIKI_LLM_BACKEND=codex-cli` / `AIWIKI_LLM_MODEL=gpt-5.5`: `codex-cli/gpt-5.5` OK，probe 约 4.55s；`copilot-cli` 20s timeout；`claude-cli` 因组织权限不可用
  - `run-ask --lean --timeout 240 --fallback-to-ask` 成功，`delivery_mode=llm`、`fallback_used=false`
  - LLM 报告写入 `output/reports/query-20260429-152929-eva-robot-batch-e-nav2-debug-retrospective-m1-se.md`
  - 该报告已 file-back 为 `wiki/judgments/judgment-20260429-153205-eva-robot-batch-e-semantic-navigation-assessment.md`，状态 confirmed
- **闭环结果**:
  - `dogfood-receipt-v5.md` 已写入 `output/reports/`，并 file-back 到 `wiki/judgments/judgment-20260429-153304-dogfood-receipt-v5-batch-e-guarded-note-ingest-s.md`，状态 confirmed
  - 最终 `metrics`: `provenance_completeness=1.0`、`stale_ratio=0.0`、`review_closure_rate=1.0`、`proposal_acceptance_rate=1.0`、`judgment_revisit_rate=0.5`、`output_file_back_rate=0.8333`、`elixir_reuse_count=1`
  - `review-queue` total=37；主要剩余项是 `machine_memory_actions=15`、concept backlog=9、counter-evidence/judgment review=9；这是真实治理债，不在本轮自动接受
  - `today` 已显示 Batch E LLM 报告与 `dogfood-receipt-v5.md`
- **eva_robot 评估结论**:
  - 已解决或显著收敛：Go2 运动前置链、Nav2→Go2 控制链、MPPI+Omni 算力/控制风险、Nvblox hard-mode 复杂度、HMSG→VLM→standoff→Nav2→GaitAdapter→Go2 的 M1 端到端路径
  - 仍阻塞 cold/warm map-frame 验收：冷启动空 HMSG 自动发现是否稳定、温启动 posegraph+HMSG replay 是否稳定、map→odom 重启后一致性、到达后是否可见语义目标、HMSG 坐标是否跨 session 有效
  - 下一步最小验证闭环：reset posegraph/HMSG，发现 3-5 个静态物体，同 session 导航到一个目标，保存 posegraph+HMSG，重启 perception/brain，温启动导航到同一目标，对比 map 坐标漂移、Nav2 result、VLM visible 和 HMSG confidence
- **炼丹炉最终形态评估**:
  - 已达到可信 local-first research dogfood runtime：guarded note ingest、monitoring baseline、deterministic compile、metrics/review、LLM synthesis、output file-back、review lifecycle 均可真实运行
  - 尚未达到最终形态：敏感输入治理只覆盖 note 路径，Product Shell 仍不是完全隐藏机械结构的终局壳，LLM 后端在本机实际单一，ranking 对最新证据仍有权重债，概念治理 backlog 随真实使用增长，planner/heavy-light/judge/distill/propose 自动化仍需显式 gate
  - 当前阶段应定义为 controlled-runtime，而非 final-form product/agent system
- **验证**:
  - focused sensitive ingest tests pass，且 `PYTHONWARNINGS=error::DeprecationWarning` 下通过
  - focused CLI dispatch tests pass；vault README/Product Shell smoke related tests pass；`node --check .obsidian/plugins/furnace-product-shell/main.js` pass；`bash -n scripts/product_shell_smoke.sh` pass
  - `bash scripts/verify.sh` exit 0；1512 unit + 13 acceptance；coverage 92%
