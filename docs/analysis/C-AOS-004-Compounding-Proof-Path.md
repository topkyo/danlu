# C — AOS-004 翻盘路径分析：从 `not-yet` 到 `pass`

> 只读分析。不修改 runtime / schema / gate 阈值。
> SoT：`scripts/dogfood_maturity_gate.py`、`docs/Furnace Agent OS Slimdown Plan.md`、`docs/Furnace Investing Dogfood Plan.md`、`PROGRESS.md`。

## 1. 问题陈述

AOS-004 已完成工程实施。`scripts/dogfood_maturity_gate.py` 在真实 dogfood vault（`/home/tim/danlu/炼丹炉`）跑出的 verdict 是 `not-yet`，**唯一缺口**为：

```
missing: trace_provenance_backed_compounding_sample
```

也就是说：六项硬指标（backlog_total、l3_proposal_counts_by_state、judgment_review_receipt_counts、prompts_ask_sha256、raw_to_wiki_count、output_file_back_rate）都已经有真实数据，**唯独缺一个能通过 receipt/trace 精确回链的 end-to-end 复用样本**。

这是炼丹炉作为 Agent OS 当前最关键的产品价值证明缺口。

## 2. `compounding_sample` 在 gate 中的判定逻辑

从 `scripts/dogfood_maturity_gate.py` 提取的判定约束：

```python
COMPOUNDING_REUSE_REF_PREFIXES = (
    "wiki/judgments/",
    "wiki/decisions/",
    "wiki/elixirs/",
)
COMPOUNDING_SAMPLE_OPERATIONS = {"ask", "file-back", "run-ask"}
FAILED_RECEIPT_STATUSES = {"blocked", "error", "failed", "reverted"}
```

要产出一个合法 sample，必须同时满足：

1. **存在一次 `ask` / `run-ask` / `file-back` 操作的 receipt**（即 `execution-receipts.jsonl` 中有 op ∈ COMPOUNDING_SAMPLE_OPERATIONS）。
2. **receipt 的 status 不在 FAILED 集合**。
3. **该 receipt 的 trace/provenance 字段引用了至少一条 `wiki/judgments/` 或 `wiki/decisions/` 或 `wiki/elixirs/` 资产**——即派生知识被复用，而不只是 raw source 被引用。
4. **该派生资产本身可以回链到更早的 receipt**（即知识资产不是孤儿，而是被前一轮 mutation 生成的）。

只有 (1)+(2)+(3)+(4) 同时成立，才算"trace-backed compounding sample"。

## 3. 当前为什么跑不出 sample

基于已读 `Furnace Investing Dogfood Plan.md` 和 `Furnace Next Direction Post-P4.md`，可推断的断点（按可能性排序）：

### 断点 A：派生资产的 trace 链路未落盘到 receipt
当前 `ask` / `run-ask` 命令在生成 output report 时，receipt 中可能只记录了 `raw_refs`（原始来源），但 **未显式列出该次问答实际复用了哪些 `wiki/judgments/*.md` / `wiki/decisions/*.md` / `wiki/elixirs/*.md`**。

判据：gate 脚本扫的是 receipt 中的 trace.provenance 引用前缀；如果 receipt 只写 `raw/...` 而不写 `wiki/judgments/...`，gate 永远拿不到 sample。

### 断点 B：`file-back` 写回时没有继承上一轮 provenance
`file-back` 是把 output 反馈回 `wiki/decisions/` 或 `wiki/elixirs/` 的关键动作。如果 file-back receipt 只记录"这一次写入了哪个文件"，但不记录"这次写入基于哪一次 ask 的 output、那次 ask 又复用了哪些前置 wiki 资产"，那么链路就在 file-back 这一步断开。

### 断点 C：派生资产存在但不是"被复用"，而是"首次创建"
当前 dogfood vault 已有：
- `raw_to_wiki_count = 25`（25 个原始 → wiki）
- `judgment_or_elixir_reuse_count = 22`（22 个判断/金丹被引用）
- `output_file_back_rate = 0.2909`

但"被引用 22 次"是基于文本扫描的静态计数，**不等于"在 receipt 里被声明为这次操作的 input dependency"**。Gate 要求的是动态、可追溯的复用证据。

### 断点 D：所有合格 sample 都恰好命中 FAILED_RECEIPT_STATUSES
可能性较低，但需要排除——LLM 调用超时/退化的 receipt 会被打 `error` 标签从而被 gate 跳过。

## 4. 翻盘路径：从 `not-yet` 到 `pass` 的最小动作集

按 ROI 排序：

### 路径 1（推荐）：补 receipt 的 `trace.provenance.wiki_refs` 字段
**改动面**：`src/aiwiki/trace.py`、`src/aiwiki/app_execution.py`、`src/aiwiki/runner/`（具体取决于 ask/run-ask/file-back 的 receipt 写入点）。
**核心动作**：
- 在 `ask` / `run-ask` 执行链路里，把"渲染 prompt 时实际注入了哪些 wiki/judgments/* / wiki/decisions/* / wiki/elixirs/*"显式收集为列表，写入 receipt 的 `trace.provenance.wiki_refs`。
- `file-back` 写入新 decision/elixir 时，把"本次基于哪个 ask receipt id"作为 `trace.parent_receipt_id` 记录。
**约束**：receipt schema 是审计层，必须做向后兼容（新字段为 optional，旧 receipt 不报错）。
**预期收益**：第一次跑出 1-2 个合法 sample，gate verdict 翻 `pass`。

### 路径 2：在 dogfood vault 里手工跑一次完整复利链路
即使路径 1 落地了，也需要至少一次"自然发生"的 end-to-end 复用：
- (a) drop 一份新 raw → compile → 生成 wiki/sources。
- (b) ask 一个问题，让 LLM 在回答时显式调用 `wiki/judgments/` 或 `wiki/elixirs/` 中已有的判断/金丹。
- (c) file-back 把 output 反馈成新的 decision/elixir，引用 (b) 的 receipt。
- (d) 跑 `scripts/dogfood_maturity_gate.py` 验证 sample 出现。
**关键**：(b) 步骤的 LLM 路由必须有明确的"先检索 wiki 派生层、再回答"机制；如果当前 ask prompt 只塞 raw，根本不会复用 wiki/judgments。

### 路径 3：审视 `prompts/ask.md` 是否引导模型复用 wiki 派生层
检查 dogfood vault 的 `prompts/ask.md`（其 sha256 是 gate 的固定输入）：
- 是否显式让模型先看 `wiki/judgments/` / `wiki/elixirs/`？
- 是否在回答里要求列出"本回答复用了哪些 wiki 资产"？
- 如果只是"基于 raw 回答问题"，那么知识复利根本不会发生。

## 5. 不推荐的翻盘方式（反模式）

- ❌ **降低 gate 阈值**：把 `compounding_sample == null` 判为 pass。这等于伪造，违反 AOS-004 设立初衷。
- ❌ **造假 receipt**：手写一条 trace.provenance.wiki_refs 而没有真实操作背书。`PROGRESS.md` 明确要求"不通过隐藏、删除或伪造 backlog 来制造复杂度下降"。
- ❌ **改用静态扫描充当 sample**：用 `judgment_or_elixir_reuse_count` 替代 trace-backed sample。Gate 已经分了静态 count 和动态 sample 两层，混用就丧失证明意义。
- ❌ **绕过 receipt 写 mock sample**：所有 sample 必须从真实 `execution-receipts.jsonl` 推出。

## 6. 时间盒与决策点

| 阶段 | 估算 | 决策点 |
|---|---|---|
| 路径 3 prompt 审视 | 0.5 day | 如果 prompt 已正确，跳到路径 1 |
| 路径 1 schema 扩展 | 1-2 day | receipt 向后兼容是硬约束 |
| 路径 2 自然 dogfood 跑通 | 2-5 day | 需要真实问答场景，不可加速 |
| Gate 验证 | 0.5 day | 翻 pass 后写 `AOS-004 Compounding Proof Receipt.md` |

总成本约 1 周（不含 LLM 不稳定带来的重试）。这是炼丹炉 6.5 万行代码当前最高 ROI 的工程动作。

## 7. 翻盘后会发生什么

`compounding_sample` 一旦出现：
1. `dogfood_maturity_gate.py` verdict 翻 `pass`。
2. AOS-004 真正完结，AOS Slimdown Plan 全部 4 milestone 收口。
3. 解锁 Slimdown 下一轮（AOS-005，详见 B 文档）：从"机制扩张冻结"转为"机制减法"。
4. 6.5 万行核心代码从"自证可能性"切换到"证明 ROI"——后续每一行代码删除都有 trace-backed 复利样本作为参考基线。

## 8. 单句结论

> **AOS-004 的 `not-yet` 不是工程失败，而是诚实信号；翻盘的关键是把 receipt 从"记录我做了什么"升级为"记录我用了什么前置知识做了什么"。**
