"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

function loadRunLogPersistenceContext() {
  const context = {
    console,
    require,
    fs,
    path,
    Date,
    Math,
    Intl,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    RegExp,
    Set,
    Map,
  };
  [
    "constants.js",
    "helpers.js",
    "plugin_helpers.js",
    "rewrite_state.js",
    "run_state.js",
    "run_log_persistence.js",
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

const t = (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? ""));

test("resolveProductShellRunLogPath preserves existing workspace-relative behavior", () => {
  const context = loadRunLogPersistenceContext();

  expect(context.resolveProductShellRunLogPath("/vault", "output/control/plugin-runs/run-1.md"))
    .toBe(path.join("/vault", "output/control/plugin-runs/run-1.md"));
  expect(context.resolveProductShellRunLogPath("", "output/control/plugin-runs/run-1.md")).toBe("");
  expect(context.resolveProductShellRunLogPath("/vault", "")).toBe("");
});

test("persistProductShellRunLog is a no-op and does not write plugin-runs md", () => {
  const context = loadRunLogPersistenceContext();
  const repoRoot = fs.mkdtempSync(path.join(os.tmpdir(), "furnace-run-log-"));
  const record = {
    id: "run-1",
    status: "success",
    protocol: "product",
    backend: "opencode-api",
    model: "deepseek-v4-pro",
    args: "run-ask hello",
    exitCode: 0,
    startedAt: "2026-05-25T00:00:00Z",
    finishedAt: "2026-05-25T00:00:01Z",
    logPath: "output/control/plugin-runs/run-1.md",
    timeline: [{ at: "2026-05-25T00:00:00Z", stage: "Submitted", summary: "run-ask hello" }],
  };

  const logPath = context.persistProductShellRunLog({
    record,
    details: { stdoutRaw: "ok" },
    t,
    repoRoot,
  });

  expect(logPath).toBe("");
  expect(record.logPath).toBe("");
  expect(fs.existsSync(path.join(repoRoot, "output/control/plugin-runs/run-1.md"))).toBe(false);
});
