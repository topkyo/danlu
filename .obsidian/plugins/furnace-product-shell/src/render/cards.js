// Reusable card render helpers extracted from render_today.js and render_primitives.js.

function renderFeedCard(plugin, container, entry) {
  const card = container.createDiv({ cls: "furnace-feed-card" });

  // Protocol-colored left bar
  if (entry.protocol) {
    card.addClass(`furnace-protocol-${entry.protocol}`);
  }

  const body = card.createDiv({ cls: "furnace-feed-card-body" });
  const titleEl = body.createEl("div", { cls: "furnace-feed-card-title furnace-today-feed-title", text: entry.title });
  if (entry.summary) {
    body.createEl("div", { cls: "furnace-feed-card-summary furnace-today-feed-summary", text: entry.summary });
  }

  return { card, body };
}

function renderReportCard(plugin, cardEl, entry) {
  const isUnread = isReportUnread(plugin, entry);
  if (isUnread) {
    cardEl.addClass("furnace-report-unread");
  }

  const actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });
  const openBtn = actions.createEl("button", {
    cls: "mod-cta",
    text: plugin.t("Open report"),
  });
  openBtn.addEventListener("click", () => {
    plugin.goToReport(entry.target);
  });

  // 仅 advanced mode 显示 View graph 按钮 (EP-004 SC#2)
  if (plugin.settings && plugin.settings.showAdvancedCommands) {
    const graphBtn = actions.createEl("button", {
      text: plugin.t("View graph"),
    });
    graphBtn.addEventListener("click", async () => {
      await plugin.runReportSubgraphCommand({ reportPath: entry.target });
    });
  }
}

function renderConfirmationCard(plugin, cardEl, entry) {
  const actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });

  if (entry.target && entry.target.startsWith("review:")) {
    const reviewBtn = actions.createEl("button", {
      cls: "mod-cta",
      text: plugin.t("Review"),
    });
    reviewBtn.addEventListener("click", () => {
      plugin.viewReviewTodayEntry(entry);
    });

    const snoozeBtn = actions.createEl("button", {
      text: plugin.t("Snooze"),
    });
    snoozeBtn.addEventListener("click", () => {
      plugin.snoozeTodayEntry(entry.target);
    });
  }
}

function renderAutomationCard(plugin, cardEl, entry) {
  const state = String(entry.autoState || "idle");
  var stateLabel, stateClass;
  switch (state) {
    case "ok":
      stateLabel = plugin.t("正常运行");
      stateClass = "furnace-auto-state-ok";
      break;
    case "pending":
      stateLabel = plugin.t("待确认");
      stateClass = "furnace-auto-state-pending";
      break;
    case "attention":
      stateLabel = plugin.t("需要关注");
      stateClass = "furnace-auto-state-attention";
      break;
    default:
      stateLabel = plugin.t("空闲");
      stateClass = "furnace-auto-state-idle";
  }
  var pill = cardEl.createDiv({ cls: "furnace-auto-state-pill " + stateClass, text: stateLabel });
}

function isReportUnread(plugin, entry) {
  const lastViewed = plugin.settings && plugin.settings.lastViewedTimestamp;
  if (!lastViewed || !entry.timestamp) return false;
  return entry.timestamp > lastViewed;
}

module.exports = {
  renderFeedCard,
  renderReportCard,
  renderConfirmationCard,
  renderAutomationCard,
  isReportUnread,
};
