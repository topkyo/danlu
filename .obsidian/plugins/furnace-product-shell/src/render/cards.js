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

function compoundLootCopy(plugin, action) {
  if (action === "alchemy-start") {
    return {
      bannerCls: "furnace-loot-banner furnace-loot-alchemy",
      badge: plugin.t("可凝丹"),
      cta: plugin.t("凝丹"),
      buttonCls: "mod-cta furnace-compound-alchemy-start",
    };
  }
  if (action === "file-back-judgment") {
    return {
      bannerCls: "furnace-loot-banner furnace-loot-file-back",
      badge: plugin.t("可沉淀"),
      cta: plugin.t("沉淀"),
      buttonCls: "mod-cta furnace-compound-file-back",
    };
  }
  return null;
}

function runCompoundSuggestAction(plugin, suggest) {
  const action = String(suggest && suggest.action || "").trim();
  if (action === "file-back-judgment") {
    if (typeof plugin.runCompoundFileBack === "function") plugin.runCompoundFileBack(suggest);
    return;
  }
  if (action === "alchemy-start") {
    if (typeof plugin.openCompoundAlchemyStart === "function") plugin.openCompoundAlchemyStart(suggest);
  }
}

function renderCompoundLootBanner(plugin, parentEl, suggest) {
  const action = String(suggest && suggest.action || "").trim();
  const reportPath = String(suggest && (suggest.report_path || suggest.reportPath) || "").trim();
  if (
    action === "file-back-judgment"
    && reportPath
    && plugin
    && plugin._locallyFiledReports instanceof Set
    && plugin._locallyFiledReports.has(reportPath)
  ) {
    return null;
  }
  const copy = compoundLootCopy(plugin, action);
  if (!copy) return null;
  const banner = parentEl.createDiv({ cls: copy.bannerCls });
  banner.createSpan({ cls: "furnace-loot-badge", text: copy.badge });
  const cta = banner.createEl("button", {
    cls: copy.buttonCls,
    text: copy.cta,
    attr: { type: "button" },
  });
  banner.addEventListener("click", (event) => {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (banner.classList.contains("is-busy")) return;
    banner.classList.add("is-busy");
    cta.disabled = true;
    runCompoundSuggestAction(plugin, suggest);
  });
  return banner;
}

function renderReportCard(plugin, cardEl, entry) {
  const suggest = entry.compound_suggest || entry.compoundSuggest;
  if (suggest && typeof suggest === "object") {
    renderCompoundLootBanner(plugin, cardEl, suggest);
  }
  const actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });
  const openBtn = actions.createEl("button", {
    cls: suggest ? "" : "mod-cta",
    text: plugin.t("Open report"),
  });
  openBtn.addEventListener("click", () => {
    if (typeof plugin.openPendingDoneTarget === "function") {
      void plugin.openPendingDoneTarget("outputs", entry.target);
      return;
    }
    plugin.openWorkspacePath(entry.target);
  });
}

function renderCompoundSuggestActionCard(plugin, cardEl, entry) {
  const suggest = entry.compound_suggest || entry.compoundSuggest;
  if (!suggest || typeof suggest !== "object") return;
  renderCompoundLootBanner(plugin, cardEl, suggest);
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
  renderCompoundLootBanner,
  compoundLootCopy,
};
