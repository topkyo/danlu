# Round 60 — Documentation Sync + Runtime Operations Manual + NV NIM Default Update

status: 完成
commit: 

Round 60 — Documentation Sync + Runtime Operations Manual + NV NIM Default Update — 完成
- **目的**: Round 59 后多处事实漂移积累；本轮把代码、README、方向文档、dogfood plan 全部对齐到现在的运行事实，并新增运行机制 / fallback 操作手册作为长期 SoT
- **方向 SoT**: 用户在线指令（key 已保存如何文档化 / 运行机制是什么 / 文档梳理）
- **已识别漂移点 + 修订**:
  - `src/aiwiki/config.py:16` `DEFAULT_NVIDIA_NIM_MODEL=moonshotai/kimi-k2.5` → `openai/gpt-oss-120b`（kimi-k2.5 已 4-30 EOL，120b 是 NIM 实测唯一 compatible 模型）
  - `tests/test_vault.py:127` 默认 model assertion 同步
  - `README.md` LLM 后端段落：默认 codex 5.4 → 5.5；默认 NIM kimi-k2.5 → openai/gpt-oss-120b；fallback chain 例子从 GLM/MiniMax 改为可用 model；新增"本地凭据存放规范"段（落 `~/.aiwiki-secrets/<provider>.env` mode 600 / dir 700 / repo 外），明确不入 .envrc.dogfood 或任何 git-tracked 文件；当前 backend 状态实测结论从 P4-1 时代更新到 2026-05-01
  - `docs/Furnace Next Direction Post-P4.md` 加 §3.1 D 系列实际收口（D-1 ~ D-4 + R1 + R3 + P4-INV-1/2/3/4 全部 done，引用 7 个 commit）
  - `docs/Furnace Investing Dogfood Plan.md` status 从 `pending(blocked-on-llm)` → `closed-with-v0-and-v1-receipts`；加 §8 实跑历史 receipt index（v0 / v1 / v2 候选）
- **新增文档**：`docs/Furnace Runtime Operations.md`（300+ 行操作手册）
  - §1 总览：watcher（5s deterministic-only daemon）+ nightly（daily timer + auto_apply_light=1）+ 显式 LLM-backed worker 三层模型
  - §2 systemd 单元详解：unit / env / 启停状态查询
  - §3 受控 LLM-backed worker 入口（run-compile / run-ask / run-nightly / run-lint）+ preflight backend_compat receipt
  - §4 LLM Backend 选择策略（2026-05-01 实测矩阵）
  - §5 NV NIM Fallback 操作手册：临时切 / nightly drop-in 配置 / 切回 / 同 backend 多 model fallback chain
  - §6 监听排障速查表
  - §7 与 deterministic baseline 不变量的关系（"出门旅行没网 → watcher 仍能 deterministic compile"）
- **运行机制现状摸清（写入新 Runtime Ops 手册）**:
  - watcher PID 3489140 active 自 2026-05-01 08:16:02 CST，34 分钟无重启，跑 `aiwiki watch --interval 5 --compile-limit 5 --deterministic-only`
  - nightly timer next trigger Sat 2026-05-02 00:00:00 CST，Persistent=true 错过补跑
  - watcher env：`AIWIKI_LLM_BACKEND=codex-cli` / `gpt-5.5` / `AIWIKI_VAULT=/home/tim/danlu/炼丹炉` / deterministic_only=1
  - nightly env：同上 + `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1`（light lane 自动 apply 已默认开启 Round 38 起）
  - 凭据：`~/.aiwiki-secrets/nvidia.env`（mode 600 / dir 700）保存 NV NIM key，不进 git；systemd 切 NV 用 `aiwiki-nightly.service.d/nvidia-fallback.conf` drop-in（操作步骤见 Runtime Ops §5.4）
- **Tests**: `tests/test_vault.py:127` 默认 model assertion 改 `openai/gpt-oss-120b`；其他 explicit-model 测试（`tests/test_llm.py` / `tests/test_runner.py` 用 kimi-k2.5）保留作为 backend chain 行为覆盖
- **指标**: clean-env verify 1571 unit + 13 acceptance / 92% coverage / `--fail-under=92` gate / `All checks passed!`
- **Stop Lines**: 0 review/apply/revert 状态机改动；NV key 完全不入 git；不破坏 9+ feasibility contract（仍然不做 cross-backend 自动 routing）；historical Direction P0-P3.md / P4.md 保留不动作为历史参考
