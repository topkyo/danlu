# 协议总览

- 最近编译时间：`2026-05-20T02:11:33+00:00`
- 当前 active protocol：`general` (通用协议)
- 协议总数：`5`
- 状态文件：`.aiwiki/state/protocol.json`
- lifecycle concept backlog / retired：`0` / `0`
- 切换命令：`PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set <slug>`

## 当前协议入口
- [schema/protocols/general/index.md](../../schema/protocols/general/index.md)
- [schema/protocols/general/taxonomy.md](../../schema/protocols/general/taxonomy.md)
- [schema/protocols/general/decision.md](../../schema/protocols/general/decision.md)
- [schema/protocols/general/judgment.md](../../schema/protocols/general/judgment.md)
- [schema/protocols/general/review.md](../../schema/protocols/general/review.md)
- [schema/protocols/general/nightly.md](../../schema/protocols/general/nightly.md)
- [schema/protocols/general/query.md](../../schema/protocols/general/query.md)

## 可用协议
- [通用协议](../../schema/protocols/general/index.md) | slug `general` | 默认的跨域协议，适合把事实、综合、判断和复审保持分层。
- [投资协议](../../schema/protocols/investing/index.md) | slug `investing` | 面向 thesis、risk、catalyst、invalidation 和 position decision 的协议。
- [运维协议](../../schema/protocols/ops/index.md) | slug `ops` | 面向 incident、runbook、mitigation、escalation 和 follow-up 的协议。
- [产品协议](../../schema/protocols/product/index.md) | slug `product` | 面向 user problem、insight、bet、metric 和 launch judgment 的协议。
- [研发协议](../../schema/protocols/research/index.md) | slug `research` | 面向 paper、repo、benchmark、experiment 和 architecture decision 的协议。

## Lifecycle Governance Summary
- 以下 lifecycle backlog 是全局 knowledge plane 工作面，按当前 active protocol 排序，不伪装成 protocol-specific 指标。
- review concepts：`0`
- revisit concepts：`0`
- retired concepts：`0`
- active concepts：`0`

## Lifecycle Concept Backlog
- 当前没有 lifecycle-driven concept backlog。

## Retired Concepts
- 当前没有 retired concept。

## 运行原则
- 统一 runtime，不复制多个炉子。
- 领域差异优先落在 `schema/protocols/`。
- 查询、回流和审阅默认沿当前 active protocol 执行，但 page frontmatter 会保留显式 protocol 字段。

## 当前协议语义
- 默认协议：`general` (通用协议)
- Review window：沿通用默认窗口。
- Auto-promotion 标题前缀：decision `决策沉淀` / judgment `判断沉淀`
- Review focus：`优先清理 overdue / escalation 项，再审新产生的 decision/judgment。 / 高风险结论默认保持 tentative / proposed，直到证据稳定。`
- Nightly focus：`关注 pending review、aging、repair backlog、concept rewrite。 / 把 recurring outputs 保守晋升到 decision/judgment。`
