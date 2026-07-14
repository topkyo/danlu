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

    new Setting(containerEl)
      .setName(t("Show advanced commands"))
      .setDesc(t("Register diagnostics, history, Review Center, and Execution Center commands in the command palette. Reload Obsidian after changing this toggle."))
      .addToggle((toggle) =>
        toggle.setValue(Boolean(this.plugin.settings.showAdvancedCommands)).onChange(async (value) => {
          this.plugin.settings.showAdvancedCommands = Boolean(value);
          await this.plugin.savePluginState();
          new Notice(this.plugin.t("Advanced command visibility refreshes after reloading Obsidian."));
        })
      );

    // ── Furnace Connection ──────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("Furnace Connection") });
    containerEl.createEl("p", {
      text: t("Full runtime is Desktop-only. iPad/iOS Obsidian can only be a future companion; it cannot run the local launcher, Python CLI, or full ingest/review flow."),
      cls: "setting-item-description",
    });

    new Setting(containerEl)
      .setName(t("Aiwiki launcher"))
      .setDesc(t("Vault-local or absolute launcher path. This vault may point at an external runtime root."))
      .addText((text) =>
        text
          .setPlaceholder("scripts/aiwiki-launcher.sh")
          .setValue(this.plugin.settings.launcherPath)
          .onChange(async (value) => {
            this.plugin.settings.launcherPath = String(value || "").trim() || DEFAULT_SETTINGS.launcherPath;
            await this.plugin.savePluginState();
            this.plugin.refreshRepoState();
          })
      );

    new Setting(containerEl)
      .setName(t("Runtime client mode"))
      .setDesc(t("Desktop launcher runs the local aiwiki runtime. Vault queue only writes .aiwiki/queue requests for desktop drain; it does not execute commands."))
      .addDropdown((dropdown) =>
        dropdown
          .addOption("desktop-launcher", t("Desktop launcher"))
          .addOption("vault-queue", t("Vault queue companion"))
          .setValue(normalizeRuntimeClientMode(this.plugin.settings.runtimeClientMode))
          .onChange(async (value) => {
            this.plugin.settings.runtimeClientMode = normalizeRuntimeClientMode(value);
            await this.plugin.savePluginState();
            this.plugin.refreshOpenViews();
          })
      );

    new Setting(containerEl)
      .setName(t("Recent runs limit"))
      .setDesc(t("How many plugin-triggered runs to keep in the Product Shell."))
      .addText((text) =>
        text.setValue(String(this.plugin.settings.recentRunsLimit)).onChange(async (value) => {
          const parsed = Number.parseInt(value, 10);
          this.plugin.settings.recentRunsLimit = Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SETTINGS.recentRunsLimit;
          this.plugin.trimRecentRuns();
          await this.plugin.savePluginState();
          this.plugin.refreshOpenViews();
        })
      );

    // ── LLM Configuration ──────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("LLM Configuration") });
    const selectedProfile = llmProviderProfile(this.plugin.settings.llmBackend);

    new Setting(containerEl)
      .setName(t("LLM backend"))
      .setDesc(t("Select the LLM provider used by run-compile / run-ask / run-nightly. Common providers are listed first; advanced entries are for local CLI sessions or custom OpenAI-compatible endpoints."))
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
        .addText((text) =>
          text
            .setPlaceholder(selectedProfile.defaultBaseUrl || "")
            .setValue(this.plugin.settings[selectedProfile.baseUrlSetting] || "")
            .onChange(async (value) => {
              this.plugin.settings[selectedProfile.baseUrlSetting] = String(value || "").trim();
              await this.plugin.savePluginState();
            })
        );
    }

    if (selectedProfile.cliHint) {
      new Setting(containerEl)
        .setName(t("CLI session"))
        .setDesc(t("This backend uses a local CLI login/session. API key fields are not used."));
      containerEl.createEl("p", {
        text: selectedProfile.cliHint,
        cls: "setting-item-description",
      });
    }

    // ── 通知（webhook） ──────────────────────────────
    // ── Notifications ────────────────────────────────
    containerEl.createEl("h3", { cls: "furnace-settings-section", text: t("Notifications") });
    containerEl.createEl("p", {
      text: t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports."),
      cls: "setting-item-description",
    });

    new Setting(containerEl)
      .setName(t("Feishu webhook URL"))
      .setDesc(t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports."))
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

    new Setting(containerEl)
      .setName(t("WeCom webhook URL"))
      .setDesc(t("Webhook settings are stored only in local plugin data. Failures are not retried. Notifications are only for new reports."))
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

    const updateEnabledChannel = async (channel, enabled) => {
      const channels = new Set(normalizeEnabledChannels(this.plugin.settings.enabledChannels));
      if (enabled) {
        channels.add(channel);
      } else {
        channels.delete(channel);
      }
      this.plugin.settings.enabledChannels = normalizeEnabledChannels(Array.from(channels));
      await this.plugin.savePluginState();
    };

    new Setting(containerEl)
      .setName(t("Enable Feishu"))
      .addToggle((toggle) =>
        toggle.setValue(normalizeEnabledChannels(this.plugin.settings.enabledChannels).includes("feishu")).onChange(async (value) => {
          await updateEnabledChannel("feishu", Boolean(value));
        })
      );

    new Setting(containerEl)
      .setName(t("Enable WeCom"))
      .addToggle((toggle) =>
        toggle.setValue(normalizeEnabledChannels(this.plugin.settings.enabledChannels).includes("wecom")).onChange(async (value) => {
          await updateEnabledChannel("wecom", Boolean(value));
        })
      );
  }
}
