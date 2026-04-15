# 机器记忆动作队列

- 最近编译时间：`2026-04-15T03:43:15+00:00`
- 动作总数：`8`
- 高优先级：`2`
- 中优先级：`0`
- 低优先级：`6`
- 已到期：`0`
- 已升级：`0`
- 已清除：`7`
- 状态文件：`.aiwiki/state/machine-memory-actions.json`

## 状态分布
- `待处理`：`8`
- `已接受`：`0`
- `暂缓`：`0`
- `已解决`：`0`
- `已拒绝`：`0`

## Planner
- Planner state：`.aiwiki/state/planner-state.json`
- Pending proposals：`8`
- Blocked proposals：`6`
- Next action：`overloaded-concept-and` | 拆分过载概念 And | score `78`
- Planner queue:
  - `overloaded-concept-and` | 拆分过载概念 And | score `78` | blocked `False`
  - `overloaded-concept-the` | 拆分过载概念 The | score `78` | blocked `False`
  - `bridge-concept-abstract` | 观察桥接概念 Abstract | score `32` | blocked `True`
  - `bridge-concept-agents` | 观察桥接概念 Agents | score `32` | blocked `True`

## 已升级动作
- 当前没有需要升级处理的动作。

## 已到期动作
- 当前没有已到期待处理的动作。

## 优先队列
- [high] 拆分过载概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | occurrences `37` | component `component-1`
- [high] 拆分过载概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | occurrences `34` | component `component-1`
- [low] 观察桥接概念 Agents | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/agents.md` | occurrences `57` | component `component-1`
- [low] 观察桥接概念 Abstract | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/abstract.md` | occurrences `57` | component `component-1`
- [low] 观察桥接概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | occurrences `54` | component `component-1`
- [low] 观察桥接概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | occurrences `54` | component `component-1`
- [low] 观察桥接概念 Protocol | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/protocol.md` | occurrences `37` | component `component-1`
- [low] 观察桥接概念 Concepts | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/concepts.md` | occurrences `13` | component `component-1`

## 补链动作
- 当前没有此类动作。

## 孤立来源动作
- 当前没有此类动作。

## 单节点概念动作
- 当前没有此类动作。

## 过载概念动作
- [high] 拆分过载概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | first `2026-04-15T01:54:06+00:00` | seen `37` | 当前挂接 `8` 个来源，可能过宽。
- [high] 拆分过载概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | first `2026-04-15T01:54:46+00:00` | seen `34` | 当前挂接 `12` 个来源，可能过宽。

## 桥接概念观察
- [low] 观察桥接概念 Agents | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/agents.md` | first `2026-04-15T01:37:58+00:00` | seen `57` | 概念连接 `8` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Abstract | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/abstract.md` | first `2026-04-15T01:37:58+00:00` | seen `57` | 概念连接 `2` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | first `2026-04-15T01:49:42+00:00` | seen `54` | 概念连接 `23` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | first `2026-04-15T01:49:42+00:00` | seen `54` | 概念连接 `18` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Protocol | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/protocol.md` | first `2026-04-15T01:54:06+00:00` | seen `37` | 概念连接 `7` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Concepts | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/concepts.md` | first `2026-04-15T01:37:58+00:00` | seen `13` | 概念连接 `7` 个相关概念，属于图谱桥接点。

## 引用快照刷新
- 当前没有此类动作。

## 最近清除
- [待处理] 观察桥接概念 Url | last_seen `2026-04-15T03:10:40+00:00` | inactive_since `2026-04-15T03:14:25+00:00`
- [待处理] 扩展单节点概念 Base | last_seen `2026-04-15T03:10:40+00:00` | inactive_since `2026-04-15T03:14:25+00:00`
- [待处理] 拆分过载概念 Url | last_seen `2026-04-15T03:08:22+00:00` | inactive_since `2026-04-15T03:10:19+00:00`
- [待处理] 观察桥接概念 Agent | last_seen `2026-04-15T01:53:07+00:00` | inactive_since `2026-04-15T01:54:06+00:00`
- [待处理] 观察桥接概念 Paper | last_seen `2026-04-15T01:45:54+00:00` | inactive_since `2026-04-15T01:49:42+00:00`
- [待处理] 观察桥接概念 Overview | last_seen `2026-04-15T01:45:54+00:00` | inactive_since `2026-04-15T01:49:42+00:00`
- [待处理] 连接孤立来源 统一的炼丹炉 | last_seen `2026-04-15T01:38:32+00:00` | inactive_since `2026-04-15T01:45:54+00:00`

## 最近执行回执
- 当前还没有 safe execution receipt。

## 相关链接
- [机器记忆](./machine-memory.md)
- [拓扑视图](./machine-memory-topology.md)
- [修复计划](./machine-memory-repair-plan.md)
- [图谱健康](./graph-health.md)
- [修复待办](./repair-backlog.md)
