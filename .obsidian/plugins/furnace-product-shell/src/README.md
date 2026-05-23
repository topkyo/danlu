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

Advanced is gated by `showAdvancedCommands` and is limited to diagnostics/history,
Recent Runs, Review Center, Execution Center, and refresh. Runtime write operations
such as compile/nightly/protocol/apply/revert are not registered as Product Shell
command-palette entries.

Phase B preview: Feishu / WeCom webhook URLs will be configured in plugin settings,
then bridged to the runtime through environment variables for report notifications.

## Module layout

| File | Purpose |
|------|---------|
| `constants.js` | Plugin ID, view types, `DEFAULT_SETTINGS`, `ZH_TEXT` i18n dictionary, status label maps |
| `helpers.js` | Pure helper functions (`truncateText`, `groupReportsByDate`, `countUnreadReports`, …) |
| `modals.js` | All `Modal` subclasses |
| `views.js` | All `ItemView` subclasses |
| `settings.js` | `FurnaceProductShellSettingTab` |
| `render_*` | Standalone render functions for Today, Universal Input, Advanced diagnostics, runs, review, and execution surfaces |
| `plugin.js` | `FurnaceProductShellPlugin` class — lifecycle, state management, updates |

## Dependency order

The modules are concatenated in this order:

1. `require` statements (added by `build.sh`)
2. `constants.js`
3. `helpers.js`
4. `modals.js`
5. `views.js`
6. `settings.js`
7. `render/cards.js`, `render_primitives.js`, `render_input.js`, `render_today.js`, `render_advanced.js`, `render_runs.js`, `render_home.js`, `render_review.js`, `render_execution.js`
8. `plugin_helpers.js`
9. `plugin.js`

## Building

```bash
bash .obsidian/plugins/furnace-product-shell/build.sh
```

Validate with:
```bash
node --check .obsidian/plugins/furnace-product-shell/main.js
```
