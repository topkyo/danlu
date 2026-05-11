"use strict";

const fs = require("fs");
const path = require("path");

test("plugin view, ribbon, and backward-compat command registration stays locked", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );

  expect(pluginSrc.match(/registerView\s*\(/g) || []).toHaveLength(4);
  expect(pluginSrc.match(/addRibbonIcon\s*\(/g) || []).toHaveLength(1);
  expect(pluginSrc.match(/addCommand\s*\(/g) || []).toHaveLength(31);
  expect(pluginSrc).toMatch(/"open-furnace-center"/);
  expect(pluginSrc).toMatch(/"open-recent-runs"/);
  expect(pluginSrc).toMatch(/"open-review-center"/);
  expect(pluginSrc).toMatch(/"open-execution-center"/);
  expect(pluginSrc).toMatch(/EP-005: kept for backward compatibility/);
});
