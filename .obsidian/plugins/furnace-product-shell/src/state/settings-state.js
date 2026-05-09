// Extracted from plugin.js

async function loadPluginState(plugin) {
    const data = (await plugin.loadData()) || {};
    const rawSettings = data.settings && typeof data.settings === "object" ? data.settings : {};
    plugin.rawPluginData = data;
    plugin.settings = Object.assign({}, DEFAULT_SETTINGS, rawSettings);
    const legacyLlmSettingsMigrated = dropLegacyLlmSettings(plugin.settings);
    plugin.settings.locale = normalizeLocale(plugin.settings.locale);
    const migratedFeishuWebhookUrl = String(plugin.settings.feishuWebhookUrl || plugin.settings.feishu_webhook_url || "").trim();
    const feishuWebhookUrlMigrated = plugin.settings.feishuWebhookUrl !== migratedFeishuWebhookUrl;
    plugin.settings.feishuWebhookUrl = migratedFeishuWebhookUrl;
    const migratedWecomWebhookUrl = String(plugin.settings.wecomWebhookUrl || plugin.settings.wecom_webhook_url || "").trim();
    const wecomWebhookUrlMigrated = plugin.settings.wecomWebhookUrl !== migratedWecomWebhookUrl;
    plugin.settings.wecomWebhookUrl = migratedWecomWebhookUrl;
    const rawEnabledChannels = Array.isArray(rawSettings.enabledChannels)
      ? rawSettings.enabledChannels
      : rawSettings.enabled_channels;
    const migratedEnabledChannels = normalizeEnabledChannels(rawEnabledChannels);
    const enabledChannelsMigrated = JSON.stringify(plugin.settings.enabledChannels || []) !== JSON.stringify(migratedEnabledChannels);
    plugin.settings.enabledChannels = migratedEnabledChannels;
    const migratedLastViewedTimestamp = normalizeLastViewedTimestamp(plugin.settings.lastViewedTimestamp);
    const lastViewedTimestampMigrated = plugin.settings.lastViewedTimestamp !== migratedLastViewedTimestamp;
    plugin.settings.lastViewedTimestamp = migratedLastViewedTimestamp;
    const recentRuns = Array.isArray(data.recentRuns)
      ? data.recentRuns
        .filter((record) => record && typeof record === "object")
        .map((record) => {
          const rewriteProposalObjects = plugin.normalizeRewriteProposalObjects(record.rewriteProposalObjects || record.updatedRewriteProposals || []);
          const rewriteRecoveryActions = plugin.normalizeRewriteRecoveryActions(record.rewriteRecoveryActions || []);
          const rewriteProposalPaths = normalizeRelativePathList(
            record.rewriteProposalPaths || plugin.rewriteProposalPathsFromObjects(rewriteProposalObjects)
          );
          const rewriteProposalSlugs = normalizeRelativePathList(
            record.rewriteProposalSlugs || plugin.rewriteProposalSlugsFromObjects(rewriteProposalObjects)
          );
          return {
            ...record,
            argv: Array.isArray(record.argv) ? record.argv.map((value) => String(value || "")) : [],
            command: String(record.command || (Array.isArray(record.argv) && record.argv.length ? record.argv[0] : "")),
            protocol: String(record.protocol || ""),
            backend: String(record.backend || ""),
            backendRequested: String(record.backendRequested || ""),
            backendEffective: String(record.backendEffective || ""),
            model: String(record.model || ""),
            modelSelected: String(record.modelSelected || ""),
            modelFinal: String(record.modelFinal || ""),
            codexReasoningEffort: String(record.codexReasoningEffort || ""),
            promptProfile: String(record.promptProfile || ""),
            retryPromptProfile: String(record.retryPromptProfile || ""),
            fallbackStage: String(record.fallbackStage || ""),
            fallbackReason: String(record.fallbackReason || ""),
            contractValidated: Boolean(record.contractValidated),
            rewriteProposalObjects,
            rewriteRecoveryActions,
            rewriteProposalPaths,
            rewriteProposalSlugs,
            fallbackFrom: String(record.fallbackFrom || ""),
            fallbackCommand: String(record.fallbackCommand || ""),
            fallbackUsed: Boolean(record.fallbackUsed),
            deliveryMode: String(record.deliveryMode || ""),
            logPath: String(record.logPath || ""),
            stdoutRaw: trimDiagnosticText(record.stdoutRaw || ""),
            stderrRaw: trimDiagnosticText(record.stderrRaw || ""),
            exitCode: record.exitCode === 0 || Number.isFinite(Number(record.exitCode || NaN))
              ? Number(record.exitCode)
              : "",
            timeline: Array.isArray(record.timeline)
              ? record.timeline
                .filter((event) => event && typeof event === "object")
                .map((event) => ({
                  stage: String(event.stage || ""),
                  at: String(event.at || ""),
                  summary: String(event.summary || ""),
                  status: String(event.status || ""),
                }))
              : [],
          };
        })
      : [];
    plugin.pluginState = { recentRuns };
    plugin.trimRecentRuns();
    if (feishuWebhookUrlMigrated || wecomWebhookUrlMigrated || enabledChannelsMigrated || lastViewedTimestampMigrated || legacyLlmSettingsMigrated) {
      await plugin.savePluginState();
    }
  }


async function savePluginState(plugin) {
    await plugin.saveData({
      settings: plugin.settings,
      recentRuns: plugin.pluginState.recentRuns,
    });
  }


function trimRecentRuns(plugin) {
    const limit = Math.max(1, Number.parseInt(String(plugin.settings.recentRunsLimit || DEFAULT_SETTINGS.recentRunsLimit), 10) || DEFAULT_SETTINGS.recentRunsLimit);
    plugin.pluginState.recentRuns = plugin.pluginState.recentRuns.slice(0, limit);
  }


module.exports = { loadPluginState, savePluginState, trimRecentRuns };
