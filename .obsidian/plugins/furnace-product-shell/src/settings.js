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

    // ── LLM configuration ──────────────────────────────────
    containerEl.createEl("h3", { text: t("LLM backend") });
    const selectedBackend = String(this.plugin.settings.llmBackend || "").trim();

    new Setting(containerEl)
      .setName(t("LLM backend"))
      .setDesc(t("Select the explicit LLM backend used by run-compile / run-ask / run-nightly. Empty = unconfigured."))
      .addDropdown((dropdown) =>
        dropdown
          .addOption("", t("unconfigured"))
          .addOption("codex-cli", "codex-cli")
          .addOption("nvidia-nim-api", "nvidia-nim-api")
          .addOption("copilot-cli", "copilot-cli")
          .addOption("claude-cli", "claude-cli")
          .setValue(this.plugin.settings.llmBackend || "")
          .onChange(async (value) => {
            this.plugin.settings.llmBackend = value;
            await this.plugin.savePluginState();
            this.display();
            new Notice(t("LLM settings saved. New runs will use the updated configuration."));
          })
      );

    new Setting(containerEl)
      .setName(t("LLM model"))
      .setDesc(t("Override the model name (e.g. gpt-5.4, claude-sonnet-4.5). Empty = selected backend default strategy (`codex-cli`: `gpt-5.4`; `nvidia-nim-api`: `moonshotai/kimi-k2.5 -> z-ai/glm-5.1 -> minimaxai/minimax-m2.7`)."))
      .addText((text) =>
        text
          .setPlaceholder("gpt-5.4 / z-ai/glm-5.1 / claude-sonnet-4.5")
          .setValue(this.plugin.settings.llmModel || "")
          .onChange(async (value) => {
            this.plugin.settings.llmModel = String(value || "").trim();
            await this.plugin.savePluginState();
          })
      );

    if (selectedBackend === "nvidia-nim-api") {
      new Setting(containerEl)
        .setName(t("NVIDIA NIM API key"))
        .setDesc(t("Optional key for nvidia-nim-api. Stored locally in plugin data. Empty = use AIWIKI_NVIDIA_NIM_API_KEY / NVIDIA_NIM_API_KEY."))
        .addText((text) => {
          text
            .setPlaceholder("nvapi-...")
            .setValue(this.plugin.settings.llmNvidiaNimApiKey || "")
            .onChange(async (value) => {
              this.plugin.settings.llmNvidiaNimApiKey = String(value || "").trim();
              await this.plugin.savePluginState();
            });
          text.inputEl.type = "password";
          text.inputEl.autocomplete = "off";
        });

      new Setting(containerEl)
        .setName(t("NVIDIA NIM base URL"))
        .setDesc(t("Override the NVIDIA NIM endpoint. Empty = https://integrate.api.nvidia.com/v1."))
        .addText((text) =>
          text
            .setPlaceholder("https://integrate.api.nvidia.com/v1")
            .setValue(this.plugin.settings.llmNvidiaNimBaseUrl || "")
            .onChange(async (value) => {
              this.plugin.settings.llmNvidiaNimBaseUrl = String(value || "").trim();
              await this.plugin.savePluginState();
            })
        );
    }
  }
}
