# Product Shell Settings Slim (A) Implementation Plan

> **For agentic workers:** Load `executing-plans`. Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** Settings A 档瘦身——通知 URL 单一真相源、废弃未读文档/CSS、删 `cliHint`、SoT §9 对齐。  
**Spec:** `docs/specs/2026-07-22-product-shell-settings-slim.md`  
**Architecture:** Shell `buildNotifyEnv` 由非空 webhook URL 推导 `AIWIKI_NOTIFY_ENABLED_CHANNELS`；`notify.py` 不动；LLM 凭据 UI 不动。  
**Tech stack:** Obsidian plugin JS (concat bundle)、Jest、`bash scripts/verify.sh product-shell-static`

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `.obsidian/plugins/furnace-product-shell/src/helpers.js` | modify | `buildNotifyEnv` 按 URL 推导 channels；删除或内联 `normalizeEnabledChannels` |
| `.obsidian/plugins/furnace-product-shell/src/constants.js` | modify | 去掉 `enabledChannels`；删 Enable/CLI 死 i18n；修正 LLM desc 去掉 CLI sessions 文案 |
| `.obsidian/plugins/furnace-product-shell/src/settings.js` | modify | 删 Enable toggles + `cliHint` 块 |
| `.obsidian/plugins/furnace-product-shell/src/plugin_state.js` | modify | load 时 delete `enabledChannels`/`enabled_channels`；不再写回该字段 |
| `.obsidian/plugins/furnace-product-shell/src/llm_settings.js` | modify | `llmProviderNeedsModel` 不再依赖 `cliHint`（恒 true / `Boolean(profile)`） |
| `.obsidian/plugins/furnace-product-shell/styles.css` | modify | 删 `.is-unread` / `.furnace-report-unread` / 仅服务未读的 `.report-dot` 规则 |
| `.obsidian/plugins/furnace-product-shell/src/__tests__/…` | create/modify | `buildNotifyEnv` 单测 + settings/CSS 源码契约 |
| `.obsidian/plugins/furnace-product-shell/main.js` | rebuild | `bash build.sh` 或仓库 sync 脚本 |
| `docs/Furnace Product Shell.md` | modify | §5/§6/§9/§10 废弃未读；schema camelCase；无 `enabledChannels` |
| `PROGRESS.md` | modify | 记一笔 A 档 settings slim |

---

## Task 1: 通知单一真相源 + cliHint/未读 CSS 代码面

**Depends on:** none

**Files:**
- Modify: `helpers.js`, `constants.js`, `settings.js`, `plugin_state.js`, `llm_settings.js`, `styles.css`
- Test: `src/__tests__/helpers/notify-env.test.js`（新建）+ 扩展 `src/__tests__/plugin/view-registration.test.js`

- [ ] **Step 1:** 改 `buildNotifyEnv`：

```js
function buildNotifyEnv(settings) {
  const env = {};
  const channels = [];
  const feishuWebhookUrl = String((settings && settings.feishuWebhookUrl) || "").trim();
  if (feishuWebhookUrl) {
    env.AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL = feishuWebhookUrl;
    channels.push("feishu");
  }
  const wecomWebhookUrl = String((settings && settings.wecomWebhookUrl) || "").trim();
  if (wecomWebhookUrl) {
    env.AIWIKI_NOTIFY_WECOM_WEBHOOK_URL = wecomWebhookUrl;
    channels.push("wecom");
  }
  if (channels.length) {
    env.AIWIKI_NOTIFY_ENABLED_CHANNELS = channels.join(",");
  }
  return env;
}
```

若 `normalizeEnabledChannels` 无其它引用则删除该函数。

- [ ] **Step 2:** `DEFAULT_SETTINGS` 删除 `enabledChannels`。`plugin_state.js`：去掉 merge/normalize `enabledChannels` 段；改为：

```js
const legacyEnabledChannelsMigrated =
  Object.prototype.hasOwnProperty.call(plugin.settings, "enabledChannels")
  || Object.prototype.hasOwnProperty.call(plugin.settings, "enabled_channels")
  || Object.prototype.hasOwnProperty.call(rawSettings, "enabledChannels")
  || Object.prototype.hasOwnProperty.call(rawSettings, "enabled_channels");
delete plugin.settings.enabledChannels;
delete plugin.settings.enabled_channels;
// include legacyEnabledChannelsMigrated in save-if-migrated condition
```

保留既有 `lastViewedTimestamp` delete。

- [ ] **Step 3:** `settings.js`：删除 `updateEnabledChannel` 与 Enable Feishu/WeCom 两个 `Setting`；删除 `if (selectedProfile.cliHint) { ... }` 整块。

- [ ] **Step 4:** `llm_settings.js`：`llmProviderNeedsModel` → `return Boolean(profile);`（或等价，不再读 `cliHint`）。更新 `llm-settings.test.js` 若断言旧语义。

- [ ] **Step 5:** `constants.js`：删除 i18n 键 `"Enable Feishu"` / `"Enable WeCom"` / `"CLI session"` 及仅服务于 CLI hint 的 desc（若有）；LLM provider `setDesc` 英文源串去掉 “advanced entries are for local CLI sessions…”——改为只描述选 provider，中文翻译同步缩短。

- [ ] **Step 6:** `styles.css`：删除
  - `.furnace-shell-report-card.is-unread` 及其 title/dot 变体
  - `.furnace-shell-report-dot`（确认 src 无 DOM 引用后再删）
  - `.furnace-report-unread` 块（约 L1178–1191）

- [ ] **Step 7:** 新建 Jest `notify-env.test.js`（按现有 helpers 测试加载方式：读源或 require 拼接全局）。覆盖：
  - 仅 feishu URL → 含 `AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL` 与 `ENABLED_CHANNELS=feishu`
  - 双 URL → `feishu,wecom`（顺序稳定）
  - 全空 → 无 webhook / enabled env 键

- [ ] **Step 8:** 扩展 `view-registration.test.js`（或同级 settings 契约测）：
  - `settingsSrc` 匹配 Integrations webhook；**不**匹配 `Enable Feishu` / `enabledChannels` / `cliHint`
  - `constantsSrc` **不**含 `enabledChannels:`
  - `stylesSrc` **不**匹配 `is-unread` / `furnace-report-unread`
  - `pluginStateSrc` 匹配 `delete plugin.settings.enabledChannels`

- [ ] **Verify:** `bash scripts/verify.sh product-shell-static` — expect PASS  
- [ ] **Commit:** `refactor(shell): settings slim — URL-only notify, drop unread CSS/cliHint`

---

## Task 2: SoT 文档收口

**Depends on:** none（文档可与 Task 1 并行；若并行，§9 字段表以 Task 1 落地后的 schema 为准，冲突时 Task 2 后合）

**Files:**
- Modify: `docs/Furnace Product Shell.md`
- Modify: `PROGRESS.md`（可放 Task 3；本 task 至少改 SoT）

- [ ] **Step 1:** §5 通知流：去掉「按 `last_viewed_timestamp` 更新视觉态」；改为回到 vault 打开报告即可（列表按时间，无未读样式）。

- [ ] **Step 2:** §3 ReportCard / 状态机：删除未读加粗·圆点与 `has-unread` / `all-read` 若仅服务未读；保留 running/error 等真实状态。

- [ ] **Step 3:** §6：删除「`last_viewed_timestamp` 存在插件 settings」条目；保留「不扩 shell-summary」结论；注明按日分组仍可在内存计算，**无**未读视觉态。

- [ ] **Step 4:** §9 schema 改为 camelCase 与代码对齐，至少列出：
  - `feishuWebhookUrl` / `wecomWebhookUrl`（可空；非空即启用）
  - **无** `enabledChannels` / `last_viewed_timestamp`
  - 可加一句：完整默认集见 `constants.js` `DEFAULT_SETTINGS`（含 LLM 等 A 档保留项）

- [ ] **Step 5:** §10 决策 2：改为「**废弃**插件内未读视觉态；不恢复 `lastViewedTimestamp`；外部 IM 通知 + Today 时间序足够」。

- [ ] **Step 6:** §0 / 其它残留「未读」若与新决策矛盾则改一句对齐（例如 §0「不扩 shell-summary」里若仍暗示未读在 settings，改为分组/通知本地闭环、无未读字段）。

- [ ] **Verify:** `bash scripts/docs_consistency_check.sh` — expect PASS（若该文档不在检查范围，至少人工确认无 snake `enabled_channels` settings 承诺）  
- [ ] **Commit:** `docs: Product Shell SoT — drop unread + URL-only notify schema`

---

## Task 3: Bundle、PROGRESS、总闸

**Depends on:** Task 1（commit）, Task 2（commit）

**Files:**
- Rebuild: `.obsidian/plugins/furnace-product-shell/main.js`
- Modify: `PROGRESS.md`
- Optional: `bash scripts/sync_product_shell_to_vault.sh`（本机 vault 可写时）

- [ ] **Step 1:** 在插件目录执行既有 build（`bash build.sh` 或仓库文档指定命令），确保 `main.js` 含新 `buildNotifyEnv`、无 Enable toggle 字符串。

- [ ] **Step 2:** `PROGRESS.md` 头部动态记一笔：Settings Slim A 落地（spec 路径 + 要点：URL-only notify / 未读废弃 / cliHint 删）。

- [ ] **Step 3（可选）：** `bash scripts/sync_product_shell_to_vault.sh` — 不改 vault `data.json`；仅同步 plugin 产物。

- [ ] **Final verify:** `bash scripts/verify.sh product-shell-static`；若 Task 2 改了 docs 且 consistency 脚本覆盖，再跑 `docs_consistency_check.sh`。建议：`bash scripts/verify_target_rules.sh` 看路径建议后跑对应 target。  
- [ ] **Commit:** `chore(shell): rebuild main.js after settings slim`

---

## Final verify

```bash
bash scripts/verify.sh product-shell-static
bash scripts/docs_consistency_check.sh
```

（可选更稳）`bash scripts/verify.sh all` — 仅当 worker 时间允许；本 plan 不以 `all` 为每 task 门闸。

---

## Out of scope

- LLM key/Base URL 下沉；删 `locale`；改 `notify.py`
- 恢复未读 UI
- 编辑 dogfood `data.json` 内容
- B/C 档 schema
