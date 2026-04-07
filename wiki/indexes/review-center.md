---
title: "审阅中心"
kind: "dashboard"
---

# 审阅中心

这里是炼丹炉的人用审阅入口，负责把 pending review、aging、repair 和 concept rewrite 收拢到一个地方。

## 先看哪里

- [审阅队列](./review-queue.md)：处理 `decision / judgment` 的状态推进
- [Aging 报告](./aging-report.md)：看 overdue 和 escalation
- [概念质量](./concept-quality.md)：看弱概念、冲突信号、证据缺口、重写优先级
- [机器记忆动作队列](./machine-memory-actions.md)：看 machine-memory action lifecycle
- [机器记忆修复计划](./machine-memory-repair-plan.md)：看 execution batch 和 execution proposal
- [修复待办](./repair-backlog.md)：看 nightly 汇总出来的优先级队列

## 推荐顺序

1. 先处理升级项和已到期复审。
2. 再处理 accepted 的 machine-memory 修复动作。
3. 然后处理高优先级弱概念页和显式冲突信号。
4. 最后处理 deferred / watch 类项目。

## 边界

- 这里是入口页，不直接替代 `review-queue.md` 或 `repair-backlog.md`。
- 高风险修复仍然应通过 review 后执行，不要直接改写事实层。
