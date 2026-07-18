async function handleProductShellVaultChange(plugin, relativePath) {
  if (!relativePath) {
    return;
  }
  if (relativePath === ".obsidian/graph.json" && typeof plugin.maybeRepairEvidenceGraphFilter === "function") {
    void plugin.maybeRepairEvidenceGraphFilter().catch(() => {});
    return;
  }
  if (relativePath === SHELL_SUMMARY_PATH) {
    await plugin.loadShellSummaryFromDisk();
    return;
  }
  if (relativePath.startsWith("output/") || relativePath.startsWith("wiki/indexes/")) {
    plugin.refreshOpenViews();
  }
}

async function syncProductShellEvidenceGraphConfig(plugin, { quiet = true } = {}) {
  if (!plugin.repoState.valid) {
    return null;
  }
  try {
    return await plugin.execLauncher(["sync-evidence-graph"]);
  } catch (error) {
    if (!quiet) {
      console.error("[furnace-product-shell] sync-evidence-graph failed", error);
    }
    return null;
  }
}

async function maybeRepairProductShellEvidenceGraphFilter(plugin) {
  const adapter = plugin.app.vault.adapter;
  const graphPath = ".obsidian/graph.json";
  if (!(await adapter.exists(graphPath))) {
    return;
  }
  try {
    const raw = await adapter.read(graphPath);
    const parsed = JSON.parse(raw);
    const search = String(parsed.search || "").trim();
    if (!search || search.includes("wiki/concepts")) {
      await plugin.syncEvidenceGraphConfig({ quiet: true });
    }
  } catch {
    await plugin.syncEvidenceGraphConfig({ quiet: true });
  }
}

async function openProductShellEvidenceGraphView(plugin) {
  await plugin.syncEvidenceGraphConfig({ quiet: false });
  await plugin.openWorkspacePath("wiki/evidence-graph.md");
  if (plugin.app.commands?.executeCommandById) {
    await plugin.app.commands.executeCommandById("graph:open");
  }
}

async function copyProductShellText(plugin, value) {
  const text = String(value || "").trim();
  if (!text) {
    new Notice(plugin.t("Nothing to copy."));
    return false;
  }
  if (clipboard && typeof clipboard.writeText === "function") {
    clipboard.writeText(text);
    new Notice(plugin.t("Copied to clipboard."));
    return true;
  }
  if (window.navigator && window.navigator.clipboard && typeof window.navigator.clipboard.writeText === "function") {
    await window.navigator.clipboard.writeText(text);
    new Notice(plugin.t("Copied to clipboard."));
    return true;
  }
  new Notice(plugin.t("Clipboard is not available in this environment."));
  return false;
}

async function revealProductShellWorkspacePath(plugin, relativePath) {
  const normalized = String(relativePath || "").trim();
  const absolutePath = plugin.resolveAbsoluteWorkspacePath(normalized);
  if (!normalized || !absolutePath || !fs.existsSync(absolutePath)) {
    new Notice(plugin.t("Path not found: {path}", { path: normalized || relativePath || "" }));
    return;
  }
  if (shell && typeof shell.showItemInFolder === "function") {
    shell.showItemInFolder(absolutePath);
    return;
  }
  if (shell && typeof shell.openPath === "function") {
    await shell.openPath(path.dirname(absolutePath));
    return;
  }
  new Notice(plugin.t("Unable to reveal {path}", { path: normalized }));
}

async function openProductShellHomeNote(plugin) {
  await plugin.openWorkspacePath("HOME.md");
}

async function openProductShellOutputsHub(plugin) {
  const links = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.links || {} : {};
  const preferredPath = String(links.output_packs_markdown || "docs/Outputs.md").trim();
  await plugin.openWorkspacePath(preferredPath);
}

async function openProductShellPendingDoneTarget(plugin, target, reconcilePath) {
  const normalizedPath = String(reconcilePath || "").trim();
  const normalizedTarget = String(target || "").trim();
  if (normalizedPath) {
    let opened = false;
    try {
      opened = await plugin.openWorkspacePath(normalizedPath);
    } catch (error) {
      opened = false;
    }
    if (opened) return;
  }
  try {
    if (normalizedTarget === "outputs" && typeof plugin.openOutputsHub === "function") {
      await plugin.openOutputsHub();
      new Notice(plugin.t("已打开输出汇总（找不到具体报告路径）"));
      return;
    }
    if (normalizedTarget === "receipts" && typeof plugin.openFurnaceCenterView === "function") {
      await plugin.openFurnaceCenterView();
      new Notice(plugin.t("已回到 Today（找不到具体回执路径）"));
      return;
    }
    if (typeof plugin.openHomeNote === "function") {
      await plugin.openHomeNote();
      return;
    }
  } catch (error) {
    // Last resort is a user-facing notice below.
  }
  new Notice(plugin.t("无法打开目标，可能尚未生成"));
}

async function readProductShellWorkspaceSnippet(plugin, relativePath, length = 420) {
  const resolvedPath = resolveWorkspaceSnippetPath(plugin.repoState.root, relativePath);
  if (!resolvedPath) return "";
  try {
    const raw = await fs.promises.readFile(resolvedPath, "utf8");
    return workspaceSnippetFromMarkdown(raw, length);
  } catch (error) {
    return "";
  }
}

function quoteProductShellFileToComposer(plugin, relativePath) {
  const normalized = String(relativePath || "").trim();
  if (!normalized) return false;
  const textarea = document.querySelector(".furnace-universal-input-textarea");
  if (!textarea) {
    new Notice(plugin.t("找不到输入框，无法引用报告"));
    return false;
  }
  const quoteLine = plugin.t("引用报告：{path}", { path: normalized });
  const update = appendComposerReportQuote(textarea.value, quoteLine);
  if (update.changed) {
    textarea.value = update.value;
  }
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.focus();
  try { textarea.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (error) {}
  return true;
}

async function openProductShellWorkspacePath(plugin, relativePath) {
  const requestedPath = String(relativePath || "").trim();
  const normalized = normalizeWorkspaceRelativePath(requestedPath);
  if (!requestedPath) {
    new Notice(plugin.t("No path to open."));
    return false;
  }
  if (!normalized) {
    new Notice(plugin.t("Unable to open {path}", { path: requestedPath }));
    return false;
  }
  const abstractFile = plugin.app.vault.getAbstractFileByPath(normalized);
  if (abstractFile && normalized.endsWith(".md")) {
    const leaf = plugin.app.workspace.getLeaf(true);
    await leaf.openFile(abstractFile);
    return true;
  }
  if (!plugin.repoState.root) {
    new Notice(plugin.t("Unable to open {path}", { path: normalized }));
    return false;
  }
  const absolutePath = resolveWorkspaceSnippetPath(plugin.repoState.root, normalized);
  if (!fs.existsSync(absolutePath)) {
    new Notice(plugin.t("Path not found: {path}", { path: normalized }));
    return false;
  }
  if (typeof plugin.app.vault.adapter.getResourcePath === "function") {
    const resourcePath = plugin.app.vault.adapter.getResourcePath(normalized);
    window.open(resourcePath, "_blank");
    return true;
  }
  new Notice(plugin.t("Unable to open resource: {path}", { path: normalized }));
  return false;
}

function updateProductShellStatusBar(plugin) {
  if (!plugin.statusBarItem) {
    return;
  }
  const runningCount = plugin.pluginState.recentRuns.filter((entry) => entry.status === "running").length;
  if (!plugin.repoState.valid) {
    plugin.statusBarItem.setText(plugin.t("Furnace shell unavailable"));
    plugin.statusBarItem.setAttribute("aria-label", plugin.t("Missing runtime paths: {missing}", { missing: plugin.repoState.missingPaths.join(", ") }));
    return;
  }
  const protocol = plugin.getActiveProtocol();
  const llmHealth = plugin.currentLlmHealth();
  const syncState = plugin.currentShellSyncState();
  const llmSuffix = llmHealth.status === "degraded" ? plugin.t(" | llm degraded") : "";
  const syncSuffix = syncState.status === "running" ? plugin.t(" | syncing") : "";
  const suffix = runningCount ? plugin.t(" | running {count}", { count: runningCount }) : "";
  plugin.statusBarItem.setText(`${plugin.t("Furnace")} ${protocol}${llmSuffix}${syncSuffix}${suffix}`);
  plugin.statusBarItem.setAttribute("aria-label", plugin.t("Furnace Product Shell active protocol {protocol}", { protocol }));
}

async function loadProductShellSummaryFromDisk(plugin) {
  if (!plugin.repoState.valid) {
    plugin.shellSummary = null;
    plugin.updateStatusBar();
    plugin.refreshOpenViews();
    return null;
  }
  let text = null;
  const summaryFile = plugin.app.vault.getAbstractFileByPath(SHELL_SUMMARY_PATH);
  if (summaryFile) {
    try {
      text = await plugin.app.vault.cachedRead(summaryFile);
    } catch (error) {
      console.error("[furnace-product-shell] vault read failed for shell summary, falling back to fs", error);
      text = null;
    }
  }
  if (text === null && plugin.repoState.root) {
    const absPath = path.join(plugin.repoState.root, SHELL_SUMMARY_PATH);
    try {
      if (fs.existsSync(absPath)) {
        text = fs.readFileSync(absPath, "utf8");
      }
    } catch (error) {
      console.error("[furnace-product-shell] fs read failed for shell summary", error);
      text = null;
    }
  }
  if (text === null) {
    plugin.shellSummary = null;
    plugin.updateStatusBar();
    plugin.refreshOpenViews();
    return null;
  }
  try {
    plugin.shellSummary = readJsonText(text);
    plugin.processShellSummaryUpdates(plugin.shellSummary);
  } catch (error) {
    console.error("[furnace-product-shell] failed to parse shell summary", error);
    plugin.shellSummary = null;
  }
  plugin.updateStatusBar();
  plugin.refreshOpenViews();
  return plugin.shellSummary;
}
