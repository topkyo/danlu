# 编译状态

- 最近编译时间：`2026-05-20T02:11:33+00:00`
- 来源页：`0`
- 概念页：`0`
- 决策页：`0`
- 判断页：`0`
- 当前 active protocol：`general` (通用协议)
- 待审项目：`0`
- 已到期复审：`0`
- 需要升级：`0`
- 证据漂移：`0`
- Compile state：`.aiwiki/state/compile-state.json`
- Concept build state：`.aiwiki/state/concept-build-state.json`
- Machine memory build state：`.aiwiki/state/machine-memory-build-state.json`
- Ranking build state：`.aiwiki/state/ranking-build-state.json`
- Output pack build state：`.aiwiki/state/output-pack-build-state.json`
- Domain pilot build state：`.aiwiki/state/domain-pilot-build-state.json`
- Dirty source：`0`
- Clean source：`0`
- Dirty concept source：`0`
- Clean concept source：`0`
- Dirty concept：`0`
- Clean concept：`0`
- Dirty machine-memory source：`0`
- Clean machine-memory source：`0`
- Dirty machine-memory concept：`0`
- Clean machine-memory concept：`0`
- Machine-memory core reused：`False`
- Dirty ranking source：`0`
- Clean ranking source：`0`
- Dirty ranking concept：`0`
- Clean ranking concept：`0`
- Dirty output pack group：`4`
- Clean output pack group：`0`
- Dirty domain pilot protocol：`5`
- Clean domain pilot protocol：`0`
- Dirty index artifact：`38`
- Clean index artifact：`0`
- Dirty maintenance artifact：`1`
- Clean maintenance artifact：`5`
- 总索引位于 `index.md`。
- 运行时规则位于 `schema/`。
- 协议规则位于 `schema/protocols/`。
- 协议总览位于 `protocols.md`。
- 炉心面板位于 `furnace-center.md`。
- 执行中心位于 `execution-center.md`。
- 输出 Pack 总览位于 `output-packs.md`。
- 领域 Pilot 总览位于 `domain-pilots.md`。
- 操作日志位于 `log.md`。
- Agent Workbench 位于 `agent-workbench.md`。
- 决策索引位于 `decisions.md`。
- 判断索引位于 `judgments.md`。
- 判断资产盘点位于 `judgment-assets.md`。
- 认知历史位于 `cognitive-history.md`。
- 审阅队列位于 `review-queue.md`。
- 审阅中心位于 `review-center.md`。
- aging 报告位于 `aging-report.md`。
- 机器记忆摘要位于 `machine-memory.md`。
- 图谱视图位于 `graph-view.md`。
- 机器记忆拓扑位于 `machine-memory-topology.md`。
- 机器记忆动作队列位于 `machine-memory-actions.md`。
- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。
- Rewrite 提案队列位于 `rewrite-proposals.md`。
- 图谱健康页位于 `graph-health.md`。
- 漂移报告位于 `drift-report.md`。
- 修复待办位于 `repair-backlog.md`。
- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。
- lint 结果输出在 `output/lint/`。

## Compile Phases
- `metadata_refresh` `metadata refresh` [full/completed] | entries=0, added=0, updated=0, removed=0, changed=0
- `incremental_source_compile` `incremental source compile` [incremental/completed] | sources=0, dirty=0, clean=0, updated_pages=0, skipped_pages=0
- `concept_refresh` `concept refresh` [incremental/completed] | concept_sources=0, dirty_concept_sources=0, clean_concept_sources=0, concepts=0, dirty_concepts=0, clean_concepts=0, updated_pages=0, skipped_pages=0
- `machine_memory_refresh` `machine memory refresh` [incremental/completed] | machine_memory_sources=0, dirty_machine_memory_sources=0, clean_machine_memory_sources=0, machine_memory_concepts=0, dirty_machine_memory_concepts=0, clean_machine_memory_concepts=0, reused_core=False
- `ranking_refresh` `concept/global ranking refresh` [incremental/completed] | ranking_sources=0, dirty_ranking_sources=0, clean_ranking_sources=0, ranking_concepts=0, dirty_ranking_concepts=0, clean_ranking_concepts=0
- `index_refresh` `index refresh` [incremental/completed] | tracked_artifacts=38, dirty_artifacts=38, clean_artifacts=0, updated_artifacts=38, skipped_artifacts=0
- `cold_archive_maintenance` `cold/archive maintenance` [incremental/completed] | tracked_artifacts=6, dirty_artifacts=1, clean_artifacts=5, updated_artifacts=1, skipped_artifacts=5, removed_generated_pages=0, material_state_entries=0, archive_candidates=0, active_corpora=3, knowledge_lifecycle_entries=0
- `output_pack_refresh` `output pack refresh` [incremental/completed] | pack_groups=4, dirty_pack_groups=4, clean_pack_groups=0, review_packs=0, decision_memos=0, sop_drafts=0, updated_artifacts=5, skipped_artifacts=0
- `domain_pilot_refresh` `domain pilot refresh` [incremental/completed] | pilot_protocols=5, dirty_protocols=5, clean_protocols=0, updated_artifacts=6, skipped_artifacts=0

## Dirty Sources
- 当前没有 dirty source page。

## Dirty Concept Sources
- 当前没有 dirty concept source。

## Dirty Machine Memory Sources
- 当前没有 dirty machine-memory source input。

## Dirty Concepts
- 当前没有 dirty concept page。

## Dirty Machine Memory Concepts
- 当前没有 dirty machine-memory concept input。

## Dirty Ranking Sources
- 当前没有 dirty ranking source record。

## Clean Ranking Sources
- 当前没有 clean ranking source record。

## Dirty Ranking Concepts
- 当前没有 dirty ranking concept record。

## Clean Ranking Concepts
- 当前没有 clean ranking concept record。

## Dirty Output Pack Groups
- `lifecycle_summary`
- `review_packs`
- `decision_memos`
- `sop_drafts`

## Clean Output Pack Groups
- 当前没有 clean output pack group。

## Dirty Domain Pilot Protocols
- `general`
- `investing`
- `ops`
- `product`
- `research`

## Clean Domain Pilot Protocols
- 当前没有 clean domain pilot protocol。

## Dirty Index Artifacts
- `wiki/indexes/sources.md`
- `wiki/indexes/concepts.md`
- `wiki/indexes/decisions.md`
- `wiki/indexes/judgments.md`
- `wiki/indexes/judgment-assets.md`
- `wiki/indexes/index.md`
- `wiki/indexes/review-center.md`
- `wiki/indexes/graph-view.md`
- `.aiwiki/state/machine-memory.json`
- `.aiwiki/cache/machine-memory-graph.json`
- `output/graph/machine-memory.html`
- `wiki/indexes/machine-memory.md`
- 其余 dirty artifact：`26`

## Dirty Maintenance Artifacts
- `.aiwiki/state/planner-state.json`
