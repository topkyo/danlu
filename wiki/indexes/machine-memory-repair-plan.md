# 机器记忆修复计划

- 最近编译时间：`2026-04-15T09:49:48+00:00`
- Ready 动作：`0`
- 待分流动作：`8`
- 暂缓动作：`0`
- 最近清除：`9`
- 执行批次：`0`
- 执行提案：`8`
- 页级 patch step：`18`
- Blocked proposals：`6`
- 状态文件：`.aiwiki/state/machine-memory-actions.json`

## Planner State
- Planner state：`.aiwiki/state/planner-state.json`
- Pending proposals：`8`
- Unblocked：`2`
- Blocked：`6`
- Next action：`overloaded-concept-and` | 拆分过载概念 And | score `78` | blocked `False`
- Priority queue:
  - `overloaded-concept-and` | 拆分过载概念 And | score `78` | impact `70` | blocked `False`
  - `overloaded-concept-the` | 拆分过载概念 The | score `78` | impact `70` | blocked `False`
  - `bridge-concept-abstract` | 观察桥接概念 Abstract | score `32` | impact `32` | blocked `True`
  - `bridge-concept-agents` | 观察桥接概念 Agents | score `32` | impact `32` | blocked `True`
  - `bridge-concept-and` | 观察桥接概念 And | score `32` | impact `32` | blocked `True`
  - `bridge-concept-judgment` | 观察桥接概念 Judgment | score `32` | impact `32` | blocked `True`

## Ready Now
- 当前没有 ready action。

## Need Triage
- [high] 拆分过载概念 And | primary `wiki/concepts/and.md` | band `review-first` | next 把过载概念拆成更窄的概念页或子主题。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`
- [high] 拆分过载概念 The | primary `wiki/concepts/the.md` | band `review-first` | next 把过载概念拆成更窄的概念页或子主题。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-the --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 Agents | primary `wiki/concepts/agents.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-agents --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 Abstract | primary `wiki/concepts/abstract.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-abstract --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 The | primary `wiki/concepts/the.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-the --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 And | primary `wiki/concepts/and.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-and --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 Protocol | primary `wiki/concepts/protocol.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-protocol --status accepted --note "Accepted for manual repair."`
- [low] 观察桥接概念 Judgment | primary `wiki/concepts/judgment.md` | band `review-first` | next 确认桥接概念仍然必要，并记录观察结论。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-judgment --status accepted --note "Accepted for manual repair."`

## Deferred
- 当前没有暂缓动作。

## Execution Batches
- 当前没有可执行批次。

## Execution Proposals
- [high] 拆分过载概念 And | status `待处理` | kind `split-concept` | risk `high` | score `78` | targets `wiki/concepts/and.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`
  - strategy: 拆分过载概念，明确子概念边界和来源分流。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/overloaded-concept-and.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - edit: 先定义更窄的子概念名称和边界。
  - edit: 把 source pages 重新分流到更具体的概念页。
  - edit: 在原概念页保留拆分说明和跳转链接。
  - patch `wiki/concepts/and.md` | role `概念页` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - patch `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - patch `wiki/indexes/rewrite-proposals.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- [high] 拆分过载概念 The | status `待处理` | kind `split-concept` | risk `high` | score `78` | targets `wiki/concepts/the.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-the --status accepted --note "Accepted for manual repair."`
  - strategy: 拆分过载概念，明确子概念边界和来源分流。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/overloaded-concept-the.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - edit: 先定义更窄的子概念名称和边界。
  - edit: 把 source pages 重新分流到更具体的概念页。
  - edit: 在原概念页保留拆分说明和跳转链接。
  - patch `wiki/concepts/the.md` | role `概念页` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - patch `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - patch `wiki/indexes/rewrite-proposals.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- [low] 观察桥接概念 Abstract | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/abstract.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-abstract --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-abstract.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/abstract.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`
- [low] 观察桥接概念 Agents | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/agents.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-agents --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-agents.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/agents.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`
- [low] 观察桥接概念 And | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/and.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-and --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-and.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/and.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`
- [low] 观察桥接概念 Judgment | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/judgment.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-judgment --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-judgment.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/judgment.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`
- [low] 观察桥接概念 Protocol | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/protocol.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-protocol --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-protocol.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/protocol.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`
- [low] 观察桥接概念 The | status `待处理` | kind `monitor-bridge` | risk `low` | score `32` | targets `wiki/concepts/the.md` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-the --status accepted --note "Accepted for manual repair."`
  - strategy: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
  - bundle: `output/control/execution-bundles/bridge-concept-the.json`
  - rollback: 回滚时需要人工恢复目标页，然后重跑 compile。
  - depends_on: `overloaded-concept-and, overloaded-concept-the`
  - edit: 在 concept page 里补一段 bridge maintenance note。
  - edit: 确认相关概念链接仍然成立。
  - edit: 如果桥接已经失效，再把动作转成 merge 或 split。 
  - patch `wiki/concepts/the.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - patch `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals`

## Page-Level Patch Plans
### `overloaded-concept-and` · 拆分过载概念 And
- Summary: 拆分过载概念，明确子概念边界和来源分流。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `high` | Protocol: `research`
- `wiki/concepts/and.md` | role `概念页` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts` | exists `True`
  - 缩窄概念边界、保留拆分说明，并给出后续子概念方向。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority` | exists `True`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/rewrite-proposals.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority` | exists `True`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`
### `overloaded-concept-the` · 拆分过载概念 The
- Summary: 拆分过载概念，明确子概念边界和来源分流。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `high` | Protocol: `research`
- `wiki/concepts/the.md` | role `概念页` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts` | exists `True`
  - 缩窄概念边界、保留拆分说明，并给出后续子概念方向。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-the --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority` | exists `True`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-the --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/rewrite-proposals.md` | role `索引页` | mode `review` | sections `Merge Candidates, Rewrite Priority` | exists `True`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-the --status accepted --note "Accepted for manual repair."`
### `bridge-concept-abstract` · 观察桥接概念 Abstract
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/abstract.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-abstract --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-abstract --status accepted --note "Accepted for manual repair."`
### `bridge-concept-agents` · 观察桥接概念 Agents
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/agents.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-agents --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-agents --status accepted --note "Accepted for manual repair."`
### `bridge-concept-and` · 观察桥接概念 And
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/and.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-and --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-and --status accepted --note "Accepted for manual repair."`
### `bridge-concept-judgment` · 观察桥接概念 Judgment
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/judgment.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-judgment --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-judgment --status accepted --note "Accepted for manual repair."`
### `bridge-concept-protocol` · 观察桥接概念 Protocol
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/protocol.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-protocol --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-protocol --status accepted --note "Accepted for manual repair."`
### `bridge-concept-the` · 观察桥接概念 The
- Summary: 记录桥接概念仍然必要的原因，避免误删跨簇连接。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Risk: `low` | Protocol: `research`
- `wiki/concepts/the.md` | role `概念页` | mode `review` | sections `Summary, Related Concepts, Related Sources` | exists `True`
  - 补 bridge maintenance note，明确为什么这个桥接概念还成立。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-the --status accepted --note "Accepted for manual repair."`
- `wiki/indexes/graph-health.md` | role `索引页` | mode `review` | sections `Bridge Concepts, Repair Signals` | exists `True`
  - 在图谱健康层确认桥接信号是否稳定，避免误删关键连接。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
  - command: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-the --status accepted --note "Accepted for manual repair."`

## Recently Cleared
- [已解决] 刷新引用快照 Protocol Boundary Judgment | inactive_since `2026-04-15T09:49:48+00:00` | next 信号已消失；确认是否要作为已解决归档。
- [待处理] 观察桥接概念 Concepts | inactive_since `2026-04-15T09:19:10+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-concepts --status resolved --note "Signal disappeared after compile."`
- [待处理] 观察桥接概念 Url | inactive_since `2026-04-15T03:14:25+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-url --status resolved --note "Signal disappeared after compile."`
- [待处理] 扩展单节点概念 Base | inactive_since `2026-04-15T03:14:25+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action singleton-concept-base --status resolved --note "Signal disappeared after compile."`
- [待处理] 拆分过载概念 Url | inactive_since `2026-04-15T03:10:19+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-url --status resolved --note "Signal disappeared after compile."`
- [待处理] 观察桥接概念 Agent | inactive_since `2026-04-15T01:54:06+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-agent --status resolved --note "Signal disappeared after compile."`
- [待处理] 观察桥接概念 Paper | inactive_since `2026-04-15T01:49:42+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-paper --status resolved --note "Signal disappeared after compile."`
- [待处理] 观察桥接概念 Overview | inactive_since `2026-04-15T01:49:42+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action bridge-concept-overview --status resolved --note "Signal disappeared after compile."`
- [待处理] 连接孤立来源 统一的炼丹炉 | inactive_since `2026-04-15T01:45:54+00:00` | next 信号已消失；确认是否要作为已解决归档。 | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action isolated-source-discovered-20260408053946-item --status resolved --note "Signal disappeared after compile."`

## 相关链接
- [动作队列](./machine-memory-actions.md)
- [机器记忆](./machine-memory.md)
- [图谱健康](./graph-health.md)
- [修复待办](./repair-backlog.md)
