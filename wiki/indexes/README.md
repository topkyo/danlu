# wiki/indexes 策略

`wiki/indexes/` 保存由 `aiwiki compile` / nightly 生成的派生索引页和看板页。

- 这些文件不是 SoT。事实来源仍是 `raw/`、`wiki/sources/`、受控回流的 `wiki/derived/`、schema 文件，以及 runtime state / receipts。
- 不要靠手改生成索引正文来修数据；应重新运行 compile，让索引从底层状态再生成。
- 如果生成索引持续产出破链或 stale 页面，应修正发出该链接的 compile 输入或规则。
- 如果生成索引对仓库太吵，应明确把生成输出移出版本控制；不要临时删除整个目录。

## 在生页面（有 writer，compile/nightly 会刷新）

| 页面 | 写入方 |
|---|---|
| `furnace-center.md` | compile（用户首屏：今天做什么 / 最近输出 / 快速跳转） |
| `index.md` | compile（全量主索引） |
| `sources.md` / `concepts.md` / `decisions.md` / `judgments.md` / `judgment-assets.md` | compile |
| `review-queue.md` | compile |
| `compile-status.md` | compile |
| `machine-memory.md` | compile |
| `protocols.md` | compile（`render_protocols_dashboard`） |
| `review-center.md` / `graph-view.md` | 模板首装（managed 静态页，正文手写维护） |
| `repair-backlog.md` | nightly |

## 已退役页面（无 writer，不要再生成或链接）

2026-08-06 入口面清理起，下列页面没有写入方，vault 里的同名文件属历史残留，可删除：

`aging-report.md`、`agent-workbench.md`、`domain-pilots.md`、`output-packs.md`、`concept-quality.md`、`rewrite-proposals.md`（索引页；单条 proposal 页仍由 reconcile 写 `wiki/rewrite-proposals/`）、`machine-memory-topology.md`、`machine-memory-actions.md`、`machine-memory-repair-plan.md`、`drift-report.md`、`graph-health.md`、`execution-audit.md`、`execution-center.md`、`cognitive-history.md`、`Outputs.md`（旧 hub，首屏由 `furnace-center.md` 取代）。

背景与执行清单见 `docs/plans/2026-08-06-entry-surfaces-cleanup.md`。

本 README 是该目录的人读策略说明，可以手写维护。
