"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadRuntimeClientContext(overrides = {}) {
  const context = Object.assign({
    console,
    Date,
    Math,
    Set,
    String,
    JSON,
    Promise,
    Error,
    module: { exports: {} },
    exports: {},
    SHELL_SUMMARY_PATH: "output/control/shell-summary.json",
    execLauncher: jest.fn(),
    pluginVaultRoot: jest.fn(() => ""),
    nodeFs: jest.fn(() => fs),
    nodePath: jest.fn(() => path),
  }, overrides);
  context.globalThis = context;
  const source = fs.readFileSync(path.resolve(__dirname, "../../bridge/runtime_client.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "runtime_client.js" });
  return Object.assign(context, context.module.exports);
}

function createAdapter() {
  const files = new Map();
  const dirs = new Set();
  return {
    files,
    dirs,
    exists: jest.fn(async (target) => dirs.has(target) || files.has(target)),
    mkdir: jest.fn(async (target) => {
      dirs.add(target);
    }),
    write: jest.fn(async (target, content) => {
      files.set(target, content);
    }),
    read: jest.fn(async (target) => files.get(target)),
  };
}

test("DesktopLauncherClient delegates exec to launcher bridge", async () => {
  const execLauncher = jest.fn(async (plugin, args) => ({ payload: { ok: true, args } }));
  const context = loadRuntimeClientContext({ execLauncher });
  const plugin = { settings: { runtimeClientMode: "desktop-launcher" } };

  const client = context.createRuntimeClient(plugin);
  const result = await client.exec(["shell-status"]);

  expect(client).toBeInstanceOf(context.DesktopLauncherClient);
  expect(execLauncher).toHaveBeenCalledWith(plugin, ["shell-status"]);
  expect(result.payload).toEqual({ ok: true, args: ["shell-status"] });
});

test("VaultQueueClient enqueues ask without reporting execution success", async () => {
  const context = loadRuntimeClientContext();
  const adapter = createAdapter();
  const plugin = {
    settings: { runtimeClientMode: "vault-queue" },
    app: { vault: { adapter } },
  };

  const client = context.createRuntimeClient(plugin);
  const result = await client.exec(["run-ask-submit", "What changed?", "--format", "report"]);

  expect(client).toBeInstanceOf(context.VaultQueueClient);
  expect(result.payload.status).toBe("queued");
  expect(result.payload.queue_path).toMatch(/^\.aiwiki\/queue\/.+\.json$/);
  const queued = JSON.parse(adapter.files.get(result.payload.queue_path));
  expect(queued).toMatchObject({
    version: 1,
    kind: "ask",
    status: "pending",
    source: "companion",
    payload: { argv: ["run-ask-submit", "What changed?", "--format", "report"] },
  });
  expect(queued.id).toBe(result.payload.id);
  expect(queued.created_at).toEqual(expect.any(String));
});

test("VaultQueueClient uses note kind for markdown drops", async () => {
  const context = loadRuntimeClientContext();
  const adapter = createAdapter();
  const plugin = {
    settings: { runtimeClientMode: "vault-queue" },
    app: { vault: { adapter } },
  };

  const result = await context.createRuntimeClient(plugin).exec(["drop", "markdown", "--text", "hello"]);
  const queued = JSON.parse(adapter.files.get(result.payload.queue_path));

  expect(queued.kind).toBe("note");
  expect(result.payload.status).toBe("queued");
});

test("VaultQueueClient.drop(request) queues markdown as note with argv", async () => {
  const context = loadRuntimeClientContext();
  const adapter = createAdapter();
  const plugin = {
    settings: { runtimeClientMode: "vault-queue" },
    app: { vault: { adapter } },
  };

  const result = await context.createRuntimeClient(plugin).drop({
    kind: "markdown",
    title: "demo",
    source: "",
  });
  const queued = JSON.parse(adapter.files.get(result.payload.queue_path));

  expect(result.payload.status).toBe("queued");
  expect(queued.kind).toBe("note");
  expect(queued.payload.argv[0]).toBe("drop");
  expect(queued.payload.argv[1]).toBe("markdown");
});

test("VaultQueueClient reads shell summary without queueing", async () => {
  const context = loadRuntimeClientContext();
  const adapter = createAdapter();
  adapter.files.set("output/control/shell-summary.json", JSON.stringify({ kind: "product-shell-summary", status: "ok" }));
  const plugin = {
    settings: { runtimeClientMode: "vault-queue" },
    app: { vault: { adapter } },
  };

  const result = await context.createRuntimeClient(plugin).exec(["shell-status"]);

  expect(result.payload).toEqual({ kind: "product-shell-summary", status: "ok" });
  expect(adapter.write).not.toHaveBeenCalled();
});
