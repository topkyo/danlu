# Round 68 — PROGRESS three-layer slimming + stop_line_audit lint

status: 完成
commit: 2c408f9

Round 68 — PROGRESS three-layer slimming + stop_line_audit lint — 完成 (commit 2c408f9)
- **目的**: 将 `PROGRESS.md` 从 1537 行瘦身到 ≤250 行，改为 Quick Index + 活跃 3 轮 + 改进方向指针。
- **历史归档**: 54+ round 历史拆到 `archive/rounds/round-NN.md`，保留原始 round 块语义。
- **机器索引**: 生成 `archive/rounds/index.json`，字段包含 `round_id` / `title` / `status` / `commit` / `archived_path` / `tags`。
- **lint**: `stop_line_audit` 作为独立脚本，静态对照 contract Stop Lines 与实际 diff，不进入 `scripts/verify.sh` 默认链路。
- **lint 设计取舍**:
  - 解析支持 inline `Stop Lines: 0 X / 0 Y` 与 `## Out Of Scope` bullet 两种格式。
  - 关键词白名单第一版覆盖 ~15 条高频 Stop Line；不在白名单内 → `unrecognized` warning，不阻塞（避免误报）。
  - 默认 baseline 用当前分支 upstream 的 `merge-base`（`@{upstream}`），fallback `origin/main`，再 fallback `HEAD~1`。
  - `git diff --name-only` 默认对 untracked 文件不可见；本轮 lint 已扩展为 `committed_diff ∪ worktree_diff ∪ ls-files --others --exclude-standard`，untracked 也参与审计（避免 silent bypass）。
  - helper 放 `scripts/stop_line_audit.py` 而非 `scripts/lib/`，因 `.gitignore` 忽略 `scripts/lib/`。
  - 已知 lint 在当前 worktree FAIL：发现 `.obsidian/plugins/furnace-product-shell/` 历史遗留 untracked npm 文件违反 `0 npm 依赖` Stop Line。这是 lint 正确发现真实越界，**不属于 R68**，下轮治理（gitignore 修补或 npm 工程边界澄清）。R68 commit 仅 add R68 文件，不会引入这些 npm。
- **dev tool**:
  - `scripts/extract_rounds.py` 默认 idempotent：已存在的 round 文件不会被覆盖，需 `--force` 才覆盖；index.json 移除 `generated_at` 时间戳避免 rerun 漂移。
  - `_parse_manual_file` 自动给 `p4-*` 加 `["P4"]` tag，`p4-inv-*` 加 `["P4-INV"]`；`_sort_key` 对 P4 family 做 numeric sort（`p4-3 < p4-11`），不再字典序。
  - R67/R67.5/R68 + Round 24/25 手工补全（不在新 PROGRESS 中），由 dev tool 扫描 archive 目录合并入索引。
  - 输出指标：PROGRESS 70 行 / round-*.md 59 个 / index.json 65 entries。
- **验证**:
  - `wc -l PROGRESS.md` = 70 (≤ 250 fail gate).
  - `ls archive/rounds/round-*.md | wc -l` = 59 (≥ 50 fail gate).
  - `archive/rounds/index.json` rounds 数 = 65.
  - `bash scripts/verify.sh` all green（13 acceptance + 全部 unit + coverage ≥ fail-under）.
  - lint 三场景：worktree FAIL（预期，发现历史 .obsidian npm 越界）/ R67 baseline `--baseline 6711efd~1` PASS / 负样本造伪 → FAIL 退出码 1。
  - lint idempotent rerun: `extract_rounds.py PROGRESS.md` 第二次跑输出 `extracted=0 written=0 indexed=65`。
- **Stop Lines**: 0 产品代码 / 0 fixture / 0 verify.sh 默认链路改动 / 0 review/apply/audit / 0 receipt schema.
- **Out Of Scope（R68 显式不动，下轮处理）**:
  - `.obsidian/plugins/furnace-product-shell/` 历史 untracked npm 文件（lint 已暴露）。
  - 当前 worktree 中与 R68 无关的 `docs/deepseek-comprehensive-evaluation-2026-05-03.md`（已 `git restore`）和 `docs/archive/Furnace Product Shell UX Plan.md`（仍 untracked，不 stage 进 R68 commit）。
