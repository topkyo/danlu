# Round 16 — Output File-back Metrics Source Files Fallback

status: 完成
commit: 

Round 16 — Output File-back Metrics Source Files Fallback — 完成
- **目的**: `output_file_back_rate=0.0323` 偏低；dogfood decision memo output 已有 `source_files`，但 metrics 只读旧字段 `derived_from`
- **设计核心**:
  - `metrics_io._read_outputs()`: `derived_from` 继续优先；缺失时用 `source_files` 作为 provenance fallback
  - 不改 `OutputMeta` dataclass、不改 compute layer、不改 metrics 顶层 key、不重写 output artifact
- **测试**:
  - `tests/test_metrics_io.py::test_reads_output_source_files_as_provenance_fallback`
  - focused output metrics tests 4/4
- **验证**:
  - `bash scripts/verify.sh` exit 0；1496 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `output_file_back_rate` 从 0.0323 → 0.3548，sample_size=31
- **当前评估**: output provenance 指标已恢复大半可信；剩余未 backed outputs 主要应是 agent/pilot/status/draft 类派生视图，需要下一轮区分“需要回流的高价值输出”和“终端控制/状态输出”，避免用一个总分母惩罚所有派生界面
