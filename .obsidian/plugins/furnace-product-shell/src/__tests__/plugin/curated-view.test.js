"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadCuratedViewContext() {
  const context = {
    console,
    String,
    Array,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../curated_view.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "curated_view.js" });
  return context;
}

test("curated output path detection covers judgments and elixirs markdown", () => {
  const context = loadCuratedViewContext();

  expect(context.isCuratedOutputPath("wiki/judgments/judgment-a.md")).toBe(true);
  expect(context.isCuratedOutputPath("wiki/elixirs/elixir-a.md")).toBe(true);
  expect(context.isCuratedOutputPath("wiki/decisions/decision-a.md")).toBe(false);
  expect(context.isCuratedOutputPath("wiki/judgments/judgment-a.txt")).toBe(false);
  expect(context.isCuratedOutputPath("")).toBe(false);
});

test("plugin registers curated leaf sync on workspace lifecycle events", () => {
  const pluginSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin.js"), "utf8");

  expect(pluginSrc).toMatch(/registerCuratedOutputLeafSync\(this\)/);
});
