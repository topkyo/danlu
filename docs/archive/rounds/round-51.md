# Round 51 — Dashboard Template Ownership

status: 完成
commit: 

Round 51 — Dashboard Template Ownership — 完成
- **目的**: 收口 `DEFAULT_DASHBOARD_FILES` 与 vault 中 dashboard markdown 的双写漂移；compile 每轮刷新 managed dashboard 模板，并通过 `CompileContext` 计入 changed/index artifacts
- **任务清单来源**: `.codex/plans/user-surface-roadmap.md`
- **实现内容**:
  - `ensure_runtime_dashboards(root, overwrite=False)` 保持 bootstrap 语义：`ensure_layout` 不覆盖既有 dashboard 文件
  - `compile_runtime_phase` 开头遍历 `MANAGED_DASHBOARD_TEMPLATE_FILES`（当前 `review-center.md` / `graph-view.md`），用 `context.write_index_artifact(root / relative, content)` 刷新静态 managed dashboard 模板
  - 动态 owner 页面（protocols、furnace / execution center、cognitive history、packs、pilots 等）排除在模板刷新之外，避免 transient rewrite 造成 compile accounting 误报
  - compile result 新增 `index_changed_pages`，与 `phase_summary[index_refresh].details.updated_artifacts` 对齐
- **测试 / 验证**:
  - 新增/更新测试：`test_compile_refreshes_managed_dashboard_templates` 覆盖手改 `graph-view.md` 后 compile 恢复模板并记录 dirty index artifact / updated_artifacts；`test_ensure_layout_does_not_overwrite_existing_dashboard_files` 覆盖 bootstrap 不覆盖；`test_compile_writes_phase_summary_and_compile_state` 覆盖 clean index artifacts / `index_changed_pages`
  - acceptance replay goldens 已刷新，因为 `graph-view.md` 进入 run-ask prompt 的内容发生变化
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1562 unit + 13 acceptance pass，coverage 92%
- **dogfood 验证**:
  - 暂停 watcher 后执行 deterministic `compile`
  - `/home/tim/danlu/炼丹炉/wiki/indexes/graph-view.md` 已恢复最新模板，包含“默认工作流仍然是先看报告”、Mihomo/Clash 与 `text/html` 中文排障提示
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - dashboard 模板与 vault 文件的漂移已由 compile 收口；repo 副本继续作为 starter/fallback，不再作为长期手工事实源
  - 下一站 Round 52：UI / 插件 polish（图谱 mini 例子、responsive 图例、可点击对端节点）
