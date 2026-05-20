# 机器记忆

- 最近编译时间：`2026-05-20T02:11:33+00:00`
- 运行时状态文件：`.aiwiki/state/machine-memory.json`
- 图谱导出文件：`.aiwiki/cache/machine-memory-graph.json`
- 漂移报告：`wiki/indexes/drift-report.md`
- 来源节点：`0`
- 判断节点：`0`
- 概念节点：`0`
- 来源到判断的边：`0`
- Judgment 到 Judgment 的边：`0`
- Judgment 到 Decision 的边：`0`
- 来源到概念的边：`0`
- 概念到概念的边：`0`
- 索引词数量：`0`
- 机器摘要：`5ca31c8ea69e89f4167e6b9ae5a0985d32ebb5382b82ee33b1641a2176bf8383`
- 图谱摘要：`f5f601586348141cb59f4afc4fab6c1a56cf15d36b9b45c2bfbfcc92b9154bcc`

## 图谱健康
- 连通分量：`0`
- 孤立来源：`0`
- 单节点概念：`0`
- 桥接概念：`0`
- 过载概念：`0`
- 已索引分量：`0`
- Hub 概念：`0`
- Hub 来源：`0`
- 修复候选：`0`
- 修复动作：`0`
- 动作已到期：`0`
- 动作需升级：`0`
- 执行批次：`0`
- 执行提案：`0`
- 页级 patch step：`0`
- 概念冲突信号：`0`
- 概念重写候选：`0`
- Rewrite 提案：`0`
- 可应用 Rewrite：`0`

## 判断层
- Judgment asset 节点：`0`
- Judgment review actions：`0`
- 决策索引：`wiki/indexes/decisions.md`
- 判断索引：`wiki/indexes/judgments.md`
- 审阅队列：`wiki/indexes/review-queue.md`

## 漂移摘要
- 缺失 raw 文件：`0`
- 缺失来源页：`0`
- 缺失概念页：`0`
- 无概念覆盖来源：`0`

## 相关链接
- [图谱健康](./graph-health.md)
- [拓扑视图](./machine-memory-topology.md)
- [动作队列](./machine-memory-actions.md)
- [修复计划](./machine-memory-repair-plan.md)
- [漂移报告](./drift-report.md)
- [修复待办](./repair-backlog.md)
- [概念质量](./concept-quality.md)
- [Rewrite Proposals](./rewrite-proposals.md)

## Action Workflow
- 状态文件：`.aiwiki/state/machine-memory-actions.json`
- 通过 `review-action` 推进 action status。
- nightly 会继续追踪 action 的 occurrences、aging 和 escalation。
- repair 计划页：`wiki/indexes/machine-memory-repair-plan.md`

## 查询加速
- `ask` 和 `run-ask` 先用机器记忆 term index 做第一轮查询规划。
- source-to-concept 和 concept-to-concept 边会在组装 prompt 前扩展候选范围。
- 查询规划还会提取最短图路径和触达分量，支持更深的检索。
- 图谱导出主要给 agent / tooling 使用，不建议直接人工修改。

## 重点概念
- 还没有编译出概念节点。

## 运行时规则
- [规则索引](../../schema/index.md)
- [引用规则](../../schema/citations.md)
- [冲突规则](../../schema/conflicts.md)
- [审阅规则](../../schema/review.md)
