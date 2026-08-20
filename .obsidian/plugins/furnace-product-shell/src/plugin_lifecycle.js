const REPORT_OUTPUT_REFRESH_DEBOUNCE_MS = 600;

function scheduleReportShellSummaryRefresh(plugin) {
  if (!plugin || typeof plugin.refreshShellSummarySilently !== "function") {
    return;
  }
  if (plugin._reportShellSummaryRefreshTimer) {
    clearTimeout(plugin._reportShellSummaryRefreshTimer);
  }
  plugin._reportShellSummaryRefreshTimer = setTimeout(() => {
    plugin._reportShellSummaryRefreshTimer = null;
    void plugin.refreshShellSummarySilently();
  }, REPORT_OUTPUT_REFRESH_DEBOUNCE_MS);
}

async function handleProductShellVaultChange(plugin, relativePath) {
  if (!relativePath) {
    return;
  }
  if (relativePath === SHELL_SUMMARY_PATH) {
    await plugin.loadShellSummaryFromDisk();
    return;
  }
  if (relativePath.startsWith("output/reports/")) {
    scheduleReportShellSummaryRefresh(plugin);
    plugin.refreshOpenViews();
    return;
  }
  if (relativePath.startsWith("output/") || relativePath.startsWith("wiki/indexes/")) {
    plugin.refreshOpenViews();
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
  // The furnace-center panel's 最近输出 section is the outputs hub; the old
  // output-packs index page was retired (no compile writer).
  const preferredPath = String(links.furnace_center_markdown || "wiki/indexes/furnace-center.md").trim();
  await plugin.openWorkspacePath(preferredPath);
}

async function openProductShellPendingDoneTarget(plugin, target, reconcilePath) {
  const normalizedPath = String(reconcilePath || "").trim();
  const normalizedTarget = String(target || "").trim();
  let openPath = normalizedPath;
  if (openPath && normalizedTarget === "outputs") {
    const blocked = await isPlaceholderAskReportPath(plugin, openPath);
    if (blocked) {
      new Notice(plugin.t("报告仍在生成中，请稍候再打开"));
      return;
    }
    openPath = resolveMissingReportOpenPath(plugin, openPath) || openPath;
  }
  if (openPath) {
    let opened = false;
    try {
      opened = await plugin.openWorkspacePath(openPath);
    } catch (error) {
      opened = false;
    }
    if (opened) {
      if (openPath !== normalizedPath) {
        new Notice(plugin.t("原报告路径已不存在，已打开同名报告"));
      }
      return;
    }
  }
  try {
    if (normalizedTarget === "outputs" && typeof plugin.openOutputsHub === "function") {
      await plugin.openOutputsHub();
      if (normalizedPath && !plugin.app.vault.getAbstractFileByPath(normalizedPath)) {
        new Notice(plugin.t("报告文件已不存在：{path}", { path: normalizedPath }));
      } else {
        new Notice(plugin.t("已打开输出汇总（找不到具体报告路径）"));
      }
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

function resolveMissingReportOpenPath(plugin, relativePath) {
  const path = String(relativePath || "").trim();
  if (!path || !plugin || !plugin.app || !plugin.app.vault) return "";
  if (plugin.app.vault.getAbstractFileByPath(path)) return path;
  if (!path.startsWith("output/reports/") || !path.endsWith(".md")) return "";
  const match = path.match(/^(output\/reports\/.+)-(\d+)\.md$/);
  if (!match) return "";
  const fallback = `${match[1]}.md`;
  return plugin.app.vault.getAbstractFileByPath(fallback) ? fallback : "";
}

async function isPlaceholderAskReportPath(plugin, relativePath) {
  const path = String(relativePath || "").trim();
  if (!path || !plugin || !plugin.app || !plugin.app.vault) return false;
  try {
    const abstract = plugin.app.vault.getAbstractFileByPath(path);
    if (!abstract) return false;
    const text = await plugin.app.vault.read(abstract);
    const body = String(text || "");
    if (body.includes("_LLM:")) return true;
    const fm = body.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!fm) return false;
    const block = fm[1];
    if (/^llm_status:\s*["']?pending["']?\s*$/m.test(block)) return true;
    if (/^artifact_quality:\s*["']?placeholder["']?\s*$/m.test(block)) return true;
    if (/^delivery_mode:\s*["']?llm-pending["']?\s*$/m.test(block)) return true;
    return false;
  } catch (_error) {
    return false;
  }
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

function prefillProductShellComposer(plugin, { question, materialPaths } = {}) {
  const textarea = document.querySelector(".furnace-universal-input-textarea");
  if (!textarea) {
    new Notice(plugin.t("找不到输入框，无法编辑问题"));
    return false;
  }
  const nextQuestion = String(question || "").trim();
  textarea.value = nextQuestion;
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.focus();
  try { textarea.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (error) {}
  const paths = normalizeMaterialPaths(materialPaths);
  if (paths.length && plugin.settings) {
    setStickyMaterialRefs(plugin.settings, paths, "explicit-@");
    if (typeof plugin.savePluginState === "function") {
      try {
        const result = plugin.savePluginState();
        if (result && typeof result.then === "function") {
          void result.catch(() => {});
        }
      } catch (_error) {
        // Prefill must not fail the edit action if persistence is unavailable.
      }
    }
  }
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
  if (normalized.startsWith("output/reports/")) {
    const blocked = await isPlaceholderAskReportPath(plugin, normalized);
    if (blocked) {
      new Notice(plugin.t("报告仍在生成中，请稍候再打开"));
      return false;
    }
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
  // File exists on disk but Obsidian did not index it (common when path is in
  // Settings → Files → Excluded files / userIgnoreFilters). Do not silently
  // window.open — Desktop often shows no visible result.
  new Notice(
    plugin.t(
      "File exists but Obsidian has not indexed it (check Excluded files / userIgnoreFilters): {path}",
      { path: normalized }
    )
  );
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
  if (plugin.repoState.root) {
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
    const summaryFile = plugin.app.vault.getAbstractFileByPath(SHELL_SUMMARY_PATH);
    if (summaryFile) {
      try {
        text = await plugin.app.vault.cachedRead(summaryFile);
      } catch (error) {
        console.error("[furnace-product-shell] vault read failed for shell summary", error);
        text = null;
      }
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
