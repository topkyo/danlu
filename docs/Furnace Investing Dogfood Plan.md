# 炼丹炉 Investing 协议端到端 Dogfood Plan

> 性质：原 contract，**已转 receipt 化**。本文档保留作为长期 dogfood SoT，新增"实跑历史"章节（§8）记录 v0 / v1 落地。
> 状态：`closed-with-v0-and-v1-receipts`（2026-05-01）— 首两次实跑已完成，receipt 落 dogfood vault；后续 dogfood 仍按本文档 §2 七步 flow 推进
> 来源：`docs/Furnace Next Direction Post-P4.md` §D-4
> 实跑 receipt：
> - v0 (2026-04-30, 9 min, 3 demo notes, codex-cli/gpt-5.5)：dogfood vault `output/reports/dogfood-receipt-investing-v0.md`
> - v1 (2026-05-01, +PDF + 双 backend)：dogfood vault `output/reports/dogfood-receipt-investing-v1.md`

> **当前状态校准（2026-05-20）**：本文是 investing dogfood 的原始 contract + receipt index，不代表当前唯一运行口径。v2 / v2.1 后续已在 2026-05-12 跑通并写入 `PROGRESS.md`：v2 真实研报 dogfood 7/7 收官，v2.1 自动 L3 proposal 周期与 accept→apply→revert 真链路收口。当前普通 CLI/runtime 默认主路由已变为 `opencode-api/deepseek-v4-pro`，`codex-cli/gpt-5.5` 只作为显式手动 route；历史 v0/v1 backend 记录保留为当时 receipt 事实。

---

## 0. 为什么开这条 dogfood

炼丹炉五个 protocol（general / investing / research / product / ops）都已落 schema，但截止 2026-04-30：

- **research / general / ops** 协议已通过 Round 28-46 的 Eva Robot Batch / VLA / 监控 dogfood 验证
- **investing** 协议从未跑通过一次完整 `drop 研报 → judgment → distill → ask 复用金丹 → L3 改 prompt` 闭环

这是炼丹炉 thesis（"给单人投资研究做知识复利"）最关键的 product proof。在本协议跑通之前：

- 不能宣称炼丹炉是"投资研究复利系统"
- 不能确定 investing protocol 的 review window / file-back 模板 / recurring promotion 语义是否在真实数据上 hold
- 不知道 LLM-backed compile 在真实研报（PDF + 中文）上的成功率
- 不能产出 investing 专属的金丹和 L3 prompt proposal

## 1. 范围与边界

### 1.1 In-Scope

- protocol：仅 `investing`（不混入其他协议）
- 输入素材类型：
  - A 股 / 美股研报 PDF
  - 公司年报 / 季报 PDF
  - 行业访谈 / 电话会议纪要（手工 paste 到 `drop note`）
  - 关键 URL（招股书披露、监管公告）
- 输出资产：
  - 至少 1 个 `settled` investing elixir（含完整 provenance + DAG）
  - 至少 1 条 investing protocol L3 prompt proposal（手工 reject 也算闭环）
  - 至少 1 条 investing judgment 走完 review-page 全状态机（tentative → tracking → confirmed）
  - 完整 dogfood 摩擦报告（receipt 引用）
- LLM backend：显式 nvidia-nim-api 或 codex-cli/gpt-5.x（视当时可用度）；不允许隐式切换

### 1.2 Out-of-Scope

- 不做投资建议生成（炼丹炉是知识复利系统，不是策略生成器）
- 不接入实时行情数据
- 不做组合优化、回测、自动调仓
- 不在 dogfood 中修改 runtime 行为；只对暴露出来的摩擦点写 follow-up milestone
- 不跑超出本机 LLM quota 的批量任务（每批 ≤5 份研报 + 显式 cost / token 记录）

### 1.3 非目标

- 不为 investing dogfood 修改 review/apply/revert/audit 状态机
- 不为 investing dogfood 引入新 schema 字段
- 不在 investing 协议下隐式开启 L3 auto-accept
- 不破坏 9+ feasibility contract 任一条款

## 2. 7 步 Flow

### 2.1 准备

```bash
# 切到 dogfood vault（避免污染 ai-wiki repo）
source .envrc.dogfood
cd "$AIWIKI_DOGFOOD_VAULT"

# 确认 backend 可用
PYTHONPATH=/home/tim/ai-wiki/src python3 -m aiwiki.cli --root . llm-check --probe --format human

# 切到 investing 协议
PYTHONPATH=/home/tim/ai-wiki/src python3 -m aiwiki.cli --root . protocol-set investing
PYTHONPATH=/home/tim/ai-wiki/src python3 -m aiwiki.cli --root . protocol-status
```

**Stop**：若 `llm-check --probe` 返回 `unavailable / requires_credential`，停止 dogfood，把状态记录到摩擦报告 `R-LLM-001`，等 backend ready 再继续。

### 2.2 投料（Drop）

每批 ≤5 份材料，分类型批投：

```bash
# 研报 PDF
aiwiki drop pdf /path/to/research-report-2025q4-XXX.pdf
aiwiki drop pdf /path/to/research-report-2025q4-YYY.pdf

# 公司年报
aiwiki drop pdf /path/to/company-annual-2024.pdf

# 行业访谈纪要（paste 模式）
aiwiki drop note --title "行业访谈：XX 行业增长动能" --text "$(< /tmp/transcript.md)"

# URL 公告
aiwiki drop url https://example.com/announcement-2025
```

**摩擦记录点**：
- F-INV-1：`drop pdf` 是否只保留 PDF 原件到 `raw/assets`，后续 compile/analysis 不把抽取文本写回 raw 原料
- F-INV-2：`drop note` 文本超过 N 字时是否截断或异常
- F-INV-3：manifest/runtime history 是否包含完整原始文件指针，raw 原料文件本身不写入 frontmatter / capture metadata

### 2.3 Compile

```bash
# 先 deterministic compile（不依赖 LLM）确认 manifest / source pages 干净
aiwiki compile

# LLM enrichment（受控 worker 入口）
AIWIKI_LLM_BACKEND=nvidia-nim-api aiwiki run-compile --limit 5

# 检查 compile 结果
aiwiki today
ls wiki/sources/
```

**Adaptive timeout（P4-INV-NEW-1）**：

`run-compile` 在创建 LLM client 时按 pending 队列里最大 raw 字节自适应估算 per-call timeout：

```
timeout_seconds = clamp(
    ceil(max_raw_bytes / BYTES_PER_PAGE) * SECONDS_PER_PAGE,
    floor = 240,   # 4 min, 防止过短
    ceil  = 1800,  # 30 min, 防止过长
)
# BYTES_PER_PAGE = 30_000；SECONDS_PER_PAGE = 60
```

规则：
- 若用户显式设置 `AIWIKI_LLM_TIMEOUT`，env 始终优先，adaptive helper 返回 `None`，沿用 `LLMConfig.from_env` 行为
- pending 为空时返回 `None`，等同未启用 adaptive，仍走 env / 默认
- pending 非空但所有 raw 都不可 stat（缺失 / 越出 vault root / 路径穿越）时回退到 floor（240s）
- 该 timeout 仅作用于本次 `run-compile` 进程，不修改 `LLMConfig.timeout_seconds=120` 默认值，不写入任何配置文件

**摩擦记录点**：
- F-INV-4：LLM compile 在中文 PDF source 上的 frontmatter 成功率
- F-INV-5：concept 抽取是否产生 investing 领域噪声词（"金额 / 季度 / 公司"等通用词应过滤）
- F-INV-6：source page 与 raw 引用关系是否能被 trace 反查
- F-INV-7：每份 compile 的 token usage / cost / duration 记录是否完整

### 2.4 Judgment 与 Decision

针对单份研报或单家公司创建 judgment：

```bash
# 通过 ask 生成 query artifact
aiwiki ask "公司 X 在 2025q4 的核心增长驱动是什么？反证有哪些？" --format report --protocol investing

# review query artifact，通过后 file-back 为 judgment
aiwiki file-back output/reports/<query-id>.md --kind judgment

# 走 review-page 状态机
aiwiki review-page wiki/judgments/<judgment-id>.md --status tentative --note "初筛"
aiwiki review-page wiki/judgments/<judgment-id>.md --status tracking --note "等 q4 财报印证"
aiwiki review-page wiki/judgments/<judgment-id>.md --status confirmed --note "财报印证逻辑成立"
```

**摩擦记录点**：
- F-INV-8：investing protocol 的 review window 是否与 dogfood 节奏匹配
- F-INV-9：file-back 的 investing 模板是否包含 thesis / catalyst / risk / invalidation 字段
- F-INV-10：confirm judgment 后 trace 链路是否完整指向所有 source

### 2.5 Distill 金丹

```bash
# 用同一 corpus 多轮 ask，让 active corpus 收敛
aiwiki ask "公司 X / Y / Z 在赛道 A 的相对竞争位置？" --format report --corpus <corpus-id>
aiwiki ask "赛道 A 的最大风险是什么？谁最先扛不住？" --corpus <corpus-id>

# promote 高价值 output 到 wiki/derived
aiwiki promote output/reports/<query-id>.md

# 起 elixir 候选
aiwiki alchemy-start <corpus-id> --topic "赛道 A 投资 thesis 2025q4"
aiwiki alchemy-distill <elixir-id> --question "如果赛道增长低于预期，thesis 在什么情况下被打破？"
aiwiki alchemy-finalize <elixir-id>
aiwiki alchemy-promote --elixir-id <elixir-id>
```

**摩擦记录点**：
- F-INV-11：counter_evidence gate 是否在真实研究材料上 hold（而不是 NONE_FOUND 兜底）
- F-INV-12：DAG 校验在 promote 失败时的错误消息可读性
- F-INV-13：金丹的 confidence_level 与 review_after 默认值是否合理

### 2.6 Compounding（复利复用）

```bash
# 先直接 ask 新问题；ask 当前不接 --include-elixir，旧丹复用通过下一步 alchemy-start --include-elixir 注入
aiwiki ask "新公司 W 是否符合赛道 A 的投资 thesis？" --protocol investing

# 起新金丹引用旧金丹（D-3 已在单元测试覆盖；这里实跑）
aiwiki alchemy-start <new-corpus> --topic "赛道 A 2026q1 thesis 演进" --include-elixir <old-elixir-id>
```

**摩擦记录点**：
- F-INV-14：`alchemy-start/-distill --include-elixir` 是否真的能让 LLM 拿到旧丹结论
- F-INV-15：跨季度的金丹更新是否会形成无效循环引用
- F-INV-16：trace 反查跨金丹链是否清晰

### 2.7 L3 Prompt Proposal

```bash
# 观察 review queue 中的 generate-proposal candidates
aiwiki review proposal-generation
aiwiki review proposals

# 或显式生成 L3 proposal 候选
aiwiki l3-proposal-generate --apply

# 人工 review；reject 或 accept
aiwiki review proposal <proposal-id> --status rejected --note "本批 dogfood 信号还不够"
# 或：
aiwiki apply <proposal-id>
```

**摩擦记录点**：
- F-INV-17：投资场景下 L3 proposal 的命中率
- F-INV-18：投资 prompt 的关键约束（thesis / catalyst / risk / invalidation 必填）是否被 proposal 触及
- F-INV-19：proposal accept 后 prompt 改进是否明显改变 ask 输出质量

### 2.8 执行模式（execute-mode）开启与 F-INV-18 复现

v2 dogfood 暴露：默认 planner replay 跑在 `observe_only` 模式，所有 planner-log records 都不带 `side_effects_allowed: true`，下游 candidate generator（`l3-proposal-generate`）会把它们标 `requires_execute_mode` 拒绝采纳，自动路径永远断在第一步。要复现 F-INV-18 / F-INV-19 的完整链路，必须显式开启 execute-mode。

**关键概念区分**（不要混淆）：

- `aiwiki planner-log-replay --execute`：把 signals 以 execute-mode 写入 `planner-log.jsonl`，让 records 带 `side_effects_allowed: true`。这是 candidate 准入的前置条件，本身**不**生成 L3 proposal。
- `aiwiki l3-proposal-generate --apply`：扫 planner-log（要求 `mode=execute` 记录）→ 产生 L3 proposal candidate → 写入 `output/_proposals/prompt/` 或 `output/_proposals/policy/`。这是真正生成 proposal 的入口。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1` + `aiwiki run-nightly`：agentic 默认开启，作用于**已存在**的 candidate proposal，但只会自动登记 `metadata_only` candidate；不无人值守写核心 prompt/policy。

**入口**：

```bash
# 步骤 1：把当前 signals 以 execute-mode 写入 planner-log
# 默认 observe-only；--execute 让 records 带 side_effects_allowed=true
aiwiki planner-log-replay --execute

# 可选：指定 signals 路径（默认读 .aiwiki/state/signals.jsonl）
aiwiki planner-log-replay --execute --signals-path .aiwiki/state/signals.jsonl
```

**行为差异**：

- `observe_only`（默认）：planner-log 落 `mode=observe_only` + `side_effects_allowed: false`；candidate generator 会打 `requires_execute_mode` blocker，拒绝采纳
- `--execute`：planner-log 落 `mode=execute` + `side_effects_allowed: true` + `reason_codes: [..., execute_mode_requested]`；解锁 `src/aiwiki/execution/l3_proposals.py` 中 `mode == "execute"` 路径，candidate 才能被生成

**风险边界**：

- `planner-log-replay --execute` 本身只写 `.aiwiki/state/planner-log.jsonl`（追加，可通过 rollback marker 回退）
- `l3-proposal-generate --apply` 会通过 `append_wiki_log` 写 `wiki/indexes/log.md` 一条记录，并生成 `output/_proposals/prompt/*.md`（或 `output/_proposals/policy/*.md`）
- `aiwiki apply <proposal-id>` 会在 human accepted 后写真 `prompts/*.md`（prompt proposal）或 `schema/policies/*`（policy proposal）；`metadata_only` 只写 receipt/state，不改目标文件。`AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1` 不绕过这个人审 gate
- 不影响 raw/ 与 wiki/sources/ 与 wiki/derived/；不触发 LLM 调用
- manual-first 仍是默认；不显式加 `--execute` 不会触发副作用

**F-INV-18 复现示例**（真 vault）：

```bash
# 1. 在 dogfood 期内确保 vault 有新 signals（drop / compile / drift_scan 后会自然产生）
source .envrc.dogfood

# 2. 开启 execute-mode planner replay（前置条件）
aiwiki planner-log-replay --execute

# 3. 生成 L3 proposal candidate（真正的 candidate 生成入口）
aiwiki l3-proposal-generate --apply

# 4. 查看新落盘的 L3 proposal
aiwiki review proposals
ls output/_proposals/prompt/ output/_proposals/policy/ 2>/dev/null

# 5. 人工 accept 后才能写核心目标；metadata_only proposal 可由 nightly 自动登记
aiwiki review proposal <proposal-id> --status accepted --note "reviewed"
aiwiki apply <proposal-id>
```

**F-INV-18 成功判据**：

- `output/_proposals/prompt/` 或 `output/_proposals/policy/` 出现新 proposal 文件
- 新 proposal 的 `evidence_refs` / `signal_ids` 对应的 planner-log records 有 `trace_id` ≠ 历史 trace `9a396669-ab7d-4123-ad2c-0e5350fb05d0`（证明是 fresh trace 产生）
- 备注：proposal 本身不存 `source_trace_id`；trace 出处需经 planner-log 反查（`signal_id` → `trace_id` 字段）

## 3. 验收标准

dogfood 完成判据（必须全部命中）：

- [ ] 至少 1 份 PDF / Note / URL drop 成功：PDF 原件落 `raw/assets`，Note/URL 落 `raw/inbox`，metadata 只进 manifest/history 或派生层
- [ ] 至少 1 份 source 通过 LLM compile 产生 wiki/sources frontmatter
- [ ] 至少 1 个 investing judgment 走完 `tentative → tracking → confirmed` 三态
- [ ] 至少 1 个 settled investing elixir 通过 promote receipt 与 counter_evidence gate
- [ ] 至少 1 条 investing L3 prompt proposal 走完 generate → review → reject/accept
- [ ] 完整摩擦报告（F-INV-1 ~ F-INV-19 每条都有 yes/no/N/A 状态 + 证据 receipt 引用）
- [ ] 摩擦报告作为 `output/reports/dogfood-receipt-investing-v0.md` 落盘
- [ ] dogfood 期间所有 LLM 调用的 backend / model / 累计 token / 失败重试都有 receipt 可查

## 4. Stop Lines

中止 dogfood 并升级的硬条件：

1. backend 不可用且无替代（`unavailable / requires_credential`）
2. 连续 3 份 PDF compile 失败且根因指向 runtime（不是 PDF 本身）
3. counter_evidence gate 在 promote 时反复因 schema 不一致拒绝
4. 触发了 9+ feasibility contract 任一硬约束（hidden backend / 无 receipt 写回 / raw/ 被覆盖）
5. dogfood 期间发现需要修改 review/apply/revert 状态机才能继续

## 5. 摩擦报告模板

落盘到 `output/reports/dogfood-receipt-investing-v0.md`：

```markdown
---
kind: dogfood-receipt
protocol: investing
version: 0
backend: <backend-id>
model: <model-id>
started_at: <ISO>
ended_at: <ISO>
total_tokens: <int>
total_cost_usd: <float, optional>
---

# Investing Protocol Dogfood Receipt v0

## 概览
- 投料数：<int> PDF / <int> Note / <int> URL
- compile 成功率：<float>
- judgment 数：<int>
- elixir 数：<int>
- L3 proposal 数：<int>
- 阻塞次数：<int>

## 7 步 flow 完成度
- [x/ ] 准备
- [x/ ] 投料
- [x/ ] compile
- [x/ ] judgment / decision
- [x/ ] distill
- [x/ ] compounding
- [x/ ] L3 proposal

## 摩擦点详单
F-INV-1 ~ F-INV-19，每条：
- 状态：yes / no / N/A
- 现象：<observation>
- 证据：<receipt path / log path>
- 是否阻塞：<bool>
- 建议：<follow-up milestone proposal>

## 跨协议偏差
对比 research / general / ops dogfood：investing 在哪些环节表现明显不同？

## 下一步建议
- P4-INV-X：<follow-up milestone>
```

## 6. 与现有 SoT 的关系

- 上层 SoT：`docs/Furnace Agent Architecture.md` + `docs/Furnace Evolution Mechanics.md`
- 直接引用方向：`docs/Furnace Next Direction Post-P4.md` §D-4
- 历史 dogfood receipt 参考：`docs/archive/Furnace Next Direction P4.md` 引用的 `dogfood-receipt-v0.md`（research protocol）
- 不替代：本文档只是 contract，实跑后产出的 receipt 是另一份独立 artifact

## 7. 文档生命周期

- 当前 `status: historical-contract-and-receipt-index`。
- 原 `pending(blocked-on-llm)` 状态已由 v0/v1 实跑关闭；后续 v2 / v2.1 dogfood 继续沿 §2 七步 flow 推进，并以 `PROGRESS.md` 与 dogfood vault receipt 作为执行事实。
- 新摩擦点的 actionable items 继续写入独立 milestone / contract（如 `P4-INV-*`、`F-INV-*`），不直接把本文升级成新的 active contract。
- 本契约文档保留为 dogfood SoT 的历史参考；涉及当前 backend、自动化成熟度或 clean vault 状态时，以 `README.md`、`docs/Furnace Runtime Operations.md`、`PROGRESS.md` 和当前 active contract 为准。

## 8. 实跑历史（receipt index）

### 8.1 v0（2026-04-30，Round 56）
- 投料：3 条 demo investing note（NVDA Q4 thesis / 推理芯片格局 / TSMC CoWoS）
- Backend：codex-cli/gpt-5.5（唯一 compatible）
- 产出：1 settled investing elixir + 1 confirmed judgment + 1 rejected L3 proposal
- 19 条 F-INV-* 摩擦点首次盘点
- Receipt：dogfood vault `output/reports/dogfood-receipt-investing-v0.md`
- 评分：Investing 协议端到端 4 → 7-8/10

### 8.2 v1（2026-05-01，Round 58–59）
- 新增投料：1 条 Q1'26 update note + 1 条 ALERT counter-evidence note + 1 份真实中文 PDF（340KB robotics API 文档）
- Backend：codex-cli/gpt-5.5（主）+ nvidia-nim-api/openai/gpt-oss-120b（备）双 compatible
- 新增产出：
  - **首个跨周期复利 settled elixir**（`elixir-nvda-q1-26-thesis-squeeze-risk-b157a58a` 引用 `elixir-nvda-4-thesis-invalidation-8fa6db3f`）
  - 8 条 counter-evidence cards 浮入 today（修了 silent breakage）
  - PDF 中文 ingestion path 验证通过
- F-INV-* 摩擦点状态：F-INV-1 / 4 / 5 / 9 / 13 / 14 / 16 全部 **fixed**
- P4-INV-1 / 2 / 3 / 4 全部 **closed**（commits `8bd33f5`, `0b4dabe`）
- Receipt：dogfood vault `output/reports/dogfood-receipt-investing-v1.md`
- 评分：Investing 协议 7-8 → **9/10**；加权综合 8.95 → **9.05/10**

### 8.3 v2（2026-05-12，真实研报 dogfood）
- 输入：3 份真实中文 PDF（韦尔 / 宁德 / 恒瑞），共 752 页 / 16.5MB 量级。
- Backend：`opencode-api/deepseek-v4-pro`。
- 结果：§2.1-§2.7 七步 flow 收官为 7/7；file-back judgment、settled elixir、derived trace、drift aging、manual L3 proposal rejection 均有 receipt / runtime 记录。
- 新摩擦点：F-INV-NEW-1~4 与 F-INV-11-revisit 后续均已拆 milestone 收口；详见 `PROGRESS.md` 2026-05-12 条目。

### 8.4 v2.1（2026-05-12，自动 L3 proposal 真链路）
- NEW-5 暴露 execute-mode 路径；F-INV-18a 修正自动 proposal 内容空洞；F-INV-18 跑通 alchemy-demote → execution receipt → signals-replay → planner-log-replay → l3-proposal-generate 自动候选链路。
- F-INV-19 完成 accept→apply→revert 真链路，对 `prompts/ask.md` 的污染被 deterministic revert 清除。
- 结论：自动 proposal 机制可审计、可回滚，但 prompt 内容质量仍需后续 contract 改进；不等于放开无人值守自改 prompt。
