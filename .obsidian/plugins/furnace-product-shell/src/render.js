// Standalone render functions extracted from the Plugin class.
// Each function takes the plugin instance as its first argument.

function renderFurnaceCenter(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.addClass("furnace-shell-main-view");
  contentEl.addClass("furnace-shell-v3");

  if (!plugin.repoState.valid) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("Vault runtime unavailable. Missing scaffold or launcher: {missing}", {
        missing: plugin.repoState.missingPaths.join(", "),
      }),
    });
    return;
  }

  // 1. Universal Input
  renderUniversalInput(plugin, contentEl);

  // 2. Today Feed (统一 5 类)
  renderTodayFeed(plugin, contentEl);

  // 3. Advanced Drawer
  renderAdvancedDrawer(plugin, contentEl);
}

function renderAdvancedDrawer(plugin, container) {
  const details = container.createEl("details", { cls: "furnace-shell-advanced" });
  details.createEl("summary", { cls: "furnace-shell-advanced-summary", text: plugin.t("Advanced") });
  const body = details.createDiv({ cls: "furnace-shell-advanced-body" });

  plugin.renderMainHeader(body);
  plugin.renderStatusPanel(body);
  plugin.renderLegacyAdvancedPanel(body);

  renderAdvancedMetricsPanel(plugin, body);
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
  if (!compact && record.modelSelected && record.modelFinal && record.modelSelected !== record.modelFinal) {
    contextParts.push(`${plugin.t("selected")} ${record.modelSelected} -> ${plugin.t("final")} ${record.modelFinal}`);
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
    if (record.fallbackStage) {
      diagnosticParts.push(plugin.t("fallback {value}", { value: record.fallbackStage }));
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
  const rewriteProposalObjects = Array.isArray(record.rewriteProposalObjects) ? record.rewriteProposalObjects : [];
  const rewriteProposalPaths = rewriteProposalObjects.length
    ? plugin.rewriteProposalPathsFromObjects(rewriteProposalObjects)
    : (Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths : []);
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
    const firstProposalPath = rewriteProposalObjects[0] && rewriteProposalObjects[0].proposalPath
      ? rewriteProposalObjects[0].proposalPath
      : rewriteProposalPaths[0];
    const proposalButton = actions.createEl("button", { text: plugin.t("Open proposal") });
    proposalButton.addEventListener("click", () => {
      plugin.runUiAction(() => plugin.openWorkspacePath(firstProposalPath), `Open rewrite proposal: ${firstProposalPath}`);
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

function renderAdvancedMetricsPanel(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  if (!summary) return;
  
  const metrics = Array.isArray(summary.metrics) ? summary.metrics : [];
  
  const section = container.createDiv({ cls: "furnace-advanced-metrics" });
  section.createEl("h3", { text: plugin.t("Knowledge Compounding Metrics") });
  
  if (!metrics.length) {
    section.createEl("div", {
      cls: "furnace-advanced-metrics-empty",
      text: plugin.t("(metrics unavailable; run aiwiki metrics for details)"),
    });
    return;
  }
  
  const list = section.createEl("ul", { cls: "furnace-advanced-metrics-list" });
  
  const labels = {
    provenance_completeness: plugin.t("Provenance Completeness"),
    stale_ratio: plugin.t("Stale Page Ratio"),
    review_closure_rate: plugin.t("Review Closure Rate (7d)"),
    proposal_acceptance_rate: plugin.t("Proposal Acceptance Rate"),
    judgment_revisit_rate: plugin.t("Judgment Revisit Rate"),
    output_file_back_rate: plugin.t("Output File-back Rate"),
    elixir_reuse_count: plugin.t("Elixir Reuse Count"),
  };
  
  for (const m of metrics) {
    if (!m || typeof m !== "object") continue;
    const li = list.createEl("li", { cls: "furnace-advanced-metrics-item" });
    const labelText = labels[m.key] || m.key;
    li.createEl("span", { cls: "furnace-advanced-metrics-label", text: labelText });
    
    if (m.value === null || m.value === undefined) {
      li.createEl("span", {
        cls: "furnace-advanced-metrics-value furnace-advanced-metrics-unavailable",
        text: plugin.t("unavailable"),
      });
      if (m.reason) {
        li.createEl("span", {
          cls: "furnace-advanced-metrics-reason",
          text: ` — ${m.reason}`,
        });
      }
    } else {
      const formatted = formatMetricValue(m.value, m.unit);
      li.createEl("span", {
        cls: "furnace-advanced-metrics-value",
        text: formatted,
      });
      if (typeof m.sample_size === "number" && m.sample_size > 0) {
        li.createEl("span", {
          cls: "furnace-advanced-metrics-sample",
          text: ` (n=${m.sample_size})`,
        });
      }
    }
  }
  
  section.createEl("div", {
    cls: "furnace-advanced-metrics-hint",
    text: plugin.t("Run `aiwiki metrics --json` for full data."),
  });
}

function formatMetricValue(value, unit) {
  if (typeof value !== "number") return String(value);
  if (unit === "ratio") return (value * 100).toFixed(1) + "%";
  if (unit === "percent") return value.toFixed(1) + "%";
  if (unit === "count") return String(value);
  return String(value);
}
