// Simplified Execution Center — only key summary and recent activity.

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
  ]);

  if (!plugin.shellSummary) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("shell-summary.json is not available yet. Run Refresh, Compile, or Nightly first."),
    });
    return;
  }

  // Summary stats only
  var receipts = Array.isArray(plugin.shellSummary.recent_receipts) ? plugin.shellSummary.recent_receipts : [];
  var actionControls = plugin.executionControlList("actions");
  var pendingActions = actionControls.filter(function (a) { return a && a.can_apply; }).length;

  var summaryRow = contentEl.createDiv({ cls: "furnace-shell-section" });
  summaryRow.createEl("h3", { text: plugin.t("执行概况") });
  var stats = summaryRow.createDiv({ cls: "furnace-shell-meta" });
  stats.setText(
    plugin.t("待执行动作") + ": " + pendingActions + "  |  " + plugin.t("最近收据") + ": " + receipts.length
  );

  // Recent activity: last 3 receipts
  if (receipts.length) {
    var recentSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    recentSection.createEl("h3", { text: plugin.t("最近活动") });
    var list = recentSection.createEl("ul", { cls: "furnace-shell-list" });
    receipts.slice(0, 3).forEach(function (entry) {
      var item = list.createEl("li");
      item.createEl("strong", { text: entry.title || entry.event_type || plugin.t("operation") });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: (entry.status || "") + " | " + (entry.occurred_at || ""),
      });
    });
  } else {
    contentEl.createDiv({ cls: "furnace-shell-empty", text: plugin.t("暂无最近收据。") });
  }

  // Quick link to full execution page
  var links = plugin.shellSummary.links || {};
  if (links.execution_center_markdown) {
    var linkDiv = contentEl.createDiv({ cls: "furnace-shell-section" });
    var linkBtn = linkDiv.createEl("button", { text: plugin.t("查看完整执行页") });
    linkBtn.addEventListener("click", function () {
      plugin.runUiAction(function () { return plugin.openWorkspacePath(links.execution_center_markdown); }, "Open execution markdown");
    });
  }
}
