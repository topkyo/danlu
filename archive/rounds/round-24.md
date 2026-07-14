# Round 24 — M-UX.3 真机 Product Shell 继续收敛

status: 完成
commit:

Round 24 / M-UX.3 真机 Product Shell 继续收敛 — 完成
- 首屏 workspace：repo `.obsidian/workspace.json`、`bootstrap_new_vault()` 默认模板、dogfood `/home/tim/danlu/炼丹炉/.obsidian/workspace.json` 均默认折叠左右侧栏；功能上保留文件列表/书签和大纲/反链，但不再占用产品首屏。
- Today feed：`review_backlog_counts` bucket 可见标题从内部 id 改为产品中文文案（补充反证候选、复核研究判断、处理 L3 提案、修复机器记忆等）；`review:*` target 和命令类 action target 首屏展示中文提示，不直接暴露 raw target 或整条命令。
- 关系图谱：`output/graph/machine-memory.html` 的 title、H1、说明、legend、筛选项、详情字段、相关入口已中文化；dogfood 已重新 compile 刷新关系图谱输出。
- Verification：focused tests pass；`bash scripts/verify.sh` pass（1504 unit + 13 acceptance，coverage 92%）。
- QA review：fresh-session reviewer mode 可解析，但本机 Codex usage limit 阻塞独立会话启动；已记录 same-context fallback，无发现。
