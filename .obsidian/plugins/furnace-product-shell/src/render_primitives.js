// Render primitives shared by Product Shell sections.

function renderCardGrid(plugin, container, cards) {
  const grid = container.createDiv({ cls: "furnace-shell-grid" });
  cards.forEach((card) => {
    const cardEl = grid.createDiv({ cls: "furnace-shell-card" });
    cardEl.createDiv({ cls: "furnace-shell-card-label", text: plugin.t(card.label) });
    const valueText = typeof card.value === "string" ? plugin.t(card.value) : String(card.value);
    cardEl.createDiv({ cls: "furnace-shell-card-value", text: valueText });
  });
}

function renderActionButtons(plugin, container, buttons) {
  const actions = container.createDiv({ cls: "furnace-shell-actions" });
  buttons.forEach((buttonConfig) => {
    const localizedLabel = plugin.t(buttonConfig.label);
    const button = actions.createEl("button", { text: localizedLabel });
    if (buttonConfig.cta) {
      button.addClass("mod-cta");
    }
    button.addEventListener("click", () => {
      plugin.runUiAction(() => buttonConfig.onClick(), localizedLabel);
    });
  });
}

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

function renderMainHeader(plugin, container) {
  const header = container.createDiv({ cls: "furnace-shell-main-header" });
  const copy = header.createDiv({ cls: "furnace-shell-main-copy" });
  copy.createEl("h2", { text: plugin.t("Furnace") });
  copy.createDiv({ cls: "furnace-shell-main-subtitle", text: path.basename(plugin.repoState.root || "") || plugin.repoState.root || "" });

  const badges = header.createDiv({ cls: "furnace-shell-pill-row" });
  plugin.renderPill(badges, plugin.t(plugin.getActiveProtocol()));
  const llmStatus = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.llm_status || {} : {};
  if (llmStatus.backend) {
    plugin.renderPill(badges, llmStatus.backend);
  }
  const runningCount = plugin.pluginState.recentRuns.filter((entry) => entry.status === "running").length;
  if (runningCount) {
    plugin.renderPill(badges, `${runningCount} ${plugin.t("running")}`, "is-running");
  }
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
      text: plugin.t("Single writer active: avoid compile / nightly / apply / revert from two surfaces at once."),
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

function renderSuggestedNextActionsBlock(plugin, container, options = {}) {
  const maxItems = Number.isFinite(Number(options.maxItems)) ? Math.max(1, Number(options.maxItems)) : 2;
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  const actions = summary && Array.isArray(summary.suggested_next_actions) ? summary.suggested_next_actions : [];
  if (!actions.length) {
    return false;
  }
  const list = container.createDiv({ cls: "furnace-shell-inline-list" });
  actions.slice(0, maxItems).forEach((action) => {
    const item = list.createDiv({ cls: "furnace-shell-inline-item" });
    const copy = item.createDiv({ cls: "furnace-shell-output-copy" });
    copy.createEl("strong", { text: action.title || action.path || plugin.t("Next Action") });
    const metaParts = [];
    if (action.kind) {
      metaParts.push(plugin.t(action.kind));
    }
    if (action.reason) {
      metaParts.push(plugin.t("reason {value}", { value: action.reason }));
    }
    if (action.path) {
      metaParts.push(action.path);
    }
    if (metaParts.length) {
      copy.createDiv({ cls: "furnace-shell-meta", text: metaParts.join(" | ") });
    }
    const buttons = item.createDiv({ cls: "furnace-shell-inline-actions furnace-shell-inline-actions-compact" });
    if (action.kind === "compound-suggest") {
      const compoundAction = String(action.action || "").trim();
      if (compoundAction === "file-back-judgment") {
        const fileBackBtn = buttons.createEl("button", { text: plugin.t("沉淀"), cls: "mod-cta" });
        fileBackBtn.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.runCompoundFileBack(action), `Compound file-back: ${action.title || action.path}`);
        });
      } else if (compoundAction === "alchemy-start") {
        const alchemyBtn = buttons.createEl("button", { text: plugin.t("凝丹"), cls: "mod-cta" });
        alchemyBtn.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openCompoundAlchemyStart(action), `Compound alchemy-start: ${action.title || action.path}`);
        });
      }
    }
    if (action.path) {
      const openButton = buttons.createEl("button", { text: plugin.t("Open") });
      openButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openWorkspacePath(action.path), `Open next action path: ${action.path}`);
      });
    }
    if (action.command) {
      const copyButton = buttons.createEl("button", { text: plugin.t("Copy command") });
      copyButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.copyText(action.command), `Copy next action command: ${action.command}`);
      });
    }
  });
  return true;
}

function renderDigestRow(plugin, container, label, value) {
  const row = container.createDiv({ cls: "furnace-shell-digest-row" });
  row.createDiv({ cls: "furnace-shell-digest-label", text: plugin.t(label) });
  row.createDiv({ cls: "furnace-shell-digest-value", text: value });
}

function renderDigestPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Daily Digest", "A compact pulse for knowledge, review, and nightly health.");
  if (!plugin.shellSummary) {
    panel.createDiv({ cls: "furnace-shell-empty", text: plugin.t("Summary unavailable. The panel will sync automatically when possible.") });
    plugin.renderInlineButtons(panel, [
      { label: "Compile", cta: true, onClick: async () => plugin.runCompileCommand() },
      { label: "Sync now", kind: "ghost", onClick: async () => plugin.refreshShellSummaryCommand() },
    ]);
    return;
  }

  const knowledgeStats = plugin.shellSummary.knowledge_stats || {};
  const review = plugin.shellSummary.review_backlog_counts || {};
  const aging = plugin.shellSummary.aging_summary || {};
  const nightly = plugin.shellSummary.nightly || {};
  const watcher = plugin.shellSummary.watcher || {};
  const llmStatus = plugin.shellSummary.llm_status || {};
  const lintCounts = nightly.lint_counts || {};
  const lintTotal = sumNumericValues(lintCounts);
  const nightlyReceipt = nightly.llm_receipt || {};
  const rerunCommand = String(
    nightly.rerun_command
      || nightlyReceipt.rerun_command
      || watcher.rerun_command
      || nightly["recovery_" + "command"]
      || nightlyReceipt["recovery_" + "command"]
      || watcher["recovery_" + "command"]
      || ""
  ).trim();

  plugin.renderDigestRow(
    panel,
    "Knowledge Base",
    `${knowledgeStats.source_nodes || 0} ${plugin.t("Sources")} · ${knowledgeStats.concept_nodes || 0} ${plugin.t("Concepts")} · ${knowledgeStats.judgments || 0} ${plugin.t("Judgments")} · ${knowledgeStats.decisions || 0} ${plugin.t("Decisions")}`
  );
  plugin.renderDigestRow(
    panel,
    "Review queue",
    `${Number(review.pending_decisions || 0) + Number(review.pending_judgments || 0)} ${plugin.t("Pending Reviews")} · ${aging.overdue_count || 0} ${plugin.t("Overdue")} · ${aging.escalated_count || 0} ${plugin.t("Escalation")}`
  );
  plugin.renderDigestRow(
    panel,
    "Execution queue",
    `${plugin.t("Protocol")} ${plugin.t(plugin.getActiveProtocol())} · ${plugin.t("LLM Backend")} ${llmStatus.backend || plugin.t("unconfigured")}`
  );
  plugin.renderDigestRow(
    panel,
    "Nightly",
    nightly.available
      ? `${lintTotal || 0} ${plugin.t("warnings")} · ${formatDisplayTime(nightly.generated_at, plugin.locale()) || plugin.t("healthy")}`
      : plugin.t("No nightly state yet.")
  );
  if (rerunCommand) {
    renderDigestRow(plugin, panel, "Rerun command", rerunCommand);
  }
  panel.createDiv({
    cls: "furnace-shell-panel-note",
    text: `${plugin.t("Last sync")} ${formatDisplayTime(plugin.shellSummary.generated_at, plugin.locale()) || plugin.t("unknown")}`,
  });
}

function isHttpUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (error) {
    return false;
  }
}
