# Round 57 R4 — P4-INV-2 filter quarter tokens

status: 完成
commit: 8bd33f5

Round 57 R4 P4-INV-2 — filter quarter tokens — 完成（commit 8bd33f5）
- **目的**: 修复 dogfood-receipt-investing-v0 §F-INV-5 — NVDA note 抽出 `2025q4` 作为 concept 噪声
- **修**: `app_utils.tokenize` + `content/concepts.concept_candidates` 加 `_QUARTER_TAG_PATTERN` 过滤 `YYYYqN / qNYYYY`；`CONCEPT_NOISE_FLOOR_VERSION` 6 → 7 触发 cache 失效
- **测试**: `test_concept_noise_floor.py` 加 2 case；clean-env verify 1563 unit + 13 acceptance pass
