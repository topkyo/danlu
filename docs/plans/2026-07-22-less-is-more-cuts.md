# Less-is-More Cuts Implementation Plan

> **For agentic workers:** Load `executing-plans`. Then `finishing`.

**Goal:** 执行 `docs/archive/Furnace Less-is-More Reassessment 2026-07-22.md` 的 P0 + 选定 P1，把用户/配置表面积再砍一刀。  
**Source:** Less-is-More 复评 Cut 优先序  
**Out:** 不为 Less 拆 hub；不重排全部 `advanced` 21 叶；不改 AGENTS facade 长文（P2 另开）。

---

## Task 1: Sync ask 成功直写 done

**Depends on:** none  
**Files:** `render_input.js`, `render_today.js` (retry), `plugin_actions.js` if needed, Jest

- [x] Ask 成功且 payload 有 `report_path`（或等价 outputs 路径）→ `markPendingSubmissionDone(id, "outputs", path)`，**不再** `markPendingSubmissionReceived`
- [x] 失败仍 `markPendingSubmissionFailed`；无 path 的成功可 retained received 或 failed-with-hint（优先 done-or-fail，避免幽灵 received）
- [x] 重试成功同样直写 done
- [x] 更新 Jest：成功路径期望 `markPendingSubmissionDone`，不期望 received
- [x] **Verify:** `bash scripts/verify.sh product-shell-static`

## Task 2: Pending 去戏（假进度 / 双层提示）

**Depends on:** Task 1（同 Shell 文件，串行或同一 agent）  
**Files:** `render_today.js`, `constants.js`, Jest

- [x] 删除或不再渲染时间驱动的假 `renderPendingProgressSteps`（running 只留一句静态等待）
- [x] 15s 软提示与静态文案合并为不叠两层（二选一：软提示替换状态句，或去掉软提示只留静态）
- [x] 用户可见文案不再强调 `backgroundStatus`
- [x] **Verify:** `bash scripts/verify.sh product-shell-static`

## Task 3: Today 默认 = 报告列表

**Depends on:** none（可与 Task 1 并行若文件冲突则串 Task 2 后）  
**Files:** `today_feed.js`, `render_today.js`, `render/cards.js` 若需, Jest

- [x] 默认 **不** 把 `compound_suggest` 打进主 Today 分组（或设置默认隐藏；无新 settings 则直接不渲染主栏）
- [x] done pending 卡与 Today 报告去重/折叠（同 path 只显示一处）
- [x] **Verify:** `bash scripts/verify.sh product-shell-static`

## Task 4: 清 no-op nightly / auto_adopt 配置面

**Depends on:** none  
**Files:** `autonomy_policy.py`, installer/docs 若引用, 相关测试

- [x] 删除或停止暴露 **unused** `AIWIKI_NIGHTLY_AUTO_*` / `auto_adopt_*` 读写（保留读旧 state JSON 的兼容默认，但不再文档化/installer 写入）
- [x] 不恢复 `runner.auto_adopt`
- [x] **Verify:** `bash scripts/verify.sh python-static acceptance`

## Task 5: 收口文档 + 总闸

**Depends on:** Task 1–4

- [x] `PROGRESS.md` 记一笔；勾选本 plan
- [x] rebuild `main.js`；同步 dogfood vault plugin（若本机 vault 可写）
- [x] **Final:** `bash scripts/verify.sh all`

## Deferred（本轮不做）

- advanced 21 叶收子树
- hub LOC 大拆 / `app_linting` rename
- AGENTS/PROGRESS Round 长尾大砍
- Scorecard Active 表合并（可跟 Task 5 轻触，非必须）
