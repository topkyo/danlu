// Plugin settings tab.

class FurnaceProductShellSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    containerEl.empty();
    containerEl.createEl("h2", { text: t("炼丹炉 Product Shell") });

    // ── Language & Appearance ────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("Language & Appearance") });

    new Setting(containerEl)
      .setName(t("UI language"))
      .setDesc(t("Default display language for the Product Shell UI. Command palette labels refresh after reloading Obsidian."))
      .addDropdown((dropdown) =>
        dropdown
          .addOption("zh", t("Chinese"))
          .addOption("en", t("English"))
          .setValue(this.plugin.locale())
          .onChange(async (value) => {
            this.plugin.settings.locale = normalizeLocale(value);
            await this.plugin.savePluginState();
            this.plugin.updateStatusBar();
            this.plugin.refreshOpenViews();
            this.display();
            new Notice(this.plugin.t("command-palette labels refresh after reloading Obsidian."));
          })
      );

    // ── Furnace Connection ──────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("Furnace Connection") });
    containerEl.createEl("p", {
      text: t("Full runtime is Desktop-only. iPad/iOS Obsidian can only be a future companion; it cannot run the local Python CLI or the full ingest/review flow."),
      cls: "setting-item-description",
    });

    new Setting(containerEl)
      .setName(t("Runtime root"))
      .setDesc(t("Path to the aiwiki runtime repository (the checkout containing src/aiwiki). All runs delegate to that runtime."))
      .addText((text) =>
        text
          .setPlaceholder("/path/to/aiwiki")
          .setValue(this.plugin.settings.runtimeRoot)
          .onChange(async (value) => {
            this.plugin.settings.runtimeRoot = String(value || "").trim();
            await this.plugin.savePluginState();
            this.plugin.refreshRepoState();
          })
      );

    // ── LLM Configuration ──────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("LLM Configuration") });
    const selectedProfile = llmProviderProfile(this.plugin.settings.llmBackend);

    new Setting(containerEl)
      .setName(t("LLM backend"))
      .setDesc(t("Select the LLM provider used by compile / run-ask / run-nightly."))
      .addDropdown((dropdown) => {
        for (const profile of LLM_PROVIDER_PROFILES) {
          const prefix = profile.tier === "advanced" ? "Advanced · " : "";
          dropdown.addOption(profile.value, `${prefix}${profile.label}`);
        }
        return dropdown
          .setValue(selectedProfile.value)
          .onChange(async (value) => {
            const nextProfile = llmProviderProfile(value);
            this.plugin.settings.llmBackend = nextProfile.value;
            this.plugin.settings.llmModel = nextProfile.defaultModel || "";
            await this.plugin.savePluginState();
            this.display();
            new Notice(t("LLM settings saved. New runs will use the updated configuration."));
          });
      });

    if (llmProviderNeedsModel(selectedProfile)) {
      new Setting(containerEl)
        .setName(t("LLM model"))
        .setDesc(t("Model for the selected API provider. Empty uses that provider profile default when one exists."))
        .addText((text) =>
          text
            .setPlaceholder(selectedProfile.defaultModel || "provider/model")
            .setValue(this.plugin.settings.llmModel || "")
            .onChange(async (value) => {
              this.plugin.settings.llmModel = String(value || "").trim();
              await this.plugin.savePluginState();
            })
        );
    }

    if (selectedProfile.apiKeySetting) {
      new Setting(containerEl)
        .setName(t("API key"))
        .setDesc(t("Stored only in local Obsidian plugin data. New runs use the key saved here and ignore stale LLM environment variables."))
        .addText((text) => {
          text
            .setPlaceholder(selectedProfile.keyPlaceholder || "sk-...")
            .setValue(this.plugin.settings[selectedProfile.apiKeySetting] || "")
            .onChange(async (value) => {
              this.plugin.settings[selectedProfile.apiKeySetting] = String(value || "").trim();
              await this.plugin.savePluginState();
            });
          text.inputEl.type = "password";
          text.inputEl.autocomplete = "off";
        });
    }

    if (selectedProfile.baseUrlSetting) {
      new Setting(containerEl)
        .setName(t("Base URL"))
        .setDesc(t("Override the provider endpoint. Leave empty to use the provider profile default."))
        .addText((text) => {
          text
            .setPlaceholder(selectedProfile.defaultBaseUrl || "")
            .setValue(this.plugin.settings[selectedProfile.baseUrlSetting] || "")
            .onChange(async (value) => {
              this.plugin.settings[selectedProfile.baseUrlSetting] = String(value || "").trim();
              await this.plugin.savePluginState();
            });
          text.inputEl.autocomplete = "off";
        });
    }

    // ── Integrations (advanced) ────────────────────
    const integrationsDetails = containerEl.createEl("details", {
      cls: "furnace-settings-fold furnace-settings-fold-integrations",
    });
    integrationsDetails.createEl("summary", {
      cls: "furnace-settings-fold-summary",
      text: t("Integrations (advanced)"),
    });
    const integrationsBody = integrationsDetails.createDiv({ cls: "furnace-settings-fold-body" });
    integrationsBody.createEl("p", {
      text: t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports. Non-empty webhook URL enables that channel."),
      cls: "setting-item-description",
    });

    new Setting(integrationsBody)
      .setName(t("Feishu webhook URL"))
      .setDesc(t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports. Non-empty webhook URL enables that channel."))
      .addText((text) => {
        text
          .setPlaceholder("https://open.feishu.cn/open-apis/bot/v2/hook/...")
          .setValue(this.plugin.settings.feishuWebhookUrl || "")
          .onChange(async (value) => {
            this.plugin.settings.feishuWebhookUrl = String(value || "").trim();
            await this.plugin.savePluginState();
          });
        text.inputEl.autocomplete = "off";
      });

    new Setting(integrationsBody)
      .setName(t("WeCom webhook URL"))
      .setDesc(t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports. Non-empty webhook URL enables that channel."))
      .addText((text) => {
        text
          .setPlaceholder("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...")
          .setValue(this.plugin.settings.wecomWebhookUrl || "")
          .onChange(async (value) => {
            this.plugin.settings.wecomWebhookUrl = String(value || "").trim();
            await this.plugin.savePluginState();
          });
        text.inputEl.autocomplete = "off";
      });

    // ── Developer / diagnostics ─────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("Developer / diagnostics") });

    new Setting(containerEl)
      .setName(t("Developer diagnostics"))
      .setDesc(t("Shows the Advanced drawer, activity timeline, and run history on the home surface. Also registers the Refresh Furnace Shell command in the command palette. Reload Obsidian after changing this toggle."))
      .addToggle((toggle) =>
        toggle.setValue(Boolean(this.plugin.settings.showAdvancedCommands)).onChange(async (value) => {
          this.plugin.settings.showAdvancedCommands = Boolean(value);
          await this.plugin.savePluginState();
          new Notice(this.plugin.t("Developer diagnostics visibility refreshes after reloading Obsidian."));
        })
      );
  }
}
