# Round 11 — Metrics Review Activity From Page Reviews

status: 完成
commit: 

Round 11 — Metrics Review Activity From Page Reviews — 完成
- **目的**: Round 10 真实 `review-page ... --status confirmed` 后，`metrics --json` 仍显示 `review_closure_rate=null reason=no review activity`。根因是 metrics 只读 execution receipts，不读 decision/judgment page review metadata
- **设计核心**:
  - `metrics_io.py`: `_read_receipts()` 追加 `_read_page_review_receipts(root)` 输出，将 `wiki/decisions/*.md` / `wiki/judgments/*.md` 中带 `reviewed_at` 的 closed status 合成为 `ReceiptMeta(subject_kind="review")`
  - closed status 口径：`approved` / `confirmed` → `approve`，`rejected` → `reject`，`needs-revisit` / `superseded` → `close`
  - `tracking` / `tentative` 不算 closure，继续作为持续跟踪态
  - 不改 metrics 顶层 key、不改 persisted schema、不改 `review-page` 写入格式
- **测试**:
  - `tests/test_metrics_io.py::test_page_review_history_counts_as_review_closure_activity`: confirmed judgment 计入 closure，tracking judgment 不计 closure；closure / pending denominator 正确
  - `tests/test_metrics.py` 既有 review closure tests 保持
- **验证**:
  - focused: `tests/test_metrics_io.py tests/test_metrics.py -k 'review_closure or page_review'` 4/4
  - `bash scripts/verify.sh` exit 0；1492 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `review_closure_rate` 从 `null/no review activity` → `1.0`，`sample_size=2`
- **当前评估**: 指标现在能反馈 Round 10 的 page review 闭环；下一轮可继续处理 remaining ready actions，或做 batch-safe apply UX（避免每条 apply 后 stale bundle 需要手动重跑 dry-run）
