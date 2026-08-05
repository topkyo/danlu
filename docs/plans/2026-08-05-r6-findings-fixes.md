# R6 发现修复（验证确认后收口）

> 目标：修 R6 未披露事实 + P1 机制债；**不加分**，把 8.6 做成可复验状态。

| # | 项 | Done when | Status |
|---|-----|-----------|--------|
| 1 | D-2 coverage 69→71 + CHANGELOG unit 钉进 docs_consistency | pins 绿 | [x] |
| 2 | T-2 `npm ci` 后 `test -x node_modules/.bin/jest` | 缺 jest 时 fail loud | [x] |
| 3 | N-1 writeback except 标注 restore-then-raise | 注释清晰；except 总数如实 | [x] |
| 4 | T-1b 六命令 argv/`main()` 最小用例 | unit 覆盖 dispatch | [x] |
| 5 | A-1 `ask_question` + `_write_run_ask_success` 真拆分（非搬家） | 编排函数明显变薄；子步骤可独立读 | [x] |
| 6 | 正式化 R6 + SoT 交叉记录 | PROGRESS/Scorecard 指针 | [x] |

Out：Commercial；S-1 manifest author；G-1b acceptance revert fixture（本轮不扩）。
