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


## 当前动态

- 2026-05-12 (P4-INV-NEW-1 adaptive run-compile timeout 收口 F-INV-NEW-1)：`run-compile` 在 `create_client` 前按 pending 队列里最大 raw 字节自适应估算 per-call timeout。`src/aiwiki/runner/workflows.py` 新增 `_compute_adaptive_compile_timeout(root, pending)` helper，常量 `BYTES_PER_PAGE=30_000` / `SECONDS_PER_PAGE=60` / floor 240 / ceil 1800，公式 `clamp(ceil(max_bytes / 30_000) * 60, 240, 1800)`。语义：env `AIWIKI_LLM_TIMEOUT` 显式设置 → 返回 `None`（env 永远赢，`LLMConfig.from_env` 沿用）；pending 为空 → `None`；pending 非空但所有 stored_path 都不可 stat / 越出 vault root（含 abs path / `..` 穿越） → 回退 floor 240s。Containment guard 用 `root.resolve()` + 每条 `raw_path.resolve()` + `relative_to(root_resolved)`。Helper 在 paths filter 之后执行，只看真正会喂给 LLM 的子集。**不动** `LLMConfig.timeout_seconds=120` 默认 / CLI surface / receipt/audit/runtime-history schema / 现有 backend。`tests/test_runner.py` 加 6 个 adaptive test（empty→None / large→1800 cap / small→240 floor / env override→None / all-unstatable mixed (missing+abs+`..`+empty+non-dict)→floor / 3-entry largest-wins→600s）。`docs/Furnace Investing Dogfood Plan.md` §2.3 加 adaptive 公式 + 三条规则。verify PASS（unit + 17 acceptance + 92% cov + ruff clean）；fresh oracle qa-review r1 REQUEST_CHANGES（docstring/docs 与 empty-pending 行为不一致 + 缺 containment guard + 缺 unstatable/largest-wins test）三处全修后 r2 APPROVE_WITH_NITS（ses_1e46b7d9affebphzcdKdjaolc9，唯一 nit：可选 integration test patch create_client，不阻塞）。下一步 P4-INV-NEW-2：run-compile fail-fast 写 execution-receipt。
- 2026-05-12 (Investing Dogfood v2 真实研报实跑 5/7 闭环)：3 份真 PDF（韦尔 274p / 宁德 229p / 恒瑞 249p）走完 §2.1-§2.6。backend=opencode-api/deepseek-v4-pro；run-compile 1211s（`AIWIKI_LLM_TIMEOUT=600`）→ 3 source pages 全 compiled；3 file-back judgment 全 confirmed；2 settled elixir（主丹 `elixir-ai-thesis-2024-97f9dc26` + 复利丹 `elixir-vs-thesis-b8dadbd3`，`derived_from` 跨丹引用 + trace --direction up 递归可见）。Step 4 drift_scan stale_judgments 闭环验证 PASS：手工 backdate 韦尔 `last_reviewed` 至 2 天前，`STALE_JUDGMENT_DAYS=1` + `AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=1` 触发 nightly → `drift_aging.signals_appended=1`，新 signal 落 `.aiwiki/state/signals.jsonl`（kind=drift, severity=medium, judgment_refs=[韦尔]）。Receipt 落盘：`output/reports/dogfood-receipt-investing-v2.md`（vault），file-back→review confirmed。**4 个新摩擦点 F-INV-NEW-1~4**：(1) `AIWIKI_LLM_TIMEOUT` default 120s 对中文年报严重不足；(2) `run-compile` fail-fast 未落 execution-receipt；(3) `ask --include-elixir` 文档与 CLI 不一致（实际入口在 alchemy-start）；(4) `trace` 不识别 derived 资产 kind。**F-INV-11 仍开放**：counter_evidence 走 NONE_FOUND 兜底通过，非真材料反证。§2.7 L3 proposal 留 v2.1。
- 2026-05-12 (D L3 proposal apply→revert acceptance Gap D 收口)：L3 governance lane create→apply→revert 三步链上提到 acceptance 层。新 fixture `tests/fixtures/acceptance/D/case_l3_proposal_apply_revert/`（seed `prompts/test-prompt.md` + 7 byte-stable golden：target / `.aiwiki/state/l3-proposals.json` / 2 receipts (apply/revert) / runtime-history / audit / wiki log）。`tests/acceptance/case_runner.py` 加 `_run_l3_proposal_apply_revert(vault, *, target_file, new_content, proposal_id, kind)` helper 真调三函数（非 stub），并 `_copy_case_and_fix_clock_from` 补 `monkeypatch.setattr("aiwiki.execution.l3_proposals.utc_now", ...)`（module-local binding via `from aiwiki.app_utils import utc_now`）+ `monkeypatch.delenv("AIWIKI_DISABLE_AUTOMATION", raising=False)`（kill switch 不应影响 acceptance）。`test_acceptance_no_stop_line_violations` 给 D 子树加精确例外（`rel == case or rel.startswith(case + "/")`），仅放过 `l3-proposal-apply` 一词，其余四个 forbidden 词全树仍禁。测试除 7 golden 字节相等外，断言 hash invariants：`revert.restored_hash == apply.before_hash` + `apply.after_hash != revert.restored_hash`。acceptance 16 → 17；verify PASS（unit + 17 acceptance + 92% coverage + ruff clean）；fresh oracle qa-review 一轮 REQUEST CHANGES 三个 finding 全修后 APPROVE（ses_1e535c7a9ffeuU1bt4wGevlX0m）。**Gap A/B/C/D（PROGRESS slim / drift_scan / drop_url / L3 proposal apply-revert）全部收口**。
- 2026-05-12 (C drop_url acceptance Gap C 收口)：`drop_url` end-to-end materialization 上提到 acceptance 层。`tests/fixtures/acceptance/C/case_drop_url/` 新建（空 vault root + 4 byte-stable golden：`raw/inbox/agent-architecture-survey.md` / `wiki/indexes/log.md` / `.aiwiki/state/runtime-history.jsonl` / `.aiwiki/state/audit.jsonl`）。`tests/acceptance/case_runner.py` 加 `_run_drop_url(vault, monkeypatch, *, url, title=None, fetched=None)` helper（patch `aiwiki.drop._fetch_url` 唯一外部边界 + 默认 fetched payload `image_urls=[]` 避开 asset 不稳路径）。`test_drop_url_writes_raw_note_and_logs` 断言 result dict shape (material/note_path/final_url/asset_paths=[]) + 4 golden。范围窄：drop_pdf/image/repo 由现有 unit test 覆盖。acceptance 15 → 16；verify PASS（2125 unit + 16 acceptance + 92% coverage + ruff clean）；fresh oracle qa-review APPROVE 一次过（ses_1e570f42affeFj4yatk0zyZ6QF）。
- 2026-05-12 (B drift/aging acceptance Gap B 收口)：`drift_scan` 三个扫描器（stale judgments / changed evidence / dependency breaks）上提到 acceptance 层。`tests/fixtures/acceptance/B/case_drift_scan/` 新建，含 1 stale judgment + 1 elixir w/ drifted+stale citation_snapshots（`raw/evidence.md` digest 故意错 + `raw/missing.md` 不存在）+ 1 elixir w/ broken `derived_from`，golden 覆盖 `.aiwiki/state/{drift-aging.json, signals.jsonl, runtime-history.jsonl, audit.jsonl}` 字节稳。`tests/acceptance/case_runner.py` 加 `_run_drift_scan(vault, monkeypatch, now=...)` helper（函数级直调避开 CLI 不存在 + nightly 无关 determinism；显式 `delenv AIWIKI_STALE_JUDGMENT_DAYS` + `monkeypatch uuid.uuid4 version=4` 在 helper 内部，避免 leak 到 collector path）。acceptance 14 → 15；verify PASS（2125 unit + 15 acceptance + 92% coverage + ruff clean）；oracle qa-review APPROVE after fixes（ses_1e58d3070ffemOz03PdcVDGNxv）。
- 2026-05-12 (D-3 acceptance Gap P1 收口)：D-3「金丹复利」从 unit-only 上提到 acceptance 层。新增 fixture `tests/fixtures/acceptance/D3/case_elixir_stage3_compounding/`，跑 5 步 CLI 链（alchemy-start/distill/finalize/promote + trace up），断言新丹 `derived_from` 含旧丹 + derived anchor / promote bundle 含 counter_evidence / `trace up` 递归 parents / 3 state JSONL byte-stable。`tests/acceptance/case_runner.py` 加 monkeypatch 把 `app_execution.datetime` + `execution.alchemy.datetime` 也 patch 成 `_FixedDateTime`（之前只 patch `utc_now`，promote receipt epoch_ms 走 `datetime.now(timezone.utc)` 泄漏）。acceptance 13 → 14；verify PASS（2125 unit + 14 acceptance + 92% coverage + ruff clean）；oracle qa-review PASS（ses_1e5c14353fferejeB7qf8aa4uG）。
- 2026-05-12 (SC-010 Structural Consolidation Sweep 完结)：清理 SC-008 fresh oracle 两条 non-blocking follow-up。`src/aiwiki/drop.py` `_LOGGER` 定义上移到模块顶部 constants 区；`tests/test_drop_phases.py` 新增 integration test `test_drop_pdf_finally_cleanup_logs_warning_on_rmtree_failure`（prefix-selective rmtree wrapper 不污染测试环境）。verify PASS；fresh oracle qa-review PASS（ses_1e5fbd4cfffek862Ps5zD09BDA）。**Structural Consolidation Sweep（SC-001..SC-010）整体收官**。完整 SC-001..SC-010 详情见 `archive/rounds/structural-consolidation-sweep.md`。
- 2026-05-11 Product UX Rectification Sweep (R97~R108 EP-001..EP-007) 详情见 `archive/rounds/ep-001-ep007-product-ux-sweep.md`。
- 2026-05-09：Product Shell + runtime LLM provider profile 整理完成；默认 route `opencode-api/deepseek-v4-pro`；NVIDIA NIM fallback 保持 `nvidia-nim-api/openai/gpt-oss-120b`；verify PASS（2001 unittest + 13 acceptance，coverage 92%），Product Shell Jest PASS（55 tests）。

## Milestone Quick Index

> 每行只保留世代 / Milestones / 一句主旨 / 状态。完整实现细节、Stop Lines、Residual Risks 见 `archive/rounds/milestone-quick-index-detail.md`。

| 世代 | Milestones | 状态 |
|---|---|---|
| **P4 Dogfood-driven** (2026-04-28) | P4-1a~1d, P4-2~6, P4-9, P4-11, P4-15 | ✅ 全部 done |
| **D 系列** (2026-04-30) | D-1~D-4 + D-3 R1 + D-4 v0/v1 | ✅ 全部 done |
| **P4-INV** (Round 57-59) | P4-INV-1~4 | ✅ 全部 done |
| **Post-R61 改进** (2026-05-03) | harness 增量升级 / QA review 启用 / plans-merge / Round 62/63 UI Polish | ✅ Round 62/63 done / 其余 🔄 |
| **Round 64-66 UX Earnest** (2026-05-03) | 命名去时间戳 / 拖放修复 / 面板精简 / L3 自动采纳 / 图谱锚点 / 导航简化 | ✅ 全部 done |
| **Round 67 Auto-adopt Hardening** (2026-05-04) | judgment review / L3 audit / nightly aggregation / strict JSONL | ✅ done (`6711efd`) |
| **Round 67.5 Acceptance Fixture Refresh** (2026-05-04) | M6.1b prompt_hash drift refresh | ✅ done (`284f8af`) |
| **Round 68 Progress Slimming** (2026-05-04) | PROGRESS 三层瘦身 / rounds archive / stop_line_audit lint | ✅ done (`2c408f9`) |
| **Round 69 Atomic State I/O** (2026-05-04) | `atomic_write_text` + `atomic_append_jsonl` helpers / 4 saver 替换 | ✅ done (`7ee3ab8`) |
| **Round 70 Receipt JSONL 事务化** (2026-05-04) | 12 JSONL writers 全量原子化 / mm revert 双 receipt + `reverts/` 子目录 | ✅ done (`950f291`) |
| **Round 71 Fetch & Path 安全** (2026-05-04) | `safe_fetch` + `safe_resolve_within` / SSRF / repo symlink 跳过 / Playwright route 拦截 | ✅ done (`a6074b9`) |
| **Round 72 Lock 高优先级缺锁补齐** (2026-05-04) | drop_* 五入口 + nightly_health + receipt_history 全加 `runtime_write_lock` | ✅ done (`addd53d`) |
| **Round 73 LLM/notify HTTP 安全** (2026-05-04) | `safe_fetch` 扩 POST + headers + redirect strip auth / llm.py + notify.py 切换 | ✅ done (`c0cf944`) |
| **Round 74 L3 事务化 + audit auto-revert** (2026-05-04) | `apply_l3_proposal` 后半 5 步 TX / `L3PostApplyAuditError` 携带证据 / auto_reverted runtime_history | ✅ done (`b6a64f5`) |
| **Round 75 receipt_history TX** (2026-05-04) | `_durable_truncate` / `ReceiptHistoryAuditError` + `ReceiptHistoryRollbackError` / R74 残余关闭 | ✅ done |
| **Round 76 runtime_history TX + audit-mirror 上移** (2026-05-04) | `_durable_truncate` + AuditMirror* 上移 `app_utils` / R75 API 保持 | ✅ done |
| **Round 77 LLM receipt TX** (2026-05-04) | `_append_llm_receipt` snapshot-then-rollback / 复用 AuditMirror* | ✅ done |
| **Round 78 age audit single-file TX** (2026-05-04) | `_durable_restore_or_remove` / `_write_age_audit` snapshot bytes | ✅ done |
| **Round 79 auto_adopt 顶层 lock** (2026-05-04) | 4 个 `auto_adopt_*` 入口加 `@runtime_write_operation` / reentrant | ✅ done |
| **Round 80 safe_fetch response close** (2026-05-04) | urlopen response 用 `with` 包；R71-R73 残余关闭 | ✅ done |
| **Round 81 citation snapshot path guard** (2026-05-04) | `safe_resolve_within` + wiki/judgments\|decisions 白名单 | ✅ done |
| **Round 82 citation revert guard 对称收口** (2026-05-04) | `revert_machine_memory_action` citation 分支复用同 helper | ✅ done |
| **Round 83 safe_fetch DNS pinning + host allowlist** (2026-05-05) | pinned-IP connect / proxy 禁用 / SNI 保留 / opt-in allowlist | ✅ done |
| **Round 84 fail-soft 收口 + 事实层 strict read 迁移** (2026-05-05) | notify 双层 fallback / `load_runtime_history_strict` / 6 callers 切 strict | ✅ done (`c94cc87`) |
| **Round 85 history JSONL strict migration** (2026-05-05) | execution policy/receipt history strict variants / fact-layer 切 strict | ✅ done (`ea08d6e`) |
| **Round 86 safe_fetch 多 IP fallback** (2026-05-05) | R83 pinning 可用性回归修复 / resolver 顺序循环 TCP | ✅ done (`b345ecf`) |
| **Round 87 R85/R86 non-blocking 小补丁** (2026-05-05) | history strict 测试断言收紧 / HTTPS fallback `wrap_socket` 单次 | ✅ done (`0891a44`) |
| **Round 88 PM-UX 三件套** (2026-05-05) | Today 空态 CTA / "处理中" 卡 state machine / 面板文案白话化 | ✅ done |
| **Round 89 PM/UX 信任闭环 + 文案统一** (2026-05-05) | pending 持久化 / 状态机两段式 / Today→今天 / groupSpecs 中文化 | ✅ done |
| **Round 90 提交→状态→结果 闭环** (2026-05-05) | Today "刷新炉子" + last-updated / pending 行动卡 / done TTL 7d | ✅ done |
| **Round 91 Advanced 抽屉信息架构** (2026-05-05) | dev banner 外置 / 三组可折叠 section + 持久化 | ✅ done |
| **Round 92 Alchemy Apply Lock + Receipt Atomicity** (2026-05-05) | runner/alchemy.py 7 入口加 lock / 7 receipt write 切 atomic / preview 透传 | ✅ done |
| **Round 92.1 Alchemy Lock Audit (Tight)** (2026-05-05) | 3 残余 unlocked writers 加 decorator / `_walk_preview_lock_status` 双函数 | ✅ done |
| **Round 92.2 Machine-Memory Action TX** (2026-05-05) | `apply/revert_machine_memory_action` snapshot/rollback / 3 apply_mode / `MachineMemoryActionReceiptError` | ✅ done |
| **Round 92.3 Drop Input Safety** (2026-05-05) | 本地 ingestion 边界：PDF 50MB / image 25MB + MIME 白名单 / repo max_files normalize | ✅ done |
| **Round 92.4 Protocol/Manifest 单文件原子写** (2026-05-05) | 6 处 protocol/manifest JSON 切 `atomic_write_text` | ✅ done |
| **Round 92.5 Cache Layer Fail-Soft** (2026-05-05) | SQLite query cache 8 boundary fail-soft / 5 compile build-state save fail-soft | ✅ done |
| **Round 92.6 Lock Audit Wide** (2026-05-05) | 7 个 SoT/state writer 入口加 lock 保护（Tight 5 + Standard 2 conditional） | ✅ done |
| **Round 92.7 Deploy/Service Defaults Hardening** (2026-05-05) | systemd installer 默认 deny-by-default / `AIWIKI_VAULT` 强制 / lock timeout / remote repo opt-in | ✅ done |
| **Round 92.8 Feed Parity (Universal Input)** (2026-05-12) | `recent_raw_inputs` summary + plugin reconcile / extractPrimaryPath 扩展 / 不新增 FeedKind | ✅ done |
| **Round 92.9 DETERMINISM compile gate** (2026-05-10) | compile log timestamp-insensitive gate | ✅ done (`f153589`) |
| **Round 92.10 TEST SPLIT test_app.py** (2026-05-10) | 7984 行拆 7 个 focused 文件 / 总 test count 不变 | ✅ done (`00b41ad`) |
| **Round 92.11 PERF Benchmark** (2026-05-10) | measurement-only `compile_wiki` benchmark / 不接 CI gate | ✅ done (`0944726`) |
| **Round 93.0 autonomy_policy fail-closed** (2026-05-11) | malformed → `CorruptStateError` / `load_autonomy_policy` 切 strict | ✅ done (`7e43e4e`) |
| **Round 93.1 material-archive TX 雏形** (2026-05-11) | `apply/revert_archive_action` 早期 receipt-tier TX；R95.1 接续 | ✅ done (`37c9341`) |
| **Round 93.2 compile-artifact 原子写** (2026-05-11) | compile pipeline 派生 artifact 全切 `os.replace` 原子路径 | ✅ done (`6d2cee6`) |
| **Round 93.3 ingest subprocess timeout** (2026-05-11) | `drop.py` ingest subprocess 加 `timeout=` / `IngestionTimeoutError` | ✅ done (`137aa4e`) |
| **Round 94.0 automation.json 原子写** (2026-05-11) | `atomic_write_text` + `fsync=True` / `load_automation_state` strict + corrupt 回收 | ✅ done (`0ddc2c7`) |
| **Round 94.1 drift_scan → append_runtime_history** (2026-05-11) | drift_scan 改走 `append_runtime_history` 复用 R76 TX + audit-mirror | ✅ done (`6bf39e0`) |
| **Round 94.2 ingest_source raw/ atomic + orphan tmp 跳过** (2026-05-11) | raw write 切 atomic + fsync / raw scanner 过滤 `*.tmp.*` | ✅ done (`4ba29e9`) |
| **Round 94.3 mm-action read-then-write fail-closed** (2026-05-11) | `apply/revert_machine_memory_action` 切 `load_json_document_strict` | ✅ done (`a85f599`) |
| **Round 94.4 concept rewrite apply/revert TX** (2026-05-11) | file + state pair TX / reversed write-order rollback | ✅ done (`ecef27f`) |
| **Round 94.5 L3 Proposal apply/revert TX** (2026-05-11) | file + receipt + state triple TX / `L3{Apply,Revert,Reject}{ReceiptError,HalfWriteError}` | ✅ done (`b093241`) |
| **Round 95.1 archive apply/revert TX** (2026-05-11) | receipt+state pair TX / phase-2 derived audit swallow-with-warning（设计保留） | ✅ done (`a49ead8`) |
| **Round 95.2 drop.py raw note + asset atomic** (2026-05-11) | raw note + asset 全切 `atomic_write_text` / `atomic_write_bytes` + `fsync=True` | ✅ done (`0731823`) |
| **Round 95.3 L3 Phase-2 False-Write Truncate** (2026-05-11) | `_durable_truncate(path, snapshot_size)` 截回 commit 前长度 | ✅ done (`70ff772`) |
| **Round 95.4 Nightly Audit Reconciler** (2026-05-11) | `reconcile_execution_receipts` nightly 检 false-success / 仅扫 `revert` | ✅ done (`3679079`) |
| **Round 96.0 alchemy receipt persistence TX** (2026-05-11) | `_persist_receipt_transactionally` 收口 receipt-tier TX 范式 | ✅ done (`4b3e32f`) |
| **Round 96.1 alchemy review_apply TX** (2026-05-11) | `run_alchemy_review_apply` receipt-tier TX | ✅ done (`8a4dd91`) |
| **Round 96.2 alchemy lane primitive Receipt TX** (2026-05-11) | `_run_receipted_lane_primitive` wrapper TX | ✅ done (`44100e2`) |
| **Round 96.3 alchemy distill/propose_apply TX** (2026-05-11) | `run_alchemy_distill_proposal_apply` / `run_alchemy_propose_apply` TX | ✅ done (`1db7925`) |
| **Round 96.4 create_l3_proposal TX** (2026-05-11) | state + page + history + audit + wiki-log 全包 receipt-tier TX | ✅ done (`4df35ea`) |
| **Round 96.5 mm_action_batch Receipt-Tier TX** (2026-05-11) | `apply_machine_memory_actions_batch` snapshot/rollback 全包 | ✅ done (`5aa4a92`) |
| **Round 96.6/96.7 L3 Phase-2 Audit Swallow DROP** (2026-05-11) | fresh oracle pre-design DROP；决议归档 `.codex/contracts/archive/R96.6/96.7-*.md` | ❌ dropped |
| **Round 96.8 apply_l3_proposal Rollback 跨流一致** (2026-05-11) | 外层 rollback 顺序 reversed write-order；补 `runtime_history_path` 还原 | ✅ done (`f2c9f5a`) |
| **Round 96.9 L3 Apply Phase-2 Audit Reconciler 扩流 DROP** (2026-05-11) | fresh oracle pre-design DROP；决议归档 `.codex/contracts/archive/R96.9-*.md` | ❌ dropped |
| **Round 97 Decision-grade Report Skeleton** (2026-05-11) | `output_format=report` 升级到 6 区块固定骨架 + `_validate_report_sections` | ✅ done |
| **Round 98.1 Decision-grade Report Bullet Minimums** (2026-05-11) | 每段 `- ` bullet 下限 + 拒 `_LLM:` placeholder 残留 / fence-aware bullet counter | ✅ done (`ae9e19f`) |
| **Round 98.2 Report Citation Integrity** (2026-05-11) | `## 引用` dedup + body ⊆ citations 校验 / fence-aware path 提取 | ✅ done |
| **Round 98.3 Report Strictness Hardening** (2026-05-11) | Phase 0 unclosed fence 拒绝 + Phase 1.5 duplicate required H2 拒绝 | ✅ done |
| **Post-P4 D-2 PROGRESS Slim** (2026-05-12) | Round 73-92.7 + Milestone Quick Index detail 切档归档 / PROGRESS 117KB→18.5KB | ✅ done (`c472677`) |
| **Post-P4 B drift_scan Acceptance** (2026-05-12) | drift_scan 三扫描器函数级 acceptance / 4 byte-stable golden / 15 cases | ✅ done (`54d7e2c`) |
| **Post-P4 C drop_url Acceptance** (2026-05-12) | drop_url end-to-end materialization acceptance / 4 byte-stable golden / 16 cases | ✅ done (pending commit) |
| **Post-P4 D-3 Acceptance Gap P1** (2026-05-12) | 金丹复利 5 步 CLI 链 acceptance / 3 state JSONL byte-stable | ✅ done (`8cd2b25`) |
| **Post-P4 B Drift/Aging Acceptance Gap B** (2026-05-12) | drift_scan 三扫描器函数级 acceptance / 4 artifact byte-stable | ✅ done |


## 状态 — 当前活跃 3 轮

### Round 92.8 — Feed Parity (Universal Input pending closure) — 完成

- **目的**：闭合 P2 fresh oracle scoping 排为 SHIP first 的用户可见 feed-parity bug——Universal Input 投料（URL/PDF/image/repo/note）成功后，pending 卡长期停在 "已接收，等待生成报告"，因为 (1) `drop_*` 返回 payload 含 `note_path` 但 plugin `extractPrimaryPath()` 只识别 `path/output_path/receipt_path/state_path/index_path/report_path`；(2) shell summary 不暴露 raw ingest，`reconcilePendingSubmissions()` 永远 miss raw drop。
- **实现**：
  - `src/aiwiki/app_shell/summary.py:145-166`：新增 `_build_recent_raw_inputs(root, *, limit=8)` helper，从 `load_runtime_history(root)`（NON-strict，关键：strict 会 raise 破坏 fail-soft）过滤 `event_type == "raw-added"`，倒序取 8 条，映射 `stored_path / original_path / source_type / title / occurred_at / protocol`，全部 `str() or ""` coercion；body wrap broad `try/except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError)` 返回 `[]` 不 raise。`build_shell_summary` 在 line 241 预计算，line 312 dict literal 插入 `"recent_raw_inputs": recent_raw_inputs` 紧跟 `recent_runs`。
  - `src/aiwiki/today_feed.py:415-440`：新增 `_build_raw_input_entries(summary, today_date)` helper，仅当 `recent_raw_inputs` 是 list 时迭代；空 `stored_path` 跳过；`_date_part(occurred_at) != today_date` 跳过；构造 `FeedEntry(kind="action", title=f"已投料：{title or original_path or stored_path}", summary=f"已接收 {source_type or '材料'}，等待编译/刷新", target=stored_path, ...)`。`build_today_feed` line 82-83 在 `_build_action_entries` 之后追加。**关键**：未新增 FeedKind，复用 `kind="action"`（priority 6 最低），避免 schema 改动。
  - `.obsidian/plugins/furnace-product-shell/src/plugin_helpers.js:178`：`extractPrimaryPath()` `candidateKeys` 数组扩展为 `["path", "output_path", "receipt_path", "state_path", "index_path", "report_path", "note_path", "stored_path", "asset_path"]`，**新增 keys 排末尾**保留既有 ask/run path 优先级。
  - `.obsidian/plugins/furnace-product-shell/src/plugin.js:2150-2213`：`reconcilePendingSubmissions()` `rawCands = summary.recent_raw_inputs`，guard 允许 raw-only proceed；`matchAgainst` `fields` 数组扩展 `stored_path / original_path / note_path`；hit 顺序保持 outputs → receipts → raw fallback；命中 raw → `target = "raw"` + `targetPath = String(hitCand.stored_path || hitCand.path || "")` → `markPendingSubmissionDone(entry.id, "raw", targetPath)`。`markPendingSubmissionDone` 不 whitelist target 字符串（plugin.js:2085-2095 直接 `entry.reconcileTarget = String(reconcileTarget)`），"raw" 不 no-op。注释 comment 同步更新（plugin.js:2082）。
  - `.obsidian/plugins/furnace-product-shell/src/today_feed.js:58-59,286-305`：JS mirror 同步新增 `buildRawInputEntries`，被 plugin 加载，与 Python 渲染契约一致。
  - `tests/test_feed_parity.py` 10 测试 + `load_tests` bridge：4 summary（drop history 收录 + 全字段映射 / 无 history 空 / 损坏 JSONL fail-soft 返回 [] / 12 events 限 8 条 most-recent-first / 混 event_type 仅 raw-added）+ 3 today_feed（today date 渲染 kind=action / 昨天跳过 / 空 stored_path 跳过）+ 2 JS grep（plugin_helpers.js candidateKeys 含三新 key / plugin.js reconcile 含 `recent_raw_inputs` + `target = "raw"` + `stored_path` token）。
- **验证**：`bash scripts/verify.sh` PASS — **1848 unittest**（+10）+ 13/13 acceptance + branch coverage 92% / ruff + compileall clean。
- **qa-review**：fresh oracle session `ses_2055cf69dffeSzSAEpOCXG597D` PASS（首次 retry，非阻塞 concerns：JS 测试是 grep 级 vs 真执行级 / `markPendingSubmissionDone` 注释 comment 已 fix）。End-to-end 链路 trace 完整：user → Universal Input → `aiwiki drop <payload>` → `dispatch.py` rewrite → `drop_*` → `_append_raw_added_history` JSONL → `build_shell_summary` `recent_raw_inputs` → plugin reconcile `rawCands` → match via `stored_path` → `markPendingSubmissionDone("raw", stored_path)`。
- **Stop Lines**：0 `drop_*` 返回签名改 / 0 CLI signature / 0 `runtime_history` 写语义 / 0 schema / 0 lock primitive / 0 新 FeedKind（`today_feed.FeedKind` Literal 不变）/ 0 `general` default protocol / 0 LLM defaults / 0 notify defaults / 0 `safe_fetch` allowlist / 0 Universal Input 命令字符串（plugin.js:2239 仍 `["drop", normalizedPayload]`）。
- **Migration**：纯加层；既有 dogfood vault 重启 plugin 后 raw drop pending 卡可被 reconcile 自动 mark done；既有 ask/run path 优先级不变。
- **Residual Risks**：JS grep 测试只覆盖 token 存在，不覆盖顺序 / 行为变化 → 未来 plugin 大改时回归防护偏弱；可在后续 round 补 node 真执行测试（DEFER 不在本轮 scope）。
- **归档**：contract `.codex/contracts/archive/round-92-feed-parity.md`。


---

> 更早的 round 详情请参考 `archive/rounds/round-*.md` / `archive/rounds/p4-*.md`，或读 `archive/rounds/index.json`。
