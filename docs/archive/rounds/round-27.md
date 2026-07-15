# Round 27 — M-UX.6 Today Target Labels + Docs Sync

status: 完成
commit: 

Round 27 — M-UX.6 Today Target Labels + Docs Sync — 完成
- **目的**: 承接 Round 26 出场建议，先提交 vault 用户视图，再做 dogfood Obsidian 复核、Product Shell 按钮语义精修和文档修订
- **已提交基线**:
  - `911c7df polish vault user view`
- **dogfood 复核**:
  - `/home/tim/danlu/炼丹炉/.obsidian/workspace.json` 结构检查通过：主区 active leaf 为 Product Shell，左右侧栏折叠，左侧仅文件列表/书签，右侧仅大纲/反链
  - `danlu-zh-folders.css` 已启用，并覆盖隐藏 `raw/wiki/schema` 与 `output/graph/output/control/output/review` 等 runtime/operator folders；`output` / `output/reports` 显示为“报告 / 全部报告”
  - Obsidian AppImage 已以 `/home/tim/danlu/炼丹炉` 参数启动；当前系统 `gio` 不支持 `obsidian://` URI，且既有 Obsidian 进程未开 CDP 端口，因此本轮以进程参数 + workspace/snippet 结构复核为准，不做截图级断言
  - dogfood `shell-status` exit 0；active protocol=`research`
- **UX 精修**:
  - Product Shell Today feed 的 workspace target 可见标签改为产品语义：报告、决策页、判断页、提案页、关系图谱、审阅入口或工作区页面；不再默认把 `output/...` / `wiki/...` 路径暴露为主标签
  - Today 报告动作与报告卡按钮从泛化 `Open` 收敛为 `Open report` / “打开报告”；决策和判断动作分别是 `Open decision` / `Open judgment`
  - 按钮补 `aria-label` 与 `title`，保留真实 target 供 hover/debug 和打开逻辑使用
  - 插件 build 产物 `main.js` 已更新；dogfood vault 插件文件与 repo 插件文件为同一 inode，因此同步生效
- **文档修订**:
  - `docs/Furnace Product Shell.md` 更新到 2026-04-29，新增 UX follow-up 状态，记录文件树用户视图、更多工具、Today target 产品标签和关系图谱中文化边界
  - `README.md` 将 Advanced 表述收敛为“更多工具”，补充普通用户文件树默认只看报告的说明
- **验证**:
  - `node --check .obsidian/plugins/furnace-product-shell/main.js`
  - focused Product Shell/vault tests: `tests.test_product_shell_today_feed tests.test_product_shell_smoke tests.test_product_shell_metrics tests.test_vault tests.test_obsidian_workspace`，55/55
  - dogfood config review pass
  - `bash scripts/verify.sh` exit 0；1506 unit + 13 acceptance；coverage 92%
- **当前评估**: UX 入口继续从 runtime 路径和泛化动作名，收敛到“投料 / 今日 / 打开报告 / 更多工具”；没有扩 `shell-summary`、settings schema 或 runtime 目录规则
