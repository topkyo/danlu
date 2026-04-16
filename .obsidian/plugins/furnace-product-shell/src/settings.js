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
    containerEl.createEl("h2", { text: t("Furnace Product Shell") });

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
      .setName(t("Default ask mode"))
      .setDesc(t("Choose whether Ask defaults to deterministic `ask` or LLM-backed `run-ask`."))
      .addDropdown((dropdown) =>
        dropdown
          .addOption("ask", "ask")
          .addOption("run-ask", "run-ask")
          .setValue(this.plugin.settings.defaultAskMode)
          .onChange(async (value) => {
            this.plugin.settings.defaultAskMode = value;
            await this.plugin.savePluginState();
          })
      );

    new Setting(containerEl)
      .setName(t("Default ask format"))
      .setDesc(t("Default output format for the Ask modal."))
      .addDropdown((dropdown) =>
        dropdown
          .addOption("report", "report")
          .addOption("slides", "slides")
          .addOption("figure", "figure")
          .setValue(this.plugin.settings.defaultAskFormat)
          .onChange(async (value) => {
            this.plugin.settings.defaultAskFormat = value;
            await this.plugin.savePluginState();
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

    new Setting(containerEl)
      .setName(t("Show advanced commands"))
      .setDesc(t("Register review, execution, protocol, and legacy panel commands in the command palette. Reload Obsidian after changing this toggle."))
      .addToggle((toggle) =>
        toggle.setValue(Boolean(this.plugin.settings.showAdvancedCommands)).onChange(async (value) => {
          this.plugin.settings.showAdvancedCommands = Boolean(value);
          await this.plugin.savePluginState();
          new Notice(this.plugin.t("Advanced command visibility refreshes after reloading Obsidian."));
        })
      );

    new Setting(containerEl)
      .setName(t("Show HTML shortcuts"))
      .setDesc(t("Whether advanced panels should show HTML shortcuts when the summary exposes them."))
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.showHtmlShortcuts).onChange(async (value) => {
          this.plugin.settings.showHtmlShortcuts = Boolean(value);
          await this.plugin.savePluginState();
          this.plugin.refreshOpenViews();
        })
      );
  }
}
