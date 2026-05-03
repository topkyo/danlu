// Recent run list and run detail rendering helpers.
function renderRecentRuns(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.createEl("h2", { text: plugin.t("Recent Runs") });

  const pluginRunsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  pluginRunsSection.createEl("h3", { text: plugin.t("Plugin-triggered Commands") });
  if (!plugin.pluginState.recentRuns.length) {
    pluginRunsSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No plugin-triggered commands yet.") });
  } else {
    const list = pluginRunsSection.createEl("ul", { cls: "furnace-shell-list" });
    plugin.pluginState.recentRuns.forEach((record) => {
      const item = list.createEl("li");
      renderRunDetail(plugin, item, record);
    });
  }

  const runtimeSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  runtimeSection.createEl("h3", { text: plugin.t("Runtime Events from shell-summary") });
  const runtimeEvents = plugin.shellSummary && Array.isArray(plugin.shellSummary.recent_runs) ? plugin.shellSummary.recent_runs : [];
  if (!runtimeEvents.length) {
    runtimeSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No shell summary recent runs are available.") });
  } else {
    const list = runtimeSection.createEl("ul", { cls: "furnace-shell-list" });
    runtimeEvents.forEach((entry) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: entry.title || plugin.t(entry.event_type || "runtime-event") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t(entry.event_type || "event")} | ${plugin.t(entry.protocol || "general")} | ${entry.occurred_at || plugin.t("unknown")}`,
      });
      const pathValue = entry.output_path || entry.receipt_path || entry.page_path || entry.path || "";
      if (pathValue) {
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const button = actions.createEl("button", { text: plugin.t("Open") });
        button.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(pathValue), `Open runtime event path: ${pathValue}`);
        });
      }
    });
  }

  const receiptSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  receiptSection.createEl("h3", { text: plugin.t("Recent Receipts") });
  const receipts = plugin.shellSummary && Array.isArray(plugin.shellSummary.recent_receipts) ? plugin.shellSummary.recent_receipts : [];
  if (!receipts.length) {
    receiptSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent receipts are available.") });
  } else {
    const list = receiptSection.createEl("ul", { cls: "furnace-shell-list" });
    receipts.forEach((receipt) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: receipt.title || receipt.subject_id || plugin.t("receipt") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t(receipt.operation || "operation")} | ${plugin.t(receipt.protocol || "general")} | ${receipt.applied_at || plugin.t("unknown")}`,
      });
      if (receipt.receipt_path) {
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const button = actions.createEl("button", { text: plugin.t("Open receipt") });
        button.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(receipt.receipt_path), `Open receipt: ${receipt.receipt_path}`);
        });
        const copyButton = actions.createEl("button", { text: plugin.t("Copy receipt path") });
        copyButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.copyText(receipt.receipt_path), `Copy receipt path: ${receipt.receipt_path}`);
        });
        const revealButton = actions.createEl("button", { text: plugin.t("Reveal receipt") });
        revealButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.revealWorkspacePath(receipt.receipt_path), `Reveal receipt: ${receipt.receipt_path}`);
        });
      }
    });
  }
}

function runStatusClass(status) {
  if (status === "success") {
    return "furnace-shell-status-ok";
  }
  if (status === "failed") {
    return "furnace-shell-status-failed";
  }
  return "furnace-shell-status-running";
}

function renderRunTimeline(plugin, container, record, compact = false) {
  const timeline = Array.isArray(record.timeline) ? record.timeline : [];
  const section = container.createDiv({ cls: "furnace-shell-run-timeline" });
  section.createDiv({ cls: "furnace-shell-inline-heading", text: plugin.t("Stage timeline") });
  if (!timeline.length) {
    section.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No stage events recorded.") });
    return section;
  }
  const list = section.createEl("ul", { cls: "furnace-shell-run-timeline-list" });
  const visibleEvents = compact ? timeline.slice(-4) : timeline;
  visibleEvents.forEach((event) => {
    const item = list.createEl("li", { cls: "furnace-shell-run-event" });
    const statusCls = event.status === "failed" ? "furnace-shell-status-failed" : (event.status === "success" ? "furnace-shell-status-ok" : "furnace-shell-status-running");
    item.addClass(statusCls);
    const header = item.createDiv({ cls: "furnace-shell-run-event-header" });
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

function renderRunDetail(plugin, container, record, options = {}) {
  const compact = Boolean(options.compact);
  const detail = container.createDiv({ cls: compact ? "furnace-shell-run-card is-compact" : "furnace-shell-run-card" });
  const header = detail.createDiv({ cls: "furnace-shell-run-header" });
  header.createEl("strong", { text: plugin.t(record.label || record.args || "command") });
  header.createDiv({
    cls: `furnace-shell-meta ${runStatusClass(record.status)}`,
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

  const contextParts = [];
  if (record.protocol) {
    contextParts.push(plugin.t("protocol {value}", { value: plugin.t(record.protocol) }));
  }
  if (record.backend) {
    contextParts.push(plugin.t("backend {value}", { value: record.backend }));
  }
  if (record.model) {
    contextParts.push(plugin.t("model {value}", { value: record.model }));
  }
  if (!compact && record.modelSelected && record.modelFinal && record.modelSelected !== record.modelFinal) {
    contextParts.push(`${plugin.t("selected")} ${record.modelSelected} -> ${plugin.t("final")} ${record.modelFinal}`);
  }
  if (contextParts.length) {
    detail.createDiv({ cls: "furnace-shell-meta", text: contextParts.join(" | ") });
  }

  if (!compact) {
    const diagnosticParts = [];
    if (record.codexReasoningEffort) {
      diagnosticParts.push(plugin.t("codex effort {value}", { value: record.codexReasoningEffort }));
    }
    if (record.promptProfile) {
      diagnosticParts.push(plugin.t("prompt {value}", { value: record.promptProfile }));
    }
    if (record.retryPromptProfile) {
      diagnosticParts.push(plugin.t("retry {value}", { value: record.retryPromptProfile }));
    }
    if (record.fallbackStage) {
      diagnosticParts.push(plugin.t("fallback {value}", { value: record.fallbackStage }));
    }
    if (diagnosticParts.length) {
      detail.createDiv({ cls: "furnace-shell-meta", text: diagnosticParts.join(" | ") });
    }
  }

  const rewriteSummary = plugin.rewriteProposalSummary(record);
  if (rewriteSummary && !compact) {
    detail.createDiv({ cls: "furnace-shell-meta", text: rewriteSummary });
  }

  if (compact) {
    const compactSummary = [
      rewriteSummary,
      record.resultPath || "",
      record.receiptPath || "",
      record.errorSummary || "",
      record.stderrSummary || "",
    ].find((value) => String(value || "").trim());
    if (compactSummary) {
      detail.createDiv({ cls: "furnace-shell-panel-note furnace-shell-run-summary", text: compactSummary });
    }
  } else {
    renderRunTimeline(plugin, detail, record, compact);
  }

  if (!compact && record.stdoutSummary) {
    detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("stdout: {value}", { value: record.stdoutSummary }) });
  }
  if (!compact && record.stderrSummary) {
    detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("stderr: {value}", { value: record.stderrSummary }) });
  }
  if (!compact && record.errorSummary) {
    detail.createDiv({ cls: "furnace-shell-meta", text: plugin.t("error: {value}", { value: record.errorSummary }) });
  }

  const actions = detail.createDiv({ cls: "furnace-shell-inline-actions" });
  const rewriteProposalObjects = Array.isArray(record.rewriteProposalObjects) ? record.rewriteProposalObjects : [];
  const rewriteProposalPaths = rewriteProposalObjects.length
    ? plugin.rewriteProposalPathsFromObjects(rewriteProposalObjects)
    : (Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths : []);
  if (!compact && Array.isArray(record.argv) && record.argv.length) {
    const rerunButton = actions.createEl("button", { text: plugin.t("Re-run") });
    rerunButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.rerunRecord(record), `Re-run: ${record.args}`);
    });
    const copyCommandButton = actions.createEl("button", { text: plugin.t("Copy command") });
    copyCommandButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.copyText(record.args), `Copy command: ${record.args}`);
    });
  }
  if (rewriteProposalPaths.length && !compact) {
    const firstProposalPath = rewriteProposalObjects[0] && rewriteProposalObjects[0].proposalPath
      ? rewriteProposalObjects[0].proposalPath
      : rewriteProposalPaths[0];
    const proposalButton = actions.createEl("button", { text: plugin.t("Open proposal") });
    proposalButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(firstProposalPath), `Open rewrite proposal: ${firstProposalPath}`);
    });
  }
  if (rewriteProposalPaths.length) {
    const reviewRewriteButton = actions.createEl("button", { text: plugin.t("Review Rewrite") });
    reviewRewriteButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openRewriteRecovery(record), `Rewrite recovery: ${record.args || record.command}`);
    });
  }
  if (rewriteProposalPaths.length > 1 && !compact) {
    const reviewCenterButton = actions.createEl("button", { text: plugin.t("Open Review Center") });
    reviewCenterButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openReviewCenterView(), plugin.t("Open Review Center"));
    });
  }
  if (record.resultPath) {
    const outputButton = actions.createEl("button", { text: plugin.t("Open result") });
    outputButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(record.resultPath), `Open result: ${record.resultPath}`);
    });
    const copyResultPathButton = actions.createEl("button", { text: plugin.t("Copy result path") });
    copyResultPathButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.copyText(record.resultPath), `Copy result path: ${record.resultPath}`);
    });
    const revealResultButton = actions.createEl("button", { text: plugin.t("Reveal result") });
    revealResultButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.revealWorkspacePath(record.resultPath), `Reveal result: ${record.resultPath}`);
    });
  }
  if (record.receiptPath) {
    const receiptButton = actions.createEl("button", { text: plugin.t("Open receipt") });
    receiptButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(record.receiptPath), `Open receipt: ${record.receiptPath}`);
    });
    const copyReceiptPathButton = actions.createEl("button", { text: plugin.t("Copy receipt path") });
    copyReceiptPathButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.copyText(record.receiptPath), `Copy receipt path: ${record.receiptPath}`);
    });
    const revealReceiptButton = actions.createEl("button", { text: plugin.t("Reveal receipt") });
    revealReceiptButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.revealWorkspacePath(record.receiptPath), `Reveal receipt: ${record.receiptPath}`);
    });
  }
  if (!compact && (record.stderrRaw || record.stderrSummary)) {
    const copyStderrButton = actions.createEl("button", { text: plugin.t("Copy stderr") });
    copyStderrButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.copyText(record.stderrRaw || record.stderrSummary), `Copy stderr: ${record.args}`);
    });
  }
  if (!compact && record.logPath) {
    const logButton = actions.createEl("button", { text: plugin.t("Open log") });
    logButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(record.logPath), `Open log: ${record.logPath}`);
    });
  }
  if (options.includeOpenRecentRuns) {
    const recentRunsButton = actions.createEl("button", { text: plugin.t("Open Recent Runs") });
    recentRunsButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openRecentRunsView(), plugin.t("Open Recent Runs"));
    });
  }
  return detail;
}
