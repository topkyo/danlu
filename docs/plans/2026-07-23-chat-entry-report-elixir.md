# Chat Entry → Report → Elixir Implementation Plan

> **For agentic workers:** Load `executing-plans` (3 tasks). Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.
>
> **Review gate (2026-07-23):** 三路交叉 review 后修订。修复：`runAskCommand(materialPaths)` 贯穿；sticky chips **只读**（继承 P0 清除规则）；`@` 前缀对齐 runtime；drop+`@` merge；build 路径；`prefillComposer`；Task 3 `Depends on: Task 2`。

**Goal:** 在「入口像 ChatGPT、产出一问一报告 + 金丹链」边界下，落地第一刀三切片：材料可见 → `@`/选文件 → 编辑再发/再生成。  
**Spec:** `docs/specs/2026-07-23-chat-entry-report-elixir.md`  
**Architecture:** Shell-only UX 增强；继续走同步 `run-ask` + `material_refs` / `stickyMaterialRefs`；交付物仍是 `output/reports/*.md`；不改 runtime 五层、不恢复 background ask、不引入 RAG。  
**Tech stack:** Product Shell JS + Jest；`bash scripts/verify.sh product-shell-static`（per-task）；Final：同 + `bash .obsidian/plugins/furnace-product-shell/build.sh`

---

## Cross-cutting contracts（三任务共用）

### C1. `runAskCommand` 显式材料 API

扩展签名（Task 1 落地，Task 2/3 复用）：

```js
async function runProductShellAskCommand(plugin, {
  question, format, mode, excludePendingId, materialPaths,
}) {
  const explicit = normalizeMaterialPaths(materialPaths);
  const resolved = resolveAskMaterialPaths(explicit, plugin.settings.stickyMaterialRefs);
  let askQuestion = String(question || "").trim();
  if (askQuestion && !questionAlreadyHasMaterialRoutingHint(askQuestion) && resolved.paths.length) {
    askQuestion = buildAutoAskQuestion(askQuestion, resolved.paths);
  }
  if (explicit.length) {
    setStickyMaterialRefs(plugin.settings, explicit, "explicit-@");
    // savePluginState as elsewhere
  } else if (resolved.paths.length && !resolved.fromSticky) {
    // no-op
  } else if (resolved.paths.length) {
    // refresh sticky updatedAt on use (existing P0 behavior)
  }
  // ... existing spawn run-ask ...
  return { ...payload, usedMaterialPaths: resolved.paths };
}
```

调用方（`render_input` / `render_today`）在 `updatePendingSubmissionRetryArgs` 时**必须**写入：

```js
materialPaths: payload.usedMaterialPaths || explicit || []
```

纯 `auto-ask` 路径今天不写 `materialPaths`——Task 1 修掉。

### C2. Runtime 可解析路径前缀（与 `_material_hint_paths` 对齐）

允许写入材料提示 / `@` 候选的 path **必须**满足（相对 vault）：

- 扩展名：`.md` 或 `.txt`
- 前缀之一：`raw/`、`wiki/`、`output/`、`.aiwiki/`

「引用当前文件」：若 active file 不在上述前缀 → `Notice` fail-loud，**不**注入。  
**不改** Python，除非实现时证实 `buildAutoAskQuestion` 注入后仍丢 path（先 `rg _material_hint_paths` 复核）。

### C3. sticky 清除规则（继承 dogfood P0，本 plan **不** supersede）

清除仅：新 drop 整组替换 / 显式 `@` 或 `materialPaths` 非空整组替换。  
Composer sticky chips = **只读展示**（无逐条 ×）。

### C4. drop 附件 + `@` vault paths 并行

| 提交内容 | 行为 |
|----------|------|
| 仅拖拽文件（±问题） | 现有 `runDroppedFilesWithAutoAsk`；drop 成功 paths → sticky |
| 仅 `@`/vault paths + 问题 | `runAskCommand({ question, materialPaths: attachedVaultPaths })` |
| 拖拽文件 **且** `attachedVaultPaths` 非空 + 问题 | drop 完成后，`union = normalizeMaterialPaths([...dropPaths, ...attachedVaultPaths])`，再 `runAskCommand({ question, materialPaths: union })`（或 auto-ask 包装传入 union）；**禁止**只走 drop 而丢掉 `@` paths |
| 非法 path | Notice，不提交该 path |

### C5. `prefillComposer`（Task 3 编辑问题）

在 `plugin_lifecycle.js`（或 `plugin.js` 方法）提供：

```js
function prefillComposer(plugin, { question, materialPaths }) {
  // 1) 找 Today/Home 上的 .furnace-universal-input-textarea，set value + focus
  // 2) 若 materialPaths 非空：setStickyMaterialRefs(..., "explicit-@") + savePluginState
  //    （不依赖 render_input 闭包内 attachedVaultPaths；下次 render 只读 sticky 条即可显示）
  // 3) 触发 input/autoResize 若存在
}
```

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `.obsidian/plugins/furnace-product-shell/src/helpers.js` | modify | chip label；`@` 解析；`isAskMaterialPathAllowed`；pending ask helpers |
| `.obsidian/plugins/furnace-product-shell/src/render_input.js` | modify | 只读 sticky 条；`@` suggest；merge 提交；写 `retryArgs.materialPaths` |
| `.obsidian/plugins/furnace-product-shell/src/render_today.js` | modify | done 卡只读材料 chips；再生成/编辑问题 |
| `.obsidian/plugins/furnace-product-shell/src/plugin_actions.js` | modify | `runAskCommand({ materialPaths })` + `usedMaterialPaths` |
| `.obsidian/plugins/furnace-product-shell/src/plugin_lifecycle.js` | modify | `prefillComposer`；quote 可复用其 textarea 写入 |
| `.obsidian/plugins/furnace-product-shell/src/plugin.js` | modify | 暴露 `prefillComposer` / `runAskCommand` 参数透传若需要 |
| `.obsidian/plugins/furnace-product-shell/src/constants.js` | modify | i18n |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/helpers/sticky-materials.test.js` | modify | helpers |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/render/universal-input-interaction.test.js` | modify | 交互；mock `app.vault.getMarkdownFiles` / `workspace.getActiveFile` 按需 |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/render/`（可选新文件） | create | 文件过大时拆测 |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | `bash .obsidian/plugins/furnace-product-shell/build.sh` |
| `PROGRESS.md` | modify | 记一笔 |
| `docs/Furnace Product Shell.md` | modify | §0 合规句 + 「交互像 chat、交付物是报告」 |

**Runtime Python：** 默认不改。

---

## Task 1: 本轮材料可见 + `materialPaths` API

**Depends on:** none

**Files:**
- Modify: `helpers.js`, `plugin_actions.js`, `render_input.js`, `render_today.js`, `constants.js`, `plugin.js`（若需透传）
- Test: `sticky-materials.test.js`, `universal-input-interaction.test.js`

- [ ] **Step 1:** `helpers.js`：

```js
function stickyMaterialDisplayPaths(settings) {
  return normalizeStickyMaterialRefs(settings && settings.stickyMaterialRefs).paths;
}
function formatMaterialChipLabel(path) {
  const p = String(path || "").replace(/\\/g, "/");
  const parts = p.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : p;
}
function isAskMaterialPathAllowed(path) {
  const s = String(path || "").replace(/\\/g, "/").replace(/^\.\//, "");
  if (!(s.endsWith(".md") || s.endsWith(".txt"))) return false;
  return s.startsWith("raw/") || s.startsWith("wiki/")
    || s.startsWith("output/") || s.startsWith(".aiwiki/");
}
```

- [ ] **Step 2:** 按 **C1** 扩展 `runProductShellAskCommand`；返回 `usedMaterialPaths`。

- [ ] **Step 3:** `render_input.js` 所有 ask 成功写 `retryArgs` 的路径（含纯 `auto-ask`）：合并 `materialPaths: usedMaterialPaths`。调用 `runAskCommand` 时若本轮已有 resolved paths，可传 `materialPaths` 或依赖 sticky——纯追问保持 `materialPaths: []` 让 sticky 注入即可，但 **retryArgs 必须记下 usedPaths**。

- [ ] **Step 4:** Composer：`furnace-input-sticky-materials` **只读** chips（文件名 + `title=全路径`）；i18n `"本轮材料（追问仍会带上）"`。无 ×。不把 sticky 当 File 附件。

- [ ] **Step 5:** `render_today.js`：**AI done/degraded 结果卡**（非 user 气泡）若 `retryArgs.materialPaths` 非空，渲染只读 `furnace-bubble-materials` chips。

- [ ] **Step 6:** Jest：sticky 非空 → chips；无 × 按钮；纯 ask 后 `retryArgs.materialPaths` 含 sticky paths（mock runAskCommand 返回 `usedMaterialPaths`）；`isAskMaterialPathAllowed` 边界。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — PASS  
- [ ] **Commit:** `feat(shell): show material chips and plumb ask materialPaths`

---

## Task 2: Composer `@` / 选文件 → material_refs

**Depends on:** Task 1（C1 API + 只读材料条 + `isAskMaterialPathAllowed`）

**Files:**
- Modify: `helpers.js`, `render_input.js`, `plugin_actions.js`（若需）, `constants.js`
- Test: interaction 或 `composer-at-mention.test.js`（mock vault）

- [ ] **Step 1:**

```js
function extractAtMentionQuery(text, cursor) { /* 回扫最近 @token；返回 { start, end, query } 或 null */ }
function filterVaultPathsForMention(paths, query, limit = 12) {
  const q = String(query || "").toLowerCase();
  return normalizeMaterialPaths(paths)
    .filter((p) => isAskMaterialPathAllowed(p) && (!q || p.toLowerCase().includes(q)))
    .slice(0, limit);
}
```

- [ ] **Step 2:** `render_input.js`：
  - `attachedVaultPaths: string[]`；pill 可 ×（只影响本轮附件，**不是** sticky 逐条删；提交成功后由 C1 整组替换 sticky）
  - `@` → `furnace-at-suggest`；候选 = filter(`getMarkdownFiles()` paths + 合法 active file)
  - 按钮「引用当前文件」：非法前缀 → Notice
  - 提交按 **C4** merge
  - Jest mock：`plugin.app = { vault: { getMarkdownFiles: () => [...] }, workspace: { getActiveFile: () => ... } }`

- [ ] **Step 3:** 显式 paths → `runAskCommand({ materialPaths })`；sticky `source: "explicit-@"`（C1）。与 `引用报告：` 并存：不去重也可（runtime 两侧都能读）；勿删 quote 按钮。

- [ ] **Step 4:** Jest：`extractAtMentionQuery`；选中 `@` → paths；显式替换 sticky；C4：files+vaultPaths 时 `runAskCommand`/`auto-ask` 收到 union（断言 mock 调用参数）。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — PASS  
- [ ] **Commit:** `feat(shell): @-mention vault paths into ask material_refs`

---

## Task 3: 编辑再发 + 成功后再生成

**Depends on:** Task 2（C1+C4 已稳定；`prefillComposer` 与材料条一致）

**Files:**
- Modify: `helpers.js`, `render_today.js`, `plugin_lifecycle.js`, `plugin.js`, `constants.js`, `PROGRESS.md`, `docs/Furnace Product Shell.md`
- Test: interaction 或 `bubble-regenerate.test.js`

- [ ] **Step 1:** helpers：

```js
function pendingAskQuestionFromEntry(entry) {
  const args = (entry && entry.retryArgs) || {};
  return String(args.askQuestion || args.question || (entry && entry.displayText) || "").trim();
}
function pendingAskMaterialPathsFromEntry(entry) {
  const args = (entry && entry.retryArgs) || {};
  return normalizeMaterialPaths(args.materialPaths || []);
}
```

- [ ] **Step 2:** 成功 done（`reconcileTarget === "outputs"` 且 **`!pendingSubmissionIsDegraded(entry)`**，勿只看 `status === "done"`）：
  - **再生成**：`resetPendingSubmissionForRetry` →  
    `paths = pendingAskMaterialPathsFromEntry(entry)` →  
    `runAskCommand({ question: pendingAskQuestionFromEntry(entry), format, materialPaths: paths, excludePendingId: entry.id })`  
    → 更新 retryArgs（含新 `materialPaths` / run 元数据）。**不删旧报告文件。**
  - **编辑问题**：`plugin.prefillComposer({ question, materialPaths: paths })`（**C5**），不提交。
  - 保留「打开报告」「引用此报告追问」。

- [ ] **Step 3:** degraded / failed：保持「重试」文案与现有行为；可同样传入 `materialPaths`（若 retryArgs 有）以免丢材料——最小一致改动允许。

- [ ] **Step 4:** Jest：成功气泡有「再生成」「编辑问题」；degraded 无「再生成」；再生成调用含 `materialPaths` + `excludePendingId`；编辑触发 `prefillComposer`。

- [ ] **Step 5:** `PROGRESS.md`；`docs/Furnace Product Shell.md`：§0「仍是一个输入 + 一个输出（报告），无新视图」+ COMPARE 对齐「交互像 chat、交付物是可审计报告/金丹」。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — PASS  
- [ ] **Commit:** `feat(shell): edit-resend and regenerate for successful asks`

---

## Final verify

- [ ] `bash scripts/verify.sh product-shell-static` — PASS  
- [ ] `bash .obsidian/plugins/furnace-product-shell/build.sh` — `main.js` 同步  
- [ ] （可选）`bash scripts/sync_product_shell_to_vault.sh` + dogfood 路径  
- [ ] **Commit**（若需要）：`chore(shell): rebuild main.js after chat-entry slice`

---

## Out of plan（禁止顺手做）

- 多轮 chat history 进 prompt、消息分叉、并行多会话、流式 UI
- background ask / submit-resume
- heavy RAG、`@文件夹` 递归索引、vision
- sticky 逐条删除 UI（与 P0 冲突）
- 扩大 `advanced`、改 Commercial Go-Live 主线叙事
- 无证据时改 Python runtime
