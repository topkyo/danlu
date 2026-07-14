# Round 45 — Final-shape User Surface V1

status: 完成
commit: 

Round 45 — Final-shape User Surface V1 — 完成
- **目的**: 把用户面从“运维 backlog 首屏”推进到“报告优先 + 自动化状态 + 少数关键确认”；底层自动化继续运行，用户默认只看报告和高影响确认点
- **实现内容**:
  - `src/aiwiki/today_feed.py` 调整主 feed 产品契约：`report` 优先级最高，`automation` 独立成类，`decision/proposal` 作为 Needs Your Confirmation，`action` 靠后
  - 新增 `FeedAudience`：默认 `primary` 给用户面降噪；`review-queue` 显式用 `audience="operator"`，继续完整展示 concept / machine-memory 等低层 backlog
  - 低层治理桶（`concept_backlog` / `review_concepts` / `revisit_concepts` / `retired_concepts` / `machine_memory_actions`）不再冒泡到普通用户首屏；仍保留在 `review_backlog_counts`、`review-queue` 和 Advanced
  - `.obsidian/plugins/furnace-product-shell/src/today_feed.js` 同步 mirror；补齐 counter-evidence / drift / metric alert，与 Python feed 行为对齐；`render_today.js` 分组改为 `Reports` / `Automation` / `Needs Your Confirmation` / `Completed` / `Suggested Actions`
  - `today --json` 新增 `automation_status` section；text 模式新增 `Automation` section；acceptance golden 已刷新
  - L3 proposal 去重：主用户面只显示单条 proposal 卡，不再同时用 `l3_proposals` / `l3_proposal_attention` 两个计数字段重复提醒
  - `main.js` 已 rebuild（7625 lines）
- **测试 / 验证**:
  - focused tests：`PYTHONPATH=src python3 -m pytest tests/test_today_feed.py tests/test_product_shell_today_feed.py tests/test_app_shell_surfaces_batch_hints.py ... -q`：66 passed
  - unittest focused：52 passed
  - 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh`：1543 unit + 13 acceptance pass，coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass；两轮 finding 已修复（CLI automation section、JS mirror 漏项、L3 proposal 重复提醒）
- **dogfood 用户面验证**:
  - 暂停 watcher 后用 deterministic `ask --format report` 生成 Round 45 smoke report：`output/reports/round-45-用户面最终形态-smoke-当前炼丹炉自动化运行后-用户今天应该优先看哪些报告和确认点.md`
  - `today --json` 现在首组 `todays_reports` 含该 report；`automation_status` 显示 `已自动维护`
  - `needs_review` 只剩 3 个高影响确认类：反证候选、研究判断复核、1 个 drift judgment；L3 proposal 只在 proposal section 出现，避免重复
  - `concept_backlog=11`、`machine_memory_actions=14` 等低层债不再压主用户面；当轮 `suggested_next_actions` 仍保留 8 条作为次级/Advanced 入口（Round 46 已继续降噪到 primary feed 0 条）
  - `aiwiki-watch.service` 与 `aiwiki-nightly.timer` 结束时均 active
- **当前评估 / 最终形态推进**:
  - 本轮完成“用户默认只看报告和关键确认”的第一层产品化：报告优先已在真实 dogfood 数据上成立，自动化与 backlog 不再抢首屏
  - 剩余用户面迭代方向：把 `suggested_next_actions` 中的 batch/review 命令进一步做成一键“稍后处理/自动归档为维护债”，并让 Product Shell 首页直接显示“已自动维护 / 无需处理”的状态卡
