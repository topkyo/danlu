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
  
  const groups = { decision: [], proposal: [], report: [], elixir: [], action: [] };
  for (const entry of feed) groups[entry.kind].push(entry);
  
  const groupSpecs = [
    ["decision", plugin.t("Needs Decision")],
    ["proposal", plugin.t("Proposals")],
    ["report", plugin.t("Today's Reports")],
    ["elixir", plugin.t("Completed")],
    ["action", plugin.t("Suggested Actions")],
  ];
  
  for (const [kind, heading] of groupSpecs) {
    const items = groups[kind];
    if (!items.length) continue;
    const groupEl = section.createDiv({ cls: `furnace-today-feed-group furnace-today-feed-${kind}` });
    groupEl.createEl("h3", { text: heading });
    const listEl = groupEl.createEl("ul", { cls: "furnace-today-feed-list" });
    for (const entry of items) {
      const li = listEl.createEl("li", { cls: "furnace-today-feed-item" });
      const titleEl = li.createEl("div", { cls: "furnace-today-feed-title", text: entry.title });
      if (entry.summary) {
        li.createEl("div", { cls: "furnace-today-feed-summary", text: entry.summary });
      }
      if (entry.target) {
        li.createEl("div", { cls: "furnace-today-feed-target", text: entry.target });
      }
    }
  }
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

  const openBtn = card.createEl("button", { text: plugin.t("Open") });
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
