// Standalone render functions extracted from the Plugin class.
// Each function takes the plugin instance as its first argument.

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
  steps.createEl("li", { text: plugin.t("Use Capture Note in Obsidian, or use drop-note / drop-url / drop-pdf / drop-image / drop-repo in the terminal.") });
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
          mode: plugin.settings.defaultAskMode,
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
            mode: plugin.settings.defaultAskMode,
            protocol: "",
          }),
        plugin.t("Ask")
      );
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
  if (status === "failed") {
    return "is-degraded";
  }
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
    cls: syncState.status === "failed" ? "furnace-shell-panel-note furnace-shell-status-failed" : "furnace-shell-panel-note",
    text: plugin.t(syncState.reason || "Summary unavailable. The panel will sync automatically when possible."),
  });
  healthBox.createDiv({
    cls: llmHealth.status === "degraded" ? "furnace-shell-panel-note furnace-shell-status-failed" : "furnace-shell-panel-note",
    text: plugin.t(llmHealth.reason || "No recent LLM health check yet."),
  });
  const healthActions = [];
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

function renderNextActionsPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Suggested Next Actions", "Keep the next safe action visible from the main surface.");
  if (!renderSuggestedNextActionsBlock(plugin, panel, { maxItems: 3 })) {
    panel.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No suggested next action right now.") });
  }
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

function renderAdvancedPanel(plugin, container) {
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

function renderFurnaceCenter(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.addClass("furnace-shell-main-view");

  if (!plugin.repoState.valid) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("Vault runtime unavailable. Missing scaffold or launcher: {missing}", {
        missing: plugin.repoState.missingPaths.join(", "),
      }),
    });
    contentEl.createDiv({
      cls: "furnace-shell-meta",
      text: plugin.t("Expected a vault scaffold (`raw/wiki/schema/output/.aiwiki`) plus an executable launcher script."),
    });
    return;
  }

  plugin.renderMainHeader(contentEl);
  plugin.renderStatusPanel(contentEl);
  plugin.renderInteractionPanel(contentEl);
  plugin.renderMaterialPanel(contentEl);
  plugin.renderOutputsPanel(contentEl);
  plugin.renderAdvancedPanel(contentEl);
}

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
  const rewriteProposalPaths = Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths : [];
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
    const proposalButton = actions.createEl("button", { text: plugin.t("Open proposal") });
    proposalButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(rewriteProposalPaths[0]), `Open rewrite proposal: ${rewriteProposalPaths[0]}`);
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

function renderReviewCenter(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.createEl("h2", { text: plugin.t("Review Center") });

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
    { label: "Execution Center", onClick: async () => plugin.openExecutionCenterView() },
  ]);
  plugin.renderActionButtons(contentEl, [
    { label: "Review Next", onClick: async () => plugin.openReviewNextTransitionPicker() },
    { label: "Batch Review", onClick: async () => plugin.openReviewBatchSuggestionPicker() },
    { label: "Review Page", onClick: async () => plugin.openReviewPageContextPicker() },
    { label: "Review Rewrite", onClick: async () => plugin.openReviewRewriteContextPicker() },
    { label: "Apply Rewrite", onClick: async () => plugin.openApplyRewriteModal() },
    { label: "Retire Concept", onClick: async () => plugin.openRetireConceptModal() },
    { label: "Reactivate Concept", onClick: async () => plugin.openReactivateConceptModal() },
    { label: "File Back", onClick: async () => plugin.openFileBackModal() },
  ]);

  if (!plugin.shellSummary) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("shell-summary.json is not available yet. Run Refresh, Compile, or Nightly first."),
    });
    return;
  }

  const review = plugin.shellSummary.review_backlog_counts || {};
  const aging = plugin.shellSummary.aging_summary || {};
  const judgmentAssets = plugin.shellSummary.judgment_assets || {};
  const judgmentCounts = judgmentAssets.counts || {};
  plugin.renderCardGrid(contentEl, [
    { label: "Pending Decisions", value: review.pending_decisions || 0 },
    { label: "Pending Judgments", value: review.pending_judgments || 0 },
    { label: "Overdue Reviews", value: aging.overdue_count || 0 },
    { label: "Escalation", value: aging.escalated_count || 0 },
    { label: "Concept Backlog", value: review.concept_backlog || 0 },
    { label: "Review Concepts", value: review.review_concepts || 0 },
    { label: "Revisit Concepts", value: review.revisit_concepts || 0 },
    { label: "Retired Concepts", value: review.retired_concepts || 0 },
  ]);

  const nextReview = plugin.nextReviewCandidate();
  const batchSuggestions = plugin.reviewBatchSuggestions();

  const nextSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  nextSection.createEl("h3", { text: plugin.t("Next Review") });
  if (!nextReview) {
    nextSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No explicit next review item is available.") });
  } else {
    const nextCard = nextSection.createDiv({ cls: "furnace-shell-card" });
    nextCard.createEl("strong", { text: nextReview.label || nextReview.pagePath || plugin.t("review-page") });
      nextCard.createDiv({
        cls: "furnace-shell-meta",
        text: nextReview.description || plugin.t("review object"),
      });
    if (nextReview.pagePath) {
      nextCard.createDiv({ cls: "furnace-shell-meta furnace-shell-code", text: nextReview.pagePath });
    }
    const actions = nextCard.createDiv({ cls: "furnace-shell-inline-actions" });
    const openButton = actions.createEl("button", { text: plugin.t("Open page") });
    openButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(nextReview.pagePath), `Open next review page: ${nextReview.pagePath}`);
    });
    plugin.preferredTransitionOptions("page", nextReview).forEach((transition) => {
      const transitionButton = actions.createEl("button", { text: transition.label });
      transitionButton.addEventListener("click", () => {
        plugin.runUiAction(
          () => plugin.runReviewPageTransition(nextReview.pagePath, transition.value),
          `Next review quick action: ${nextReview.pagePath} -> ${transition.value}`
        );
      });
    });
    const moreButton = actions.createEl("button", { text: plugin.t("More") });
    moreButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openReviewPageTransitionPicker(nextReview), `Open next review transitions: ${nextReview.pagePath}`);
    });
  }

  const batchSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  batchSection.createEl("h3", { text: plugin.t("Batch Suggestions") });
  if (!batchSuggestions.length) {
    batchSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No batch review groups share the same recommended transition.") });
  } else {
    const list = batchSection.createEl("ul", { cls: "furnace-shell-list" });
    batchSuggestions.slice(0, 6).forEach((suggestion) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: suggestion.label });
      item.createDiv({ cls: "furnace-shell-meta", text: suggestion.description });
      const preview = suggestion.pages
        .slice(0, 3)
        .map((page) => page.label || page.pagePath)
        .filter(Boolean)
        .join(" · ");
      if (preview) {
        item.createDiv({ cls: "furnace-shell-meta", text: truncateText(preview, 180) });
      }
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const batchButton = actions.createEl("button", { text: plugin.t("Batch review") });
      batchButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openReviewPageBatchModal(suggestion), `Open batch review modal: ${suggestion.key}`);
      });
      const openFirstButton = actions.createEl("button", { text: plugin.t("Open first") });
      openFirstButton.addEventListener("click", () => {
        const firstPath = suggestion.pagePaths[0] || "";
        if (!firstPath) {
          return;
        }
        plugin.runUiAction(() => plugin.openWorkspacePath(firstPath), `Open first batch review page: ${firstPath}`);
      });
    });
  }

  const judgmentSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  judgmentSection.createEl("h3", { text: plugin.t("Judgment Assets") });
  plugin.renderCardGrid(judgmentSection, [
    { label: "Strong Assets", value: judgmentCounts.strong_assets || 0 },
    { label: "Attention Pages", value: judgmentCounts.attention_pages || 0 },
    { label: "Missing Counter Evidence", value: judgmentCounts.missing_counter_evidence || 0 },
    { label: "Missing Invalidation", value: judgmentCounts.missing_invalidation || 0 },
    { label: "Missing Review History", value: judgmentCounts.missing_review_history || 0 },
    { label: "Citation Drift", value: judgmentCounts.citation_drift || 0 },
  ]);

  const reviewControlObjects = plugin.reviewControlList("pages");
  const decisionControlObjects = plugin.reviewControlList("decision_pages").length
    ? plugin.reviewControlList("decision_pages")
    : reviewControlObjects.filter((page) => String(page.kind || "").trim() === "decision");
  const judgmentControlObjects = plugin.reviewControlList("judgment_pages").length
    ? plugin.reviewControlList("judgment_pages")
    : reviewControlObjects.filter((page) => String(page.kind || "").trim() === "judgment");
  const reviewControlsByPath = new Map(
    reviewControlObjects
      .filter((page) => page && typeof page === "object" && String(page.path || "").trim())
      .map((page) => [String(page.path || "").trim(), page])
  );
  const renderReviewObjectSection = (title, pages, emptyText) => {
    const section = contentEl.createDiv({ cls: "furnace-shell-section" });
    section.createEl("h3", { text: title });
    if (!pages.length) {
      section.createDiv({ cls: "furnace-shell-empty", text: emptyText });
      return;
    }
    const list = section.createEl("ul", { cls: "furnace-shell-list" });
    pages.slice(0, 10).forEach((page) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: page.title || page.path || plugin.t("review-page") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: reviewObjectMetaText(page, plugin.locale()) || plugin.t("review-object"),
      });
      if (page.latest_review_history_entry) {
        item.createDiv({
          cls: "furnace-shell-meta",
          text: truncateText(page.latest_review_history_entry, 180),
        });
      }
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const openButton = actions.createEl("button", { text: plugin.t("Open page") });
      openButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openWorkspacePath(page.path), `Open review control page: ${page.path}`);
      });
      if (page.can_refresh_review) {
        const refreshButton = actions.createEl("button", { text: plugin.t("Re-review") });
        refreshButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.openReviewPageModal({ pagePath: page.path, status: page.current_status || page.status || "", confidence: page.confidence || "" }),
            `Re-review control page: ${page.path}`
          );
        });
      }
      plugin.preferredTransitionOptions("page", page).forEach((transition) => {
        const transitionButton = actions.createEl("button", { text: transition.label });
        transitionButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.runReviewPageTransition(page.path, transition.value),
            `Review control quick action: ${page.path} -> ${transition.value}`
          );
        });
      });
      if (Array.isArray(page.allowed_transitions) && page.allowed_transitions.length) {
        const reviewButton = actions.createEl("button", { text: plugin.t("More") });
        reviewButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openReviewPageTransitionPicker(page), `Review control page: ${page.path}`);
        });
      }
    });
  };
  renderReviewObjectSection(plugin.t("Decision Objects"), decisionControlObjects, plugin.t("No explicit decision review object is available."));
  renderReviewObjectSection(plugin.t("Judgment Objects"), judgmentControlObjects, plugin.t("No explicit judgment review object is available."));

  const rewriteControlObjects = plugin.reviewControlList("rewrite_proposals");
  const rewriteSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  rewriteSection.createEl("h3", { text: plugin.t("Rewrite Proposal Objects") });
  if (!rewriteControlObjects.length) {
    rewriteSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No explicit rewrite proposal object is available.") });
  } else {
    const list = rewriteSection.createEl("ul", { cls: "furnace-shell-list" });
    rewriteControlObjects.slice(0, 10).forEach((proposal) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: proposal.title || proposal.slug || plugin.t("rewrite-proposal") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${displayRewriteStatus(proposal.status, plugin.locale())} | ${plugin.t("priority")} ${plugin.t(proposal.priority || "medium")} | ${plugin.t("score")} ${proposal.score || 0}`,
      });
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      if (proposal.proposal_path) {
        const proposalButton = actions.createEl("button", { text: plugin.t("Open proposal") });
        proposalButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(proposal.proposal_path), `Open rewrite proposal: ${proposal.proposal_path}`);
        });
      }
      if (proposal.target_path) {
        const targetButton = actions.createEl("button", { text: plugin.t("Open target") });
        targetButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(proposal.target_path), `Open rewrite target: ${proposal.target_path}`);
        });
      }
      if (proposal.can_refresh_review) {
        const refreshButton = actions.createEl("button", { text: plugin.t("Re-review") });
        refreshButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.openReviewRewriteModal({ slug: proposal.slug, status: proposal.current_status || proposal.status || "" }),
            `Re-review rewrite object: ${proposal.slug}`
          );
        });
      }
      plugin.preferredTransitionOptions("rewrite", proposal).forEach((transition) => {
        const transitionButton = actions.createEl("button", { text: transition.label });
        transitionButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.runReviewRewriteTransition(proposal.slug, transition.value),
            `Rewrite quick action: ${proposal.slug} -> ${transition.value}`
          );
        });
      });
      if (proposal.can_review && Array.isArray(proposal.allowed_transitions) && proposal.allowed_transitions.length) {
        const reviewButton = actions.createEl("button", { text: plugin.t("More") });
        reviewButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openReviewRewriteTransitionPicker(proposal), `Review rewrite object: ${proposal.slug}`);
        });
      }
      if (proposal.can_apply) {
        const applyButton = actions.createEl("button", { text: plugin.t("Apply rewrite") });
        applyButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openApplyRewriteModal({ slug: proposal.slug }), `Apply rewrite object: ${proposal.slug}`);
        });
      }
    });
  }

  const agingSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  agingSection.createEl("h3", { text: plugin.t("Aging Summary") });
  const agingList = agingSection.createEl("ul", { cls: "furnace-shell-list" });
  [
    ["Overdue pages", aging.overdue_pages || []],
    ["Escalated pages", aging.escalated_pages || []],
    ["Scheduled pages", aging.scheduled_pages || []],
  ].forEach(([label, pages]) => {
    const item = agingList.createEl("li");
    item.createEl("strong", { text: `${label}: ${pages.length}` });
    if (!pages.length) {
      item.createDiv({ cls: "furnace-shell-meta", text: plugin.t("none") });
      return;
    }
    const pageList = item.createEl("ul", { cls: "furnace-shell-list" });
    pages.slice(0, 6).forEach((pagePath) => {
      const pageItem = pageList.createEl("li");
      pageItem.createEl("span", { text: pagePath });
      const actions = pageItem.createDiv({ cls: "furnace-shell-inline-actions" });
      const reviewControl = reviewControlsByPath.get(String(pagePath || "").trim());
      const openButton = actions.createEl("button", { text: plugin.t("Open") });
      openButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openWorkspacePath(pagePath), `Open aging page: ${pagePath}`);
      });
      const reviewButton = actions.createEl("button", { text: plugin.t("Review") });
      reviewButton.addEventListener("click", () => {
        plugin.runUiAction(
          () => (reviewControl ? plugin.openReviewPageTransitionPicker(reviewControl) : plugin.openReviewPageModal({ pagePath })),
          `Review aging page: ${pagePath}`
        );
      });
    });
  });

  const reviewEvents = Array.isArray(plugin.shellSummary.recent_runs)
    ? plugin.shellSummary.recent_runs.filter((entry) => entry.event_type === "review")
    : [];
  const eventsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  eventsSection.createEl("h3", { text: plugin.t("Recent Review Events") });
  if (!reviewEvents.length) {
    eventsSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent review events are available.") });
  } else {
    const list = eventsSection.createEl("ul", { cls: "furnace-shell-list" });
    reviewEvents.slice(0, 8).forEach((entry) => {
      const item = list.createEl("li");
      const reviewControl = reviewControlsByPath.get(String(entry.page_path || "").trim());
      item.createEl("strong", { text: entry.title || entry.page_path || plugin.t("review") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t(entry.status || "status-unknown")} | ${entry.occurred_at || plugin.t("unknown")}`,
      });
      if (entry.page_path) {
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const button = actions.createEl("button", { text: plugin.t("Open page") });
        button.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(entry.page_path), `Open review page: ${entry.page_path}`);
        });
        const reviewButton = actions.createEl("button", { text: plugin.t("Review") });
        reviewButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => (
              reviewControl
                ? plugin.openReviewPageTransitionPicker(reviewControl)
                : plugin.openReviewPageModal({ pagePath: entry.page_path, status: entry.status || "" })
            ),
            `Review event page: ${entry.page_path}`
          );
        });
      }
    });
  }

  const links = plugin.shellSummary.links || {};
  const linksSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  linksSection.createEl("h3", { text: plugin.t("Governance Links") });
  const linkList = linksSection.createEl("ul", { cls: "furnace-shell-list" });
  [
    ["review_center_markdown", "Review Center Index"],
    ["review_center_html", "Review Center HTML"],
    ["judgment_assets_markdown", "Judgment Assets"],
    ["cognitive_history_markdown", "Cognitive History"],
    ["protocols_markdown", "Protocols"],
    ["domain_pilots_markdown", "Domain Pilots"],
    ["output_packs_markdown", "Output Packs"],
  ].forEach(([key, label]) => {
    if (!links[key]) {
      return;
    }
    const item = linkList.createEl("li");
    item.createEl("span", { text: plugin.t(label) });
    const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
    const button = actions.createEl("button", { text: plugin.t("Open") });
    button.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
    });
  });
}

function renderExecutionCenter(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.createEl("h2", { text: plugin.t("Execution Center") });

  if (!plugin.repoState.valid) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("Repo-local runtime unavailable. Missing: {missing}", {
        missing: plugin.repoState.missingPaths.join(", "),
      }),
    });
    return;
  }

  plugin.renderActionButtons(contentEl, [
    { label: "Refresh", cta: true, onClick: async () => plugin.refreshShellSummaryCommand() },
    { label: "Furnace Center", onClick: async () => plugin.openFurnaceCenterView() },
    { label: "Review Center", onClick: async () => plugin.openReviewCenterView() },
    { label: "Recent Runs", onClick: async () => plugin.openRecentRunsView() },
  ]);
  plugin.renderActionButtons(contentEl, [
    { label: "Review Action", onClick: async () => plugin.openReviewActionContextPicker() },
    { label: "Apply Action", onClick: async () => plugin.openApplyActionContextPicker() },
    { label: "Revert Action", onClick: async () => plugin.openRevertActionContextPicker() },
    { label: "Apply All Low-Risk", onClick: async () => plugin.runApplyAllAcceptedLowRiskCommand() },
    { label: "Revert Last Batch", onClick: async () => plugin.runRevertLastBatchCommand() },
    { label: "Apply Archive", onClick: async () => plugin.openApplyArchiveContextPicker() },
    { label: "Revert Archive", onClick: async () => plugin.openRevertArchiveContextPicker() },
  ]);

  if (!plugin.shellSummary) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("shell-summary.json is not available yet. Run Refresh, Compile, or Nightly first."),
    });
    return;
  }

  const receipts = Array.isArray(plugin.shellSummary.recent_receipts) ? plugin.shellSummary.recent_receipts : [];
  const executionEvents = Array.isArray(plugin.shellSummary.recent_runs)
    ? plugin.shellSummary.recent_runs.filter((entry) =>
        ["archive-apply", "archive-revert", "knowledge-lifecycle-override", "nightly"].includes(entry.event_type)
      )
    : [];
  const actionControlsById = plugin.actionControlsById();
  const archiveControlsById = plugin.archiveControlsById();
  const actionControlObjects = plugin.executionControlList("actions");
  plugin.renderCardGrid(contentEl, [
    { label: "Recent Receipts", value: receipts.length },
    { label: "Execution Events", value: executionEvents.length },
    {
      label: "Archive Events",
      value: executionEvents.filter((entry) => ["archive-apply", "archive-revert"].includes(entry.event_type)).length,
    },
    {
      label: "Lifecycle Overrides",
      value: executionEvents.filter((entry) => entry.event_type === "knowledge-lifecycle-override").length,
    },
    {
      label: "Nightly Runs",
      value: executionEvents.filter((entry) => entry.event_type === "nightly").length,
    },
  ]);

  const planner = plugin.shellSummary.planner || {};
  const plannerCounts = planner.counts || {};
  const plannerQueue = Array.isArray(planner.priority_queue) ? planner.priority_queue : [];
  const plannerNextAction = planner.next_action || {};
  if (plannerQueue.length || plannerCounts.pending_proposals) {
    const plannerSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    plannerSection.createEl("h3", { text: plugin.t("Planner Queue") });
    plugin.renderCardGrid(plannerSection, [
      { label: "Pending Proposals", value: plannerCounts.pending_proposals || 0 },
      { label: "Executed", value: plannerCounts.executed_actions || 0 },
      { label: "Unblocked", value: plannerCounts.unblocked || 0 },
      { label: "Blocked", value: plannerCounts.blocked || 0 },
    ]);
    if (plannerNextAction.action_id) {
      const nextDiv = plannerSection.createDiv({ cls: "furnace-shell-section" });
      nextDiv.createEl("h4", { text: plugin.t("Next Action") });
      const item = nextDiv.createDiv();
      item.createEl("strong", { text: plannerNextAction.title || plannerNextAction.action_id });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t("score")}: ${plannerNextAction.priority_score || 0} | ${plannerNextAction.action_id || ""}`,
      });
      const nextActions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const reviewBtn = nextActions.createEl("button", { text: plugin.t("Review") });
      reviewBtn.addEventListener("click", () => {
        plugin.runUiAction(
          () => plugin.openReviewActionModal({ actionId: plannerNextAction.action_id, status: "accepted" }),
          `Review planner next: ${plannerNextAction.action_id}`
        );
      });
    }
    if (plannerQueue.length > 1) {
      const queueList = plannerSection.createEl("ul", { cls: "furnace-shell-list" });
      plannerQueue.slice(0, 8).forEach((queueItem) => {
        const item = queueList.createEl("li");
        item.createEl("strong", { text: queueItem.title || queueItem.action_id || plugin.t("action") });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${plugin.t("score")}: ${queueItem.priority_score || 0} | ${queueItem.action_id || ""}`,
        });
      });
    }
  }

  const actionObjectsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  actionObjectsSection.createEl("h3", { text: plugin.t("Action Control Objects") });
  if (!actionControlObjects.length) {
    actionObjectsSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No explicit action control object is available.") });
  } else {
    const list = actionObjectsSection.createEl("ul", { cls: "furnace-shell-list" });
    actionControlObjects.slice(0, 10).forEach((action) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: action.title || action.action_id || plugin.t("action") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${displayActionStatus(action.status, plugin.locale())} | ${plugin.t(action.priority || "medium")} | ${action.primary_path || ""}`,
      });
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      if (action.primary_path) {
        const openPrimary = actions.createEl("button", { text: plugin.t("Open primary") });
        openPrimary.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(action.primary_path), `Open action primary: ${action.primary_path}`);
        });
      }
      if (action.proposal_path) {
        const openProposal = actions.createEl("button", { text: plugin.t("Open proposal") });
        openProposal.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(action.proposal_path), `Open action proposal: ${action.proposal_path}`);
        });
      }
      if (action.can_refresh_review) {
        const refreshButton = actions.createEl("button", { text: plugin.t("Re-review") });
        refreshButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.openReviewActionModal({ actionId: action.action_id, status: action.current_status || action.status || "" }),
            `Re-review action object: ${action.action_id}`
          );
        });
      }
      plugin.preferredTransitionOptions("action", action).forEach((transition) => {
        const transitionButton = actions.createEl("button", { text: transition.label });
        transitionButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.runReviewActionTransition(action.action_id, transition.value),
            `Action quick transition: ${action.action_id} -> ${transition.value}`
          );
        });
      });
      if (action.can_review && Array.isArray(action.allowed_transitions) && action.allowed_transitions.length) {
        const moreButton = actions.createEl("button", { text: plugin.t("More") });
        moreButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openReviewActionTransitionPicker(action), `Review action object: ${action.action_id}`);
        });
      }
      if (action.can_apply) {
        const applyButton = actions.createEl("button", { text: plugin.t("Apply action") });
        applyButton.addEventListener("click", () => {
          plugin.runUiAction(
            () => plugin.openApplyActionModal({ actionId: action.action_id, bundle: action.bundle_path || "" }),
            `Apply action object: ${action.action_id}`
          );
        });
      }
      if (action.can_revert) {
        const revertButton = actions.createEl("button", { text: plugin.t("Revert action") });
        revertButton.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openRevertActionModal({ actionId: action.action_id }), `Revert action object: ${action.action_id}`);
        });
      }
    });
  }

  const receiptsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  receiptsSection.createEl("h3", { text: plugin.t("Recent Receipts") });
  if (!receipts.length) {
    receiptsSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent receipts are available.") });
  } else {
    const list = receiptsSection.createEl("ul", { cls: "furnace-shell-list" });
    receipts.slice(0, 8).forEach((receipt) => {
      const item = list.createEl("li");
      const actionId = plugin.inferActionIdFromReceipt(receipt);
      const actionControl = actionControlsById.get(actionId);
      const archiveEntryId = String(receipt.subject_id || "").trim();
      const archiveControl = archiveControlsById.get(archiveEntryId);
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
        if (String(receipt.subject_kind || "") === "material-archive" && archiveControl) {
          if (archiveControl.can_revert || archiveControl.can_apply) {
            const archiveButton = actions.createEl("button", {
              text: plugin.t(archiveControl.can_revert ? "Revert archive" : "Apply archive"),
            });
            archiveButton.addEventListener("click", () => {
              plugin.runUiAction(
                () =>
                  (archiveControl.can_revert
                    ? plugin.openRevertArchiveModal({ entryId: archiveControl.entry_id })
                    : plugin.openApplyArchiveModal({ entryId: archiveControl.entry_id })),
                `Archive receipt action: ${archiveControl.entry_id}`
              );
            });
          }
        } else if (actionControl) {
          if (actionControl.can_review) {
            const reviewButton = actions.createEl("button", { text: plugin.t("Review action") });
            reviewButton.addEventListener("click", () => {
              plugin.runUiAction(() => plugin.openReviewActionTransitionPicker(actionControl), `Review action from receipt: ${actionId}`);
            });
          }
          if (actionControl.can_revert || actionControl.can_apply) {
            const actionButton = actions.createEl("button", {
              text: plugin.t(actionControl.can_revert ? "Revert action" : "Apply action"),
            });
            actionButton.addEventListener("click", () => {
              plugin.runUiAction(
                () =>
                  (actionControl.can_revert
                    ? plugin.openRevertActionModal({ actionId })
                    : plugin.openApplyActionModal({ actionId, bundle: actionControl.bundle_path || "" })),
                `Execution receipt action: ${actionId}`
              );
            });
          }
        }
      }
    });
  }

  const eventsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  eventsSection.createEl("h3", { text: plugin.t("Recent Execution Events") });
  if (!executionEvents.length) {
    eventsSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent execution events are available.") });
  } else {
    const list = eventsSection.createEl("ul", { cls: "furnace-shell-list" });
    executionEvents.slice(0, 10).forEach((entry) => {
      const item = list.createEl("li");
      const archiveEntryId = String(entry.entry_id || (Array.isArray(entry.source_ids) && entry.source_ids.length ? entry.source_ids[0] : "") || "");
      const archiveControl = archiveControlsById.get(archiveEntryId);
      item.createEl("strong", { text: entry.title || plugin.t(entry.event_type || "event") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: `${plugin.t(entry.event_type || "event")} | ${plugin.t(entry.protocol || "general")} | ${entry.occurred_at || plugin.t("unknown")}`,
      });
      const pathValue = entry.receipt_path || entry.path || entry.output_path || "";
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      if (pathValue) {
        const button = actions.createEl("button", { text: plugin.t("Open") });
        button.addEventListener("click", () => {
          plugin.runUiAction(() => plugin.openWorkspacePath(pathValue), `Open execution path: ${pathValue}`);
        });
      }
      if (["archive-apply", "archive-revert"].includes(String(entry.event_type || "")) && archiveControl) {
        if (archiveControl.can_revert || archiveControl.can_apply) {
          const archiveButton = actions.createEl("button", {
              text: plugin.t(archiveControl.can_revert ? "Revert archive" : "Apply archive"),
          });
          archiveButton.addEventListener("click", () => {
            plugin.runUiAction(
              () =>
                (archiveControl.can_revert
                  ? plugin.openRevertArchiveModal({ entryId: archiveControl.entry_id })
                  : plugin.openApplyArchiveModal({ entryId: archiveControl.entry_id })),
              `Archive event action: ${archiveControl.entry_id}`
            );
          });
        }
      }
      if (String(entry.event_type || "") === "knowledge-lifecycle-override" && String(entry.path || "").startsWith("wiki/concepts/")) {
        const slug = path.basename(String(entry.path || ""), ".md");
        const lifecycleButton = actions.createEl("button", {
          text: plugin.t(String(entry.lifecycle_state || "") === "retired" ? "Reactivate concept" : "Retire concept"),
        });
        lifecycleButton.addEventListener("click", () => {
          plugin.runUiAction(
            () =>
              String(entry.lifecycle_state || "") === "retired"
                ? plugin.openReactivateConceptModal({ slug })
                : plugin.openRetireConceptModal({ slug }),
            `Lifecycle override action: ${slug}`
          );
        });
      }
    });
  }

  const links = plugin.shellSummary.links || {};
  const linksSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  linksSection.createEl("h3", { text: plugin.t("Execution Links") });
  const linkList = linksSection.createEl("ul", { cls: "furnace-shell-list" });
  [
    ["execution_center_markdown", "Execution Center Index"],
    ["execution_center_html", "Execution Center HTML"],
    ["execution_audit_markdown", "Execution Audit"],
    ["execution_audit_html", "Execution Audit HTML"],
    ["graph_view_markdown", "Graph View"],
  ].forEach(([key, label]) => {
    if (!links[key]) {
      return;
    }
    const item = linkList.createEl("li");
    item.createEl("span", { text: plugin.t(label) });
    const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
    const button = actions.createEl("button", { text: plugin.t("Open") });
    button.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
    });
  });
}
