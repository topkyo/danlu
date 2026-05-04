# Round 47 — Chinese Relationship Graph Cleanup

status: 完成
commit: 

Round 47 — Chinese Relationship Graph Cleanup — 完成
- **目的**: 按用户要求清理关系图谱，并把图谱的人用表达统一改成中文；底层 `.aiwiki/cache/machine-memory-graph.json` 的机器 edge type / schema 不变
- **实现内容**:
  - `src/aiwiki/memory/graph.py` 新增中文关系标签：材料提到概念、材料支撑判断、概念相关、判断支持、判断冲突、判断相关、决策依据、决策反证、决策相关、决策替代、因果链、促成关系、约束关系、冲突关系、阻塞关系
  - HTML 图谱边新增 `data-relation-label` / tooltip；节点详情新增“相关关系”列表，显示该节点相连边的中文关系
  - 图例从泛化“关系边”扩展为中文关系类别；新增“关系说明”面板，解释材料、判断、概念、决策之间的读图方式
  - `wiki/indexes/graph-view.md` 与 `src/aiwiki/app_protocol.py` starter 模板改为中文产品化说明：默认先看报告，需要追溯证据链时再看图谱
- **测试 / 验证**:
  - focused graph tests：`test_compile_writes_machine_memory_graph_html` / `test_compile_generates_interactive_machine_memory_graph_html` / `test_compile_surfaces_judgment_relations_across_memory_and_history` / `test_machine_memory_graph_relation_labels_are_chinese` / `test_compile_graph_view_note_explains_local_html_behavior`：5 passed
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1548 unit + 13 acceptance pass，coverage 92%
  - `plugin-build`: not applicable（本轮未触碰 Obsidian 插件文件）
- **dogfood 图谱验证**:
  - 暂停 watcher 后执行 deterministic `compile` 刷新 `/home/tim/danlu/炼丹炉/output/graph/machine-memory.html`
  - 确认 HTML 中存在 `关系说明`、`材料提到概念`、`材料支撑判断`、`概念相关`、`判断冲突`、`决策依据`、`相关关系`
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - 图谱现在更像“报告之后的证据追溯工具”，而不是暴露机器 edge type 的运维页面
  - 剩余图谱体验方向：按报告/判断路径做一键高亮，避免用户从全图里自己找证据链
