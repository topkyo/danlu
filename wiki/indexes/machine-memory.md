# 机器记忆

- 最近编译时间：`2026-04-07T09:50:15+00:00`
- 运行时状态文件：`.aiwiki/state/machine-memory.json`
- 图谱导出文件：`.aiwiki/cache/machine-memory-graph.json`
- 漂移报告：`wiki/indexes/drift-report.md`
- 来源节点：`0`
- 概念节点：`0`
- 来源到概念的边：`0`
- 概念到概念的边：`0`
- 索引词数量：`0`
- 机器摘要：`93afc12caa746000fbf7659e7fddef3c61e3666e45e1124367379e1d2d7f5fad`
- 图谱摘要：`f5f601586348141cb59f4afc4fab6c1a56cf15d36b9b45c2bfbfcc92b9154bcc`

## 图谱健康
- 连通分量：`0`
- 孤立来源：`0`
- 单节点概念：`0`
- 桥接概念：`0`
- 过载概念：`0`
- 已索引分量：`0`

## 判断层
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
- [漂移报告](./drift-report.md)
- [修复待办](./repair-backlog.md)

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
