# 运行时规则

这个目录存放 `aiwiki` 的运行时规则。

它服务于产品运行时，不属于开发治理。

## 核心规则文件

- [采集规则](./ingest.md)
- [引用规则](./citations.md)
- [冲突规则](./conflicts.md)
- [审阅规则](./review.md)
- [回流规则](./writeback.md)
- [分类规则](./taxonomy.md)
- [协议规则](./protocols/index.md)

## 边界

- `AGENTS.md` 和 `CLAUDE.md` 是仓库/开发侧文件。
- 运行时行为应由这个目录和 `prompts/` 共同驱动。
