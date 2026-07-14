"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadPluginHelpersContext() {
  const context = {
    console,
    require,
    fs,
    path,
    Array,
    String,
    Number,
    Object,
    Set,
    Date,
    RegExp,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../plugin_helpers.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "plugin_helpers.js" });
  return context;
}

test("known report id update ignores invalid summaries", () => {
  const context = loadPluginHelpersContext();

  expect(context.knownReportIdsUpdateFromSummary(null, ["old"])).toEqual({ shouldSave: false, ids: [] });
  expect(context.knownReportIdsUpdateFromSummary({}, ["old"])).toEqual({ shouldSave: false, ids: [] });
});

test("known report id update tracks empty and first report lists", () => {
  const context = loadPluginHelpersContext();

  expect(context.knownReportIdsUpdateFromSummary({ recent_outputs: [] }, ["old"])).toEqual({
    shouldSave: true,
    ids: [],
  });
  expect(context.knownReportIdsUpdateFromSummary({
    recent_outputs: [
      { path: "output/reports/a.md" },
      { title: "Report B" },
      { created_at: "2026-05-25T00:00:00Z" },
      null,
    ],
  }, [])).toEqual({
    shouldSave: true,
    ids: ["output/reports/a.md", "Report B", "2026-05-25T00:00:00Z"],
  });
});

test("known report id update saves new ids and order changes only when needed", () => {
  const context = loadPluginHelpersContext();

  expect(context.knownReportIdsUpdateFromSummary({
    recent_outputs: [{ path: "a" }, { path: "b" }],
  }, ["a", "b"])).toEqual({
    shouldSave: false,
    ids: ["a", "b"],
  });
  expect(context.knownReportIdsUpdateFromSummary({
    recent_outputs: [{ path: "b" }, { path: "a" }],
  }, ["a", "b"])).toEqual({
    shouldSave: true,
    ids: ["b", "a"],
  });
  expect(context.knownReportIdsUpdateFromSummary({
    recent_outputs: [{ path: "a" }, { path: "c" }],
  }, ["a", "b"])).toEqual({
    shouldSave: true,
    ids: ["a", "c"],
  });
});

test("workspace snippet path resolver rejects empty, absolute, and escaping paths", () => {
  const context = loadPluginHelpersContext();
  const root = path.resolve("/tmp/furnace-vault");

  expect(context.normalizeWorkspaceRelativePath(" wiki/../HOME.md ")).toBe("HOME.md");
  expect(context.normalizeWorkspaceRelativePath("/tmp/furnace-vault/HOME.md")).toBe("");
  expect(context.normalizeWorkspaceRelativePath("../outside.md")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, "")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, "/tmp/furnace-vault/HOME.md")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, "../outside.md")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, "wiki/../../outside.md")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, ".")).toBe("");
  expect(context.resolveWorkspaceSnippetPath(root, "wiki/../HOME.md")).toBe(path.join(root, "HOME.md"));
});

test("workspace markdown snippet strips frontmatter, headings, whitespace, and truncates", () => {
  const context = loadPluginHelpersContext();

  expect(context.workspaceSnippetFromMarkdown([
    "---",
    "title: Demo",
    "---",
    "# Heading",
    "",
    "  First line.  ",
    "Second    line.",
  ].join("\n"))).toBe("First line. Second line.");

  expect(context.workspaceSnippetFromMarkdown("alpha beta gamma", 8)).toBe("alpha b…");
  expect(context.workspaceSnippetFromMarkdown("alpha", 0)).toBe("alpha");
});

test("composer report quote update appends once and preserves duplicates", () => {
  const context = loadPluginHelpersContext();

  expect(context.appendComposerReportQuote("", "引用报告：output/reports/r.md")).toEqual({
    changed: true,
    value: "引用报告：output/reports/r.md\n",
  });
  expect(context.appendComposerReportQuote("已有问题  \n", "引用报告：output/reports/r.md")).toEqual({
    changed: true,
    value: "已有问题\n引用报告：output/reports/r.md\n",
  });
  expect(context.appendComposerReportQuote(
    "已有问题\n  引用报告：output/reports/r.md  \n",
    "引用报告：output/reports/r.md"
  )).toEqual({
    changed: false,
    value: "已有问题\n  引用报告：output/reports/r.md  \n",
  });
  expect(context.appendComposerReportQuote("已有问题", "")).toEqual({
    changed: false,
    value: "已有问题",
  });
});
