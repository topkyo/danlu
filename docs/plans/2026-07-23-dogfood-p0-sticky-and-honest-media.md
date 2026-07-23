# Dogfood P0 Sticky + Honest Media Implementation Plan

> **For agentic workers:** Load `executing-plans`. Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** Shell 持久化材料粘性 + 不可读材料 ask 诚实降级，修 dogfood 追问丢锚 / 图片假成功。  
**Spec:** `docs/specs/2026-07-23-dogfood-p0-sticky-and-honest-media.md`  
**Architecture:** `stickyMaterialRefs` 存插件 settings；追问经 `buildAutoAskQuestion` 注入；runtime 在 `material_refs` 非空但可读 context 为空时短答降级，不灌无关 wiki。  
**Tech stack:** Product Shell JS + Jest；Python ask (`workflows_ask*`)；`bash scripts/verify.sh product-shell-static llm-integration`

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `.obsidian/plugins/furnace-product-shell/src/constants.js` | modify | `DEFAULT_SETTINGS.stickyMaterialRefs` + i18n Notice 文案 |
| `.obsidian/plugins/furnace-product-shell/src/helpers.js` | modify | normalize/get/set sticky；`resolveAskMaterialPaths`；image-unreadable payload helper |
| `.obsidian/plugins/furnace-product-shell/src/plugin_state.js` | modify | load 时 normalize sticky |
| `.obsidian/plugins/furnace-product-shell/src/plugin_actions.js` | modify | drop 成功写 sticky；纯 ask 注入 sticky；ask 后刷新 updatedAt |
| `.obsidian/plugins/furnace-product-shell/src/render_input.js` / `render_today.js` | modify | 若有旁路 ask 入口，统一走 sticky 解析（尽量经 plugin_actions） |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/helpers/sticky-materials.test.js` | create | sticky 单元测 |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/…` | modify | 追问注入 / Notice 契约 |
| `src/aiwiki/runner/workflows_ask_context.py` | modify | 检测 unreadable materials；诚实短答正文 builder |
| `src/aiwiki/runner/workflows_ask.py` | modify | 空 context + 有 refs → 降级分支（跳过无关 wiki 主合成或强制诚实 prompt+degraded） |
| `tests/test_llm_integration.py` | modify | 仅 jpeg material_refs 诚实降级契约 |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | build.sh |
| `PROGRESS.md` | modify | 记一笔 |

---

## Task 1: Shell stickyMaterialRefs

**Depends on:** none

**Files:**
- Modify: `constants.js`, `helpers.js`, `plugin_state.js`, `plugin_actions.js`
- Touch ask entry points only as needed so **所有** `runAskCommand` / `runDroppedPayloadsWithAutoAsk` 路径一致
- Test: `src/__tests__/helpers/sticky-materials.test.js` + 扩展既有 interaction/auto-ask 测

- [ ] **Step 1:** `DEFAULT_SETTINGS` 增加：

```js
stickyMaterialRefs: { paths: [], updatedAt: "", source: "" },
```

i18n 键预留（Task 2 也用）：`"Image archived only; content analysis is unavailable for now."` 等。

- [ ] **Step 2:** helpers 增加：

```js
function normalizeStickyMaterialRefs(value) {
  // paths: normalizeMaterialPaths; updatedAt/source strings; corrupt → empty
}
function setStickyMaterialRefs(settings, paths, source) {
  settings.stickyMaterialRefs = {
    paths: normalizeMaterialPaths(paths),
    updatedAt: new Date().toISOString(),
    source: String(source || "drop"),
  };
}
function resolveAskMaterialPaths(explicitPaths, sticky) {
  const explicit = normalizeMaterialPaths(explicitPaths);
  if (explicit.length) return { paths: explicit, fromSticky: false };
  const stickyPaths = normalizeStickyMaterialRefs(sticky).paths;
  return { paths: stickyPaths, fromSticky: stickyPaths.length > 0 };
}
```

- [ ] **Step 3:** `plugin_state.js` load 后 `plugin.settings.stickyMaterialRefs = normalizeStickyMaterialRefs(...)`；若纠正则纳入 save-if-migrated。

- [ ] **Step 4:** `runProductShellDroppedPayloadsWithAutoAsk`：drop 收集到 `normalizedMaterialPaths` 非空 → `setStickyMaterialRefs(..., "drop")` + `savePluginState`。  
  `runProductShellAskCommand`（或调用前包装）：无 caller 显式 materials 时，用 `resolveAskMaterialPaths([], sticky)`；若 `fromSticky`，`question = buildAutoAskQuestion(question, paths)` 再 `buildAskCommandSpec`。  
  ask 成功且本轮 paths 非空 → 刷新 sticky（`source: fromSticky ? sticky.source : "ask"` 或 `"explicit-@"` 若问题自带材料提示——实现时：显式 paths 用 `"ask"`）。

- [ ] **Step 5:** Jest：normalize 损坏输入；set/replace；`resolveAskMaterialPaths` 显式优先于 sticky；模拟 drop→ask 注入（可测 helpers + plugin_actions 经 vm/mock）。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — expect PASS  
- [ ] **Commit:** `feat(shell): persist stickyMaterialRefs for follow-up asks`

---

## Task 2: Shell image drop 诚实 Notice

**Depends on:** Task 1（共享 helpers/i18n；可同一 agent 串行）

**Files:**
- Modify: `helpers.js`, `plugin_actions.js`（或 drop 完成回调处）, `constants.js`
- Test: Jest 契约

- [ ] **Step 1:** helper `imageDropLacksReadableAnalysis(payload)`：  
  当 payload 表明 image drop 且 `visual_analysis_present === false` 或 `vision_status` ∈ `{disabled,skipped,failed,""}`（字段名以 CLI JSON 实际为准，实现前 `rg visual_analysis` 对齐）。

- [ ] **Step 2:** 在 drop 成功路径（`runUniversalInputCommand` / dropped payloads 循环内）若 helper 为 true → `new Notice(t("Image archived only; content analysis is unavailable for now."))`。  
  不阻断 sticky 写入（图路径仍可进 sticky，供 runtime 诚实降级）。

- [ ] **Step 3:** Jest：payload 无分析 → helper true；有 `visual_analysis_present: true` → false。

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`  
- [ ] **Commit:** `feat(shell): notice when image drop has no visual analysis`

---

## Task 3: Runtime 不可读材料诚实降级

**Depends on:** none（可与 Task 1 并行；合 main 时注意无文件冲突）

**Files:**
- Modify: `src/aiwiki/runner/workflows_ask_context.py`, `workflows_ask.py`（必要时 `workflows_ask_frontmatter.py` / prompts）
- Test: `tests/test_llm_integration.py` 新增用例

- [ ] **Step 1:** 在 `workflows_ask_context.py` 增加：

```python
def _material_refs_unreadable(root: Path, refs: list[str], context_text: str) -> bool:
    """True when refs non-empty but no usable textual material context."""
    ...
```

判定：`refs` 非空且 `strip(context_text)` 为空（因 `_read_material_context` 已跳过非 md/txt）。可选：若唯一 ref 是 image 扩展名则同为 True。

- [ ] **Step 2:** `workflows_ask.py` 在读完 `material_context` 后：若 `_material_refs_unreadable(...)`：
  - **不要**用无关 ranked wiki 生成「分析了附件」长文；优先写固定诚实短正文（首段说明材料已登记但当前无法读取内容；列出 refs），并 `_mark_run_ask_artifact_degraded` 或等价 degraded 标记（对齐现有 `llm_status` / delivery 字段；选最小侵入已有约定）。
  - 若仍调用 LLM：prompt 必须强制只输出诚实短答 + 禁止编造图片内容；并收窄/清空无关 source 页注入。**推荐最小路径：确定性短答 + degraded，不调用 LLM**（更 KISS、测更稳）。

- [ ] **Step 3:** 文本弱命中：在 ask prompt 系统约束加一句——若不确定所指材料，**第一段**必须声明不确定，禁止先写长替代分析（可与现有 prompt builder 一处修改）。

- [ ] **Step 4:** llm-integration：构造 vault fixture，`material_refs` 仅 `raw/assets/x.jpeg`（文件可存在但无 md 上下文）→ run-ask（mock）→ 报告含诚实首段、且不出现无关长综述标题模式；status/degraded 断言。

- [ ] **Verify:** `bash scripts/verify.sh llm-integration python-static`  
- [ ] **Commit:** `fix(ask): honest degrade when material refs are unreadable`

---

## Task 4: Bundle、PROGRESS、总闸

**Depends on:** Task 1, Task 2, Task 3

**Files:**
- Rebuild: `main.js`
- Modify: `PROGRESS.md`；可选勾选本 plan checkboxes
- Optional: `bash scripts/sync_product_shell_to_vault.sh`

- [ ] **Step 1:** `bash .obsidian/plugins/furnace-product-shell/build.sh`
- [ ] **Step 2:** PROGRESS 记：P0 sticky + honest media；链 spec/plan；Jest 计数若变则更新 AGENTS/Scorecard
- [ ] **Step 3（可选）:** sync dogfood vault plugin links
- [ ] **Final verify:**

```bash
bash scripts/verify.sh product-shell-static
bash scripts/verify.sh llm-integration
```

- [ ] **Commit:** `chore(shell): rebuild main.js after sticky + honest media`

---

## Final verify

```bash
bash scripts/verify.sh product-shell-static
bash scripts/verify.sh llm-integration
```

建议再跑：`bash scripts/verify_target_rules.sh` 后按建议补 `python-static`。可选 `all`。

---

## Out of scope

- Runtime session 文件；vision；图片 hash 去重；概念门槛；探针失踪；notify 验证（Slice 2/3）
