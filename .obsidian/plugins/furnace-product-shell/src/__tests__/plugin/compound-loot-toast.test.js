"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadPipelineContext() {
  const notices = [];
  const context = {
    console,
    require,
    module: { exports: {} },
    exports: {},
    Notice: class Notice {
      constructor(message) {
        notices.push(String(message || ""));
      }
    },
    notices,
    Set,
    Map,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    RegExp,
  };
  const root = path.resolve(__dirname, "../..");
  for (const relativePath of ["today_feed.js", "plugin_run_pipeline.js"]) {
    context.module = { exports: {} };
    context.exports = context.module.exports;
    const source = fs.readFileSync(path.join(root, relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
    Object.assign(context, context.module.exports || {});
  }
  return context;
}

test("compound loot toast fires once per action path", () => {
  const context = loadPipelineContext();
  const plugin = {
    t: (key) => key,
    reconcilePendingSubmissions: jest.fn(),
  };
  const summary = {
    compound_suggest: {
      available: true,
      items: [
        { action: "alchemy-start", report_path: "output/reports/a.md", corpus_id: "c1" },
        { action: "file-back-judgment", report_path: "output/reports/b.md" },
      ],
    },
  };

  context.processProductShellSummaryUpdates(plugin, summary);
  expect(context.notices).toEqual(["✦ 可凝丹", "✦ 可沉淀"]);
  expect(plugin.reconcilePendingSubmissions).toHaveBeenCalledWith(summary);

  context.processProductShellSummaryUpdates(plugin, summary);
  expect(context.notices).toEqual(["✦ 可凝丹", "✦ 可沉淀"]);
});
