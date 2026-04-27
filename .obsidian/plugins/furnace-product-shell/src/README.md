# Furnace Product Shell — Source Modules

The Obsidian plugin is shipped as a single `main.js` file (Obsidian does not
support relative `require()` within plugins). The source code lives in this
`src/` directory as separate modules for readability and maintenance.

## Product Shell home surface
The M-PS.1 home surface is intentionally linear:
1. **AskBox** — Raycast-style `Ask / Command...` input at the top.
2. **Today's Reports / Previous Reports** — report cards grouped from `recent_outputs`.
3. **DropZone** — `Drop URL / PDF / Image / Repo` ingestion surface.
4. **Advanced** — collapsed drawer for operator/debug surfaces.

Unread reports are local UI state based on `lastViewedTimestamp`: unread cards show
a small dot and stronger title weight, without Notice or Badge behavior.

DropZone accepts URL text plus PDF/image file drags; repo ingestion remains available
through the explicit button/modal path.

Advanced contains System Status, LLM Health, Review Center, Execution Center,
Recent Runs, Refresh/Compile/Nightly, and protocol controls. Old view types and
commands remain registered for command-palette access.

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
| `render.js` | Standalone render functions (AskBox, Reports, DropZone, AdvancedDrawer) |
| `plugin.js` | `FurnaceProductShellPlugin` class — lifecycle, state management, updates |

## Dependency order

The modules are concatenated in this order:

1. `require` statements (added by `build.sh`)
2. `constants.js`
3. `helpers.js`
4. `modals.js`
5. `views.js`
6. `settings.js`
7. `render.js`
8. `plugin.js`

## Building

```bash
bash .obsidian/plugins/furnace-product-shell/build.sh
```

Validate with:
```bash
node --check .obsidian/plugins/furnace-product-shell/main.js
```
