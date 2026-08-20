"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadPendingRuntimeContext() {
  const context = {
    console,
    require,
    fs,
    path,
    Date,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    Set,
    Promise,
    window: {
      setInterval: jest.fn(),
      clearInterval: jest.fn(),
    },
    pendingHasActiveAsk: jest.fn(() => false),
    createPendingSubmissionEntry: jest.fn((payload) => payload),
    resetPendingSubmissionEntryForRetry: jest.fn(),
    markPendingSubmissionEntryDone: jest.fn(() => true),
    markPendingSubmissionEntryFailed: jest.fn(),
    updatePendingSubmissionEntryRunNotes: jest.fn(),
    updatePendingSubmissionEntryArtifactMeta: jest.fn(),
    reconcilePendingSubmissionList: jest.fn(() => ({ remaining: [], hits: [] })),
    truncateText: (value) => String(value || ""),
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../pending_runtime.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "pending_runtime.js" });
  return context;
}

function createPlugin(overrides = {}) {
  return Object.assign({
    pendingSubmissions: [],
    savePluginState: jest.fn(() => Promise.resolve()),
    refreshOpenViews: jest.fn(),
  }, overrides);
}

test("ensurePendingSubmissionRuntimeList initializes plugin list", () => {
  const context = loadPendingRuntimeContext();
  const plugin = createPlugin({ pendingSubmissions: null });

  const list = context.ensurePendingSubmissionRuntimeList(plugin);

  expect(Array.isArray(list)).toBe(true);
  expect(plugin.pendingSubmissions).toBe(list);
});

test("find and remove pending runtime entries mutate plugin list", () => {
  const context = loadPendingRuntimeContext();
  const plugin = createPlugin({
    pendingSubmissions: [{ id: "p1" }, { id: "p2" }],
  });

  expect(context.findPendingSubmissionRuntimeEntry(plugin, "p2")).toEqual({ id: "p2" });
  expect(context.removePendingSubmissionRuntimeEntry(plugin, "p1")).toBe(true);
  expect(plugin.pendingSubmissions).toEqual([{ id: "p2" }]);
  expect(context.removePendingSubmissionRuntimeEntry(plugin, "missing")).toBe(false);
});

test("commitPendingSubmissionRuntimeChange honors save and refresh flags", () => {
  const context = loadPendingRuntimeContext();
  const plugin = createPlugin();

  context.commitPendingSubmissionRuntimeChange(plugin, { save: false, refresh: true });

  expect(plugin.savePluginState).not.toHaveBeenCalled();
  expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(1);

  context.commitPendingSubmissionRuntimeChange(plugin);

  expect(plugin.savePluginState).toHaveBeenCalledTimes(1);
  expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(2);
});
