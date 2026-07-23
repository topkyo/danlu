# Chat 入口 + 一问一报告 + 金丹链

**Date:** 2026-07-23  
**Status:** Approved (chat)  
**Owner:** Product Shell + ask runtime（第一刀）；金丹链不变  
**Related:**  
- `docs/specs/2026-07-23-dogfood-p0-sticky-and-honest-media.md`（Slice 1 已落地基础）  
- `docs/specs/2026-07-22-ask-sync-chat.md`  
- `docs/Furnace Product Shell.md`  
- `docs/commercial/COMPARE.md`  
- `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md`（Commercial Go-Live 仍为主线）

## Goal

把 Product Shell 的对话体验收成明确产品边界：

- **入口像 ChatGPT**（单框、可带材料、可追问、可再发）。
- **产出永远是一问一报告**（`output/reports/*.md` + Today 卡片；气泡只做进度/摘要）。
- **长期价值走金丹链**（file-back → alchemy；对话记录不是 SoT）。

本 spec 批准方向与第一刀切片；不把产品叙事改写成「Obsidian 版 ChatGPT」，也不开 Agent CLI 功能大包。

## Constraints

1. 五层分层不变：`raw/` 唯一事实输入；对话产出不得当 SoT。
2. Ask 保持同步单飞；不恢复 `run-ask-submit` / resume / background jobs。
3. `@` / 材料引用 = 显式 path → `material_refs`；禁止 heavy RAG / 向量全库检索。
4. 再生成 / 编辑再发 = 新 `run-ask` + 新报告 + 新 receipt；不覆盖旧报告。
5. 不扩 `shell-summary` 契约字段；不把 Shell 做成 Agent IDE（工具步进默认 UI）。
6. 不替代 Commercial Go-Live 主线；本方向是 dogfood 入口补强。

## Decisions

1. **产品边界 = 方案 ①**（用户确认）：入口像 ChatGPT；产出一问一报告 + 金丹链；不做多轮全文线程当 prompt 上下文，也不做 Cursor/Agent CLI 对齐。
2. **ChatGPT 隐喻只映射交互层**，系统语义按下表：

| ChatGPT 预期 | 炼丹炉等价物 |
|--------------|--------------|
| 发一条消息 | 一次 `run-ask`（或 drop→ask） |
| 气泡里的答案 | `output/reports/*.md` + Today 卡片 |
| @文件 | 显式 `material_refs`（可 sticky） |
| 重新提问 | 新 `run-ask` + 新报告 + 新 receipt |
| Memory | `wiki/judgments/` + `wiki/elixirs/`（须 file-back / alchemy） |

3. **第一刀只做三件事**（顺序 1→2→3）：追问不断档 → Composer `@`/选文件 → 编辑再发/再生成。
4. **对外叙事**（销售/README/Demo 开场）：  
   「在 Obsidian 里把散落资料炼成可追溯的判断资产：投料、提问、出报告；金丹可审计、可回滚，不是聊完即忘的 vault chat。」
5. **对内三不做**：① 对话记录不当 SoT、不恢复 background/多 tab 并行 ask；② 不做 chat memory、Agent 工具步进默认 UI、heavy RAG；③ Go-Live 未收口前不开 Agent CLI 功能包叙事。

## Design

### Architecture

```text
Universal Input（像 ChatGPT 的入口）
        │
        ├─ drop / @path / sticky materials → material_refs
        └─ question → run-ask（同步单飞）
                │
                ▼
        output/reports/<new>.md  + receipt
                │
                ▼
        Today Feed（打开报告 / 引用追问 / 沉淀 / 凝丹）
                │
                ├─ file-back → wiki/judgments/
                └─ alchemy-* → wiki/elixirs/
```

对话气泡与 pending 流只服务「进行中 + 摘要 + 重试入口」；**交付物始终是报告文件**。

### Components（第一刀）

| Priority | Slice | Change surface | Done when |
|----------|-------|----------------|-----------|
| **1** | 追问不断档 | 巩固 `stickyMaterialRefs` + `引用报告：…`；composer/气泡可见「本轮材料」 | 追问无显式材料时仍带 sticky；用户能看见本轮 paths；无可读材料时诚实短答 |
| **2** | Composer `@` / 选文件 | Universal Input：`@` 或 picker → 附件 pill → `material_refs` | 可引用：当前打开文件、`wiki/sources|judgments`、`output/reports`、vault 内 `.md/.txt`；走现有 ask 路由 |
| **3** | 编辑再发 / 再生成 | 气泡动作：编辑问题、成功后再生成 | 每次新 `run-ask`、新报告、新 receipt；failed/degraded 继续现有重试 |

### Data flow

1. 用户在 composer 输入问题，可选 `@`/拖拽/sticky 材料。
2. Shell 解析为 `question` + `material_refs`（显式优先于 sticky；显式集合替换 sticky，规则继承 dogfood P0 spec）。
3. `run-ask` 同步执行；成功写 `output/reports/*.md`；失败/降级写诚实状态，不伪装成功。
4. Today / 气泡展示摘要与「打开报告」「引用此报告追问」；沉淀/凝丹仍走现有报告卡动作，不进聊天框隐式写 wiki。

### Error handling

- 有 `material_refs` 但无可读上下文 → 诚实短答（已有 P0 契约）。
- Ask 进行中拒绝新 ask（单飞）；drop 仍可并行。
- 再生成失败 → 保留旧报告；新 pending 标 failed/degraded，可重试。
- `@` 指向不存在或 vault 外路径 → fail-loud，不静默忽略。

### Testing

- Shell Jest：sticky 可见性、`@` → material_refs、编辑再发/再生成触发新 ask（不覆盖旧 pending id 规则沿用 `excludePendingId`）。
- llm-integration / acceptance：仅在 runtime 契约变化时补测；纯 UI 切片不强制扩 acceptance fixture 数。
- Dogfood：真实 vault 一条路径「投料 → 追问 → @ 换材料 → 再生成 → 打开报告」。

## Out of scope

- 多轮全文 chat history 作为 LLM 主上下文（corpus 复利排名除外，保持现有 runtime）。
- 消息分叉树、并行多会话、流式 token UI。
- Vision / OCR 多模态理解。
- Chat 导出 JSON、chat memory、自定义 per-thread system prompt 面板。
- 恢复 background ask；扩大 `advanced` 默认面。
- 将 Commercial Go-Live（EULA/PyPI/Demo 媒体/WS6）替换为本方向主线。

## Open questions

(none — 边界 ①、§2 三刀、§3 非目标与叙事均已在 chat 确认)

## Implementation note

批准本 spec 后，下一文档应为 `docs/plans/2026-07-23-chat-entry-report-elixir.md`（writing-plans），按 Slice 1→2→3 拆任务；**未批准 plan 前不写代码**。
