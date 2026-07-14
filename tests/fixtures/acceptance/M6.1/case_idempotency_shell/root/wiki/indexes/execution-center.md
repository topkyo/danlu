# 执行中心

这里是炼丹炉的人用执行入口，负责把 repair action、page-level patch plan 和 safe apply 候选收拢到一个地方。

## 先看哪里

- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch、proposal 和 patch plan
- [机器记忆动作队列](./machine-memory-actions.md)：看 action lifecycle 和 ready actions
- [审阅中心](./review-center.md)：看 aging、rewrite 和 pending review
- [认知历史](./cognitive-history.md)：看哪些 judgment 已因证据漂移需要拉回复审
- [执行审计](./execution-audit.md)：看 apply / revert 历史和策略分级
- [炉心面板](./furnace-center.md)：看统一产品壳入口
- `output/control/execution-center.html`：本地执行面板；这是浏览器 / 系统 HTML 入口，不是 Obsidian 内部页面。

## 怎么用

1. 先看 accepted 的 safe apply action。
2. 再看 execution proposal 和 page-level patch plan。
3. 需要深入时，再跳到具体 proposal 页面或目标页面。

## 边界

- 这里优先展示 reviewable execution plan，不自动 apply 高风险修复。
- safe apply 仍只覆盖 allowlist 内的低风险动作。
