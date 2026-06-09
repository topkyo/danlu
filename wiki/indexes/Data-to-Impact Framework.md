# Data-to-Impact Framework / 从原料到影响的智能体闭环

> 状态：战略方法论文档  
> 适用范围：炼丹炉、aiwiki runtime、machine memory、decision / judgment、research / investing / product / ops protocols  
> 核心判断：**资料不是资产，能把资料持续炼成可复审判断并影响真实决策的系统才是资产。**

## 1. 背景

炼丹炉不是静态笔记库，也不是一次性 RAG 问答器。

它的核心价值不是「存了多少网页、PDF、图片、repo、会议纪要和本地笔记」，而是能不能把这些原料持续编译成：

- 可追溯的 wiki；
- 可查询的 machine memory；
- 可复审的 decision / judgment；
- 可回流的 output；
- 可被 nightly / review / aging / repair 持续治理的长期判断资产。

这套系统可以用一条更通用的链路概括：

```text
Data → Information → Knowledge → Insight → Wisdom → Impact
```

在炼丹炉里，对应为：

```text
Raw Material
→ Structured Notes / Metadata
→ Wiki / Machine Memory / Relationship Graph
→ Key Signal / Contradiction / Risk / Opportunity
→ Judgment / Decision / Thesis / Architecture Choice
→ Better Research, Better Decisions, Reviewable Compounding
```

## 2. 六层价值链

### 2.1 Data：原始材料

这一层包括所有未被充分组织的输入：

- 网页；
- PDF；
- 图片；
- repo；
- 会议纪要；
- 本地笔记；
- 财报、电话会、访谈；
- paper、benchmark、experiment；
- 临时想法、聊天记录、手动摘录。

关键判断：

> Raw material 本身不是资产，只是投进炉子的矿石。

资料越多，不代表判断越好。如果没有结构化、引用、关系、复审和回流，资料只会变成信息负债。

### 2.2 Information：结构化信息

这一层把原料变成可被系统处理的结构化信息。

典型产物：

- source manifest；
- frontmatter；
- title / author / date / source / domain；
- 摘要；
- 标签；
- 关键实体；
- 引用位置；
- 时间线；
- protocol 归属。

这一层回答：

```text
这个材料是什么？
来自哪里？
什么时候产生？
属于哪个协议？
和哪个主题有关？
可信度和时效性如何？
```

### 2.3 Knowledge：知识网络

这一层把结构化信息连接起来，形成可持续演化的知识网络。

典型产物：

- wiki 页面；
- concept graph；
- machine memory；
- source ↔ concept ↔ judgment 关系；
- thesis / catalyst / risk / invalidation 结构；
- paper / repo / benchmark / experiment / architecture decision 结构；
- protocol-specific memory surfaces。

这一层回答：

```text
哪些材料支持同一个概念？
哪些判断依赖哪些证据？
哪些结论互相矛盾？
哪些主题正在形成长期复利？
```

Knowledge 不是简单摘要集合，而是带来源、关系、状态和治理机制的长期认知网络。

### 2.4 Insight：关键洞察

这一层从知识网络里抽取当前真正重要的信号。

典型 Insight 包括：

- 一个投资 thesis 的关键变化；
- 一个技术路线的核心瓶颈；
- 一篇 paper 和一个 repo 之间的架构差异；
- 一个 benchmark 的可信度问题；
- 一个产品方向的真实用户价值；
- 一个判断中的缺失证据；
- 一个需要 revisiting 的旧结论。

这一层回答：

```text
当前最重要的变化是什么？
哪些证据改变了原判断？
哪里存在矛盾、风险或机会？
哪个结论需要升级、降级、重写或废弃？
```

Insight 的价值在于从大量材料中识别少数真正会改变判断的信号。

### 2.5 Wisdom：判断与路径

Wisdom 不是摘要，也不是知识点，而是面向行动和决策的判断资产。

典型产物：

- investment thesis；
- decision memo；
- architecture decision record；
- research conclusion；
- product judgment；
- risk / invalidation checklist；
- execution proposal；
- revisit plan。

这一层回答：

```text
我现在应该相信什么？
为什么？
证据是什么？
反证是什么？
什么情况会推翻这个判断？
下一步应该做什么实验、调研、验证或执行？
```

炼丹炉真正要沉淀的是这一层：

> 可追溯、可复审、可回滚、可老化、可重新审判的判断资产。

### 2.6 Impact：真实影响

最终目标不是知识库本身，而是对真实研究、投资、研发和产品决策产生影响。

Impact 可以表现为：

- 更快形成高质量研究报告；
- 更少重复阅读和重复推理；
- 更好地记住历史判断和判断变化；
- 更早发现 thesis 失效；
- 更清晰地比较技术路线；
- 更稳定地产出 architecture decision；
- 更可复盘地解释为什么当时做了某个决定；
- 把个人认知积累变成长期复利资产。

这一层回答：

```text
这个系统是否让判断质量提高？
是否减少了重复劳动？
是否让历史判断可复审？
是否让错误能回流成规则和改进？
```

## 3. 炼丹炉中的具体映射

| 层级 | 炼丹炉产物 | 关键问题 |
| --- | --- | --- |
| Data | raw materials：网页、PDF、图片、repo、笔记、会议纪要 | 有哪些原始材料？ |
| Information | source manifest、frontmatter、摘要、标签、metadata | 这些材料是什么？来自哪里？如何归类？ |
| Knowledge | wiki、machine memory、concept graph、引用关系 | 这些材料之间有什么关系？ |
| Insight | 关键信号、矛盾、风险、机会、缺失证据 | 什么会改变当前判断？ |
| Wisdom | decision、judgment、thesis、ADR、research conclusion | 现在应该形成什么判断？ |
| Impact | 更好的研究、投资、研发、产品决策 | 判断有没有产生真实价值？ |

## 4. 与现有 runtime 的关系

当前炼丹炉已有主线：

```text
raw → compile → wiki → ask → output → file-back → review / nightly
```

这条链路可以映射为：

```text
raw              = Data
compile          = Data → Information → Knowledge
wiki             = Knowledge
machine memory   = Knowledge graph / retrieval surface
ask              = Insight extraction
output           = Insight / Wisdom expression
file-back        = Wisdom 回流为 Knowledge
review / nightly = Impact 复盘与治理
```

因此，Data-to-Impact Framework 不是替代当前 runtime，而是给当前 runtime 提供更清晰的价值解释和产品北极星。

## 5. 必须沉淀的关键资产

### 5.1 Judgment Asset Schema

每个高价值判断都应该结构化。

建议字段：

```yaml
judgment_id: judgment-20260609-001
title: 某技术路线是否值得采用
domain: research
protocol: research
status: active
confidence: medium
claim: 当前判断是什么
why_now: 为什么现在需要判断
supporting_evidence:
  - source_id: source-001
    note: 支持点
contradicting_evidence:
  - source_id: source-002
    note: 反证点
assumptions:
  - 关键假设
invalidation:
  - 什么情况会推翻该判断
next_actions:
  - 需要继续验证的实验/调研/对比
review_window: 30d
last_reviewed_at: null
outcome: pending
```

### 5.2 Source-to-Judgment Trace

所有判断都应该能追溯到来源。

```text
source → note → concept → insight → judgment → output → review
```

如果一个判断不能追溯来源，它就不能成为高质量判断资产。

### 5.3 Review / Aging / Repair

判断资产必须有生命周期。

- `review`：人工或 Agent 复审；
- `aging`：根据时间、领域和证据变化降低新鲜度；
- `escalation`：重要判断到期后进入优先复审；
- `repair`：修复缺失引用、冲突关系、过期结论；
- `nightly`：周期性巡检和生成待处理队列。

### 5.4 Protocol-specific Wisdom

不同协议里的 Wisdom 不一样：

| Protocol | Wisdom 形态 |
| --- | --- |
| general | 通用结论、解释、知识整理 |
| investing | thesis、catalyst、risk、invalidation、position note |
| research | paper comparison、benchmark judgment、technical conclusion |
| product | user value、positioning、feature tradeoff、go-to-market judgment |
| ops | SOP、incident review、execution proposal、process improvement |

协议层的目标，是让同一套炉子在不同领域炼出不同形态的判断资产。

## 6. 护城河判断

炼丹炉的护城河不在：

```text
RAG
向量数据库
网页剪藏
PDF 摘要
Obsidian 插件
聊天问答
```

这些都是能力组件，但不是最终壁垒。

真正的护城河在：

```text
长期原料积累
× 结构化 schema
× machine memory
× 判断资产
× 复审历史
× 协议化输出
× nightly 治理
× 个人/团队认知习惯
```

当系统知道：

```text
我过去为什么相信 A，后来哪些证据让它变成 B，
哪些判断被验证，哪些判断失效，哪些规则应该更新。
```

它才开始形成真正的知识复利。

## 7. 产品原则

1. **不要做资料库，要做判断资产系统。**
2. **不要只做 RAG 问答，要做可追溯、可复审、可回流的认知闭环。**
3. **不要追求一次性总结，要追求长期复利。**
4. **不要只保存输出，要保存判断形成路径。**
5. **不要让旧判断自然腐烂，要让它进入 aging / review / repair。**
6. **不要只问「这是什么」，要问「它如何改变我的判断」。**

## 8. 下一步落地建议

### P0：判断资产标准化

- 为 `decision / judgment` 补齐统一 schema；
- 每个 judgment 必须包含 evidence、assumption、invalidation、review_window；
- 输出页展示 judgment 的来源链路。

### P1：从 ask 到 judgment

- `ask` 输出不只是 report，也可以选择生成 judgment draft；
- 高置信、可追溯输出可以进入 `file-back`；
- 低置信输出进入 review queue，而不是直接沉淀。

### P2：Impact 复盘

- 每周生成「本周新增判断 / 改变判断 / 失效判断 / 待复审判断」；
- 给每个 protocol 生成 Impact Summary；
- 对被验证或被推翻的判断生成 repair proposal。

## 9. 与 Digital Farm 的共通性

Digital Farm 处理物理世界：

```text
Physical Data → Operational Wisdom → Farm Impact
```

炼丹炉处理认知世界：

```text
Cognitive Raw Material → Judgment Wisdom → Decision Impact
```

两者底层飞轮一致：

```text
输入原料
→ 结构化
→ 建关系
→ 找关键点
→ 生成路径/判断
→ 产生结果
→ 复盘回流
→ 系统变聪明
```

## 10. 一句话总结

> 炼丹炉最值钱的不是保存资料，也不是回答问题，而是把认知原料持续炼成可追溯、可复审、可回流、能影响真实决策的判断资产。
