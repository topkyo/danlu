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
    updateLongRunningPoller: jest.fn(),
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

test("commitPendingSubmissionRuntimeChange honors save refresh and poller flags", () => {
  const context = loadPendingRuntimeContext();
  const plugin = createPlugin();

  context.commitPendingSubmissionRuntimeChange(plugin, { save: false, refresh: true, poller: false });

  expect(plugin.savePluginState).not.toHaveBeenCalled();
  expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(1);
  expect(plugin.updateLongRunningPoller).not.toHaveBeenCalled();

  context.commitPendingSubmissionRuntimeChange(plugin);

  expect(plugin.savePluginState).toHaveBeenCalledTimes(1);
  expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(2);
  expect(plugin.updateLongRunningPoller).toHaveBeenCalledTimes(1);
});
