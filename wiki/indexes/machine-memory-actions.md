# 机器记忆动作队列

- 最近编译时间：`2026-04-16T02:09:53+00:00`
- 动作总数：`8`
- 高优先级：`2`
- 中优先级：`0`
- 低优先级：`6`
- 已到期：`0`
- 已升级：`0`
- 已清除：`9`
- 状态文件：`.aiwiki/state/machine-memory-actions.json`

## 状态分布
- `待处理`：`7`
- `已接受`：`1`
- `暂缓`：`0`
- `已解决`：`0`
- `已拒绝`：`0`

## Planner
- Planner state：`.aiwiki/state/planner-state.json`
- Pending proposals：`8`
- Blocked proposals：`7`
- Next action：`overloaded-concept-and` | 拆分过载概念 And | score `92`
- Planner queue:
  - `overloaded-concept-and` | 拆分过载概念 And | score `92` | blocked `False`
  - `overloaded-concept-the` | 拆分过载概念 The | score `74` | blocked `True`
  - `bridge-concept-abstract` | 观察桥接概念 Abstract | score `32` | blocked `True`
  - `bridge-concept-agents` | 观察桥接概念 Agents | score `32` | blocked `True`

## 已升级动作
- 当前没有需要升级处理的动作。

## 已到期动作
- 当前没有已到期待处理的动作。

## 优先队列
- [high] 拆分过载概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | occurrences `73` | component `component-1`
- [low] 观察桥接概念 Agents | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/agents.md` | occurrences `96` | component `component-1`
- [low] 观察桥接概念 Abstract | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/abstract.md` | occurrences `96` | component `component-1`
- [low] 观察桥接概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | occurrences `93` | component `component-1`
- [low] 观察桥接概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | occurrences `93` | component `component-1`
- [low] 观察桥接概念 Protocol | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/protocol.md` | occurrences `76` | component `component-1`
- [low] 观察桥接概念 Judgment | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/judgment.md` | occurrences `38` | component `component-1`
- [high] 拆分过载概念 And | status `已接受` | band `manual-repair` | policy `manual-repair` | primary `wiki/concepts/and.md` | occurrences `76` | component `component-1`

## 补链动作
- 当前没有此类动作。

## 孤立来源动作
- 当前没有此类动作。

## 单节点概念动作
- 当前没有此类动作。

## 过载概念动作
- [high] 拆分过载概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | first `2026-04-15T01:54:46+00:00` | seen `73` | 当前挂接 `12` 个来源，可能过宽。
- [high] 拆分过载概念 And | status `已接受` | band `manual-repair` | policy `manual-repair` | primary `wiki/concepts/and.md` | first `2026-04-15T01:54:06+00:00` | seen `76` | 当前挂接 `8` 个来源，可能过宽。

## 桥接概念观察
- [low] 观察桥接概念 Agents | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/agents.md` | first `2026-04-15T01:37:58+00:00` | seen `96` | 概念连接 `11` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Abstract | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/abstract.md` | first `2026-04-15T01:37:58+00:00` | seen `96` | 概念连接 `4` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 The | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/the.md` | first `2026-04-15T01:49:42+00:00` | seen `93` | 概念连接 `24` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 And | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/and.md` | first `2026-04-15T01:49:42+00:00` | seen `93` | 概念连接 `19` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Protocol | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/protocol.md` | first `2026-04-15T01:54:06+00:00` | seen `76` | 概念连接 `11` 个相关概念，属于图谱桥接点。
- [low] 观察桥接概念 Judgment | status `待处理` | band `review-first` | policy `triage` | primary `wiki/concepts/judgment.md` | first `2026-04-15T09:19:10+00:00` | seen `38` | 概念连接 `8` 个相关概念，属于图谱桥接点。

## 引用快照刷新
- 当前没有此类动作。

## 最近清除
- [已解决] 刷新引用快照 Protocol Boundary Judgment | last_seen `2026-04-15T09:49:48+00:00` | inactive_since `2026-04-15T09:49:48+00:00`
- [待处理] 观察桥接概念 Concepts | last_seen `2026-04-15T08:01:21+00:00` | inactive_since `2026-04-15T09:19:10+00:00`
- [待处理] 观察桥接概念 Url | last_seen `2026-04-15T03:10:40+00:00` | inactive_since `2026-04-15T03:14:25+00:00`
- [待处理] 扩展单节点概念 Base | last_seen `2026-04-15T03:10:40+00:00` | inactive_since `2026-04-15T03:14:25+00:00`
- [待处理] 拆分过载概念 Url | last_seen `2026-04-15T03:08:22+00:00` | inactive_since `2026-04-15T03:10:19+00:00`
- [待处理] 观察桥接概念 Agent | last_seen `2026-04-15T01:53:07+00:00` | inactive_since `2026-04-15T01:54:06+00:00`
- [待处理] 观察桥接概念 Paper | last_seen `2026-04-15T01:45:54+00:00` | inactive_since `2026-04-15T01:49:42+00:00`
- [待处理] 观察桥接概念 Overview | last_seen `2026-04-15T01:45:54+00:00` | inactive_since `2026-04-15T01:49:42+00:00`

## 最近执行回执
- [已解决] 刷新引用快照 Protocol Boundary Judgment | receipt `output/control/execution-receipts/refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment.json` | updated `2026-04-15T09:49:48+00:00`

## 相关链接
- [机器记忆](./machine-memory.md)
- [拓扑视图](./machine-memory-topology.md)
- [修复计划](./machine-memory-repair-plan.md)
- [图谱健康](./graph-health.md)
- [修复待办](./repair-backlog.md)
