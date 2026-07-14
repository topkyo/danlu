# Round 46 — Suggested Actions De-noise

status: 完成
commit: 

Round 46 — Suggested Actions De-noise — 完成
- **目的**: 继续用户面最终形态迭代，把 `suggested_next_actions` 中的 batch/review/apply 维护命令从普通用户首屏移走；用户默认只看报告、自动化状态和少数高影响确认，维护命令保留在 Advanced / review-queue / operator 面
- **实现内容**:
  - `src/aiwiki/today_feed.py` 新增 primary/operator action filtering：primary audience 跳过 `batch-hint:*`、`review-page`、`review-action`、`apply-action`、`revert-action`、concept/rewrite/archive/alchemy auto 等维护命令
  - `audience="operator"` 仍保留维护命令，避免破坏 operator / review-queue 视图
  - `.obsidian/plugins/furnace-product-shell/src/today_feed.js` 同步 `isMaintenanceCommandAction` mirror；`main.js` rebuild（7648 lines）
  - `shell-summary.suggested_next_actions` schema 与原始数据不改；只在 primary Today/Product Shell feed 层降噪
- **测试 / 验证**:
  - focused tests：`PYTHONPATH=src python3 -m pytest tests/test_today_feed.py tests/test_product_shell_today_feed.py tests/test_cli.py::CLITests::test_today_json_hides_maintenance_suggested_actions ... -q`：58 passed
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1547 unit + 13 acceptance pass，coverage 92%
- **dogfood 用户面验证**:
  - `today --json` 当前 `todays_reports` 仍优先显示 Round 45 smoke report
  - `automation_status` 显示 `已自动维护`
  - `needs_review` 保持 3 个高影响确认：反证候选、研究判断复核、1 个 drift judgment
  - `suggested_next_actions` 从 8 条维护命令降为 0；维护命令仍存在于 `shell-summary.suggested_next_actions` / Advanced / review-queue operator 面
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - 用户面已经从“报告 + 自动化 + 关键确认 + 一串维护命令”推进为“报告 + 自动化 + 关键确认”；这更接近“用户只关心报告”的最终形态
  - 剩余迭代方向：把 `needs_review` 中的高影响确认进一步产品化为一句话决策卡 / 稍后提醒，而不是 review bucket 文案
