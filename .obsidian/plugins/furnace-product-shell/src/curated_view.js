"use strict";

const CURATED_OUTPUT_LEAF_CLASS = "aiwiki-output";
const CURATED_OUTPUT_PATH_PREFIXES = ["wiki/judgments/", "wiki/elixirs/"];

function isCuratedOutputPath(relativePath) {
  const normalized = String(relativePath || "");
  if (!normalized.endsWith(".md")) {
    return false;
  }
  return CURATED_OUTPUT_PATH_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

function getMarkdownLeafPath(leaf) {
  const view = leaf && leaf.view ? leaf.view : null;
  if (!view || typeof view.getViewType !== "function" || view.getViewType() !== "markdown") {
    return "";
  }
  const file = view.file;
  return file && typeof file.path === "string" ? file.path : "";
}

function syncCuratedOutputLeafClass(leaf) {
  if (!leaf || !leaf.view) {
    return;
  }
  const container = leaf.view.containerEl;
  if (!container) {
    return;
  }
  const shouldHide = isCuratedOutputPath(getMarkdownLeafPath(leaf));
  if (shouldHide) {
    container.addClass(CURATED_OUTPUT_LEAF_CLASS);
  } else {
    container.removeClass(CURATED_OUTPUT_LEAF_CLASS);
  }
}

function syncAllCuratedOutputLeafClasses(workspace) {
  if (!workspace || typeof workspace.iterateAllLeaves !== "function") {
    return;
  }
  workspace.iterateAllLeaves((leaf) => syncCuratedOutputLeafClass(leaf));
}

function registerCuratedOutputLeafSync(plugin) {
  const sync = () => syncAllCuratedOutputLeafClasses(plugin.app.workspace);
  plugin.registerEvent(plugin.app.workspace.on("active-leaf-change", sync));
  plugin.registerEvent(plugin.app.workspace.on("layout-change", sync));
  sync();
}
