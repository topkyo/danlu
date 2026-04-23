---
title: "炼丹炉大规模原料处理设计"
kind: "design"
status: "active"
---

# 炼丹炉大规模原料处理设计

这份文档回答的是：

**当 `raw/` 里的原料越来越多时，炼丹炉应该如何继续稳定工作，而不是退化成一个越来越重的资料仓库。**

它不是当前 runtime 已完整实现的承诺，而是后续规模化演进的设计基线。

对应关系：

- 基线架构：[[docs/Alchemy Furnace|炼丹炉架构]]
- 终局形态：[[docs/Furnace Ultimate Architecture|炼丹炉最终极形态]]
- 状态模型：[[docs/Furnace Material State Model|原料状态模型]]

## 核心原则

原料越来越多时，不能继续按“所有资料都保持热态、所有 query 都扫全库”的方式运转。

正确方向是：

- 把原料分层，而不是平铺
- 把知识编译，而不是临时堆上下文
- 把 query 限定在活动工作集，而不是反复扫全库
- 把旧材料降温归档，而不是让所有旧材料长期处于热区
- 让 protocol 参与原料路由，而不是只影响输出模板

一句话：

**全库是底座，活动工作集才是运行面。**

## 设计目标

这份设计希望解决 5 个问题：

1. `raw/` 持续增长后，如何不把 `compile` 和 `ask` 压垮。
2. 不同协议下，如何让投资/研发/产品/运维材料各自形成稳定工作集。
3. 老材料如何保留可追溯性，但不反复进入热路径。
4. machine memory 如何承担“窄化入口”而不是只做被动索引。
5. nightly / review / repair 如何优先处理真正活跃的知识面。

## 分层模型

### 1. 热度分层

未来不应只把材料按目录摆放，还应在 manifest / state 中显式记录温度：

- `hot`
  - 新投喂材料
  - 当前 protocol 高频使用材料
  - 与 pending `decision / judgment` 直接相关的来源
- `warm`
  - 曾经高频使用、但当前没有直接进入工作集的材料
  - 仍有稳定引用，但不应每轮都参与 compile / ask
- `cold`
  - 历史证据、旧主题材料、低频引用材料
  - 保留事实与 provenance，但默认不进入热路径
- `archived`
  - 明确完成生命周期、只保留追溯价值的材料

这层温度不是只看时间，而应综合：

- 最近一次被引用时间
- 最近一次被 query 命中时间
- 当前协议相关性
- 是否支撑 active `judgment / decision`
- 是否被 nightly 标成 drift / revisit / escalation 相关证据

### 2. 活动工作集

真正进入运行时的，不该是整个知识库，而应是 **active corpus**。

这里的 active corpus 更接近：

- 可持久化的 runtime working set
- 当前问题 / 当前协议 / 当前复审面的运行态聚焦结果

而不是：

- 新的事实源
- 只靠 `raw/ + wiki/ + machine memory` 就能无损重建的静态快照

每个 active corpus 由 4 类信号组成：

- 当前 `protocol`
- 当前主题 / question
- 当前待审 `decision / judgment`
- 当前 graph neighborhood

它的最小成员应该包括：

- 相关 `wiki/sources`
- 相关 `wiki/concepts`
- 支撑这些 concept 的 hot / warm evidence
- 与当前 judgment/review 直接关联的历史输出

它的作用是：

- 为 `ask / run-ask` 提供有限、稳定、可解释的上下文边界
- 为 `nightly` 定义当前优先巡检面
- 为 `review / repair / execution` 定义真正需要优先处理的工作域

### 3. 归档与降温

“越来越多的原料”问题，不靠删除解决，而靠：

- 降温
- 归档
- 可召回

设计上应支持：

- `archive candidates`
- `cold evidence`
- `cold attachments`
- `reactivation candidates`

规则：

- 归档不能破坏 provenance
- 归档后仍应保留被引用路径
- 归档只改变默认优先级，不改变历史可追溯性

### 4. 证据温度层 vs 知识资产生命周期

这里必须明确分开两件事：

- **证据温度层**
  - 面向 `raw`、附件、capture notes、source-level evidence
  - 解决“哪些材料应该继续处于热路径”这个问题
- **知识资产生命周期**
  - 面向 `concept / judgment / decision`
  - 解决“哪些知识资产处于 active / review / retired / revisit”这个问题

两者相关，但不应共用同一套状态机。

原因：

- `raw/` 仍然是唯一事实输入层
- `concept / judgment / decision` 属于编译后的知识层和判断层
- 证据降温不等于知识资产退役
- 某个旧 evidence 可以进入 cold/archive，但由它支撑的 judgment 仍然可能处于 active revisit

因此，规模化设计里应该始终保持：

- 证据层讨论 `hot / warm / cold / archived`
- 知识层讨论 `active / review / deferred / retired / revisit`

## Protocol-aware Material Routing

当前 protocol 已经会影响 query、review、nightly 和 output。规模化后，它还应该影响：

- 什么材料先进入 `hot`
- 什么 judgment 先进入复审
- 什么 concept 应继续硬化
- 什么 evidence 可以降温
- 什么 archive 需要重新升温
- 哪些跨协议证据应作为 bridge evidence 被召回

举例：

- `investing`
  - 优先保留 earnings、thesis、catalyst、risk、invalidation 相关材料在热区
- `research`
  - 优先保留 paper、repo、benchmark、experiment、architecture decision 相关材料在热区
- `product`
  - 优先保留 problem、metric、bet、launch readiness 相关材料在热区
- `ops`
  - 优先保留 incident、runbook、mitigation、escalation 相关材料在热区

这意味着：

**同一个炉子可以有多个协议，但每个协议在同一时刻只“优先点亮”自己最相关的材料面。**

这里的关键不是协议隔离，而是协议偏置：

- 当前 active protocol 应主导排序和优先级
- 但跨协议证据不能被硬隔离
- 当 graph、judgment、review 或 drift 信号显示跨域关联存在时，相关证据应被稳定召回

也就是说，正确形态不是“按协议切成几个互不相见的桶”，而是：

**一个统一炉子，当前协议优先，跨协议证据可召回。**

## Machine Memory 的职责升级

规模化后，machine memory 不能只当被动索引层，而应承担“上下文窄化入口”。

至少要支持：

- topic shard
- protocol shard
- graph neighborhood retrieval
- time-aware retrieval
- judgment-aware retrieval
- archive recall hints

也就是：

- LLM 不直接面对大库
- `aiwiki` 先通过 machine memory 选出当前最值得看的那一小块
- LLM 在这块“被编译过、被筛过、被约束过”的上下文上工作

## Compile / Nightly / Query 的规模化策略

### Compile

未来 compile 应更明确地分成：

- metadata refresh
- incremental source compile
- concept refresh
- index refresh
- cold/archive maintenance

不是每次都做全库热编译。

### Nightly

nightly 的重点应转向：

- 当前 active corpus 的 drift
- pending judgment 的 evidence drift
- hot materials 的缺口和冲突
- cold/archive candidates 的降温建议
- 需要重新升温的旧材料

### Query

query 未来应遵循：

1. 先选 protocol
2. 再定 active corpus
3. 再用 machine memory 做图谱邻域窄化
4. 最后才让 LLM 在这批上下文上生成输出

这保证：

- query 复杂度不随全库线性恶化
- 输出仍然保持 provenance 和可解释性

## 运行约束

当前 runtime 已明确采用：

**`single writer, many readers`**

规模化后仍不建议直接开放多写者并发。

更合理的演进是：

- 先保持单写者
- 再引入 job queue / serialized executor
- 最后再考虑更细粒度任务拆分

原因很简单：

- 这套炉子是 file-based runtime，不是事务型数据库
- `wiki/indexes`、`.aiwiki/state`、`output/control`、`output/packs` 会被同一轮 compile / nightly 一起改写
- 没有串行化，状态一致性会先坏掉

## 建议的下一步实现顺序

如果未来真的要把这份设计落到 runtime，建议顺序是：

1. 在 manifest / state 中引入 `temperature` 和 `last_touched_at`
2. 定义 `active corpus` 的最小状态模型
3. 让 protocol 参与 material routing
4. 引入 `archive candidates / cold evidence` 状态
5. 让 machine memory 支持 protocol/topic/time shard
6. 让 nightly 开始处理升温 / 降温 / 归档建议

实现时还有两个收口原则应一开始写死：

- 第一步如果先落 `material-state`，其中 `active_corpus_ids` 应保持空/缺省；等 `active-corpora` 接上后再统一回填
- `active corpus` 所依赖的近期 `query / review / nightly` 历史，应该统一落在 machine-readable 的 runtime history 文件里，而不是让各模块各记一份

## 结论

原料越来越多时，炼丹炉不该变成“更大的仓库”，而应该变成：

**一个有温度层、有活动工作集、有 protocol 路由、有 machine-memory 窄化入口的长期知识炉。**

这份设计的意义不在“现在已经实现了多少”，而在于给后续 runtime 演进一个清晰边界：

- 什么应该保持热
- 什么应该被降温
- 什么应该进入当前工作集
- 什么应该只作为可召回证据存在

如果后续要继续往实现层推进，下一步直接读：

- [[docs/Furnace Material State Model|炼丹炉原料状态模型]]
