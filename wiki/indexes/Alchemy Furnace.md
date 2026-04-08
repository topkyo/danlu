---
title: "炼丹炉架构"
kind: "architecture"
status: "active"
---

# 炼丹炉架构

`Alchemy Furnace` 是把 `aiwiki` 推进成复利型知识系统的产品架构。

它不是一个“记笔记”的比喻，而是一个运行时模型：

- 原料进入系统
- 编译器把原料整理成结构化知识
- agent 基于知识层查询并生成产物
- 高价值输出持续回流
- lint、drift、review 和 nightly loop 让系统长期保持一致性

## 目标

构建一个本地优先的系统，使得：

- 人负责投喂原料并保留判断权
- `aiwiki` 维护编译后的知识层
- Obsidian 作为给人用的前端
- 机读索引和图谱记忆持续提升后续 agent 的工作效率

最终目标不是“更多笔记”，而是一个会持续增厚的知识操作系统。

## 统一内核 + 多协议

炼丹炉应该统一成一个系统，而不是拆成“投资版炉子”和“研发版炉子”两个 runtime。

正确的长期形态是：

- 一个统一的 `aiwiki` 炼丹炉内核
- 多套按场景切换的 protocol / schema

也就是：

- 炉子只有一个
- 丹方可以有很多套

统一内核负责：

- `raw -> wiki -> machine memory -> outputs` 主链
- provenance、review、aging、escalation、repair、nightly
- graph / machine-memory
- decision / judgment 的基本生命周期

协议层负责：

- 概念分类和 taxonomy
- decision / judgment 模板
- review 窗口与升级规则
- nightly 应重点跟踪的信号
- query / writeback / lint 的领域偏置

这意味着：

- 投资、研发、产品、运营可以共用一套炉子
- 不同领域通过 protocol 形成不同“炼丹方式”
- 跨域判断仍然可以互相引用和迁移

不要把“一个炉子，多种 protocol”误写成“多个炉子，多套系统”。

### 协议层示例

- `investing`
  - `company / thesis / catalyst / risk / invalidation / position decision`
- `research`
  - `paper / repo / benchmark / experiment / architecture decision`
- `product`
  - `user problem / insight / bet / metric / launch judgment`
- `ops`
  - `incident / runbook / mitigation / escalation / follow-up`

### 规划中的协议路径

- `schema/protocols/`

建议每个协议至少定义：

- taxonomy
- decision template
- judgment template
- review policy
- nightly policy
- query / output hints

当前它仍属于架构方向，而不是完整 runtime 功能；但后续增强应围绕这一层展开，而不是再复制一套新的炉子。

## 分层模型

### 1. Raw Sources

目的：最早、最可控的证据层，以及 ingest 生成的 capture artifact。

当前路径：

- `raw/inbox/`
- `raw/assets/`
- `raw/normalized/`

典型内容：

- 网页剪藏、文档、文章
- 论文和 PDF
- 截图、图示、白板照片
- repo snapshot
- 日志、会议纪要、转录稿、现场笔记
- PDF 抽取文本、OCR note、repo capture note 这类 ingest 产物

规则：

- 能保留原始附件时优先保留
- capture note 必须回指原文件或原 URL
- `raw/` 先于 `wiki/`，但不是所有文件都是 pristine original
- 派生结论不能覆盖 raw evidence 或 capture note

### 2. Compiled Wiki

目的：由 `aiwiki` 维护的人可读共识层。

当前路径：

- `wiki/sources/`
- `wiki/concepts/`
- `wiki/indexes/`
- `wiki/derived/`
- `wiki/decisions/`
- `wiki/judgments/`

典型内容：

- 带摘要和引用的 source page
- 横跨多个来源的 concept page
- decision/judgment 页面
- 索引、日志、开放问题、运行看板
- 值得回流保留的报告和派生产物

规则：

- 这是人首先阅读的层
- 重要结论都必须保留 provenance
- concept 和 decision 页面应做综合，而不是简单复述

### 3. Machine Memory

目的：给 agent 用的机读加速层。

当前路径：

- `.aiwiki/cache/`
- `.aiwiki/state/`

典型内容：

- term / citation 索引
- source / concept graph
- retrieval cache
- 时间快照
- drift 记录
- graph export 和 query planner 产物

规则：

- 优化 agent 查询，而不是人类浏览
- 必须能从 raw / wiki 层重建
- wiki 与 machine memory 的漂移必须可观测

这一层最接近 `graphify` 这类图谱型 machine memory。

### 4. Schema

目的：定义系统如何 ingest、compile、cite、review、lint、write back。

当前路径：

- `prompts/compile.md`
- `prompts/ask.md`
- `prompts/lint.md`
- `schema/`

规划中的路径：

- `policy/`
- `schema/protocols/`

典型内容：

- ingest 规则
- 引用与 provenance 规则
- 冲突处理规则
- review state 规则
- 输出模板
- taxonomy / naming convention

规则：

- schema 是运行时策略，不只是文档
- 系统在运行中学到的新约束，应该回写到这里

边界：

- `AGENTS.md` 和 `CLAUDE.md` 是开发治理文件
- 它们不属于 `aiwiki` runtime 架构

### 5. Outputs

目的：从编译知识层中生产出的可消费产物。

当前路径：

- `output/reports/`
- `output/slides/`
- `output/figures/`
- `output/lint/`

典型内容：

- 报告
- 幻灯片提纲
- 图表 brief
- lint 报告
- 后续可能的 SOP、决策 memo、review pack

规则：

- 输出不是终点
- 高价值输出应继续回流到 `wiki/derived/`、`wiki/decisions/`、`wiki/judgments/`

## 运行闭环

### Ingest Loop

1. 原料通过 `drop-url`、`drop-pdf`、`drop-image`、`drop-repo` 或直接丢文件进入系统。
2. `aiwiki` 记录 provenance，并保存本地附件。
3. deterministic compile 生成 source/index 层。

### Compile Loop

1. `compile` 维护 source、concept、index、review queue 等层。
2. `run-compile` 用 LLM 替换 placeholder source summary、fallback concept summary，并继续重写高优先级弱概念页。
3. raw 变化后，旧的 summary 和 concept synthesis 会被失效。

### Query Loop

1. `ask` / `run-ask` 优先读取编译层，并用 machine-memory query planning 扩展相关来源与概念。
2. 系统产出 report、slides、figure brief。
3. 高价值结果可以通过 `file-back` 回流。
4. `nightly` / `run-nightly` 可以把重复出现且问题类型明确的 output 自动晋升到 decision / judgment。

### Lint Loop

1. `lint` 检查缺页、坏引用、明显 provenance 缺口。
2. `run-lint` 补 semantic review。
3. `nightly` / `run-nightly` 会把 drift、review queue、repair backlog 聚合起来。
4. pending 的 decision / judgment 会持续进入 aging / revisit / escalation 跟踪。
5. machine-memory action queue 会保留 `proposed / accepted / deferred / resolved / rejected` 生命周期，并把 overdue / escalation / inactive 历史暴露给 nightly。
6. repair plan 会把 accepted / proposed / deferred 动作整理成 execution batches，给 nightly 和人工修复提供下一步提示。
7. repair plan 还会继续生成页级 execution proposals，把图谱修复推进到可审执行方案。
8. concept quality loop 会把弱概念页、占位概念、概念合并候选、冲突信号、证据缺口和重写优先级整理成稳定看板。

## 角色分工

### 人

- 决定投什么原料
- 提好问题
- 审核重要判断
- 决定哪些产物值得回流

### aiwiki Runtime

- 负责 ingest、compile、ask、lint、watch、nightly、provenance
- 维护本地 artifact tree
- 维持 source / derived / decision / judgment 的边界

### LLM Backend

- 补来源摘要
- 补概念综合
- 回答 grounded 问题
- 做 semantic lint

### Obsidian

- 作为前端和 IDE
- 负责浏览 raw、wiki、output
- 不是编译器本体

## 当前状态

现在已经实现当前架构文档定义的主线阶段：

- 四类 `drop-*` 原料入口
- source / concept / index 编译层
- machine-memory graph export、drift tracking、query planning
- graph-aware retrieval、query routes、component-aware traversal
- graph-health 看板和 repair backlog
- machine-memory topology、hub 指标、动作队列和 Mermaid 拓扑切片
- machine-memory action lifecycle、review-action 入口、inactive / overdue / escalation 视图
- machine-memory repair plan、execution batch、页级 execution proposals、next-step / command-hint
- concept-quality 看板、弱概念页、概念合并候选、冲突信号、证据缺口和重写优先级
- concept rewrite proposal / review / apply gate
- 低风险 repair 的 safe execution layer（`apply-action`）
- 交互式 machine-memory graph HTML（搜索、分量过滤、节点详情、safe-apply 摘要）
- decision / judgment writeback layers
- decision / judgment review workflow 与 review queue
- recurring outputs 自动晋升到 decision / judgment 页面
- aging-report、overdue review、escalation 候选信号
- `run-compile` 的 source/concept 双层维护与高优先级弱概念重写
- nightly health checks 和 timer 化调度
- output 生成和高价值回流
- `watch` 自动化与 user service
- Obsidian 前端层

后续增强方向：

- 更强的 review-center / graph-view 产品壳
- 更丰富的 graph execution 和 page-level patch/apply 策略
- 更深的 protocol starter library（`product / ops / more domain packs`）

## 架构不变量

- 原始证据和 capture note 必须留在 `raw/`
- `wiki/derived/` 不能静默改写 `raw/`
- provenance 必须穿过 compile / query / writeback 全链路
- 人读层和机读层要分开
- 新学到的规则要沉到 schema
- 重要输出应继续回流，形成复利

## 实际阅读顺序

1. 需要证据时先看 `raw/`
2. 需要综合时看 `wiki/sources/` 和 `wiki/concepts/`
3. 需要系统状态时看 `wiki/indexes/`
4. 需要任务产物时看 `output/`
5. 把 machine memory 当作支撑层，而不是主界面

## 总结

炼丹炉架构下：

- `raw/` 存矿石
- `wiki/` 存提炼后的知识
- `machine memory` 存机读加速层
- `schema` 存炼制规则
- `output/` 存可直接消费的产物

这就是 `aiwiki` 的产品方向：
不是更聪明的笔记软件，而是一个会持续增厚的知识操作系统。
