---
title: "炼丹炉下一步执行计划"
kind: "execution-plan"
status: "active"
owner: "tim"
created_at: "2026-04-27"
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
  - docs/Furnace Product Shell.md
---

# 炼丹炉下一步执行计划

本文档记录 2026-04-27 评估后的后续执行入口。以后继续推进炼丹炉时，默认先按本文档执行；若本文档与更高层 SoT 冲突，以 `Furnace Agent Architecture.md`、`Furnace Evolution Mechanics.md` 和 `Furnace Product Shell.md` 为准。

## 当前判断

炼丹炉已经具备扎实的 local-first agent runtime / OS kernel：五层文件平面、judgment / decision、protocol-learning、elixir、planner-log、lane、receipt、audit 和 Product Shell 都已经形成可验证闭环。

但它还不是完整意义上的“知识复利并自主进化的 Agent OS 产品”。当前更准确的定位是：

> **受控自主的知识复利 runtime + 本地控制面，正在向单输入 / 单输出的 Agent OS 产品收敛。**

主要缺口不在单个 primitive，而在四件事：

- 用户面还没有完全收敛为真正的 universal input + single Today feed。
- 自主进化仍以 proposal / explicit apply / human gate 为主，不默认生成或接受语义判断。
- 缺少一套可重复演示的 deterministic end-to-end acceptance pack。
- 缺少衡量“知识是否复利”的运行指标。

## 下一阶段主线

### M6.1 Deterministic Loop Acceptance Pack

目标：定义并实现一个不依赖 LLM、不依赖外部服务、可重复跑通的 runtime acceptance baseline。

这里的“不依赖 LLM”不是产品上限，也不是说炼丹炉最终应避免使用 GPT / Claude。它只限定 M6.1 的验收基线：先证明 `raw -> wiki -> output -> review/apply -> receipt/audit -> today` 这条 OS 内核链路在没有模型、网络、API key、额度和模型版本漂移时也能稳定成立。

真正的产品黄金闭环必须使用 LLM。GPT / Claude / 其他显式选择的 backend 应用于语义提炼、判断生成、复盘、重写、金丹演化和自主建议。LLM golden loop 应建立在 M6.1 deterministic baseline 之上，而不是替代它。

推荐闭环：

```text
drop -> compile -> today -> review/apply -> receipt/audit -> today
```

验收标准：

- 从一个固定 fixture vault 或 fixture workspace 开始。
- 投入一份 raw material 后，能确定性生成 source / concept / output 或 review item。
- `aiwiki today` 能显示用户应该看的输出和应该拍板的事项。
- 至少一个低风险 review/apply 路径能产生 receipt 和 universal audit record。
- 再次运行同一 pack 时保持幂等，不重复制造无意义结果。
- `bash scripts/verify.sh` 保持通过。

非目标：

- 不引入 LLM 语义生成。
- 不启用 hidden backend / hidden model fallback。
- 不改动 hosted service、multi-user sync、heavy RAG、fine-tuning 等非目标边界。
- 不自动接受 L3 / judge / semantic proposal。

建议产物：

- `tests/fixtures/acceptance/`：最小黄金闭环输入。
- `tests/test_acceptance_loop.py`：fixture-driven CLI acceptance tests。
- `scripts/run_acceptance.sh`：本地一键验收入口，可被 `scripts/verify.sh` 或 harness gate 调用。
- `output/control/` 或 `.aiwiki/state/` 中的 receipt / audit 断言样例。

### M6.1b LLM Golden Loop

目标：在 M6.1 deterministic baseline 通过后，用真实 LLM backend 跑通用户可感知的炼丹炉产品黄金闭环。

推荐闭环：

```text
universal input -> LLM distill/judge/rewrite -> today -> human decision -> apply -> receipt/audit -> learning/evolution -> today
```

验收标准：

- backend 必须由用户或配置显式选择，不允许 hidden fallback。
- LLM 输出必须保留 provenance、prompt / backend / model metadata 和可审计 receipt。
- L3 / judge / semantic proposal 默认只进入 review，不自动接受。
- 同一输入至少能产生一个用户可理解的 output、一个需要拍板的 decision，或一个可回滚的建议动作。
- `aiwiki today` 与 Product Shell Today feed 都能展示该闭环结果。
- 失败时能明确区分 runtime failure、backend failure、schema failure 和 semantic quality failure。

非目标：

- 不把 LLM 输出直接写成不可追溯事实。
- 不把模型供应商能力当作 OS 内核正确性的证明。
- 不绕过 review / apply / revert / audit。

## 后续阶段顺序

1. **M6.1 Deterministic Loop Acceptance Pack**
   - 先证明炼丹炉不靠 LLM 也能跑完一个 runtime acceptance baseline。
   - 这是后续 UX / autonomy / metrics 的共同基线。

2. **M6.1b LLM Golden Loop**
   - 在 M6.1 通过后，用 GPT / Claude / 其他显式 backend 验证真实炼丹产品体验。
   - 这是“智能价值”验收，不替代 deterministic baseline。

3. **M6.2 Universal Input**
   - 把 AskBox 与 DropZone 收敛成一个用户心智入口。
   - 用户输入 URL / PDF / image / repo / note / question 时，不需要先选择命令类型。
   - Product Shell 可保留高级按钮，但默认路径必须是一个输入框。

4. **M6.3 Single Today Feed**
   - 把 reports、needs decision、review、elixir、suggested actions 收敛成一个 Today feed。
   - Advanced 继续保留运维面板，但首屏不暴露 receipt / audit / lane / planner / signal 等机制词。
   - `aiwiki today` 与 Product Shell Today feed 共享同一 shell-facing contract 或同一排序策略。

5. **M6.4 Knowledge Compounding Metrics**
   - 增加可解释指标：provenance completeness、review closure rate、stale ratio、proposal acceptance rate、judgment revisit rate、output file-back rate、elixir reuse count。
   - 指标先用于本地报告，不作为自动调度硬门槛。

6. **M6.5 Product Shell UI Smoke Tests**
   - 增加真实 UI 层验证，至少覆盖首屏空状态、长文本、移动宽度、Advanced 折叠和主要按钮存在性。
   - 若不引入浏览器自动化，至少保留 DOM/string-level contract tests，避免首屏退化为 dashboard。

7. **M6.6 Module Size Reduction**
   - 继续拆 `render.js`、`plugin.js`、`app_shell.py`、`runner/alchemy.py` 等大模块。
   - 每次拆分只移动 ownership，不改 JSON schema、receipt schema、ShellSummary 字段和 CLI stdout contract。

## Stop Lines

任一触发即停止并重新写 contract：

- 需要调用真实外部 LLM 或 webhook 才能完成 M6.1 deterministic acceptance。
- 需要引入 hosted service、multi-user sync、数据库服务、向量库或 fine-tuning。
- 需要自动接受或自动写入语义判断内容。
- 需要改变 `raw/ -> wiki/ -> output/` 分层事实。
- 需要破坏 existing CLI compatibility 或删除 Advanced 入口。
- 需要修改 receipt / audit / ShellSummary schema，但没有明确迁移策略。

## 执行方式

默认每个 milestone 都按以下流程：

```text
读 SoT -> 写/更新 .codex/contracts/active.md -> 小步实现 -> focused tests -> bash scripts/verify.sh -> closed_loop -> 回写 PROGRESS.md -> 本地 commit
```

以后继续闭环开发炼丹炉时，默认以本文档作为下一步执行入口。除非用户明确改目标，后续任务先执行本文档中最靠前且尚未完成的 milestone，并把该 milestone 物化为 `.codex/contracts/active.md` 后再开始改代码。

M6.1 开始时，先把本文档中的 M6.1 物化为 `.codex/contracts/active.md`，再开始改代码。M6.1 通过后，优先进入 M6.1b，而不是直接做 UI 收敛。

## 当前验证基线

- `bash scripts/verify.sh`：1160 tests / 93% coverage / pass。
- Product Shell build：`bash .obsidian/plugins/furnace-product-shell/build.sh` pass。
- Product Shell syntax：`node --check .obsidian/plugins/furnace-product-shell/main.js` pass。
- 分支同步状态以 `git status --short --branch` 为准，不作为验收条件。
