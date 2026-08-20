"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadLauncherBridgeContext(overrides = {}) {
  const spawn = jest.fn(() => {
    const handlers = {};
    return {
      stdout: { on: jest.fn() },
      stderr: { on: jest.fn() },
      on(event, fn) {
        handlers[event] = fn;
      },
      emitClose(code = 0) {
        if (handlers.close) handlers.close(code);
      },
    };
  });
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
    spawn,
    path,
    guiPatchedPath: jest.fn((pathValue) => pathValue),
    resolvePythonBin: jest.fn(() => "/opt/homebrew/bin/python3"),
    readJsonText: jest.fn(() => ({ ok: true })),
    buildLlmEnv: jest.fn(() => ({
      AIWIKI_LLM_BACKEND: "deepseek-api",
      AIWIKI_LLM_MODEL: "deepseek-v4-pro",
      AIWIKI_DEEPSEEK_API_KEY: "sk-test",
    })),
    clearKnownLlmEnv: jest.fn(),
    buildNotifyEnv: jest.fn(() => ({})),
    process: { env: { PATH: "/usr/bin" } },
  }, overrides);
  context.globalThis = context;
  const source = fs.readFileSync(path.resolve(__dirname, "../../bridge/launcher.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "launcher.js" });
  return Object.assign(context, context.module.exports);
}

function makePlugin() {
  return {
    t: (text) => text,
    repoState: {
      valid: true,
      root: "/vault/obsidian",
      runtimeRoot: "/repo",
      missingPaths: [],
    },
    settings: {
      llmBackend: "deepseek-api",
      llmModel: "deepseek-v4-pro",
      llmDeepseekApiKey: "sk-test",
    },
  };
}

test("execLauncher spawns python -m aiwiki.cli with vault root and selected LLM backend env", async () => {
  const context = loadLauncherBridgeContext();
  const plugin = makePlugin();

  const pending = context.execLauncher(plugin, ["run-ask", "hello", "--format", "report", "--lean"]);
  const spawned = context.spawn.mock.results[0].value;
  spawned.emitClose(0);
  await pending;

  expect(context.spawn).toHaveBeenCalledTimes(1);
  const [bin, argv, options] = context.spawn.mock.calls[0];
  expect(bin).toBe("/opt/homebrew/bin/python3");
  expect(argv).toEqual(["-m", "aiwiki.cli", "--root", "/vault/obsidian", "advanced", "run-ask", "hello", "--format", "report", "--lean"]);
  expect(options.cwd).toBe("/repo");
  expect(options.env.PYTHONPATH).toBe("/repo/src");
  expect(context.clearKnownLlmEnv).toHaveBeenCalled();
  expect(context.buildLlmEnv).toHaveBeenCalledWith(plugin.settings);
  expect(options.env.AIWIKI_VAULT).toBe("/vault/obsidian");
  expect(options.env.AIWIKI_LLM_BACKEND).toBe("deepseek-api");
  expect(options.env.AIWIKI_LLM_MODEL).toBe("deepseek-v4-pro");
  expect(options.env.AIWIKI_DEEPSEEK_API_KEY).toBe("sk-test");
});

test("execLauncher keeps advanced-prefixed primary commands unchanged", async () => {
  const context = loadLauncherBridgeContext();
  const plugin = makePlugin();

  const pending = context.execLauncher(plugin, ["advanced", "run-ask", "q"]);
  context.spawn.mock.results[0].value.emitClose(0);
  await pending;

  expect(context.spawn.mock.calls[0][1]).toEqual(["-m", "aiwiki.cli", "--root", "/vault/obsidian", "advanced", "run-ask", "q"]);
});

test("execLauncher rejects before spawn when no Python >= 3.10 is available", async () => {
  const context = loadLauncherBridgeContext({ resolvePythonBin: jest.fn(() => "") });
  await expect(context.execLauncher(makePlugin(), ["today"])).rejects.toThrow(/Python >= 3\.10/);
  expect(context.spawn).not.toHaveBeenCalled();
});
