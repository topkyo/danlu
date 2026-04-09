const { Plugin, PluginSettingTab, Setting, ItemView, Modal, Notice } = require("obsidian");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const PLUGIN_ID = "furnace-product-shell";
const VIEW_TYPE_FURNACE_CENTER = "furnace-product-shell-furnace-center";
const VIEW_TYPE_RECENT_RUNS = "furnace-product-shell-recent-runs";
const VIEW_TYPE_REVIEW_CENTER = "furnace-product-shell-review-center";
const VIEW_TYPE_EXECUTION_CENTER = "furnace-product-shell-execution-center";
const SHELL_SUMMARY_PATH = "output/control/shell-summary.json";
const DEFAULT_PROTOCOLS = ["general", "investing", "research", "product", "ops"];
const DEFAULT_SETTINGS = {
  launcherPath: "scripts/aiwiki-launcher.sh",
  defaultAskMode: "ask",
  defaultAskFormat: "report",
  recentRunsLimit: 8,
  showHtmlShortcuts: true,
};

function truncateText(value, limit = 240) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}…`;
}

function readJsonText(rawText) {
  const text = String(rawText || "").trim();
  if (!text) {
    return null;
  }
  return JSON.parse(text);
}

class AskCommandModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Ask 炼丹炉" });

    const questionSetting = new Setting(contentEl).setName("Question");
    const questionInput = questionSetting.controlEl.createEl("textarea");
    questionInput.rows = 5;
    questionInput.placeholder = "Enter the research question...";
    questionInput.addClass("furnace-shell-code");

    const formatSetting = new Setting(contentEl).setName("Format");
    const formatSelect = formatSetting.controlEl.createEl("select");
    ["report", "slides", "figure"].forEach((item) => {
      const option = formatSelect.createEl("option", { text: item, value: item });
      option.value = item;
    });
    formatSelect.value = this.plugin.settings.defaultAskFormat;

    const modeSetting = new Setting(contentEl).setName("Mode");
    const modeSelect = modeSetting.controlEl.createEl("select");
    [
      ["ask", "ask"],
      ["run-ask", "run-ask"],
    ].forEach(([value, label]) => {
      const option = modeSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    modeSelect.value = this.plugin.settings.defaultAskMode;

    const protocolSetting = new Setting(contentEl).setName("Protocol");
    const protocolSelect = protocolSetting.controlEl.createEl("select");
    protocolSelect.createEl("option", { text: "current protocol", value: "" });
    this.plugin.getAvailableProtocols().forEach((protocol) => {
      const option = protocolSelect.createEl("option", { text: protocol, value: protocol });
      option.value = protocol;
    });

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText("Run").setCta().onClick(async () => {
        const question = String(questionInput.value || "").trim();
        if (!question) {
          new Notice("Question 不能为空。");
          return;
        }
        const format = String(formatSelect.value || "report");
        const mode = String(modeSelect.value || "ask");
        const protocol = String(protocolSelect.value || "").trim();
        this.close();
        this.plugin.runUiAction(
          () =>
            this.plugin.runAskCommand({
              question,
              format,
              mode,
              protocol,
            }),
          "Ask modal"
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );

    questionInput.focus();
  }
}

class ProtocolCommandModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Set Protocol" });

    const setting = new Setting(contentEl).setName("Protocol");
    const select = setting.controlEl.createEl("select");
    this.plugin.getAvailableProtocols().forEach((protocol) => {
      const option = select.createEl("option", { text: protocol, value: protocol });
      option.value = protocol;
    });
    select.value = this.plugin.getActiveProtocol();

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText("Apply").setCta().onClick(async () => {
        const protocol = String(select.value || "").trim();
        if (!protocol) {
          new Notice("请选择 protocol。");
          return;
        }
        this.close();
        this.plugin.runUiAction(() => this.plugin.runProtocolSetCommand(protocol), "Set protocol modal");
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );

    select.focus();
  }
}

class FurnaceCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_FURNACE_CENTER;
  }

  getDisplayText() {
    return "Furnace Center";
  }

  getIcon() {
    return "flask-conical";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderFurnaceCenter(this.contentEl);
  }
}

class RecentRunsView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_RECENT_RUNS;
  }

  getDisplayText() {
    return "Recent Runs";
  }

  getIcon() {
    return "history";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderRecentRuns(this.contentEl);
  }
}

class StructuredCommandModal extends Modal {
  constructor(app, plugin, spec) {
    super(app);
    this.plugin = plugin;
    this.spec = spec;
    this.controls = {};
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: this.spec.title || "Run command" });
    if (this.spec.description) {
      contentEl.createDiv({ cls: "furnace-shell-meta", text: this.spec.description });
    }

    (this.spec.fields || []).forEach((field) => {
      const setting = new Setting(contentEl).setName(field.label);
      if (field.description) {
        setting.setDesc(field.description);
      }
      const initialValue = typeof field.initialValue === "function" ? field.initialValue() : field.initialValue;
      const normalized = field.kind === "toggle" ? Boolean(initialValue) : String(initialValue || "");
      let control = null;

      if (field.kind === "textarea") {
        control = setting.controlEl.createEl("textarea");
        control.rows = field.rows || 4;
        control.value = normalized;
      } else if (field.kind === "select") {
        control = setting.controlEl.createEl("select");
        (field.options || []).forEach((optionValue) => {
          const option = Array.isArray(optionValue)
            ? { value: optionValue[0], label: optionValue[1] }
            : { value: optionValue.value, label: optionValue.label };
          const element = control.createEl("option", { text: option.label, value: option.value });
          element.value = option.value;
        });
        control.value = normalized;
      } else if (field.kind === "toggle") {
        control = setting.controlEl.createEl("input", { type: "checkbox" });
        control.checked = Boolean(initialValue);
      } else {
        control = setting.controlEl.createEl("input", { type: "text" });
        control.value = normalized;
      }

      if (field.placeholder && "placeholder" in control) {
        control.placeholder = field.placeholder;
      }
      if (field.kind !== "toggle") {
        control.addClass("furnace-shell-code");
      }
      this.controls[field.key] = control;
    });

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(this.spec.submitLabel || "Run").setCta().onClick(() => {
        const values = {};
        for (const field of this.spec.fields || []) {
          const control = this.controls[field.key];
          const value = field.kind === "toggle" ? Boolean(control.checked) : String(control.value || "").trim();
          if (field.required && !value) {
            new Notice(`${field.label} 不能为空。`);
            return;
          }
          values[field.key] = value;
        }
        this.close();
        this.plugin.runUiAction(() => this.spec.onSubmit(values), this.spec.title || "command modal");
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );

    const firstField = this.spec.fields && this.spec.fields.length ? this.controls[this.spec.fields[0].key] : null;
    if (firstField && typeof firstField.focus === "function") {
      firstField.focus();
    }
  }
}

class ContextPickerModal extends Modal {
  constructor(app, plugin, spec) {
    super(app);
    this.plugin = plugin;
    this.spec = spec;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: this.spec.title || "Pick context" });
    if (this.spec.description) {
      contentEl.createDiv({ cls: "furnace-shell-meta", text: this.spec.description });
    }

    const options = Array.isArray(this.spec.options) ? this.spec.options : [];
    if (!options.length) {
      contentEl.createDiv({ cls: "furnace-shell-empty", text: "当前没有可用上下文。" });
      new Setting(contentEl).addButton((button) =>
        button.setButtonText("Close").onClick(() => {
          this.close();
        })
      );
      return;
    }

    const list = contentEl.createEl("ul", { cls: "furnace-shell-list" });
    options.forEach((option) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: option.label || option.value || "context" });
      if (option.description) {
        item.createDiv({ cls: "furnace-shell-meta", text: option.description });
      }
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const button = actions.createEl("button", { text: this.spec.submitLabel || "Use" });
      button.addEventListener("click", () => {
        this.close();
        this.plugin.runUiAction(() => this.spec.onSubmit(option), this.spec.title || "context picker");
      });
    });

    new Setting(contentEl).addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );
  }
}

class ReviewCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_REVIEW_CENTER;
  }

  getDisplayText() {
    return "Review Center";
  }

  getIcon() {
    return "clipboard-check";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderReviewCenter(this.contentEl);
  }
}

class ExecutionCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_EXECUTION_CENTER;
  }

  getDisplayText() {
    return "Execution Center";
  }

  getIcon() {
    return "play-circle";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderExecutionCenter(this.contentEl);
  }
}

class FurnaceProductShellSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Furnace Product Shell" });

    new Setting(containerEl)
      .setName("Aiwiki launcher")
      .setDesc("Repo-local launcher path, relative to the vault root by default.")
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
      .setName("Default ask mode")
      .setDesc("Choose whether Ask defaults to deterministic `ask` or LLM-backed `run-ask`.")
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
      .setName("Default ask format")
      .setDesc("Default output format for the Ask modal.")
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
      .setName("Recent runs limit")
      .setDesc("How many plugin-triggered runs to keep in the Product Shell.")
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
      .setName("Show HTML shortcuts")
      .setDesc("Whether Furnace Center should show HTML panel shortcuts when the summary exposes them.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.showHtmlShortcuts).onChange(async (value) => {
          this.plugin.settings.showHtmlShortcuts = Boolean(value);
          await this.plugin.savePluginState();
          this.plugin.refreshOpenViews();
        })
      );
  }
}

module.exports = class FurnaceProductShellPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
    this.pluginState = { recentRuns: [] };
    this.shellSummary = null;
    this.repoState = { valid: false, root: "", launcherPath: "", missingPaths: ["vault-root"] };
    this.openViews = new Set();
    this.statusBarItem = this.addStatusBarItem();

    await this.loadPluginState();
    this.refreshRepoState();

    this.registerView(VIEW_TYPE_FURNACE_CENTER, (leaf) => new FurnaceCenterView(leaf, this));
    this.registerView(VIEW_TYPE_RECENT_RUNS, (leaf) => new RecentRunsView(leaf, this));
    this.registerView(VIEW_TYPE_REVIEW_CENTER, (leaf) => new ReviewCenterView(leaf, this));
    this.registerView(VIEW_TYPE_EXECUTION_CENTER, (leaf) => new ExecutionCenterView(leaf, this));
    this.addSettingTab(new FurnaceProductShellSettingTab(this.app, this));

    this.addRibbonIcon("flask-conical", "Open Furnace Center", () => {
      this.runUiAction(() => this.openFurnaceCenterView(), "Open Furnace Center");
    });
    this.addRibbonIcon("refresh-ccw", "Refresh Furnace Shell", () => {
      this.runUiAction(() => this.refreshShellSummaryCommand(), "Refresh Furnace Shell");
    });

    this.addCommand({
      id: "open-furnace-center",
      name: "Open Furnace Center",
      callback: () => {
        this.runUiAction(() => this.openFurnaceCenterView(), "Open Furnace Center");
      },
    });
    this.addCommand({
      id: "open-recent-runs",
      name: "Open Recent Runs",
      callback: () => {
        this.runUiAction(() => this.openRecentRunsView(), "Open Recent Runs");
      },
    });
    this.addCommand({
      id: "open-review-center",
      name: "Open Review Center",
      callback: () => {
        this.runUiAction(() => this.openReviewCenterView(), "Open Review Center");
      },
    });
    this.addCommand({
      id: "open-execution-center",
      name: "Open Execution Center",
      callback: () => {
        this.runUiAction(() => this.openExecutionCenterView(), "Open Execution Center");
      },
    });
    this.addCommand({
      id: "refresh-furnace-shell",
      name: "Refresh Furnace Shell",
      callback: () => {
        this.runUiAction(() => this.refreshShellSummaryCommand(), "Refresh Furnace Shell");
      },
    });
    this.addCommand({
      id: "run-compile",
      name: "Compile",
      callback: () => {
        this.runUiAction(() => this.runCompileCommand(), "Compile");
      },
    });
    this.addCommand({
      id: "run-ask",
      name: "Ask",
      callback: () => {
        new AskCommandModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "run-nightly",
      name: "Nightly",
      callback: () => {
        this.runUiAction(() => this.runNightlyCommand(), "Nightly");
      },
    });
    this.addCommand({
      id: "set-protocol",
      name: "Set Protocol",
      callback: () => {
        new ProtocolCommandModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "file-back",
      name: "File Back",
      callback: () => {
        this.openFileBackModal();
      },
    });
    this.addCommand({
      id: "review-page",
      name: "Review Page",
      callback: () => {
        this.openReviewPageContextPicker();
      },
    });
    this.addCommand({
      id: "review-rewrite",
      name: "Review Rewrite",
      callback: () => {
        this.openReviewRewriteContextPicker();
      },
    });
    this.addCommand({
      id: "apply-rewrite",
      name: "Apply Rewrite",
      callback: () => {
        this.openApplyRewriteModal();
      },
    });
    this.addCommand({
      id: "retire-concept",
      name: "Retire Concept",
      callback: () => {
        this.openRetireConceptModal();
      },
    });
    this.addCommand({
      id: "reactivate-concept",
      name: "Reactivate Concept",
      callback: () => {
        this.openReactivateConceptModal();
      },
    });
    this.addCommand({
      id: "apply-archive",
      name: "Apply Archive",
      callback: () => {
        this.openApplyArchiveContextPicker();
      },
    });
    this.addCommand({
      id: "revert-archive",
      name: "Revert Archive",
      callback: () => {
        this.openRevertArchiveContextPicker();
      },
    });
    this.addCommand({
      id: "review-action",
      name: "Review Action",
      callback: () => {
        this.openReviewActionContextPicker();
      },
    });
    this.addCommand({
      id: "apply-action",
      name: "Apply Action",
      callback: () => {
        this.openApplyActionContextPicker();
      },
    });
    this.addCommand({
      id: "revert-action",
      name: "Revert Action",
      callback: () => {
        this.openRevertActionContextPicker();
      },
    });

    this.registerEvent(this.app.vault.on("modify", (file) => {
      void this.handleVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("create", (file) => {
      void this.handleVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("delete", (file) => {
      void this.handleVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => {
      void this.handleVaultChange(file.path || oldPath);
    }));

    await this.loadShellSummaryFromDisk();
    this.updateStatusBar();
  }

  async onunload() {
    this.openViews.clear();
  }

  registerOpenView(view) {
    this.openViews.add(view);
  }

  unregisterOpenView(view) {
    this.openViews.delete(view);
  }

  async loadPluginState() {
    const data = (await this.loadData()) || {};
    this.settings = Object.assign({}, DEFAULT_SETTINGS, data.settings || {});
    const recentRuns = Array.isArray(data.recentRuns) ? data.recentRuns : [];
    this.pluginState = { recentRuns };
    this.trimRecentRuns();
  }

  async savePluginState() {
    await this.saveData({
      settings: this.settings,
      recentRuns: this.pluginState.recentRuns,
    });
  }

  trimRecentRuns() {
    const limit = Math.max(1, Number.parseInt(String(this.settings.recentRunsLimit || DEFAULT_SETTINGS.recentRunsLimit), 10) || DEFAULT_SETTINGS.recentRunsLimit);
    this.pluginState.recentRuns = this.pluginState.recentRuns.slice(0, limit);
  }

  launcherIsExecutable(launcherPath) {
    if (!launcherPath || !fs.existsSync(launcherPath)) {
      return false;
    }
    try {
      fs.accessSync(launcherPath, fs.constants.X_OK);
      return true;
    } catch (error) {
      return false;
    }
  }

  refreshRepoState() {
    const adapter = this.app.vault && this.app.vault.adapter;
    const root = adapter && typeof adapter.basePath === "string" ? adapter.basePath : "";
    const launcherPath = this.resolveLauncherPath(root);
    const missingPaths = [];
    if (!root) {
      missingPaths.push("vault-root");
    } else {
      [
        "src/aiwiki/cli.py",
        "raw",
        "wiki",
        "schema",
      ].forEach((relativePath) => {
        if (!fs.existsSync(path.join(root, relativePath))) {
          missingPaths.push(relativePath);
        }
      });
      if (!this.launcherIsExecutable(launcherPath)) {
        missingPaths.push(this.settings.launcherPath);
      }
    }
    this.repoState = {
      valid: missingPaths.length === 0,
      root,
      launcherPath,
      missingPaths,
    };
    this.updateStatusBar();
    this.refreshOpenViews();
  }

  resolveLauncherPath(root) {
    const launcherPath = String(this.settings.launcherPath || DEFAULT_SETTINGS.launcherPath).trim();
    if (!root || !launcherPath) {
      return "";
    }
    if (path.isAbsolute(launcherPath)) {
      return launcherPath;
    }
    return path.join(root, launcherPath);
  }

  getActiveProtocol() {
    return String(this.shellSummary && this.shellSummary.active_protocol ? this.shellSummary.active_protocol : "general");
  }

  getAvailableProtocols() {
    const fromSummary = this.shellSummary && Array.isArray(this.shellSummary.available_protocols)
      ? this.shellSummary.available_protocols.filter((item) => typeof item === "string" && item)
      : [];
    return fromSummary.length ? fromSummary : DEFAULT_PROTOCOLS;
  }

  getActiveFilePath() {
    const activeFile = this.app.workspace.getActiveFile ? this.app.workspace.getActiveFile() : null;
    return activeFile && typeof activeFile.path === "string" ? activeFile.path : "";
  }

  getActiveConceptSlug() {
    const activePath = this.getActiveFilePath();
    if (!activePath.startsWith("wiki/concepts/") || !activePath.endsWith(".md")) {
      return "";
    }
    return path.basename(activePath, ".md");
  }

  getActiveOutputPath() {
    const activePath = this.getActiveFilePath();
    if (activePath.startsWith("output/") && activePath.endsWith(".md")) {
      return activePath;
    }
    return "";
  }

  getActiveCuratedPagePath() {
    const activePath = this.getActiveFilePath();
    if (
      activePath.endsWith(".md")
      && (activePath.startsWith("wiki/decisions/") || activePath.startsWith("wiki/judgments/"))
    ) {
      return activePath;
    }
    return "";
  }

  appendOptionalArg(args, flag, value) {
    const normalized = String(value || "").trim();
    if (!normalized) {
      return args;
    }
    args.push(flag, normalized);
    return args;
  }

  openStructuredCommandModal(spec) {
    new StructuredCommandModal(this.app, this, spec).open();
  }

  openContextPicker(spec) {
    new ContextPickerModal(this.app, this, spec).open();
  }

  controlIdSet(key) {
    const executionControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.execution_controls
      : null;
    const values = executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
    return new Set(values.map((item) => String(item || "").trim()).filter(Boolean));
  }

  uniqueContextOptions(options, keyName = "value") {
    const seen = new Set();
    return (Array.isArray(options) ? options : []).filter((option) => {
      if (!option || typeof option !== "object") {
        return false;
      }
      const key = String(option[keyName] || option.value || option.pagePath || option.actionId || option.entryId || "").trim();
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  pickActionControlSet(mode = "review") {
    if (mode === "apply") {
      return this.controlIdSet("apply_ready_action_ids");
    }
    if (mode === "revert") {
      return this.controlIdSet("revert_ready_action_ids");
    }
    return null;
  }

  pickArchiveControlSet(mode = "apply") {
    if (mode === "apply") {
      return this.controlIdSet("apply_ready_archive_entry_ids");
    }
    if (mode === "revert") {
      return this.controlIdSet("revert_ready_archive_entry_ids");
    }
    return new Set();
  }

  inferActionIdFromReceipt(receipt) {
    if (!receipt || typeof receipt !== "object") {
      return "";
    }
    const direct = String(receipt.action_id || "").trim();
    if (direct) {
      return direct;
    }
    const receiptPath = String(receipt.receipt_path || "").trim();
    if (!receiptPath) {
      return "";
    }
    return path.basename(receiptPath, path.extname(receiptPath));
  }

  activeConceptContextOption() {
    const slug = this.getActiveConceptSlug();
    if (!slug) {
      return null;
    }
    return {
      value: slug,
      label: slug,
      description: "当前激活的 concept 页面",
      slug,
    };
  }

  visibleReviewPageCandidates() {
    if (!this.shellSummary) {
      return [];
    }
    const aging = this.shellSummary.aging_summary || {};
    const pathToCandidate = new Map();
    const addCandidate = (pagePath, description, extras = {}) => {
      const normalized = String(pagePath || "").trim();
      if (!normalized) {
        return;
      }
      const current = pathToCandidate.get(normalized) || {
        value: normalized,
        label: normalized,
        description: "",
        pagePath: normalized,
        pageKind: "",
        status: "",
      };
      current.description = current.description || description || "";
      current.pageKind = current.pageKind || String(extras.pageKind || "").trim();
      current.status = current.status || String(extras.status || "").trim();
      pathToCandidate.set(normalized, current);
    };

    (aging.escalated_pages || []).forEach((pagePath) => addCandidate(pagePath, "Escalated review candidate"));
    (aging.overdue_pages || []).forEach((pagePath) => addCandidate(pagePath, "Overdue review candidate"));
    (aging.scheduled_pages || []).forEach((pagePath) => addCandidate(pagePath, "Scheduled review candidate"));

    const reviewEvents = Array.isArray(this.shellSummary.recent_runs)
      ? this.shellSummary.recent_runs.filter((entry) => entry.event_type === "review")
      : [];
    reviewEvents.forEach((entry) => {
      addCandidate(entry.page_path, `Recent review event${entry.status ? ` | ${entry.status}` : ""}`, {
        pageKind: entry.page_kind,
        status: entry.status,
      });
    });
    return this.uniqueContextOptions(Array.from(pathToCandidate.values()), "pagePath");
  }

  visibleRewriteCandidates() {
    const candidates = [];
    const activeConcept = this.activeConceptContextOption();
    if (activeConcept) {
      candidates.push(activeConcept);
    }
    const executionEvents = Array.isArray(this.shellSummary && this.shellSummary.recent_runs)
      ? this.shellSummary.recent_runs.filter((entry) => entry.event_type === "knowledge-lifecycle-override")
      : [];
    executionEvents.forEach((entry) => {
      const conceptPath = String(entry.path || "").trim();
      if (!conceptPath.startsWith("wiki/concepts/") || !conceptPath.endsWith(".md")) {
        return;
      }
      const slug = path.basename(conceptPath, ".md");
      candidates.push({
        value: slug,
        label: slug,
        description: `Lifecycle override | ${entry.lifecycle_state || entry.operation || "concept"}`,
        slug,
      });
    });
    return this.uniqueContextOptions(candidates, "slug");
  }

  visibleActionCandidates(mode = "review") {
    const receipts = Array.isArray(this.shellSummary && this.shellSummary.recent_receipts) ? this.shellSummary.recent_receipts : [];
    const allowedIds = this.pickActionControlSet(mode);
    const candidates = receipts
      .map((receipt) => {
        const actionId = this.inferActionIdFromReceipt(receipt);
        if (!actionId || String(receipt.subject_kind || "") === "material-archive") {
          return null;
        }
        if (allowedIds && !allowedIds.has(actionId)) {
          return null;
        }
        return {
          value: actionId,
          label: receipt.title || actionId,
          description: `${receipt.operation || "operation"} | ${receipt.applied_at || "unknown"}`,
          actionId,
          operation: String(receipt.operation || ""),
          receiptPath: String(receipt.receipt_path || ""),
        };
      })
      .filter(Boolean);
    return this.uniqueContextOptions(candidates, "actionId");
  }

  visibleArchiveCandidates(mode = "apply") {
    const candidates = [];
    const allowedIds = this.pickArchiveControlSet(mode);
    const receipts = Array.isArray(this.shellSummary && this.shellSummary.recent_receipts) ? this.shellSummary.recent_receipts : [];
    receipts.forEach((receipt) => {
      if (String(receipt.subject_kind || "") !== "material-archive") {
        return;
      }
      const entryId = String(receipt.subject_id || "").trim();
      if (!entryId || !allowedIds.has(entryId)) {
        return;
      }
      candidates.push({
        value: entryId,
        label: receipt.title || entryId,
        description: `${receipt.operation || "operation"} | ${receipt.applied_at || "unknown"}`,
        entryId,
        operation: String(receipt.operation || ""),
        receiptPath: String(receipt.receipt_path || ""),
      });
    });
    const executionEvents = Array.isArray(this.shellSummary && this.shellSummary.recent_runs)
      ? this.shellSummary.recent_runs.filter((entry) => ["archive-apply", "archive-revert"].includes(entry.event_type))
      : [];
    executionEvents.forEach((entry) => {
      const entryId = Array.isArray(entry.source_ids) && entry.source_ids.length ? String(entry.source_ids[0] || "").trim() : "";
      if (!entryId || !allowedIds.has(entryId)) {
        return;
      }
      candidates.push({
        value: entryId,
        label: entry.title || entryId,
        description: `${entry.event_type || "archive"} | ${entry.occurred_at || "unknown"}`,
        entryId,
        operation: entry.event_type === "archive-apply" ? "apply" : "revert",
        receiptPath: String(entry.receipt_path || ""),
      });
    });
    return this.uniqueContextOptions(candidates, "entryId");
  }

  openContextAwareAction(spec) {
    const options = this.uniqueContextOptions(spec.options || [], spec.keyName || "value");
    if (!options.length) {
      new Notice(spec.emptyNotice || "当前没有可用上下文，已回退到手动表单。");
      spec.onFallback();
      return;
    }
    if (options.length === 1) {
      spec.onSubmit(options[0]);
      return;
    }
    this.openContextPicker({
      title: spec.title,
      description: spec.description,
      submitLabel: spec.submitLabel || "Use",
      options,
      onSubmit: spec.onSubmit,
    });
  }

  async handleVaultChange(relativePath) {
    if (!relativePath) {
      return;
    }
    if (relativePath === SHELL_SUMMARY_PATH) {
      await this.loadShellSummaryFromDisk();
      return;
    }
    if (relativePath.startsWith("output/") || relativePath.startsWith("wiki/indexes/")) {
      this.refreshOpenViews();
    }
  }

  updateStatusBar() {
    if (!this.statusBarItem) {
      return;
    }
    const runningCount = this.pluginState.recentRuns.filter((entry) => entry.status === "running").length;
    if (!this.repoState.valid) {
      this.statusBarItem.setText("Furnace shell unavailable");
      this.statusBarItem.setAttribute("aria-label", `Missing runtime paths: ${this.repoState.missingPaths.join(", ")}`);
      return;
    }
    const protocol = this.getActiveProtocol();
    const suffix = runningCount ? ` | running ${runningCount}` : "";
    this.statusBarItem.setText(`Furnace ${protocol}${suffix}`);
    this.statusBarItem.setAttribute("aria-label", `Furnace Product Shell active protocol ${protocol}`);
  }

  async loadShellSummaryFromDisk() {
    if (!this.repoState.valid) {
      this.shellSummary = null;
      this.updateStatusBar();
      this.refreshOpenViews();
      return null;
    }
    const summaryFile = this.app.vault.getAbstractFileByPath(SHELL_SUMMARY_PATH);
    if (!summaryFile) {
      this.shellSummary = null;
      this.updateStatusBar();
      this.refreshOpenViews();
      return null;
    }
    try {
      const text = await this.app.vault.cachedRead(summaryFile);
      this.shellSummary = readJsonText(text);
    } catch (error) {
      console.error("[furnace-product-shell] failed to read shell summary", error);
      this.shellSummary = null;
    }
    this.updateStatusBar();
    this.refreshOpenViews();
    return this.shellSummary;
  }

  async execLauncher(args) {
    if (!this.repoState.valid) {
      throw new Error(`Missing runtime paths: ${this.repoState.missingPaths.join(", ")}`);
    }
    return await new Promise((resolve, reject) => {
      const child = spawn(this.repoState.launcherPath, args, {
        cwd: this.repoState.root,
        env: Object.assign({}, process.env),
      });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (chunk) => {
        stdout += String(chunk);
      });
      child.stderr.on("data", (chunk) => {
        stderr += String(chunk);
      });
      child.on("error", (error) => {
        reject(error);
      });
      child.on("close", (code) => {
        let payload = null;
        try {
          payload = readJsonText(stdout);
        } catch (error) {
          payload = null;
        }
        if (code === 0) {
          resolve({ stdout, stderr, payload, code });
          return;
        }
        const error = new Error(stderr.trim() || stdout.trim() || `Command failed with exit code ${code}`);
        error.code = code;
        error.stdout = stdout;
        error.stderr = stderr;
        error.payload = payload;
        reject(error);
      });
    });
  }

  runUiAction(action, label = "ui-action") {
    Promise.resolve()
      .then(() => action())
      .catch((error) => {
        console.error(`[furnace-product-shell] ${label} failed`, error);
      });
  }

  createRunRecord(label, args) {
    const record = {
      id: `run-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      label,
      args: args.join(" "),
      status: "running",
      startedAt: new Date().toISOString(),
      finishedAt: "",
      stdoutSummary: "",
      stderrSummary: "",
      resultPath: "",
      receiptPath: "",
      errorSummary: "",
    };
    this.pluginState.recentRuns.unshift(record);
    this.trimRecentRuns();
    this.updateStatusBar();
    this.refreshOpenViews();
    void this.savePluginState();
    return record;
  }

  updateRunRecord(record, updates) {
    Object.assign(record, updates);
    this.trimRecentRuns();
    this.updateStatusBar();
    this.refreshOpenViews();
    void this.savePluginState();
  }

  extractPrimaryPath(payload) {
    if (!payload || typeof payload !== "object") {
      return "";
    }
    const candidateKeys = ["path", "output_path", "receipt_path", "state_path", "index_path", "report_path"];
    for (const key of candidateKeys) {
      const value = payload[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
    return "";
  }

  async runPluginCommand(label, args, options = {}) {
    const record = this.createRunRecord(label, args);
    try {
      const result = await this.execLauncher(args);
      const primaryPath = this.extractPrimaryPath(result.payload);
      const receiptPath = result.payload && typeof result.payload.receipt_path === "string" ? result.payload.receipt_path : "";
      this.updateRunRecord(record, {
        status: "success",
        finishedAt: new Date().toISOString(),
        stdoutSummary: truncateText(result.stdout),
        stderrSummary: truncateText(result.stderr),
        resultPath: primaryPath,
        receiptPath,
      });
      if (options.updateSummaryFromPayload && result.payload && result.payload.kind === "product-shell-summary") {
        this.shellSummary = result.payload;
        this.updateStatusBar();
        this.refreshOpenViews();
      } else if (options.refreshAfter !== false) {
        await this.refreshShellSummarySilently();
      }
      if (options.notice !== false) {
        new Notice(`${label} completed.`);
      }
      return result.payload;
    } catch (error) {
      this.updateRunRecord(record, {
        status: "failed",
        finishedAt: new Date().toISOString(),
        stdoutSummary: truncateText(error.stdout || ""),
        stderrSummary: truncateText(error.stderr || ""),
        errorSummary: truncateText(error.message || "Command failed"),
      });
      new Notice(`${label} failed: ${truncateText(error.message || "unknown error", 120)}`);
      throw error;
    }
  }

  async refreshShellSummarySilently() {
    try {
      const result = await this.execLauncher(["shell-status"]);
      if (result.payload && result.payload.kind === "product-shell-summary") {
        this.shellSummary = result.payload;
        this.updateStatusBar();
        this.refreshOpenViews();
        return result.payload;
      }
    } catch (error) {
      console.error("[furnace-product-shell] shell-status refresh failed", error);
    }
    return await this.loadShellSummaryFromDisk();
  }

  async refreshShellSummaryCommand() {
    await this.runPluginCommand("Refresh Furnace Shell", ["shell-status"], {
      refreshAfter: false,
      updateSummaryFromPayload: true,
      notice: false,
    });
  }

  async runCompileCommand() {
    await this.runPluginCommand("Compile", ["compile"], { refreshAfter: true });
  }

  async runNightlyCommand() {
    await this.runPluginCommand("Nightly", ["nightly"], { refreshAfter: true });
  }

  async runProtocolSetCommand(protocol) {
    await this.runPluginCommand(`Set Protocol: ${protocol}`, ["protocol-set", protocol], { refreshAfter: true });
  }

  async runAskCommand({ question, format, mode, protocol }) {
    const args = [mode, question, "--format", format];
    if (protocol) {
      args.push("--protocol", protocol);
    }
    await this.runPluginCommand(`Ask: ${truncateText(question, 48)}`, args, { refreshAfter: true });
  }

  async runCliAction(label, command, args = []) {
    await this.runPluginCommand(label, [command, ...args], { refreshAfter: true });
  }

  openFileBackModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "File Back",
      description: "File an output artifact back into wiki/derived, wiki/decisions, or wiki/judgments.",
      fields: [
        {
          key: "artifact",
          label: "Artifact path",
          required: true,
          placeholder: "output/reports/....md",
          initialValue: () => prefill.artifact || this.getActiveOutputPath(),
        },
        {
          key: "title",
          label: "Title",
          placeholder: "Optional filed-back title",
          initialValue: prefill.title || "",
        },
        {
          key: "kind",
          label: "Kind",
          kind: "select",
          initialValue: prefill.kind || "derived",
          options: [
            ["derived", "derived"],
            ["decision", "decision"],
            ["judgment", "judgment"],
          ],
        },
        {
          key: "protocol",
          label: "Protocol",
          kind: "select",
          initialValue: prefill.protocol || "",
          options: [["", "current protocol"], ...this.getAvailableProtocols().map((item) => [item, item])],
        },
      ],
      onSubmit: async (values) => {
        const args = [values.artifact];
        this.appendOptionalArg(args, "--title", values.title);
        this.appendOptionalArg(args, "--kind", values.kind);
        this.appendOptionalArg(args, "--protocol", values.protocol);
        await this.runCliAction(`File Back: ${values.kind}`, "file-back", args);
      },
    });
  }

  openReviewPageModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Review Page",
      description: "Advance a decision or judgment page through the explicit review workflow.",
      fields: [
        {
          key: "page",
          label: "Page path",
          required: true,
          placeholder: "wiki/decisions/... or wiki/judgments/...",
          initialValue: () => prefill.pagePath || this.getActiveCuratedPagePath(),
        },
        {
          key: "status",
          label: "Status",
          required: true,
          placeholder: "approved / confirmed / needs-revision ...",
          initialValue: prefill.status || "",
        },
        {
          key: "note",
          label: "Note",
          kind: "textarea",
          placeholder: "Optional review note",
          rows: 4,
          initialValue: prefill.note || "",
        },
        {
          key: "confidence",
          label: "Confidence",
          placeholder: "Optional confidence override",
          initialValue: prefill.confidence || "",
        },
      ],
      onSubmit: async (values) => {
        const args = [values.page, "--status", values.status];
        this.appendOptionalArg(args, "--note", values.note);
        this.appendOptionalArg(args, "--confidence", values.confidence);
        await this.runCliAction(`Review Page: ${values.status}`, "review-page", args);
      },
    });
  }

  openReviewRewriteModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Review Rewrite",
      description: "Advance a concept rewrite proposal through the rewrite workflow.",
      fields: [
        { key: "slug", label: "Concept slug", required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "status", label: "Status", required: true, placeholder: "accepted / rejected / needs-revision ...", initialValue: prefill.status || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional review note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug, "--status", values.status];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Review Rewrite: ${values.slug}`, "review-rewrite", args);
      },
    });
  }

  openApplyRewriteModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Apply Rewrite",
      description: "Apply an accepted concept rewrite proposal.",
      fields: [
        { key: "slug", label: "Concept slug", required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional apply note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Apply Rewrite: ${values.slug}`, "apply-rewrite", args);
      },
    });
  }

  openRetireConceptModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Retire Concept",
      description: "Apply an explicit retired override for a concept.",
      fields: [
        { key: "slug", label: "Concept slug", required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Why retire this concept?", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Retire Concept: ${values.slug}`, "retire-concept", args);
      },
    });
  }

  openReactivateConceptModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Reactivate Concept",
      description: "Clear the explicit retired override for a concept.",
      fields: [
        { key: "slug", label: "Concept slug", required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional reactivate note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Reactivate Concept: ${values.slug}`, "reactivate-concept", args);
      },
    });
  }

  openApplyArchiveModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Apply Archive",
      description: "Apply a ready archive candidate and pin it to archived.",
      fields: [
        { key: "entry_id", label: "Entry id", required: true, placeholder: "manifest/material entry id", initialValue: prefill.entryId || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional apply note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.entry_id];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Apply Archive: ${values.entry_id}`, "apply-archive", args);
      },
    });
  }

  openRevertArchiveModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Revert Archive",
      description: "Revert the latest explicit archive transition.",
      fields: [
        { key: "entry_id", label: "Entry id", required: true, placeholder: "manifest/material entry id", initialValue: prefill.entryId || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional revert note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.entry_id];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Revert Archive: ${values.entry_id}`, "revert-archive", args);
      },
    });
  }

  openReviewActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Review Action",
      description: "Advance a machine-memory repair action through the explicit action workflow.",
      fields: [
        { key: "action_id", label: "Action id", required: true, placeholder: "machine-memory action id", initialValue: prefill.actionId || "" },
        { key: "status", label: "Status", required: true, placeholder: "accepted / rejected / ready ...", initialValue: prefill.status || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional action review note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id, "--status", values.status];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Review Action: ${values.action_id}`, "review-action", args);
      },
    });
  }

  openApplyActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Apply Action",
      description: "Apply an accepted low-risk machine-memory repair action.",
      fields: [
        { key: "action_id", label: "Action id", required: true, placeholder: "machine-memory action id", initialValue: prefill.actionId || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional apply note", initialValue: prefill.note || "" },
        { key: "bundle", label: "Bundle path", placeholder: "Optional execution bundle path", initialValue: prefill.bundle || "" },
        { key: "dry_run", label: "Dry run", kind: "toggle", initialValue: Boolean(prefill.dryRun) },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id];
        this.appendOptionalArg(args, "--note", values.note);
        this.appendOptionalArg(args, "--bundle", values.bundle);
        if (values.dry_run) {
          args.push("--dry-run");
        }
        await this.runCliAction(`Apply Action: ${values.action_id}`, "apply-action", args);
      },
    });
  }

  openRevertActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: "Revert Action",
      description: "Revert the latest low-risk safe apply for a machine-memory action.",
      fields: [
        { key: "action_id", label: "Action id", required: true, placeholder: "machine-memory action id", initialValue: prefill.actionId || "" },
        { key: "note", label: "Note", kind: "textarea", rows: 4, placeholder: "Optional revert note", initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id];
        this.appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Revert Action: ${values.action_id}`, "revert-action", args);
      },
    });
  }

  openReviewPageContextPicker(options = this.visibleReviewPageCandidates()) {
    this.openContextAwareAction({
      title: "Pick Review Page",
      description: "Prefer a visible review backlog item before falling back to manual page entry.",
      keyName: "pagePath",
      options,
      emptyNotice: "当前没有可见的 review backlog 条目，已回退到手动表单。",
      onFallback: () => this.openReviewPageModal(),
      onSubmit: (option) => this.openReviewPageModal({
        pagePath: option.pagePath,
        status: option.status || "",
      }),
    });
  }

  openReviewRewriteContextPicker(options = this.visibleRewriteCandidates()) {
    this.openContextAwareAction({
      title: "Pick Rewrite Context",
      description: "Prefer a visible or active concept context before falling back to manual slug entry.",
      keyName: "slug",
      options,
      emptyNotice: "当前没有可见的 concept context，已回退到手动表单。",
      onFallback: () => this.openReviewRewriteModal(),
      onSubmit: (option) => this.openReviewRewriteModal({ slug: option.slug || option.value || "" }),
    });
  }

  openReviewActionContextPicker(options = this.visibleActionCandidates("review")) {
    this.openContextAwareAction({
      title: "Pick Review Action",
      description: "Prefer a visible execution receipt before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openReviewActionModal(),
      onSubmit: (option) => this.openReviewActionModal({ actionId: option.actionId || option.value || "" }),
    });
  }

  openApplyArchiveContextPicker(options = this.visibleArchiveCandidates("apply")) {
    this.openContextAwareAction({
      title: "Pick Archive Target",
      description: "Prefer a visible archive receipt or event before falling back to manual entry id.",
      keyName: "entryId",
      options,
      emptyNotice: "当前没有可见的 archive context，已回退到手动表单。",
      onFallback: () => this.openApplyArchiveModal(),
      onSubmit: (option) => this.openApplyArchiveModal({ entryId: option.entryId || option.value || "" }),
    });
  }

  openRevertArchiveContextPicker(options = this.visibleArchiveCandidates("revert")) {
    this.openContextAwareAction({
      title: "Pick Archive Revert Target",
      description: "Prefer a visible archive receipt or event before falling back to manual entry id.",
      keyName: "entryId",
      options,
      emptyNotice: "当前没有可见的 archive context，已回退到手动表单。",
      onFallback: () => this.openRevertArchiveModal(),
      onSubmit: (option) => this.openRevertArchiveModal({ entryId: option.entryId || option.value || "" }),
    });
  }

  openApplyActionContextPicker(options = this.visibleActionCandidates("apply")) {
    this.openContextAwareAction({
      title: "Pick Apply Action",
      description: "Prefer a visible execution receipt before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openApplyActionModal(),
      onSubmit: (option) => this.openApplyActionModal({ actionId: option.actionId || option.value || "" }),
    });
  }

  openRevertActionContextPicker(options = this.visibleActionCandidates("revert")) {
    this.openContextAwareAction({
      title: "Pick Revert Action",
      description: "Prefer a visible execution receipt before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openRevertActionModal(),
      onSubmit: (option) => this.openRevertActionModal({ actionId: option.actionId || option.value || "" }),
    });
  }

  async openView(viewType) {
    let leaf = this.app.workspace.getLeavesOfType(viewType)[0];
    if (!leaf) {
      leaf = this.app.workspace.getRightLeaf(false) || this.app.workspace.getLeaf(true);
    }
    await leaf.setViewState({ type: viewType, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  async openFurnaceCenterView() {
    await this.openView(VIEW_TYPE_FURNACE_CENTER);
  }

  async openRecentRunsView() {
    await this.openView(VIEW_TYPE_RECENT_RUNS);
  }

  async openReviewCenterView() {
    await this.openView(VIEW_TYPE_REVIEW_CENTER);
  }

  async openExecutionCenterView() {
    await this.openView(VIEW_TYPE_EXECUTION_CENTER);
  }

  async openWorkspacePath(relativePath) {
    const normalized = String(relativePath || "").trim();
    if (!normalized) {
      new Notice("No path to open.");
      return;
    }
    const abstractFile = this.app.vault.getAbstractFileByPath(normalized);
    if (abstractFile && normalized.endsWith(".md")) {
      const leaf = this.app.workspace.getLeaf(true);
      await leaf.openFile(abstractFile);
      return;
    }
    if (!this.repoState.root) {
      new Notice(`Unable to open ${normalized}`);
      return;
    }
    const absolutePath = path.join(this.repoState.root, normalized);
    if (!fs.existsSync(absolutePath)) {
      new Notice(`Path not found: ${normalized}`);
      return;
    }
    if (typeof this.app.vault.adapter.getResourcePath === "function") {
      const resourcePath = this.app.vault.adapter.getResourcePath(normalized);
      window.open(resourcePath, "_blank");
      return;
    }
    new Notice(`Unable to open resource: ${normalized}`);
  }

  renderCardGrid(container, cards) {
    const grid = container.createDiv({ cls: "furnace-shell-grid" });
    cards.forEach((card) => {
      const cardEl = grid.createDiv({ cls: "furnace-shell-card" });
      cardEl.createDiv({ cls: "furnace-shell-card-label", text: card.label });
      cardEl.createDiv({ cls: "furnace-shell-card-value", text: String(card.value) });
    });
  }

  renderActionButtons(container, buttons) {
    const actions = container.createDiv({ cls: "furnace-shell-actions" });
    buttons.forEach((buttonConfig) => {
      const button = actions.createEl("button", { text: buttonConfig.label });
      if (buttonConfig.cta) {
        button.addClass("mod-cta");
      }
      button.addEventListener("click", () => {
        this.runUiAction(() => buttonConfig.onClick(), `Button: ${buttonConfig.label}`);
      });
    });
  }

  renderFurnaceCenter(contentEl) {
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Furnace Center" });

    if (!this.repoState.valid) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: `Repo-local runtime unavailable. Missing: ${this.repoState.missingPaths.join(", ")}`,
      });
      return;
    }

    this.renderActionButtons(contentEl, [
      { label: "Refresh", cta: true, onClick: async () => this.refreshShellSummaryCommand() },
      { label: "Compile", onClick: async () => this.runCompileCommand() },
      { label: "Ask", onClick: async () => new AskCommandModal(this.app, this).open() },
      { label: "Nightly", onClick: async () => this.runNightlyCommand() },
      { label: "Set Protocol", onClick: async () => new ProtocolCommandModal(this.app, this).open() },
      { label: "Review Center", onClick: async () => this.openReviewCenterView() },
      { label: "Execution Center", onClick: async () => this.openExecutionCenterView() },
      { label: "Recent Runs", onClick: async () => this.openRecentRunsView() },
    ]);

    if (!this.shellSummary) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: "shell-summary.json 尚未生成。先运行 Refresh / Compile / Nightly 之一。",
      });
      return;
    }

    const review = this.shellSummary.review_backlog_counts || {};
    const aging = this.shellSummary.aging_summary || {};
    const llmStatus = this.shellSummary.llm_status || {};
    this.renderCardGrid(contentEl, [
      { label: "Active Protocol", value: this.shellSummary.active_protocol || "general" },
      { label: "LLM Backend", value: llmStatus.backend || "unconfigured" },
      { label: "Pending Reviews", value: Number(review.pending_decisions || 0) + Number(review.pending_judgments || 0) },
      { label: "Overdue", value: Number(aging.overdue_count || 0) },
      { label: "Escalation", value: Number(aging.escalated_count || 0) },
      { label: "Recent Outputs", value: Array.isArray(this.shellSummary.recent_outputs) ? this.shellSummary.recent_outputs.length : 0 },
    ]);

    const summarySection = contentEl.createDiv({ cls: "furnace-shell-section" });
    summarySection.createEl("h3", { text: "Summary" });
    summarySection.createEl("div", {
      cls: "furnace-shell-meta",
      text: `Generated at ${this.shellSummary.generated_at || "unknown"} | contract v${this.shellSummary.contract_version || "?"}`,
    });
    summarySection.createEl("div", {
      cls: "furnace-shell-meta",
      text: `Review backlog ${Number(review.pending_decisions || 0) + Number(review.pending_judgments || 0)} | concept backlog ${review.concept_backlog || 0} | retired concepts ${review.retired_concepts || 0}`,
    });

    const outputsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    outputsSection.createEl("h3", { text: "Recent Outputs" });
    const outputs = Array.isArray(this.shellSummary.recent_outputs) ? this.shellSummary.recent_outputs : [];
    if (!outputs.length) {
      outputsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent outputs。" });
    } else {
      const list = outputsSection.createEl("ul", { cls: "furnace-shell-list" });
      outputs.slice(0, 8).forEach((artifact) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: artifact.title || artifact.path || "output" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${artifact.format || "unknown"} | ${artifact.protocol || "general"} | ${artifact.created_at || "unknown"}`,
        });
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const openButton = actions.createEl("button", { text: "Open" });
        openButton.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(artifact.path), `Open output: ${artifact.path}`);
        });
      });
    }

    const linksSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    linksSection.createEl("h3", { text: "Quick Links" });
    const linkList = linksSection.createEl("ul", { cls: "furnace-shell-list" });
    const links = this.shellSummary.links || {};
    [
      ["furnace_center_markdown", "Furnace Center Index"],
      ["review_center_markdown", "Review Center"],
      ["protocols_markdown", "Protocols"],
      ["domain_pilots_markdown", "Domain Pilots"],
      ["output_packs_markdown", "Output Packs"],
    ].forEach(([key, label]) => {
      if (!links[key]) {
        return;
      }
      const item = linkList.createEl("li");
      item.createEl("span", { text: label });
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const button = actions.createEl("button", { text: "Open" });
      button.addEventListener("click", () => {
        this.runUiAction(() => this.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
      });
    });
    if (this.settings.showHtmlShortcuts) {
      [
        ["furnace_center_html", "Furnace HTML"],
        ["review_center_html", "Review HTML"],
        ["execution_center_html", "Execution HTML"],
      ].forEach(([key, label]) => {
        if (!links[key]) {
          return;
        }
        const item = linkList.createEl("li");
        item.createEl("span", { text: label });
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const button = actions.createEl("button", { text: "Open" });
        button.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
        });
      });
    }
  }

  renderRecentRuns(contentEl) {
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Recent Runs" });

    const pluginRunsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    pluginRunsSection.createEl("h3", { text: "Plugin-triggered Commands" });
    if (!this.pluginState.recentRuns.length) {
      pluginRunsSection.createDiv({ cls: "furnace-shell-empty", text: "当前还没有插件触发的命令。" });
    } else {
      const list = pluginRunsSection.createEl("ul", { cls: "furnace-shell-list" });
      this.pluginState.recentRuns.forEach((record) => {
        const item = list.createEl("li");
        const statusClass =
          record.status === "success"
            ? "furnace-shell-status-ok"
            : record.status === "failed"
              ? "furnace-shell-status-failed"
              : "furnace-shell-status-running";
        item.createEl("strong", { text: record.label || record.args || "command" });
        item.createDiv({
          cls: `furnace-shell-meta ${statusClass}`,
          text: `${record.status || "unknown"} | started ${record.startedAt || "unknown"}${record.finishedAt ? ` | finished ${record.finishedAt}` : ""}`,
        });
        if (record.args) {
          item.createDiv({ cls: "furnace-shell-code", text: record.args });
        }
        if (record.stdoutSummary) {
          item.createDiv({ cls: "furnace-shell-meta", text: `stdout: ${record.stdoutSummary}` });
        }
        if (record.stderrSummary) {
          item.createDiv({ cls: "furnace-shell-meta", text: `stderr: ${record.stderrSummary}` });
        }
        if (record.errorSummary) {
          item.createDiv({ cls: "furnace-shell-meta", text: `error: ${record.errorSummary}` });
        }
        if (record.resultPath || record.receiptPath) {
          const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
          if (record.resultPath) {
          const outputButton = actions.createEl("button", { text: "Open result" });
          outputButton.addEventListener("click", () => {
              this.runUiAction(() => this.openWorkspacePath(record.resultPath), `Open result: ${record.resultPath}`);
          });
        }
        if (record.receiptPath) {
          const receiptButton = actions.createEl("button", { text: "Open receipt" });
          receiptButton.addEventListener("click", () => {
              this.runUiAction(() => this.openWorkspacePath(record.receiptPath), `Open receipt: ${record.receiptPath}`);
          });
        }
        }
      });
    }

    const runtimeSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    runtimeSection.createEl("h3", { text: "Runtime Events from shell-summary" });
    const runtimeEvents = this.shellSummary && Array.isArray(this.shellSummary.recent_runs) ? this.shellSummary.recent_runs : [];
    if (!runtimeEvents.length) {
      runtimeSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 shell summary recent runs。" });
    } else {
      const list = runtimeSection.createEl("ul", { cls: "furnace-shell-list" });
      runtimeEvents.forEach((entry) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: entry.title || entry.event_type || "runtime-event" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${entry.event_type || "event"} | ${entry.protocol || "general"} | ${entry.occurred_at || "unknown"}`,
        });
        const pathValue = entry.output_path || entry.receipt_path || entry.page_path || entry.path || "";
        if (pathValue) {
          const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
          const button = actions.createEl("button", { text: "Open" });
          button.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(pathValue), `Open runtime event path: ${pathValue}`);
          });
        }
      });
    }

    const receiptSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    receiptSection.createEl("h3", { text: "Recent Receipts" });
    const receipts = this.shellSummary && Array.isArray(this.shellSummary.recent_receipts) ? this.shellSummary.recent_receipts : [];
    if (!receipts.length) {
      receiptSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent receipts。" });
    } else {
      const list = receiptSection.createEl("ul", { cls: "furnace-shell-list" });
      receipts.forEach((receipt) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: receipt.title || receipt.subject_id || "receipt" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${receipt.operation || "operation"} | ${receipt.protocol || "general"} | ${receipt.applied_at || "unknown"}`,
        });
        if (receipt.receipt_path) {
          const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
          const button = actions.createEl("button", { text: "Open receipt" });
          button.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(receipt.receipt_path), `Open receipt: ${receipt.receipt_path}`);
          });
        }
      });
    }
  }

  renderReviewCenter(contentEl) {
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Review Center" });

    if (!this.repoState.valid) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: `Repo-local runtime unavailable. Missing: ${this.repoState.missingPaths.join(", ")}`,
      });
      return;
    }

    this.renderActionButtons(contentEl, [
      { label: "Refresh", cta: true, onClick: async () => this.refreshShellSummaryCommand() },
      { label: "Furnace Center", onClick: async () => this.openFurnaceCenterView() },
      { label: "Execution Center", onClick: async () => this.openExecutionCenterView() },
    ]);
    this.renderActionButtons(contentEl, [
      { label: "Review Page", onClick: async () => this.openReviewPageContextPicker() },
      { label: "Review Rewrite", onClick: async () => this.openReviewRewriteContextPicker() },
      { label: "Apply Rewrite", onClick: async () => this.openApplyRewriteModal() },
      { label: "Retire Concept", onClick: async () => this.openRetireConceptModal() },
      { label: "Reactivate Concept", onClick: async () => this.openReactivateConceptModal() },
      { label: "File Back", onClick: async () => this.openFileBackModal() },
    ]);

    if (!this.shellSummary) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: "shell-summary.json 尚未生成。先运行 Refresh / Compile / Nightly 之一。",
      });
      return;
    }

    const review = this.shellSummary.review_backlog_counts || {};
    const aging = this.shellSummary.aging_summary || {};
    this.renderCardGrid(contentEl, [
      { label: "Pending Decisions", value: review.pending_decisions || 0 },
      { label: "Pending Judgments", value: review.pending_judgments || 0 },
      { label: "Overdue Reviews", value: aging.overdue_count || 0 },
      { label: "Escalation", value: aging.escalated_count || 0 },
      { label: "Concept Backlog", value: review.concept_backlog || 0 },
      { label: "Review Concepts", value: review.review_concepts || 0 },
      { label: "Revisit Concepts", value: review.revisit_concepts || 0 },
      { label: "Retired Concepts", value: review.retired_concepts || 0 },
    ]);

    const agingSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    agingSection.createEl("h3", { text: "Aging Summary" });
    const agingList = agingSection.createEl("ul", { cls: "furnace-shell-list" });
    [
      ["Overdue pages", aging.overdue_pages || []],
      ["Escalated pages", aging.escalated_pages || []],
      ["Scheduled pages", aging.scheduled_pages || []],
    ].forEach(([label, pages]) => {
      const item = agingList.createEl("li");
      item.createEl("strong", { text: `${label}: ${pages.length}` });
      if (!pages.length) {
        item.createDiv({ cls: "furnace-shell-meta", text: "none" });
        return;
      }
      const pageList = item.createEl("ul", { cls: "furnace-shell-list" });
      pages.slice(0, 6).forEach((pagePath) => {
        const pageItem = pageList.createEl("li");
        pageItem.createEl("span", { text: pagePath });
        const actions = pageItem.createDiv({ cls: "furnace-shell-inline-actions" });
        const openButton = actions.createEl("button", { text: "Open" });
        openButton.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(pagePath), `Open aging page: ${pagePath}`);
        });
        const reviewButton = actions.createEl("button", { text: "Review" });
        reviewButton.addEventListener("click", () => {
          this.runUiAction(() => this.openReviewPageModal({ pagePath }), `Review aging page: ${pagePath}`);
        });
      });
    });

    const reviewEvents = Array.isArray(this.shellSummary.recent_runs)
      ? this.shellSummary.recent_runs.filter((entry) => entry.event_type === "review")
      : [];
    const eventsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    eventsSection.createEl("h3", { text: "Recent Review Events" });
    if (!reviewEvents.length) {
      eventsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent review events。" });
    } else {
      const list = eventsSection.createEl("ul", { cls: "furnace-shell-list" });
      reviewEvents.slice(0, 8).forEach((entry) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: entry.title || entry.page_path || "review" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${entry.status || "status-unknown"} | ${entry.occurred_at || "unknown"}`,
        });
        if (entry.page_path) {
          const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
          const button = actions.createEl("button", { text: "Open page" });
          button.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(entry.page_path), `Open review page: ${entry.page_path}`);
          });
          const reviewButton = actions.createEl("button", { text: "Review" });
          reviewButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.openReviewPageModal({ pagePath: entry.page_path, status: entry.status || "" }),
              `Review event page: ${entry.page_path}`
            );
          });
        }
      });
    }

    const links = this.shellSummary.links || {};
    const linksSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    linksSection.createEl("h3", { text: "Governance Links" });
    const linkList = linksSection.createEl("ul", { cls: "furnace-shell-list" });
    [
      ["review_center_markdown", "Review Center Index"],
      ["review_center_html", "Review Center HTML"],
      ["protocols_markdown", "Protocols"],
      ["domain_pilots_markdown", "Domain Pilots"],
      ["output_packs_markdown", "Output Packs"],
    ].forEach(([key, label]) => {
      if (!links[key]) {
        return;
      }
      const item = linkList.createEl("li");
      item.createEl("span", { text: label });
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const button = actions.createEl("button", { text: "Open" });
      button.addEventListener("click", () => {
        this.runUiAction(() => this.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
      });
    });
  }

  renderExecutionCenter(contentEl) {
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Execution Center" });

    if (!this.repoState.valid) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: `Repo-local runtime unavailable. Missing: ${this.repoState.missingPaths.join(", ")}`,
      });
      return;
    }

    this.renderActionButtons(contentEl, [
      { label: "Refresh", cta: true, onClick: async () => this.refreshShellSummaryCommand() },
      { label: "Furnace Center", onClick: async () => this.openFurnaceCenterView() },
      { label: "Review Center", onClick: async () => this.openReviewCenterView() },
      { label: "Recent Runs", onClick: async () => this.openRecentRunsView() },
    ]);
    this.renderActionButtons(contentEl, [
      { label: "Review Action", onClick: async () => this.openReviewActionContextPicker() },
      { label: "Apply Action", onClick: async () => this.openApplyActionContextPicker() },
      { label: "Revert Action", onClick: async () => this.openRevertActionContextPicker() },
      { label: "Apply Archive", onClick: async () => this.openApplyArchiveContextPicker() },
      { label: "Revert Archive", onClick: async () => this.openRevertArchiveContextPicker() },
    ]);

    if (!this.shellSummary) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: "shell-summary.json 尚未生成。先运行 Refresh / Compile / Nightly 之一。",
      });
      return;
    }

    const receipts = Array.isArray(this.shellSummary.recent_receipts) ? this.shellSummary.recent_receipts : [];
    const executionEvents = Array.isArray(this.shellSummary.recent_runs)
      ? this.shellSummary.recent_runs.filter((entry) =>
          ["archive-apply", "archive-revert", "knowledge-lifecycle-override", "nightly"].includes(entry.event_type)
        )
      : [];
    this.renderCardGrid(contentEl, [
      { label: "Recent Receipts", value: receipts.length },
      { label: "Execution Events", value: executionEvents.length },
      {
        label: "Archive Events",
        value: executionEvents.filter((entry) => ["archive-apply", "archive-revert"].includes(entry.event_type)).length,
      },
      {
        label: "Lifecycle Overrides",
        value: executionEvents.filter((entry) => entry.event_type === "knowledge-lifecycle-override").length,
      },
      {
        label: "Nightly Runs",
        value: executionEvents.filter((entry) => entry.event_type === "nightly").length,
      },
    ]);

    const receiptsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    receiptsSection.createEl("h3", { text: "Recent Receipts" });
    if (!receipts.length) {
      receiptsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent receipts。" });
    } else {
      const list = receiptsSection.createEl("ul", { cls: "furnace-shell-list" });
      receipts.slice(0, 8).forEach((receipt) => {
        const item = list.createEl("li");
        const actionId = this.inferActionIdFromReceipt(receipt);
        const revertReadyActions = this.controlIdSet("revert_ready_action_ids");
        const applyReadyActions = this.controlIdSet("apply_ready_action_ids");
        const revertReadyArchives = this.controlIdSet("revert_ready_archive_entry_ids");
        const applyReadyArchives = this.controlIdSet("apply_ready_archive_entry_ids");
        item.createEl("strong", { text: receipt.title || receipt.subject_id || "receipt" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${receipt.operation || "operation"} | ${receipt.protocol || "general"} | ${receipt.applied_at || "unknown"}`,
        });
        if (receipt.receipt_path) {
          const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
          const button = actions.createEl("button", { text: "Open receipt" });
          button.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(receipt.receipt_path), `Open receipt: ${receipt.receipt_path}`);
          });
          if (String(receipt.subject_kind || "") === "material-archive" && String(receipt.subject_id || "")) {
            const entryId = String(receipt.subject_id || "");
            if (revertReadyArchives.has(entryId) || applyReadyArchives.has(entryId)) {
              const archiveButton = actions.createEl("button", {
                text: revertReadyArchives.has(entryId) ? "Revert archive" : "Apply archive",
              });
              archiveButton.addEventListener("click", () => {
                this.runUiAction(
                  () => (revertReadyArchives.has(entryId) ? this.openRevertArchiveModal({ entryId }) : this.openApplyArchiveModal({ entryId })),
                  `Archive receipt action: ${entryId}`
                );
              });
            }
          } else if (actionId) {
            const reviewButton = actions.createEl("button", { text: "Review action" });
            reviewButton.addEventListener("click", () => {
              this.runUiAction(() => this.openReviewActionModal({ actionId }), `Review action from receipt: ${actionId}`);
            });
            if (revertReadyActions.has(actionId) || applyReadyActions.has(actionId)) {
              const actionButton = actions.createEl("button", {
                text: revertReadyActions.has(actionId) ? "Revert action" : "Apply action",
              });
              actionButton.addEventListener("click", () => {
                this.runUiAction(
                  () => (revertReadyActions.has(actionId) ? this.openRevertActionModal({ actionId }) : this.openApplyActionModal({ actionId })),
                  `Execution receipt action: ${actionId}`
                );
              });
            }
          }
        }
      });
    }

    const eventsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    eventsSection.createEl("h3", { text: "Recent Execution Events" });
    if (!executionEvents.length) {
      eventsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent execution events。" });
    } else {
      const list = eventsSection.createEl("ul", { cls: "furnace-shell-list" });
      executionEvents.slice(0, 10).forEach((entry) => {
        const item = list.createEl("li");
        const revertReadyArchives = this.controlIdSet("revert_ready_archive_entry_ids");
        const applyReadyArchives = this.controlIdSet("apply_ready_archive_entry_ids");
        item.createEl("strong", { text: entry.title || entry.event_type || "event" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${entry.event_type || "event"} | ${entry.protocol || "general"} | ${entry.occurred_at || "unknown"}`,
        });
        const pathValue = entry.receipt_path || entry.path || entry.output_path || "";
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        if (pathValue) {
          const button = actions.createEl("button", { text: "Open" });
          button.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(pathValue), `Open execution path: ${pathValue}`);
          });
        }
        if (["archive-apply", "archive-revert"].includes(String(entry.event_type || "")) && Array.isArray(entry.source_ids) && entry.source_ids.length) {
          const entryId = String(entry.source_ids[0] || "");
          if (revertReadyArchives.has(entryId) || applyReadyArchives.has(entryId)) {
            const archiveButton = actions.createEl("button", {
              text: revertReadyArchives.has(entryId) ? "Revert archive" : "Apply archive",
            });
            archiveButton.addEventListener("click", () => {
              this.runUiAction(
                () => (revertReadyArchives.has(entryId) ? this.openRevertArchiveModal({ entryId }) : this.openApplyArchiveModal({ entryId })),
                `Archive event action: ${entryId}`
              );
            });
          }
        }
        if (String(entry.event_type || "") === "knowledge-lifecycle-override" && String(entry.path || "").startsWith("wiki/concepts/")) {
          const slug = path.basename(String(entry.path || ""), ".md");
          const lifecycleButton = actions.createEl("button", {
            text: String(entry.lifecycle_state || "") === "retired" ? "Reactivate concept" : "Retire concept",
          });
          lifecycleButton.addEventListener("click", () => {
            this.runUiAction(
              () =>
                String(entry.lifecycle_state || "") === "retired"
                  ? this.openReactivateConceptModal({ slug })
                  : this.openRetireConceptModal({ slug }),
              `Lifecycle override action: ${slug}`
            );
          });
        }
      });
    }

    const links = this.shellSummary.links || {};
    const linksSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    linksSection.createEl("h3", { text: "Execution Links" });
    const linkList = linksSection.createEl("ul", { cls: "furnace-shell-list" });
    [
      ["execution_center_markdown", "Execution Center Index"],
      ["execution_center_html", "Execution Center HTML"],
      ["execution_audit_markdown", "Execution Audit"],
      ["execution_audit_html", "Execution Audit HTML"],
      ["graph_view_markdown", "Graph View"],
    ].forEach(([key, label]) => {
      if (!links[key]) {
        return;
      }
      const item = linkList.createEl("li");
      item.createEl("span", { text: label });
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const button = actions.createEl("button", { text: "Open" });
      button.addEventListener("click", () => {
        this.runUiAction(() => this.openWorkspacePath(links[key]), `Open link: ${links[key]}`);
      });
    });
  }

  refreshOpenViews() {
    this.openViews.forEach((view) => {
      if (view && typeof view.render === "function") {
        view.render();
      }
    });
  }
};
