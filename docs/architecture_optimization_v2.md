# 炼丹炉 (aiwiki) 下一代架构演进与优化设计

**文档状态**: 提议 (Draft, Review v6)
**作者**: 架构师 (AI)
**目标系统**: `aiwiki` 本地优先知识复利操作系统
**修订说明**: 本版在 v5 基础上继续消除与当前工程事实的偏差：保留 KISS 与 Obsidian 插件“黑盒瘦客户端”的产品原则，但把 P4 从 `serve/RPC` 路线收回到当前已落地的 `launcher + aiwiki CLI + shell-summary` 契约；同时修正 execution owner、deterministic fallback 语义与测试基线，使本文可以直接作为后续工程 contract 的依据。

## 0. 本轮优化的"非目标"（Non-Goals）

为防止过度解读，先显式划定本次架构演进**不做**的事：

- **不引入 hosted service / multi-user sync** — 严守 `AGENTS.md` 的稳定约束。
- **不做跨 backend 自动故障转移** — requested backend 始终以 `AIWIKI_LLM_BACKEND` 为准；只允许 backend 内既有的 model-chain fallback。
- **不把 SQLite 升级为事实来源** — SQLite 只做易失性索引，Markdown + JSON manifest 仍是唯一 source of truth。
- **不引入外部 Web 框架**（FastAPI / Flask 等） — 当前插件继续走 `launcher + aiwiki CLI`，不新增 Web 运行面。
- **本轮不引入 daemon / service / server** — Obsidian 插件继续通过 vault-local launcher、`aiwiki CLI` 与 `shell-summary` 和 runtime 交互；如后续要评估 local control plane，必须另开 contract。
- **不改变 `raw / wiki / machine memory / schema / outputs` 五层分层** — 只优化各层内部实现。
- **不替换现有的 `apply / revert / receipt / audit` 协议** — 新架构必须 **100% 兼容** 现存的治理与执行层。
- **不追求极致性能** — 目标是"在 10 万级文件量下仍可在单次 compile 内收敛"，而不是毫秒级查询。

## 1. 架构演进背景

当前 `aiwiki` 已完成第一阶段解耦重构（`app.py` → 协议/编译/内存/渲染多模块），并把 `verify` 基线提升到当前约 `355 tests / 92% coverage`（以 `README.md` / `PROGRESS.md` 为准）。系统稳定性与护栏纪律已达高位。

但随着本地知识资产（Raw、Wiki、Machine Memory、Judgment）规模扩张，以下瓶颈正在显现：

1. **巨石模块残留**（经代码核对）：
   - `app_compile.py`：**4,359 行**（~180KB）
   - `app_memory_surfaces.py`：**3,728 行**
   - 拓展新协议或新生命周期状态时认知负荷极高，容易引发跨模块回归。
2. **I/O 瓶颈显现**：重度依赖 Markdown + JSON manifest 的纯文件系统遍历，在因果图谱（Causal Graph）跨文件校验时性能衰减明显。
3. **LLM 边界脆弱**：经代码核对，`llm.py` 内有 **4 处** 核心 `subprocess.run` 调用负责外部 CLI 交互；而 prompt-profile retry、model fallback 与 deterministic fallback 编排同时分布在 `runner.py`。这层语义目前分散，后续若继续加 backend/guardrail，维护成本会继续上升。
4. **体验割裂**：Obsidian 作为 IDE、Product Shell (HTML) 作为治理视图，二者之间上下文切换成本高。

## 1.1 最新 LLM 现实校准（2026-04）

基于 danlu vault 的最近真实运行记录，可以得到三条对后续架构非常关键的事实：

1. **route 正常 ≠ backend 实时可用**
   - `llm-check` 可以稳定解析出 `backend_requested / backend / effective_model`，但 `llm-check --probe` 与真实 `run-ask` 仍可能因外部 timeout / quota / auth 波动失败。
   - 因此 LLM 健康度至少要拆成三层：`route health`、`probe health`、`contract health`。
2. **成功样本可能来自模型级 fallback，而不是首模型直通**
   - danlu vault 的一次真实成功样本 `run-ask "你是啥大模型?" --format report` 最终成功写出了结果，但其 stderr 明确记录了首模型失败、随后切到下一模型继续执行。
   - 这证明当前 runtime 的关键能力不是“首模型永远稳定”，而是“失败后仍能在同 backend 内收敛到可用模型”。
3. **当前观测面仍有不一致**
   - runtime `.aiwiki/logs/runs.jsonl` 已记录最终成功使用的模型；但 Product Shell recent run / run log 在部分情况下仍展示初始选路模型。
   - 这会导致用户误判“究竟是哪一个模型成功回答了问题”，也会让健康状态与调试路径产生偏差。

这三条事实说明：P1 不是单纯的“统一调用封装”，而是一次**调用 + 契约验证 + fallback 编排 + 审计一致性**的整体收口。

## 2. 核心优化方向与设计原则

**不可变底线**：`Local-first` / `Single writer, many readers` / `Markdown as Source of Truth` / `deterministic baseline 必须可用` / `显式 backend 选择不可被 Gateway 改写` / `apply-revert-audit 必须闭环`。

在此底线之上，引入三个核心演进方向：**微内核管道**、**易失性索引**、**LLM Gateway 审计收口**；同时继续收紧 Obsidian 插件的前台契约。

### 2.1 微内核 + 管道模式 (Pipeline Pattern) 拆解巨石模块

将 `app_compile.py` 拆解为声明式 Pipeline。

- **现状**：4,359 行的过程式长函数，耦合了 AST 解析、链接解析、实体提取、因果图校验、持久化等多个关注点。内含 `apply_concept_rewrite / apply_machine_memory_action / apply_material_archive` 等一大批 apply/revert 函数——**这是现有治理层的核心**。
- **设计**：
  - 定义 `CompilerStep` 接口：`run(context: CompileContext) -> CompileContext`。
  - 新建 `src/aiwiki/compile/` 子包：
    - `parse_step.py`：Markdown AST 与 frontmatter 解析
    - `link_resolve_step.py`：内部链接与引用解析
    - `causal_graph_step.py`：因果边提取与校验
    - `lint_step.py`：lint_wiki 内 lint 规则注册器
    - `persist_step.py`：JSON manifest 与派生产物写入
  - Pipeline 本身是无状态的 step 列表；`compile_wiki()` 负责构造 pipeline 并驱动执行。
- **owner 边界（关键修正）**：
  - `apply / revert / bundle / receipt` **不并入** `compile/`；它们继续归 execution owner 管理。
  - **当前代码事实** 是：`app_compile.py` 仍然承载对外的 `apply_* / revert_*` 入口，`app_execution.py` 目前只负责 bundle / receipt helper。
  - 因此当前最小正确步骤是：先把 compile owner 拆出去，同时维持 apply/revert 入口留在 `app_compile.py`；如后续 execution 逻辑继续膨胀，再单独演进为 `app_execution.py` owner 扩张或 `src/aiwiki/execution/` 子包。
  - 换句话说：P2 先拆 compile，不假设 execution owner 已经稳定落在 `app_execution.py`。
- **兼容性约束**：
  - `app_compile.py` 保留为 facade shim；`apply_concept_rewrite`、`apply_machine_memory_action`、`apply_material_archive` 等公开函数签名必须**零变更**。
  - 即使未来把 execution 实现迁到 `app_execution.py` 或 `execution/` 子包，`app_compile.py` 的 import surface 仍保持稳定。
  - 每一步迁移后，旧入口用 re-export 保持，待全部测试通过后再清理。
- **收益**：符合开闭原则；新增编译检查项（如新的判断资产强校验）只需注册新 Step；单文件认知负荷下降 5-10 倍。

### 2.2 易失性图谱缓存层 (Volatile Indexing) — SQLite

坚决不把 SQLite 升级为 source of truth，只做**非事实、可随时重建、可随时丢弃**的索引层。

- **现状**：每次查询/增量编译都要反序列化 `.aiwiki/` 下的大量 JSON。跨文件图谱遍历（尤其是因果边传递闭包）是纯 O(N*M) 的文件扫描。
- **设计**：
  - 路径：`.aiwiki/cache.db`（SQLite，显式列入 `.gitignore`，**严禁纳入版本控制**）。
  - 物化表：`nodes`, `edges`, `concept_lifecycle`, `judgment_summary`, `routing_snapshot`。
  - 每条记录携带 `source_hash`（来源 JSON/MD 的内容哈希）与 `schema_version`。
  - **失效粒度（关键）**：
    - **Row-level 失效**：单个源文件哈希变化 → 失效该文件对应的所有 row。
    - **Schema-level 作废**：`schema_version` 不匹配 → 整库 drop + rebuild。
    - **手动逃生口**：`aiwiki cache --drop` 命令无条件清空缓存。
  - **并发安全**：复用 `app_utils.py` 现有 runtime lock（`Single writer` 语义），SQLite 连接以 `PRAGMA journal_mode=WAL` 启用，允许 reader 并发。
  - **可观测性**：每次 compile 结束写一条 `.aiwiki/state/cache-status.json`，记录 cache hit/miss 统计与重建耗时，供 `aging/nightly` 追溯。
- **deterministic baseline 兼容**：所有命中缓存的 Query，必须在 debug mode 下可以通过 `--no-cache` 旗标回退到纯 JSON 扫描路径，二者结果必须 byte-for-byte 一致（加入 CI 对拍测试）。
- **收益**：图谱遍历和跨文件 Query 提速 1-2 个数量级，不牺牲事实主权。

### 2.3 LLM Gateway 容错网关

把 `llm.py` 中 4 处 CLI 调用统一收口为 backend-local Gateway，但**不**改写“显式 backend 选择”这条用户契约。

- **现状（已核对）**：
  - LLM subprocess 调用集中在 `llm.py`；`drop.py` 的 subprocess 是 `curl/pdftotext` 等数据摄入工具，**不属于本模块改造范围**。
  - `runner.py` 已经承载 `balanced -> lean` prompt-profile retry、`nvidia-nim-api` 的 model-chain fallback，以及部分 deterministic fallback 编排。
  - 这意味着当前 retry/fallback 语义是“跨文件分层存在”，不是单点可替换。
  - 真实运行还表明：同一次 ask 里“初始选路模型”和“最终成功模型”可能不同；如果审计层只记一个 `model` 字段，就会丢失关键诊断信息。
- **设计**：
  - 抽象 `LLMGateway` 接口：`invoke(prompt, schema, timeout) -> LLMResult`，backend 来源始终是已解析好的 `LLMConfig.backend`。
  - **重要约束**：Gateway 不做跨 backend 自动切换；requested/effective backend 仍由 `AIWIKI_LLM_BACKEND` 决定。
  - **健康度分层**：
    - `route health`：配置解析、backend 发现、requested/effective backend 是否一致。
    - `probe health`：最小真实 completion 是否能返回预期探针结果。
    - `contract health`：`run-ask / run-compile / run-lint` 的最终产物是否通过 frontmatter / markdown / citation 等校验。
  - **三层防线（从内到外）**：
    1. **Invocation Normalization**：统一 subprocess/API 调用、timeout/auth/rate-limit 错误分类和结构化返回。
    2. **Backend-local Retry**：保留现有 prompt-profile retry 在 `runner.py`；只在 backend 已有语义允许时做 model-chain fallback（当前主要是 `nvidia-nim-api`）。
    3. **Deterministic Fallback**：Gateway 只提供可分类错误，不擅自切 backend。**当前现实语义** 是：`run-ask` 的 deterministic fallback 仍在 Product Shell 外层；compile/lint 的 deterministic 收口当前主要发生在 `auto_process_once()`，不是所有 `run-*` 命令的通用契约。
  - **可选防抖**：可在单次 run 内加入 backend-local circuit breaker，避免同一个显式 backend 在连续 auth/timeout 失败后被无意义重试，但它只负责“尽快失败”，**不**负责“偷偷换 backend”。
  - **审计**：每次 invoke 追加 `.aiwiki/logs/llm-receipts.jsonl` 一行记录，至少包含 `backend_requested`、`backend_effective`、`model_selected`、`model_final`、`duration_ms`、`fallback_stage`、`fallback_reason`、`prompt_profile`、`retry_prompt_profile`、`contract_validated`，喂给现有 audit 链路。
  - **收益**：requested/effective backend 语义保持可预测；`run-ask` 的初始选路模型与最终成功模型可审计；为后续再把 compile/lint/nightly 扩到同一套 receipt 体系打基础。

### 2.4 Plugin-facing Contract 与 Obsidian 融合

收敛 Obsidian ↔ Product Shell 的体验割裂，并**严格贯彻 KISS (Keep It Simple, Stupid) 原则**。

- **现状**：Product Shell 已经是“Obsidian + launcher CLI 双入口，共用同一 runtime”；插件侧的正式接口是 vault-local launcher、`aiwiki CLI` 和 `shell-summary`，而不是 daemon/RPC。底层仍会生成大量 `wiki/derived/`、`machine memory/`、JSON 等面向机器和审计的中间态，用户感知过载。
- **设计**：
  - **产品哲学 (单输入 / 单输出)**：Obsidian 插件必须设计为绝对的**“黑盒瘦客户端 (Thin Client)”**。插件不关心底层文件解析、SQLite 缓存或 LLM 调用逻辑，只负责极简的单一输入（发请求）和单一输出（呈现决策、报告或通知）。
  - **当前正式契约继续保持 CLI-first**：插件通过 vault-local launcher 调 `aiwiki CLI`，并用 `shell-status` / `shell-summary` 读取前台摘要；不新增 RPC 协议，也不把 hidden `.aiwiki/state/*` 暴露成前端长期接口。
  - **屏蔽中间态**：在产品交互面上彻底隐藏底层复杂的运行记录。只有生成最终的报告 (Outputs) 或需要人工介入的决策 (Judgment/Review) 时，才通过 `shell-summary`、CLI payload 或结果路径把最少必要信息暴露给插件。
  - 当前推荐的插件-facing 命令面保持为：
    - 读：`shell-status`、`dashboard`、`search`
    - 写：`review-page`、`review-pages-batch`、`apply-action`、`revert-action`、`apply-archive`、`revert-archive`、`apply-rewrite`、`revert-rewrite`
  - 所有写操作继续复用现有 owner 函数与 `runtime_write_operation`；禁止插件直写 `.aiwiki/state/*.json`。
  - HTML Product Shell 继续保留为 fallback；如果未来 CLI-first 方案在交互延迟或状态同步上成为真实瓶颈，再单开 contract 评估 local control plane。
- **收益**：UI 与 runtime 解耦，同时不破坏现有 CLI/治理语义；用户感知大幅净化，专注价值输出；插件可以无缝复用底层，而免受未来架构演进的影响。

## 3. 演进路线图 (Implementation Phasing)

严格遵守 `AGENTS.md` 规定的 `open-harness` 闭环护栏：`contract -> implement -> verify -> qa-review -> update PROGRESS`。

每个 Phase 都必须可独立合入、可独立回滚。

| Phase | 内容 | 风险 | 收益 | 回滚策略 |
|-------|------|------|------|----------|
| **P1** | LLM Gateway（2.3） | 中 | 高（稳定性立竿见影） | 改动主要集中在 `llm.py` + `runner.py`；回滚时同时恢复 Gateway 适配层与现有 retry/orchestration |
| **P2** | Pipeline Refactor（2.1） | 中 | 中（治理技术债） | facade shim 保留旧签名；回滚即删 `compile/` 子包并恢复 compile owner 映射 |
| **P3** | SQLite Cache（2.2） | 中高 | 高（性能） | `aiwiki cache --drop` + 去掉缓存读取分支即可 |
| **P4** | Plugin-facing Contract Tightening（2.4） | 低中 | 中（UX） | 纯收紧现有 launcher + CLI + shell-summary 契约；回滚即恢复旧摘要/旧插件 wiring |

**详细步骤：**

### Phase 1: LLM Gateway & Audit Consistency（推荐优先）
- 在 `llm.py` 与 `runner.py` 之间重新收口职责：Gateway 负责调用与错误分类，`runner.py` 保留 prompt-profile retry / model fallback orchestration。
- 保持 `AIWIKI_LLM_BACKEND` 显式契约；不做跨 backend 自动切换。
- 保留 `nvidia-nim-api` 现有 model-chain fallback；其他 backend 失败时返回分类错误给上层。
- **P1A 当前最小实现面**：先收口 `run-ask` 的调用审计与最终模型一致性；`run-compile / run-lint / run-nightly` 的完整 receipt 统一化后续再开子阶段。
- 新增 `.aiwiki/logs/llm-receipts.jsonl` 审计流。
- **验收**：`bash scripts/verify.sh` 全绿；新增 fallback / schema-validate 单元测试；`llm-check`、Product Shell 和 README 中 requested/effective backend 语义不回退成 auto；`run-ask` 返回与审计能区分 `model_selected / model_final`。

**新增 canary 要求：**

- `route canary`：`llm-check`
- `probe canary`：`llm-check --probe`
- `contract canary`：最小 `run-ask`
- 若 `contract canary` 成功依赖模型级 fallback，也必须把 `model_selected -> model_final` 的变化写入审计，而不是只显示初始模型。

### Phase 2: Pipeline Refactor
- 冻结 `app_compile.py` 新特性。
- 建立 `src/aiwiki/compile/` 子包并逐 Step 迁移；`app_compile.py` 收口为 facade。
- `apply / revert / bundle / receipt` 不进入 `compile/`；当前对外 apply/revert 入口仍留在 `app_compile.py`，`app_execution.py` 继续只承接 bundle/receipt helper；如后续 execution owner 真正膨胀，再单独开启 execution 子包 contract。
- **关键兼容性验证**：所有 `apply_*` / `revert_*` 公开函数签名零变更。
- **验收**：当前主线 `verify` 基线 100% 通过（现为约 `355 tests / 92% coverage`，以当时 `README.md / PROGRESS.md` 为准，不允许新增跳过项）；compile-only 实现不再与 execution 实现混居；若要继续把 `app_compile.py` 压到更低行数，再另开 execution owner refactor。

### Phase 3: Volatile SQLite Cache
- 引入 `sqlite3` 标准库构建 `.aiwiki/cache.db`。
- 改造 `app_memory_surfaces.py` 查询逻辑，先命中缓存、miss 则回源。
- **关键约束**：
  - 必须复用 `app_utils.py` runtime lock。
  - 必须提供 `--no-cache` deterministic 回退路径，且 CI 对拍。
  - 必须加入 `aiwiki cache --drop` 逃生口。
- **验收**：测试全绿 + 对拍一致 + 新增 benchmark 脚本（至少展示因果图谱遍历 >5x 加速）；`.aiwiki/cache.db` 已被 Git 忽略。

### Phase 4: Plugin-facing Contract Tightening
- 继续坚持 Obsidian 插件通过 vault-local launcher 调 `aiwiki CLI`，并以 `shell-status` / `shell-summary` 作为唯一正式前台摘要契约。
- 逐步把插件仍在猜测的对象身份、LLM 运行结果与恢复动作，从 runtime payload / summary 中显式暴露出来，而不是让插件继续读 hidden state 或自行猜测。
- 写操作继续复用现有 owner 函数与 runtime lock；不增加 daemon / server / RPC。
- **验收**：CLI / plugin smoke test 全绿；插件仍只通过 launcher + CLI 工作；静态 HTML fallback 继续可用；插件不需要直接读取 `.aiwiki/state/*` 才能完成主路径交互。

## 4. 风险矩阵与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| SQLite 缓存与 JSON 不一致 | 中 | 高（事实污染） | `--no-cache` 对拍 + schema_version 强制整库 rebuild |
| Pipeline 重构回归 | 中 | 中（测试保护） | facade shim + 分 Step 灰度迁移 |
| Gateway 过度吞错，掩盖真实问题 | 中 | 中 | receipt 必写；fallback 必进 Review Center |
| 显式 backend 契约被 Gateway 偷偷改写 | 低 | 高 | requested/effective backend contract tests + 禁止 cross-backend failover |
| 初始选路模型与最终成功模型记录不一致 | 中 | 中 | 审计拆分 `model_selected / model_final`，Product Shell 与 runtime 共用同一份最终视图 |
| 插件前台契约漂移，重新逼迫插件读取 hidden state | 中 | 高 | 继续以 `launcher + aiwiki CLI + shell-summary` 为唯一正式前台契约 |
| 缓存数据库意外提交到 git | 低 | 低 | `.gitignore` 显式列入 `.aiwiki/cache.db`；如后续启用 pre-commit，再加二次拦截 |

## 5. 权衡与取舍

- **牺牲**：少量运行时复杂性（维护易失性 SQLite 缓存、Gateway 状态机、额外审计流）。
- **保卫**：Local-first、Markdown 作为唯一事实来源、deterministic baseline 可用、apply/revert/audit 闭环——**这四项是绝对不可妥协的底线**。
- **长期价值**：为"炼丹炉"从个人 10 万级知识资产扩张到 50 万级+ 提供一次性架构空间，且每一层优化都可独立回滚。

## 5.1 对当前默认模型的现实取舍

- 基于最近真实运行记录，`moonshotai/kimi-k2.5` 已经证明自己能在 `glm-5.1` 产物不满足输出契约时接住同一条 ask 请求。
- 因此当前把 `nvidia-nim-api` 的默认首选模型切到 `moonshotai/kimi-k2.5` 更符合“默认先选更容易成功完成完整 contract 的模型”这一原则。
- 但这不代表 `glm-5.1` 无效；它仍保留在同 backend 内的 fallback 链中，作为二跳模型继续存在。

## 6. 本文档 Review 记录

- **v1 (初版)**：仅列出四个优化方向与 4 个 Phase。
- **v2 (本版本)**：
  - 修正事实错误：LLM subprocess 调用**不**分布在 `app_execution.py`，只在 `llm.py`。
  - 补 Section 0 "非目标"声明。
  - 补 deterministic baseline fallback（对齐 `AGENTS.md`）。
  - 补 apply/revert 兼容性约束（对齐 `AGENTS.md` 的治理链）。
  - 补 SQLite 缓存的失效粒度、schema_version、逃生口。
  - 补风险矩阵与每 Phase 的回滚策略。
  - 加入真实行数与调用点数（经代码核对）。
- **v3 (当前版本)**：
  - 保留显式 backend 选择，不再建议跨 backend 自动 failover。
  - 把 `serve` 收口为 Obsidian 插件专用 local control plane，并加入 session token 约束。
  - 明确 compile/execution owner 边界：`compile/` 不承接 apply/revert/bundle/receipt。
  - 用 CLI 对等 local RPC 替换过度泛化的 REST API 形状。
  - 把 `cache` / `llm` 新增运行产物路径改到已忽略的 `.aiwiki/state` / `.aiwiki/logs` 体系，并补齐 `.aiwiki/cache.db` Git 忽略。
  - 修正 P1 范围：不再假设只改 `llm.py`，而是把 `runner.py` 的现有 retry/orchestration 一并纳入设计边界。
- **v4 (当前版本)**：
  - 吸收最新真实 LLM 调研：新增 `route health / probe health / contract health` 分层。
  - 把“成功样本可能来自模型级 fallback”写入 P1 设计前提。
  - 补充 `model_selected / model_final` 的审计一致性要求。
  - 新增 canary 设计：`llm-check` / `llm-check --probe` / 最小 `run-ask` 三段式验证。
  - 根据最近成功样本，把 `nvidia-nim-api` 的默认首选模型调整为 `moonshotai/kimi-k2.5`，同时保留 `z-ai/glm-5.1` 在同 backend fallback 链中。
- **v5 (当前版本)**：
  - 吸收产品与交互层面的 KISS 原则：在产品感知面上严格区分“机器内部态”（Wiki/JSON）与“用户关注产出”（Output/Judgment），只把最少必要信息通过通知抛给用户。
  - 在 P4 (Plugin Control Plane) 补充了“单输入/单输出”和“黑盒瘦客户端 (Thin Client)”的设计哲学。
- **v6 (当前版本)**：
  - 把 P4 从 `serve/RPC` 收回到当前已落地的 `launcher + aiwiki CLI + shell-summary` 契约，避免与 Product Shell 既有设计稿和 runtime plan 冲突。
  - 修正 execution owner 事实：当前 `app_compile.py` 仍是 apply/revert 对外入口，`app_execution.py` 只承接 bundle/receipt helper。
  - 修正 deterministic fallback 语义：当前只把 `run-ask` 的外层 fallback 和 `auto_process_once()` 的 compile/lint fallback 当成既有事实，不再把它写成所有 `run-*` 的现状契约。
  - 更新测试基线表述，不再把 Phase 2 验收写死在过时的 `309 tests`。
