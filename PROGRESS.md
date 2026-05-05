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
| **Round 88 PM-UX 三件套** (2026-05-05) | Today 空态 CTA「投一份材料」聚焦 universal input / 提交后"处理中"卡片（runtime-only push/done/failed/reset state machine + reconcile 时间戳门槛 + 字段扩展 + 短指纹 exact + 超窗保留 + dedupe）/ 用户层面板文案白话化（plugin/constants/render_execution/render_review/render_primitives/health-state，"shell-summary.json" → "数据还没准备好"等）/ pending 卡片样式 + pulse / 12 契约测试 / oracle qa-review 2 轮全 PASS | ✅ done |
| **Round 89 PM/UX 信任闭环 + 文案统一** (2026-05-05) | pending 持久化（settings.persistedPendingSubmissions + serialize/hydrate + TTL 24h running→failed + cap 8）/ 状态机两段式（running → received "已接收，等待生成报告" → done(target=outputs\|receipts) "报告已生成"\|"已记录"）/ markReceived/markDone 互斥防御（防 reconcile race & 重复 setTimeout）/ 失败卡通用 hint + 重试统一收口 markReceived / Today→今天 闭环（标题 + 3 处 input hint）/ groupSpecs 中文化（新报告/系统动态/需要你确认/已完成/下一步建议）/ Advanced drawer "开发者诊断信息"分隔横条 / 23 pending 测试 + 9 today_feed 测试 + 48 jest / oracle qa-review 2 轮全 PASS | ✅ done |
| **Round 91 Advanced 抽屉信息架构** (2026-05-05) | dev banner 外置（不再嵌外层 Advanced details）/ 三组可折叠 section（系统状态/运行与历史/开发者操作）/ 折叠态持久化 `settings.advancedSectionsExpanded.{status,history,devops}` 默认全收 / `getAdvancedSectionExpanded` + `async setAdvancedSectionExpanded`（own-object 防 DEFAULT_SETTINGS 浅拷贝污染）/ summary helpers：协议 {p}·LLM {l}·同步 {s} / 最近运行 {n} 条·待审 {r}·待执行 {e} / 编译·同步·协议切换·日志 / renderHistorySectionBody 含 Recent Runs+Review+Execution 三入口 + Latest LLM run 摘要 / renderLegacyAdvancedPanel 去外层 details body 平铺 / 11 翻译键 + .furnace-advanced-section* 样式 / 99 pytest+13 acceptance+48 jest 全过 / oracle qa-review 2 轮 PASS | ✅ done |
| **Round 90 提交→状态→结果 闭环** (2026-05-05) | Today 顶部"刷新炉子"+last-updated（getLastSummaryRefreshLabel 4 档：刚刚/N 分钟前/N 小时前/N 天前 + clamp 未来时间）/ pending received/running 卡加"刷新状态"按钮 / done 卡不再 4s 自动消失 → 行动卡（outputs:打开报告 / receipts:查看回执 / 完成）/ openPendingDoneTarget helper：openWorkspacePath 改返 boolean，失败退化到 Outputs Hub / Recent Runs / HOME.md + Notice / refreshShellSummaryCommand 始终 fallback loadShellSummaryFromDisk（保证 reconcile）/ done TTL 7d hydrate（finishedAt 缺失退 startedAt）/ reconcilePath 进序列化 / +10 R90 测试（46 pending+today / 13 acceptance / 48 jest 全过）/ oracle qa-review 3 轮 PASS | ✅ done |
 | **Round 92 Alchemy Apply Lock + Receipt Atomicity** (2026-05-05) | runner/alchemy.py 7 个顶层 apply/auto/lane 入口加 `@runtime_write_operation`（judge_apply / judge_proposal_apply / distill_apply / review_apply / propose_apply / lane_apply / auto）/ 7 处 receipt JSON write 切到 `atomic_write_text` / 4 个 `run_alchemy_*_preview` + 4 个 `preview_*_primitive` 加 `allow_current_writer_lock` 透传参数 / apply 内部 5 处 preview + lane_apply preview + auto 内 lane_dry_run 全部 force True / `_normalize_preview_lock_status` 30 行递归 helper 把 `held_by_current_process` 还原为 `available + would_acquire` 保 receipt schema / acceptance fixture 兼容 / `_run_receipted_lane_primitive` 不加装饰器靠外层 reentrant lock / 新建 `tests/test_alchemy_apply_lock.py` 10 测试（7 入口 lock 持有 + outer-lock reentrant + atomic_write_text failure + grep guard）/ verify.sh all green（1776 unit + 13 acceptance + coverage 92%）/ fresh isolated oracle qa-review PASS | ✅ done |
 | **Round 92.1 Alchemy Lock Audit (Tight)** (2026-05-05) | R92 non-blocking observations 合并轮：runner/alchemy.py 3 残余 unlocked writers 加 `@runtime_write_operation`（`run_alchemy_judge_propose` / `run_alchemy_legacy_migration_apply` / `run_alchemy_superseded_cleanup_apply`）/ `_normalize_preview_lock_status` 重构为 `_walk_preview_lock_status(value, in_lock_subtree)` 双函数：只在 `lock` key 子树下改写 `held_by_current_process → available + would_acquire`，不再误伤同形非-lock dict / `tests/test_alchemy_apply_lock.py` +6 测试（3 新装饰器 lock probe + 1 lane→primitive nested depth>=2 真实探针 patching `run_alchemy_review_preview` 让 review_apply 装饰器先递增 depth + 2 normalize 收紧 unit）/ grep guard 从固定字符串扩到 receipt-like 变量正则 `\b(\w*receipt\w*)\.write_text\(json\.dumps\(`/ verify.sh all green（1782 unit + 13 acceptance + coverage 92%）/ fresh oracle qa-review round 1 FAIL（lane test vacuous）→ round 2 全 PASS | ✅ done |
 | **Round 92.5 Cache Layer Fail-Soft** (2026-05-05) | `src/aiwiki/app_cache.py` SQLite query cache 全 fail-soft：模块 logger + `_log_cache_fault(label, exc)` helper / 8 boundary 包 try/except 仅捕 `(sqlite3.Error, OSError, json.JSONDecodeError, TypeError)`：`sync_query_cache` / `_load_rows`(narrow `JSONDecodeError, TypeError`) / `load_query_cache_snapshot` / `load_cached_query_result` / `save_cached_query_result` / `_merge_cache_status` / `record_query_cache_event` — corrupt sqlite db / corrupt payload_json (`cache_query_results` / `cache_nodes` / `cache_edges`) / write commit failure 全部 warn + miss / skip-write 不抛 / `src/aiwiki/app_state.py` cache-status boundary：`load_cache_status:632-637` + `save_cache_status:678-683` 仅捕 `OSError`（不动通用 `load_json_document` / `save_json_document` / `atomic_write_text`）/ 5 compile build-state save callsite 直接调生产 `write_json_document_if_changed_ignoring_generated_timestamps(...)` + try/except `OSError` warning：`compile/content_step.py:53-59` concept / `runtime_step.py:408-414` machine-memory + `:575-581` ranking / `output_step.py:356-362` output-pack + `:427-433` domain-pilot / 新建 `tests/test_cache_failsoft.py` 12 测试 + `load_tests` bridge（corrupt result/nodes/edges payload + 非法 sqlite db 字节 + `_connect_cache` patch sqlite3.OperationalError + `save_json_document` patch OSError + 5 build-state OSError patch 各 compile step 模块 namespace 真实生产路径 + grep guard 扫禁 broad `except Exception` / `except BaseException`）/ verify.sh PASS（**1818 unit**(+12) + 13 acceptance + 92% coverage）/ fresh oracle qa-review round 1 CONCERNS（`__module__` 测试感知分支泄漏 + edges payload 未直测）→ fix：移除全部 5 callsite 的 `__module__` 分支 + 新增 corrupt edges 测试 + 重写 build-state 测试 patch 真实生产 helper at compile step namespace → round 2 PASS（`ses_2072c8fdfffe0FXemS421lGPid`）/ 0 SoT fail-soft / 0 `load_json_document_strict` / `CorruptStateError` / `atomic_write_text` 改动 / 0 `.aiwiki/cache/machine-memory-graph.json` 改动 / 0 lock 语义 / 0 receipt / manifest schema / 0 LLM raw response | ✅ done |
 | **Round 92.4 Protocol/Manifest Single-File Atomic Writes** (2026-05-05) | `src/aiwiki/app_protocol.py` 5 处 + `src/aiwiki/app_compile_ops.py` 1 处 protocol/manifest JSON state 写入从裸 `write_text(json.dumps(...))` / `json.dump(...)` 迁到 `atomic_write_text`：runtime.yaml default schema (`:1700`) / runtime.yaml scaffold schema (`:1760`) / initial protocol.json (`:1774`) / normalized protocol.json (`:1808`) / manifest.json (`:1995`，`json.dump` block→`atomic_write_text + json.dumps`) / active protocol switch (`app_compile_ops.py:312`) / 保留 indent=2 / sort_keys=True / ensure_ascii=False (runtime schema) 全部原始 kwargs / 新建 `tests/test_protocol_manifest_atomic.py` 5 测试 + `load_tests` bridge（save_manifest / set_active_protocol / load_protocol_state normalization / load_protocol_runtime_schema default 各 patch `os.replace` raise 验旧 bytes preserved + 无 tmp 残留 + grep guard 扫两文件禁 `write_text(json.dumps(` / `json.dump(`）/ verify.sh PASS（**1806** unit (+5) + 13 acceptance + 92% coverage）/ fresh oracle qa-review round 1 FAIL（pytest-style 测试未被 unittest discover 收集，count 1801 != 1806）→ fix `load_tests` adapter（复用 R92.2 模式）→ round 2 PASS（`ses_2075a2334ffe4zJfZUFXRcFUpP`）/ 0 schema / lock / multi-file TX / markdown scaffold / generic residual writer 改动 | ✅ done |
 | **Round 92.3 Drop Input Safety (Bounded Local Ingestion)** (2026-05-05) | `src/aiwiki/drop.py` 加本地 ingestion 边界：常量 `_LOCAL_PDF_MAX_BYTES` 50MB / `_LOCAL_IMAGE_MAX_BYTES` 25MB / `_SUPPORTED_IMAGE_MIME_TYPES` 白名单（png/jpeg/gif/webp/svg+xml）/ helpers `_assert_file_size` + `_assert_pdf_asset`（5 字节 `%PDF-` magic）+ `_assert_supported_image_mime`（错误消息列允许集）+ `_normalize_repo_max_files`（1..1000）/ `drop_pdf:240-241` 在 `_extract_pdf_text` 前 size+magic / `drop_image:318-319` 在 OCR + `_analyze_image_asset` 前 MIME+size / `drop_repo:416` 入口 normalize max_files / `_repo_key_files:1344-1348` 加 residual 注释 / `cli/parsers.py` drop-pdf/drop-image/`--max-files` help 文案补限制 / `tests/test_drop_safety.py` 扩 7 测试（image rejection 双 patch 验证 vision 不可达 + MIME 错误断言列允许集 + repo max_files 边界参数化）/ verify.sh PASS（1801 unit + 13 acceptance + 92% coverage）/ fresh oracle qa-review round 1 CONCERNS（4 P2: image rejection 未验 vision / MIME 错误未列允许集 / CLI help 未文档化 / `_repo_key_files` walk 不受 max_files 约束 residual）→ round 2 PASS（`ses_2078a47c5ffeT39FAKQvK3cwCx`）/ 0 root containment 改动 / 0 safe_fetch / SSRF / LLM HTTP / receipt schema / atomic write helper 改动 | ✅ done |
 | **Round 92.2 Machine-Memory Action TX** (2026-05-05) | `apply_machine_memory_action` / `revert_machine_memory_action` 加 snapshot/rollback 事务边界，覆盖 3 种 apply_mode（manual-link-state / citation-snapshot-refresh / resolve-monitor）/ 新增错误类型 `MachineMemoryActionReceiptError`（普通事务失败）/ `MachineMemoryActionHalfWriteError`（rollback 自身失败 loud）/ helper `_snapshot_file_bytes` + `_restore_file_bytes`(atomic tmp+os.replace, None→unlink) + `_rollback_snapshots` / 进入 try 前 snapshot 4 核心路径（receipt_path / `.aiwiki/state/execution-receipts.jsonl` / `.aiwiki/state/audit.jsonl` / `.aiwiki/state/machine-memory-actions.json`）+ mode-specific（manual-links.json 或 citation page bytes）/ mutation + receipt JSON write + history append + actions.json save 全部 try 内，except → rollback all + 抛 ReceiptError；rollback 失败抛 HalfWriteError / receipt JSON 与 citation page revert write 全切 `atomic_write_text` / `split-overloaded-concept` auto-retire 留 best-effort 在 try 内，rollback 不覆盖（contract residual） / 新建 `tests/test_machine_memory_action_transaction.py` 12 测试（manual-link/citation/resolve-monitor 各自 happy + rollback 真实分支 + 真实 `_restore_file_bytes` 失败 → HalfWriteError + 源码 atomic-write guard）/ verify.sh PASS（1794 unit + 13 acceptance + coverage 92%）/ fresh oracle qa-review round 1 CONCERNS（测试命名误导 + 缺真实 citation/resolve-monitor 分支覆盖）→ round 2 PASS（`ses_207a58043ffe71a5R252pG0Mn3`） | ✅ done |

## 状态 — 当前活跃 3 轮

### Round 92.5 — Cache Layer Fail-Soft — 完成

- **目的**：闭环 oracle batch review 中的 R92-CACHE-FAILSOFT P1。Cache layer（不可作 SoT）原本 hard-fail：corrupt sqlite db / corrupt JSON payload / cache write failure 都直接抛异常，破坏主路径 query/compile 结果。把它改成 fail-soft：cache fault 只 warn + treat-as-miss / skip-write，绝不影响主路径。Standard scope：SQLite query cache + cache-status JSON + 5 incremental compile build-state writes。SoT 状态（manifest / machine-memory / compile-state / protocol / receipts / audit / runtime history）保持 hard-fail。
- **实现**：
  - `src/aiwiki/app_cache.py`：`:29-36` 加 module logger + `_log_cache_fault(label, exc)` helper（`logger.warning("cache %s failed: %s", label, exc)`）；8 boundary 包 try/except 严格捕获 `(sqlite3.Error, OSError, json.JSONDecodeError, TypeError)`，绝无 broad `except Exception`：`sync_query_cache:277-517` 失败返当前 cache status / `_load_rows:526-535` 仅捕 `(JSONDecodeError, TypeError)` 返空 / `load_query_cache_snapshot:544-606` 失败返 None（caller 当 miss）/ `load_cached_query_result:617-632` 同 miss / `save_cached_query_result:641-654` skip-write / `_merge_cache_status:662-685` skip / `record_query_cache_event:704-719` best-effort default。
  - `src/aiwiki/app_state.py` cache-status boundary：`load_cache_status:632-637` 包 `OSError` 返 default empty status / `save_cache_status:678-683` 包 `OSError` warning skip — 不动通用 `load_json_document` / `save_json_document`（也服务 SoT）/ 不动 `atomic_write_text` / 不动 `load_json_document_strict` / `CorruptStateError`。
  - 5 compile build-state save callsite 直接调生产 `write_json_document_if_changed_ignoring_generated_timestamps(<path>, <state>)` 包 try/except `OSError` warning + continue（next run 走 deterministic rebuild）：`compile/content_step.py:53-59` concept / `runtime_step.py:408-414` machine-memory + `:575-581` ranking / `output_step.py:356-362` output-pack + `:427-433` domain-pilot — 不动 `save_*_build_state` helper 自身（避免影响其它 caller）。
  - 新建 `tests/test_cache_failsoft.py` 12 测试 + `load_tests` bridge：(1) corrupt `cache_query_results.payload_json` / (2) corrupt `cache_nodes.payload_json` / (3) corrupt `cache_edges.payload_json` / (4) 非法 sqlite db 字节 → query 不抛 + 返主路径有效结果 / (5) `_connect_cache` patch `sqlite3.OperationalError("readonly database")` → query 仍返结果 / (6) patch `aiwiki.app_state.save_json_document` 抛 `OSError("No space left on device")` → cache-status 写失败不破坏 query / (7-11) 5 build-state 测试各 patch `aiwiki.compile.<step>.write_json_document_if_changed_ignoring_generated_timestamps` 抛 `PermissionError` → compile 完成 + 主输出存在 / (12) grep guard 扫目标文件禁 broad `except Exception` / `except BaseException`。
- **验证**：`bash scripts/verify.sh` PASS — **1818 unittest**（+12）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session round 1 CONCERNS（CRITICAL: 5 compile callsite 用 `__module__` 测试感知分支决定走生产 `write_json_document_if_changed_ignoring_generated_timestamps` 还是 stub `save_*_build_state`，测试只 patch stub 分支 → 生产路径 fail-soft 实际未被验证；MINOR: edges payload 未直测）→ fixer 修：移除全部 5 callsite 的 `__module__` 分支，直接调生产 helper 包 try/except；重写 build-state 测试 patch 各 compile step 模块 namespace 中真实绑定的 `write_json_document_if_changed_ignoring_generated_timestamps`；加 `test_query_cache_corrupt_edges_payload_falls_back` → round 2 fresh oracle PASS（`ses_2072c8fdfffe0FXemS421lGPid`）。
- **Stop Lines**：0 broad `except Exception` / `except BaseException` / 0 SoT 状态 fail-soft（`manifest.json` / `machine-memory.json` / `compile-state.json` / protocol state / receipts / audit / runtime history）/ 0 `load_json_document` / `save_json_document` / `load_json_document_strict` / `CorruptStateError` / `atomic_write_text` 语义改动 / 0 `.aiwiki/cache/machine-memory-graph.json` 改动（视为 required derived）/ 0 explicit `drop_query_cache` CLI 语义 / 0 receipt / manifest schema / 0 LLM raw response（`llm.py:856` 已 fail-soft）/ 0 lock 语义。
- **Residual Risks**：corrupt sqlite db → fail-soft 后 cache 永久 miss 直至下次 explicit `drop_query_cache`，性能退化但功能不破（cache 本意如此）/ disk full 持续 → 每次 warn 日志噪音，未在本轮 scope / `.aiwiki/cache/machine-memory-graph.json` 仍 hard-fail（lint 视作 required derived）/ 未来 LLM cache 需另评估。
- **归档**：contract `.codex/contracts/archive/round-92-cache-failsoft.md`；gate `.codex/gates/qa-review.md` 覆盖为 R92-CACHE-FAILSOFT pass。

### Round 92.4 — Protocol/Manifest Single-File Atomic Writes — 完成

- **目的**：闭环 oracle batch 全仓 review 中的 R92-PROTOCOL-MANIFEST-ATOMIC P1。protocol layer 中 6 处 JSON/state 单文件写入仍裸 `write_text(json.dumps(...))` / `json.dump(...)`，存在 partial-write 窗口（写一半进程被杀 → 文件半写状态留盘 → 下次启动 schema 解析失败 / state 损坏）。Narrow scope：仅 JSON/state，不动 markdown scaffold，不动多文件事务。
- **实现**：
  - `src/aiwiki/app_protocol.py`：`:35` import `atomic_write_text`；`:1700` runtime.yaml default schema / `:1760` runtime.yaml scaffold schema / `:1774` initial protocol.json / `:1808` normalized protocol.json — 4 处 `path.write_text(json.dumps(payload, ...) + "\n", encoding="utf-8")` 全部切到 `atomic_write_text(path, json.dumps(payload, ...) + "\n")`；`:1995` `manifest.json` 从 `with path.open("w") as handle: json.dump(payload, handle, indent=2, sort_keys=True); handle.write("\n")` 改为 `atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")`。
  - `src/aiwiki/app_compile_ops.py`：`:285` import；`:312` active protocol switch 同 pattern 切原子。
  - 保留全部原始 `json.dumps` kwargs（runtime schema：`indent=2 / sort_keys=True / ensure_ascii=False`；protocol state / manifest：`indent=2 / sort_keys=True`），无格式漂移，acceptance fixture 0 改动。
  - 新建 `tests/test_protocol_manifest_atomic.py` 5 测试 + `load_tests` bridge（必需：`scripts/verify.sh` 走 `unittest discover -p 'test_*.py'`，pytest-style 函数无法被收集；模式与 R92.2 `tests/test_machine_memory_action_transaction.py:408-443` 完全一致）：
    - `save_manifest` patch `os.replace` raise → 旧 manifest bytes 不变 + 无 `.tmp` 残留；
    - `set_active_protocol` patch raise → protocol.json 不变；
    - `load_protocol_state` normalization patch raise → 原 JSON 未被半写覆盖；
    - `load_protocol_runtime_schema` default creation patch raise → 无半文件；
    - grep guard 扫 `app_protocol.py` + `app_compile_ops.py` 禁 `write_text(json.dumps(` / `json.dump(`，broad guard 加注释说明意图。
- **验证**：`bash scripts/verify.sh` PASS — **1806 unittest**（+5）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session round 1 FAIL（关键发现：5 新测试虽 pytest 5 passed，但 `unittest discover` 0 tests，count 仍 1801 而非预期 1806；用户特别要求复核的 #6 命中）→ fixer 加 `load_tests` adapter 把 4 个 `tmp_path/monkeypatch` 测试包装为 `unittest.FunctionTestCase`，grep guard 也加入 suite，每 case 独立 `TemporaryDirectory` + `pytest.MonkeyPatch().undo()` 在 finally → round 2 fresh oracle session PASS（`ses_2075a2334ffe4zJfZUFXRcFUpP`，1806 confirmed）。
- **Stop Lines**：0 schema 字段改动 / 0 `runtime_write_lock` / `@runtime_write_operation` 语义 / 0 `execution/protocol_learnings.py`（已 atomic via custom helper）/ 0 `runner/alchemy.py`（R92/R92.1 已覆盖）/ 0 multi-file 跨步事务 / 0 markdown scaffold（`schema/protocols/index.md` / overview.md / sections）/ 0 generic residual writers（`runner/automation.py` / `app_linting/nightly.py` / `agent_loop.py` / `app_execution.py` / `execution/alchemy.py` / `execution/l3_proposals.py` / `runner/auto_adopt.py` — 留 R92-RECEIPT-ATOMIC-EXTEND）。
- **Residual Risks**：multi-file 跨步事务仍非原子（`set_active_protocol` 后续 dashboard/log 写）/ markdown scaffold partial-write 残留（低危）/ generic residual JSON writers 未迁 / `atomic_write_text` dir fsync 失败仅 warning 不 raise（既有，不在本轮范围）/ broad `json.dump(` grep guard 抓不到 alias `path = manifest_path; path.write_text(...)` 形式。
- **归档**：contract `.codex/contracts/archive/round-92-protocol-manifest-atomic.md`；gate `.codex/gates/qa-review.md` 覆盖为 R92-PROTOCOL-MANIFEST-ATOMIC pass。

### Round 92.3 — Drop Input Safety (Bounded Local Ingestion) — 完成

- **目的**：闭环 oracle batch 全仓 review 中的 R92-INPUT-SAFETY P1。`drop_pdf` / `drop_image` / `drop_repo` 本地 ingestion 入口对超大文件 / 非 PDF magic 头 / 非白名单 MIME / 非法 `max_files` 缺乏边界校验：可让 pdftotext / OCR / vision / repo walk 以攻击者控制的输入运行。用户决定**不**做 root containment（保留 Downloads/Desktop drop primary UX）。
- **实现**：
  - `src/aiwiki/drop.py` 新常量 `_LOCAL_PDF_MAX_BYTES = 50 * 1024 * 1024` / `_LOCAL_IMAGE_MAX_BYTES = 25 * 1024 * 1024` / `_SUPPORTED_IMAGE_MIME_TYPES = {"image/png","image/jpeg","image/gif","image/webp","image/svg+xml"}`。
  - 新 helpers：`_assert_file_size(path, max_bytes, label)` / `_assert_pdf_asset(path)`（open + 5 字节 `b"%PDF-"` 校验）/ `_assert_supported_image_mime(mime)`（错误消息含 `sorted(_SUPPORTED_IMAGE_MIME_TYPES)`）/ `_normalize_repo_max_files(max_files)`（int + 1..1000）。
  - 接线：`drop_pdf:240-241` 在 `_extract_pdf_text` 前 `_assert_file_size` + `_assert_pdf_asset`；`drop_image:318-319` 在 OCR / `_analyze_image_asset` 前 `_assert_supported_image_mime` + `_assert_file_size`；`drop_repo:416` 入口 normalize max_files；`_repo_key_files:1344-1348` 加 residual 注释（其自身 `rglob("*")` 不受 max_files 约束，靠 12 selected files 早退，留 future R92-INPUT-SAFETY-WIDE）。
  - `src/aiwiki/cli/parsers.py:1067-1080,1093-1098` drop-pdf / drop-image / `--max-files` help 文案补限制（50MB / 25MB / 支持格式 / 1..1000）。
  - `tests/test_drop_safety.py` 扩 7 测试：oversized PDF/image / 非 PDF magic / unsupported MIME（双 patch `_extract_image_text` + `_analyze_image_asset` 双断言 vision 不可达 + 错误消息含允许集）/ repo max_files 边界参数化 `[0,-1,1001,"10"]` / 正路径 `max_files=10` / 小 PDF happy。
- **验证**：`bash scripts/verify.sh` PASS — 1801 unittest（含 7 新测试）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session round 1 CONCERNS（4 P2: image rejection 未验 vision 不可达 / MIME 错误未列允许集 / CLI help 未文档化限制 / `_repo_key_files` walk 不受 max_files 约束）→ fixer 4 修复 → round 2 fresh oracle session PASS（`ses_2078a47c5ffeT39FAKQvK3cwCx`）。
- **Stop Lines**：0 `safe_fetch` / `_validate_safe_url` / `safe_resolve_within` / SSRF / LLM HTTP / receipt schema / runtime lock / atomic write helper / frontmatter parsing 改动 / 0 root-containment 改动（既有 `_materialize_binary_source` 走 `safe_resolve_within` 不动）。
- **Residual Risks**：size guard 是 post-copy（先复制到 `raw/assets` 再 reject），不硬限本地 ingestion I/O — 留 R92-INPUT-SAFETY-WIDE / `_repo_key_files` 自身 walk 不受 max_files 约束（注释 residual）/ Remote `git clone` host 仍开放（deferred SSRF）/ frontmatter & 其它 CLI path-like args 未做 root containment（用户已选保留 primary UX）/ File magic + MIME 是 coarse guards。
- **归档**：contract `.codex/contracts/archive/round-92-input-safety.md`；gate `.codex/gates/qa-review.md` 覆盖为 R92-INPUT-SAFETY pass。

### Round 92.2 — Machine-Memory Action TX — 完成

- **目的**：闭环 oracle batch 4 全仓 read-only review 中的 R92-MM-ACTION-TX P1。`apply_machine_memory_action` / `revert_machine_memory_action` 三种 apply_mode（`manual-link-state` / `citation-snapshot-refresh` / `resolve-monitor`）原本"事实层先变（manual-links.json / citation page）→ receipt JSON 写 → history append → actions.json save"非原子；任一后续步骤失败留下事实层与 receipt 不一致的半提交窗口。
- **实现**：
  - `src/aiwiki/execution/machine_memory_actions.py` 新增错误类型 `MachineMemoryActionReceiptError`（普通事务失败）/ `MachineMemoryActionHalfWriteError`（rollback 自身失败 loud，绝不静默吞错）+ helpers `_snapshot_file_bytes(path)` / `_restore_file_bytes(path, original_bytes)`（atomic tmp+`os.replace`；`original_bytes is None` → `path.unlink()` 复原"原本不存在"语义）/ `_rollback_snapshots(snapshots) -> list[str]`（返失败列表，调用方据此区分 receipt vs half-write）。
  - `apply_machine_memory_action`：在 mutation 前 snapshot 4 核心路径（`execution_receipt_path` / `execution_receipt_history_path` `.aiwiki/state/execution-receipts.jsonl` / `AUDIT_STREAM_PATH` `.aiwiki/state/audit.jsonl` / `machine_memory_action_state_path` `.aiwiki/state/machine-memory-actions.json`）+ mode-specific（`manual-link-state` 加 `manual_link_state_path`；`citation-snapshot-refresh` 加 citation page bytes）。mutation + receipt JSON `atomic_write_text` + `append_execution_receipt_history` + `_save_machine_memory_action_records` 全部 try 内；except 走 `_rollback_snapshots`，失败列表为空抛 `MachineMemoryActionReceiptError(... was rolled back)`，列表非空抛 `MachineMemoryActionHalfWriteError(... rollback also failed; manual repair required)`，两者均 `from exc` 保 cause。`compile_wiki` / `append_wiki_log` 移到 try 之外的成功后路径。
  - `revert_machine_memory_action`：同 pattern；citation page revert write 从裸 `page.write_text` 切到 `atomic_write_text`；revert receipt 路径 `receipts/reverts/<id>.json` 也走 `atomic_write_text`。
  - `split-overloaded-concept` auto-retire 留 try 内的 best-effort，错误吞进 response 字段（`auto_retire_error` / `auto_retire_skipped_active_corpus`），不入 rollback 范围 — contract 中显式标 residual。
  - 新建 `tests/test_machine_memory_action_transaction.py` 12 测试 + `load_tests` bridge：manual-link happy/rollback × 3 / citation 真实 happy/rollback × 2 + revert citation rollback × 1 / revert manual-link happy/rollback × 2 / resolve-monitor 真实 happy + 真实 rollback × 2 / 真实 `_restore_file_bytes` patch 触发 `MachineMemoryActionHalfWriteError` × 1 / 源码 grep guard 禁止 receipt 与 page 裸 `write_text(json.dumps(...))` × 1。
- **验证**：`bash scripts/verify.sh` PASS — 1794 unittest（含 12 新 TX 测试）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session round 1 CONCERNS（3 测试命名误导：citation/resolve-monitor 名实际跑 manual-link；缺真实 citation apply/revert 与 resolve-monitor 分支覆盖；half-write 仅 patch `_rollback_snapshots`，不验真实 `_restore_file_bytes` 失败）→ fixer 扩 9→12 真实分支 + 测试命名对齐 + 真 restore failure → round 2 fresh oracle session PASS（`ses_207a58043ffe71a5R252pG0Mn3`）。
- **Stop Lines**：0 receipt JSON schema / response 结构改动 / 0 snapshot/rollback helpers 抽到 `app_utils`（保 file-local 与 `app_utils.runtime_write_operation` / `atomic_write_text` 解耦）/ 0 `append_execution_receipt_history` / `append_runtime_history` 既有 audit-rollback 内部事务改动 / 0 `compile_wiki` / `append_wiki_log` 进 rollback 范围 / 0 `split-overloaded-concept` auto-retire 进 rollback。
- **Residual Risks**：`split-overloaded-concept` 下游 `retire_concept` side-effects 不在 rollback 范围（contract residual，已在 code/contract 双层标注）/ `_restore_file_bytes` 仅 bytes restore，不做 dir fsync — 异常恢复 OK，不保 crash-durable / `execution/alchemy.py` legacy/superseded per-action receipt 仍裸 `path.write_text(json.dumps(...))` — out of scope，留 R92-RECEIPT-ATOMIC-EXTEND。
- **归档**：contract `.codex/contracts/archive/round-92-mm-action-tx.md`；gate `.codex/gates/qa-review.md` 覆盖为 R92-MM-ACTION-TX pass。

### Round 92 — Alchemy Apply Lock + Receipt Atomicity — 完成

- **目的**：闭环 oracle batch 4 全仓 read-only review 唯一 P0 半提交风险。`runner/alchemy.py` 7 个 apply/auto/lane 顶层入口"无顶层 lock + 裸 `receipt_path.write_text(json.dumps(...))` + 多步顺序写"，多 writer 并发可同时进入破坏 single-writer 约束；任一后续步骤失败留下"事实层已变 + receipt 未落 / 半 receipt"窗口。M9-P0.1 收口。
- **实现**：
  - **#1 7 装饰器**：`runner/alchemy.py:173,460,631,823,975,1800,1915` 加 `@runtime_write_operation`（`run_alchemy_judge_apply / judge_proposal_apply / distill_apply / review_apply / propose_apply / lane_apply / auto`）。`runtime_write_lock` 是 depth-counted reentrant，嵌套调用不 deadlock；`_run_receipted_lane_primitive` 不加装饰器，依赖外层 lane_apply 已持锁。
  - **#2 7 atomic_write_text**：`runner/alchemy.py:269,413,567,754,907,1111,2312` 7 处 `receipt_path.write_text(json.dumps(...) + "\n", encoding="utf-8")` 切到 `atomic_write_text(receipt_path, json.dumps(...) + "\n")`；新加 `from aiwiki.app_utils import atomic_write_text`。
  - **#3 preview lock 透传**：planner 层 `_preview_runtime_lock` 在自持锁时返 `conflict`（depth>0 + allow_current_writer=False），破坏 apply-under-lock preview；`runner/alchemy.py` 4 个 `run_alchemy_*_preview` + `planner/dry_run.py` 4 个 `preview_*_primitive` 加 `allow_current_writer_lock: bool = False` kwarg 透传到 `preview_alchemy_lane`。apply 内部 5 处 preview + `run_alchemy_lane_apply` 内 `preview_alchemy_lane` + `run_alchemy_auto` 内 `run_alchemy_lane_dry_run` 全部 force `allow_current_writer_lock=True`。
  - **#4 normalize helper**：planner 在 allow_current_writer=True 时返 `lock.status: held_by_current_process`，与 acceptance fixture 期望的 `lock.status: "available"` 不符。新增 `_normalize_preview_lock_status(value)` 30 行递归 helper（`runner/alchemy.py:46-68`）：扫 dict 中所有 `status: held_by_current_process` 节点改回 `available + would_acquire: True`，保 receipt JSON schema / 13 acceptance fixture / 下游 `_materialize_*` helpers 兼容。语义合理：当前进程已持 reentrant lock → 对自己 lock 是可用的。
  - **#5 测试**：新建 `tests/test_alchemy_apply_lock.py` ~160 行 10 测试：`AlchemyApplyLockTests`(7) — 每个入口 patch 最早内部 helper 断言 `_RUNTIME_LOCKS[root]["depth"] >= 1` 后 short-circuit raise；`AlchemyApplyReentrantLockTests`(1) — 外层 `runtime_write_lock` 包 `run_alchemy_judge_apply` 观察 depth=2 内 / depth=1 外 / 无 deadlock；`AlchemyReceiptAtomicWriteTests`(2) — mock `os.replace` 抛错验证 atomic_write_text 不留 partial file + grep guard 扫源码确认无残余 `receipt_path.write_text(json.dumps(`。
- **验证**：`bash scripts/verify.sh` all green（1776 unit + 13 acceptance + branch coverage 92%）；ruff + compileall clean。
- **qa-review**：fresh isolated oracle session PASS（不复用 batch 4 / fixer / 任何旧 session）。Non-blocking observations 留 R92-LOCK-AUDIT：`run_alchemy_judge_propose:309` 仍未加锁（不在合同 7 入口列表）/ legacy migration & superseded cleanup wrappers `:77,89` 未加装饰器 / reentrant 测试覆盖 outer-lock+direct-apply，realistic `lane_apply→_run_receipted_lane_primitive` 嵌套靠 `test_alchemy_lanes.py` 间接覆盖 / grep guard 偏脆 / `_normalize_preview_lock_status` 递归改写所有同形 dict（更稳应只改 `lock` 节点）/ `runtime_write_lock` 在 `flock` 成功后入 try/finally 前异常的 fd/lock 窗口属既有实现风险。
- **Stop Lines**：0 receipt JSON schema 改动 / 0 apply 返回值结构改动 / 0 `_materialize_*` helpers 改动 / 0 通用 `alchemy_apply_decorator` 抽象 / 0 事实层 snapshot-rollback（留 R92-MM-ACTION-TX）/ 0 disable_alchemy_auto 改动（留 R92-LOCK-AUDIT）/ 0 `append_execution_receipt_history` / `append_runtime_history` 既有事务化逻辑改动。
- **拒绝方案**：fixer 第一次实现 300+/54- 越界 — 复刻 250 行 planner.dry_run primitive dispatch 到 alchemy.py + import private `_RUNTIME_LOCKS` + 加 `_preview_primitive_under_lock` / `_presentation_safe_preview_lock` 两 helper；已 stash 弃用，重写为 71+/9- 最小实现。
- **Residual Risks**：事实层多步顺序写仍非原子（留 R92-MM-ACTION-TX）/ atomic_write_text NFS rename 语义弱（既有共享）/ 未识别同类 writer 仍可能存在（grep 已过；oracle 评估未识别新增）。
- **归档**：contract `.codex/contracts/archive/round-92-alchemy-lock-tx.md`；gate `.codex/gates/qa-review.md` status=pass / reviewer_mode=fresh-isolated。

### Round 92.1 — Alchemy Lock Audit (Tight) — 完成

- **范围**：R92 oracle qa-review non-blocking observations 中可在小 diff 内消化的部分。tight scope 共 ~50 行 src diff + 6 新测试。
- **实现**：
  - `runner/alchemy.py` 给 `run_alchemy_judge_propose:326` / `run_alchemy_legacy_migration_apply:92` / `run_alchemy_superseded_cleanup_apply:105` 三个残余 unlocked writers 加 `@runtime_write_operation`（前者 propose 内调 `run_alchemy_judge_preview(allow_current_writer_lock=True)` 兼容 reentrant；后两者下游 `execution.alchemy.apply_legacy_elixir_migration` / `apply_superseded_elixir_cleanup` 走 `append_execution_receipt_history` 已 reentrant safe）。
  - `_normalize_preview_lock_status` 重构：拆为外层 wrapper + `_walk_preview_lock_status(value, *, in_lock_subtree)` 递归。`in_lock_subtree=True` 仅在 dict 进入名为 `lock` 的子键时设置；list 继承父 flag；只有 in_lock_subtree 为真才把 `status: held_by_current_process + would_acquire: False` 改写为 `status: available + would_acquire: True`。避免 R92 旧实现误伤"同形非-lock dict"的风险。
  - 测试：`AlchemyAdditionalApplyLockTests`（3 新装饰器 lock probe）/ `AlchemyLaneNestedLockTests`（lane→primitive 真实嵌套：patch `preview_alchemy_lane` 返 fake plan + patch `run_alchemy_review_preview` 作 probe，让 review_apply 自身装饰器先递增到 depth=2 再观测）/ `AlchemyNormalizeLockStatusTightenedTests`（同形非-lock dict 不被误伤 + nested list-in-lock 仍被规范化）。grep guard 扩为 receipt-like 变量名正则。
- **验证**：`bash scripts/verify.sh` PASS — 1782 unittest（含 16 alchemy lock）+ 13 acceptance + 92% branch coverage + ruff/compileall clean。
- **qa-review**：fresh oracle session round 1 FAIL（`AlchemyLaneNestedLockTests` 早期版本 vacuous：未传 primitives + patch 的 helper 自身无装饰器，depth 期望错位）→ 按 reviewer 推荐重写测试（patch decorated `run_alchemy_review_preview` + 传 `primitives=["review"]` + 严格 `len(observed_depths) == 1`）→ round 2 fresh oracle session PASS（`ses_207e62a2bffe77Kattg64FIHan`）。
- **Stop Lines**：0 接口/schema 改动 / 0 触碰 R92 已 commit 的 7 装饰器和 7 atomic_write_text / 0 wide-scope LOCK-AUDIT-WIDE 项（cli/dispatch / app_routing.datetime.now → utc_now 留单合同）/ 0 `execution/alchemy.py` per-action receipt 裸 write_text:343/551 改动（out of tight scope）。
- **Residual Risks**：grep guard 仍是字符串正则启发式，不抓 alias `path = receipt_path; path.write_text(...)` 形式 / `execution/alchemy.py` legacy/superseded per-action receipt 仍裸 `path.write_text(json.dumps(...))`，但路径外层有 snapshot/rollback —— 这两条留 future R92-RECEIPT-ATOMIC-EXTEND。
- **归档**：contract `.codex/contracts/archive/round-92.1-lock-audit.md`；gate `.codex/gates/qa-review.md` 覆盖为 R92.1 pass。

### Round 91 — Advanced 抽屉信息架构 — 完成

- **目的**：R90 收口后 Advanced 抽屉仍是 5 段平铺（dev banner / Main Header / System status / Legacy Advanced Panel / Knowledge Compounding Metrics），开发者诊断信息和首屏并列，认知负担高。目标：把"以下为开发者诊断信息"提示外置 + 把内容压缩为 3 个默认折叠的语义 section。
- **实现**：
  - **#1 dev banner 外置**：`render_advanced.js:renderAdvancedDrawer` wrapper 顶部直接 `.furnace-advanced-dev-banner`（"以下为开发者诊断信息"），**不再嵌外层 Advanced `<details>`**；三组 section 直接挂 wrapper。
  - **#2 三组语义 section**：`renderAdvancedSection(plugin, parentEl, spec)` 渲染单个 `<details class="furnace-advanced-section-{key}">`：summary 含标题 + 摘要 hint；body 内调 `spec.render(bodyEl)` 包 try/catch；toggle 事件比对 + 持久化。三组：`status`(系统状态—Main Header + Status Panel + Metrics Panel) / `history`(运行与历史—3 入口按钮 + Latest LLM run 摘要) / `devops`(开发者操作—Legacy Advanced Panel)。
  - **#3 折叠态持久化**：`constants.js:DEFAULT_SETTINGS.advancedSectionsExpanded = { status:false, history:false, devops:false }`（默认全折叠）；plugin.js 加 `getAdvancedSectionExpanded(key)` + `async setAdvancedSectionExpanded(key, value)`；setter 检测 `current !== DEFAULT_SETTINGS.advancedSectionsExpanded` 强制 own object（防 `Object.assign({}, DEFAULT_SETTINGS, raw)` 浅拷贝共享引用导致 mutate 默认值）。
  - **#4 summary helpers**：`buildStatusSectionSummary` 读 `shellSummary.protocol/active_protocol` + `currentLlmHealth()` + `currentShellSyncState()` 兜底（未配置/未知/正常/异常）→ "协议 X · LLM Y · 同步 Z"；`buildHistorySectionSummary` 读 `advancedDrawerCounts(plugin)` → "最近运行 N 条 · 待审 R · 待执行 E"；devops 固定 "编译 / 同步 / 协议切换 / 日志等命令"。
  - **#5 renderLegacyAdvancedPanel 去 details**：`render_primitives.js` 改为直接平铺 body 到调用方 container（避免 DevOps section `<details>` 二次嵌套），保留 Compile/Nightly/Set Protocol/Sync 按钮 + Suggested Actions + Quick review/execution/Latest plugin runs 三栏。
  - **#6 翻译键 + 样式**：constants.js +11 键（`系统状态/运行与历史/开发者操作/协议 {protocol}·LLM {llm}·同步 {sync}/最近运行 {n} 条·待审 {review}·待执行 {execution}/编译/同步/协议切换/日志等命令/未配置/正常/异常`等）；styles.css 加 `.furnace-advanced-dev-banner` + `.furnace-advanced-section / -summary / -title / -hint / -body / -error / -actions / -latest-llm*`，自实现 chevron `::before "▶"` + `[open] → rotate(90deg)`。
- **验证**：`bash .obsidian/plugins/furnace-product-shell/build.sh` → main.js 8183 行；`pytest tests/test_product_shell_*` 99 passed；`bash scripts/verify.sh` 13 acceptance pass；`npx jest` 48/48 pass。新增 `tests/test_product_shell_advanced_sections.py`（结构 / 持久化 / 翻译 / built main.js / 历史 body / 无外层 Advanced details / DevOps 不嵌 details）。
- **qa-review**：oracle round 1 fail（2 P1：顶层仍有外层 Advanced details 包住三组 / DevOps section 内嵌旧 renderLegacyAdvancedPanel 的 details）→ round 2 全 PASS（外层去除 + Legacy 平铺 + 浅拷贝防护充分）。非阻塞：DevOps 展开后 Quick review/execution/Latest plugin runs 与"运行与历史"略重叠（R92+ 再优化）。
- **Stop Lines**：不引入第三方 collapse；不改 renderMainHeader/renderStatusPanel/renderLegacyAdvancedPanel/renderAdvancedMetricsPanel 子组件签名；三组默认全折叠；不动 today_feed.py↔js mirror。
- **归档**：contract `.codex/contracts/archive/round-91-advanced-drawer-ia.md`；gate `.codex/gates/qa-review.md` status=pass。

### Round 90 — 提交→状态→结果 闭环 — 完成

- **目的**：oracle PM/UX 三轮评估给到 8.2/10，剩余两个最大痛点：done 卡 4s 自动消失令人焦虑（用户在卡片消失前还来不及反应）+ 首屏没有"刷新炉子"主动同步入口；目标 8.2→8.7。
- **实现**：
  - **#1 done 卡变行动卡**：`markPendingSubmissionDone(id, target, reconcilePath)` 移除 4s `setTimeout`，新增 `reconcilePath` 参数；render_today done 分支不再静默消失，渲染按钮 outputs→「打开报告」`.furnace-pending-open-report-btn` / receipts→「查看回执」`.furnace-pending-open-receipt-btn` + 共用「完成」`.furnace-pending-done-btn`(removePendingSubmission)。done 卡颜色变绿（`.furnace-pending-done` 左 border + status text 走 `--text-success`）。
  - **#2 reconcile 提取 path**：`reconcilePendingSubmissions` 从 hitCand 提 `path`（outputs:`hitCand.path` / receipts:`hitCand.path||hitCand.receipt_path`），通过 `hits[{id,target,path}]` 传给 markDone；`serializePendingSubmissions/hydratePendingSubmissions` 加 reconcilePath 字段；done 7 天 TTL（`finishedAt` 缺失退 `startedAt` 兜底）。
  - **#3 顶部刷新炉子 + last updated**：render_today 标题行改 `.furnace-today-feed-head`：标题 + `.furnace-today-refresh-btn`「刷新炉子」（disabled 切换 + try/catch + Notice）+ `.furnace-today-last-updated`；plugin 新增 `getLastSummaryRefreshLabel()` 4 档（`刚刚 / N 分钟前 / N 小时前 / N 天前 / 未刷新`）+ clamp 未来时间 `Math.max(0, ...)`。
  - **#4 受信 refresh + 退化路径**：`refreshShellSummaryCommand()` 改成 try/catch 包 `runPluginCommand` 后 **无条件** `await loadShellSummaryFromDisk()` —— 保证无论 launcher payload 形态如何都触发基于磁盘 summary 的 reconcile。`openWorkspacePath(path)` 改返 boolean（成功 2 处 return true / 失败 4 处 return false：no path / repo missing / not found / no adapter）；既有调用方不读返回值，无破坏。新增 `openPendingDoneTarget(target, path)`：基于 boolean 决定退化路径 outputs→`openOutputsHub()`+Notice / receipts→`openRecentRunsView()`+Notice / 兜底 `openHomeNote()` + 最终兜底 Notice "无法打开目标，可能尚未生成"。
  - **#5 received stale 文案校准**：`已接收，等待生成报告 / 可能已完成，点下方刷新状态`（指向 received 卡上自带的"刷新状态"按钮，不再依赖顶部刷新）。running 卡也加「刷新状态」让用户主动同步。
  - **#6 翻译键 + 样式**：constants.js 加 `刷新炉子 / 刷新状态 / 打开报告 / 查看回执 / 完成 / 未刷新 / 刚刚 / {n} 分钟前 / {n} 小时前 / {n} 天前 / 已打开输出汇总（找不到具体报告路径）/ 已打开运行记录（找不到具体回执路径）/ 无法打开目标，可能尚未生成`；styles.css 加 `.furnace-today-feed-head / .furnace-today-feed-title / .furnace-today-feed-refresh / .furnace-today-refresh-btn / .furnace-today-last-updated / .furnace-pending-refresh-btn / .furnace-pending-open-report-btn / .furnace-pending-open-receipt-btn / .furnace-pending-done-btn / .furnace-pending-done`。
- **验证**：`bash build.sh` → main.js 7992 行；pytest pending_card 30/30 + today_feed 16/16 = 46 测试全过；全量 1739 + 13 acceptance 全过；jest 48/48 全过。
- **qa-review**：oracle round 1 fail（3 P1：done 行动按钮 fallback 静默失效 / receipts 缺 path 调不存在的 openAdvancedDrawer / refreshCommand 不保证基于磁盘 reconcile）→ round 2 fail（P1-1 未完全解：openWorkspacePath 失败时不 throw 导致 helper 误判成功）→ round 3 全 PASS。
- **Stop Lines**：done 卡不自动消失（必须用户主动「完成」）；不引入 openAdvancedDrawer 不存在的方法；不破坏既有 openWorkspacePath 调用方（boolean 返回向下兼容）；reconcile 路径与首屏刷新走同一条管道。
- **归档**：contract `.codex/contracts/archive/round-90-submit-status-result-loop.md`；gate `.codex/gates/qa-review.md` status=pass。

### Round 89 — PM/UX 信任闭环 + 文案统一收口 — 完成

- **目的**：闭环 R88 PM/UX 二轮评估（oracle 7/10）残余 3 大痛点：pending 关闭重开断链、提交语义错位（接收=报告）、首屏机制词与中英混用。
- **实现**：
  - **#1 pending 持久化**：plugin.js 新增 `serializePendingSubmissions/hydratePendingSubmissions`；写入 `settings.persistedPendingSubmissions`；onload 期间 hydrate（保留 displayText 120 / payload fingerprint 80 截断）；TTL 24h running 自动降级 failed 并附文案 "上次提交可能仍在处理或已完成…"；cap 8。
  - **#2 状态机两段式**：status 枚举 `running|received|done|failed`；新 helper `markPendingSubmissionReceived(id)` 与 `markPendingSubmissionDone(id, target)`；render_input handleSubmit 成功 → markReceived（不自动消失）；reconcile 命中 → markDone(target="outputs"|"receipts") → 4s remove；render_today 三态分文案（received="已接收，等待生成报告" / done outputs="报告已生成" / done receipts="已记录" / received >12h stale="可能已完成，点上方刷新"）。
  - **#3 race 防御**：markReceived `if status !== "running" return`（防 reconcile 抢先升 done 后被回退）；markDone `if status === "done"|"failed" return`（防重复 4s setTimeout）。
  - **#4 失败卡 + 重试**：render_today 失败卡上方加通用 hint "这次没成功。可以点重试，或检查输入是否完整。"；retry 成功路径统一改 markReceived（与 handleSubmit 同语义）。
  - **#5 文案统一**：constants.js `Today: "今日" → "今天"`；render_input 三处 hint "结果会出现在 Today" → "结果会出现在“今天”"；today_feed groupSpecs 中文化（Reports→新报告 / Automation→系统动态 / Needs Your Confirmation→需要你确认 / Completed→已完成 / Suggested Actions→下一步建议）。
  - **#6 Advanced 抽屉分隔**：render_advanced.js drawer body 顶部插入 `.furnace-advanced-dev-banner` "以下为开发者诊断信息"，把 LLM/run history/system 等开发者层面板与首屏视觉分层。
- **验证**：pytest pending_card 23/23 + today_feed 9/9 + 全量 1739 + acceptance 13 全过；jest 48/48 全过；`bash scripts/verify.sh` 全过。
- **qa-review**：oracle round 1 fail（3 P1：reconcile-race 回退、retry 用 markDone 破坏两段式、Today/今天未闭环）→ round 2 全 PASS。
- **归档**：contract `.codex/contracts/archive/round-89-pm-ux-trust-loop.md`；gate `.codex/gates/qa-review.md` status=pass。

### Round 88 — PM-UX 三件套（空态 CTA / 处理中卡片 / 文案白话化）— 完成

- **目的**：从 PM 角度把"用户投了东西看不到反馈 + 满屏机制词"这两个最伤的体验问题闭环掉。
- **实现**：
  - **#1 Today 空态 CTA**：`render_today.js` 抽 `renderTodayEmptyCta(plugin, parentEl, viewRoot)`；`!summary` 与 `feed.length===0` 两条空态分支都渲染「投一份材料」按钮，click 优先在 `.furnace-shell-view` 内查 `.furnace-universal-input-textarea` 并 `focus + scrollIntoView`，不做跨视图全局 fallback。
  - **#2 提交后"处理中"卡片**：plugin.js 新增 `pendingSubmissions[]` runtime-only state（不持久化）+ `pushPendingSubmission/markPendingSubmissionDone/markPendingSubmissionFailed/removePendingSubmission/resetPendingSubmissionForRetry/reconcilePendingSubmissions` 6 个 helper；`render_input.js` handleSubmit push→done/failed 双路径，retryArgs 带 `kind:"text"|"files"`；`render_today.js` `renderPendingSubmissionsGroup` 顶部独立 group，失败态卡片含「重试」（resetForRetry → run → markDone/markFailed 同卡循环）+「Dismiss」。
  - **#3 reconcile 收紧（P1 第二轮）**：candidate 必须含 `created_at/generated_at/applied_at/occurred_at/timestamp` 任一且 `candMs + 60s skew >= startMs`；匹配字段扩到 `title/path/summary/payload/receipt_path/output_path/query/target`；短指纹 (<16 char) 走 normalized exact 匹配，长指纹至少 60 char 前缀；title ≥4 char 才参与；超 5min 的 running 卡片仅停止 reconcile，push 进 remaining 保留显示（长任务保护，不再丢卡）。
  - **#4 dedupe**：pushPendingSubmission 同 fingerprint+running 直接复用 dup.id，双击/多入口不会重复堆卡。
  - **#5 文案白话化**：plugin.js 503/544、constants.js 90/92/112/295/301、render_execution.js / render_review.js / render_primitives.js / state/health-state.js 全部把 "shell-summary.json" / "Click Refresh first" / "Runtime Events from shell-summary" 等机制词替换为"数据还没准备好"/"运行事件"等白话；constants 翻译表加 self-key→self-key 兼容映射。
  - **#6 Recent Runs 抽屉文案**：render_execution.js 顶栏 "最近收据" → "最近运行记录"；render_primitives.js LLM Health "Copy receipt path"/"Copy stderr" 翻译表 → "复制运行记录路径"/"复制诊断信息"；render_runs.js 抽屉内 stdout/stderr/Open receipt 等技术按钮保留，定位为开发者层。
  - **样式**：styles.css 加 `.furnace-pending-card` + pulse 动画 + 失败态错误文本 + CTA 按钮样式。
- **测试**：`tests/test_product_shell_pending_card.py` 12 case（pending helpers 暴露 / built-into-main / render_input 接入 / today group 渲染 / reconcile hooked / 空态 CTA / 文案 dejargon / reconcile timestamp+fields+useExact / 超窗保留 running / dup-fingerprint 复用 / retry 不删卡 / !summary CTA）。
- **Stop Lines**：pendingSubmissions 不入 buildTodayFeed（不污染 today_feed.js↔py mirror 契约）/ runtime-only 不持久化 / 不改 today_feed.py / Recent Runs 技术按钮保留开发者层 / 不动 dogfood `output/control/shell-summary.json`。
- **验证**：`bash build.sh` → main.js 7698 行；`npx jest` 48/48；`bash scripts/verify.sh` exit=0（13 acceptance + 全量 unit + coverage 92%）；`tests/test_product_shell_pending_card.py` 12/12。oracle qa-review 第一轮 6 个 P1（无 P0），整改后第二轮全 6 项 PASS、无新 P0/P1，可收口。

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
