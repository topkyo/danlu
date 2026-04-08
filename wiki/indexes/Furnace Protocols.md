---
title: "统一炼丹协议"
kind: "guide"
status: "active"
---

# 统一炼丹协议

这页回答一个核心问题：

炼丹炉应该统一成一个系统，还是拆成投资版、研发版等多个系统？

答案是：

**统一成一个炉子，但支持多个协议。**

不是：

- 一个投资炉子
- 一个研发炉子
- 一个产品炉子

而是：

- 一个统一 runtime
- 多个按场景切换的 protocol

## 为什么不能拆成多个炉子

如果拆成多个系统，会直接带来 4 个问题：

1. 底层能力重复
   - `review / repair / nightly / machine-memory / outputs` 都要重复维护
2. 跨域知识断裂
   - 研发 insight 很可能影响投资判断
   - 产品判断也可能反过来影响研发优先级
3. 维护成本翻倍
   - schema、prompt、tooling、watch、nightly 都会分叉
4. 复利被削弱
   - 真正的知识复利来自跨域连接，而不是孤岛系统

## 统一炉子里，什么该统一

这些能力应该始终共用：

- `raw -> wiki -> machine memory -> outputs`
- provenance 和事实分层
- `review / aging / escalation`
- `repair / lint / nightly`
- `decision / judgment`
- graph / machine-memory
- product shell

也就是说：

**炉子的物理结构统一。**

## 什么不该统一到一套死规则

这些应该按协议变化：

- taxonomy
- concept page 结构
- decision 模板
- judgment 模板
- review policy
- nightly 重点信号
- query / output 偏置

也就是说：

**炼丹方法可以变化。**

## 协议层应该长什么样

建议最终放在：

- `schema/protocols/`

每个协议至少包含：

- `taxonomy.md`
- `decision.md`
- `judgment.md`
- `review.md`
- `nightly.md`
- `query.md`

## 示例

### Investing Protocol

典型对象：

- company
- thesis
- catalyst
- risk
- invalidation
- position decision

最重要的不是“推荐买什么”，而是：

- thesis 如何形成
- thesis 何时失效
- 哪些证据支持 / 反对
- 什么时候复审

### Research Protocol

典型对象：

- paper
- repo
- benchmark
- experiment
- architecture decision
- regression

最重要的不是“收了多少资料”，而是：

- 哪些结论已经稳定
- 哪些实验失败过
- 哪些设计判断需要回看

### Product Protocol

典型对象：

- user problem
- insight
- bet
- metric
- launch judgment

### Ops Protocol

典型对象：

- incident
- runbook
- mitigation
- escalation
- follow-up

## 运行原则

统一炼丹炉不等于把所有知识混在一起。

正确方式是：

- 统一 runtime
- 每个知识域带自己的 protocol
- 决策和判断页明确标注 protocol
- review / nightly 按 protocol 采用不同规则

## 当前已落地到 runtime 的协议差异

现在这不是纯文档原则，runtime 已经有最小行为差异：

- `decision / judgment` 的默认 review window 会按 protocol 变化
- `file-back` 生成的 `decision / judgment` 模板会按 protocol 变化
- recurring promotion 的标题前缀和分类提示会按 protocol 变化
- `review-queue`、`review-center`、`repair-backlog` 和 machine-memory action queue 会按 active protocol 调整优先级

这意味着 protocol 已经不是“只贴一个标签”，而是会改变一部分 deterministic 行为。

## 当前结论

现在的炼丹炉应该继续沿这条路走：

- 不复制多个产品
- 不拆多个 runtime
- 只补一个统一内核
- 在这个内核上发展多个协议

一句话：

**一个总炉，多个丹方。**
