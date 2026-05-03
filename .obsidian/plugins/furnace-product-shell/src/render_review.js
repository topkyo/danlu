// Review center render function extracted from render.js.

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
    { label: t("待决策"), value: review.pending_decisions || 0 },
    { label: t("待判断"), value: review.pending_judgments || 0 },
    { label: t("逾期审阅"), value: aging.overdue_count || 0 },
    { label: t("已升级"), value: aging.escalated_count || 0 },
    { label: t("概念积压"), value: review.concept_backlog || 0 },
    { label: t("待审概念"), value: review.review_concepts || 0 },
    { label: t("需回访概念"), value: review.revisit_concepts || 0 },
    { label: t("已退役概念"), value: review.retired_concepts || 0 },
  ]);

  const nextReview = plugin.nextReviewCandidate();
  const batchSuggestions = plugin.reviewBatchSuggestions();

  const nextSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  nextSection.createEl("h3", { text: plugin.t("下一个审阅") });
  if (!nextReview) {
    nextSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("当前没有待审阅项。") });
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
  batchSection.createEl("h3", { text: plugin.t("批处理建议") });
  if (!batchSuggestions.length) {
    batchSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("暂无批处理建议。") });
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
  judgmentSection.createEl("h3", { text: plugin.t("判断资产") });
  plugin.renderCardGrid(judgmentSection, [
    { label: plugin.t("强资产"), value: judgmentCounts.strong_assets || 0 },
    { label: plugin.t("需关注页"), value: judgmentCounts.attention_pages || 0 },
    { label: plugin.t("缺反证"), value: judgmentCounts.missing_counter_evidence || 0 },
    { label: plugin.t("缺失效条件"), value: judgmentCounts.missing_invalidation || 0 },
    { label: plugin.t("缺审阅历史"), value: judgmentCounts.missing_review_history || 0 },
    { label: plugin.t("引用漂移"), value: judgmentCounts.citation_drift || 0 },
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
  renderReviewObjectSection(plugin.t("决策页"), decisionControlObjects, plugin.t("当前没有待审决策页。"));
  renderReviewObjectSection(plugin.t("判断页"), judgmentControlObjects, plugin.t("当前没有待审判断页。"));

  const rewriteControlObjects = plugin.reviewControlList("rewrite_proposals");
  const rewriteSection = contentEl.createDiv({ cls: "furnace-shell-section" });
  rewriteSection.createEl("h3", { text: plugin.t("改写提案") });
  if (!rewriteControlObjects.length) {
    rewriteSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("当前没有改写提案。") });
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

  // ── Aging (foldable) ──
  const agingDetails = contentEl.createEl("details", { cls: "furnace-shell-section" });
  agingDetails.createEl("summary", { text: plugin.t("老化摘要") + " · " + (aging.overdue_count || 0) + " 逾期 / " + (aging.escalated_count || 0) + " 升级", cls: "furnace-shell-panel-description" });
  const agingBody = agingDetails.createDiv();
  const agingList = agingBody.createEl("ul", { cls: "furnace-shell-list" });
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

  // ── Recent Review Events (foldable) ──
  const reviewEvents = Array.isArray(plugin.shellSummary.recent_runs)
    ? plugin.shellSummary.recent_runs.filter((entry) => entry.event_type === "review")
    : [];
  const eventsDetails = contentEl.createEl("details", { cls: "furnace-shell-section" });
  eventsDetails.createEl("summary", { text: plugin.t("最近审阅事件") + " (" + reviewEvents.length + ")", cls: "furnace-shell-panel-description" });
  const eventsBody = eventsDetails.createDiv();
  if (!reviewEvents.length) {
    eventsBody.createDiv({ cls: "furnace-shell-empty", text: plugin.t("暂无最近审阅事件。") });
  } else {
    const list = eventsBody.createEl("ul", { cls: "furnace-shell-list" });
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

  // ── Links (foldable) ──
  const links = plugin.shellSummary.links || {};
  const linksDetails = contentEl.createEl("details", { cls: "furnace-shell-section" });
  linksDetails.createEl("summary", { text: plugin.t("治理链接"), cls: "furnace-shell-panel-description" });
  const linksBody = linksDetails.createDiv();
  const linkList = linksBody.createEl("ul", { cls: "furnace-shell-list" });
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

