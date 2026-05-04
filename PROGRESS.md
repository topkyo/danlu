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
| **Round 72 Lock 高优先级缺锁补齐** (2026-05-04) | drop_* 五入口 + nightly_health + append_execution_receipt_history 全加 runtime_write_lock / 抽 _unlocked helper 保签名 / 3 lock coverage 测试 | ✅ done (`addd53d`) |
| **Round 73 LLM/notify HTTP 安全** (2026-05-04) | safe_fetch 扩展 POST + headers + redirect strip auth / llm.py 三处 + notify.py webhook 切换 / _LLM_MAX_BYTES 10MB + _NOTIFY_MAX_BYTES 1MB / 7 安全测试 | ✅ done (`c0cf944`) |
| **Round 74 L3 事务化 + audit 失败 auto-revert** (2026-05-04) | apply_l3_proposal 后半段 5 步事务化 / target byte-equal write_bytes(snapshot) / _persist_l3_proposal_page atomic_write_text + proposal deep-copy revert / L3PostApplyAuditError 携带 failed_step+before/after_hash+target_file+action_id+deleted_receipt_path / auto_adopt_l3 标记 auto_reverted 写完整 runtime_history 严重事件 / L3RevertError 二级失败 / 9 测试 | ✅ done |

## 状态 — 当前活跃 3 轮

### Round 74 — L3 自动采纳事务化 + audit 失败 auto-revert — 完成

- **目的**：为 L3 自动采纳建立"事务化 + audit 失败 auto-revert"护栏，让 L3 默认 ON 安全（终局无人值守主线护栏第六轮）。
- **实现**：
  - `execution/l3_proposals.py` `apply_l3_proposal` 后半段 5 步（receipt_history / state_save / persist_proposal_page / runtime_history / wiki_log）包进单个 try/except 事务段；任一失败：`target.write_bytes(snapshot)` byte-equal 还原 + `receipt_path.unlink(missing_ok=True)` + 通过 deep-copy 的 proposal snapshot 强制恢复 state/page → raise `L3PostApplyAuditError(target_reverted=True, failed_step, target_file, before_hash, after_hash, deleted_receipt_path, action_id)`；revert 自身失败 raise `L3RevertError`。
  - `_persist_l3_proposal_page` 改用 `atomic_write_text`，避免半写。
  - `runner/auto_adopt.py` 捕获 `L3PostApplyAuditError` → `status="auto_reverted"`，捕获 `L3RevertError` → `status="audit_revert_failed"`；写 `l3-proposal-auto-revert` runtime history 严重事件，含 7 字段（action_id / failed_step / target_file / before_hash / after_hash / target_reverted / deleted_receipt_path）。
  - 方案 B：apply 已物理回滚 + receipt file 已删，不再调 `revert_l3_proposal`。
- **测试**：`tests/test_l3_auto_revert.py` 9 测试（5 失败步骤 + revert 自身失败 + auto_adopt 元数据 + L3RevertError 路径）；`test_execution.py` / `test_auto_adopt.py` 既有用例预期同步更新。
- **Stop Lines**：0 通用 `with l3_transaction(root)` 抽象 / 0 receipt+audit JSON schema 改动 / 0 audit_preview.append_audit 改动 / 0 L3 触发条件改动 / 0 machine_memory auto_adopt 类似改动（留 R75+） / 0 generate_l3_proposals_from_planner 改动。
- **Residual Risks**：`append_execution_receipt_history` nested IO partial 失败仍可能留下 receipt_history apply 行而无对应 fact，本轮接受留 R75+；方案 B 无独立 revert receipt 文件，事后审计依赖 runtime_history 严重事件 + 原 receipt 已删。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1647 unit + coverage 92%）；oracle qa-review 经 fail-then-fix（5 条 blocker → 全清零 → PASS）。

### Round 73 — LLM Client + Notify HTTP 安全 — 完成 (commit c0cf944)

- **目的**：把 R71 的 fetch 安全（private IP 拒绝 + redirect 复检 + max_bytes + 显式 timeout）贯通到 LLM client 与 notify webhook 路径。无人值守可信化主线第五轮（R69 原子写 → R70 receipt 事务化 → R71 drop fetch → R72 lock → R73 LLM/notify fetch）。
- **实现**：
  - `app_utils.safe_fetch` 扩展支持 `method="POST"` + `data: bytes | None` + `headers: dict | None`，签名返 `tuple[bytes, str]` (body, final_url)。redirect 跨 host 时 case-insensitive strip `Authorization` / `x-api-key` / `Cookie`；同 host 保留。显式 User-Agent 不被默认值覆盖。
  - `llm.py` 三处裸 urlopen（OpenAI chat / OpenAI image / Anthropic messages）全切换；新增 `_LLM_MAX_BYTES = 10 * 1024 * 1024`；`FetchPolicyError -> LLMError("unsafe LLM endpoint: ...")`，原有 `HTTPError` / `URLError` 链不变。
  - `notify.py` webhook 同样切换；`_NOTIFY_MAX_BYTES = 1 * 1024 * 1024`；`FetchPolicyError` 走 fail-soft audit 路径不 crash 调用方。
  - drop.py R71 GET 调用方 `payload, final_url = safe_fetch(...)` 兼容（tuple 接口保持）。
- **测试**：`tests/test_safe_fetch.py` 加 POST body/header + 跨 host strip auth + 同 host 保留 auth 三个；`tests/test_llm_safety.py`(3) + `tests/test_notify_safety.py`(1) 新建；`tests/test_llm.py` / `tests/test_notify.py` 既有 mock 迁移到 `safe_fetch`。
- **Stop Lines**：0 第三方 SDK / 0 DNS pinning（推 R73+）/ 0 域名 allowlist / 0 backend 选择改动 / 0 streaming API。
- **Residual Risks**：DNS rebinding（resolve→connect IP 变化）；TLS cert pinning 仍依赖系统 CA；域名仅黑名单未 allowlist；非阻断观察：`safe_fetch` response 未显式 `with`/`finally` close（建议未来清理）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1636 unit + coverage 92%）；oracle qa-review PASS（无 Critical/High/Medium）。

### Round 72 — Single-Writer Lock 高优先级缺锁补齐 — 完成 (commit addd53d)

- **目的**：为炼丹炉 single-writer-many-readers 模型补齐 3 类高优先级缺锁入口。无人值守可信化主线第四轮（R69 原子写 → R70 receipt 事务化 → R71 fetch 安全 → R72 lock 全覆盖）。
- **实现**：
  - `drop.py` 五个公共入口（`drop_url` / `drop_pdf` / `drop_image` / `drop_repo` / `drop_note`）抽 `_..._unlocked` 内部 helper，公共入口外层 `with runtime_write_lock(root):` 包整个事务。
  - `runtime_surfaces.py` `nightly_health(root)` 同样 helper + 外层加锁（之前仅子流程 `write_nightly_health` 加锁）。
  - `app_execution.py` `append_execution_receipt_history` 加 `@runtime_write_operation` 装饰器，与 `run_nightly` / `run_lint` 风格一致。
- **测试**：`tests/test_lock_coverage.py` 3 个 unittest，patch `runtime_write_lock` 断言被调用。
- **Stop Lines**：0 lock 实现改动 / 0 lock 文件路径改动 / 0 read-write 锁分离 / 0 atomic_* 原语自动取锁 / 0 中优先级 8 handler 顶层兜底（today-snooze / apply-* / revert-* / planner-log-replay / batch-review / review-next 留 R72+）。
- **Residual Risks**：中优先级 8 handler 仍依赖底层分散加锁，重构可能漏；`today-snooze` load-modify-save 非事务化（accepted Medium）；NFS fcntl 异常本轮不防御。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1629 unit + coverage 92%）；oracle qa-review PASS（无 Critical/High，仅 accepted residual Medium）。

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
