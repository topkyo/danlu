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
| **Round 74 L3 事务化 + audit 失败 auto-revert** (2026-05-04) | apply_l3_proposal 后半段 5 步事务化 / target byte-equal write_bytes(snapshot) / _persist_l3_proposal_page atomic_write_text + proposal deep-copy revert / L3PostApplyAuditError 携带 failed_step+before/after_hash+target_file+action_id+deleted_receipt_path / auto_adopt_l3 标记 auto_reverted 写完整 runtime_history 严重事件 / L3RevertError 二级失败 / 9 测试 | ✅ done (`b6a64f5`) |
| **Round 75 receipt_history 事务化** (2026-05-04) | append_execution_receipt_history 改 snapshot-then-rollback / `_durable_truncate` (open r+b + truncate + flush + fsync) / ReceiptHistoryAuditError + ReceiptHistoryRollbackError / R74 partial 残余风险关闭 / 5 unit + 1 集成 | ✅ done |
| **Round 76 runtime_history 事务化 + audit-mirror helper 上移** (2026-05-04) | `_durable_truncate` + AuditMirror* 上移 app_utils / app_execution alias 保持 R75 API / append_runtime_history snapshot-then-rollback + runtime lock / 5 unit | ✅ done |
| **Round 77 LLM receipt 事务化** (2026-05-04) | `_append_llm_receipt` snapshot-then-rollback / 复用 AuditMirror* + `_durable_truncate` / 不扩 lock 边界 / 5 unit | ✅ done |
| **Round 78 age audit single-file 事务化** (2026-05-04) | `_durable_restore_or_remove` / `_write_age_audit` snapshot bytes + restore/remove / audit-mirror 主线收口 / 5 unit | ✅ done |
| **Round 79 auto_adopt 顶层 lock 收口** (2026-05-04) | 4 个 `auto_adopt_*` 顶层入口加 `@runtime_write_operation` / reentrant lock 验证 / 4 unit | ✅ done |
| **Round 80 safe_fetch response close** (2026-05-04) | `safe_fetch` urlopen response 用 with 包住 read+return / 3 close-path tests / R71-R73 残余关闭 | ✅ done |
| **Round 81 citation snapshot path guard** (2026-05-04) | `citation-snapshot-refresh` 加 `safe_resolve_within` + wiki/judgments|decisions 白名单 / 4 unit | ✅ done |
| **Round 82 citation revert guard 对称收口** (2026-05-04) | `revert_machine_memory_action` citation 分支复用同 helper / R81 follow-up 单点 1 行 | ✅ done |
| **Round 83 safe_fetch DNS pinning + host allowlist** (2026-05-05) | custom HTTP/HTTPS connection pinned-IP connect / proxy 禁用 / SNI 保留 / opt-in allowlist via env / 11 unit | ✅ done |
| **Round 84 fail-soft 降级路径收口 + 事实层 strict read 迁移** (2026-05-05) | notify.py 双层 fallback-of-fallback logger.warning + sanitized metadata / `load_runtime_history_strict` / 6 个事实层 best-effort→strict 切换 / CorruptStateError 自然传播到 CLI / 8 strict 迁移测试 + notify 双层 warning 测试 | ✅ done (`c94cc87`) |
| **Round 85 history JSONL strict migration** (2026-05-05) | execution policy/receipt history JSONL best-effort loader 显式 warning / strict variants / fact-layer callers 切 strict / 8 migration tests | ✅ done (`ea08d6e`) |
| **Round 86 safe_fetch 多 IP fallback** (2026-05-05) | R83 pinning 可用性回归修复 / `_PinnedHTTP[S]Connection` 按 resolver 顺序循环 TCP / 全失败抛 OSError 不混入 FetchPolicyError / handler 接 list / 4 fallback tests | ✅ done (`b345ecf`) |
| **Round 87 R85/R86 non-blocking 小补丁清理** (2026-05-05) | history strict 测试 path:N 断言收紧 / receipt strict missing+non-dict edge tests / HTTPS fallback wrap_socket 单次 + server_hostname 锁定 / redirect 后 IP list 重建测试 / 实现 0 改动 | ✅ done (`0891a44`) |

## 状态 — 当前活跃 3 轮

### Round 87 — R85/R86 non-blocking 小补丁清理 — 完成

- **目的**：清理 R85/R86 oracle qa-review 留下的 5 个 non-blocking findings；纯测试 + docstring 范畴，不改实现。
- **实现**：
  - `tests/test_history_strict_migration.py`：finding 1 — `:33,65` 两处分步 `assertIn(str(path),...)` + `assertIn(":2",...)` 合并为 `f"{path}:2"` 单一 assertIn（对齐 `memory.py` CorruptStateError 抛错格式 `f"... at {path}:{line_no}"`）。finding 2 — 末尾追加 `test_receipt_strict_missing_file_returns_empty`（path 不存在 → []，不抛）+ `test_receipt_strict_non_dict_row_raises`（合法 JSON `["a","b"]` 非 dict → `CorruptStateError(path:1, non-dict)`）。
  - `tests/test_safe_fetch_multi_ip_fallback.py`：fake socket 扩展（:12）支持 status/header 用于 redirect 测试。finding 4 — `test_https_first_ip_fails_second_succeeds_wrap_once`（:146）：URL `https://example.com/path`、2 public IP、首个 OSError 第二个成功；mock `_PinnedHTTPSConnection._context.wrap_socket` 验证 (a) 调用 1 次（防每次失败都 wrap 退化）、(b) 入参为最终 sock、(c) `server_hostname="example.com"` 原始 host 不是 IP。finding 5 — `test_redirect_rebuilds_ip_list`（:177）：第一次 resolve `[1.1.1.1]` 返回 302 + Location，第二次 resolve `[2.2.2.2, 3.3.3.3]`，三次 connect IP 顺序 `["1.1.1.1","2.2.2.2","3.3.3.3"]` 锁住"redirect 后 pinned_ips 来自新 resolve 全 list 而非旧"+"新 list 内可 fallback"。
  - finding 3：receipt best-effort docstring oracle 评估留 non-blocking（`replacement-decoded bad UTF-8 are skipped` 表述对落在 JSON string 内的坏字节略有歧义；fixer 评估清晰未改，oracle 同意 non-blocking 留作后续）。
- **测试**：4 新增（finding 2×2 + finding 4×1 + finding 5×1）。1712 → 1716 unit。
- **Stop Lines**：0 实现逻辑改动 / 0 docstring 改动 / 0 公共 API 签名 / 0 schema / 0 caller / 0 R86 fallback 实现 / 0 R85 strict loader 实现 / untracked Obsidian/docs 不纳入 / 不写 PROGRESS（archive 阶段统一）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1716 unit + coverage 92%）；oracle qa-review PASS（无 blocker；2 个 non-blocking 留作后续：receipt best-effort docstring 表述微调 / redirect 测试可加 `patch.dict(os.environ, {}, clear=True)` 显式 allowlist 隔离）。

### Round 86 — safe_fetch 多 IP fallback — 完成

- **目的**：修 R83 DNS pinning 引入的可用性回归。原实现 `pinned_list[0].ip` 单 IP，CDN / 多 region / dual-stack 首 IP 不可达整体失败；stdlib 默认 `getaddrinfo` 列表 TCP fallback 被丢掉。
- **实现**：
  - `app_utils.py` `_PinnedHTTPConnection` / `_PinnedHTTPSConnection`：`_pinned_ip: str` → `_pinned_ips: list[str]`；`connect()` 按 resolver 顺序循环 `socket.create_connection`，首个成功 break；全失败保留 last `OSError` 抛出（urllib 包成 `URLError`），不混入 `FetchPolicyError` 策略语义。
  - HTTPS `wrap_socket(sock, server_hostname=self.host)` 仅在最终成功 sock 上执行；`_tunnel` 顺序与 R83 一致。
  - `_PinnedHTTPHandler` / `_PinnedHTTPSHandler`：`pinned_ip: str` → `pinned_ips: list[str]`，`_make_connection` 传 `_pinned_ips=`。
  - `safe_fetch:927`：`pinned_ips = [addr.ip for addr in pinned_list]` 保留 resolver 顺序；redirect 后下一轮 while 顶部重建。
  - 不在 `safe_fetch` 主循环 retry 整个 request（避免 POST 重放）；只 connect 层 fallback。
  - 不动 zone-id `split("%")` / IPv6 sockaddr 4-tuple（R87+ 候选，oracle 评估 link-local + allow_private 边缘组合，无明确需求）。
- **测试**：新增 `tests/test_safe_fetch_multi_ip_fallback.py` 4 测试（首 IP fallback / 全失败 URLError 而非 FetchPolicyError / 单 IP 防退化 / v6+v4 顺序保留）；既有 `test_safe_fetch_pinning.py:78` 1 处 `_pinned_ip=` → `_pinned_ips=[...]` 适配；其余 11 测试不破。
- **Stop Lines**：0 公共 API 签名 / 0 caller (drop.py / llm.py / notify.py) / 0 schema / 0 第三方依赖 / 不在 safe_fetch 层 retry POST / 不动 zone-id / 不动 IPv6 sockaddr 4-tuple / untracked Obsidian/docs 文件不纳入。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1712 unit + coverage 92%）；oracle qa-review PASS（无 blocker；2 个 non-blocking 缺口：HTTPS fallback 测试 / redirect 后 IP list 重建测试，留作后续）。

### Round 85 — history JSONL strict migration — 完成

- **目的**：延续 R84 事实层 strict read 主线，把 execution policy / receipt history JSONL loader 从隐式 best-effort 区分为“UI/dashboard 可跳坏行”与“事实层坏数据 fail-fast”。
- **实现**：
  - `content/memory.py`: `load_execution_policy_decision_history` / `load_execution_receipt_history` 保持 best-effort，但对 malformed JSONL row / non-dict row 显式 `logger.warning`，包含 `path`、`line_no`、错误类型；新增 `load_execution_policy_decision_history_strict` / `load_execution_receipt_history_strict`，missing file 返回 `[]`，malformed JSONL / non-dict row 抛 `CorruptStateError`，receipt strict 对 invalid UTF-8 自然抛 `UnicodeDecodeError`。
  - fact-layer callers 切 strict：`app_linting/nightly.py`、`app_linting/phases.py`、`memory/execution_surfaces.py`；为守 facade stop line，strict imports 直接来自 `aiwiki.content.memory`，未添加到 `app_content.py` 等 facade re-export。
  - 保留 best-effort 路径：`app_shell/surfaces.py`、`app_linting/core.py`、`app_linting/repair.py` 与既有 facade re-export 不动。
- **测试**：新增 `tests/test_history_strict_migration.py` 8 测试（policy corrupt/non-dict/missing/limit；receipt corrupt/invalid UTF-8/filter kind；best-effort warning + skip）。
- **Stop Lines**：0 public API 签名改动 / 0 schema 改动 / 0 writer path 改动 / 0 facade re-export 改动 / 不触碰 R84 runtime_history / single receipt JSON / revert receipt；untracked Obsidian/docs 文件不纳入。
- **验证**：`PYTHONPATH=src python -m unittest tests.test_app tests.test_runner tests.test_linting tests.test_execution tests.test_history_strict_migration` 451 tests OK；`bash scripts/verify.sh` all green（1708 unit + 13 acceptance + coverage 92%）。

### Round 77 — `_append_llm_receipt` 事务化 — 完成

- **目的**：关闭 audit-mirror 二段写主线最后一个 jsonl 同构裂缝。`_append_llm_receipt` 原先先写 `.aiwiki/logs/llm-receipts.jsonl` 再写 universal `audit.jsonl`，audit 失败会留下 primary-only 行。
- **实现**：
  - `runner/receipts.py:_append_llm_receipt` 改为 `size_before` snapshot → `_append_jsonl_log` → try `append_universal_audit_record` → audit 失败 `_durable_truncate(log_path, size_before)` → `AuditMirrorError`；truncate 失败 → `AuditMirrorRollbackError`。
  - 复用 R76 上移到 `app_utils.py` 的 `_durable_truncate` / `AuditMirrorError` / `AuditMirrorRollbackError`。
  - 按 contract 不加 `@runtime_write_operation`，不动 `_append_jsonl_log` / `_next_jsonl_line_number` / schema / source_stream / source_ref / document / caller。
- **测试**：新增 `tests/test_llm_receipt_transaction.py` 5 测试（audit 失败回滚 / truncate 失败 rollback error / 成功 primary 写入 / primary 不存在前置 / 防退化 spy helper）。
- **Stop Lines**：0 通用 audit_transaction context manager / ~~0 `_write_age_audit` single-file mirror 修复（留 R78+）~~ → R78 已关闭 / 0 lock 边界扩张 / 0 schema 改动。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1663 unit + coverage 92%）。

### Round 76 — append_runtime_history 事务化 + audit-mirror helper 上移 — 完成

- **目的**：关闭 R75 留下的最后一口 nested IO partial。`append_runtime_history` 内部先写 `runtime-history.jsonl` 再写 universal `audit.jsonl`，第二步失败时 primary 已落但 audit 缺；R76 复用 R75 的 snapshot-then-rollback 模式，并把通用 helper 上移到 `app_utils.py`。
- **实现**：
  - `app_utils.py` 新增 `_durable_truncate`、`AuditMirrorError`、`AuditMirrorRollbackError` 三个公共名字。
  - `app_execution.py` 删除本地 `_durable_truncate` / `ReceiptHistoryAuditError` / `ReceiptHistoryRollbackError` 定义，改为从 `app_utils.py` import alias，保持 R75 外部 import 兼容。
  - `append_runtime_history` 新加 `@runtime_write_operation`，事务化为 `size_before` snapshot → `atomic_append_jsonl` → try `append_universal_audit_record` → audit 失败 `_durable_truncate(path, size_before)` → `AuditMirrorError`；truncate 失败 → `AuditMirrorRollbackError`。
  - 保持 27 处调用方、`atomic_append_jsonl`、`append_audit` / `append_universal_audit_record`、schema 不动。
- **测试**：新增 `tests/test_runtime_history_transaction.py` 5 测试（audit 失败回滚 / truncate 失败 rollback error / 成功路径双写 + line_number / primary 不存在前置 / 防退化 spy helper）。
- **Stop Lines**：0 通用 `audit_transaction` context manager / 0 schema 改动 / 0 atomic append 原语改动 / 0 runtime_history 调用方改动 / 0 universal audit backfill 行为改动。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1658 unit + coverage 92%）。

### Round 75 — append_execution_receipt_history 事务化 — 完成

- **目的**：关闭 R74 留下的 nested IO partial 残余风险。`append_execution_receipt_history` 内部先写 `execution-receipts.jsonl` 再写 universal `audit.jsonl`，第二步失败时 primary 已落但 audit 缺；R75 让两者要么都成功要么 primary 回滚到调用前长度。无人值守可信化主线第七轮。
- **实现**：
  - `app_execution.py` 新增 `ReceiptHistoryAuditError` / `ReceiptHistoryRollbackError`。
  - `append_execution_receipt_history` 事务化：`size_before = path.stat().st_size if path.exists() else 0` → `atomic_append_jsonl(path, receipt)` → try `append_universal_audit_record(...)`；audit 失败调内部 helper `_durable_truncate(path, size_before)`（open `r+b` + truncate + flush + `os.fsync(fileno)`）回滚 primary，raise `ReceiptHistoryAuditError`；truncate/fsync 自身失败 raise `ReceiptHistoryRollbackError` 含 audit_exc + truncate_exc 双层信息。
  - 保持 `@runtime_write_operation` 装饰器、签名、line_number 逻辑不变。所有调用方（L3 / machine_memory / alchemy / archive / runner，共 18 处）透明受益。
  - 方案 3（snapshot-then-rollback）：保持 primary=成功标记的语义不变，避免顺序翻转影响下游消费方。
- **测试**：`tests/test_receipt_history_transaction.py` 5 测试（audit 失败回滚 / truncate 也失败 raise rollback / 成功路径双写 / primary 不存在前置 / 防退化 spy `_durable_truncate` 必被调用）；`tests/test_l3_auto_revert.py` 新增 1 集成测试（mock universal audit 失败 → R75 primary rollback → R74 L3 revert target → raise `L3PostApplyAuditError(failed_step="append_execution_receipt_history")`）。
- **Stop Lines**：0 通用 `with audit_transaction(root)` 抽象（推 R76+） / 0 receipts.jsonl + audit.jsonl schema 改动 / 0 atomic_append_jsonl 内部改动 / 0 调用方改动 / 0 universal audit backfill 改动 / 0 `append_runtime_history` 同类修复（留 R76+）。
- **Residual Risks**：~~`append_runtime_history` 同构 nested IO partial 仍存在（runtime-history.jsonl + audit.jsonl），R76+ 收口~~ → R76 已关闭；rollback 在 `truncate + flush + fsync` 过程中崩溃的窗口仍为接受残余风险（fsync 后 durable）；NFS 等网络文件系统的 truncate 行为不完全保证（本地 ext4/btrfs/apfs 没问题）。
- **验证**：`bash scripts/verify.sh` all green（13 acceptance + 1653 unit + coverage 92%）；oracle qa-review 经 fail-then-fix（1 High → 清零 → PASS）。

### Round 74 — L3 自动采纳事务化 + audit 失败 auto-revert — 完成 (commit b6a64f5)

- **目的**：为 L3 自动采纳建立"事务化 + audit 失败 auto-revert"护栏，让 L3 默认 ON 安全（终局无人值守主线护栏第六轮）。
- **实现**：
  - `execution/l3_proposals.py` `apply_l3_proposal` 后半段 5 步（receipt_history / state_save / persist_proposal_page / runtime_history / wiki_log）包进单个 try/except 事务段；任一失败：`target.write_bytes(snapshot)` byte-equal 还原 + `receipt_path.unlink(missing_ok=True)` + 通过 deep-copy 的 proposal snapshot 强制恢复 state/page → raise `L3PostApplyAuditError(target_reverted=True, failed_step, target_file, before_hash, after_hash, deleted_receipt_path, action_id)`；revert 自身失败 raise `L3RevertError`。
  - `_persist_l3_proposal_page` 改用 `atomic_write_text`，避免半写。
  - `runner/auto_adopt.py` 捕获 `L3PostApplyAuditError` → `status="auto_reverted"`，捕获 `L3RevertError` → `status="audit_revert_failed"`；写 `l3-proposal-auto-revert` runtime history 严重事件，含 7 字段（action_id / failed_step / target_file / before_hash / after_hash / target_reverted / deleted_receipt_path）。
  - 方案 B：apply 已物理回滚 + receipt file 已删，不再调 `revert_l3_proposal`。
- **测试**：`tests/test_l3_auto_revert.py` 9 测试（5 失败步骤 + revert 自身失败 + auto_adopt 元数据 + L3RevertError 路径）；`test_execution.py` / `test_auto_adopt.py` 既有用例预期同步更新。
- **Stop Lines**：0 通用 `with l3_transaction(root)` 抽象 / 0 receipt+audit JSON schema 改动 / 0 audit_preview.append_audit 改动 / 0 L3 触发条件改动 / 0 machine_memory auto_adopt 类似改动（留 R75+） / 0 generate_l3_proposals_from_planner 改动。
- **Residual Risks**：~~`append_execution_receipt_history` nested IO partial 失败仍可能留下 receipt_history apply 行而无对应 fact，本轮接受留 R75+~~ → R75 已关闭；方案 B 无独立 revert receipt 文件，事后审计依赖 runtime_history 严重事件 + 原 receipt 已删。
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
