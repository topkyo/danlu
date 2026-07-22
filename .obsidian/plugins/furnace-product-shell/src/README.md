# Furnace Product Shell — Source Modules

The Obsidian plugin is shipped as a single `main.js` file (Obsidian does not
support relative `require()` within plugins). The source code lives in this
`src/` directory as separate modules for readability and maintenance.

## Product Shell home surface
The AgentOS shell surface is intentionally narrow:
1. **Today Feed** — user-visible outputs, review prompts, and non-degraded activity from the runtime summary.
2. **Universal Input** — the only default input surface; accepts URLs, file drags, raw text notes, and questions through `runUniversalInputCommand`.

Unread reports are local UI state based on `lastViewedTimestamp`: unread cards show
a small dot and stronger title weight, without Notice or Badge behavior.

Universal Input owns URL/file/question routing. Legacy DropZone and start-guide surfaces are not part of the default shell.

Advanced is gated by `showAdvancedCommands` and is limited to diagnostics/history
and refresh. Runtime write operations such as compile/nightly/protocol/apply/revert
are not registered as Product Shell command-palette entries.

Phase B preview: Feishu / WeCom webhook URLs will be configured in plugin settings,
then bridged to the runtime through environment variables for report notifications.

## Module layout

| File | Purpose |
|------|---------|
| `constants.js` | Plugin ID, view types, `DEFAULT_SETTINGS`, `ZH_TEXT` i18n dictionary, status label maps |
| `helpers.js` | Pure helper functions (`truncateText`, `groupReportsByDate`, `countUnreadReports`, …) |
| `command_specs.js` | Pure launcher command argument/label specs for Product Shell actions |
| `pending_state.js` | Pure pending-submission serialization, hydration, and status helpers |
| `context_state.js` | Pure active protocol/file/concept/output context helpers |
| `rewrite_state.js` | Pure rewrite proposal/recovery normalization and extraction helpers |
| `control_items.js` | Pure review/execution control option builders for context pickers |
| `modal_specs.js` | Structured command modal specs for operator actions |
| `run_state.js` | Pure run-record initialization and run-log rendering helpers |
| `state/health-state.js` | Pure LLM health, latest-run, shell-sync, and self-check state helpers |
| `modals.js` | All `Modal` subclasses |
| `views.js` | All `ItemView` subclasses |
| `settings.js` | `FurnaceProductShellSettingTab` |
| `render_*` | Standalone render functions for Today, Universal Input, Advanced diagnostics, runs, and home surfaces |
| `plugin.js` | `FurnaceProductShellPlugin` class — lifecycle, state management, updates |

## Dependency order

The modules are concatenated in this order:

1. `require` statements (added by `build.sh`)
2. `constants.js`
3. `helpers.js`
4. `command_specs.js`
5. `pending_state.js`
6. `context_state.js`
7. `modals.js`
8. `views.js`
9. `settings.js`
10. `render/cards.js`, `render_primitives.js`, `render_input.js`, `render_today.js`, `render_advanced.js`, `render_home.js`
11. `plugin_helpers.js`
12. `rewrite_state.js`
13. `control_items.js`
14. `modal_specs.js`
15. `run_state.js`
16. `state/health-state.js`
17. `plugin.js`

## Building

```bash
bash .obsidian/plugins/furnace-product-shell/build.sh
```

Validate with:
```bash
node --check .obsidian/plugins/furnace-product-shell/main.js
```
