# C — AOS-004 翻盘路径分析：从 `not-yet` 到 `pass`

> 只读分析。不修改 runtime / schema / gate 阈值。
> SoT：`scripts/dogfood_maturity_gate.py`、`docs/Furnace Agent OS Slimdown Plan.md`、`docs/Furnace Investing Dogfood Plan.md`、`PROGRESS.md`。

## 1. 问题陈述

AOS-004 的 maturity gate 已有实现并可运行，但 active contract 尚未收口。`scripts/dogfood_maturity_gate.py` 在真实 dogfood vault（`/home/tim/danlu/炼丹炉`）跑出的 verdict 是 `not-yet`，**唯一缺口**为：

```
missing: trace_provenance_backed_compounding_sample
```

也就是说：AOS-004 关注的 knowledge compounding metrics（`raw_to_wiki_count`、`judgment_or_elixir_reuse_count`、`output_file_back_rate`、`receipt_backed_actions`、`human_required_exception_count`）都已经有真实数据，**唯独缺一个能通过 output provenance + receipt 精确匹配的 end-to-end 复用样本**。

这是炼丹炉作为 Agent OS 当前最关键的产品价值证明缺口。

## 2. `compounding_sample` 在当前 gate 中的判定逻辑

从 `scripts/dogfood_maturity_gate.py` 当前实现提取的判定约束：

```python
COMPOUNDING_REUSE_REF_PREFIXES = (
    "wiki/judgments/",
    "wiki/decisions/",
    "wiki/elixirs/",
)
COMPOUNDING_SAMPLE_OPERATIONS = {"ask", "file-back", "run-ask"}
FAILED_RECEIPT_STATUSES = {"blocked", "error", "failed", "reverted"}
```

要产出一个合法 sample，当前必须同时满足：

1. **存在一个 output markdown artifact**（不含 `output/control`），其 frontmatter 的 `derived_from` 或 `source_files` 至少引用一条 `wiki/judgments/`、`wiki/decisions/` 或 `wiki/elixirs/` 资产。
2. **存在匹配该 artifact path 的 receipt**。当前 gate 从 `output/control/execution-receipts/**/*.json` 和 `.aiwiki/state/execution-receipts.jsonl` 聚合 receipt，并用 receipt 的 `target_file` / `target_subject_id` / `primary_path` 与 artifact path 匹配。
3. **匹配 receipt 的 operation 属于 `ask` / `run-ask` / `file-back`**。
4. **匹配 receipt 的 status 不在 FAILED 集合**。空 status 也会被视为非 failed。

只有 (1)+(2)+(3)+(4) 同时成立，才算当前实现中的"trace/provenance-backed compounding sample"。

重要修正：当前 gate **并不读取** receipt 内的 `trace.provenance.wiki_refs` 或 `trace.parent_receipt_id`。这些字段是更强、更理想的审计 schema，可作为后续硬化方向，但不是 AOS-004 现行 pass 的硬要求。当前测试 `test_collect_metrics_reports_pass_for_receipt_backed_compounding_sample` 也证明：只要 output frontmatter + receipt path 匹配成立，即使没有 trace 字段也能 pass。

## 3. 当前为什么跑不出 sample

基于已读 `Furnace Investing Dogfood Plan.md` 和 `Furnace Next Direction Post-P4.md`，可推断的断点（按可能性排序）：

### 断点 A：output artifact frontmatter 没有记录派生层复用
当前 dogfood vault 已经存在判断/金丹复用的静态迹象，但可能没有任何 `output/**/*.md` 的 `derived_from` / `source_files` 写入 `wiki/judgments/*`、`wiki/decisions/*` 或 `wiki/elixirs/*`。

判据：gate 首先扫 output frontmatter。若 output 只记录 `raw/...` 或 `wiki/sources/...`，即使 prompt 实际读过 judgment/elixir，也不会形成 sample。

### 断点 B：output artifact 有派生层引用，但 receipt target 没对上 artifact path
当前 gate 用 receipt 的 `target_file` / `target_subject_id` / `primary_path` 与 output path 做精确匹配。如果 receipt 记录的是 run id、临时 path、control artifact path，或缺少 target 字段，就无法把 output 与 receipt 接上。

### 断点 C：派生资产存在但不是 receipt-backed 复用
当前 dogfood vault 已有：
- `raw_to_wiki_count = 25`（25 个原始 → wiki）
- `judgment_or_elixir_reuse_count = 22`（22 个判断/金丹被引用）
- `output_file_back_rate = 0.2909`

但"被引用 22 次"是基于文本/metadata 扫描的静态计数，**不等于"某个 output artifact 同时具备派生层引用和匹配成功 receipt"**。Gate 要求的是 output provenance 与 receipt 的交集。

### 断点 D：所有匹配 sample 都恰好命中 FAILED_RECEIPT_STATUSES
可能性较低，但需要排除——LLM 调用超时/退化的 receipt 会被打 `error` 标签从而被 gate 跳过。

## 4. 翻盘路径：从 `not-yet` 到 `pass` 的最小动作集

按 ROI 排序：

### 路径 1（推荐）：让 ask/run-ask output frontmatter 保留派生层引用
**改动面**：`src/aiwiki/execution/ask.py`、`src/aiwiki/runner/workflows.py`、prompt/source selection 相关路径（具体取决于 output artifact 的 frontmatter 写入点）。
**核心动作**：
- 在 `ask` / `run-ask` 的 context/provenance 收集链路里，识别实际注入或选择的 `wiki/judgments/*`、`wiki/decisions/*`、`wiki/elixirs/*`。
- 写 output artifact frontmatter 的 `derived_from` 或 `source_files` 时保留这些派生层 refs，而不是只保留 raw/source refs。
- 确认对应 receipt 的 `target_file` / `primary_path` 指向同一个 output artifact。
**约束**：frontmatter schema 必须向后兼容；不能为了 pass 手写历史 artifact 或伪造复用。
**预期收益**：真实 dogfood 只要跑出 1 个复用派生层资产的 output，gate verdict 即可翻 `pass`。

### 路径 1b（后续硬化）：补 receipt 的 `trace.provenance.wiki_refs` / `parent_receipt_id`
这是更强的审计 schema，但不是当前 AOS-004 pass 的最短路径。它的价值是把 sample 从"output frontmatter + receipt target 匹配"升级为"receipt 自身声明 input dependency + parent receipt 链"。如果实施，必须作为向后兼容 optional 字段，并同步更新 gate/tests 后再把它升为硬要求。

### 路径 2：在 dogfood vault 里手工跑一次完整复利链路
即使路径 1 落地了，也需要至少一次"自然发生"的 end-to-end 复用：
- (a) drop 一份新 raw → compile → 生成 wiki/sources。
- (b) ask 一个问题，让 LLM 在回答时显式调用 `wiki/judgments/` 或 `wiki/elixirs/` 中已有的判断/金丹。
- (c) file-back 把 output 反馈成新的 decision/elixir，引用 (b) 的 receipt。
- (d) 跑 `scripts/dogfood_maturity_gate.py` 验证 sample 出现。
**关键**：(b) 步骤的 runtime provenance 必须把派生层 ref 写回 output frontmatter；只在正文里提到 judgment/elixir 不足以通过当前 gate。

### 路径 3：审视 `prompts/ask.md` 是否引导模型复用 wiki 派生层
检查 dogfood vault 的 `prompts/ask.md`（其 sha256 是 gate 的固定输入）：
- 是否显式让模型先看 `wiki/judgments/` / `wiki/elixirs/`？
- 是否在回答里要求列出"本回答复用了哪些 wiki 资产"？
- 如果只是"基于 raw 回答问题"，那么知识复利根本不会发生。

## 5. 不推荐的翻盘方式（反模式）

- ❌ **降低 gate 阈值**：把 `compounding_sample == null` 判为 pass。这等于伪造，违反 AOS-004 设立初衷。
- ❌ **造假 receipt**：手写一条 trace.provenance.wiki_refs 而没有真实操作背书。`PROGRESS.md` 明确要求"不通过隐藏、删除或伪造 backlog 来制造复杂度下降"。
- ❌ **改用静态扫描充当 sample**：用 `judgment_or_elixir_reuse_count` 替代 trace-backed sample。Gate 已经分了静态 count 和动态 sample 两层，混用就丧失证明意义。
- ❌ **绕过 receipt 写 mock sample**：所有 sample 必须从真实 `output/control/execution-receipts/**/*.json` 或 `.aiwiki/state/execution-receipts.jsonl` 推出。

## 6. 时间盒与决策点

| 阶段 | 估算 | 决策点 |
|---|---|---|
| 路径 3 prompt/context 审视 | 0.5 day | 确认 ask 是否会选择派生层资产 |
| 路径 1 output provenance 修复 | 1-2 day | frontmatter 向后兼容是硬约束 |
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

> **AOS-004 的 `not-yet` 不是工程失败，而是诚实信号；当前最短翻盘路径是让真实 output artifact 的 `derived_from/source_files` 保留派生层知识引用，并确保它能精确匹配成功 receipt。receipt 内部 trace 链路是后续硬化方向，不是当前 gate 的现行硬要求。**
