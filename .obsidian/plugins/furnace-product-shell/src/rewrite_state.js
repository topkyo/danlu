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

function openRewriteFollowupForRecord(plugin, _record) {
  if (typeof plugin.openReviewPageContextPicker === "function") {
    plugin.openReviewPageContextPicker();
  }
}
