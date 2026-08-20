"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

function loadLifecycleContext() {
  const context = {
    console,
    require,
    fs,
    path,
    setTimeout,
    clearTimeout,
    Notice: class Notice {},
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    RegExp,
    Promise,
    SHELL_SUMMARY_PATH: "output/control/shell-summary.json",
    readJsonText: (raw) => JSON.parse(String(raw || "{}")),
    compoundSuggestItems: jest.fn(() => []),
    normalizeWorkspaceRelativePath: (value) => String(value || "").trim(),
    resolveWorkspaceSnippetPath: jest.fn(() => ""),
    workspaceSnippetFromMarkdown: jest.fn(() => ""),
    appendComposerReportQuote: jest.fn((value) => ({ changed: false, value })),
    normalizeMaterialPaths: jest.fn((values) => (Array.isArray(values) ? values : [])),
    setStickyMaterialRefs: jest.fn(),
    dictItems: jest.fn((value) => (Array.isArray(value) ? value : [])),
  };
  const root = path.resolve(__dirname, "../..");
  for (const relativePath of ["helpers.js", "plugin_lifecycle.js"]) {
    const source = fs.readFileSync(path.join(root, relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  }
  return context;
}

function loadPipelineContext() {
  const context = loadLifecycleContext();
  context.Notice = class Notice {};
  context.notices = [];
  context.compoundSuggestItems = jest.fn(() => []);
  const source = fs.readFileSync(path.resolve(__dirname, "../../plugin_run_pipeline.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "plugin_run_pipeline.js" });
  return context;
}

function createPlugin(overrides = {}) {
  return Object.assign({
    repoState: { valid: true, root: "/tmp/vault", missingPaths: [] },
    shellSummary: null,
    pluginState: { recentRuns: [] },
    app: {
      vault: {
        getAbstractFileByPath: jest.fn(() => ({ path: "output/control/shell-summary.json" })),
        cachedRead: jest.fn(async () => '{"kind":"stale-vault"}'),
      },
    },
    t: (key) => key,
    updateStatusBar: jest.fn(),
    refreshOpenViews: jest.fn(),
    processShellSummaryUpdates: jest.fn(),
    loadShellSummaryFromDisk: jest.fn(async () => null),
    refreshShellSummarySilently: jest.fn(async () => null),
    runPluginCommand: jest.fn(async () => ({ kind: "product-shell-summary", recent_outputs: [{ path: "output/reports/new.md" }] })),
    executeRuntimeCommand: jest.fn(async () => ({
      payload: { kind: "product-shell-summary", recent_outputs: [{ path: "output/reports/runtime.md" }] },
    })),
  }, overrides);
}

describe("shell summary refresh", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test("report vault changes debounce refreshShellSummarySilently", async () => {
    const context = loadLifecycleContext();
    const plugin = createPlugin();

    await context.handleProductShellVaultChange(plugin, "output/reports/ask-1.md");
    expect(plugin.refreshShellSummarySilently).not.toHaveBeenCalled();
    expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(1);

    jest.advanceTimersByTime(599);
    expect(plugin.refreshShellSummarySilently).not.toHaveBeenCalled();

    jest.advanceTimersByTime(1);
    expect(plugin.refreshShellSummarySilently).toHaveBeenCalledTimes(1);
  });

  test("loadShellSummaryFromDisk prefers fs over vault cachedRead", async () => {
    const context = loadLifecycleContext();
    const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "furnace-shell-summary-"));
    const summaryDir = path.join(tmpRoot, "output", "control");
    fs.mkdirSync(summaryDir, { recursive: true });
    const summaryPath = path.join(summaryDir, "shell-summary.json");
    fs.writeFileSync(summaryPath, JSON.stringify({ kind: "product-shell-summary", recent_outputs: [{ path: "output/reports/fs.md" }] }));

    const plugin = createPlugin({
      repoState: { valid: true, root: tmpRoot, missingPaths: [] },
      app: {
        vault: {
          getAbstractFileByPath: jest.fn(() => ({ path: "output/control/shell-summary.json" })),
          cachedRead: jest.fn(async () => JSON.stringify({ kind: "stale-vault" })),
        },
      },
    });

    await context.loadProductShellSummaryFromDisk(plugin);

    expect(plugin.app.vault.cachedRead).not.toHaveBeenCalled();
    expect(plugin.shellSummary).toEqual({
      kind: "product-shell-summary",
      recent_outputs: [{ path: "output/reports/fs.md" }],
    });

    fs.rmSync(tmpRoot, { recursive: true, force: true });
  });

  test("refreshShellSummaryCommand keeps payload when shell-status succeeds", async () => {
    const context = loadPipelineContext();
    const payload = {
      kind: "product-shell-summary",
      recent_outputs: [{ path: "output/reports/payload.md" }],
    };
    const plugin = createPlugin({
      runPluginCommand: jest.fn(async () => {
        plugin.shellSummary = payload;
        return payload;
      }),
      loadShellSummaryFromDisk: jest.fn(async () => {
        plugin.shellSummary = { kind: "stale-disk" };
        return plugin.shellSummary;
      }),
    });

    await context.refreshProductShellSummaryCommand(plugin);

    expect(plugin.runPluginCommand).toHaveBeenCalledTimes(1);
    expect(plugin.loadShellSummaryFromDisk).not.toHaveBeenCalled();
    expect(plugin.shellSummary).toEqual(payload);
  });

  test("refreshShellSummarySilently does not reload disk after runtime payload", async () => {
    const context = loadPipelineContext();
    const payload = {
      kind: "product-shell-summary",
      recent_outputs: [{ path: "output/reports/runtime.md" }],
    };
    const plugin = createPlugin({
      executeRuntimeCommand: jest.fn(async () => ({ payload })),
      loadShellSummaryFromDisk: jest.fn(async () => {
        throw new Error("should not reload disk after payload");
      }),
    });

    const result = await context.refreshProductShellSummarySilently(plugin);

    expect(result).toEqual(payload);
    expect(plugin.loadShellSummaryFromDisk).not.toHaveBeenCalled();
    expect(plugin.shellSummary).toEqual(payload);
  });
});
