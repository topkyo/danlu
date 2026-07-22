function createProductShellPluginRunRecord(plugin, label, args) {
  const record = createProductShellRunRecord({
    label,
    args,
    llm: plugin.currentLlmSelection(),
    protocol: plugin.getActiveProtocol(),
  });
  plugin.pluginState.recentRuns.unshift(record);
  plugin.trimRecentRuns();
  plugin.persistRunLog(record);
  plugin.updateStatusBar();
  plugin.refreshOpenViews();
  void plugin.savePluginState();
  return record;
}

function updateProductShellPluginRunRecord(plugin, record, updates) {
  Object.assign(record, updates);
  plugin.trimRecentRuns();
  plugin.persistRunLog(record);
  plugin.updateStatusBar();
  plugin.refreshOpenViews();
  void plugin.savePluginState();
}

function latestProductShellPluginRun(plugin) {
  return plugin.pluginState.recentRuns.length ? plugin.pluginState.recentRuns[0] : null;
}

async function rerunProductShellPluginRecord(plugin, record) {
  const argv = record && Array.isArray(record.argv) ? record.argv.map((value) => String(value || "")) : [];
  if (!argv.length) {
    new Notice(plugin.t("Cannot re-run this entry because argv was not recorded."));
    return null;
  }
  return await plugin.runPluginCommand(record.label || record.args || plugin.t("command"), argv, { refreshAfter: true });
}

async function runProductShellPluginCommand(plugin, label, args, options = {}) {
  const record = plugin.createRunRecord(label, args);
  appendRunEvent(record, "Executing", args.join(" "), "running");
  plugin.updateRunRecord(record, {});
  try {
    const result = await plugin.executeRuntimeCommand(args);
    const runContext = buildProductShellRunResultContext(result);
    if (options.updateSummaryFromPayload && result.payload && result.payload.kind === "product-shell-summary") {
      plugin.shellSummary = result.payload;
      plugin.processShellSummaryUpdates(plugin.shellSummary);
      plugin.updateStatusBar();
      plugin.refreshOpenViews();
    } else if (options.refreshAfter !== false) {
      await plugin.refreshShellSummarySilently();
    }
    const llm = plugin.currentLlmSelection();
    const completedState = buildProductShellCompletedRunState({
      record,
      result,
      llm,
      runContext,
      rewriteProposalSummary: plugin.rewriteProposalSummary({ rewriteProposalPaths: runContext.rewriteProposalPaths }),
      fallbackSummary: result.payload && (result.payload.primary_error || result.payload.fallback_reason)
        || plugin.t("LLM timed out or failed before producing an answer."),
      successSummary: runContext.primaryPath || runContext.receiptPath || plugin.t("Command completed successfully."),
      degradedNotice: plugin.t("LLM timed out or failed. Open the failure notice for details, then retry or switch model."),
      successNotice: `${plugin.t(label)} ${plugin.t("completed")}.`,
    });
    completedState.events.forEach((event) => appendRunEvent(record, event.stage, event.summary, event.status));
    plugin.updateRunRecord(record, completedState.updates);
    if (completedState.llmHealthOverrides) {
      plugin.recordLlmHealthFromRun(record, completedState.llmHealthOverrides);
    }
    plugin.persistRunLog(record, { stdoutRaw: result.stdout, stderrRaw: result.stderr });
    if (options.notice !== false) {
      new Notice(completedState.noticeMessage);
    }
    return result.payload;
  } catch (error) {
    const failedState = buildProductShellFailedRunState({
      record,
      error,
      noticeMessage: `${plugin.t(label)} ${plugin.t("failed: {message}", { message: truncateText(error.message || plugin.t("unknown error"), 120) })}`,
    });
    failedState.events.forEach((event) => appendRunEvent(record, event.stage, event.summary, event.status));
    plugin.updateRunRecord(record, failedState.updates);
    if (failedState.llmHealthOverrides) {
      plugin.recordLlmHealthFromRun(record, failedState.llmHealthOverrides);
    }
    plugin.persistRunLog(record, failedState.logDetails);
    new Notice(failedState.noticeMessage);
    throw error;
  }
}

async function refreshProductShellSummarySilently(plugin) {
  try {
    const result = await plugin.executeRuntimeCommand(["shell-status"]);
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

function processProductShellSummaryUpdates(plugin, summary) {
  plugin.reconcilePendingSubmissions(summary);
  const update = knownReportIdsUpdateFromSummary(summary, plugin.settings.lastKnownReportIds);
  if (update.shouldSave) {
    plugin.settings.lastKnownReportIds = update.ids;
    void plugin.savePluginState();
  }
}

async function refreshProductShellSummaryCommand(plugin) {
  try {
    await plugin.runPluginCommand(plugin.t("Refresh Furnace Shell"), ["shell-status"], {
      refreshAfter: false,
      updateSummaryFromPayload: true,
      notice: false,
    });
  } catch (error) {
    // Falling back to the disk summary still advances pending reconciliation.
  }
  await plugin.loadShellSummaryFromDisk();
}
