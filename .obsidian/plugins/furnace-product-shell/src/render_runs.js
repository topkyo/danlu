// Simplified Recent Runs — only latest runs with basic status.
// renderRunDetail / renderRunTimeline helpers kept for cross-module use.

function renderRecentRuns(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.createEl("h2", { text: plugin.t("Recent Runs") });

  if (!plugin.repoState.valid) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("Vault runtime unavailable. Missing scaffold or launcher: {missing}", {
        missing: plugin.repoState.missingPaths.join(", "),
      }),
    });
    return;
  }

  plugin.renderActionButtons(contentEl, [
    { label: "Refresh", cta: true, onClick: async () => plugin.refreshShellSummaryCommand() },
    { label: "Furnace Center", onClick: async () => plugin.openFurnaceCenterView() },
  ]);

  var section = contentEl.createDiv({ cls: "furnace-shell-section" });
  section.createEl("h3", { text: plugin.t("最近运行") });

  if (!plugin.pluginState.recentRuns.length) {
    section.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No plugin-triggered commands yet.") });
    return;
  }

  var list = section.createEl("ul", { cls: "furnace-shell-list" });
  plugin.pluginState.recentRuns.slice(0, 5).forEach(function (record) {
    var item = list.createEl("li");
    var label = record.command || record.label || plugin.t("command");
    var status = record.status || "unknown";
    var metaText = plugin.t(status) + " | " + (record.finishedAt || "");
    item.createEl("strong", { text: label });
    item.createDiv({ cls: "furnace-shell-meta", text: metaText });
  });
}

function runStatusClass(status) {
  if (status === "success") return "furnace-shell-status-ok";
  if (status === "failed") return "furnace-shell-status-failed";
  return "furnace-shell-status-running";
}

function renderRunTimeline(plugin, container, record, compact) {
  compact = Boolean(compact);
  var timeline = Array.isArray(record.timeline) ? record.timeline : [];
  var section = container.createDiv({ cls: "furnace-shell-run-timeline" });
  section.createDiv({ cls: "furnace-shell-inline-heading", text: plugin.t("Stage timeline") });
  if (!timeline.length) {
    section.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No stage events recorded.") });
    return section;
  }
  var list = section.createEl("ul", { cls: "furnace-shell-run-timeline-list" });
  var visibleEvents = compact ? timeline.slice(-4) : timeline;
  visibleEvents.forEach(function (event) {
    var item = list.createEl("li", { cls: "furnace-shell-run-event" });
    var statusCls = event.status === "failed" ? "furnace-shell-status-failed" : (event.status === "success" ? "furnace-shell-status-ok" : "furnace-shell-status-running");
    item.addClass(statusCls);
    var header = item.createDiv({ cls: "furnace-shell-run-event-header" });
    header.createEl("strong", { text: plugin.t(event.stage || "event") });
    if (event.at) {
      header.createDiv({ cls: "furnace-shell-meta", text: formatDisplayTime(event.at, plugin.locale()) });
    }
    if (event.summary) {
      item.createDiv({ cls: "furnace-shell-meta furnace-shell-code", text: event.summary });
    }
  });
  return section;
}

function renderRunDetail(plugin, container, record, options) {
  options = options || {};
  var compact = Boolean(options.compact);
  var detail = container.createDiv({ cls: compact ? "furnace-shell-run-card is-compact" : "furnace-shell-run-card" });
  var header = detail.createDiv({ cls: "furnace-shell-run-header" });
  header.createEl("strong", { text: plugin.t(record.label || record.args || "command") });
  header.createDiv({
    cls: "furnace-shell-meta " + runStatusClass(record.status),
    text: plugin.t("status {status} | started {started}{finished}", {
      status: plugin.t(record.status || "unknown"),
      started: formatDisplayTime(record.startedAt, plugin.locale()) || plugin.t("unknown"),
      finished: record.finishedAt
        ? plugin.t(" | finished {finished}", { finished: formatDisplayTime(record.finishedAt, plugin.locale()) || record.finishedAt })
        : "",
    }),
  });

  if (!compact && record.args) {
    detail.createDiv({ cls: "furnace-shell-code", text: record.args });
  }

  var contextParts = [];
  if (record.protocol) contextParts.push(plugin.t("protocol {value}", { value: plugin.t(record.protocol) }));
  if (record.backend) contextParts.push(plugin.t("backend {value}", { value: record.backend }));
  if (record.model) contextParts.push(plugin.t("model {value}", { value: record.model }));
  if (!compact && record.modelSelected && record.modelFinal && record.modelSelected !== record.modelFinal) {
    contextParts.push(plugin.t("selected") + " " + record.modelSelected + " -> " + plugin.t("final") + " " + record.modelFinal);
  }
  if (contextParts.length) detail.createDiv({ cls: "furnace-shell-meta", text: contextParts.join(" | ") });

  if (!compact) {
    var diagnosticParts = [];
    if (record.codexReasoningEffort) diagnosticParts.push(plugin.t("codex effort {value}", { value: record.codexReasoningEffort }));
    if (record.promptProfile) diagnosticParts.push(plugin.t("prompt {value}", { value: record.promptProfile }));
    if (record.retryPromptProfile) diagnosticParts.push(plugin.t("retry {value}", { value: record.retryPromptProfile }));
    if (record.fallbackStage) diagnosticParts.push(plugin.t("fallback {value}", { value: record.fallbackStage }));
    if (diagnosticParts.length) detail.createDiv({ cls: "furnace-shell-meta", text: diagnosticParts.join(" | ") });
  }

  var rewriteSummary = plugin.rewriteProposalSummary(record);
  if (rewriteSummary && !compact) detail.createDiv({ cls: "furnace-shell-meta", text: rewriteSummary });

  if (compact) {
    var compactSummary = [rewriteSummary, record.resultPath || "", record.receiptPath || "", record.errorSummary || "", record.stderrSummary || ""].find(function (value) { return String(value || "").trim(); });
    if (compactSummary) detail.createDiv({ cls: "furnace-shell-panel-note furnace-shell-run-summary", text: compactSummary });
  } else {
    renderRunTimeline(plugin, detail, record, compact);
  }

  if (!compact && record.stdoutSummary) detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("stdout: {value}", { value: record.stdoutSummary }) });
  if (!compact && record.stderrSummary) detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("stderr: {value}", { value: record.stderrSummary }) });
  if (!compact && record.errorSummary) detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("error: {value}", { value: record.errorSummary }) });

  var actions = detail.createDiv({ cls: "furnace-shell-inline-actions" });
  var rewriteProposalObjects = Array.isArray(record.rewriteProposalObjects) ? record.rewriteProposalObjects : [];
  var rewriteProposalPaths = rewriteProposalObjects.length
    ? plugin.rewriteProposalPathsFromObjects(rewriteProposalObjects)
    : (Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths : []);

  if (!compact && Array.isArray(record.argv) && record.argv.length) {
    var rerunButton = actions.createEl("button", { text: plugin.t("Re-run") });
    rerunButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.rerunRecord(record); }, "Re-run: " + record.args); });
    var copyCmdButton = actions.createEl("button", { text: plugin.t("Copy command") });
    copyCmdButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.copyText(record.args); }, "Copy command: " + record.args); });
  }

  if (rewriteProposalPaths.length && !compact) {
    var firstProposalPath = rewriteProposalObjects[0] && rewriteProposalObjects[0].proposalPath ? rewriteProposalObjects[0].proposalPath : rewriteProposalPaths[0];
    var proposalButton = actions.createEl("button", { text: plugin.t("Open proposal") });
    proposalButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openWorkspacePath(firstProposalPath); }, "Open rewrite proposal: " + firstProposalPath); });
  }

  if (rewriteProposalPaths.length) {
    var reviewRewriteButton = actions.createEl("button", { text: plugin.t("Review Rewrite") });
    reviewRewriteButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openRewriteRecovery(record); }, "Rewrite recovery: " + (record.args || record.command)); });
  }

  if (record.resultPath) {
    var outputButton = actions.createEl("button", { text: plugin.t("Open result") });
    outputButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openWorkspacePath(record.resultPath); }, "Open result: " + record.resultPath); });
    var copyResultButton = actions.createEl("button", { text: plugin.t("Copy result path") });
    copyResultButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.copyText(record.resultPath); }, "Copy result path: " + record.resultPath); });
    var revealResultButton = actions.createEl("button", { text: plugin.t("Reveal result") });
    revealResultButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.revealWorkspacePath(record.resultPath); }, "Reveal result: " + record.resultPath); });
  }

  if (record.receiptPath) {
    var receiptButton = actions.createEl("button", { text: plugin.t("Open receipt") });
    receiptButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openWorkspacePath(record.receiptPath); }, "Open receipt: " + record.receiptPath); });
    var copyReceiptButton = actions.createEl("button", { text: plugin.t("Copy receipt path") });
    copyReceiptButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.copyText(record.receiptPath); }, "Copy receipt path: " + record.receiptPath); });
    var revealReceiptButton = actions.createEl("button", { text: plugin.t("Reveal receipt") });
    revealReceiptButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.revealWorkspacePath(record.receiptPath); }, "Reveal receipt: " + record.receiptPath); });
  }

  if (!compact && (record.stderrRaw || record.stderrSummary)) {
    var copyStderrButton = actions.createEl("button", { text: plugin.t("Copy stderr") });
    copyStderrButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.copyText(record.stderrRaw || record.stderrSummary); }, "Copy stderr: " + record.args); });
  }

  if (!compact && record.logPath) {
    var logButton = actions.createEl("button", { text: plugin.t("Open log") });
    logButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openWorkspacePath(record.logPath); }, "Open log: " + record.logPath); });
  }

  if (options.includeOpenRecentRuns) {
    var recentRunsButton = actions.createEl("button", { text: plugin.t("Open Recent Runs") });
    recentRunsButton.addEventListener("click", function () { plugin.runUiAction(function () { return plugin.openRecentRunsView(); }, "Open Recent Runs"); });
  }

  return detail;
}
