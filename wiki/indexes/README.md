# wiki/indexes 策略

`wiki/indexes/` 保存由 `aiwiki compile` 生成的派生索引页和看板页。

- 这些文件不是 SoT。事实来源仍是 `raw/`、`wiki/sources/`、受控回流的 `wiki/derived/`、schema 文件，以及 runtime state / receipts。
- 不要靠手改生成索引正文来修数据；应重新运行 compile，让索引从底层状态再生成。
- 如果生成索引持续产出破链或 stale 页面，应修正发出该链接的 compile 输入或规则。
- 如果生成索引对仓库太吵，应明确把生成输出移出版本控制；不要临时删除整个目录。

本 README 是该目录的人读策略说明，可以手写维护。
