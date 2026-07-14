// Pure rewrite proposal/recovery state helpers.

function normalizeRewriteProposalObjects(value) {
  const items = Array.isArray(value) ? value : [value];
  const seen = new Set();
  return items
    .map((item) => normalizeRewriteProposalObject(item))
    .filter((item) => {
      if (!item) {
        return false;
      }
      if (seen.has(item.slug)) {
        return false;
      }
      seen.add(item.slug);
      return true;
    });
}

function normalizeRewriteFollowupActions(value) {
  const items = Array.isArray(value) ? value : [value];
  const seen = new Set();
  return items
    .map((item) => normalizeRewriteFollowupAction(item))
    .filter((item) => {
      if (!item) {
        return false;
      }
      if (seen.has(item.command)) {
        return false;
      }
      seen.add(item.command);
      return true;
    });
}

function rewriteProposalPathsFromObjects(objects) {
  return normalizeRelativePathList(
    (Array.isArray(objects) ? objects : []).map((item) => item && item.proposalPath ? item.proposalPath : "")
  );
}

function rewriteProposalSlugsFromObjects(objects) {
  return normalizeRelativePathList(
    (Array.isArray(objects) ? objects : []).map((item) => item && item.slug ? item.slug : "")
  );
}

function extractRewriteProposalObjects(payload) {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  return normalizeRewriteProposalObjects(payload.updated_rewrite_proposals || []);
}

function extractRewriteFollowupActions(payload) {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const preferred = payload.rewrite_followup_actions;
  const historical = payload["rewrite_" + "recovery_actions"];
  return normalizeRewriteFollowupActions(
    Array.isArray(preferred) ? preferred : Array.isArray(historical) ? historical : []
  );
}

function extractRewriteProposalPaths(payload) {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const objects = extractRewriteProposalObjects(payload);
  return objects.length
    ? rewriteProposalPathsFromObjects(objects)
    : normalizeRelativePathList(payload.updated_rewrite_proposal_pages);
}

function extractRewriteProposalSlugs(paths) {
  return normalizeRelativePathList(paths).map((proposalPath) => path.basename(proposalPath, ".md"));
}

function rewriteProposalSummary(plugin, record) {
  const count = Array.isArray(record && record.rewriteProposalObjects) && record.rewriteProposalObjects.length
    ? record.rewriteProposalObjects.length
    : (Array.isArray(record && record.rewriteProposalPaths) ? record.rewriteProposalPaths.length : 0);
  if (!count) {
    return "";
  }
  return plugin.t("rewrite proposals: {count}", { count });
}

function openRewriteFollowupForRecord(plugin, record) {
  const recoveryActions = Array.isArray(record && record.rewriteFollowupActions)
    ? plugin.normalizeRewriteFollowupActions(record.rewriteFollowupActions)
    : [];
  const proposalObjects = Array.isArray(record && record.rewriteProposalObjects)
    ? plugin.normalizeRewriteProposalObjects(record.rewriteProposalObjects)
    : [];
  if (recoveryActions.length === 1) {
    const action = recoveryActions[0];
    const control = proposalObjects.find((item) => item.slug === action.slug) || action;
    if (action.kind === "apply-rewrite") {
      plugin.openApplyRewriteModal({ slug: action.slug });
      return;
    }
    plugin.openReviewRewriteTransitionPicker({
      ...control,
      slug: action.slug,
      status: action.status || control.status || control.currentStatus || "",
      currentStatus: action.currentStatus || control.currentStatus || control.status || "",
      allowedTransitions: action.allowedTransitions || control.allowedTransitions || [],
      preferredTransitions: action.preferredTransitions || control.preferredTransitions || [],
      defaultTransition: action.transition || action.defaultTransition || control.defaultTransition || "",
    });
    return;
  }
  if (proposalObjects.length > 1) {
    plugin.openReviewRewriteContextPicker(
      proposalObjects.map((proposal) => ({
        ...proposal,
        value: proposal.slug,
        label: proposal.title || proposal.slug || "rewrite-proposal",
        description: `${displayRewriteStatus(proposal.status || proposal.currentStatus || "unknown", plugin.locale())} | ${proposal.proposalPath || proposal.targetPath || ""}`,
      }))
    );
    return;
  }
  const rewriteControls = plugin.rewriteCandidatesForSlugs(record && record.rewriteProposalSlugs, "review");
  if (rewriteControls.length === 1) {
    plugin.openReviewRewriteTransitionPicker(rewriteControls[0]);
    return;
  }
  if (rewriteControls.length > 1) {
    plugin.openReviewRewriteContextPicker(rewriteControls);
    return;
  }
  const rewriteSlugs = normalizeRelativePathList(record && record.rewriteProposalSlugs);
  if (rewriteSlugs.length === 1) {
    plugin.openReviewRewriteModal({ slug: rewriteSlugs[0] });
    return;
  }
  plugin.runUiAction(() => plugin.openReviewCenterView(), plugin.t("Open Review Center"));
}
