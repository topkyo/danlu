# 执行审计

这里是炼丹炉的人用执行审计入口，负责把 execution receipt、revert 历史、policy 分级和协议分布收拢到一个地方。

## 先看哪里

- [执行中心](./execution-center.md)：看当前 ready action、proposal 和 patch plan
- [认知历史](./cognitive-history.md)：对照 judgment drift 和 review history 决定是否升级修复
- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和页级 patch plan
- [机器记忆动作队列](./machine-memory-actions.md)：看 action lifecycle 和 policy
- `output/control/execution-audit.html`：本地执行审计面板；这是浏览器 / 系统 HTML 入口，不是 Obsidian 内部页面。

## 怎么用

1. 先看最近 apply / revert 是否符合预期。
2. 再看 policy bands 是否和当前动作状态一致。
3. 最后看协议分布和 receipt history，确认执行层没有漂移。

## 边界

- 这里负责审计，不直接替代 execution-center。
- receipt history 仍然是 file-based，本页展示的是当前快照。
