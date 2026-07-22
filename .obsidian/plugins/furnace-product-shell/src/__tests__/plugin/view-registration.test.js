"use strict";

const fs = require("fs");
const path = require("path");

test("plugin view, ribbon, and command registration stays Today-only", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );

  expect(pluginSrc.match(/registerView\s*\(/g) || []).toHaveLength(1);
  expect(pluginSrc.match(/addRibbonIcon\s*\(/g) || []).toHaveLength(1);
  expect(pluginSrc.match(/addCommand\s*\(/g) || []).toHaveLength(2);
  expect(pluginSrc).toMatch(/"open-furnace-center"/);
  expect(pluginSrc).not.toMatch(/"open-recent-runs"/);
  expect(pluginSrc).not.toMatch(/"open-review-center"/);
  expect(pluginSrc).not.toMatch(/"open-execution-center"/);
  expect(pluginSrc).not.toMatch(/RecentRunsView/);
  expect(pluginSrc).not.toMatch(/ReviewCenterView/);
  expect(pluginSrc).not.toMatch(/ExecutionCenterView/);
});

test("advanced command palette stays limited to shell refresh", () => {
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );
  const start = pluginSrc.indexOf("registerAdvancedCommands()");
  const end = pluginSrc.indexOf("registerOpenView(view)", start);
  const body = pluginSrc.slice(start, end);

  expect(body).toMatch(/id: "refresh-furnace-shell"/);
  for (const commandId of [
    "open-recent-runs",
    "open-review-center",
    "open-execution-center",
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

test("settings trim removes recentRunsLimit and groups developer diagnostics", () => {
  const settingsSrc = fs.readFileSync(
    path.resolve(__dirname, "../../settings.js"),
    "utf8"
  );
  const constantsSrc = fs.readFileSync(
    path.resolve(__dirname, "../../constants.js"),
    "utf8"
  );
  const pluginSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin.js"),
    "utf8"
  );
  const pluginStateSrc = fs.readFileSync(
    path.resolve(__dirname, "../../plugin_state.js"),
    "utf8"
  );

  expect(settingsSrc).not.toMatch(/recentRunsLimit/);
  expect(settingsSrc).toMatch(/Developer \/ diagnostics/);
  expect(settingsSrc).toMatch(/Developer diagnostics/);
  const langSectionStart = settingsSrc.indexOf("Language & Appearance");
  const langSectionEnd = settingsSrc.indexOf("Furnace Connection");
  expect(settingsSrc.slice(langSectionStart, langSectionEnd)).not.toMatch(/showAdvancedCommands/);

  expect(constantsSrc).toMatch(/const RECENT_RUNS_LIMIT = 8;/);
  expect(constantsSrc).not.toMatch(/recentRunsLimit:/);

  expect(pluginSrc).toMatch(/RECENT_RUNS_LIMIT/);
  expect(pluginSrc).not.toMatch(/recentRunsLimit/);

  expect(pluginStateSrc).toMatch(/delete plugin\.settings\.recentRunsLimit/);
  expect(pluginStateSrc).toMatch(/legacyRecentRunsLimitMigrated/);
});

test("default furnace center keeps Advanced out of the primary shell path", () => {
  const renderHomeSrc = fs.readFileSync(
    path.resolve(__dirname, "../../render_home.js"),
    "utf8"
  );

  expect(renderHomeSrc).toMatch(/showAdvancedCommands[\s\S]+renderAdvancedDrawer\(plugin, contentEl\)/);
});

test("advanced drawer only exposes diagnostics and inline history", () => {
  const renderAdvancedSrc = fs.readFileSync(
    path.resolve(__dirname, "../../render_advanced.js"),
    "utf8"
  );

  expect(renderAdvancedSrc).not.toMatch(/renderLegacyAdvancedPanel/);
  expect(renderAdvancedSrc).not.toMatch(/开发者操作/);
  expect(renderAdvancedSrc).not.toMatch(/renderAdvancedMetricsPanel/);
  expect(renderAdvancedSrc).not.toMatch(/openExecutionCenterView/);
  expect(renderAdvancedSrc).not.toMatch(/openReviewCenterView/);
  expect(renderAdvancedSrc).not.toMatch(/openRecentRunsView/);
  expect(renderAdvancedSrc).not.toMatch(/execution_controls/);
  expect(renderAdvancedSrc).toMatch(/renderHistorySectionBody/);
  expect(renderAdvancedSrc).toMatch(/pluginState\.recentRuns/);
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

  expect(pluginSrc).toMatch(/running \| done \| failed \| degraded/);
  expect(pluginSrc).toMatch(/isPendingSubmissionDegradedEntry\(entry\)/);
  expect(pendingStateSrc).toMatch(/markPendingSubmissionEntryDone/);
  expect(pendingStateSrc).toMatch(/isPendingSubmissionDegradedEntry\(entry\) \? "degraded" : "done"/);
  expect(pendingStateSrc).toMatch(/entry\.status === "degraded"/);
  expect(pendingStateSrc).toMatch(/llmStatus === "degraded"/);
  expect(pendingStateSrc).toMatch(/artifactQuality/);
  expect(pendingStateSrc).toMatch(/backgroundStatus/);
});
