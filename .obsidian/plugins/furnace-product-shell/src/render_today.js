// Render today feed and report surfaces for Product Shell.

function renderTodayFeed(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;

  const section = container.createDiv({ cls: "furnace-today-feed" });
  section.createEl("h2", { text: plugin.t("Today") });

  // R88: pending submissions（用户刚提交、流水线未落地的"处理中"卡片）
  // 始终在最前面渲染，独立于 shellSummary 状态，构成视觉闭环
  renderPendingSubmissionsGroup(plugin, section);

  if (!summary) {
    section.createEl("div", {
      cls: "furnace-today-feed-empty",
      text: plugin.t("数据还没就绪。先点上方刷新，或等首次任务跑完。"),
    });
    // R88 #1 (P1 fix): summary 缺失也提供 CTA
    renderTodayEmptyCta(plugin, section, container);
    return;
  }

  const feed = buildTodayFeed(summary);

  if (!feed.length) {
    // 如果有 pending 卡片在上方，已经构成"投了在跑"的视觉反馈，不再渲染冷空态
    const hasPending = Array.isArray(plugin.pendingSubmissions) && plugin.pendingSubmissions.length > 0;
    if (hasPending) return;
    const empty = section.createDiv({ cls: "furnace-today-feed-empty" });
    empty.createEl("div", {
      cls: "furnace-today-feed-empty-title",
      text: plugin.t("今天还没有新报告"),
    });
    empty.createEl("div", {
      cls: "furnace-today-feed-empty-hint",
      text: plugin.t("拖入 URL / PDF / 图片 / repo，或在上方直接提一个问题；生成的报告会出现在这里。"),
    });
    renderTodayEmptyCta(plugin, empty, container);
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

// R88 #1: 空态 CTA — 聚焦上方 UniversalInput textarea
function renderTodayEmptyCta(plugin, parentEl, viewRoot) {
  const ctaRow = parentEl.createDiv({ cls: "furnace-today-feed-empty-cta" });
  const ctaBtn = ctaRow.createEl("button", {
    cls: "furnace-today-cta-submit mod-cta",
    text: plugin.t("投一份材料"),
  });
  ctaBtn.addEventListener("click", () => {
    // 优先在当前视图根内查找；不要跨 view 全局 fallback（避免误聚焦）
    const root = (viewRoot && viewRoot.closest && (viewRoot.closest(".furnace-shell-view") || viewRoot)) || viewRoot;
    const textarea = root && root.querySelector
      ? root.querySelector(".furnace-universal-input-textarea")
      : null;
    if (textarea) {
      textarea.focus();
      try { textarea.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
    }
  });
}

// R88 #2: 渲染"处理中"卡片（runtime-only pending submissions）
function renderPendingSubmissionsGroup(plugin, section) {
  const items = Array.isArray(plugin.pendingSubmissions) ? plugin.pendingSubmissions : [];
  if (!items.length) return;
  const groupEl = section.createDiv({ cls: "furnace-today-feed-group furnace-today-feed-pending" });
  groupEl.createEl("h3", { text: plugin.t("处理中") });
  const listEl = groupEl.createEl("ul", { cls: "furnace-today-feed-list" });
  for (const entry of items) {
    const li = listEl.createEl("li", { cls: `furnace-today-feed-item furnace-pending-card furnace-pending-${entry.status || "running"}` });
    const card = li.createDiv({ cls: "furnace-pending-card-inner" });
    const head = card.createDiv({ cls: "furnace-pending-card-head" });
    let statusLabel;
    if (entry.status === "done") statusLabel = plugin.t("已完成");
    else if (entry.status === "failed") statusLabel = plugin.t("失败");
    else statusLabel = plugin.t("处理中…");
    head.createEl("span", { cls: "furnace-pending-card-status", text: statusLabel });
    head.createEl("span", { cls: "furnace-pending-card-time", text: formatDisplayTime(entry.startedAt, plugin.locale()) || "" });
    card.createDiv({ cls: "furnace-pending-card-text", text: entry.displayText || "" });
    if (entry.status === "failed") {
      const errEl = card.createDiv({ cls: "furnace-pending-card-error", text: entry.error || plugin.t("失败") });
      errEl.setAttr && errEl.setAttr("title", entry.error || "");
      const actions = card.createDiv({ cls: "furnace-pending-card-actions" });
      const retryBtn = actions.createEl("button", { cls: "mod-cta", text: plugin.t("重试") });
      retryBtn.addEventListener("click", async () => {
        // R88 P1 fix: 重试不删卡，把状态改回 running，复用同一卡片做闭环
        const args = entry.retryArgs || {};
        plugin.resetPendingSubmissionForRetry(entry.id);
        try {
          if (args.kind === "files" && Array.isArray(args.files)) {
            for (const f of args.files) {
              await plugin.runUniversalInputCommand({ payload: f.path || f.name || "", title: args.title || "" });
            }
          } else {
            await plugin.runUniversalInputCommand({ payload: args.payload || entry.displayText || "" });
          }
          plugin.markPendingSubmissionDone(entry.id);
        } catch (e) {
          plugin.markPendingSubmissionFailed(entry.id, e);
        }
      });
      const dismissBtn = actions.createEl("button", { text: plugin.t("Dismiss") });
      dismissBtn.addEventListener("click", () => plugin.removePendingSubmission(entry.id));
    }
  }
}

function renderTodayFeedItem(plugin, listEl, entry) {
  const li = listEl.createEl("li", { cls: "furnace-today-feed-item" });
  const { card } = renderFeedCard(plugin, li, entry);

  if (entry.kind === "report") {
    renderReportCard(plugin, card, entry);
  } else if (entry.kind === "decision" || entry.kind === "proposal") {
    renderConfirmationCard(plugin, card, entry);
  } else if (entry.kind === "automation") {
    renderAutomationCard(plugin, card, entry);
  }

  // Fallback action buttons (for entries not handled by card renderers)
  if (entry.kind !== "report" && entry.kind !== "decision" && entry.kind !== "proposal" && entry.kind !== "automation") {
    const targetLabel = todayFeedTargetLabel(plugin, entry);
    if (targetLabel && card.querySelector) {
      const meta = card.createDiv({ cls: "furnace-today-feed-target" });
      meta.setText(targetLabel);
    }
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
    return reviewBucketDisplayLabel(plugin, target);
  }
  if (isWorkspaceTarget(target)) {
    return workspaceTargetDisplayLabel(plugin, target, entry);
  }
  if (entry.kind === "action" || looksLikeCommandTarget(target)) {
    if (target.startsWith("metric:")) {
      return plugin.t("指标提醒");
    }
    switch (entry.kind) {
      case "report": return plugin.t("新报告");
      case "automation": return plugin.t("自动维护");
      case "elixir": return plugin.t("金丹完成");
      default: return plugin.t("待确认操作");
    }
  }
  return target;
}

function reviewBucketDisplayLabel(plugin, target) {
  var kind = String(target || "").replace(/^review:/, "").trim();
  switch (kind) {
    case "counter_evidence_candidates": return plugin.t("新反证待审");
    case "judgment_review_actions": return plugin.t("判断需要复核");
    case "machine_memory_actions": return plugin.t("机器记忆待修复");
    case "pending_judgments": return plugin.t("待定判断");
    case "pending_decisions": return plugin.t("待定决策");
    case "ready_actions": return plugin.t("安全动作待确认");
    case "escalated_actions": return plugin.t("升级动作");
    case "escalation_candidates": return plugin.t("升级候选");
    case "overdue_actions": return plugin.t("逾期动作");
    case "overdue_reviews": return plugin.t("逾期复审");
    case "l3_proposals": return plugin.t("L3 提案");
    case "l3_proposal_attention": return plugin.t("L3 提案需要关注");
    case "drift": return plugin.t("数据漂移");
    default: return plugin.t("待审队列");
  }
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
