# Furnace Product Shell — Source Modules

The Obsidian plugin is shipped as a single `main.js` file (Obsidian does not
support relative `require()` within plugins).  The source code lives in this
`src/` directory as separate modules for readability and maintenance.

## Module layout

| File | Purpose |
|------|---------|
| `constants.js` | Plugin ID, view types, `DEFAULT_SETTINGS`, `ZH_TEXT` i18n dictionary, status label maps |
| `helpers.js` | Pure helper functions (`truncateText`, `readJsonText`, `normalizeLocale`, `t`, `formatDisplayTime`, …) |
| `modals.js` | All `Modal` subclasses (Ask, CaptureNote, Protocol, Search, DropUrl, DropFile, DropImage, StructuredCommand, ContextPicker) |
| `views.js` | All `ItemView` subclasses (FurnaceCenter, RecentRuns, ReviewCenter, ExecutionCenter) |
| `settings.js` | `FurnaceProductShellSettingTab` |
| `render.js` | Standalone render functions extracted from the plugin class; each takes `(plugin, …)` as first argument |
| `plugin.js` | `FurnaceProductShellPlugin` class — lifecycle, commands, state management, thin render wrappers |

## Dependency order

The modules are concatenated in this order so that every symbol is defined
before it is referenced:

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
# From the plugin directory:
bash build.sh

# Or from the repo root:
bash .obsidian/plugins/furnace-product-shell/build.sh
```

The script writes `main.js` in the plugin directory.  Validate with:

```bash
node --check .obsidian/plugins/furnace-product-shell/main.js
```

## Design notes

- **No module system between files** — Obsidian loads only `main.js`, so the
  build script concatenates the source files into a single CommonJS module.
  Individual source files must not use `require()` or `module.exports` for
  inter-module communication.
- **Render extraction** — render methods are extracted from the plugin class
  into standalone `function renderXxx(plugin, ...)` functions.  The plugin
  class retains thin wrappers that delegate to these functions so that view
  classes can still call `this.plugin.renderFurnaceCenter(contentEl)`.
- **i18n** — the free function `t(locale, text, vars)` is defined in
  `helpers.js` and used everywhere.  The plugin class provides a convenience
  `this.t(text, vars)` that curries in the current locale.
