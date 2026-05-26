// Product Shell plugin settings and persisted state helpers.

async function loadProductShellPluginState(plugin) {
  const data = (await plugin.loadData()) || {};
  const rawSettings = data.settings && typeof data.settings === "object" ? data.settings : {};
  plugin.rawPluginData = data;
  plugin.settings = Object.assign({}, DEFAULT_SETTINGS, rawSettings);
  if (plugin.settings.defaultAskFormat === "report") {
    plugin.settings.defaultAskFormat = "note";
  }
  const legacyShowHtmlShortcutsMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "showHtmlShortcuts");
  delete plugin.settings.showHtmlShortcuts;
  const legacyDefaultAskModeMigrated = Object.prototype.hasOwnProperty.call(plugin.settings, "defaultAskMode");
  delete plugin.settings.defaultAskMode;
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
  const rawEnabledChannels = Array.isArray(rawSettings.enabledChannels)
    ? rawSettings.enabledChannels
    : rawSettings.enabled_channels;
  const migratedEnabledChannels = normalizeEnabledChannels(rawEnabledChannels);
  const enabledChannelsMigrated = JSON.stringify(plugin.settings.enabledChannels || []) !== JSON.stringify(migratedEnabledChannels);
  plugin.settings.enabledChannels = migratedEnabledChannels;
  const migratedLastViewedTimestamp = normalizeLastViewedTimestamp(plugin.settings.lastViewedTimestamp);
  const lastViewedTimestampMigrated = plugin.settings.lastViewedTimestamp !== migratedLastViewedTimestamp;
  plugin.settings.lastViewedTimestamp = migratedLastViewedTimestamp;
  plugin.pendingSubmissions = plugin.hydratePendingSubmissions(plugin.settings.persistedPendingSubmissions);
  const recentRuns = normalizeProductShellRecentRuns(data.recentRuns);
  plugin.pluginState = { recentRuns };
  plugin.trimRecentRuns();
  const defaultAskFormatMigrated = rawSettings.defaultAskFormat === "report";
  if (
    feishuWebhookUrlMigrated
    || wecomWebhookUrlMigrated
    || enabledChannelsMigrated
    || lastViewedTimestampMigrated
    || legacyLlmSettingsMigrated
    || defaultAskFormatMigrated
    || legacyShowHtmlShortcutsMigrated
    || legacyDefaultAskModeMigrated
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
