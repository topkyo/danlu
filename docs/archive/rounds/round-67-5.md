# Round 67.5 — Acceptance fixture prompt_hash refresh

status: 完成
commit: 284f8af

Round 67.5 — Acceptance fixture prompt_hash refresh — 完成
- **目的**: 修复 R67 期间发现的 M6.1b acceptance fixture `prompt_hash` drift；该 drift 与 R67 代码改动无关，源于 prompt 历史漂移。
- **修复内容**: 刷新 3 个 M6.1b fixture `prompt_hash`，保持 expected goldens 语义不变。
- **dev tool**: `scripts/refresh_acceptance_fixture.py`（144 行），复用 `CapturingBackend` 与 `compute_prompt_hash`。
- **helper 提取**: `tests/acceptance/case_runner.py`。
- **文档**: `tests/fixtures/acceptance/M6.1b/README.md` 记录刷新方法与边界。
- **验证**: 13 acceptance passed；`bash scripts/verify.sh` all green；coverage 92%；oracle isolated qa-review PASS（零 finding）。
- **Stop Lines**: 0 prompt builder / 0 ReplayBackend / 0 compute_prompt_hash / 0 expected goldens / 0 installer defaults。
