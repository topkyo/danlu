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
  const actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });
  const suggest = entry.compound_suggest || entry.compoundSuggest;
  if (suggest && typeof suggest === "object") {
    renderCompoundSuggestActions(plugin, actions, suggest);
  }
  const openBtn = actions.createEl("button", {
    cls: suggest ? "" : "mod-cta",
    text: plugin.t("Open report"),
  });
  openBtn.addEventListener("click", () => {
    plugin.openWorkspacePath(entry.target);
  });

}

function renderCompoundSuggestActionCard(plugin, cardEl, entry) {
  const suggest = entry.compound_suggest || entry.compoundSuggest;
  if (!suggest || typeof suggest !== "object") return;
  const actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });
  renderCompoundSuggestActions(plugin, actions, suggest);
}

function renderCompoundSuggestActions(plugin, actionsEl, suggest) {
  const action = String(suggest.action || "").trim();
  if (action === "file-back-judgment") {
    const fileBackBtn = actionsEl.createEl("button", {
      cls: "mod-cta furnace-compound-file-back",
      text: plugin.t("沉淀"),
    });
    fileBackBtn.addEventListener("click", () => {
      plugin.runCompoundFileBack(suggest);
    });
    return;
  }
  if (action === "alchemy-start") {
    const alchemyBtn = actionsEl.createEl("button", {
      cls: "mod-cta furnace-compound-alchemy-start",
      text: plugin.t("凝丹"),
    });
    alchemyBtn.addEventListener("click", () => {
      plugin.openCompoundAlchemyStart(suggest);
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
      if (typeof plugin.openReviewPageContextPicker === "function") {
        plugin.openReviewPageContextPicker();
      }
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

module.exports = {
  renderFeedCard,
  renderReportCard,
  renderConfirmationCard,
  renderAutomationCard,
  renderCompoundSuggestActionCard,
  renderCompoundSuggestActions,
};
