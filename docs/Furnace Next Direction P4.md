# Furnace Next Direction P4

P4 阶段要回答 P3 之后的核心问题：炼丹炉的 deterministic 地基已经足够支撑 9.0 dogfood，但要进入 9.5，必须证明 **LLM 执行层可用、trace 血缘可 demo、CLI 错误可自解释、dogfood 流程可复现**；因此 P4 不是扩功能，而是把第一次真实 dogfood receipt 暴露的阻塞点收敛成可独立合并、可验收、可回归的工程路线图。

> 来源证据：`output/reports/dogfood-receipt-v0.md`（炼丹炉 vault 内），含 12 个摩擦点 F1–F12 + F5/F9 真因调查 + F13/F14 派生发现。

---

## 阻塞 dogfood 9.5 必修

### P4-1：LLM backend compatibility gate

**目标**：把 F5/F9/F14 从"运行时才爆炸"变成"dogfood 前可检测、可解释、可选择"的 LLM 后端兼容性门禁。

**根因证据指针**：

- F5：`copilot-cli/gpt-5.4 frontmatter 成功率 0%`，`run-compile --limit 3` 最终 0/3 成功
- F9：`run-ask --lean --timeout 120` 仍 timeout，说明不是单个 compile prompt 问题
- F5/F9 真因：copilot CLI stdout 带 `●`、长横线、frontmatter reflow，和 `parse_frontmatter()` 严格围栏不兼容
- F14：现有三类后端在当前 dogfood 环境下均不可直接可靠使用，`codex --model gpt-5.5` 是新的候选

**验收判据**：

- dogfood 前存在一个明确的 LLM readiness 检查结果，至少能区分：
  - compatible
  - degraded
  - unavailable
  - requires credential
- `copilot-cli/gpt-5.4` 不再被误判为完全可用。
- `codex-cli/gpt-5.5` 若在本机可用，应被识别为推荐候选。
- LLM backend 不可用时，CLI 输出必须说明失败原因和下一步动作，而不是只在 compile/ask 中超时或 frontmatter reject。
- dogfood receipt 能记录本次使用的 backend、model、兼容性判断和失败原因。

**估时**：M

**依赖关系**：无；应作为 P4 第一优先级。

---

### P4-2：LLM response observability receipt

**目标**：所有 LLM 成功/失败都必须留下可审计原始响应路径，避免再次靠手工 subprocess 复刻排查。

**根因证据指针**：

- F5 最初只表现为 `Compile response is missing frontmatter`，根因必须绕过 ai-wiki 直接调 copilot 才能看见
- F13 派生建议：raw LLM response 写盘到 receipt
- audit-preview 已能记录 runtime history 和 LLM receipts，但缺少原始响应定位

**验收判据**：

- 任意 LLM 调用失败时，receipt 中必须包含：
  - backend/model
  - timeout 或 parser error 类型
  - raw response artifact 路径，若无响应则明确写 `no_response`
- frontmatter parse failure 时，可以直接从 receipt 找到原始 stdout/stderr。
- audit-preview 能追溯到 LLM 失败事件，不需要重新运行命令复现。
- 不改变 deterministic fallback 的行为。

**估时**：S/M

**依赖关系**：建议先于或并行 P4-1；它是 P4-1 的排障基础设施。

---

### P4-3：Trace concept layer support

**目标**：让 `trace` 能识别 concept layer，并展示 source→concept 派生边，恢复 read-side 第二站的血缘 demo 能力。

**根因证据指针**：

- F8：`trace jetson` / `trace concept-jetson` / `trace wiki/concepts/jetson.md` 三种入口全 `not_found`
- source page trace 只能回自己一行，说明 graph 未构 source→concept 派生边
- 最终主链路中 trace concept 是 9.5 阻塞点

**验收判据**：

- 对已有 concept page，以下入口至少一种稳定可用，最好三种都可用：
  - concept slug
  - concept file path
  - source-derived concept reference
- `trace <concept>` 能返回 concept 本身及其上游 source。
- `trace <source> --down` 能显示 source 派生出的 concept。
- JSON 输出的 `kind` 不应错误兜底成 `receipt`。
- 使用 Batch A fixture 能稳定复现并通过回归测试。

**估时**：M

**依赖关系**：无；和 P4-1 并列为 9.5 必修。

---

## CLI / UX 类

### P4-4：Review workflow boundary clarification

**目标**：消除 `file-back --kind derived` 可以落盘但 `review-page` 拒收的死支线，让用户知道哪些 artifact 可进入 review。

**根因证据指针**：

- F11：`file-back --kind derived` 正常落盘但 `review-page` 拒收
- dogfood 主链路必须改用 `kind=judgment` 才能继续

**验收判据**：

- CLI help、错误消息或 workflow 文档明确说明：
  - derived 是否进入 review
  - judgment/decision 的 review 语义
  - 推荐 dogfood 链路应该用哪一种 kind
- 用户不需要读源码即可完成 `file-back → review-page`。
- 若 derived 仍不进入 review，失败消息必须解释替代路径。
- 若 derived 被纳入 review，则 audit/review 语义必须保持清晰，不污染 judgment/decision 层。

**估时**：S/M

**依赖关系**：无。

---

### P4-5：Review status schema self-discovery

**目标**：让 `review-page --status` 的错误信息直接暴露合法值，避免第一次使用必须翻源码。

**根因证据指针**：

- F12：`--status approved` 报错但不说明 judgment 合法值
- 合法值需要从源码推断：judgment=`tentative/tracking/confirmed/rejected`，decision=`approved/...`

**验收判据**：

- status 非法时，错误信息包含当前 page kind 对应的合法 status 集合。
- decision 和 judgment 的 status 不再混淆。
- CLI help 或 schema 文档能直接查到合法状态。
- dogfood 中 `approved` 用错位置时，用户能按提示一次修正为 `confirmed` 或其他合法值。

**估时**：S

**依赖关系**：可与 P4-4 合并为同一 PR，但仍应保持独立验收。

---

### P4-6：run-compile limit / fail-fast semantics clarification

**目标**：澄清 `run-compile --limit` 和 fail-fast 的语义，避免用户误以为 limit=3 一定尝试 3 份。

**根因证据指针**：

- F7：`limit=3` 但只尝试 1 份，fail 即退出
- F5 中 `run-compile --limit 3` 最终 0/3 成功，但实际行为容易误读

**验收判据**：

- CLI help 明确说明 `--limit` 是候选数量、成功数量、还是最大尝试数量。
- fail-fast 行为若是设计，错误输出必须说明"已因首个失败停止"。
- fail-fast 行为若不是设计，则需有回归测试覆盖 limit 下多个 source 的尝试行为。
- receipt 中能看出 attempted / succeeded / failed / skipped 的数量差异。

**估时**：S

**依赖关系**：建议在 P4-2 之后做，因为 LLM receipt observability 能帮助统计 attempted/failure。

---

## 基础设施类

### P4-7：Dogfood-aware watch service mode

**目标**：避免 `aiwiki-watch.service` 在 dogfood 前后自动抢跑 compile，保证 receipt 链路可复现、可归因。

**根因证据指针**：

- F1：systemd user service 自 Apr 21 起持续运行 codex-cli 自动 compile，污染 dogfood 链路
- 本次 dogfood 全程必须 stop+disable watch service

**验收判据**：

- dogfood 模式下 watch service 状态可见、可控。
- receipt 明确记录 watch service 是 enabled/disabled/running/stopped。
- 如果 watch service 会影响 dogfood，启动前必须给出阻断或强提醒。
- 不改变普通用户日常 watch 行为。

**估时**：S/M

**依赖关系**：无。

---

### P4-8：wiki/indexes layer separation

**目标**：把手写 dashboard 和 compile 派生 index 分层，避免 cleanup 和 dogfood baseline 判断错误。

**根因证据指针**：

- F3：`wiki/indexes/` 混合 6 份手写 dashboard + 19 份 compile 派生
- 影响 dogfood receipt 中"投喂前 vault 干净"的可信度

**验收判据**：

- hand-written index 与 derived index 可机器区分。
- cleanup 不会误删手写 dashboard，也不会误保留派生垃圾。
- receipt 能声明 index 层清理状态，并说明哪些是 static、哪些是 derived。
- 现有 vault 不需要手工大规模迁移才能继续 dogfood。

**估时**：M

**依赖关系**：无；但建议在 P4-7 之后做，减少自动 compile 干扰。

---

### P4-9：Concept extractor noise floor reduction

**目标**：降低 concept graph 的停用词噪声，提高 deterministic concept layer 的信噪比。

**根因证据指针**：

- F6：23 个 concepts 中 9 个是停用词级 token：`for/one/kind/mode/task/sub/2026/captured/capture`
- concept graph 信噪比偏低
- deterministic compile 当前生成 23 concepts

**验收判据**：

- Batch A 上停用词级 concept 明显减少。
- 关键 robotics/VLM/navigation concept 不被误删。
- concept 数量下降必须有 receipt 或测试说明，不追求越少越好。
- trace 和 ask 的 ranked concepts 仍能命中主要主题。

**估时**：S/M

**依赖关系**：建议在 P4-3 之后做；先让 trace concept 可见，再优化 concept 质量。

---

## 流程类

### P4-10：Review SOP hardening for test output

**目标**：修补评审 SOP，避免再次出现高分评审漏看 unittest 末尾失败。

**根因证据指针**：

- F2：M9 评审 9.7/10 漏看 `FAILED (errors=1)`
- 已修复 fixture drift：commit `86812f9`

**验收判据**：

- QA/review SOP 明确要求检查测试输出末尾 summary。
- review 结论不能只看前段 green log。
- 若测试存在 error/failure，即使主体功能可用，也不能给出"无阻塞"结论。
- 后续 dogfood receipt 中记录 reviewer 是否执行该检查。

**估时**：S

**依赖关系**：无。

---

### P4-11：Dogfood vault path explicitness follow-up

**目标**：把 F4 的已修事项从 env 层扩展到启动提示和操作边界，防止 agent/CLI 再误把 runtime repo 当 vault。

**根因证据指针**：

- F4：`.envrc.dogfood` 缺 vault 显式化，导致 agent 误改 ai-wiki 源码仓库 3 个 commit
- 已修复：commit `82130a6` 加 `AIWIKI_DOGFOOD_VAULT`

**验收判据**：

- dogfood 启动时清晰显示：
  - runtime repo path
  - target vault path
  - active protocol
- 如果当前目录看起来是 runtime repo 而不是 vault，CLI/文档必须提醒。
- receipt 记录 vault path 与 repo path，避免事后混淆。
- 不改变普通非 dogfood 使用路径。

**估时**：S

**依赖关系**：无；作为 follow-up，不阻塞 P4-1/P4-3。

---

## 不该做的事 / Non-goals

P4 不解决以下范围，除非后续单独立项：

- 不做 hosted service。
- 不做 multi-user sync。
- 不引入 heavy RAG infra。
- 不做 fine-tuning。
- 不把 raw/wiki/output 分层规则推倒重来。
- 不把 dogfood vault 和 ai-wiki runtime repo 合并。
- 不把 fallback 变成静默降级；fallback 必须继续可见、可审计。
- 不追求一次性支持所有 LLM provider；P4 只要求本地 dogfood 可检测、可选择、可解释。
- 不做 P5+ 的大规模 protocol 泛化；本次 dogfood 只覆盖 `research`。
- 不做长周期 drift 结论；本次没有完整等待 24h。
- 不把 concept extractor 优化扩展成完整 ontology / taxonomy 系统。
- 不实现复杂权限、多用户审计或远端发布流程。

---

## 顺序建议

### 先做 P4-1 + P4-2

理由：

- F5/F9/F14 是 dogfood 9.5 的最大阻塞，当前 LLM 层在实际 receipt 中等价不可用。
- P4-2 是最高 ROI 的可观测性补洞；没有 raw response receipt，后续 LLM 问题仍会反复变成黑盒排查。
- 两者能直接回答"炼丹炉是否可以可靠使用某个 LLM backend"。

### 并行或紧随做 P4-3

理由：

- F8 是另一个 9.5 必修阻塞。
- deterministic 层已可用，但 trace concept 不通会让"可审计、可追溯、看派生"的核心 demo 断裂。
- P4-3 不依赖 LLM 修复，可以并行推进。

### 之后按体验影响排序

建议顺序：

1. P4-4 / P4-5：修 review UX，减少第一次使用摩擦。
2. P4-7 / P4-8：修 dogfood 可复现性和 layer hygiene。
3. P4-9：降低 concept 噪声。
4. P4-10 / P4-11：流程 hardening 和 F4 follow-up。
5. P4-6：澄清 limit/fail-fast 语义，可与 CLI help 改进合并处理。

---

## 风险与未知

- 本次 dogfood 只跑 Batch A=10 份 robotics navigation + VLM 文档，不能代表所有文档类型。
- protocol 只覆盖 `research`，没有覆盖 investing/product/ops/general。
- drift 阶段没有完整等待 24h，不能评价 aging/drift 的真实表现。
- LLM root cause 主要基于当前本机 CLI/provider 状态；不同账号、模型、CLI 版本可能表现不同。
- `codex-cli/gpt-5.5` 只是调查中发现的高概率可用候选，仍需单独 dogfood 验证。
- copilot CLI 输出装饰可能随版本变化；P4 应以 compatibility gate 为准，不硬编码信任某个当前表现。
- concept extractor 降噪有误删关键概念的风险，必须用 Batch A 回归验证。
- watch service 修复需要避免破坏日常自动 compile 体验。
- wiki/indexes 分层调整涉及已有 vault 内容，必须保证可回滚、可审计，不做隐式迁移。
- review workflow 是否纳入 derived 是语义决策，不能只按 CLI 方便性处理。
