# Round 20 — Elixir Reuse From Structured Derived References

status: 完成
commit: 

Round 20 — Elixir Reuse From Structured Derived References — 完成
- **目的**: dogfood 主指标只剩 `elixir_reuse_count=0`；需要区分“真实尚未复用”和“metrics 没读到 promote/include-elixir 事实”
- **设计核心**:
  - `metrics.compute_elixir_reuse_count()`: `operation=promote` + `subject_kind=elixir_promotion` 现在会把 settled 金丹加入 active set；保留 legacy `finalize/elixir` 口径
  - `metrics_io._read_elixir_reference_receipts()`: 只扫描 elixir page frontmatter 的结构化 `derived_from`，将 `wiki/elixirs/*.md` 引用合成为 read-side reuse receipt
  - 不把普通正文里提到金丹路径的 dogfood receipt/report 算作复用，避免伪造复利
- **真实 dogfood 复用**:
  - 执行 `alchemy-start research-v3-6-v3-5-slam-f63b5345 --topic "Round 20 reuse of V3.6/V3.5 SLAM elixir" --protocol research --include-elixir elixir-v3-6-vs-v3-5-slam-a4566731`
  - 新 candidate: `output/_candidates/elixirs/elixir-round-20-reuse-of-v3-6-v3-5-slam-elixir-9b99f14a.md`
  - `derived_from` 同时包含 `wiki/derived/derived-20260428-123017-v3-6-v3-5-slam.md` 与 `wiki/elixirs/elixir-v3-6-vs-v3-5-slam-a4566731.md`
- **测试**:
  - `tests/test_metrics.py::test_elixir_reuse_promote_receipt_activates_settled_elixir_path`
  - `tests/test_metrics_io.py::test_elixir_derived_from_reference_counts_as_reuse_after_promotion`
  - focused elixir metric tests 4/4
- **验证**:
  - `bash scripts/verify.sh` exit 0；1501 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `elixir_reuse_count` 从 0 → 1，sample_size 15 → 16
- **当前评估**: 所有 dogfood 主指标已反映一个完整闭环；剩余工作应转向体验/队列 backlog，而不是继续读侧修正指标
