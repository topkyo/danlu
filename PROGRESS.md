# 炼丹炉 Progress — Furnace 世代

> **PROGRESS.md 是当前任务状态唯一 SoT**。Round-by-round 长文、Milestone Quick Index 与较早「当前动态」已切档至 [`docs/archive/rounds/progress-round-detail-snapshot-2026-07-22.md`](docs/archive/rounds/progress-round-detail-snapshot-2026-07-22.md)（及既有 `docs/archive/rounds/*` 史料）。

## SoT 引用

- 终局架构：`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md`
- 评分 / release gate：`docs/AGOS-9-Scorecard.md`
- 当前执行计划：`docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`（审计报告 + Commercial Go-Live WS1–WS6）
- 已归档 cleanup：`docs/archive/Furnace Commercial Grade Cleanup Plan 2026-07.md`（executed-reviewed-pass）
- 验证入口：`bash scripts/verify.sh`
- 改进清单：见本文件底部「改进方向」段


## 当前动态

- 2026-07-27 (**SCC / planner / Post-Cleanup 卫生**)：断 `app_linting.phases→core`（TYPE_CHECKING，全库仅剩此 1 个模块级 SCC）；`planner/` docstring 标明 state/paths live（非空壳）；Post-Cleanup §1 Top hubs 去掉已删 `graph.py`/`drop.py`，对齐 202/51.6k 与现行巨石。

- 2026-07-27 (**会话交接刷新**)：结构债第 3 条从「第一刀 content↔memory / auto-resolution」改为续刀（巨石 / 剩余 SCC）；已完成段补记 07-26/27 结构债与 stale 扫除。

- 2026-07-27 (**acceptance prompt_hash 漂移**)：`M6.1b/case_backend_failure` 两帧 hash 重算（call1 `362a531dbb999d74` / call2 `bd9a5ac99b472325`）；保留 `failure` 字段。acceptance **24** PASS。

- 2026-07-27 (**结构债 state↛protocol**)：`save_manifest` 不再调用 `ensure_layout`；只 `mkdir` manifest 父目录。`state/` 零 import `protocol`（单向分层越界切断）。调用方仍自备 `ensure_layout`。

- 2026-07-27 (**third-pass residual CLI wording scrub**)：CHANGELOG `advanced run-nightly`；Demo Pack / Runtime Ops 去掉 apply/revert 产品 CLI 暗示；vault templates / repair / pilots / furnace_center 对齐 `advanced review-page|file-back|review-queue|alchemy-revert` 现行 operator 路径。验证：`docs_consistency_check` + ruff。

- 2026-07-27 (**第二轮 stale 扫除**)：Active 计数/门禁已对齐后残留主战场是缺 `advanced` 与旧名 `nightly`/`auto-once`/`apply|revert`。修 Runtime Ops / Evolution / INSTALL / BOUNDARIES / PRICING；src+vault 模板+Shell i18n+acceptance fixture 同步；Jest 206 仍绿。

- 2026-07-26 (**大扫除 stale SoT/src**)：4-agent 全量扫描后 scrub — CHANGELOG/Post-Cleanup/README/Scorecard/Product Shell/USER_GUIDE 现行计数与 coverage/app_state 误导；src 21 文件去掉「facade 仍在」与缺 `advanced` 的 CLI 提示；`verify_target_rules` 补 acceptance/llm-integration 路径。archive 与 Scorecard 冻结块不动。

- 2026-07-26 (**旧单测痕迹清理**)：Active SoT（AGENTS/DEVELOPER/Post-Cleanup）与 src 注释去掉已删 144 unit / `tests/unit/` 误导引用；archive/CHANGELOG/Scorecard 冻结史料不动。

- 2026-07-26 (**结构债 audit 簇外提**)：`collect/build/render` execution audit → `memory/execution_audit_surfaces.py`（~400 LOC）；`execution_surfaces` 1003→619，re-export 保持调用方零改。

- 2026-07-26 (**结构债 memory 加载隔离**)：`content/io` + `content/material` 对 `execution.history` 改为函数内 lazy；`import memory.execution_surfaces|action_core` 时 `sys.modules` 无 `aiwiki.execution.*`。

- 2026-07-26 (**结构债 memory↛execution 清零**)：SoT=`memory` 不得 import `execution`。五刀：digest→`rewrite_readiness`；`ELIXIR_DIR` 本地常量；`action_policy` + `execution_audit_io` + path helpers 下沉 memory；`policy`/`repair_plan` re-export；dry-run rotate 内联。`rg memory→execution` 空；acceptance 24 + llm 79 PASS。

- 2026-07-26 (**结构债 Knife C**)：断 `execution_surfaces → repair_plan` 跨层边——rewrite readiness 三函数迁入 `memory/rewrite_readiness.py`；`repair_plan` re-export；surfaces 直引 memory。

- 2026-07-26 (**结构债第一刀**)：Knife B 断 `content↔memory` 环（`action_rank.py` + `placeholder_concept_slugs` 迁入 concepts；`action_core` re-export）；Knife A 外提 `machine_memory_auto_resolution.py`（actions 1382→1001）。`verify` python-static/smoke/acceptance PASS。

- 2026-07-26 (**SoT 卫生**)：Jest 现行实测 **206**（文档曾写 200）；`verify.sh` usage 17/78 → **24/79**；AGENTS/Scorecard/DEVELOPER/Post-Cleanup/PROGRESS 对齐。

- 2026-07-26 (**SoT 计数 + dogfood 收口**)：verify 实测对齐 acceptance **24** / llm **79** / Jest **200**（后同日对齐 **206**）；沉淀/金丹 Properties（Obsidian 1.12 leaf class）CDP PASS；WS2 wheel 本地验收通过（未 upload）；`.aiwiki/state` 外置防 iCloud 分叉。下一刀仍为 EULA/PyPI upload/Demo 媒体。

- 2026-07-24 (**文档对齐 + dogfood/质保维护**)：Scorecard/AGENTS/Post-Cleanup 计数对齐 acceptance **18** / llm **78** / Jest **189**；alchemy CLI 位置参数与 `--elixir-id` 互通；Today 报告卡无 pending 也可再生成/编辑（读报告 `query` + sticky）。下一轮指针见文末「会话交接」。

- 2026-07-24 (**质保 Round1–3 / DEF-R2-01**)：重复 file-back 保留 judgment 锚点（不踢金丹链）；Shell sticky 记账回退 + Today 报告卡「引用追问」；同 corpus 多轮可点亮 compound_suggest。Plan：`docs/plans/2026-07-24-codex-goal-elixir-maturity-loop.md` + 四 Lane 验收。`verify acceptance` **18**；Jest **189**。

- 2026-07-23 (**Chat-entry 第一刀**)：入口像 ChatGPT、产出仍一问一报告+金丹。落地材料 chips、`runAskCommand(materialPaths)`、`@`/引用当前文件、成功气泡「再生成/编辑问题」。Spec/plan：`docs/specs|plans/2026-07-23-chat-entry-report-elixir.md`。Jest **186**。

- 2026-07-23 (**Dogfood P0 sticky + honest media**)：Shell `stickyMaterialRefs` 追问继承刚投材料；图片无视觉摘要 Notice；ask 对不可读 material_refs 诚实短答降级（不灌无关 wiki）。Spec/plan：`docs/specs|plans/2026-07-23-dogfood-p0-sticky-and-honest-media.md`。Jest **177**；llm-integration **78**。

- 2026-07-22 (**Settings Slim A**)：通知 URL 非空即启用（删 `enabledChannels` toggle）；废弃未读文档/CSS/`cliHint`；SoT §9 camelCase。Spec/plan：`docs/specs|plans/2026-07-22-product-shell-settings-slim.md`。Jest **172**。

- 2026-07-22（shell settings less · batch 3）：Base URL 与 Feishu/WeCom webhook 收进默认折叠 `<details>`；主设置页顺序 Language → Connection → LLM → Integrations → Developer；Jest **169**。

- 2026-07-22（shell less cuts）：去掉 pending received/soft-hint；删死 modal/未用 Today builder/无引用 i18n；删 vault-queue 仅留 desktop launcher；Jest **169**（此前文档误记 174）。

- 2026-07-22 (**eng-debt radar**)：统一 alchemy/autonomy atomic write；CLI dispatch lazy import；multipart HTTP→CompletionResult 集成测；verify 计数对齐 acceptance **17** / llm **77** / Jest **180**。

- 2026-07-22 (**Less 推荐收口包**)：去掉 Shell runs 死面+僵尸 i18n；SoT Active 单枚举；PROGRESS 瘦身；`advanced alchemy` 子树（旧 alchemy-* compat）。计划：`docs/plans/2026-07-22-less-recommended-pack.md`。

- 2026-07-22 (**Less-is-More cuts**)：Ask 成功直写 done；pending 去假进度；Today 主栏仅报告；清 no-op nightly/auto_adopt env。计划：`docs/plans/2026-07-22-less-is-more-cuts.md`。

- 2026-07-22 (**Less-is-More 复评**)：四路审计加权 **7.1**（Surface 7.9 / Code 7.0 / UX 6.8 / Docs 6.0）。热路径已瘦；主债在 Shell 幽灵 pending、advanced+env、SoT 三套重叠。报告：`docs/archive/Furnace Less-is-More Reassessment 2026-07-22.md`。

- 2026-07-22 (**多尺子全量复评**)：Ask sync 后四路审计 — Local Eng **9.05**；Live 维 **7.0**（Gate not-yet，估算加权 ~8.3）；Commercial **7.8**；Ask 架构 A/B **8.0**。报告：`docs/archive/Furnace Multi-Ruler Reassessment 2026-07-22.md`；Scorecard 已刷新（acceptance 17 / Jest 179 / llm 76）。

- 2026-07-22 (**Ask follow-ups · 收口**)：dogfood 基线（ask 25s/43s + mid drop，`/tmp/ask-dogfood-baseline.md`）；读侧 background 过滤与 pending `jobId` 已删；sync ask ≥15s「仍在生成」软提示；Post-Cleanup/Go-Live SoT 已对齐。计划：`docs/plans/2026-07-22-ask-followups.md`。

- 2026-07-22 (**Ask sync chat · 删除 submit/resume**)：Shell 提问改同步 `run-ask` + 单飞；删除 `run-ask-submit`/`run-ask-resume`/`background.py`/longRunning poller。审查修 P0：`excludePendingId` 避免 push 后自挡。Dogfood：清 `background-jobs/`、移骨架报告、同步 vault `main.js`。Spec/plan：`docs/specs|plans/2026-07-22-ask-sync-chat.md`。验证：`verify.sh all` PASS。

- 2026-07-21 (**自用打磨 · wiki 页中文段名**)：source/concept compile 写出中文 `##` 标题与空态；`preserved_section` / upsert / lint 兼容旧英文段名；acceptance prompt_hash 刷新。不做 Shell 清炉入口；nightly reconciliation / L3 revert partial 继续 defer。

- 2026-07-21 (**provenance body scrub + concept soft/overload**)：正文死 `output/reports` →「（报告已删除）」；GC acceptance 边界加厚；≤1 source 概念强制 soft；overload lint warn。

- 2026-07-21 (**report provenance scrub + gc-orphans**)：落地 KISS spec——compile 剥离死 `output/reports` 并 sticky 标 `provenance_status`；`advanced gc-orphans` dry-run/`--apply`+receipt；①′ HTML 停写保持。acceptance **17**。dogfood：compile → GC apply（degraded file-back + 噪音概念 + vphone 误投）→ recompile。

- 2026-07-20 (**ingest dedup + drop UX**)：同规范化 URL 默认复用 raw（`--refresh` 重抓）；Shell 纯投料「已收料」不暗示报告。Spec/plan：`docs/specs|plans/2026-07-20-ingest-dedup-and-drop-ux.md`。验证：acceptance **25** + llm-integration **76**。

- 2026-07-20 (**Obsidian Python 3.9 zip crash**): drop 后 auto-compile 在 Apple `/usr/bin/python3` 上因 `zip(..., strict=)` 崩 → Shell「生成被阻断」+ 收件箱重复。修：去 `strict=`；launcher 挑 ≥3.10；vault launcher 转发 runtime。

- 2026-07-20 (**rescan P1 ingest/governance**): 死 CLI hint→`advanced review-queue`；CJK phrase 乱码；确定性 GitHub raw rewrite；路径 fail-loud 误伤（裸目录 / 中文 A/B）；`run-ask` LLM 出写锁；alchemy lane 假回滚文案；local target 须派生自 original。验证：acceptance **25** + llm-integration **69**。Deferred：L3 revert partial、nightly reconciliation gate、EN-only page copy。

- 2026-07-20 (**capability follow-up**): 修 5d6bcef 下游空洞——CJK concept `len>=2` + unicode `slugify` + CJK stopwords；`fetch_raw` 全失败 fail-loud；planner 本地路径 fail-loud + vault containment；distill LLM 锁外合成 + receipt `llm_invoked`/`generation_mode`；GitHub blob/tree planner 规则。验证：acceptance **25** + llm-integration **65**（随后 rescan 波升至 **69**）。

- 2026-07-20 (**plan/execute + capability remediation**，`5d6bcef`)：universal `drop <payload>` 默认走 LLM `input_planner` → deterministic `executor`（`drop plan` 可只看计划；`AIWIKI_LLM_PLANNER=0` 退回确定性分类）。能力层补洞：CJK bigram `tokenize`、conflict CJK pairs、repo/url 抽取扩面、alchemy distill 在 runner 注入可选 LLM synthesizer（`AIWIKI_LLM_DISTILL=0` 关闭）。文档 SoT 同步 `a89779d`。

- 2026-07-18 (**Active SoT sync + ask/atomic hot-path**)：Architecture / Evolution / Elixir / Runtime Ops / USER_GUIDE 对齐金丹锚点 `wiki/judgments|derived` 与 judgment-only file-back；execution/runner ask 热路径续扫 `write_text`→`atomic_write_text`。验证：`bash scripts/verify.sh scripts python-static acceptance`。

- 2026-07-18 (**hub decomposition + LLM integration tests + pre-commit**)：用户显式覆盖 AGENTS.md 原「legacy hub 另一条搬迁线、本轮不动」定案，一次做干净三个 central hub 下沉 + 反向依赖消除。**app_utils.py** → `utils/` 子包；**app_state.py** → `state/` + owner 子包；**content/memory.py** → `memory/action_core` + `execution/policy` + `execution/patch_plan` + `execution/repair_plan`；**反向依赖消除**：ranking 函数迁入 `compile/ranking.py`，`app_compile.py` 587→18 行。附加：LLM 集成测试 38 条；pre-commit hook；`app_*` hub 削薄定案推进。验证：`bash scripts/verify.sh all` PASS。commit `145276a`。

- 2026-07-18 (**W9 hygiene close**)：Task 1 删除 `agent_loop`/`debt_autopilot` 与 orphan `run_compile`/`run_lint`；Task 2 P9 general-only + execution-center 产品面清理；Task 3 去掉 `today_snooze`/summary `agent_loop`、重命名 review-queue helper id、Shell i18n 僵尸键清理、Active docs/AGENTS 收尾。验证：`bash scripts/verify.sh all` PASS。

- 2026-07-18 (**W8 final AgentOS residual close**)：Task 1 `run-nightly` 仅 deterministic compile+lint；Task 2 live-only `shell_capabilities` + 生成面 dead CLI 清理；Task 3 drop 默认 auto-process、judgment-only file-back、删除 review-page batch；Task 4 Today-only Shell 视图 + 最小 shell-summary persist；Task 5 Active docs / acceptance / orphan `render_review.js`+`render_execution.js` 删除 + rg gate。验证：`bash scripts/verify.sh all` PASS。

- 2026-07-18 (**W2–W5 compounding 波完成**)：W1 单协议 runtime；W2 Ask 复利 rank + `used_refs` + `compound_suggest`；W3 governance CLI 侧切；W4 非核心 CLI/Shell/HTML 控制台噪声；W5 review 三态 / file-back 默认 judgment / Shell Today-first / shell-summary 瘦身 / graph-index 遥测页停写 / LLM 产品默认 `opencode-api/deepseek-v4-pro` 文档锁定（B44）。验证：`bash scripts/verify.sh all` PASS。

- 2026-07-22 (**PROGRESS 瘦身**)：Round 长尾、Milestone Quick Index、cleanup R1–R13 长文切档至 `docs/archive/rounds/progress-round-detail-snapshot-2026-07-22.md`；本文件保留 head + 改进方向。

- 当前节奏：Commercial Go-Live 执行波已落地 WS1–WS3/WS5 主项；Less-is-More 收口包进行中。
- 当前 blocker：无 runtime blocker；残留 PyPI 正式发布、EULA 法律签收、demo 媒体、WS6 dogfood。

> Round cleanup 摘要表、2026-07-18 W 波细项、2026-07-17 及更早动态、Milestone Quick Index、Round R1–R13 长文：见 [`docs/archive/rounds/progress-round-detail-snapshot-2026-07-22.md`](docs/archive/rounds/progress-round-detail-snapshot-2026-07-22.md)。

---

## 改进方向

> SoT：详细缺陷表、工作流与 Done 判据见 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`。此处只保留指针级清单。

| 优先级 | 方向 | 状态 |
|---|---|---|
| P0 | Commercial go-live：真实邮箱、询价决策、商业 EULA | **done（草案）**：`topkyoxp@gmail.com` + `EULA.md`；正式法律签收仍 open |
| P1 | 分发闭环：`pip install` 或 INSTALL 明确预览边界；版本与 tag 对齐 | **partial**：`-e .` + 本地 wheel（`build_release_wheel.sh`）+ v0.4.0；**PyPI upload 待运营** |
| P1 | Jest hard-gate + env-coupled 测试隔离 | **done / moot**：Jest **206** hard-gate；env unit 已退 |
| P1 | Alchemy materialize 等裸 `write_text` → `atomic_write_text` | **done**（ask/alchemy helpers；execution+runner ask 热路径续扫） |
| P2 | Scorecard hub 行数刷新；PROGRESS 活跃 round 切档卫生 | **done 2026-07-22**：Round 长尾切档 archive snapshot |
| P2 | Demo Pack 截图/录屏资产（fixture + checklist 已交付） | checklist done；媒体可选待补 |
| P2 | Active SoT 金丹锚点文档（derived-only → judgments\|derived） | **done 2026-07-18**：Architecture / Evolution / Elixir / Runtime Ops / USER_GUIDE |
| 观测 | 14/30-day natural dogfood proof（不伪造 PASS） | Scorecard not-yet |
| Out | 再开 hub 大拆（已清零）、SaaS、全功能 iOS、用 AgentOS 9 冒充商业 9 分 | 禁止 |

---

## 会话交接（给下一轮 agent）

复制下面整段到新对话开头即可：

```text
说人话。先读 PROGRESS.md 头条 + docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md。

已完成：沉淀/金丹 FM + Properties leaf sync（CDP PASS）；state 外置防 iCloud 分叉；WS2 本地 wheel；SoT 计数 24/79/206；结构债 Knife A/B + memory↛execution + audit 外提 + state↛protocol；stale SoT/CLI 三轮扫除；M6.1b prompt_hash 刷新。

下一刀优先（择一）：
1) Commercial：EULA 法律签收 / twine upload + tag v0.4.0 / Demo 9 PNG
2) WS6 dogfood 自然观测（不伪造 Live PASS）
3) 结构债续刀（非阻塞开售）：巨石 concepts/views/phases 单 seam 外提（模块级 SCC 已清零）— 禁止 broad hub rewrite
4) 勿宣称 AgentOS 9 live / 诚实可售

Vault：iCloud「炼丹炉」；state → ~/Library/Application Support/aiwiki/dogfood-state；CDP：9228；验证：bash scripts/verify.sh all
```
