# Furnace Agentic Debt Autopilot

## Principle

炼丹炉的 agentic 边界是：系统核心不能自己修改，非核心知识、治理、内容和运行债务默认交给 LLM 全权处理。这里的“全权”不是无审计写盘，而是 LLM 可以决定并执行非核心 debt 的处理，runtime 必须提供 receipt、验证、回滚或补偿 receipt。

核心 manual-only 面：

- runtime 代码与脚本
- `schema/`
- `prompts/`
- `policy/`
- `.aiwiki/state/autonomy-policy.json`
- `raw/`
- 凭据、env、远端发布和部署

非核心 LLM-owned 面：

- `wiki/sources` 的摘要和解释层
- `wiki/concepts`
- `wiki/decisions`
- `wiki/judgments`
- `wiki/elixirs`
- machine-memory actions
- concept rewrite proposals
- review / repair / archive debt
- L3 metadata/governance debt, when policy classifies it as safe and non-core
- `output/` 中由 runtime 管理的报告与控制面

## Runtime Shape

- `src/aiwiki/debt_autopilot.py` 是 owner-state collector，不依赖 Product Shell controls。
- `collect_debt_inventory()` 聚合 source summary backlog、weak concepts、rewrite candidates、judgment review debt 和 machine-memory actions；只把 policy 分类为 `non_core_semantic` 的项目计入 `llm_owned_non_core` remaining。
- `run_debt_autopilot()` 默认 dry-run；在 nightly light apply 打开时会复用 `run_compile` 消化 source summary debt，生成/处理 concept rewrite debt，并自动消化 accepted low-risk action debt；不把 proposed semantic debt 降级成 human-required。
- Content debt 按 source 逐项执行，单个 LLM timeout / backend failure 只记录为该项失败，不阻塞后续 debt。
- Weak-only concepts 也进入 rewrite generation；生成后的 proposal 必须保持 active/current，才能被自动 accept/apply。
- Concept rewrite verification 会规范化等价的本地 wikilink / markdown link / rendered local link 形式，但仍保留 source signature、source pages、frontmatter 和 summary drift 检查。
- `agent_loop` 每轮写入 `debt_autopilot` 结果；`signal_pipeline` 暴露 `debt_inventory`。
- `dogfood_maturity_gate.py` 输出 `debt_autopilot_report`，用于观察 debt detected / auto resolved / remaining。

## Safety Contract

- Product Shell 只展示 debt-autopilot 结果，不参与无人值守 apply 判定。
- Judgment auto-adopt 使用 atomic write，page、receipt、history、runtime history 任一步失败必须回滚。
- `split-overloaded-concept` 的 auto-retire 纳入 `apply-action` 主事务回滚域。
- Concept rewrite 只应用 current/valid proposal；stale 或 invalid candidate 会 skip，不会强写。
- Core L3 仍是 proposal-only；metadata/governance L3 不能伪装成 `llm_owned_non_core` debt。
- deterministic fallback 只能维护结构和暴露失败，不能生成语义内容冒充 LLM 成功。

## Maturity Signals

Live dogfood proof 需要同时观察：

- `agentic_autonomy_report.llm_governed_apply_count > 0`
- `agentic_autonomy_report.core_auto_apply_count = 0`
- `debt_autopilot_report.debt_auto_resolved_count`
- `debt_autopilot_report.debt_remaining_count`
- `human_required_report.routine_primary_debt_count = 0`
- 连续 nightly / maturity receipts

`debt_remaining_count > 0` 不自动代表失败；它表示仍有非核心 debt 等待 LLM-governed apply、补偿 receipt 或后续素材支撑。真正的失败是 core auto-apply、非核心 hidden human-required、或 LLM 失败被伪装成 deterministic success。

## Dogfood Evidence

2026-06-01 在真实 dogfood vault `/home/tim/danlu/炼丹炉` 上执行 debt-autopilot 小批次消化：

- pending source summaries 清零。
- weak/rewrite concept debt 清零。
- verified debt-autopilot rewrite applies: `20`。
- latest maturity snapshot: `output/control/maturity-gate/snapshot-20260601T073134Z.json`。
- `debt_autopilot_report.status=clear`，`debt_remaining_count=0`。
- `agentic_autonomy_report.status=pass`，`llm_governed_apply_count=20`，`violations=[]`。
