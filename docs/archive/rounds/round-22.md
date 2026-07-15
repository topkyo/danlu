# Round 22 — M-UX.1 Product Shell New-user UX Refactor

status: 完成
commit: 

Round 22 — M-UX.1 Product Shell New-user UX Refactor — 完成
- **目的**: 先单独提交 `docs/archive/Furnace Product UX Assessment.md`，再按该 UX 评估和 `docs/Furnace Product Shell.md` 的“一输入端 + 一输出端 + Advanced 折叠”原则，做面向新用户测试的 Product Shell UX 收敛；本轮不考虑老用户既有布局习惯
- **先行提交**:
  - `b65427a docs: add Furnace product UX assessment`
- **设计核心**:
  - Today feed 从文本列表升级为 action card；路径类 item 提供 `Open`，review bucket 提供 `Open Review`，命令类 item 只提供 `Copy command`，未知 target 只提供 `Copy target`
  - Advanced summary 展示审阅、执行、最近运行计数，保持治理能力可发现但不占首屏
  - 默认 workspace 主区打开 Product Shell；左侧只保留文件列表和书签；右侧只保留 Outline / Backlinks
  - `HOME.md` 与 new-vault `HOME.md` 从全量索引页降级为产品入口说明和关键链接
  - UX Assessment 增加二次评估与落地边界，明确不扩 `shell-summary`、不改 schema、不做 Today 一键 Run、不迁移已有 vault
- **测试**:
  - `tests/test_product_shell_today_feed.py`: Today item action controls + Advanced count summary static contract
  - `tests/test_obsidian_workspace.py`: repo workspace default shell-first layout
  - `tests/test_vault.py`: new-vault workspace/home defaults
  - 既有 `tests/test_product_shell_smoke.py::TodayFeedTypographyContract` 保持 raw color 约束
- **验证**:
  - `node --check .obsidian/plugins/furnace-product-shell/main.js`
  - focused unittest: `tests.test_obsidian_workspace tests.test_product_shell_today_feed tests.test_vault`
  - `bash scripts/verify.sh` exit 0；1503 unit + 13 acceptance；coverage 92%
- **QA gate**:
  - `qa-review`: same-context fallback pass；原因是当前没有独立 reviewer 可用
  - `qa-runtime`: scripted pass；覆盖 focused checks + full verify
- **当前评估**: Product Shell 默认入口更接近“投料 / 提问 / 看 Today / 打开报告”的产品路径；runtime 分层仍保留，但不再作为新用户首屏必须理解的导航结构
