// Standalone render functions extracted from the Plugin class.
// Each function takes the plugin instance as its first argument.


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

