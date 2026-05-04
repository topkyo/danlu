# Round 49 — Report ↔ Graph Anchor

status: 完成
commit: 

Round 49 — Report ↔ Graph Anchor — 完成
- **目的**: 把报告与关系图谱双向锚定：报告记录依赖的图谱节点，图谱节点详情列出引用它的报告；底层 graph JSON schema 不变
- **任务清单来源**: `.codex/plans/user-surface-roadmap.md`
- **实现内容**:
  - `ask_question` 输出 artifact 时写入 `graph_anchor_node_ids` frontmatter（至多 8 条，来源 / 概念 / 判断节点 id）并追加 `## 关系图谱锚点` 中文 section
  - `run_ask` 改为先生成 deterministic baseline 时不写锚点，避免污染 LLM prompt；LLM 覆盖文件后再重新注入 candidate frontmatter 与 graph anchors
  - `memory/graph.py::collect_report_anchors` 扫描最近 50 个 `output/reports|slides|figures/*.md`，生成 `node_id -> reports` 反向索引
  - `compile/runtime_step.py` 把 report anchors 传入 `render_machine_memory_graph_html`
  - 图谱节点详情新增“引用此节点的报告”列表；没有引用时显示空状态
- **测试 / 验证**:
  - 新增 focused tests：frontmatter 锚点写入、body 锚点 section、graph HTML 反向引用渲染、无 anchors 时不报错、collect_report_anchors 映射
  - replay acceptance golden 已刷新：`tests/fixtures/acceptance/M6.1b/case_happy_run_ask/expected/stdout/01-run-ask.json`
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1556 unit + 13 acceptance pass，coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass；已修复 `run-ask --fallback-to-ask` deterministic 成功路径漏写 graph anchors 的 finding
- **dogfood 验证**:
  - 暂停 watcher 后执行 deterministic `ask --format report --protocol research` 生成 `output/reports/round-49-graph-anchor-dogfood-报告如何反向定位关系图谱节点.md`
  - 该报告 frontmatter 含 8 个 `graph_anchor_node_ids`，body 含 `## 关系图谱锚点`
  - 重新 `compile` 后 `output/graph/machine-memory.html` 含“引用此节点的报告”，并能找到该 report path
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - 报告现在能反向追溯图谱节点，图谱节点也能回到引用报告；这让图谱成为报告之后的证据追溯层
  - 下一站 Round 50：关键确认卡产品化 + snooze
