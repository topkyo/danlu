# Furnace Product Shell — Source Modules

The Obsidian plugin is shipped as a single `main.js` file (Obsidian does not
support relative `require()` within plugins). The source code lives in this
`src/` directory as separate modules for readability and maintenance.

## UI v3 Paradigm (EP-024)
This UI now follows the "Input/Output + Notification" paradigm:
- **AskBox**: Raycast-style single input.
- **UnreadBadge**: Superhuman-style top-right notification badge.
- **ReportCards**: Notion-style outputs, highlighting content.
- **AdvancedDrawer**: All old system dashboards and views have been moved here.

### Where did my dashboards go?
If you are looking for the System Status, LLM Health, Graph Health, Recent Runs, Review Center, Execution Center, or Repair Backlog—they are all collapsed in the **"Advanced"** drawer at the bottom of the home surface.

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
