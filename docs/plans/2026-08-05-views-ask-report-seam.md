# views hub 单 seam：ask_report 外提

> **For agentic workers:** inline / executing-plans。禁止 broad rewrite。

**Goal:** 从 `render/views.py` 外提 ask 报告渲染簇到 `render/ask_report.py`，views 行数明显下降。  
**Seam（唯一）：** `machine_memory_query_plan_lines` … `render_report`（约 L671–921）。  
**Out:** 不动 review_queue / furnace_center / curated_index；不改报告语义。

## Task 1

- [x] Create `src/aiwiki/render/ask_report.py`（剪切上述函数 + 所需 import）
- [x] `views.py` 删除该簇；更新模块 docstring
- [x] Callers：`execution/ask.py`、`runner/workflows_ask.py` → `render.ask_report`
- [x] Optional：`views.py` 不留 re-export（直引 owner）
- [x] Verify：`python-static` / `unit` **153** / `acceptance` **24** / `llm-integration` **85** / `scripts` 绿
- [x] Done：`wc -l views.py` = **668**（< 700）；ask_report 266 行可独立 import
