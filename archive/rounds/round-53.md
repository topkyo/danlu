# Round 53 — D-1/D-2 Direction SoT + Archive Sweep

status: 完成
commit: 

Round 53 — D-1/D-2 Direction SoT + Archive Sweep — 完成
- **目的**: 基于 Round 52 收口后的全量 SoT 复盘，把"下一阶段方向"固化为 SoT；同时收口 PROGRESS / `.codex/plans/active.md` 旧世代的体量污染，让 active 文件回到健康规模
- **方向 SoT**: `docs/Furnace Next Direction Post-P4.md`（本轮落地）
- **D-1 Direction SoT 落地**:
  - 写 `docs/Furnace Next Direction Post-P4.md`，承接 Round 52 + P4-15 收口后的剩余 gap
  - 二次校准纠错：初评把 P0/P1/P3/P4-1~15 误列为 gap；实测后确认这些已落地（line 1253 P0 / line 1235 P1 / line 1209 P3 / line 1184 P4-1）
  - 真实剩余 gap 收敛为：D-3 Stage-3 Compounding acceptance + D-4 Investing dogfood plan + 长尾 (Signal routing density / 外部 LLM)
  - 文件大小：~9KB；引用关系：补丁 `docs/archive/Furnace Next Direction P0-P3.md` + `docs/archive/Furnace Next Direction P4.md`
- **D-2 Archive Sweep 落地**:
  - `PROGRESS.md`: 2331 行 → 1209 行；切出 1130 行（pre-Round 1 / pre-P4 内容含 M0-M9 / M-PS / M-UX / M6 / P0~P3 / M7 / 9-Standard Closure）到 `archive/PROGRESS-pre-round1.md`
  - `.codex/plans/active.md`: 6013 行 → 1550 行；切出 4394 行（EP-001~021 / EP-PLAN-001 / Furnace M0-M5 / 9-Standard Closure M9-Px）到 `.codex/plans/archive/pre-furnace-and-furnace-rollout.md`
  - 两文件顶部加 archive header pointer，git 历史仍是不可抹除审计源
- **验证**: 干净 env `env -i HOME=$HOME PATH=$PATH LANG=C.UTF-8 bash scripts/verify.sh` pass（1562 unit + 13 acceptance / 92% coverage / `--fail-under=92` gate）
- **副作用确认**: D-2 archive 不破坏既有 reference；3 个 verify failure 仅在污染 env 下出现（pre-existing baseline issue, 与 D-2 无关）
- **Stop Lines**: 0 src 改动；不动 git history；不删旧 EP 文件，只是物理切档；不破坏 9+ feasibility contract
- **下一步**: D-3 Elixir Stage-3 Compounding acceptance fixture（next contract）、D-4 Investing Dogfood Plan contract-only 文档
