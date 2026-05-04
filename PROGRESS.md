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
| **Round 68 Progress Slimming** (2026-05-04) | PROGRESS 三层瘦身 / rounds archive / index.json / stop_line_audit lint | ✅ done (`2c408f9`) |
| **Round 69 Atomic State I/O Foundation** (2026-05-04) | atomic_write_text + atomic_append_jsonl helpers / 4 saver 替换 / 21 unit tests / R69.5 fixture refresh 归并 | ✅ done (`7ee3ab8`) |
| **Round 70 Receipt JSONL 事务化 + Revert 双 receipt** (2026-05-04) | 12 JSONL writers 全量原子化 / atomic_append_line 原语 / machine_memory revert 双 receipt + reverts/ 子目录 / receipt_path override / mock seam 清除 / R70.5 fixture refresh 归并 | ✅ done (`950f291`) |
| **Round 71 Fetch & Path 安全** (2026-05-04) | safe_fetch + safe_resolve_within helpers / drop.py SSRF (private IP 表 + IPv4-mapped + redirect 复检) / 越界检查 / repo symlink 跳过 / Playwright page.route subresource 拦截 / 22 安全测试 | ✅ done (`a6074b9`) |

## 状态 — 当前活跃 3 轮

### Round 71 — Fetch & Path 安全 (drop.py SSRF + 越界 + symlink) — 完成 (commit a6074b9)

- **目的**：为 drop.py URL fetch / 本地 path / repo ingest 三类入口建立统一安全边界，阻断 SSRF / 任意读 / symlink 越界。无人值守可信化主线第三轮（R69 原子写 → R70 receipt 事务化 → R71 fetch & path 安全）。
- **实现**：
  - `app_utils.py` 新增 `FetchPolicyError` / `PathOutsideWorkspaceError`、`_is_private_address`（IPv4 + IPv6 私网 + link-local + **IPv4-mapped IPv6 折叠**封堵 `::ffff:127.0.0.1` bypass）、`_validate_safe_url`、`safe_fetch(url, *, max_bytes, timeout, allow_private, max_redirects)`（redirect 每跳复检 + max_bytes 截断 raise）、`safe_resolve_within(path, root)`。
  - `drop.py` 切换：`_http_fetch_url` / `_download_asset_url` 用 `safe_fetch`；`_fetch_url` / `_http_fetch_url` 加 `root: Path` 参数让 `file://` 分支走 `safe_resolve_within(path, root)` 而非 `path.parent`（封堵 `drop_url(file:///etc/passwd)` bypass）；`_materialize_binary_source` / `drop_repo` 本地分支 + `_resolve_asset_url` 的 `file://` 都走 `safe_resolve_within`；`_repo_tree` / `_repo_key_files` rglob 后跳过 symlink + 越界检查双保险；`_render_url_with_playwright` 加 `page.route("**/*", _guard)` 拦截每个 navigation/subresource。
  - 常量：`_HTML_MAX_BYTES = 5MB` / `_ASSET_MAX_BYTES = 50MB`。
- **测试**：`tests/test_safe_fetch.py`（9 unittest）+ `test_safe_resolve.py`（6）+ `test_drop_safety.py`（7）；caller 适配 `tests/test_drop.py` 3 处 + `tests/test_app.py` 2 处 `_fetch_url(..., root=self.root)`。
- **Stop Lines**：0 lock 实现改动 / 0 L3 自动采纳 / 0 LLM client 改动 / 0 git clone 远程 URL / 0 fact-layer 直写改动 / 0 receipt schema 改动 / 0 第三方依赖。
- **Residual Risks**：DNS rebinding（推 R73）、CLI render fallback 无 hook 能力（R71+ 视用量决定是否禁用 fallback）、HTTPS cert pinning（依赖 stdlib 默认）、CGN `100.64/10` 未拒绝（接受）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1626 unit + coverage 92%）；oracle qa-review 经一轮 fail-then-fix（3 条 blocker → 全清零 → PASS）。

### Round 70 — Receipt JSONL 事务化 + Revert 双 Receipt — 完成 (commit 950f291)

- **目的**：把 JSONL append 全量从 `path.open("a")` 直写迁到 R69 atomic helper；machine_memory revert 在 R67 单 receipt 基础上加 reverse-event receipt（双 receipt），让 audit/rollback 有完整事务证据。
- **实现**：
  - `src/aiwiki/app_utils.py` 新增 `atomic_append_line(path, line, *, fsync=True)` 单行原子 append 原语（拒绝嵌入 `\n`，自动建父目录），`atomic_append_jsonl` 保持 dict-only + sort_keys。
  - 12 处 JSONL writer 全迁移：`app_state.append_runtime_history` / `app_execution.append_execution_receipt_history` / `runner/receipts._append_jsonl_log` / `metrics_history.append_snapshot` / `memory/graph.append_machine_memory_history` / `content/memory.append_execution_policy_decisions` / `drift_scan` runtime+signals / `planner/rollback` marker / `audit_preview.append_audit` + canonical writer `signals/collector` / `planner/log_writer` / `drift_scan` 走 `atomic_append_line`。
  - `execution/machine_memory_actions.py` revert 写 `output/control/execution-receipts/reverts/<id>.json`（避开 forward receipt glob），payload 内 `receipt_path` override 与实际路径对齐；`metrics_io._receipt_json_paths()` 过滤 `reverts/` 子目录。
  - `metrics_history.append_snapshot` 语义从 best-effort swallow 改为传播 fsync/IO 错误（与无人值守不静默吞错一致）。
  - `runner/receipts.py` 删 `fsync=isinstance(log_path, Path)` 死表达式与 MagicMock seam；`tests/test_execution_compat.py` 两处 seam test 改用 `tempfile.TemporaryDirectory()` + `Path` 替代 MagicMock root。
- **测试**：`tests/unit/test_atomic_io.py` 扩展 `atomic_append_line`（happy / fsync 失败 / 嵌入 `\n` raise / parent dir 自动建）；`tests/unit/test_machine_memory_revert_receipts.py` 新增双 receipt 验证；`test_app.py` / `test_metrics_history.py` / `test_runner.py` / `test_state_utils.py` 抽样 fsync 失败传播扩展。
- **R70.5 归并**：M6.1b `case_backend_failure` fixture refresh（pre-existing prompt drift，与 R70 无关，借本轮归并，`f9b16282…` → `b6f002b9…`）。
- **Stop Lines**：0 lock 实现改动 / 0 L3 自动采纳 / 0 fetch / 0 LLM client / 0 prompt builder / 0 receipt schema 改动 / 0 fact-layer 直写改动（`content/io.py:370` 推 R75）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1604 unit + coverage 92%，30 文件 complete coverage）；oracle qa-review 经一轮 fail-then-fix（5 条 blocker → 全清零 → 1 条 mock seam Medium → 修复后 PASS）。

### Round 69 — Atomic State I/O Foundation — 完成 (commit 7ee3ab8)

- **目的**：为炼丹炉建立原子写 + fsync 的状态 I/O 基础设施，作为 R70 receipt 事务化、R71 fetch 安全、R72 lock 全审计、R74 L3 硬护栏等"无人值守可信化"主线的最底层基石。
- **实现**：`src/aiwiki/app_utils.py` 新增 `atomic_write_text(path, content, *, fsync=True)` + `atomic_append_jsonl(path, record, *, fsync=True)`，tmp+rename+fsync 全套语义，BaseException 也清 tmp。`src/aiwiki/app_state.py` 4 处 saver（`save_json_document` / `save_machine_memory_action_state` / `save_concept_rewrite_state` / `save_manual_link_state`）从 `path.write_text(...)` 直写迁移到 atomic helper。
- **测试**：21 unit tests（`test_atomic_io.py` 16 + `test_app_state_atomic.py` 5），覆盖 happy path / fsync 失败 / replace 失败 / KeyboardInterrupt cleanup / 并发同 path 单胜者 / 自动建父目录 / TypeError 不留文件 / saver 级 fsync 注入失败保留原文件。
- **R69.5 归并**：M6.1b `case_happy_run_ask` fixture pre-existing prompt drift（与 R69 无关，git stash 验证），借本轮归并，`scripts/refresh_acceptance_fixture.py` 一键刷新。
- **Stop Lines**：0 receipt 语义改动 / 0 lock 实现改动 / 0 L3 自动采纳 / 0 fetch / 0 LLM client / 0 prompt builder / 0 73 处其他 write_text 全量迁移（推 R70+）。
- **Lock 边界**：`save_json_document` R69 前后都是 lock-free primitive；helper 不内嵌锁，把 lock 责任完全交给调用方（R72 全 CLI lock 审计 scope）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1601+ unit + coverage 92%）；oracle qa-review PASS（无 Critical/High/Medium 残留）。

### Round 71 — 候选方向（已启动 → 见上方）

### Round 72 — 候选方向（未启动）

- 候选 A：single-writer lock 全 CLI 审计（drop-* / nightly_health 缺锁），R72 主线。
- 候选 B：LLM client 安全（`llm.py` urlopen 三处 + DNS rebinding pinning），R73 主线。
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
