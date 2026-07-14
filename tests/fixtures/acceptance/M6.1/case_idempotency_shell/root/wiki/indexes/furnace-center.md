# 炉心面板

这里是炼丹炉的人用统一入口，负责把今天最该处理的 review、repair、graph 和 output 收到一个地方。

## 先看哪里

- [审阅中心](./review-center.md)：看 pending review、aging、rewrite 和 ready action
- [认知历史](./cognitive-history.md)：看旧判断是否被新证据挑战
- [图谱视图](./graph-view.md)：看 machine-memory 图层和 graph health
- [修复待办](./repair-backlog.md)：看 nightly 汇总出的优先级队列
- [协议总览](./protocols.md)：看当前 active protocol
- `output/control/furnace-center.html`：本地炉心面板；这是浏览器 / 系统 HTML 入口，不是 Obsidian 内部页面。

## 怎么用

1. 先看今天的 ready actions、apply-ready rewrites 和 overdue review。
2. 再看最新 output 是否值得回流成 derived / decision / judgment。
3. 需要深入时，再跳到 review-center、graph-view 或具体页面。

## 边界

- 这是统一入口，不替代各自的专业页面。
- 高风险修复仍然停留在 proposal / review 层，不会从这里直接自动 apply。
