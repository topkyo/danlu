// Extracted from plugin.js
// DEPRECATED: not concatenated into main.js; vault change handling lives in plugin.js.

async function handleVaultChange(plugin, relativePath) {
    if (!relativePath) {
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


function updateStatusBar(plugin) {
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


async function loadShellSummaryFromDisk(plugin) {
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


async function refreshShellSummarySilently(plugin) {
    try {
      const result = await plugin.execLauncher(["shell-status"]);
      if (result.payload && result.payload.kind === "product-shell-summary") {
        plugin.shellSummary = result.payload;
        plugin.processShellSummaryUpdates(plugin.shellSummary);
        plugin.updateStatusBar();
        plugin.refreshOpenViews();
        return result.payload;
      }
    } catch (error) {
      console.error("[furnace-product-shell] shell-status refresh failed", error);
    }
    return await plugin.loadShellSummaryFromDisk();
  }

  

function processShellSummaryUpdates(plugin, summary) {
    if (!summary || !Array.isArray(summary.recent_outputs)) return;
    const outputs = summary.recent_outputs.filter((item) => item && typeof item === "object");
    const currentIds = outputs.map((r) => r.path || r.title || r.created_at).filter(Boolean);
    const lastIds = Array.isArray(plugin.settings.lastKnownReportIds) ? plugin.settings.lastKnownReportIds.filter(Boolean) : [];

    if (!currentIds.length) {
      plugin.settings.lastKnownReportIds = [];
      void plugin.savePluginState();
      return;
    }

    if (!lastIds.length && outputs.length > 0) {
      plugin.settings.lastKnownReportIds = currentIds;
      void plugin.savePluginState();
      return;
    }

    const newIds = currentIds.filter((id) => !lastIds.includes(id));
    if (!newIds.length) {
      if (currentIds.length !== lastIds.length || currentIds.some((id, i) => id !== lastIds[i])) {
        plugin.settings.lastKnownReportIds = currentIds;
        void plugin.savePluginState();
      }
      return;
    }

    plugin.settings.lastKnownReportIds = currentIds;
    void plugin.savePluginState();
  }


async function refreshShellSummaryCommand(plugin) {
    await plugin.runPluginCommand(plugin.t("Refresh Furnace Shell"), ["shell-status"], {
      refreshAfter: false,
      updateSummaryFromPayload: true,
      notice: false,
    });
  }


module.exports = { handleVaultChange, updateStatusBar, loadShellSummaryFromDisk, refreshShellSummarySilently, processShellSummaryUpdates, refreshShellSummaryCommand };
