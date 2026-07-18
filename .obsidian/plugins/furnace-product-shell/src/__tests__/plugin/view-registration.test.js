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
  expect(pluginSrc.match(/addCommand\s*\(/g) || []).toHaveLength(5);
  expect(pluginSrc).toMatch(/"open-furnace-center"/);
  expect(pluginSrc).toMatch(/"open-recent-runs"/);
  expect(pluginSrc).toMatch(/"open-review-center"/);
  expect(pluginSrc).toMatch(/"open-execution-center"/);
  expect(pluginSrc).toMatch(/EP-005: kept for backward compatibility/);
});

test("advanced command palette stays limited to operator surfaces", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );
  const start = pluginSrc.indexOf("registerAdvancedCommands()");
  const end = pluginSrc.indexOf("registerOpenView(view)", start);
  const body = pluginSrc.slice(start, end);

  for (const commandId of [
    "open-recent-runs",
    "open-review-center",
    "open-execution-center",
    "refresh-furnace-shell",
  ]) {
    expect(body).toMatch(new RegExp(`id: "${commandId}"`));
  }
  for (const commandId of [
    "run-nightly",
    "set-protocol",
    "file-back",
    "review-page",
    "apply-action",
    "revert-action",
    "drop-image",
    "drop-url",
    "drop-file",
    "search-workspace",
  ]) {
    expect(body).not.toMatch(new RegExp(`id: "${commandId}"`));
  }
});

test("public command palette keeps only the Furnace entrypoint", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );
  const start = pluginSrc.indexOf("  registerPublicCommands() {");
  const end = pluginSrc.indexOf("registerAdvancedCommands()", start);
  const body = pluginSrc.slice(start, end);

  expect(body).toMatch(/id: "open-furnace-center"/);
  for (const commandId of [
    "run-compile",
    "run-ask",
    "capture-note",
    "drop-url",
    "drop-file",
    "open-evidence-graph",
  ]) {
    expect(body).not.toMatch(new RegExp(`id: "${commandId}"`));
  }
});

test("default furnace center keeps Advanced out of the primary shell path", () => {
  const renderHomeSrc = fs.readFileSync(
    path.resolve(__dirname, "../../render_home.js"),
    "utf8"
  );

  expect(renderHomeSrc).toMatch(/showAdvancedCommands[\s\S]+renderAdvancedDrawer\(plugin, contentEl\)/);
});

test("advanced drawer only exposes diagnostics and history surfaces", () => {
  const renderAdvancedSrc = fs.readFileSync(
    path.resolve(__dirname, "../../render_advanced.js"),
    "utf8"
  );

  expect(renderAdvancedSrc).not.toMatch(/renderLegacyAdvancedPanel/);
  expect(renderAdvancedSrc).not.toMatch(/开发者操作/);
  expect(renderAdvancedSrc).not.toMatch(/renderAdvancedMetricsPanel/);
  expect(renderAdvancedSrc).not.toMatch(/openExecutionCenterView/);
  expect(renderAdvancedSrc).toMatch(/renderHistorySectionBody/);
  expect(renderAdvancedSrc).toMatch(/openReviewCenterView/);
});

test("digest panel exposes shell recovery commands when available", () => {
  const renderPrimitivesSrc = fs.readFileSync(
    path.resolve(__dirname, "../../render_primitives.js"),
    "utf8"
  );

  expect(renderPrimitivesSrc).toMatch(/nightly\.rerun_command/);
  expect(renderPrimitivesSrc).toMatch(/nightlyReceipt\.rerun_command/);
  expect(renderPrimitivesSrc).toMatch(/watcher\.rerun_command/);
  expect(renderPrimitivesSrc).toMatch(/Rerun command/);
});

test("pending submissions have a first-class degraded terminal state", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );
  const pendingStateSrc = fs.readFileSync(
    path.resolve(__dirname, "../../pending_state.js"),
    "utf8"
  );

  expect(pluginSrc).toMatch(/running \| received \| done \| failed \| degraded/);
  expect(pluginSrc).toMatch(/isPendingSubmissionDegradedEntry\(entry\)/);
  expect(pendingStateSrc).toMatch(/markPendingSubmissionEntryDone/);
  expect(pendingStateSrc).toMatch(/isPendingSubmissionDegradedEntry\(entry\) \? "degraded" : "done"/);
  expect(pendingStateSrc).toMatch(/entry\.status === "degraded"/);
  expect(pendingStateSrc).toMatch(/llmStatus === "degraded"/);
  expect(pendingStateSrc).toMatch(/artifactQuality/);
  expect(pendingStateSrc).toMatch(/backgroundStatus/);
});
