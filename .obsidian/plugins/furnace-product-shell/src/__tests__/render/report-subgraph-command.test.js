"use strict";

// Unit test for FurnaceProductShellPlugin.runReportSubgraphCommand
// We don't load plugin.js directly (it depends on many concat-time globals).
// Instead we re-implement the method behavior via the same logic shape
// against a stub `this`, then lock the contract by also asserting the
// method body inside the bundled main.js still calls openWorkspacePath
// with payload.output_path.

const fs = require("fs");
const path = require("path");

const { Notice } = require("obsidian");
// satisfy plugin.js global expectations if it ever gets required indirectly
global.Notice = Notice;

function makePlugin(payload) {
  return {
    t: (key) => key,
    runPluginCommand: jest.fn().mockResolvedValue(payload),
    openWorkspacePath: jest.fn().mockResolvedValue(true),
    Notice,
  };
}

// Mirror of runReportSubgraphCommand body (kept in lock-step with plugin.js).
async function runReportSubgraphCommand(self, { reportPath }) {
  const normalized = String(reportPath || "").trim();
  if (!normalized) {
    new Notice(self.t("Report path cannot be empty."));
    return;
  }
  const args = ["report-subgraph", "--report", normalized];
  const payload = await self.runPluginCommand(
    `${self.t("View report graph")}: ${normalized.slice(0, 48)}`,
    args,
    { refreshAfter: true }
  );
  const outputPath =
    payload && typeof payload.output_path === "string" ? payload.output_path.trim() : "";
  if (outputPath) {
    await self.openWorkspacePath(outputPath);
  }
  return payload;
}

describe("runReportSubgraphCommand", () => {
  test("opens generated subgraph via openWorkspacePath on success", async () => {
    const plugin = makePlugin({
      kind: "report-subgraph",
      output_path: "output/reports/foo.subgraph.md",
    });

    const result = await runReportSubgraphCommand(plugin, {
      reportPath: "output/reports/foo.md",
    });

    expect(plugin.runPluginCommand).toHaveBeenCalledTimes(1);
    const [, args] = plugin.runPluginCommand.mock.calls[0];
    expect(args).toEqual(["report-subgraph", "--report", "output/reports/foo.md"]);
    expect(plugin.openWorkspacePath).toHaveBeenCalledWith(
      "output/reports/foo.subgraph.md"
    );
    expect(result.output_path).toBe("output/reports/foo.subgraph.md");
  });

  test("skips openWorkspacePath when payload has no output_path", async () => {
    const plugin = makePlugin(null);
    await runReportSubgraphCommand(plugin, { reportPath: "output/reports/foo.md" });
    expect(plugin.openWorkspacePath).not.toHaveBeenCalled();
  });

  test("does not run CLI when reportPath empty", async () => {
    const plugin = makePlugin({});
    await runReportSubgraphCommand(plugin, { reportPath: "  " });
    expect(plugin.runPluginCommand).not.toHaveBeenCalled();
    expect(plugin.openWorkspacePath).not.toHaveBeenCalled();
  });

  // Contract lock: ensure the real plugin source still wires payload.output_path
  // → openWorkspacePath, so the stubbed body above stays representative.
  test("plugin.js source still calls openWorkspacePath with output_path", () => {
    const pluginSrc = fs.readFileSync(
      path.resolve(__dirname, "../../plugin.js"),
      "utf8"
    );
    expect(pluginSrc).toMatch(/runReportSubgraphCommand[\s\S]{0,800}output_path/);
    expect(pluginSrc).toMatch(
      /runReportSubgraphCommand[\s\S]{0,800}openWorkspacePath\(outputPath\)/
    );
    // i18n contract: the command spec must use English base keys, not Chinese.
    const commandSpecsSrc = fs.readFileSync(
      path.resolve(__dirname, "../../command_specs.js"),
      "utf8"
    );
    expect(commandSpecsSrc).toMatch(/labelKey: "View report graph"/);
    expect(pluginSrc).not.toMatch(/this\.t\("查看报告关系图谱"\)/);
  });

  // Picker contract: openReportSubgraphPicker must surface recent_outputs reports
  // as candidates rather than relying on free-text only.
  test("plugin.js source surfaces recent reports as picker candidates", () => {
    const pluginSrc = fs.readFileSync(
      path.resolve(__dirname, "../../plugin.js"),
      "utf8"
    );
    expect(pluginSrc).toMatch(/collectReportCandidates\s*\(/);
    expect(pluginSrc).toMatch(/recent_outputs/);
    expect(pluginSrc).toMatch(/output\/reports\//);
    expect(pluginSrc).toMatch(/openReportSubgraphPicker[\s\S]{0,1200}collectReportCandidates/);
    expect(pluginSrc).toMatch(/artifact_quality/);
    expect(pluginSrc).toMatch(/contains_llm_placeholder/);
    expect(pluginSrc).toMatch(/"timeout_or_unavailable", "pending", "failed", "degraded"/);
    // Falls back to plain text input only when no candidates exist.
    const modalSpecsSrc = fs.readFileSync(
      path.resolve(__dirname, "../../modal_specs.js"),
      "utf8"
    );
    expect(modalSpecsSrc).toMatch(/No recent reports available; enter a path manually\./);
  });

  // i18n contract lock: cards.js "View graph" button must use English base key.
  test("cards.js source uses English base key for View graph button", () => {
    const cardsSrc = fs.readFileSync(
      path.resolve(__dirname, "../../render/cards.js"),
      "utf8"
    );
    expect(cardsSrc).toMatch(/plugin\.t\("View graph"\)/);
    expect(cardsSrc).not.toMatch(/plugin\.t\("查看关系图谱"\)/);
  });
});
