# Chat Entry → Report → Elixir Implementation Plan

> **For agentic workers:** Load `executing-plans` (3 tasks). Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** 在「入口像 ChatGPT、产出一问一报告 + 金丹链」边界下，落地第一刀三切片：材料可见 → `@`/选文件 → 编辑再发/再生成。  
**Spec:** `docs/specs/2026-07-23-chat-entry-report-elixir.md`  
**Architecture:** Shell-only UX 增强；继续走同步 `run-ask` + `material_refs` / `stickyMaterialRefs`；交付物仍是 `output/reports/*.md`；不改 runtime 五层、不恢复 background ask、不引入 RAG。  
**Tech stack:** Product Shell JS + Jest；`bash scripts/verify.sh product-shell-static`（per-task）；Final：`bash scripts/verify.sh product-shell-static` + `bash scripts/sync_product_shell_to_vault.sh`（若本机 vault 需同步）

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `.obsidian/plugins/furnace-product-shell/src/helpers.js` | modify | sticky/explicit 材料展示 helpers；`@` token 解析；vault-relative path normalize |
| `.obsidian/plugins/furnace-product-shell/src/render_input.js` | modify | composer 材料条（sticky+附件）；`@` 补全/选文件；提交时把 vault path 写入 ask materials |
| `.obsidian/plugins/furnace-product-shell/src/render_today.js` | modify | done 气泡：本轮材料 chips；「编辑问题」「再生成」；保留 failed/degraded「重试」 |
| `.obsidian/plugins/furnace-product-shell/src/plugin_actions.js` | modify | ask 入口接受显式 vault `materialPaths`；`@`/picker 路径写 sticky（`source: "explicit-@"`） |
| `.obsidian/plugins/furnace-product-shell/src/plugin_lifecycle.js` | modify | 若需：quote / 打开 composer 预填问题共用 helper |
| `.obsidian/plugins/furnace-product-shell/src/constants.js` | modify | i18n：本轮材料 / 编辑问题 / 再生成 / `@` 空结果等 |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/helpers/sticky-materials.test.js` | modify | 展示/解析 helpers |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/render/universal-input-interaction.test.js` | modify | `@`、材料条、编辑/再生成交互 |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/render/`（新文件可选） | create | 若 interaction 文件过大，拆 `composer-at-mention.test.js` / `bubble-regenerate.test.js` |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | `bash scripts/build.sh` 或现有 product-shell build 入口 |
| `PROGRESS.md` | modify | 记一笔第一刀进度 |
| `docs/Furnace Product Shell.md` | modify | §0/Universal Input 补一句：入口像 chat，产出仍是报告（不扩 schema） |

**Runtime Python：** 本 plan 默认不改；诚实降级已在 dogfood P0。仅当 Task 2 发现 CLI 无法接受 vault 相对 path 作为 material 时，才允许最小补丁 `workflows_ask*` —— 实现前先 `rg material_refs` 确认，能复用则不改。

---

## Task 1: 本轮材料可见（追问不断档 UI）

**Depends on:** none（sticky 注入已在 dogfood P0；本任务只做可见性 + 测试加固）

**Files:**
- Modify: `helpers.js`, `render_input.js`, `render_today.js`, `constants.js`
- Test: `sticky-materials.test.js`, `universal-input-interaction.test.js`

- [ ] **Step 1:** 在 `helpers.js` 增加展示用 helper（不改 sticky 写入语义）：

```js
function stickyMaterialDisplayPaths(settings) {
  return normalizeStickyMaterialRefs(settings && settings.stickyMaterialRefs).paths;
}

function formatMaterialChipLabel(path) {
  const p = String(path || "").replace(/\\/g, "/");
  const parts = p.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : p;
}
```

- [ ] **Step 2:** `renderUniversalInput`：在 attachments 容器上方或同区增加 `furnace-input-sticky-materials` 条：
  - sticky paths 非空时显示 chips（文件名 + 完整 path 作 `title`）
  - 每 chip 可 × 移除：从 sticky.paths 删该 path 并 `setStickyMaterialRefs` + `savePluginState`
  - 文案用 i18n：`"本轮材料（追问仍会带上）"` / `"Sticky materials (used on follow-up)"`
  - **不**把 sticky 路径伪装成 File 附件（避免误走 drop）

- [ ] **Step 3:** `render_today.js` 用户气泡或 AI done 卡：若 `entry.retryArgs.materialPaths`（或 ask 写入的等价字段）非空，渲染一行 `furnace-bubble-materials` chips（只读）。若 pending 尚无该字段，在 `plugin_actions` ask 成功路径把本轮 `resolveAskMaterialPaths` 结果写入 `retryArgs.materialPaths`（最小字段，不扩 shell-summary）。

- [ ] **Step 4:** Jest：
  - sticky 非空 → composer 出现 chips；点 × → paths 更新
  - pending done + `retryArgs.materialPaths` → 气泡可见材料名
  - 追问无显式材料时仍走既有 `buildAutoAskQuestion`（回归 sticky-materials 测）

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — expect PASS  
- [ ] **Commit:** `feat(shell): show sticky and ask material chips in composer`

---

## Task 2: Composer `@` / 选文件 → material_refs

**Depends on:** Task 1（共用材料条 UI 与 chip helpers）

**Files:**
- Modify: `helpers.js`, `render_input.js`, `plugin_actions.js`, `constants.js`
- Test: `universal-input-interaction.test.js` 或新建 `composer-at-mention.test.js`

- [ ] **Step 1:** helpers 增加 `@` 解析（KISS，不做模糊语义检索）：

```js
function extractAtMentionQuery(text, cursor) {
  // 从 cursor 回扫：匹配最近未闭合的 @token（允许路径字符 [^\s]）
  // 返回 { start, end, query } 或 null
}

function filterVaultPathsForMention(paths, query, limit = 12) {
  const q = String(query || "").toLowerCase();
  const allow = (p) => {
    const s = String(p || "").replace(/\\/g, "/");
    if (!(s.endsWith(".md") || s.endsWith(".txt"))) return false;
    if (!(s.startsWith("wiki/sources/") || s.startsWith("wiki/judgments/")
        || s.startsWith("output/reports/") || s.startsWith("raw/"))) {
      // 仍允许「当前打开文件」即使不在以上前缀（由调用方单独 prepend）
      return false;
    }
    return !q || s.toLowerCase().includes(q);
  };
  return paths.filter(allow).slice(0, limit);
}
```

- [ ] **Step 2:** `render_input.js`：
  - 维护 `attachedVaultPaths: string[]`（与拖拽 `attachedFiles` 并列）
  - 输入 `@` 时弹出轻量 suggest（`div.furnace-at-suggest`，不用新依赖）：候选 = 当前打开文件（若有）+ vault 内允许前缀的 `.md/.txt`（通过 `plugin.app.vault.getMarkdownFiles()` 或等价 API 取 path）
  - 选中一项：从 textarea 删除 `@query`，把 path 推进 `attachedVaultPaths`，刷新 pills（复用 `furnace-input-attachment` 样式，标注为 vault 引用）
  - 另提供按钮「引用当前文件」（若 `workspace.getActiveFile()` 有值）——无 `@` 也能一键加
  - 提交时：`explicitMaterialPaths = attachedVaultPaths`；若还有拖拽文件仍走现有 drop；纯 ask + vault paths → `runAskCommand` 带 materials（见 Step 3）
  - 非法/ vault 外 path：Notice fail-loud，不静默提交

- [ ] **Step 3:** `plugin_actions.js` / ask 入口：
  - 接受 `materialPaths: string[]`（vault 相对）
  - `resolveAskMaterialPaths(explicit, sticky)`：显式非空则替换 sticky，`setStickyMaterialRefs(..., "explicit-@")`
  - 将 paths 编入 ask 问题句式：**优先复用** `buildAutoAskQuestion(question, paths)`（与 sticky 同一契约），避免新 prompt 方言
  - 实现前确认 runtime 已能读这些 path 为 material context；若仅支持 `raw/`，则 Task 2 范围收窄为 `raw/` + `output/reports/` + 当前文件拷贝进材料提示——**不得**引入 embedding

- [ ] **Step 4:** Jest：
  - `extractAtMentionQuery` 边界（中文、路径、空格结束）
  - 选中 `@` 候选 → `attachedVaultPaths` 含 path；提交 mock `runAskCommand` 收到注入后的 question 或 materialPaths
  - 显式 `@` 替换 sticky（`resolveAskMaterialPaths` 契约）

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — expect PASS  
- [ ] **Commit:** `feat(shell): @-mention vault paths into ask material_refs`

---

## Task 3: 编辑再发 + 成功后再生成

**Depends on:** Task 1（气泡材料展示与 `retryArgs.materialPaths`）；与 Task 2 接口独立，但建议在 Task 2 之后做，避免同一文件 `render_today.js` 冲突

**Files:**
- Modify: `render_today.js`, `plugin_lifecycle.js`（若抽 `prefillComposer`）, `constants.js`
- Test: `universal-input-interaction.test.js` 或 `bubble-regenerate.test.js`

- [ ] **Step 1:** 对 `entry.status === "done"` 且 `reconcileTarget === "outputs"` 且 **非** degraded：在现有「打开报告」「引用此报告追问」旁增加：
  - **再生成**（`furnace-pending-regenerate-btn`）：行为对齐 degraded「重试」——`resetPendingSubmissionForRetry` + `runAskCommand`（同 `retryArgs` 的 question/format/materialPaths）+ `excludePendingId` + 新报告路径写入 pending；**旧报告文件不删**
  - **编辑问题**（`furnace-pending-edit-ask-btn`）：把 `retryArgs.question`（或 `askQuestion` / `displayText`）写入 composer textarea；若有 `materialPaths` 预填 sticky/attachedVaultPaths；focus textarea。不立即提交。

- [ ] **Step 2:** failed / degraded 路径保持现有「重试」按钮文案与行为；不要用「再生成」替换失败态（避免语义混淆）。

- [ ] **Step 3:** 抽小 helper（可放 `helpers.js` 或 `render_today.js` 顶部）：

```js
function pendingAskQuestionFromEntry(entry) {
  const args = entry && entry.retryArgs || {};
  return String(args.askQuestion || args.question || entry.displayText || "").trim();
}

function pendingAskMaterialPathsFromEntry(entry) {
  const args = entry && entry.retryArgs || {};
  return normalizeMaterialPaths(args.materialPaths || []);
}
```

编辑 / 再生成共用，避免三处拷贝。

- [ ] **Step 4:** Jest：
  - done 成功气泡有「再生成」「编辑问题」；degraded 仍只有「重试」
  - 点再生成 → `runAskCommand` 被调用且 `excludePendingId === entry.id`；question/format 来自 retryArgs
  - 点编辑 → textarea.value === 原问题（mock quote/prefill）

- [ ] **Step 5:** `PROGRESS.md` 记一笔；`docs/Furnace Product Shell.md` 用 2–4 句写明：Universal Input 可 `@`/粘性材料/再生成，但输出端仍是 Today 报告，金丹仍走报告卡沉淀/凝丹。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — expect PASS  
- [ ] **Commit:** `feat(shell): edit-resend and regenerate for successful asks`

---

## Final verify

- [ ] `bash scripts/verify.sh product-shell-static` — expect PASS（含全量 Jest）
- [ ] `bash scripts/build.sh`（或仓库惯用 product-shell build）确保 `main.js` 与 src 同步
- [ ] （可选 dogfood）`bash scripts/sync_product_shell_to_vault.sh` 后在真实 vault 走：投料 → 追问见材料 → `@` 换材料 → 再生成 → 打开新报告；旧报告仍在
- [ ] **Commit**（若 build/docs 尚有未提交）：`chore(shell): rebuild main.js after chat-entry slice`

---

## Out of plan（禁止顺手做）

- 多轮 chat history 进 prompt、消息分叉、并行多会话、流式 UI
- background ask / submit-resume
- heavy RAG、`@文件夹` 递归索引、vision
- 扩大 `advanced`、改 Commercial Go-Live 主线叙事
- 纯为测试去改 Python runtime（除非 Task 2 证实 path 契约缺口）
