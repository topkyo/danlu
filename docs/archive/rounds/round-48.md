# Round 48 — Graph Polish Sweep

status: 完成
commit: 

Round 48 — Graph Polish Sweep — 完成
- **目的**: 收掉 Round 47 review 留下的 4 个图谱低风险问题；底层 graph schema 不变
- **任务清单来源**: `.codex/plans/user-surface-roadmap.md`
- **实现内容**:
  - `src/aiwiki/memory/graph.py` 把关系标签集中成模块级常量 `RELATION_LABELS` + 中文家族 fallback `判断关系 / 决策关系 / 因果关系 / 其他关系`，不再回落到英文后缀
  - 中文命名表统一为：跨类边「{源}{动}{目标}」（材料提到概念 / 材料支撑判断），同类边「{节点}{关系}」（概念相关 / 判断 X / 决策 X / 因果 X）；旧词 `因果链 / 促成关系 / 约束关系 / 冲突关系 / 阻塞关系` 全部退役
  - `HAS_CONCEPT` 启用独立配色 `#0ea5e9`，与 fallback 灰 `#94a3b8` 区分；图例 / SVG `<line>` 同步
  - 关系数量统计 key 从中文 label 改为 `edge_type`，渲染时再映射；每行追加 `<code class="relation-machine-type">` 暴露原始 type，方便排查未来新增 edge
  - `wiki/indexes/graph-view.md` 与 `app_protocol.py` 模板恢复一句中文 Mihomo/Clash 排障提示
- **测试 / 验证**:
  - 新增 4 个测试：`test_relation_label_table_is_uniform_chinese`（命名表完整断言）、`test_relation_style_has_concept_uses_dedicated_color`（颜色独立）、`test_relation_summary_keys_by_edge_type_not_chinese_label`（同 label 不合并）、`test_graph_surface_uses_unified_relation_naming`（因果链旧词不再出现）
  - focused tests：8 passed
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1551 unit + 13 acceptance pass，coverage 92%
  - `plugin-build`: not applicable（本轮未触碰 Obsidian 插件文件）
- **dogfood 图谱验证**:
  - 暂停 watcher 后跑 deterministic `compile`，刷新 `/home/tim/danlu/炼丹炉/output/graph/machine-memory.html`
  - 确认改动落地：`#0ea5e9`（HAS_CONCEPT 独立色）、`data-relation-label`、`data-relation-type`、`relation-machine-type` CSS class
  - dogfood vault 自身 `wiki/indexes/graph-view.md` 是用户副本（compile 不重写），Mihomo 提示同步留作 Round 51 模板↔vault 收口处理
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - 关系图谱表达层完全中文且自洽，机器 schema 完整保留
  - 下一站 Round 49：报告↔图谱锚点（让用户从报告反向追溯图谱节点）
