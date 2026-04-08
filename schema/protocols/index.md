# 协议规则索引

这里存放统一炼丹炉的多协议规则层。

- 炉子只有一个。
- 领域协议可以有很多套。
- 当前 starter library 先提供 `general / investing / research` 三套协议。

## 可用协议
- [通用协议](./general/index.md)：默认的跨域协议，适合把事实、综合、判断和复审保持分层。
- [投资协议](./investing/index.md)：面向 thesis、risk、catalyst、invalidation 和 position decision 的协议。
- [研发协议](./research/index.md)：面向 paper、repo、benchmark、experiment 和 architecture decision 的协议。

## 约束

- 协议层是统一 runtime 的覆盖层，不是新的 runtime 分叉。
- 领域差异优先落到 `schema/protocols/`，而不是复制一套 `aiwiki`。

## 当前已经生效的运行时差异

- `decision / judgment` 的默认 review window 会按协议变化。
- `file-back` 生成的 `decision / judgment` 页面模板会按协议变化。
- recurring promotion 的标题前缀和分类提示会按协议变化。
- `review-queue`、`review-center`、`repair-backlog` 和 machine-memory action queue 会按 active protocol 调整优先级。
- `ask` 会按 active protocol 调整 source / concept ranking。
- `report / slides / figure` 会写入协议化输出偏置，约束最终成品组织方式。
- machine-memory repair execution proposal 会按 active protocol 追加领域化修复提示。
