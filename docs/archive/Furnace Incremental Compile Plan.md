---
title: "炼丹炉增量编译计划"
kind: "roadmap"
status: "superseded"
superseded_at: 2026-04-24
superseded_by: docs/Furnace Evolution Mechanics.md
---

> **已归档**：增量 compile 的 phase 设计与 dirty set 语义已被 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]] §4 / §5 吸收。正文保留作史料。

# 炼丹炉增量编译计划

这份计划只回答一件事：

**在不打穿当前 runtime 分层的前提下，先把 `compile` 推进到可观察、可验证的最小分段 / 增量 baseline。**

它不是终局 compile 架构稿。

它是当前这条线的最近实施计划。

## 为什么现在做这件事

截至 2026-04-10，炼丹炉最强的部分已经不是 Product Shell，而是炉心本身：

- evidence state 已落地
- knowledge lifecycle 已落地
- governance / execution 已闭环
- Product Shell 也已经进入可用阶段

当前最弱、同时价值最大的缺口，反而回到了 `compile`：

- `compile_wiki()` 仍然是一轮大刷新
- 虽然已经有 deterministic baseline，但还没有把“哪些东西真的脏了”显式化
- `Furnace Material Scaling` 里要求的 `metadata refresh / incremental source compile / concept refresh / index refresh / cold maintenance` 还没有被压成实现级 contract

对应设计文档：

- [[docs/Furnace Material Scaling|大规模原料处理]]
- [[docs/Furnace Material State Model|原料状态模型]]

## 当前问题

今天的 `compile` 有三个实际问题：

1. **不可观察**
   - 目前只能知道“compile 跑完了”，但不知道这轮到底更新了哪些 source、哪些阶段在工作、哪些阶段只是保守重刷。

2. **source page 没有最小增量**
   - 即使 raw 没变，也会再次走完整 source page render path。

3. **设计文档与实现之间还差一层 contract**
   - 设计上已经讲清楚要分段
   - 但 runtime 还没有 phase summary / compile state / dirty set 这些机读面

## 这一轮的目标

这一轮不做“真正复杂的 compile scheduler”。

这一轮只做：

- 把 `compile` 分成显式 phase
- 让 source page 进入最小增量模式
- 让 compile 输出 machine-readable state
- 让 `compile-status.md` 和 CLI 返回值都能看见这些 phase

一句话：

**先把 compile 从“黑箱大刷新”推进成“可观察的最小分段 baseline”。**

## 非目标

这一轮明确不做：

- daemon / job queue
- 多写者并发
- full incremental concept synthesis
- full incremental index refresh
- heavy cache invalidation graph
- learned ranker
- auto archive executor

## Phase 设计

这轮采用 5 段模型，但只在第一段真正做最小增量。

### 1. metadata refresh

职责：

- `raw/` 与 manifest 对齐
- 统计 manifest 层变化
- 形成当前 compile 的输入快照

### 2. incremental source compile

职责：

- 识别 dirty source page
- 只重写脏的 source page
- 显式统计：
  - dirty source count
  - skipped clean source count
  - updated source count

这一段是本轮真正落地的最小增量。

### 3. concept refresh

职责：

- 继续保守重建 concept records / concept pages
- 先不做 concept 级细粒度增量

### 4. index refresh

职责：

- 继续保守刷新索引、dashboard、output pack、pilot、HTML control surfaces
- 先不把 index 层也拆成独立 invalidation graph

### 5. cold / archive maintenance

职责：

- stale generated page 清理
- archive / lifecycle / repair 相关派生面的继续刷新
- 把“收尾维护”从主编译叙事里显式拆出来

## 本轮交付物

### A. compile state

新增 machine-readable compile state，至少包含：

- `version`
- `compiled_at`
- `manifest_entry_count`
- `dirty_source_ids`
- `clean_source_ids`
- `phase_summary`

建议路径：

- `.aiwiki/state/compile-state.json`

### B. compile-status 可观察性

`wiki/indexes/compile-status.md` 需要显式展示：

- phase 列表
- dirty / clean / updated source 统计
- 当前 round 是否只对 source page 做了最小增量

### C. CLI / app 返回结构

`compile_wiki()` 的返回结构需要暴露：

- `compile_state_path`
- `dirty_sources`
- `clean_sources`
- `phase_summary`

## Success Criteria

- `compile` 产出 machine-readable `compile-state.json`
- `compile-status.md` 显式展示 compile phase summary
- 第二次 `compile` 在 raw 未变化时，不再重写未变 source page
- `compile_wiki()` 返回 dirty / clean source 统计
- 继续保持 concept / index / governance / output 层语义不回归
- `bash scripts/verify.sh` 通过
- `qa-review` / `qa-runtime` 通过
- `closed_loop` 与 `finalize_task.sh` 通过

## 推荐实现顺序

1. 先补计划文档与 active contract
2. 再补 compile state path / load-save helper
3. 再给 `compile_wiki()` 加 phase summary 与 dirty source 集合
4. 让 source page 进入最小增量
5. 更新 `compile-status.md`
6. 补回归测试
7. 跑 harness 默认闭环

## Stop Conditions

如果出现下面任一情况，这轮应立刻止损，不继续扩：

- 为了做最小增量，不得不把 compile 改成多写者或后台服务
- 为了省事，开始让 Product Shell 直接参与 compile state 真相维护
- 为了做 concept/index 增量，被迫引入复杂 cache graph 或不可解释 invalidation 规则

## 这一轮之后的升级路径

如果这轮 baseline 稳定，下一轮才值得继续推进：

1. concept refresh 的增量识别
2. index refresh 的更细粒度失效
3. cold maintenance 从 compile 中进一步抽离
4. compile / nightly 的职责重新压边界

## 总结

当前最值钱的不是再补一个控制台，而是先把 `compile` 这条主干从“全量刷新习惯”推进成“有 phase、有 dirty set、有状态页”的最小增量 baseline。
