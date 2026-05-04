# Round 54 — D-3 Elixir Stage-3 Compounding End-to-End

status: 完成
commit: 

Round 54 — D-3 Elixir Stage-3 Compounding End-to-End — 完成
- **目的**: D-1 方向文档识别的真实 gap：金丹 thesis 阶段 3 "新丹引用旧丹 + 锚定 wiki/derived 底层证据" 在 unit test 已有部分覆盖（`test_distill_include_rejects_candidate_reference` 反例），但缺一份完整的 happy-path 端到端：promote 旧丹 → 新丹引用旧丹 + DAG/anchor/counter_evidence gate 通过 → trace 反查能看到引用链
- **方向 SoT**: `docs/Furnace Next Direction Post-P4.md` §D-3
- **设计核心**:
  - 选 unit-test-level 端到端而不是 byte-frozen acceptance fixture：金丹 chain 涉及 ask/promote/start/distill/finalize/promote 多步，每步生成 candidate / receipts / runtime-history，用 byte golden 容易脆弱；unit test 直接断言 schema 字段更稳
  - 新增 `AlchemyStage3CompoundingTests` 类，单测 `test_stage3_new_elixir_compounds_old_and_traces_back`
  - flow: corpus-A 提问 → promote → settle elixir-old；corpus-B 提问 → promote → start elixir-new (`include_elixir_ids=[elixir-old]`) → distill (再次显式 include) → finalize → promote
  - 断言矩阵：(1) start 后 candidate frontmatter `derived_from` 同时含 `wiki/elixirs/<old>.md` + `wiki/derived/...` anchor；(2) settled frontmatter 同样保留两类 anchor；(3) promote receipt clean，bundle 含 `counter_evidence` + `primary_path_sha256` + `secondary_path_sha256`；(4) `aiwiki.trace.resolve_trace(elixir_new, direction="up", depth=3)` 能在 parents 中看到 elixir_old
- **Stop Lines**: 0 src 改动；不改 elixir schema；不放松 DAG / anchor / counter_evidence gate；不引入 acceptance byte-golden
- **指标**: `bash scripts/verify.sh` pass（1562 → 1563 unit / 13 acceptance / 92% coverage / `--fail-under=92` gate）
- **下一步**: D-4 Investing Dogfood Plan contract-only 文档
