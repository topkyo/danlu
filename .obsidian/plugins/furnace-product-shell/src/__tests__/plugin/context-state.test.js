"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadContextStateContext() {
  const context = {
    console,
    require,
    fs,
    path,
    DEFAULT_PROTOCOLS: ["general"],
    Array,
    String,
    Object,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../context_state.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "context_state.js" });
  return context;
}

test("active protocol helpers use summary values with defaults", () => {
  const context = loadContextStateContext();

  expect(context.getActiveProtocolFromSummary({ active_protocol: "research" })).toBe("research");
  expect(context.getActiveProtocolFromSummary({ active_protocol: "" })).toBe("general");
  expect(context.getAvailableProtocolsFromSummary({ available_protocols: ["product", "", 7, "ops"] })).toEqual([
    "general",
  ]);
  expect(context.getAvailableProtocolsFromSummary({ available_protocols: [] })).toEqual([
    "general",
  ]);
});

test("active file helpers derive concept, output, and curated paths", () => {
  const context = loadContextStateContext();
  const app = { workspace: { getActiveFile: () => ({ path: "wiki/concepts/model-quality.md" }) } };

  expect(context.getActiveFilePathFromApp(app)).toBe("wiki/concepts/model-quality.md");
  expect(context.getConceptSlugForPath("wiki/concepts/model-quality.md")).toBe("model-quality");
  expect(context.getConceptSlugForPath("wiki/sources/model-quality.md")).toBe("");
});

test("curated page helper follows summary roots instead of hardcoded prefixes", () => {
  const context = loadContextStateContext();
  const summary = {
    curated_page_roots: {
      decisions: "wiki/custom-decisions/",
      judgments: "wiki/custom-judgments/",
    },
  };

  expect(context.getCuratedPagePathForSummary("wiki/custom-decisions/a.md", summary)).toBe("wiki/custom-decisions/a.md");
  expect(context.getCuratedPagePathForSummary("wiki/decisions/a.md", summary)).toBe("");
  expect(context.getCuratedPagePathForSummary("wiki/custom-decisions/a.txt", summary)).toBe("");
  expect(context.getCuratedPagePathForSummary("wiki/custom-judgments/a.md", {})).toBe("");
});
