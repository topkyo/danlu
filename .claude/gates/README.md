# Gate Artifacts

`deploy-gate` 读取本目录中的 gate artifact，决定是否允许进入 deploy。

## 文件

- `qa-review.md`
- `qa-runtime.md`

## 头部格式

每个文件开头必须包含:

```markdown
status: pass | fail | blocked | not-required
checked_at: YYYY-MM-DD
contract_sha: <sha256 of .claude/contracts/active.md>
worktree_fingerprint: <fingerprint of current git HEAD + worktree state, or file snapshot fallback when git is unavailable>
summary: 一句话摘要
```

后续正文可自由补充 findings、跳过项、风险说明。

可用以下命令自动写入这些头部字段:

```bash
bash scripts/write_gate_artifact.sh qa-review --status pass --summary "no findings" --reviewer-mode same-context --reviewer-fallback-reason "isolated reviewer unavailable"
```

若当前 gate 已经是本轮最后一个 gate，也可以顺手追加 calibration entry:

```bash
bash scripts/write_gate_artifact.sh qa-runtime --status pass --summary "runtime smoke passed" --runtime-mode scripted --append-calibration --calibration-task "feature round" --contract-scope-changed no --new-session yes --progress-read no
```

执行模式字段:

```markdown
reviewer_mode: isolated-agent | external-agent | fresh-session | same-context | human
reviewer_fallback_reason: <required when reviewer_mode is same-context>
reviewer_identity: <tool / model / session name>
reviewer_scope: contract+diff+touched-files | full-repo | custom
runtime_mode: scripted | isolated-agent | same-context | human
runtime_identity: <tool / model / session name>
```

其中:
- `qa-review` 在 `status: pass` 时必须写 `reviewer_mode`
- 若 `reviewer_mode: same-context`，必须写 `reviewer_fallback_reason`
- 其余 `reviewer_*` 推荐写
- `qa-runtime` 在 `status: pass` 时必须写 `runtime_mode`；其余 `runtime_*` 推荐写
- `deploy-gate` 会校验这些必填 mode 字段；identity / scope 主要用于保留执行方式与校准数据
- 若希望 `write_calibration_entry.sh --from-current-gates` 在 `fail` / `blocked` artifact 上也能自动导入 mode，建议这些状态同样保留对应 mode 头部

## 规则

- `qa-review` 是否必需，由 `.claude/contracts/active.md` 中的 `Gate Requirements` 决定
- `qa-runtime` 是否必需，由 `.claude/contracts/active.md` 中的 `Gate Requirements` 决定
- `qa-review` / `qa-runtime` 的 artifact 路径由 contract 中的 `Gate Artifacts` 声明决定；脚本会实际读取这些路径
- artifact 路径必须保持在 `.claude/gates/*.md` 下，否则 `deploy-gate` 会拒绝放行
- 若 `qa-runtime` 在本轮不必需，建议仍写 artifact，并标记 `status: not-required`
- `contract_sha` 必须与当前 `.claude/contracts/active.md` 匹配，否则视为旧 artifact，不得放行
- `worktree_fingerprint` 必须与当前工作区一致；contract 不变但代码变了，旧 artifact 仍然失效
- 若项目不在 Git worktree 中，`deploy-gate` 会退化为对当前项目文件树做快照哈希；该模式不会复用 `.gitignore` 语义，因此会比 Git 模式更敏感
- 计算 `worktree_fingerprint` 时应排除 gate artifact 自身（`.claude/gates/*.md`），避免自指失效
