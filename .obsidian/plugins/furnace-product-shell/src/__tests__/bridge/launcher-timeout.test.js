"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { EventEmitter } = require("events");

const LAUNCHER_TIMEOUT_MS = 180000;
const LAUNCHER_MAX_OUTPUT_BYTES = 4 * 1024 * 1024;

function createFakeChild() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = jest.fn();
  return child;
}

function createPlugin() {
  return {
    t: (text, variables = {}) => String(text).replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? "")),
    repoState: {
      valid: true,
      root: "/vault",
      launcherPath: "/repo/scripts/aiwiki-launcher.sh",
      missingPaths: [],
    },
    settings: {},
  };
}

function loadLauncherContext(overrides = {}) {
  const context = Object.assign({
    console,
    Promise,
    Error,
    Object,
    Array,
    String,
    module: { exports: {} },
    exports: {},
    setTimeout,
    clearTimeout,
    spawn: jest.fn(),
    readJsonText: (rawText) => {
      const text = String(rawText || "").trim();
      if (!text) {
        return null;
      }
      return JSON.parse(text);
    },
    buildLlmEnv: jest.fn(() => ({})),
    clearKnownLlmEnv: jest.fn(),
    buildNotifyEnv: jest.fn(() => ({})),
    process: { env: {} },
  }, overrides);
  context.globalThis = context;
  const source = fs.readFileSync(path.resolve(__dirname, "../../bridge/launcher.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "launcher.js" });
  return Object.assign(context, context.module.exports);
}

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

test("execLauncher rejects with code timeout and kills the child when the command hangs", async () => {
  const context = loadLauncherContext();
  const child = createFakeChild();
  context.spawn.mockReturnValue(child);

  const pending = context.execLauncher(createPlugin(), ["today"]);
  const captured = pending.catch((error) => error);
  child.stdout.emit("data", "partial stdout");
  child.stderr.emit("data", "partial stderr");

  jest.advanceTimersByTime(LAUNCHER_TIMEOUT_MS);

  const error = await captured;
  expect(error).toBeInstanceOf(Error);
  expect(error.code).toBe("timeout");
  expect(error.message).toContain("timed out");
  expect(error.stdout).toBe("partial stdout");
  expect(error.stderr).toBe("partial stderr");
  expect(child.kill).toHaveBeenCalledWith("SIGTERM");

  // A late close after the timeout kill must not settle the promise again.
  child.emit("close", null);
  await expect(pending).rejects.toMatchObject({ code: "timeout" });
});

test("execLauncher rejects with code output-overflow when stdout exceeds the cap", async () => {
  const context = loadLauncherContext();
  const child = createFakeChild();
  context.spawn.mockReturnValue(child);

  const pending = context.execLauncher(createPlugin(), ["today"]);
  const captured = pending.catch((error) => error);

  child.stdout.emit("data", "x".repeat(LAUNCHER_MAX_OUTPUT_BYTES + 1));

  const error = await captured;
  expect(error.code).toBe("output-overflow");
  expect(error.stdout.length).toBeGreaterThan(LAUNCHER_MAX_OUTPUT_BYTES);
  expect(child.kill).toHaveBeenCalledWith("SIGTERM");
});

test("execLauncher rejects with code output-overflow when stderr exceeds the cap", async () => {
  const context = loadLauncherContext();
  const child = createFakeChild();
  context.spawn.mockReturnValue(child);

  const pending = context.execLauncher(createPlugin(), ["today"]);
  const captured = pending.catch((error) => error);

  child.stderr.emit("data", "e".repeat(LAUNCHER_MAX_OUTPUT_BYTES + 1));

  const error = await captured;
  expect(error.code).toBe("output-overflow");
  expect(child.kill).toHaveBeenCalledWith("SIGTERM");
});

test("execLauncher resolves with payload null and warns when exit-0 stdout is not JSON", async () => {
  const context = loadLauncherContext();
  const child = createFakeChild();
  context.spawn.mockReturnValue(child);
  const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});

  const pending = context.execLauncher(createPlugin(), ["today"]);
  child.stdout.emit("data", "this is not json");
  child.emit("close", 0);

  const result = await pending;
  expect(result.code).toBe(0);
  expect(result.payload).toBeNull();
  expect(result.stdout).toBe("this is not json");
  expect(warnSpy).toHaveBeenCalledTimes(1);
  expect(warnSpy.mock.calls[0][0]).toBe("[furnace-product-shell] launcher returned non-JSON stdout");
});

test("execLauncher resolves valid JSON and clears the timeout timer", async () => {
  const context = loadLauncherContext();
  const child = createFakeChild();
  context.spawn.mockReturnValue(child);
  const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});

  const pending = context.execLauncher(createPlugin(), ["today"]);
  child.stdout.emit("data", JSON.stringify({ ok: true, answer: "42" }));
  child.emit("close", 0);

  const result = await pending;
  expect(result.code).toBe(0);
  expect(result.payload).toEqual({ ok: true, answer: "42" });
  expect(warnSpy).not.toHaveBeenCalled();

  // The timer was cleared: advancing past the timeout must not kill or reject.
  jest.advanceTimersByTime(LAUNCHER_TIMEOUT_MS * 2);
  expect(child.kill).not.toHaveBeenCalled();
  await expect(pending).resolves.toMatchObject({ code: 0 });
});
