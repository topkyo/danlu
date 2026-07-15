# Round 15 — Provenance Completeness Metrics Schema Alignment

status: 完成
commit: 

Round 15 — Provenance Completeness Metrics Schema Alignment — 完成
- **目的**: `metrics --json` 长期显示 `provenance_completeness=0.0`，但 dogfood source pages 实际已有 `source_files` + `source_sha256` raw provenance；根因是 metrics 仍按旧字段 `source_url/captured_at/derived_from` 判定完整性
- **设计核心**:
  - `metrics_io._read_wiki_pages()`: `source_files` 计入 source anchor 和 derived-from provenance
  - `source_sha256` 计入 capture/integrity provenance
  - 保留旧字段 `source_url` / `captured_at` / `derived_from` 兼容；不改 compute layer、不改 metrics 顶层 key、不迁移 vault 数据
- **测试**:
  - `tests/test_metrics_io.py::test_wiki_page_current_source_schema_counts_as_provenance`
  - focused provenance metrics tests 3/3
- **验证**:
  - `bash scripts/verify.sh` exit 0；1495 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `provenance_completeness` 从 0.0 → 1.0，sample_size=15
- **当前评估**: source 层 provenance 指标已恢复可信；剩余关键缺口转为 `output_file_back_rate=0.0323` 与 `elixir_reuse_count=0`，即高价值输出回流和金丹复用还没有形成稳定复利
