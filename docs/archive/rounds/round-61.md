# Round 61 — Nightly NV NIM Auto Fallback + Docs Archive Sweep

status: 完成
commit: 

Round 61 — Nightly NV NIM Auto Fallback + Docs Archive Sweep — 完成
- **目的**: 按用户指令把 NV NIM 从手动 fallback 升级为 nightly unattended fallback；同时清理 active docs 根目录，把过时方向/评估文档归档，并 push 当前分支
- **方向 SoT**: 用户在线指令（"把 NV NIM 装到 nightly 自动跑 fallback；梳理文档后哪些过时或不用的文档做清理或归档；然后 push"）+ `.codex/contracts/active.md`
- **nightly fallback 实现**:
  - `scripts/run_nightly.sh` 改为 wrapper 决策：primary `run-nightly` 成功则退出；primary 失败或未配置时，若 `AIWIKI_NIGHTLY_FALLBACK_ENABLED=1`，source `AIWIKI_NIGHTLY_FALLBACK_ENV`，切到 `nvidia-nim-api/openai/gpt-oss-120b` 重跑；fallback 也不可用时最终跑 deterministic `nightly`
  - fallback 只存在于 nightly wrapper；不改 `LLMConfig`，普通 CLI/runtime 仍保持显式 backend 选择、不做 hidden routing
  - `scripts/install_user_service.sh` 对新旧 `~/.config/aiwiki/aiwiki-nightly.env` 补齐 `AIWIKI_NIGHTLY_FALLBACK_*`，只写 repo 外 key 路径，不写 key
  - 顺手修正 `run_watch.sh` / `run_nightly.sh` 的 `PYTHONPATH` 前置逻辑，避免外部 ROS 等已有 `PYTHONPATH` 时找不到 `aiwiki`
- **本机 systemd 更新**:
  - 已执行 `bash scripts/install_user_service.sh`
  - 当前 nightly env：primary `codex-cli/gpt-5.5` + `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1` + fallback `nvidia-nim-api/openai/gpt-oss-120b` + `AIWIKI_NIGHTLY_FALLBACK_ENV=/home/tim/.aiwiki-secrets/nvidia.env`
  - `LLMConfig.status_from_env()` 验证 fallback configured=True / key present=True（未打印 key）
  - `aiwiki-nightly.timer` enabled+active，next trigger Sat 2026-05-02 00:00:00 CST
- **文档清理 / 归档**:
  - `docs/README.md` 改为 active SoT 索引：Agent Architecture / Evolution Mechanics / Product Shell / Runtime Operations / Next Direction Post-P4 / Investing Dogfood / Market Scan / Elixir
  - 新增 `docs/archive/README.md`
  - 归档：`docs/archive/Furnace Next Direction P0-P3.md`、`docs/archive/Furnace Next Direction P4.md`、`docs/archive/Furnace Product UX Assessment.md`
  - `README.md` 与 `docs/Furnace Runtime Operations.md` 更新 nightly fallback 语义；active docs 中旧路径引用已改到 archive
- **Tests**:
  - focused: `PYTHONPATH=src python3 -m unittest tests.test_app.AiwikiFlowTests.test_run_watch_script_uses_root_relative_paths tests.test_app.AiwikiFlowTests.test_run_nightly_script_uses_root_relative_paths tests.test_app.AiwikiFlowTests.test_run_nightly_script_retries_nim_fallback_before_deterministic`
  - `python3 -m ruff check src tests`
  - `bash scripts/verify.sh`: 1572 unit + 13 acceptance / 92% coverage / `All checks passed!`
- **Stop Lines**: 0 review/apply/revert 状态机改动；0 NV key 入 git；0 core runtime backend routing 语义改动；文档仅归档不删除历史
