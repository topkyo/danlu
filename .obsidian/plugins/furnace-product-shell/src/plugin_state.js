// Product Shell plugin settings and persisted state helpers.

async function loadProductShellPluginState(plugin) {
  const data = (await plugin.loadData()) || {};
  const rawSettings = data.settings && typeof data.settings === "object" ? data.settings : {};
  plugin.rawPluginData = data;
  plugin.settings = Object.assign({}, DEFAULT_SETTINGS, rawSettings);
  const legacyDefaultAskFormatMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "defaultAskFormat");
  delete plugin.settings.defaultAskFormat;
  const legacyLastViewedTimestampMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "lastViewedTimestamp");
  delete plugin.settings.lastViewedTimestamp;
  const legacyLastKnownReportIdsMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "lastKnownReportIds");
  delete plugin.settings.lastKnownReportIds;
  const legacyOnboardingShownMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "onboardingShown");
  delete plugin.settings.onboardingShown;
  const selectedProfile = llmProviderProfile(plugin.settings.llmBackend);
  const llmBackendMigrated = plugin.settings.llmBackend !== selectedProfile.value;
  plugin.settings.llmBackend = selectedProfile.value;
  const legacyRuntimeClientModeMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "runtimeClientMode");
  delete plugin.settings.runtimeClientMode;
  const legacyShowHtmlShortcutsMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "showHtmlShortcuts");
  delete plugin.settings.showHtmlShortcuts;
  const legacyDefaultAskModeMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "defaultAskMode");
  delete plugin.settings.defaultAskMode;
  const legacyRecentRunsLimitMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "recentRunsLimit");
  delete plugin.settings.recentRunsLimit;
  const rawAdvancedSectionsExpanded = plugin.settings.advancedSectionsExpanded && typeof plugin.settings.advancedSectionsExpanded === "object"
    ? plugin.settings.advancedSectionsExpanded
    : {};
  const migratedAdvancedSectionsExpanded = {
    status: Boolean(rawAdvancedSectionsExpanded.status),
    history: Boolean(rawAdvancedSectionsExpanded.history),
  };
  const advancedSectionsExpandedMigrated = JSON.stringify(plugin.settings.advancedSectionsExpanded || {}) !== JSON.stringify(migratedAdvancedSectionsExpanded);
  plugin.settings.advancedSectionsExpanded = migratedAdvancedSectionsExpanded;
  const legacyLlmSettingsMigrated = dropLegacyLlmSettings(plugin.settings);
  plugin.settings.locale = normalizeLocale(plugin.settings.locale);
  const migratedFeishuWebhookUrl = String(plugin.settings.feishuWebhookUrl || plugin.settings.feishu_webhook_url || "").trim();
  const feishuWebhookUrlMigrated = plugin.settings.feishuWebhookUrl !== migratedFeishuWebhookUrl;
  plugin.settings.feishuWebhookUrl = migratedFeishuWebhookUrl;
  const migratedWecomWebhookUrl = String(plugin.settings.wecomWebhookUrl || plugin.settings.wecom_webhook_url || "").trim();
  const wecomWebhookUrlMigrated = plugin.settings.wecomWebhookUrl !== migratedWecomWebhookUrl;
  plugin.settings.wecomWebhookUrl = migratedWecomWebhookUrl;
  const legacyEnabledChannelsMigrated =
    Object.prototype.hasOwnProperty.call(plugin.settings, "enabledChannels")
    || Object.prototype.hasOwnProperty.call(plugin.settings, "enabled_channels")
    || Object.prototype.hasOwnProperty.call(rawSettings, "enabledChannels")
    || Object.prototype.hasOwnProperty.call(rawSettings, "enabled_channels");
  delete plugin.settings.enabledChannels;
  delete plugin.settings.enabled_channels;
  delete plugin.settings.feishu_webhook_url;
  delete plugin.settings.wecom_webhook_url;
  plugin.pendingSubmissions = plugin.hydratePendingSubmissions(plugin.settings.persistedPendingSubmissions);
  const recentRuns = normalizeProductShellRecentRuns(data.recentRuns);
  const llmHealth = data.llmHealth && typeof data.llmHealth === "object" ? data.llmHealth : null;
  plugin.pluginState = { recentRuns, llmHealth };
  plugin.trimRecentRuns();
  if (
    feishuWebhookUrlMigrated
    || wecomWebhookUrlMigrated
    || legacyEnabledChannelsMigrated
    || legacyDefaultAskFormatMigrated
    || legacyLastViewedTimestampMigrated
    || legacyLastKnownReportIdsMigrated
    || legacyOnboardingShownMigrated
    || legacyLlmSettingsMigrated
    || llmBackendMigrated
    || legacyRuntimeClientModeMigrated
    || legacyShowHtmlShortcutsMigrated
    || legacyDefaultAskModeMigrated
    || legacyRecentRunsLimitMigrated
    || advancedSectionsExpandedMigrated
  ) {
    await plugin.savePluginState();
  }
}

async function saveProductShellPluginState(plugin) {
  await plugin.saveData({
    settings: Object.assign({}, plugin.settings, {
      persistedPendingSubmissions: plugin.serializePendingSubmissions(),
    }),
    recentRuns: plugin.pluginState.recentRuns,
    llmHealth: plugin.pluginState && plugin.pluginState.llmHealth ? plugin.pluginState.llmHealth : null,
  });
}

function getProductShellAdvancedSectionExpanded(plugin, key) {
  const state = plugin.settings && plugin.settings.advancedSectionsExpanded;
  if (!state || typeof state !== "object") return false;
  return Boolean(state[key]);
}

async function setProductShellAdvancedSectionExpanded(plugin, key, value) {
  if (key !== "status" && key !== "history") {
    return;
  }
  const current = plugin.settings && plugin.settings.advancedSectionsExpanded;
  const next = {
    status: Boolean(current && typeof current === "object" && current.status),
    history: Boolean(current && typeof current === "object" && current.history),
  };
  next[key] = Boolean(value);
  plugin.settings.advancedSectionsExpanded = next;
  try {
    await plugin.savePluginState();
  } catch (error) {
    // Persisting drawer state must not break UI interaction.
  }
}
