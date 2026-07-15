# Round 33 — Human-readable Output Filenames

status: 完成
commit: 

Round 33 — Human-readable Output Filenames — 完成
- **目的**: 回应用户指出的产品表面问题：`query-20260429-152929-...` 这类文件名不直观；时间戳已存在于 frontmatter / runtime history，用户可见文件名应优先表达内容
- **实现**:
  - `ask` / `run-ask` 的 report/slides/figure/decision-memo/sop 产物不再默认生成 `query-{timestamp}-...` 文件名
  - 新命名策略基于问题/标题生成可读 stem，保留英文和中文等 alnum 字符，过滤路径分隔符与不可打印字符
  - 同名碰撞使用 `-2` / `-3`，不重新引入时间戳
  - `file-back` 生成的 `wiki/derived` / `wiki/decisions` / `wiki/judgments` 文件名去掉时间戳，保留 kind 前缀，例如 `judgment-eva-robot-batch-e-semantic-navigation-assessment.md`
  - 继续保留 `created_at`、`formed_at`、`last_compiled_at`、runtime history、candidate state 和 review lifecycle 作为审计事实来源
  - 保留 `aiwiki.execution.ask.slugify` 导入符号，维持既有迁移测试覆盖的 hot-patch seam
- **示例**:
  - 旧：`output/reports/query-20260427-000000-deterministic-source-a.md`
  - 新：`output/reports/deterministic-source-a.md`
  - 中文：`output/reports/评估炼丹炉最终形态.md`
  - file-back：`wiki/judgments/judgment-eva-robot-batch-e-semantic-navigation-assessment.md`
- **边界**:
  - 不批量重命名既有 dogfood 产物，避免破坏已记录的 runtime history、judgment `source_files`、LLM receipts 和 acceptance trace
  - 本轮不改 `raw/` / `wiki/sources/` 的审计 ID 与 provenance 命名规则；它们属于事实输入和编译层，不是普通用户报告入口
- **验证**:
  - focused filename tests 覆盖英文、中文、同名碰撞、decision-memo 后缀和 file-back judgment 命名
  - acceptance `run-ask` happy/failure replay fixture 已更新并通过；全套 acceptance 13/13
  - `bash scripts/verify.sh` exit 0；1517 unit + 13 acceptance；coverage 92%
