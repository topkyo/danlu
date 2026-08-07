# 2026-08-06 入口面清理：README / HOME / 炉心面板 / 索引页分层

## 背景（多 agent 摸底结论）

- 仓库 README/HOME 是新版，但 dogfood vault 的 HOME/README 停在 6-2 旧版（旧 CLI、`apply/revert` 残留）。
- 炉心面板（`wiki/indexes/furnace-center.md`，compile 生成）内容新鲜，但 9KB / 10+ section，治理信息压过「今天先做什么」。
- `wiki/indexes/` 30 个页面中 **14 个没有任何写入方**（8-04 治理簇删除后渲染器成为死代码或只剩静态模板），vault 里这些页面停在 7-20。
- 死链：炉心/workspace.json/Shell fallback 三处指向不存在的 `wiki/indexes/Outputs.md`（真实页是 `output-packs.md`，且它本身也无写入方）。
- Active docs 硬错误：Runtime Ops 列已删 maturity gate retention + `autonomy-status/disable/enable` CLI；Evolution Mechanics §7 标题与正文矛盾；Architecture 金丹命令旧形态。

用户拍板：W1–W4 全做；炉心瘦身为用户首屏（今天做什么 / 最近输出 / 快速跳转，治理细节收进专页）；vault 删除类清理全授权。

## 页面分层定案

**Live（compile/nightly 每次刷新，保留）**：
furnace-center、index、sources、concepts、decisions、judgments、judgment-assets、review-queue、compile-status、machine-memory、protocols、review-center（managed static）、graph-view（managed static）、repair-backlog（nightly）。

**Retired（无写入方，代码+页面一起退）**：
aging-report、agent-workbench、domain-pilots、output-packs、concept-quality、rewrite-proposals（索引页；`wiki/rewrite-proposals/` 单提案页保留）、machine-memory-topology、machine-memory-actions、machine-memory-repair-plan、drift-report、graph-health、execution-audit、execution-center、cognitive-history。

治理信息的 live 归宿：待审/aging/生命周期 → review-queue.md；修复优先级/弱概念/rewrite 候选 → repair-backlog.md（nightly）；判断资产 → judgment-assets.md；机器记忆 → machine-memory.md + `.aiwiki/cache/machine-memory-graph.json`。

## 执行清单

### 代码（仓库）
1. `render/furnace_center.py`：瘦身为 3 section（今天先做什么 / 最近输出 / 快速跳转）+ 3 行元信息；签名去掉 output_packs/domain_pilots/execution_audit；快速跳转只链 live 页。
2. `compile/output_step.py`：调用点同步。
3. `render/views.py`：删死渲染器 `render_domain_pilots_index` / `render_agent_workbench` / `render_aging_report`；清 review-queue / master-index 的死链；facade 签名同步；清理变为零调用的 helper（furnace_quick_commands / protocol_execution_receipts 等，以 grep 为准）。
4. `render/paths.py`：删 14 个无调用 path helper（HTML legacy helper 按 JS 用量裁剪）。
5. `render/judgment_assets.py`、`render/compile_status.py`：页面清单只留 live；去掉 `log.md` 行。
6. `protocol/templates.py`：DEFAULT_DASHBOARD_FILES 删 execution-audit/cognitive-history 静态模板；review-center / graph-view / furnace-center 模板链接改 live 页。
7. `app_shell/meta.py`：links/views 去掉死页键与 legacy HTML 键（JS 均未读）；`output_packs_markdown` 键移除。
8. `app_linting/nightly.py`：state JSON 去掉死页 path 项（数据列表保留）。
9. `execution/patch_plan.py`：PATCH_PLAN_AUXILIARY_PATHS 死页 → repair-backlog.md。
10. `runner/prompts.py`：`_select_ask_index_pages` 去掉死页 preferred（available 列表本就不含它们，零行为变化）。
11. `vault/templates.py`：workspace lastOpenFiles 去 Outputs.md。
12. Product Shell `plugin_lifecycle.js`：Outputs Hub 改开 `furnace_center_markdown`（最近输出即输出总览）；重建 main.js。
13. `tests/test_repair.py`：patch target 期望同步。
14. `wiki/indexes/README.md`：重写为分层策略页。

### 文档（仓库）
15. README.md「控制台与索引页」段重写（分层口径）。
16. HOME.md（仓库 + vault 模板同源）微调：入口叙事与新炉心对齐。
17. docs/Furnace Product Shell.md：补一段 Shell（shell-summary 驱动 view）与 markdown 面板页（compile 生成）的关系。
18. docs/Furnace Runtime Operations.md：删 maturity gate retention 行、§9 删 autonomy-* CLI 引用。
19. docs/Furnace Evolution Mechanics.md：§7 标题对齐正文（library 已移除）。
20. docs/Furnace Agent Architecture.md：金丹命令改 `advanced alchemy` 推荐形态。

### Vault（dogfood，删除已授权）
21. 删 vault `wiki/indexes/` 14 个退休页 + 0 字节 `Outputs.md`。
22. 删 iCloud 冲突垃圾：`.obsidian 2/`、插件目录 `* 2.*`（含旧凭据 `data 2.json`）、0 字节 `docs/DEPLOY.md`；比对后删 `output/reports/` 的 ` 2` 重复报告。
23. 刷新 vault HOME.md / README.md / `wiki/indexes/README.md`（模板同源）；全量 compile 重刷面板；验证首屏无死链。

## 验证

- `bash scripts/verify.sh scripts python-static unit acceptance` + `product-shell-static`（JS 改动 + bundle drift 门禁）+ `llm-integration`（prompts.py 改动）；收口 `verify.sh all`。
- `bash scripts/docs_consistency_check.sh`。
- vault：compile 后检查 furnace-center 内容、HOME 链接、Shell 打开。

## 完成情况（2026-08-07 收口，全部完成）

清单 1–23 全部落地。验证：`verify.sh all` EXIT=0（acceptance **25** / llm-integration **84** / unit **176** / Jest **203** + drift 门禁）；docs_consistency 绿。

执行中比清单多做的事（同目标内的根因清理）：

- 死渲染器扩面：`memory/status.py` 整页重写（删 drift-report / graph-health / machine-memory-actions / machine-memory-repair-plan 4 个死渲染器）；`memory/execution_surfaces.py` 删 3 个死索引渲染器（保留 reconcile + 单提案页）；`memory/execution_audit_surfaces.py` 只留 `collect_execution_consistency_signals`；删零调用模块 `render/markdown_links.py`、`render/pilots.py`、`memory/execution_surface_helpers.py`；`compile/context.py` 删死字段 `execution_audit`，`compile/runtime_step.py` 删对应 snapshot 构建调用；`memory/action_core.py`、`app_linting/repair.py` 死引用同步。
- acceptance fixture 修复：3 个 run-ask 回放 case 的 5 个 prompt_hash 帧因 DEFAULT_DASHBOARD_FILES 模板内容变化而失配，用回放捕获脚本重算并改名（`tests/fixtures/acceptance/{M6.1b,W2}/…/backend_responses/`）；`tests/acceptance/llm_replay.py` 曾临时加 `AIWIKI_REPLAY_REFRESH` 自愈模式，用后已 `git checkout` 还原。
- 测试计数钉：`tests/test_llm_integration.py` 删 `furnace_quick_commands` 用例（85→**84**），verify.sh / docs_consistency_check.sh / AGENTS.md / Scorecard / DEVELOPER.md / Post-Cleanup / CHANGELOG 钉全部同步。
- vault 额外清理：`wiki/concepts/* 2.md` ×5（旧编译态副本）、`output/control/shell-summary 2.json`、vault `workspace.json` lastOpenFiles 死条目 ×8；发现并重启 `com.aiwiki.watch` launchd 服务（旧进程驻留 8-06 前代码，把我删的退役页重新编译回来；重启后新代码生效）。
- vault 保留项：`raw/inbox/vphone-aio 2.md`（它是 `wiki/sources/source-vphone-aio-2.md` 的 provenance 锚，不是重复副本）；`.aiwiki/state.icloud-backup-20260725-224322/`（修复备份，不在授权范围）。

发现并已做（2026-08-07 用户确认后清理）：`autonomy_policy.policy_status()` 零调用（原服务已删的 autonomy-status CLI），已随本计划删除；其依赖的 helper（`policy_path` / `disabled_reason` / `_profile_override` / `_env_global_override`）均有其他调用方，保留。

## 交叉审查（2026-08-07，read-only reviewer，APPROVE_WITH_NITS）

9 项必查全过：41 个被删符号零残留引用、炉心签名与调用点一致、5 个新帧 sequence/hash 一致且无凭据、84 计数钉全对齐、diff 无疑惑串、无 scope 夹带、文档抽查三处属实、未跟踪文件恰好为计划文档+新帧。

审查后顺手修复：`app_shell/summary.py` thin links 删掉永不命中的 `furnace_center_html` 死条目；W2 acceptance case 增加炉心三节形态断言（含退休页链接零出现）。

~~留作后续（不阻塞）~~ → 已全部落地（2026-08-07，紧随 `088f822` 的 follow-up commit）：

- `render/views.py` 两个零调用 delegate wrapper（`render_furnace_center` / `render_compile_status`）已删。
- 新增 Jest 用例：`openOutputsHub` 优先读 `links.furnace_center_markdown`、无 links 时 fallback `wiki/indexes/furnace-center.md`（Jest 203→**204**，verify.sh 之外全部计数钉同步）。
- `tests/test_vault_plugin.py` 补 vault `workspace.json` lastOpenFiles 内容断言（含 review-queue.md、无 Outputs.md）。
