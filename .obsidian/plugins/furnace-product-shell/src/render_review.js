// Simplified Review Center — only key summary and next action.

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
  ]);

  if (!plugin.shellSummary) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("数据还没准备好。先点上方刷新，或等当前任务跑完。"),
    });
    return;
  }

  var review = plugin.shellSummary.review_backlog_counts || {};
  var summaryRow = contentEl.createDiv({ cls: "furnace-shell-section" });
  summaryRow.createEl("h3", { text: plugin.t("审阅概况") });
  var stats = summaryRow.createDiv({ cls: "furnace-shell-meta" });
  stats.setText(
    plugin.t("待决策") + ": " + (review.pending_decisions || 0) +
    "  |  " + plugin.t("待判断") + ": " + (review.pending_judgments || 0)
  );

  var nextReview = plugin.nextReviewCandidate();
  if (nextReview) {
    var nextSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    nextSection.createEl("h3", { text: plugin.t("下一个审阅") });
    var nextCard = nextSection.createDiv({ cls: "furnace-shell-card" });
    nextCard.createEl("strong", { text: nextReview.label || nextReview.pagePath || plugin.t("review-page") });
    nextCard.createDiv({ cls: "furnace-shell-meta", text: nextReview.description || "" });
    var actions = nextCard.createDiv({ cls: "furnace-shell-inline-actions" });
    var openBtn = actions.createEl("button", { text: plugin.t("Open page") });
    openBtn.addEventListener("click", function () {
      plugin.runUiAction(function () { return plugin.openWorkspacePath(nextReview.pagePath); }, "Open review page: " + nextReview.pagePath);
    });
    plugin.preferredTransitionOptions("page", nextReview).forEach(function (transition) {
      var btn = actions.createEl("button", { text: transition.label });
      btn.addEventListener("click", function () {
        plugin.runUiAction(function () { return plugin.runReviewPageTransition(nextReview.pagePath, transition.value); }, "Next review: " + nextReview.pagePath + " -> " + transition.value);
      });
    });
  } else {
    contentEl.createDiv({ cls: "furnace-shell-empty", text: plugin.t("当前没有待审阅项。") });
  }

  // Quick link to full review markdown page
  var links = plugin.shellSummary.links || {};
  if (links.review_center_markdown) {
    var linkDiv = contentEl.createDiv({ cls: "furnace-shell-section" });
    var linkBtn = linkDiv.createEl("button", { text: plugin.t("查看完整审阅页") });
    linkBtn.addEventListener("click", function () {
      plugin.runUiAction(function () { return plugin.openWorkspacePath(links.review_center_markdown); }, "Open review markdown");
    });
  }
}
