// Render today feed and report surfaces for Product Shell.

function renderTodayFeed(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  if (!summary) {
    return;
  }
  
  const feed = buildTodayFeed(summary);
  
  const section = container.createDiv({ cls: "furnace-today-feed" });
  section.createEl("h2", { text: plugin.t("Today") });
  
  if (!feed.length) {
    section.createEl("div", { 
      cls: "furnace-today-feed-empty", 
      text: plugin.t("(nothing for today)") 
    });
    return;
  }
  
  const groups = { report: [], automation: [], decision: [], proposal: [], elixir: [], action: [] };
  for (const entry of feed) groups[entry.kind].push(entry);
  
  const groupSpecs = [
    ["report", plugin.t("Reports"), groups.report],
    ["automation", plugin.t("Automation"), groups.automation],
    ["confirmation", plugin.t("Needs Your Confirmation"), [...groups.decision, ...groups.proposal]],
    ["elixir", plugin.t("Completed"), groups.elixir],
    ["action", plugin.t("Suggested Actions"), groups.action],
  ];
  
  for (const [kind, heading, items] of groupSpecs) {
    if (!items.length) continue;
    const groupEl = section.createDiv({ cls: `furnace-today-feed-group furnace-today-feed-${kind}` });
    groupEl.createEl("h3", { text: heading });
    const listEl = groupEl.createEl("ul", { cls: "furnace-today-feed-list" });
    for (const entry of items) {
      renderTodayFeedItem(plugin, listEl, entry);
    }
  }
}

function renderTodayFeedItem(plugin, listEl, entry) {
  const li = listEl.createEl("li", { cls: "furnace-today-feed-item furnace-today-feed-card" });
  const copy = li.createDiv({ cls: "furnace-today-feed-copy" });
  copy.createEl("div", { cls: "furnace-today-feed-title", text: entry.title });
  if (entry.summary) {
    copy.createEl("div", { cls: "furnace-today-feed-summary", text: entry.summary });
  }
  const targetLabel = todayFeedTargetLabel(plugin, entry);
  if (targetLabel) {
    copy.createEl("div", { cls: "furnace-today-feed-target", text: targetLabel });
  }

  const actions = todayFeedActions(plugin, entry);
  if (!actions.length) {
    return;
  }
  const actionRow = li.createDiv({ cls: "furnace-today-feed-actions" });
  for (const action of actions) {
    const buttonLabel = plugin.t(action.label);
    const button = actionRow.createEl("button", {
      text: buttonLabel,
      attr: {
        "aria-label": buttonLabel,
        title: action.description || buttonLabel,
      },
    });
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      plugin.runUiAction(() => action.onClick(), action.description || action.label);
    });
  }
}

function todayFeedActions(plugin, entry) {
  const target = String(entry && entry.target || "").trim();
  if (!target) {
    return [];
  }
  if (isReviewTarget(target)) {
    return [
      {
        label: "Open Review",
        description: `Open review surface: ${target}`,
        onClick: async () => plugin.openReviewCenterView(),
      },
      {
        label: "Snooze",
        description: `Snooze today item: ${target}`,
        onClick: async () => plugin.runTodaySnoozeCommand(target),
      },
    ];
  }
  if (isWorkspaceTarget(target)) {
    return [
      {
        label: workspaceTargetActionLabel(target, entry),
        description: `Open today target: ${target}`,
        onClick: async () => plugin.openWorkspacePath(target),
      },
    ];
  }
  if (entry.kind === "action" || looksLikeCommandTarget(target)) {
    return [
      {
        label: "Copy command",
        description: `Copy today command: ${target}`,
        onClick: async () => plugin.copyText(target),
      },
    ];
  }
  return [
    {
      label: "Copy target",
      description: `Copy today target: ${target}`,
      onClick: async () => plugin.copyText(target),
    },
  ];
}

function todayFeedTargetLabel(plugin, entry) {
  const target = String(entry && entry.target || "").trim();
  if (!target) {
    return "";
  }
  if (isReviewTarget(target)) {
    return plugin.t("Review queue");
  }
  if (isWorkspaceTarget(target)) {
    return workspaceTargetDisplayLabel(plugin, target, entry);
  }
  if (entry.kind === "action" || looksLikeCommandTarget(target)) {
    if (target.startsWith("metric:")) {
      return plugin.t("Metric alert");
    }
    return plugin.t("Command prepared for manual confirmation");
  }
  return target;
}

function workspaceTargetActionLabel(target, entry) {
  const text = String(target || "").trim();
  if (entry && entry.kind === "proposal") {
    return "Open proposal";
  }
  if (text.startsWith("output/reports/")) {
    return "Open report";
  }
  if (text.startsWith("wiki/decisions/")) {
    return "Open decision";
  }
  if (text.startsWith("wiki/judgments/")) {
    return "Open judgment";
  }
  return "Open page";
}

function workspaceTargetDisplayLabel(plugin, target, entry) {
  const text = String(target || "").trim();
  if (entry && entry.kind === "proposal") {
    return plugin.t("Proposal page");
  }
  if (text.startsWith("output/reports/")) {
    return plugin.t("Report");
  }
  if (text.startsWith("wiki/decisions/")) {
    return plugin.t("Decision page");
  }
  if (text.startsWith("wiki/judgments/")) {
    return plugin.t("Judgment page");
  }
  if (text.startsWith("wiki/rewrite-proposals/") || text.startsWith("output/_proposals/")) {
    return plugin.t("Proposal page");
  }
  if (text.startsWith("output/graph/") || text.startsWith("wiki/indexes/graph")) {
    return plugin.t("Graph page");
  }
  if (text.startsWith("output/review/") || text.startsWith("wiki/indexes/review")) {
    return plugin.t("Review surface");
  }
  return plugin.t("Workspace page");
}

function isReviewTarget(target) {
  return String(target || "").startsWith("review:");
}

function isWorkspaceTarget(target) {
  const text = String(target || "").trim();
  if (!text || text.includes("\n")) {
    return false;
  }
  if (/^(?:raw|wiki|output|schema|docs|\.aiwiki)\//.test(text)) {
    return true;
  }
  return /\.(?:md|json|html|pdf|png|jpg|jpeg|webp|svg)$/i.test(text);
}

function looksLikeCommandTarget(target) {
  const text = String(target || "").trim();
  if (!text) {
    return false;
  }
  return /^(?:aiwiki|python3?|PYTHONPATH=|drop-|run-|ask\b|compile\b|nightly\b|review-|apply-|revert-|file-back\b|metrics\b|today\b)/.test(text);
}

function renderReportsPanel(plugin, container, reports) {
  const grouped = splitReportsByLocalDate(reports, { limitPreviousDays: 7 });
  const section = container.createDiv({ cls: "furnace-shell-reports-section" });

  const todaySection = section.createDiv({ cls: "furnace-shell-reports-group furnace-shell-reports-today" });
  todaySection.createEl("h3", { text: plugin.t("Today's Reports") });
  renderReportsGroup(plugin, todaySection, grouped.today, "(no reports today)");

  const previousSection = section.createDiv({ cls: "furnace-shell-reports-group furnace-shell-previous-reports" });
  previousSection.createEl("h3", { text: plugin.t("Previous Reports") });
  if (!grouped.previous.length) {
    previousSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("(no previous reports)") });
    return;
  }
  grouped.previous.forEach((group) => {
    const groupEl = previousSection.createDiv({ cls: "furnace-shell-date-group" });
    groupEl.createDiv({ cls: "furnace-shell-date-header", text: plugin.t(group.label) });
    renderReportsGroup(plugin, groupEl, group.items, "(no previous reports)");
  });
}

function renderReportsGroup(plugin, container, reports, emptyText) {
  const items = Array.isArray(reports) ? reports : [];
  if (!items.length) {
    container.createDiv({ cls: "furnace-shell-empty", text: plugin.t(emptyText) });
    return;
  }
  const list = container.createDiv({ cls: "furnace-shell-report-list" });
  items.forEach((report) => renderReportItem(plugin, list, report));
}

function renderReportItem(plugin, container, report) {
  const isUnread = isReportUnread(report, plugin.settings.lastViewedTimestamp);
  const titleText = report.title || report.path || plugin.t("output");
  const card = container.createDiv({ cls: "furnace-shell-report-card" });
  if (isUnread) {
    card.addClass("is-unread");
  }

  const openReport = async () => {
    if (!report.path) {
      return;
    }
    await plugin.openWorkspacePath(report.path);
    plugin.settings.lastViewedTimestamp = new Date().toISOString();
    await plugin.savePluginState();
    plugin.refreshOpenViews();
  };

  card.addEventListener("click", () => {
    plugin.runUiAction(() => openReport(), `Open output: ${report.path || titleText}`);
  });

  const content = card.createDiv({ cls: "furnace-shell-report-content" });
  content.createEl("span", { cls: "furnace-shell-report-dot", attr: { "aria-hidden": "true" } });
  const copy = content.createDiv({ cls: "furnace-shell-report-copy" });
  copy.createEl("span", { cls: "furnace-shell-report-title", text: titleText });
  copy.createDiv({
    cls: "furnace-shell-report-meta",
    text: `${plugin.t(report.protocol || "general")} · ${plugin.t(report.format || "markdown")} · ${formatDisplayTime(report.created_at, plugin.locale()) || report.created_at || plugin.t("unknown")}`,
  });

  const openBtn = card.createEl("button", { text: plugin.t("Open report") });
  openBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    plugin.runUiAction(() => openReport(), `Open output: ${report.path || titleText}`);
  });
}

function renderNeedsDecisionSection(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  if (!summary) {
    return;
  }
  const suggested = Array.isArray(summary.suggested_next_actions) ? summary.suggested_next_actions : [];
  const drifts = Array.isArray(summary.drift_warnings) ? summary.drift_warnings : [];
  const rewrites = Array.isArray(summary.rewrite_recovery_actions) ? summary.rewrite_recovery_actions : [];
  const backlog = summary.review_backlog_counts && typeof summary.review_backlog_counts === "object" ? summary.review_backlog_counts : {};
  const backlogTotal = Object.values(backlog).reduce((acc, v) => acc + (Number.isFinite(Number(v)) ? Number(v) : 0), 0);

  if (!suggested.length && !drifts.length && !rewrites.length && backlogTotal <= 0) {
    return;
  }

  const section = container.createDiv({ cls: "furnace-shell-needs-section" });
  section.createEl("h3", { text: plugin.t("Needs your decision") });

  const maxItems = 5;
  if (suggested.length) {
    renderSuggestedNextActionsBlock(plugin, section, { maxItems: Math.min(suggested.length, maxItems) });
  }

  const renderItem = (item, kindLabel) => {
    const wrapper = section.createDiv({ cls: "furnace-shell-inline-list" });
    const row = wrapper.createDiv({ cls: "furnace-shell-inline-item" });
    const copy = row.createDiv({ cls: "furnace-shell-output-copy" });
    copy.createEl("strong", { text: item.title || item.path || item.message || plugin.t(kindLabel) });
    const metaParts = [plugin.t(kindLabel)];
    if (item.reason) {
      metaParts.push(plugin.t("reason {value}", { value: item.reason }));
    }
    if (item.path) {
      metaParts.push(item.path);
    }
    if (metaParts.length) {
      copy.createDiv({ cls: "furnace-shell-meta", text: metaParts.join(" | ") });
    }
    if (item.path) {
      const buttons = row.createDiv({ cls: "furnace-shell-inline-actions furnace-shell-inline-actions-compact" });
      const openButton = buttons.createEl("button", { text: plugin.t("Open") });
      openButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openWorkspacePath(item.path), `Open needs item: ${item.path}`);
      });
    }
  };

  let used = Math.min(suggested.length, maxItems);
  let truncated = Math.max(0, suggested.length - maxItems);
  for (const item of drifts) {
    if (used >= maxItems) {
      truncated += 1;
      continue;
    }
    renderItem(item, "drift warning");
    used += 1;
  }
  for (const item of rewrites) {
    if (used >= maxItems) {
      truncated += 1;
      continue;
    }
    renderItem(item, "rewrite recovery");
    used += 1;
  }

  if (backlogTotal > 0) {
    const backlogRow = section.createDiv({ cls: "furnace-shell-needs-backlog" });
    backlogRow.setText(plugin.t("Review backlog: {value} pending", { value: String(backlogTotal) }));
  }

  if (truncated > 0) {
    const more = section.createDiv({ cls: "furnace-shell-needs-more" });
    more.setText(plugin.t("+{value} more in Advanced", { value: String(truncated) }));
  }
}

function renderNextActionsPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Suggested Next Actions", "Keep the next safe action visible from the main surface.");
  if (!renderSuggestedNextActionsBlock(plugin, panel, { maxItems: 3 })) {
    panel.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No suggested next action right now.") });
  }
}
