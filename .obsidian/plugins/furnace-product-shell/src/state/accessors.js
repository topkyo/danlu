// Extracted from plugin.js
// DEPRECATED: not concatenated into main.js; accessors inlined in bundled modules.

function getActiveProtocol(plugin) {
    return String(plugin.shellSummary && plugin.shellSummary.active_protocol ? plugin.shellSummary.active_protocol : "general");
  }


function getAvailableProtocols(plugin) {
    const fromSummary = plugin.shellSummary && Array.isArray(plugin.shellSummary.available_protocols)
      ? plugin.shellSummary.available_protocols.filter((item) => typeof item === "string" && item)
      : [];
    return fromSummary.length ? fromSummary : DEFAULT_PROTOCOLS;
  }


function getActiveFilePath(plugin) {
    const activeFile = plugin.app.workspace.getActiveFile ? plugin.app.workspace.getActiveFile() : null;
    return activeFile && typeof activeFile.path === "string" ? activeFile.path : "";
  }


function getActiveConceptSlug(plugin) {
    const activePath = plugin.getActiveFilePath();
    if (!activePath.startsWith("wiki/concepts/") || !activePath.endsWith(".md")) {
      return "";
    }
    return path.basename(activePath, ".md");
  }


function getActiveOutputPath(plugin) {
    const activePath = plugin.getActiveFilePath();
    if (activePath.startsWith("output/") && activePath.endsWith(".md")) {
      return activePath;
    }
    return "";
  }


function getActiveCuratedPagePath(plugin) {
    const activePath = plugin.getActiveFilePath();
    if (!activePath.endsWith(".md")) {
      return "";
    }
    // Curated-page prefixes come from the CLI summary (EP-015). Plugin no
    // longer hardcodes "wiki/decisions/" / "wiki/judgments/"; CLI is the
    // single source of truth for which repo-relative roots count as curated.
    const roots = (plugin.shellSummary && typeof plugin.shellSummary === "object")
      ? plugin.shellSummary.curated_page_roots
      : null;
    if (!roots || typeof roots !== "object") {
      return "";
    }
    for (const key of Object.keys(roots)) {
      const prefix = roots[key];
      if (typeof prefix === "string" && prefix && activePath.startsWith(prefix)) {
        return activePath;
      }
    }
    return "";
  }


module.exports = { getActiveProtocol, getAvailableProtocols, getActiveFilePath, getActiveConceptSlug, getActiveOutputPath, getActiveCuratedPagePath };
