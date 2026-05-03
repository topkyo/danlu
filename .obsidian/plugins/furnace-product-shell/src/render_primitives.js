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

function renderGettingStartedSection(plugin, container) {
  const section = container.createDiv({ cls: "furnace-shell-section" });
  section.createEl("h3", { text: plugin.t("Start Here") });
  section.createDiv({
    cls: "furnace-shell-meta",
    text: plugin.t("Obsidian Product Shell and the launcher CLI share the same runtime: Ask works from both sides, and ingest can happen through Capture Note / raw/inbox / drop-*."),
  });
  const steps = section.createEl("ol");
  steps.createEl("li", { text: plugin.t("Click Refresh first so shell-summary is generated.") });
  steps.createEl("li", { text: plugin.t("Use Capture Note in Obsidian, or use drop note / drop url / drop pdf / drop image / drop repo in the terminal.") });
  steps.createEl("li", { text: plugin.t("Use the Ask modal when you need to ask a question, or run ./scripts/aiwiki-launcher.sh ask ...") });
  steps.createEl("li", { text: plugin.t("Follow single writer for write actions: do not run compile / nightly / apply / revert in Obsidian and the terminal at the same time.") });
  plugin.renderActionButtons(section, [
    { label: "Capture Note", cta: true, onClick: async () => new CaptureNoteModal(plugin.app, plugin).open() },
    { label: "Ask", onClick: async () => new AskCommandModal(plugin.app, plugin).open() },
    { label: "Compile", onClick: async () => plugin.runCompileCommand() },
  ]);
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

function latestInteractionEntry(plugin) {
  const telemetry = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.route_telemetry || {} : {};
  const entries = Array.isArray(telemetry.entries) ? telemetry.entries : [];
  if (entries.length) {
    return entries[0];
  }
  return telemetry.last_entry && typeof telemetry.last_entry === "object" ? telemetry.last_entry : null;
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

function renderInteractionPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Interaction", "Ask anything about the current workspace.");
  const input = panel.createEl("textarea", { cls: "furnace-shell-composer-input" });
  input.rows = 3;
  input.placeholder = plugin.t("Type a question or keyword...");
  input.addClass("furnace-shell-code");

  plugin.renderInlineButtons(panel, [
    {
      label: "Send",
      cta: true,
      onClick: async () => {
        const question = String(input.value || "").trim();
        if (!question) {
          new Notice(plugin.t("Question cannot be empty."));
          return;
        }
        await plugin.runAskCommand({
          question,
          format: plugin.settings.defaultAskFormat,
          mode: "run-ask",
          protocol: "",
        });
      },
    },
    {
      label: "Search",
      kind: "ghost",
      onClick: async () => {
        const query = String(input.value || "").trim();
        if (!query) {
          new Notice(plugin.t("Search query cannot be empty."));
          return;
        }
        await plugin.runShellSearchCommand(query, 8);
      },
    },
  ]);

  input.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      const question = String(input.value || "").trim();
      if (!question) {
        new Notice(plugin.t("Question cannot be empty."));
        return;
      }
      plugin.runUiAction(
        () =>
          plugin.runAskCommand({
            question,
            format: plugin.settings.defaultAskFormat,
          mode: "run-ask",
          protocol: "",
        });
      } finally {
        setRunning(false);
      }
    };
  
    askButton.addEventListener("click", () => {
      plugin.runUiAction(() => submitAsk(), plugin.t("Ask"));
    });
  
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        plugin.runUiAction(() => submitAsk(), plugin.t("Ask"));
      }
    });
  }
  });

  const latestInteraction = plugin.latestInteractionEntry();
  if (latestInteraction && latestInteraction.question_preview) {
    panel.createDiv({
      cls: "furnace-shell-panel-note",
      text: `${truncateText(latestInteraction.question_preview, 120)} · ${formatDisplayTime(latestInteraction.occurred_at, plugin.locale())}`,
    });
  } else {
    panel.createDiv({ cls: "furnace-shell-panel-note", text: plugin.t("No interaction yet. Ask a question or run a search.") });
  }

  const latestRun = plugin.latestPluginRun();
  const runSection = panel.createDiv({ cls: "furnace-shell-run-section" });
  runSection.createDiv({ cls: "furnace-shell-inline-heading", text: plugin.t("Latest run") });
  if (!latestRun) {
    runSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No plugin run yet. Send a question or use a command.") });
  } else {
    renderRunDetail(plugin, runSection, latestRun, { compact: true, includeOpenRecentRuns: true });
  }

  const searchResults = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.search_results || {} : {};
  const searchItems = Array.isArray(searchResults.results) ? searchResults.results : [];
  if (String(searchResults.query || "").trim()) {
    const resultBox = panel.createDiv({ cls: "furnace-shell-inline-list" });
    resultBox.createDiv({
      cls: "furnace-shell-inline-heading",
      text: `${plugin.t("Search")} · ${truncateText(searchResults.query, 48)} (${searchResults.result_count || 0})`,
    });
    if (!searchItems.length) {
      resultBox.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No matching pages in the compiled workspace.") });
    } else {
      searchItems.slice(0, 3).forEach((result) => {
        const item = resultBox.createDiv({ cls: "furnace-shell-inline-item" });
        item.createEl("strong", { text: result.title || result.path || plugin.t("result") });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${plugin.t(result.kind || "page")} · ${result.path || ""}`,
        });
        if (result.path) {
          const openButton = item.createEl("button", { text: plugin.t("Open") });
          openButton.addEventListener("click", () => {
            plugin.runUiAction(() => plugin.openWorkspacePath(result.path), `Open search result: ${result.path}`);
          });
        }
      });
    }
  }
}

function renderMaterialPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Materials", "Push new material into the furnace.");
  const grid = panel.createDiv({ cls: "furnace-shell-material-grid" });
  [
    { icon: "📝", label: "Capture Note", onClick: async () => new CaptureNoteModal(plugin.app, plugin).open() },
    { icon: "🔗", label: "Drop URL", onClick: async () => new DropUrlModal(plugin.app, plugin).open() },
    { icon: "📄", label: "Drop File", onClick: async () => new DropFileModal(plugin.app, plugin).open() },
    { icon: "📷", label: "Drop Image", onClick: async () => new DropImageModal(plugin.app, plugin).open() },
  ].forEach((item) => {
    const button = grid.createEl("button", { cls: "furnace-shell-material-button" });
    button.createEl("span", { cls: "furnace-shell-material-icon", text: item.icon });
    button.createEl("span", { cls: "furnace-shell-material-label", text: plugin.t(item.label) });
    button.addEventListener("click", () => {
      plugin.runUiAction(() => item.onClick(), plugin.t(item.label));
    });
  });
  panel.createDiv({
    cls: "furnace-shell-panel-note",
    text: plugin.t("Follow single writer for write actions: do not run compile / nightly / apply / revert in Obsidian and the terminal at the same time."),
  });
}

function renderOutputsPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Latest outputs", "Open the newest outputs without diving into control surfaces.", {
    action: { label: "View all", onClick: async () => plugin.openOutputsHub() },
  });
  const outputs = plugin.shellSummary && typeof plugin.shellSummary === "object" && Array.isArray(plugin.shellSummary.recent_outputs)
    ? plugin.shellSummary.recent_outputs
    : [];
  if (!outputs.length) {
    panel.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent outputs yet. Drop material or run a compile.") });
    plugin.renderInlineButtons(panel, [
      { label: "Compile", cta: true, onClick: async () => plugin.runCompileCommand() },
      { label: "Open outputs hub", kind: "ghost", onClick: async () => plugin.openOutputsHub() },
    ]);
    return;
  }
  const list = panel.createDiv({ cls: "furnace-shell-output-list" });
  outputs.slice(0, 2).forEach((artifact) => {
    const item = list.createDiv({ cls: "furnace-shell-output-item" });
    const copy = item.createDiv({ cls: "furnace-shell-output-copy" });
    copy.createEl("strong", { text: artifact.title || artifact.path || plugin.t("output") });
    copy.createDiv({
      cls: "furnace-shell-meta",
      text: `${plugin.t(artifact.protocol || "general")} · ${plugin.t(artifact.format || "markdown")} · ${formatDisplayTime(artifact.created_at, plugin.locale())}`,
    });
    const openButton = item.createEl("button", { text: plugin.t("Open") });
    openButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(artifact.path), `Open output: ${artifact.path}`);
    });
  });
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
    plugin.renderPill(healthPills, plugin.t("Deterministic fallback active"), "is-degraded");
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
  const healthActions = [];
  if (llmHealth.recoveryCommand) {
    healthActions.push({
      label: "Copy command",
      kind: "ghost",
      onClick: async () => plugin.copyText(llmHealth.recoveryCommand),
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
    { label: "Open Recent Runs", kind: "ghost", onClick: async () => plugin.openRecentRunsView() },
  ]);
}

function resolveBatchHintInvocation(plugin, action) {
  // Round 43 / Stage C: batch hint commands -> existing pickers / runners.
  // Returns { label, run } or null when the action is not a recognised batch hint.
  if (!action || typeof action !== "object") {
    return null;
  }
  const kind = String(action.kind || "");
  if (kind !== "batch-review" && kind !== "batch-apply") {
    return null;
  }
  const command = String(action.command || "");
  if (kind === "batch-apply" && command.includes("apply-action --all-accepted-low-risk")) {
    return {
      label: plugin.t("Run batch"),
      run: () => plugin.runApplyAllAcceptedLowRiskCommand(),
    };
  }
  if (kind === "batch-review" && command.includes("review-page --all-pending")) {
    return {
      label: plugin.t("Run batch"),
      run: () => plugin.openReviewBatchSuggestionPicker(),
    };
  }
  if (kind === "batch-review" && command.includes("review-action --all-pending")) {
    // Action-kind batch review still routes through the batch suggestion picker;
    // the picker filters to the active suggestion bundle, so the same entry point works.
    return {
      label: plugin.t("Run batch"),
      run: () => plugin.openReviewBatchSuggestionPicker(),
    };
  }
  return null;
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
    const batchInvocation = resolveBatchHintInvocation(plugin, action);
    if (batchInvocation) {
      const runButton = buttons.createEl("button", { text: batchInvocation.label, cls: "mod-cta" });
      runButton.addEventListener("click", () => {
        plugin.runUiAction(batchInvocation.run, `Run batch hint: ${action.title || action.command}`);
      });
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
  const llmStatus = plugin.shellSummary.llm_status || {};
  const lintCounts = nightly.lint_counts || {};
  const lintTotal = sumNumericValues(lintCounts);

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
  panel.createDiv({
    cls: "furnace-shell-panel-note",
    text: `${plugin.t("Last sync")} ${formatDisplayTime(plugin.shellSummary.generated_at, plugin.locale()) || plugin.t("unknown")}`,
  });
}

function renderLegacyAdvancedPanel(plugin, container) {
  const details = container.createEl("details", { cls: "furnace-shell-advanced" });
  const summary = details.createEl("summary", { cls: "furnace-shell-advanced-summary" });
  const summaryCopy = summary.createDiv({ cls: "furnace-shell-advanced-copy" });
  summaryCopy.createEl("span", { cls: "furnace-shell-advanced-title", text: plugin.t("Advanced Actions") });
  summaryCopy.createEl("span", { cls: "furnace-shell-advanced-description", text: plugin.t("Core workflows stay available here, but hidden by default.") });
  const summaryBadges = summary.createDiv({ cls: "furnace-shell-pill-row" });
  const review = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.review_backlog_counts || {} : {};
  const pendingReviewCount = Number(review.pending_decisions || 0) + Number(review.pending_judgments || 0);
  plugin.renderPill(summaryBadges, `${pendingReviewCount} ${plugin.t("Pending Reviews")}`);
  plugin.renderPill(summaryBadges, `${review.ready_actions || 0} ${plugin.t("actions")}`);

  const body = details.createDiv({ cls: "furnace-shell-advanced-body" });
  plugin.renderInlineButtons(body, [
    { label: "Compile", cta: true, onClick: async () => plugin.runCompileCommand() },
    { label: "Nightly", onClick: async () => plugin.runNightlyCommand() },
    { label: "Set Protocol", onClick: async () => new ProtocolCommandModal(plugin.app, plugin).open() },
    { label: "Sync now", kind: "ghost", onClick: async () => plugin.refreshShellSummaryCommand() },
  ]);

  const suggestedActions = body.createDiv({ cls: "furnace-shell-subpanel furnace-shell-subpanel-compact" });
  suggestedActions.createEl("h4", { text: plugin.t("Suggested Next Actions") });
  if (!renderSuggestedNextActionsBlock(plugin, suggestedActions, { maxItems: 2 })) {
    suggestedActions.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No suggested next action right now.") });
  }

  const columns = body.createDiv({ cls: "furnace-shell-advanced-grid" });

  const reviewCard = columns.createDiv({ cls: "furnace-shell-subpanel" });
  reviewCard.createEl("h4", { text: plugin.t("Quick review") });
  reviewCard.createDiv({
    cls: "furnace-shell-meta",
    text: `${pendingReviewCount} ${plugin.t("Pending Reviews")} · ${(plugin.shellSummary && plugin.shellSummary.aging_summary && plugin.shellSummary.aging_summary.overdue_count) || 0} ${plugin.t("Overdue")}`,
  });
  const nextReview = plugin.nextReviewCandidate();
  if (nextReview && nextReview.pagePath) {
    reviewCard.createEl("strong", { text: nextReview.label || nextReview.pagePath });
    reviewCard.createDiv({ cls: "furnace-shell-meta", text: nextReview.description || plugin.t("review object") });
  }
  plugin.renderInlineButtons(reviewCard, [
    { label: "Review Next", onClick: async () => plugin.openReviewNextTransitionPicker() },
    { label: "Batch Review", onClick: async () => plugin.openReviewBatchSuggestionPicker() },
    { label: "Open Review Center", kind: "ghost", onClick: async () => plugin.openReviewCenterView() },
  ], "furnace-shell-subpanel-actions");

  const executionCard = columns.createDiv({ cls: "furnace-shell-subpanel" });
  executionCard.createEl("h4", { text: plugin.t("Quick execution") });
  executionCard.createDiv({
    cls: "furnace-shell-meta",
    text: `${review.ready_actions || 0} ${plugin.t("actions")} · ${review.overdue_actions || 0} ${plugin.t("Overdue")} · ${review.escalated_actions || 0} ${plugin.t("Escalation")}`,
  });
  plugin.renderInlineButtons(executionCard, [
    { label: "Review Action", onClick: async () => plugin.openReviewActionContextPicker() },
    { label: "Apply All Low-Risk", onClick: async () => plugin.runApplyAllAcceptedLowRiskCommand() },
    { label: "Open Execution Center", kind: "ghost", onClick: async () => plugin.openExecutionCenterView() },
  ], "furnace-shell-subpanel-actions");

  const runsCard = columns.createDiv({ cls: "furnace-shell-subpanel" });
  runsCard.createEl("h4", { text: plugin.t("Latest plugin runs") });
  if (!plugin.pluginState.recentRuns.length) {
    runsCard.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent plugin runs.") });
  } else {
    const runList = runsCard.createDiv({ cls: "furnace-shell-inline-list" });
    plugin.pluginState.recentRuns.slice(0, 3).forEach((record) => {
      const item = runList.createDiv({ cls: "furnace-shell-inline-item" });
      item.createEl("strong", { text: record.label || record.args || plugin.t("command") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t(record.status || "status-unknown")} · ${formatDisplayTime(record.startedAt, plugin.locale())}`,
      });
    });
  }
  plugin.renderInlineButtons(runsCard, [
    { label: "Open Recent Runs", kind: "ghost", onClick: async () => plugin.openRecentRunsView() },
    { label: "Open Home Note", kind: "ghost", onClick: async () => plugin.openHomeNote() },
  ], "furnace-shell-subpanel-actions");
}

function isHttpUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (error) {
    return false;
  }
}
