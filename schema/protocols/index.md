# 协议规则索引

这里存放统一炼丹炉的单 runtime 协议规则层。

- 炉子只有一个 runtime：`general`。
- 领域差异通过概念、判断和 schema 扩展表达，不再拆多套 protocol slug。

## 可用协议
- [通用协议](./general/index.md)：默认的跨域协议，适合把事实、综合、判断和复审保持分层。

## 约束

- 协议层是统一 runtime 的规则覆盖，不是新的 runtime 分叉。
- 非 `general` 的旧 protocol slug 会在 state 加载时一次性迁移到 `general`。

## 运行时行为

- `decision / judgment` 默认 review window 沿通用协议执行。
- `file-back` 生成的页面模板沿通用协议执行。
- recurring promotion、review / nightly / repair 沿通用协议焦点执行。
- `query / output / execution proposal` 沿通用协议偏置执行。
