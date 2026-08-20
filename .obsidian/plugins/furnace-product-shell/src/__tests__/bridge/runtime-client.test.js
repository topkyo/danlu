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
    execLauncher: jest.fn(),
  }, overrides);
  context.globalThis = context;
  const source = fs.readFileSync(path.resolve(__dirname, "../../bridge/runtime_client.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "runtime_client.js" });
  return Object.assign(context, context.module.exports);
}

test("DesktopLauncherClient delegates exec to launcher bridge", async () => {
  const execLauncher = jest.fn(async (plugin, args) => ({ payload: { ok: true, args } }));
  const context = loadRuntimeClientContext({ execLauncher });
  const plugin = { settings: {} };

  const client = context.createRuntimeClient(plugin);
  const result = await client.exec(["shell-status"]);

  expect(client).toBeInstanceOf(context.DesktopLauncherClient);
  expect(execLauncher).toHaveBeenCalledWith(plugin, ["shell-status"]);
  expect(result.payload).toEqual({ ok: true, args: ["shell-status"] });
});
