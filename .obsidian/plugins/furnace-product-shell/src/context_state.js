"use strict";

function getActiveProtocolFromSummary(summary) {
  return String(summary && summary.active_protocol ? summary.active_protocol : "general");
}

function getAvailableProtocolsFromSummary(summary) {
  const fromSummary = summary && Array.isArray(summary.available_protocols)
    ? summary.available_protocols.filter((item) => typeof item === "string" && item)
    : [];
  return fromSummary.length ? fromSummary : DEFAULT_PROTOCOLS;
}

function getActiveFilePathFromApp(app) {
  const workspace = app && app.workspace ? app.workspace : null;
  const activeFile = workspace && workspace.getActiveFile ? workspace.getActiveFile() : null;
  return activeFile && typeof activeFile.path === "string" ? activeFile.path : "";
}

function getConceptSlugForPath(activePath) {
  const normalized = String(activePath || "");
  if (!normalized.startsWith("wiki/concepts/") || !normalized.endsWith(".md")) {
    return "";
  }
  return path.basename(normalized, ".md");
}

function getOutputPathForPath(activePath) {
  const normalized = String(activePath || "");
  if (normalized.startsWith("output/") && normalized.endsWith(".md")) {
    return normalized;
  }
  return "";
}

function getCuratedPagePathForSummary(activePath, summary) {
  const normalized = String(activePath || "");
  if (!normalized.endsWith(".md")) {
    return "";
  }
  const roots = summary && typeof summary === "object" ? summary.curated_page_roots : null;
  if (!roots || typeof roots !== "object") {
    return "";
  }
  for (const key of Object.keys(roots)) {
    const prefix = roots[key];
    if (typeof prefix === "string" && prefix && normalized.startsWith(prefix)) {
      return normalized;
    }
  }
  return "";
}
