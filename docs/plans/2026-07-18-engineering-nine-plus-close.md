# Engineering Nine-Plus Close（排除商业）

> **Goal**：修复 2026-07-18 全量审计中的非商业缺口，使 **工程/runtime 综合分 ≥ 9.0**，并刷新 Scorecard 工程门禁口径。  
> **Out of scope**：PyPI、EULA 法律签收、Demo 媒体、价格/销售页、WS6 商业话术。  
> **Approved by**：用户「针对发现的缺口进行修复…除了商业…提高到 9 分以上…闭环」。

## Success criteria

1. P0 路径越界：`file-back` / `review-page` / machine-memory `bundle_path` 统一 `safe_resolve_within`（vault 外拒绝）。
2. P1 写入：`review-page` 与 ask 失败标记路径改 `atomic_write_text`（或等价 atomic helper）。
3. P1 死代码：确认无 caller 后删除 `runner/auto_adopt.py`；清理指向已删 CLI 的错误文案 / docstring / Shell 测试引用。
4. SoT：AGENTS / Scorecard / Active docs 计数与治理面与代码一致（acceptance 21、Jest 168、单协议、W3 后 CLI）。
5. Scorecard：拆出 **Local Engineering Gate ≥9.0**（可复算）；Dogfood live 诚实标 not-yet / historical，**不阻塞**工程门禁宣称。
6. CI：`.github/workflows/verify.yml` 跑 `bash scripts/verify.sh all`。
7. `bash scripts/verify.sh all` PASS；交叉 review 无 Critical 残留。

## Scoring rulers（本计划）

| 尺子 | 目标 | 不含 |
|---|---|---|
| Local Engineering Gate（新） | ≥ 9.0 | 商业 go-live |
| AGOS Dogfood live | 诚实 not-yet | 不伪造 PASS |
| 商业可售 | 不动 | 本计划 Out |

## Tasks

### Task 1 — Vault 路径边界 + atomic 写
**Depends on:** none  
**Files:** `src/aiwiki/execution/ask.py`, `src/aiwiki/execution/review.py`, `src/aiwiki/execution/machine_memory_actions.py`, `src/aiwiki/runner/workflows_ask.py`（仅 degraded mark 路径）, 必要时 `app_utils.py` 复用 `safe_resolve_within`  
**Steps:**
1. `file_back` / `review_page`：解析后路径必须 `safe_resolve_within(root)`；vault 外 → 明确错误。
2. `bundle_path` 拼接后同样约束。
3. `review_page` 持久化改 `atomic_write_text`；`_mark_run_ask_artifact_degraded` 同。
4. 保持现有成功路径语义（vault 内相对/绝对路径仍可用）。
**Verify:** `bash scripts/verify.sh python-static` && `PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -q --tb=line`（至少相关 subset；全量可在 Task 5）

### Task 2 — 删除 orphan `auto_adopt` + 死 CLI 文案
**Depends on:** none（与 Task 1 文件尽量不重叠；若冲突先合 Task 1）  
**Files:** `src/aiwiki/runner/auto_adopt.py`（删）、其 import 点、`execution/machine_memory_actions.py` 错误文案、`execution/__init__.py`、Product Shell 测试中死 CLI 断言、`cli/parsers.py` help 若仍提 audit/apply  
**Steps:**
1. `rg` 确认无 runtime caller（仅 docs/config flags 除外）。
2. 删除 `auto_adopt.py`；清理 import；`autonomy_policy` 保留 flag 字段但文档注明 unused/legacy（或最小兼容，不扩 scope）。
3. 错误消息不再教用户跑 `apply-action`；改为「库内 apply / nightly reconcile / alchemy-revert」。
4. Shell 测试去掉或改写死 CLI token 断言。
**Verify:** `bash scripts/verify.sh python-static product-shell-static`

### Task 3 — Acceptance 补盖路径安全
**Depends on:** Task 1  
**Files:** `tests/test_acceptance_loop.py` 和/或新 fixture under `tests/fixtures/acceptance/`  
**Steps:**
1. 新增最小 case：vault 外 path 对 `file-back` 或 `review-page` 失败（可 function-level 直接调 API，避免大 fixture）。
2. 可选：atomic 写后文件完整可读的 smoke 断言。
**Verify:** `PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -q --tb=short`

### Task 4 — GitHub Actions CI
**Depends on:** none  
**Files:** `.github/workflows/verify.yml`（新建）  
**Steps:**
1. 在 `ubuntu-latest` 上：checkout、setup Python 3.10+、Node（Jest）、`pip install -e '.[dev]'`、`bash scripts/verify.sh all`。
2. 不引入商业/部署步骤。
**Verify:** 工作流 YAML 语法合理；本地仍 `bash scripts/verify.sh scripts` PASS

### Task 5 — SoT + Scorecard Local Engineering Gate ≥9.0
**Depends on:** Task 1–4（数字与行为稳定后）  
**Files:** `docs/AGOS-9-Scorecard.md`, `AGENTS.md`, `PROGRESS.md`（若可写；注意 gitignore）, `docs/Furnace Post-Cleanup Audit...` 指针段（轻量）, Active docs 中明显 stale 的治理 CLI 列表  
**Steps:**
1. 刷新 hub LOC、acceptance **21**、Jest **168**、runtime ~63.6k。
2. 新增/改写「Local Engineering Gate」：权重维（Runtime / Shell / LLM / Governance-remaining / Maintainability / Docs / Verify+CI）加权 ≥9.0；明确 Dogfood live 不阻塞本门禁。
3. Governance 维改为 post-W3 现实：review-page、alchemy revert、receipts、kill switch、nightly reconcile；删 CLI 不假装仍在。
4. AGENTS Cloud 段去掉已删 `run-compile`；计数对齐。
**Verify:** `bash scripts/docs_consistency_check.sh`

### Task 6 — 全量验证 + 交叉 review + 重评分闭环
**Depends on:** Task 1–5  
**Steps:**
1. `bash scripts/verify.sh all`
2. 只读 reviewer 对整支分支 diff 做 Critical/Warning 审查；Critical 必须修。
3. 父会话写短评分表：工程综合 ≥9.0；商业分不动。
**Verify:** `all` PASS + review 无 Critical

## Commit policy

每完成一 Task：一次 commit（`fix:` / `refactor:` / `docs:` / `ci:`）。

## Non-goals

- hub broad rewrite（D16）
- 恢复已删 governance CLI
- 伪造 dogfood live PASS
- 商业 go-live 项
