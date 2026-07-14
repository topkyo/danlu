---
title: "炼丹炉 Residual Clearance Plan"
kind: "plan"
status: "executed-reviewed-pass"
updated_at: 2026-07-14
parent: "docs/Furnace Cleanup Commercial Audit Plan 2026-07.md"
---

# Residual Clearance Plan（2026-07）

承接 Cleanup Plan residual：C1/C2 单 seam、真实 Demo Pack、移动端 companion。  
**C4 14/30-day natural proof 仍不伪造**，本轮只提供探测命令与 not-yet 口径。  
纯 facade 一次清除在本 PR 执行；CLI primary surface 已合入 `investing-research`。禁止再开“半迁移 facade”条目。

## Goal

1. C1/C2：各做一个**有测试边界的单 seam**，禁止 broad rewrite。
2. C3：交付可打开的脱敏 Demo Pack vault fixture + 截图/视频脚本。
3. C5：落地 `RuntimeClient` 抽象、`VaultQueueClient`、desktop drain；companion 薄路径（Desktop-only 主插件不变）。
4. ~~facade 再迁一批（可选）~~ → **superseded**：按 `AGENTS.md` 一次清除，不做半迁移。

## Out

- 不伪造 14/30-day PASS
- 不做 iOS 商店发布包
- 不拆整个 alchemy/drop/graph
- 不扩 L3 自治

## Tasks

- [x] R-C1：从 `execution/alchemy.py` 或 `runner/alchemy.py` 抽出一个纯 helper seam + tests
- [x] R-C2：从 `drop.py` 抽出一个纯 helper seam + tests
- [x] R-DEMO：`demos/investing-demo-pack/` 脱敏 vault + scripts + Spec 升级为 delivered-fixture
- [x] R-MOBILE：`RuntimeClient` / DesktopLauncher / VaultQueue + Python drain + tests
- [x] R-DOCS：更新 Cleanup Plan residual、docs/README、M-MOBILE 勾选
- [x] R-C4：maturity long-window probe 脚本（只报告 not-yet / pass，不伪造）
- [x] verify + independent review + merge to `investing-research`

## Verify

```bash
bash scripts/verify.sh scripts
bash scripts/verify.sh python-static
bash scripts/verify.sh product-shell-static
PYTHONPATH=src python3 -m pytest tests/test_alchemy.py tests/test_drop.py tests/test_vault_queue.py -q --tb=line
cd .obsidian/plugins/furnace-product-shell && npm test -- --testPathPattern='runtime-client|vault-queue' 
```


## Residual honesty

- C4 14/30-day：`scripts/long_window_proof_probe.py` 只探测；demo vault 当前 `not-yet`。
- M-MOBILE-3：vault-queue settings mode = thin companion path；非独立 iOS 插件包。
- M-MOBILE-4：商业包装文案已写入 Demo Pack / RuntimeClient docs。

## Follow-up completed

- 纯 facade 一次清除：已执行（删除 `app.py` / `app_content` / `app_render` / `app_surfaces` / `app_memory_surfaces`；owner 直引）。
- CLI primary surface：顶层只注册 `drop/today/metrics/advanced`；旧顶层 rewrite compat。
