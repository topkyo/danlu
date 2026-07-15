# Round 17 — Output File-back Candidate Denominator

status: 完成
commit: 

Round 17 — Output File-back Candidate Denominator — 完成
- **目的**: Round 16 后 `output_file_back_rate=0.3548` 仍偏低；拆解发现分母包含 agent-pack、pilot-scorecard、dashboard、dogfood receipt、prompt proposal 等不应 file-back 的控制面/状态面输出
- **设计核心**:
  - `metrics_io._read_outputs()`: 优先读取 `.aiwiki/state/output-candidates.json`，有 candidate 时以 candidates 作为 file-back 分母
  - promoted candidate 且有 `promoted_to` 时计为 backed；pending/demoted 不计 backed
  - 没有 candidates state 时保留旧的 output markdown scan fallback
  - 不改 persisted schema、不改 metrics 顶层 key、不重写 output artifact
- **测试**:
  - `tests/test_metrics_io.py::test_output_candidates_define_file_back_denominator_when_present`
  - focused output candidate metric tests 3/3；BadPath fail-soft 回归 2/2
- **验证**:
  - 首次 full verify 暴露 BadPath fail-soft 缺口；补 `AttributeError` 捕获后重跑通过
  - `bash scripts/verify.sh` exit 0；1497 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `output_file_back_rate` 从 0.3548 → 1.0，sample_size 从 31 → 2
- **当前评估**: 高价值 output candidates 已 2/2 回流；指标现在更接近炼丹炉最终效果的真实状态。剩余主要缺口是 `elixir_reuse_count=0` 和 proposed action / judgment revisit 的长期复利信号
