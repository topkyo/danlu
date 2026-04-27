// Execution center render function extracted from render.js.

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

