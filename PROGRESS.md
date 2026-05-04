# 炼丹炉 Progress — Furnace 世代

> **结构 v2** (R68, 2026-05-04): PROGRESS.md 仅保留 Quick Index + 活跃 3 轮 + 改进方向指针。
> **PROGRESS.md 仍是当前任务状态唯一 SoT；archive/rounds/ 只是历史延伸。**
> 历史 round 详情：`archive/rounds/round-*.md` / `archive/rounds/p4-*.md`
> 机器索引：`archive/rounds/index.json`
> 切档历史：pre-Round 1 在 `archive/PROGRESS-pre-round1.md`（注意：里面也包含 Round 24/25 的早期记录，已重新落入 `archive/rounds/round-24.md` 和 `round-25.md`）

## SoT 引用

- 终局架构：`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md`
- 当前方向：`docs/Furnace Next Direction Post-P4.md`
- Active contract：`.codex/contracts/active.md`
- 改进清单：见本文件底部「改进方向」段

## Milestone Quick Index

| 世代 | Milestones | 状态 |
|---|---|---|
| **P4 Dogfood-driven** (2026-04-28) | P4-1a~1d, P4-2~6, P4-9, P4-11, P4-15 | ✅ 全部 done |
| **D 系列** (2026-04-30) | D-1~D-4 + D-3 R1 + D-4 v0/v1 | ✅ 全部 done |
| **P4-INV** (Round 57-59) | P4-INV-1~4 | ✅ 全部 done |
| **Post-R61 改进** (2026-05-03) | harness 增量升级 / QA review 启用 / plans-merge / **Round 62/63 UI Polish** | ✅ Round 62/63 done / 其余 🔄 |
| **Round 64-66 UX Earnest** (2026-05-03) | 文件命名去时间戳 / 拖放修复 / 面板精简 / L3 自动采纳 / 图谱锚点链接化 / 导航树简化 / ask 移除 | ✅ 全部 done |
| **Round 67 Auto-adopt Hardening** (2026-05-04) | judgment review / L3 audit / nightly aggregation / strict JSONL load | ✅ done (`6711efd`) |
| **Round 67.5 Acceptance Fixture Refresh** (2026-05-04) | M6.1b prompt_hash drift refresh / fixture helper 文档化 | ✅ done (`284f8af`) |
| **Round 68 Progress Slimming** (2026-05-04) | PROGRESS 三层瘦身 / rounds archive / index.json / stop_line_audit lint | ✅ done |

## 状态 — 当前活跃 3 轮

### Round 68 — PROGRESS Three-Layer Slimming + stop_line_audit Lint — 完成

- **目的**: `PROGRESS.md` 从 1537 行瘦身到 ≤250 行，只保留 Quick Index、活跃 3 轮和改进方向。
- **历史层**: 旧 round 详情迁移到 `archive/rounds/round-NN.md`，保留原始块语义。
- **机器层**: `archive/rounds/index.json` 提供 `round_id/title/status/commit/archived_path/tags` 最小 schema。
- **工具**: `scripts/extract_rounds.py` 负责批量切分与索引生成；R67/R67.5/R68 手工文件合并入索引。
- **Stop Lines**: 0 产品代码 / 0 fixture / 0 verify.sh 默认链路改动 / 0 review/apply/audit / 0 receipt schema。
- **验证目标**: 行数 ≤250、round 文件 ≥50、index rounds ≥50、spot-check 5 个文件、`bash scripts/verify.sh` 全绿。

### Round 67.5 — Acceptance Fixture Refresh — 完成 (commit 284f8af)

- 修复 R67 期间发现的 M6.1b 3 个 fixture `prompt_hash` drift。
- drift 原因是 prompt 历史漂移；与 R67 auto-adopt hardening 改动无关。
- 新增 dev tool `scripts/refresh_acceptance_fixture.py`，复用 `CapturingBackend` 与 `compute_prompt_hash`。
- 提取 helper 到 `tests/acceptance/case_runner.py`，并补充 `tests/fixtures/acceptance/M6.1b/README.md`。
- 验证：`bash scripts/verify.sh` all green（13 acceptance + unit + coverage ≥ 92% fail-under）+ oracle isolated qa-review PASS（零 finding）。
- Stop Lines：0 prompt builder / 0 ReplayBackend / 0 compute_prompt_hash / 0 expected goldens / 0 installer defaults。

### Round 69 — 候选方向（未启动）

- 候选 A：清理 `.obsidian/plugins/furnace-product-shell/` 历史遗留 untracked npm 文件（R68 lint 已暴露），决定保留/迁移/gitignore 边界。
- 候选 B：H5 runtime_history 双写一致性（R67 scope 外）。
- 候选 C：lint 接入 `closed_loop` 或 verify 的可选 gate（基于 R68 第一版误报率数据）。
- 候选 D：`stop_line_audit` 关键词白名单扩展 / `unrecognized` 转 strict 模式。
- 启动条件：选定方向后写 `.codex/contracts/active.md`，本块替换为对应 in-progress 摘要。

## 改进方向

- **H5 runtime_history 双写一致性**: R67 明确 scope 外；后续需统一 runtime history 写入路径与一致性验证。
- **semantic candidate/adoption 产品化**: L1/L2/L3 候选生成、显式采纳、receipt、revert 与 backlog closure 仍需长期稳定闭环。
- **review-queue closure**: 继续降低反证候选、judgment review、machine memory actions 等积压，并让 metrics 稳定反映 closure rate。
- **多周自然运行**: watcher/nightly/LLM worker 已具备基础闭环，但仍需多周 dogfood 数据证明无人值守稳定性。
- **investing 实战输入**: 真实投资研报 PDF、多轮追问、复审产品化仍是 P4-INV 后续候选。
- **UI/产品面剩余项**: 生产级通知验证、大规模知识库下图谱性能、生态/GUI 细节继续打磨。
- **工程债候选**: `build.sh` dead modules、`app.json` merge、relative path、`node --check` gate、`app_*.py` 巨石拆分。
- **stop_line_audit 扩展**: R68 第一版只做独立 lint；未来可按误报率和覆盖率决定是否接入更强 gate。

---

> 更早的 round 详情请参考 `archive/rounds/round-*.md` / `archive/rounds/p4-*.md`，或读 `archive/rounds/index.json`。
