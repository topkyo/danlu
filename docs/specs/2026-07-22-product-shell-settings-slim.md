# Product Shell Settings Slim（A 档）

**Date:** 2026-07-22  
**Status:** Approved (chat)  
**Owner:** Product Shell  
**Approach:** ① Shell 推导 `enabled_channels`；runtime `notify.py` 本轮不动

## Goal

对炼丹炉 Product Shell 做 **settings 最小瘦身**：通知改为单一真相源（webhook URL）、正式废弃未读视觉态文档/CSS、删除 `cliHint` 死分支，并使 SoT §9 与 `DEFAULT_SETTINGS` 对齐。落实 KISS / less is more 的一小步，不扩 scope 到 LLM 凭据下沉。

## Decisions

1. **范围 = A 档**：不挪 LLM API key / Base URL；不改 `locale`；不做 B/C 激进 schema。
2. **通知启用规则**：渠道 URL 非空 = 启用；清空 URL = 关闭。删除 settings 字段 `enabledChannels` 与 Integrations UI 上的 Enable Feishu/WeCom toggle。
3. **迁移语义 X**：load 时直接 `delete` `enabledChannels`（及 snake `enabled_channels`）。原先「有 URL + toggle 关」的用户本轮起会开始推送——已接受。
4. **桥接路径 ①**：`buildNotifyEnv` 由非空 URL 推导 `AIWIKI_NOTIFY_ENABLED_CHANNELS`；继续注入对应 webhook URL env。`src/aiwiki/notify.py` 本轮不改。
5. **未读 = 文档废弃（选项 1）**：SoT 删除 `last_viewed_timestamp` / 未读加粗·圆点承诺；删除 orphan `.is-unread` CSS；保留对旧 `lastViewedTimestamp` 的 load 时 delete。不恢复未读读写。
6. **死分支**：删除 `cliHint` 设置 UI 与仅为其服务的 helper；确认无 profile 再挂 `cliHint`。

## Design

### Architecture

- 用户面 Integrations：仅 Feishu / WeCom webhook URL 文本框（仍在默认折叠的 `<details>` 内）。
- 持久化：`DEFAULT_SETTINGS` 去掉 `enabledChannels`；无未读字段。
- Launcher spawn 前 `buildNotifyEnv(settings)` 是唯一把插件通知配置变成 runtime env 的桥。

### Components / files (expected)

| Area | Files |
|------|--------|
| Schema + i18n | `constants.js` |
| Notify bridge | `helpers.js` (`buildNotifyEnv`, drop or shrink `normalizeEnabledChannels` if unused) |
| Load migration | `plugin_state.js` |
| Settings UI | `settings.js` |
| LLM dead branch | `llm_settings.js`（若有仅 `cliHint` helper） |
| Orphan CSS | `styles.css` |
| Bundle | rebuild `main.js` via plugin `build.sh` / sync script |
| SoT | `docs/Furnace Product Shell.md`（§5 通知流、§6、§9、§10 未读决策） |
| Tests | Jest under `src/__tests__/`（notify env + settings 源码契约） |

### Data flow

```text
settings.feishuWebhookUrl / wecomWebhookUrl
        │
        ▼
buildNotifyEnv(settings)
        │  non-empty URL → set *_WEBHOOK_URL
        │  derive channel ids → AIWIKI_NOTIFY_ENABLED_CHANNELS
        ▼
launcher spawn env → notify.py NotifyConfig.from_env()
```

### Error handling

- 无 URL：不注入 enabled channels；runtime 保持「无渠道则直接 return」（现有行为）。
- webhook 推送失败：沿用现有 `notify_failed` / 不重试；本轮不改。
- 迁移：静默 drop legacy keys；无需 Notice。

### Testing

- Jest：`buildNotifyEnv` 单 URL / 双 URL / 全空。
- Jest 源码契约：Integrations 有 webhook 输入；无 Enable toggle / 无 `enabledChannels` 赋值；无 `cliHint` 设置块；`styles.css` 无 `.is-unread`。
- Verify：`bash scripts/verify.sh product-shell-static`；改 SoT 后跑 `bash scripts/docs_consistency_check.sh`（若脚本覆盖该文档）或 `verify_target_rules.sh` 建议 target。
- 不跑真实 webhook；不强制改 dogfood `data.json`（load 自动 drop）。

## Target settings schema (post-change)

仍保留（A 档）：

- `launcherPath`
- `showAdvancedCommands`
- `locale`
- `llmBackend` / `llmModel`
- provider `llm*ApiKey` / `llm*BaseUrl`（4 providers）
- `feishuWebhookUrl` / `wecomWebhookUrl`
- `advancedSectionsExpanded`（内部 UI 状态）

移除：

- `enabledChannels`
- 任何未读 timestamp 字段（含文档中的 `last_viewed_timestamp`）

## Success criteria

- Settings UI 无通知 channel toggle；填 URL 即可推送（经推导 env）。
- SoT 与代码一致：无未读视觉承诺、无 `enabled_channels` settings 字段、schema camelCase。
- 无 `cliHint` 死 UI；无 `.is-unread` CSS。
- `bash scripts/verify.sh product-shell-static` PASS。

## Out of scope

- LLM 凭据 / Base URL 下沉 Advanced 或 env-only（B/C）。
- 删除或跟随宿主的 `locale`。
- 恢复未读 UI。
- 修改 `src/aiwiki/notify.py` 语义（例如「空 enabled 时按 URL 推」）。
- 大改 pending / Today UX（已由 Less-is-More 其它 plan 覆盖）。
- 主动编辑 iCloud dogfood vault（除非 sync script 更新 plugin 链接）。

## Open questions

(none)
