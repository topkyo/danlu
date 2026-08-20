// Render primitives shared by Product Shell sections.

function renderPanel(plugin, container, title, description = "", options = {}) {
  const panel = container.createDiv({ cls: "furnace-shell-panel" });
  const header = panel.createDiv({ cls: "furnace-shell-panel-header" });
  const copy = header.createDiv({ cls: "furnace-shell-panel-copy" });
  copy.createEl("h3", { cls: "furnace-shell-panel-title", text: plugin.t(title) });
  if (description) {
    copy.createDiv({ cls: "furnace-shell-panel-description", text: plugin.t(description) });
  }
  if (options.action) {
    const actionButton = header.createEl("button", {
      cls: "furnace-shell-panel-link",
      text: plugin.t(options.action.label),
    });
    actionButton.addEventListener("click", () => {
      plugin.runUiAction(() => options.action.onClick(), plugin.t(options.action.label));
    });
  }
  return panel;
}

function renderInlineButtons(plugin, container, buttons, cls = "furnace-shell-panel-actions") {
  const actions = container.createDiv({ cls });
  buttons.forEach((buttonConfig) => {
    const button = actions.createEl("button", { text: plugin.t(buttonConfig.label) });
    if (buttonConfig.cta) {
      button.addClass("mod-cta");
    }
    if (buttonConfig.kind === "ghost") {
      button.addClass("furnace-shell-ghost-button");
    }
    button.addEventListener("click", () => {
      plugin.runUiAction(() => buttonConfig.onClick(), plugin.t(buttonConfig.label));
    });
  });
  return actions;
}

function renderPill(plugin, container, text, extraClass = "") {
  const pill = container.createEl("span", { cls: "furnace-shell-pill", text: String(text || "") });
  if (extraClass) {
    pill.addClass(extraClass);
  }
  return pill;
}

function llmHealthToneClass(status) {
  if (status === "healthy") {
    return "is-healthy";
  }
  if (status === "warning") {
    return "is-warning";
  }
  if (status === "degraded") {
    return "is-degraded";
  }
  if (status === "failed") {
    return "is-degraded";
  }
  return "is-unknown";
}

function syncToneClass(status) {
  if (status === "healthy") {
    return "is-healthy";
  }
  if (status === "running") {
    return "is-running";
  }
  // EP-015: currentShellSyncState() is summary-only and only returns
  // running / healthy / unknown. There is no "failed" domain state anymore.
  return "is-unknown";
}

function formatBackendFallbackReadiness(plugin, fallback) {
  if (!fallback || typeof fallback !== "object") return "";
  const backend = String(fallback.backend || "").trim() || plugin.t("unconfigured");
  const model = String(fallback.model || "").trim();
  const available = Boolean(fallback.available);
  const configured = Boolean(fallback.configured);
  const reason = String(fallback.reason || "").trim();
  const state = available
    ? plugin.t("available")
    : configured
      ? plugin.t("configured but unavailable")
      : plugin.t("not configured");
  const route = model ? `${backend}/${model}` : backend;
  return reason ? `${route}: ${state} (${reason})` : `${route}: ${state}`;
}

function renderBackendFallbackReadiness(plugin, container, llmStatus) {
  const fallbacks = llmStatus && Array.isArray(llmStatus.backend_fallbacks)
    ? llmStatus.backend_fallbacks.filter((item) => item && typeof item === "object")
    : [];
  if (!fallbacks.length) {
    container.createDiv({ cls: "furnace-shell-panel-note", text: plugin.t("No backup LLM route configured.") });
    return;
  }
  const readyCount = fallbacks.filter((item) => Boolean(item.available)).length;
  const summary = readyCount > 0
    ? plugin.t("Backup LLM route ready: {count}/{total}", { count: readyCount, total: fallbacks.length })
    : plugin.t("Backup LLM route not ready.");
  container.createDiv({ cls: "furnace-shell-panel-note", text: summary });
  const list = container.createDiv({ cls: "furnace-shell-inline-list furnace-shell-inline-list-compact" });
  fallbacks.slice(0, 3).forEach((fallback) => {
    const item = list.createDiv({ cls: "furnace-shell-inline-item" });
    const text = formatBackendFallbackReadiness(plugin, fallback);
    item.createDiv({ cls: "furnace-shell-meta", text });
  });
}

function renderStatusPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "System status", "Make runtime state explicit before you act.");
  const runningCount = plugin.pluginState.recentRuns.filter((entry) => entry.status === "running").length;
  const llmStatus = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.llm_status || {} : {};
  const llmHealth = plugin.currentLlmHealth();
  const syncState = plugin.currentShellSyncState();
  const statusText = runningCount
    ? plugin.t("{count} command(s) running right now.", { count: runningCount })
    : plugin.t("No command is currently running.");
  panel.createDiv({ cls: "furnace-shell-panel-note", text: statusText });
  if (runningCount) {
    panel.createDiv({
      cls: "furnace-shell-panel-note furnace-shell-status-running",
      text: plugin.t("Single writer active: avoid compile / nightly / alchemy / file-back from two surfaces at once."),
    });
  }
  const meta = [
    `${plugin.t("Protocol")} ${plugin.t(plugin.getActiveProtocol())}`,
    `${plugin.t("LLM Backend")} ${llmStatus.backend || plugin.t("unconfigured")}`,
  ];
  if (llmStatus.model) {
    meta.push(`${plugin.t("LLM Model")} ${llmStatus.model}`);
  }
  panel.createDiv({ cls: "furnace-shell-meta", text: meta.join(" | ") });

  const healthBox = panel.createDiv({ cls: "furnace-shell-health-box" });
  const healthPills = healthBox.createDiv({ cls: "furnace-shell-pill-row" });
  plugin.renderPill(
    healthPills,
    `${plugin.t("Sync")} ${plugin.t(syncState.status || "unknown")}`,
    syncToneClass(syncState.status)
  );
  plugin.renderPill(
    healthPills,
    `${plugin.t("LLM health")} ${plugin.t(llmHealth.status || "unknown")}`,
    llmHealthToneClass(llmHealth.status)
  );
  if (llmHealth.fallbackCommand) {
    plugin.renderPill(healthPills, plugin.t("LLM failure notice active"), "is-degraded");
  }
  const routeParts = [];
  if (syncState.checkedAt) {
    routeParts.push(`${plugin.t("Last sync")} ${formatDisplayTime(syncState.checkedAt, plugin.locale()) || syncState.checkedAt}`);
  }
  if (llmHealth.backend || llmHealth.model) {
    routeParts.push(
      `${plugin.t("Configured route")} ${[llmHealth.backend || plugin.t("unconfigured"), llmHealth.model || plugin.t("default")].join(" · ")}`
    );
  }
  if (llmHealth.checkedAt) {
    routeParts.push(`${plugin.t("Last checked")} ${formatDisplayTime(llmHealth.checkedAt, plugin.locale()) || llmHealth.checkedAt}`);
  }
  if (routeParts.length) {
    healthBox.createDiv({ cls: "furnace-shell-meta", text: routeParts.join(" | ") });
  }
  healthBox.createDiv({
    // EP-015: syncState.status ∈ {running, healthy, unknown}; no failed branch.
    cls: "furnace-shell-panel-note",
    text: plugin.t(syncState.reason || "Summary unavailable. The panel will sync automatically when possible."),
  });
  healthBox.createDiv({
    cls: llmHealth.status === "degraded" ? "furnace-shell-panel-note furnace-shell-status-failed" : "furnace-shell-panel-note",
    text: plugin.t(llmHealth.reason || "No recent LLM health check yet."),
  });
  renderBackendFallbackReadiness(plugin, healthBox, llmStatus);
  const healthActions = [];
  if (llmHealth.rerunCommand) {
    healthActions.push({
      label: "Copy command",
      kind: "ghost",
      onClick: async () => plugin.copyText(llmHealth.rerunCommand),
    });
  }
  if (llmHealth.resultPath) {
    healthActions.push({
      label: "Copy result path",
      kind: "ghost",
      onClick: async () => plugin.copyText(llmHealth.resultPath),
    });
  }
  if (llmHealth.receiptPath) {
    healthActions.push({
      label: "Copy receipt path",
      kind: "ghost",
      onClick: async () => plugin.copyText(llmHealth.receiptPath),
    });
  }
  if (llmHealth.stderrRaw || llmHealth.stderrSummary) {
    healthActions.push({
      label: "Copy stderr",
      kind: "ghost",
      onClick: async () => plugin.copyText(llmHealth.stderrRaw || llmHealth.stderrSummary),
    });
  }
  if (llmHealth.logPath) {
    healthActions.push({
      label: "Open log",
      kind: "ghost",
      onClick: async () => plugin.openWorkspacePath(llmHealth.logPath),
    });
  }
  if (healthActions.length) {
    plugin.renderInlineButtons(healthBox, healthActions, "furnace-shell-inline-actions furnace-shell-inline-actions-compact");
  }
  plugin.renderInlineButtons(panel, [
    { label: "Refresh Furnace Shell", onClick: async () => plugin.refreshShellSummaryCommand() },
  ]);
}
