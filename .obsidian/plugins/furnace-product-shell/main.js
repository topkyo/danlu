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
const CURATED_STATUS_LABELS = {
  proposed: "Proposed",
  approved: "Approved",
  "needs-revisit": "Needs revisit",
  superseded: "Superseded",
  tentative: "Tentative",
  tracking: "Tracking",
  confirmed: "Confirmed",
  rejected: "Rejected",
};
const ACTION_STATUS_LABELS = {
  proposed: "Proposed",
  accepted: "Accepted",
  deferred: "Deferred",
  resolved: "Resolved",
  rejected: "Rejected",
};
const REWRITE_STATUS_LABELS = {
  proposed: "Proposed",
  accepted: "Accepted",
  deferred: "Deferred",
  applied: "Applied",
  rejected: "Rejected",
};
const REVIEW_REASON_LABELS = {
  "pending-review": "pending review",
  "overdue-review": "overdue review",
  "escalation-candidate": "escalation candidate",
  "scheduled-review": "scheduled review",
  "missing-counter-evidence": "missing counter evidence",
  "missing-invalidation": "missing invalidation",
  "missing-next-signals": "missing next signals",
  "missing-review-history": "missing review history",
  "citation-drift": "citation drift",
  "citation-snapshot-gap": "citation snapshot gap",
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

function displayCuratedStatus(status) {
  return CURATED_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown");
}

function displayActionStatus(status) {
  return ACTION_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown");
}

function displayRewriteStatus(status) {
  return REWRITE_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown");
}

function displayReviewReason(reason) {
  const normalized = String(reason || "").trim();
  return REVIEW_REASON_LABELS[normalized] || normalized;
}

function displayReviewReasonList(reasons) {
  if (!Array.isArray(reasons) || !reasons.length) {
    return "";
  }
  return reasons.map((reason) => displayReviewReason(reason)).filter(Boolean).join(", ");
}

function reviewObjectMetaText(control) {
  const parts = [
    String(control.kind || "").trim() || "page",
    displayCuratedStatus(control.status),
  ];
  const confidence = String(control.confidence || "").trim();
  if (confidence) {
    parts.push(`confidence ${confidence}`);
  }
  if (String(control.kind || "").trim() === "decision" || String(control.kind || "").trim() === "judgment") {
    parts.push(`asset ${Number(control.asset_score || 0)}/4`);
  }
  const reviewHistoryEntries = Number(control.review_history_entries || 0);
  if (reviewHistoryEntries) {
    parts.push(`history ${reviewHistoryEntries}`);
  }
  if (control.citation_drift) {
    parts.push(`drift ${Number(control.citation_drift_count || 0) || 1}`);
  }
  const snapshotGapCount = Number(control.citation_snapshot_gap_count || 0);
  if (snapshotGapCount) {
    parts.push(`snapshot gaps ${snapshotGapCount}`);
  }
  const reasons = displayReviewReasonList(control.reasons);
  if (reasons) {
    parts.push(reasons);
  }
  return parts.join(" | ");
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

class CaptureNoteModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Capture Note" });

    const titleSetting = new Setting(contentEl).setName("Title");
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = "Optional note title...";
    titleInput.addClass("furnace-shell-code");

    const kindSetting = new Setting(contentEl).setName("Kind");
    const kindSelect = kindSetting.controlEl.createEl("select");
    [
      ["note", "note"],
      ["transcript", "transcript"],
    ].forEach(([value, label]) => {
      const option = kindSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    kindSelect.value = "note";

    const textSetting = new Setting(contentEl).setName("Text");
    const textInput = textSetting.controlEl.createEl("textarea");
    textInput.rows = 10;
    textInput.placeholder = "Capture a note, meeting log, or quick observation...";
    textInput.addClass("furnace-shell-code");

    const hint = contentEl.createDiv({ cls: "furnace-shell-meta" });
    hint.setText("This writes into raw/inbox through the same launcher/runtime used by CLI commands.");

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText("Capture").setCta().onClick(async () => {
        const text = String(textInput.value || "").trim();
        if (!text) {
          new Notice("Text 不能为空。");
          return;
        }
        const title = String(titleInput.value || "").trim();
        const kind = String(kindSelect.value || "note");
        this.close();
        this.plugin.runUiAction(
          () =>
            this.plugin.runDropNoteCommand({
              text,
              title,
              kind,
            }),
          "Capture note modal"
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );

    textInput.focus();
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

class SearchCommandModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Search 炼丹炉" });

    const querySetting = new Setting(contentEl).setName("Query");
    const queryInput = querySetting.controlEl.createEl("textarea");
    queryInput.rows = 4;
    queryInput.placeholder = "Search wiki/sources, concepts, judgments, decisions, and derived pages...";
    queryInput.addClass("furnace-shell-code");

    const limitSetting = new Setting(contentEl).setName("Limit");
    const limitInput = limitSetting.controlEl.createEl("input", { type: "text" });
    limitInput.value = "8";
    limitInput.addClass("furnace-shell-code");

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText("Search").setCta().onClick(async () => {
        const query = String(queryInput.value || "").trim();
        if (!query) {
          new Notice("Search query 不能为空。");
          return;
        }
        const parsedLimit = Number.parseInt(String(limitInput.value || "8"), 10);
        this.close();
        this.plugin.runUiAction(
          () => this.plugin.runShellSearchCommand(query, Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 8),
          "Search modal"
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText("Cancel").onClick(() => {
        this.close();
      })
    );

    queryInput.focus();
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
      .setDesc("Vault-local or absolute launcher path. This vault may point at an external runtime root.")
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
      id: "capture-note",
      name: "Capture Note",
      callback: () => {
        new CaptureNoteModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "search-workspace",
      name: "Search Workspace",
      callback: () => {
        new SearchCommandModal(this.app, this).open();
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
      id: "review-next-page",
      name: "Review Next Page",
      callback: () => {
        this.openReviewNextTransitionPicker();
      },
    });
    this.addCommand({
      id: "batch-review-pages",
      name: "Batch Review Pages",
      callback: () => {
        this.openReviewBatchSuggestionPicker();
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
    this.addCommand({
      id: "apply-all-accepted-low-risk",
      name: "Apply All Accepted Low-Risk Actions",
      callback: () => {
        this.runUiAction(() => this.runApplyAllAcceptedLowRiskCommand(), "Apply All Accepted Low-Risk Actions");
      },
    });
    this.addCommand({
      id: "revert-last-action-batch",
      name: "Revert Last Action Batch",
      callback: () => {
        this.runUiAction(() => this.runRevertLastBatchCommand(), "Revert Last Action Batch");
      },
    });
    this.addCommand({
      id: "open-home-note",
      name: "Open Home Note",
      callback: () => {
        this.runUiAction(() => this.openHomeNote(), "Open Home Note");
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
        "raw",
        "wiki",
        "schema",
        "output",
        ".aiwiki",
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

  parseLineList(value) {
    return Array.from(
      new Set(
        String(value || "")
          .split(/\r?\n/)
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      )
    );
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

  reviewControlList(key) {
    const reviewControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.review_controls
      : null;
    return reviewControls && Array.isArray(reviewControls[key]) ? reviewControls[key] : [];
  }

  executionControlList(key) {
    const executionControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.execution_controls
      : null;
    return executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
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

  inferActionIdFromReceipt(receipt) {
    if (!receipt || typeof receipt !== "object") {
      return "";
    }
    return String(receipt.action_id || "").trim();
  }

  reviewPageControlItems() {
    const pages = this.reviewControlList("pages");
    return this.uniqueContextOptions(
      pages.map((page) => {
        const kind = String(page.kind || "").trim() || "page";
        const status = String(page.status || "").trim() || "unknown";
        const metaText = truncateText(reviewObjectMetaText(page) || "review object", 180);
        return {
          value: page.path,
          label: page.title || page.path || "review-page",
          description: metaText || `${kind} | ${displayCuratedStatus(status)} | review object`,
          pageId: String(page.page_id || ""),
          pagePath: String(page.path || ""),
          pageKind: kind,
          currentStatus: status,
          confidence: String(page.confidence || ""),
          canRefreshReview: Boolean(page.can_refresh_review),
          allowedTransitions: Array.isArray(page.allowed_transitions) ? page.allowed_transitions : [],
          preferredTransitions: Array.isArray(page.preferred_transitions) ? page.preferred_transitions : [],
          defaultTransition: String(page.default_transition || ""),
        };
      }),
      "pagePath"
    );
  }

  nextReviewCandidate() {
    const candidates = this.visibleReviewPageCandidates();
    return candidates.length ? candidates[0] : null;
  }

  reviewKindLabel(kind, count = 1) {
    const normalized = String(kind || "").trim();
    if (normalized === "decision") {
      return count === 1 ? "decision" : "decisions";
    }
    if (normalized === "judgment") {
      return count === 1 ? "judgment" : "judgments";
    }
    return count === 1 ? "page" : "pages";
  }

  commonReviewTransitionOptions(pages) {
    const controls = Array.isArray(pages) ? pages.filter((page) => page && typeof page === "object") : [];
    if (!controls.length) {
      return [];
    }
    const stats = new Map();
    controls.forEach((page) => {
      const seen = new Set();
      this.transitionOptions("page", page).forEach((option) => {
        if (seen.has(option.value)) {
          return;
        }
        seen.add(option.value);
        const current = stats.get(option.value) || {
          value: option.value,
          label: option.label,
          sharedCount: 0,
          preferredCount: 0,
          defaultCount: 0,
        };
        current.label = option.label;
        current.sharedCount += 1;
        if (option.isPreferred) {
          current.preferredCount += 1;
        }
        if (option.isDefault) {
          current.defaultCount += 1;
        }
        stats.set(option.value, current);
      });
    });
    return Array.from(stats.values())
      .filter((option) => option.sharedCount === controls.length)
      .sort((left, right) => {
        if (left.defaultCount !== right.defaultCount) {
          return right.defaultCount - left.defaultCount;
        }
        if (left.preferredCount !== right.preferredCount) {
          return right.preferredCount - left.preferredCount;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  reviewBatchSuggestions() {
    const groups = new Map();
    this.visibleReviewPageCandidates().forEach((page) => {
      const prioritized = this.preferredTransitionOptions("page", page);
      const selectedOptions = prioritized.length
        ? prioritized
        : this.transitionOptions("page", page).filter((option) => option.isDefault).slice(0, 1);
      selectedOptions.forEach((transition) => {
        const kind = String(page.pageKind || "page").trim() || "page";
        const key = `${kind}::${transition.value}`;
        const current = groups.get(key) || {
          key,
          kind,
          status: transition.value,
          transitionLabel: transition.label,
          pages: [],
        };
        current.pages.push(page);
        groups.set(key, current);
      });
    });
    return Array.from(groups.values())
      .filter((group) => group.pages.length >= 2)
      .map((group) => {
        const count = group.pages.length;
        const kindLabel = this.reviewKindLabel(group.kind, count);
        return {
          key: group.key,
          kind: group.kind,
          status: group.status,
          label: `${group.transitionLabel} · ${count} ${kindLabel}`,
          description: `${count} ${kindLabel} share the recommended ${String(group.transitionLabel || "").toLowerCase()} transition.`,
          pagePaths: group.pages.map((page) => page.pagePath).filter(Boolean),
          pages: group.pages,
          statusOptions: this.commonReviewTransitionOptions(group.pages),
        };
      })
      .sort((left, right) => {
        if (right.pagePaths.length !== left.pagePaths.length) {
          return right.pagePaths.length - left.pagePaths.length;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  rewriteControlItems(mode = "review") {
    const proposals = this.reviewControlList("rewrite_proposals");
    return this.uniqueContextOptions(
      proposals
        .filter((proposal) => (mode === "apply" ? Boolean(proposal.can_apply) : Boolean(proposal.can_review)))
        .map((proposal) => {
          const status = String(proposal.status || "").trim() || "unknown";
          const priority = String(proposal.priority || "").trim() || "medium";
          return {
            value: proposal.slug,
            label: proposal.title || proposal.slug || "rewrite-proposal",
            description: `${displayRewriteStatus(status)} | priority ${priority} | score ${proposal.score || 0}`,
            slug: String(proposal.slug || ""),
            status,
            currentStatus: String(proposal.current_status || status),
            proposalPath: String(proposal.proposal_path || ""),
            targetPath: String(proposal.target_path || ""),
            canApply: Boolean(proposal.can_apply),
            canRefreshReview: Boolean(proposal.can_refresh_review),
            allowedTransitions: Array.isArray(proposal.allowed_transitions) ? proposal.allowed_transitions : [],
            preferredTransitions: Array.isArray(proposal.preferred_transitions) ? proposal.preferred_transitions : [],
            defaultTransition: String(proposal.default_transition || ""),
          };
        }),
      "slug"
    );
  }

  actionControlItems(mode = "review") {
    return this.uniqueContextOptions(
      this.executionControlList("actions")
        .filter((action) => {
          if (mode === "apply") {
            return Boolean(action.can_apply);
          }
          if (mode === "revert") {
            return Boolean(action.can_revert);
          }
          return Boolean(action.can_review);
        })
        .map((action) => {
          const status = String(action.status || "").trim() || "unknown";
          const priority = String(action.priority || "").trim() || "medium";
          const primaryPath = String(action.primary_path || "").trim();
          return {
            value: action.action_id,
            label: action.title || action.action_id || "action",
            description: `${displayActionStatus(status)} | priority ${priority}${primaryPath ? ` | ${primaryPath}` : ""}`,
            actionId: String(action.action_id || ""),
            status,
            currentStatus: String(action.current_status || status),
            bundlePath: String(action.bundle_path || ""),
            canRefreshReview: Boolean(action.can_refresh_review),
            allowedTransitions: Array.isArray(action.allowed_transitions) ? action.allowed_transitions : [],
            preferredTransitions: Array.isArray(action.preferred_transitions) ? action.preferred_transitions : [],
            defaultTransition: String(action.default_transition || ""),
          };
        }),
      "actionId"
    );
  }

  archiveControlItems(mode = "apply") {
    return this.uniqueContextOptions(
      this.executionControlList("archives")
        .filter((entry) => (mode === "revert" ? Boolean(entry.can_revert) : Boolean(entry.can_apply)))
        .map((entry) => {
          const candidateStatus = String(entry.candidate_status || "").trim();
          const currentTemperature = String(entry.current_temperature || "").trim();
          return {
            value: entry.entry_id,
            label: entry.title || entry.entry_id || "archive-entry",
            description: `${candidateStatus || currentTemperature || "archive"} | ${entry.source_path || ""}`,
            entryId: String(entry.entry_id || ""),
            allowedTransitions: Array.isArray(entry.allowed_transitions) ? entry.allowed_transitions : [],
            preferredTransitions: Array.isArray(entry.preferred_transitions) ? entry.preferred_transitions : [],
            defaultTransition: String(entry.default_transition || ""),
          };
        }),
      "entryId"
    );
  }

  actionControlsById() {
    const controls = this.executionControlList("actions");
    return new Map(
      controls
        .filter((action) => action && typeof action === "object" && String(action.action_id || "").trim())
        .map((action) => [String(action.action_id || "").trim(), action])
    );
  }

  archiveControlsById() {
    const controls = this.executionControlList("archives");
    return new Map(
      controls
        .filter((entry) => entry && typeof entry === "object" && String(entry.entry_id || "").trim())
        .map((entry) => [String(entry.entry_id || "").trim(), entry])
    );
  }

  transitionLabel(controlType, transition) {
    if (controlType === "page") {
      return displayCuratedStatus(transition);
    }
    if (controlType === "rewrite") {
      return displayRewriteStatus(transition);
    }
    if (controlType === "action") {
      return displayActionStatus(transition);
    }
    if (controlType === "archive") {
      return transition === "revert" ? "Revert archive" : "Apply archive";
    }
    return String(transition || "transition");
  }

  transitionOptions(controlType, control) {
    if (!control || typeof control !== "object") {
      return [];
    }
    const allowed = Array.isArray(control.allowedTransitions || control.allowed_transitions)
      ? (control.allowedTransitions || control.allowed_transitions)
      : [];
    const preferredSet = new Set(
      (Array.isArray(control.preferredTransitions || control.preferred_transitions)
        ? (control.preferredTransitions || control.preferred_transitions)
        : []
      ).map((item) => String(item || "").trim()).filter(Boolean)
    );
    const defaultTransition = String(control.defaultTransition || control.default_transition || "").trim();
    return allowed
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .map((value) => ({
        value,
        label: this.transitionLabel(controlType, value),
        description: preferredSet.has(value) ? "preferred transition" : "allowed transition",
        isDefault: value === defaultTransition,
        isPreferred: preferredSet.has(value),
      }))
      .sort((left, right) => {
        if (left.isDefault !== right.isDefault) {
          return left.isDefault ? -1 : 1;
        }
        if (left.isPreferred !== right.isPreferred) {
          return left.isPreferred ? -1 : 1;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  preferredTransitionOptions(controlType, control) {
    return this.transitionOptions(controlType, control).filter((option) => option.isPreferred).slice(0, 2);
  }

  manualReviewOption(controlType) {
    const labelMap = {
      page: "Manual review...",
      rewrite: "Manual rewrite review...",
      action: "Manual action review...",
    };
    return {
      value: "__manual__",
      label: labelMap[controlType] || "Manual review...",
      description: "keep current status and capture note / confidence in the full form",
      isManual: true,
      isPreferred: false,
      isDefault: false,
    };
  }

  openTransitionPicker({ title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice }) {
    const transitionOptions = this.transitionOptions(controlType, control);
    if (!transitionOptions.length && typeof onManual !== "function") {
      if (emptyNotice) {
        new Notice(emptyNotice);
      }
      if (typeof onFallback === "function") {
        onFallback();
      }
      return;
    }
    if (!transitionOptions.length && typeof onManual === "function") {
      onManual();
      return;
    }
    if (transitionOptions.length === 1 && typeof onManual !== "function") {
      onSubmit(transitionOptions[0].value);
      return;
    }
    const options = transitionOptions.slice();
    if (typeof onManual === "function") {
      options.push(this.manualReviewOption(controlType));
    }
    this.openContextPicker({
      title,
      description,
      submitLabel: "Use",
      options,
      onSubmit: (option) => {
        if (option && option.isManual && typeof onManual === "function") {
          onManual();
          return;
        }
        onSubmit(option.value);
      },
    });
  }

  async runReviewPageTransition(pagePath, status) {
    await this.runCliAction(`Review Page: ${status}`, "review-page", [pagePath, "--status", status]);
  }

  async runReviewPageBatchTransition(pagePaths, status, note = "", confidence = "") {
    const normalizedPaths = Array.isArray(pagePaths)
      ? Array.from(new Set(pagePaths.map((pagePath) => String(pagePath || "").trim()).filter(Boolean)))
      : [];
    if (!normalizedPaths.length) {
      throw new Error("Batch review requires at least one page path.");
    }
    const args = ["--batch", ...normalizedPaths, "--status", status];
    this.appendOptionalArg(args, "--note", note);
    this.appendOptionalArg(args, "--confidence", confidence);
    await this.runCliAction(`Batch Review: ${status}`, "review-page", args);
  }

  async runReviewRewriteTransition(slug, status) {
    await this.runCliAction(`Review Rewrite: ${slug}`, "review-rewrite", [slug, "--status", status]);
  }

  async runReviewActionTransition(actionId, status) {
    await this.runCliAction(`Review Action: ${actionId}`, "review-action", [actionId, "--status", status]);
  }

  visibleReviewPageCandidates() {
    return this.reviewPageControlItems();
  }

  visibleRewriteCandidates() {
    return this.rewriteControlItems("review");
  }

  visibleActionCandidates(mode = "review") {
    return this.actionControlItems(mode);
  }

  visibleArchiveCandidates(mode = "apply") {
    return this.archiveControlItems(mode);
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

  async runShellSearchCommand(query, limit = 8) {
    const normalizedQuery = String(query || "").trim();
    if (!normalizedQuery) {
      new Notice("Search query 不能为空。");
      return;
    }
    const parsedLimit = Number.parseInt(String(limit || 8), 10);
    await this.runPluginCommand(
      `Search: ${truncateText(normalizedQuery, 48)}`,
      ["search", normalizedQuery, "--limit", String(Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 8)],
      { refreshAfter: false, notice: false }
    );
    await this.loadShellSummaryFromDisk();
    new Notice(`Search completed: ${truncateText(normalizedQuery, 60)}`);
  }

  async runApplyAllAcceptedLowRiskCommand() {
    await this.runCliAction("Apply All Accepted Low-Risk", "apply-action", ["--all-accepted-low-risk"]);
  }

  async runRevertLastBatchCommand() {
    await this.runCliAction("Revert Last Action Batch", "revert-action", ["--last-batch"]);
  }

  async openHomeNote() {
    await this.openWorkspacePath("HOME.md");
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

  async runDropNoteCommand({ text, title, kind }) {
    const args = ["drop-note", "--text", text];
    if (title) {
      args.push("--title", title);
    }
    args.push("--kind", kind || "note");
    await this.runPluginCommand(`Capture Note: ${truncateText(title || text, 48)}`, args, { refreshAfter: true });
  }

  async runCliAction(label, command, args = []) {
    await this.runPluginCommand(label, [command, ...args], { refreshAfter: true });
  }

  async runLauncherCommand(fullCommandStr, label = "Suggested Action") {
    // Extract CLI subcommand+args from a full command string like:
    //   "PYTHONPATH=src python3 -m aiwiki.cli --root . review-action foo --status accepted"
    // The launcher already sets PYTHONPATH and --root, so we strip the prefix.
    let trimmed = String(fullCommandStr || "").trim();
    const prefixPattern = /^(?:PYTHONPATH=\S+\s+)?(?:python3?\s+-m\s+aiwiki\.cli\s+)?(?:--root\s+\S+\s+)?/;
    trimmed = trimmed.replace(prefixPattern, "").trim();
    if (!trimmed) {
      new Notice(`Cannot parse command: ${truncateText(fullCommandStr, 80)}`);
      return;
    }
    // Simple shell-like split respecting double quotes
    const args = [];
    let current = "";
    let inQuote = false;
    for (let i = 0; i < trimmed.length; i++) {
      const ch = trimmed[i];
      if (ch === '"') {
        inQuote = !inQuote;
      } else if (ch === " " && !inQuote) {
        if (current) {
          args.push(current);
          current = "";
        }
      } else {
        current += ch;
      }
    }
    if (current) {
      args.push(current);
    }
    await this.runPluginCommand(label, args, { refreshAfter: true });
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
      description: "Prefer an explicit review control object before falling back to manual page entry.",
      keyName: "pagePath",
      options,
      emptyNotice: "当前没有可见的 review backlog 条目，已回退到手动表单。",
      onFallback: () => this.openReviewPageModal(),
      onSubmit: (option) => this.openReviewPageTransitionPicker(option),
    });
  }

  openReviewNextTransitionPicker() {
    const nextReview = this.nextReviewCandidate();
    if (!nextReview) {
      new Notice("当前没有可 review 的页面。");
      return;
    }
    this.openReviewPageTransitionPicker(nextReview);
  }

  openReviewPageBatchModal(prefill = {}) {
    const pagePaths = Array.isArray(prefill.pagePaths) ? prefill.pagePaths : [];
    const statusOptions = Array.isArray(prefill.statusOptions) ? prefill.statusOptions : [];
    const normalizedStatusOptions = statusOptions.map((option) => ({
      value: option.value,
      label: option.label || this.transitionLabel("page", option.value),
    }));
    const statusField = normalizedStatusOptions.length
      ? {
          key: "status",
          label: "Status",
          required: true,
          kind: "select",
          initialValue: prefill.status || normalizedStatusOptions[0].value || "",
          options: normalizedStatusOptions,
        }
      : {
          key: "status",
          label: "Status",
          required: true,
          placeholder: "tracking / needs-revisit / approved ...",
          initialValue: prefill.status || "",
        };
    this.openStructuredCommandModal({
      title: "Batch Review Pages",
      description: prefill.description || "Advance multiple review pages that share a safe common transition.",
      submitLabel: "Run batch",
      fields: [
        {
          key: "pages",
          label: "Page paths",
          required: true,
          kind: "textarea",
          rows: 6,
          placeholder: "wiki/judgments/... (one per line)",
          initialValue: pagePaths.join("\n"),
        },
        statusField,
        {
          key: "note",
          label: "Note",
          kind: "textarea",
          rows: 4,
          placeholder: "Optional shared batch note",
          initialValue: prefill.note || "",
        },
        {
          key: "confidence",
          label: "Confidence",
          placeholder: "Optional shared confidence override",
          initialValue: prefill.confidence || "",
        },
      ],
      onSubmit: async (values) => {
        const paths = this.parseLineList(values.pages);
        if (!paths.length) {
          throw new Error("Batch review requires at least one page path.");
        }
        await this.runReviewPageBatchTransition(paths, values.status, values.note, values.confidence);
      },
    });
  }

  openReviewBatchSuggestionPicker() {
    const suggestions = this.reviewBatchSuggestions();
    if (!suggestions.length) {
      new Notice("当前没有共享推荐状态的批量 review 建议。");
      return;
    }
    if (suggestions.length === 1) {
      this.openReviewPageBatchModal(suggestions[0]);
      return;
    }
    this.openContextPicker({
      title: "Pick Batch Review",
      description: "Batch review is only offered when multiple pages share the same preferred or default transition.",
      submitLabel: "Batch review",
      options: suggestions.map((suggestion) => ({
        value: suggestion.key,
        label: suggestion.label,
        description: suggestion.description,
        suggestion,
      })),
      onSubmit: (option) => this.openReviewPageBatchModal(option.suggestion || option),
    });
  }

  openReviewRewriteContextPicker(options = this.visibleRewriteCandidates()) {
    this.openContextAwareAction({
      title: "Pick Rewrite Context",
      description: "Prefer an explicit rewrite proposal object before falling back to manual slug entry.",
      keyName: "slug",
      options,
      emptyNotice: "当前没有可见的 concept context，已回退到手动表单。",
      onFallback: () => this.openReviewRewriteModal(),
      onSubmit: (option) => this.openReviewRewriteTransitionPicker(option),
    });
  }

  openReviewActionContextPicker(options = this.visibleActionCandidates("review")) {
    this.openContextAwareAction({
      title: "Pick Review Action",
      description: "Prefer an explicit action control object before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openReviewActionModal(),
      onSubmit: (option) => this.openReviewActionTransitionPicker(option),
    });
  }

  openApplyArchiveContextPicker(options = this.visibleArchiveCandidates("apply")) {
    this.openContextAwareAction({
      title: "Pick Archive Target",
      description: "Prefer an explicit archive control object before falling back to manual entry id.",
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
      description: "Prefer an explicit archive control object before falling back to manual entry id.",
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
      description: "Prefer an explicit action control object before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openApplyActionModal(),
      onSubmit: (option) => this.openApplyActionModal({ actionId: option.actionId || option.value || "", bundle: option.bundlePath || "" }),
    });
  }

  openRevertActionContextPicker(options = this.visibleActionCandidates("revert")) {
    this.openContextAwareAction({
      title: "Pick Revert Action",
      description: "Prefer an explicit action control object before falling back to manual action id entry.",
      keyName: "actionId",
      options,
      emptyNotice: "当前没有可见的 machine-memory action context，已回退到手动表单。",
      onFallback: () => this.openRevertActionModal(),
      onSubmit: (option) => this.openRevertActionModal({ actionId: option.actionId || option.value || "" }),
    });
  }

  openReviewPageTransitionPicker(control) {
    const pagePath = String(control.pagePath || control.path || control.value || "").trim();
    const currentStatus = String(control.currentStatus || control.current_status || control.status || "").trim();
    const confidence = String(control.confidence || "").trim();
    this.openTransitionPicker({
      title: "Pick Review Transition",
      description: "Choose a valid next status for this review page.",
      controlType: "page",
      control,
      emptyNotice: "当前没有显式 review transition，已回退到手动表单。",
      onFallback: () => this.openReviewPageModal({ pagePath, status: currentStatus, confidence }),
      onManual: () => this.openReviewPageModal({ pagePath, status: currentStatus, confidence }),
      onSubmit: (status) => {
        this.runUiAction(
          () => this.runReviewPageTransition(pagePath, status),
          `Review page transition: ${pagePath} -> ${status}`
        );
      },
    });
  }

  openReviewRewriteTransitionPicker(control) {
    const slug = String(control.slug || control.value || "").trim();
    const currentStatus = String(control.currentStatus || control.current_status || control.status || "").trim();
    this.openTransitionPicker({
      title: "Pick Rewrite Transition",
      description: "Choose a valid next status for this rewrite proposal.",
      controlType: "rewrite",
      control,
      emptyNotice: "当前没有显式 rewrite transition，已回退到手动表单。",
      onFallback: () => this.openReviewRewriteModal({ slug, status: currentStatus }),
      onManual: () => this.openReviewRewriteModal({ slug, status: currentStatus }),
      onSubmit: (status) => {
        this.runUiAction(
          () => this.runReviewRewriteTransition(slug, status),
          `Review rewrite transition: ${slug} -> ${status}`
        );
      },
    });
  }

  openReviewActionTransitionPicker(control) {
    const actionId = String(control.actionId || control.action_id || control.value || "").trim();
    const currentStatus = String(control.currentStatus || control.current_status || control.status || "").trim();
    this.openTransitionPicker({
      title: "Pick Action Transition",
      description: "Choose a valid next status for this machine-memory action.",
      controlType: "action",
      control,
      emptyNotice: "当前没有显式 action transition，已回退到手动表单。",
      onFallback: () => this.openReviewActionModal({ actionId, status: currentStatus }),
      onManual: () => this.openReviewActionModal({ actionId, status: currentStatus }),
      onSubmit: (status) => {
        this.runUiAction(
          () => this.runReviewActionTransition(actionId, status),
          `Review action transition: ${actionId} -> ${status}`
        );
      },
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

  renderGettingStartedSection(container) {
    const section = container.createDiv({ cls: "furnace-shell-section" });
    section.createEl("h3", { text: "Start Here" });
    section.createDiv({
      cls: "furnace-shell-meta",
      text: "Obsidian Product Shell 与 launcher CLI 共用同一个 runtime：Ask 两边都能跑，投料可走 Capture Note / raw/inbox / drop-*。",
    });
    const steps = section.createEl("ol");
    steps.createEl("li", { text: "先点 Refresh，确认 shell-summary 已生成。" });
    steps.createEl("li", { text: "在 Obsidian 里用 Capture Note，或在终端里用 drop-note / drop-url / drop-pdf / drop-image / drop-repo 投料。" });
    steps.createEl("li", { text: "需要提问时用 Ask modal，或运行 ./scripts/aiwiki-launcher.sh ask ..." });
    steps.createEl("li", { text: "写操作遵守 single writer：不要同时在 Obsidian 和终端里各跑一个 compile / nightly / apply / revert。" });
    this.renderActionButtons(section, [
      { label: "Capture Note", cta: true, onClick: async () => new CaptureNoteModal(this.app, this).open() },
      { label: "Ask", onClick: async () => new AskCommandModal(this.app, this).open() },
      { label: "Compile", onClick: async () => this.runCompileCommand() },
    ]);
  }

  renderFurnaceCenter(contentEl) {
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: "Furnace Center" });

    if (!this.repoState.valid) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: `Vault runtime unavailable. Missing scaffold or launcher: ${this.repoState.missingPaths.join(", ")}`,
      });
      contentEl.createDiv({
        cls: "furnace-shell-meta",
        text: "Expected a vault scaffold (`raw/wiki/schema/output/.aiwiki`) plus an executable launcher script.",
      });
      return;
    }

    this.renderActionButtons(contentEl, [
      { label: "Home", onClick: async () => this.openHomeNote() },
      { label: "Refresh", cta: true, onClick: async () => this.refreshShellSummaryCommand() },
      { label: "Compile", onClick: async () => this.runCompileCommand() },
      { label: "Capture Note", onClick: async () => new CaptureNoteModal(this.app, this).open() },
      { label: "Ask", onClick: async () => new AskCommandModal(this.app, this).open() },
      { label: "Search", onClick: async () => new SearchCommandModal(this.app, this).open() },
      { label: "Nightly", onClick: async () => this.runNightlyCommand() },
      { label: "Set Protocol", onClick: async () => new ProtocolCommandModal(this.app, this).open() },
      { label: "Review Center", onClick: async () => this.openReviewCenterView() },
      { label: "Execution Center", onClick: async () => this.openExecutionCenterView() },
      { label: "Recent Runs", onClick: async () => this.openRecentRunsView() },
    ]);
    this.renderGettingStartedSection(contentEl);

    if (!this.shellSummary) {
      contentEl.createDiv({
        cls: "furnace-shell-empty",
        text: "shell-summary.json 尚未生成。先运行 Refresh / Compile / Nightly 之一。",
      });
      return;
    }

    const review = this.shellSummary.review_backlog_counts || {};
    const aging = this.shellSummary.aging_summary || {};
    const judgmentAssets = this.shellSummary.judgment_assets || {};
    const judgmentCounts = judgmentAssets.counts || {};
    const reviewControlObjects = this.reviewControlList("pages");
    const reviewControlsByPath = new Map(
      reviewControlObjects
        .filter((page) => page && typeof page === "object" && String(page.path || "").trim())
        .map((page) => [String(page.path || "").trim(), page])
    );
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
    summarySection.createEl("div", {
      cls: "furnace-shell-meta",
      text: `Judgment assets ${judgmentCounts.pages || 0} | strong assets ${judgmentCounts.strong_assets || 0} | attention ${judgmentCounts.attention_pages || 0} | citation drift ${judgmentCounts.citation_drift || 0}`,
    });

    const knowledgeStats = this.shellSummary.knowledge_stats || {};
    if (knowledgeStats.source_nodes || knowledgeStats.concept_nodes) {
      const statsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      statsSection.createEl("h3", { text: "Knowledge Base" });
      this.renderCardGrid(statsSection, [
        { label: "Sources", value: knowledgeStats.source_nodes || 0 },
        { label: "Concepts", value: knowledgeStats.concept_nodes || 0 },
        { label: "Judgments", value: knowledgeStats.judgments || 0 },
        { label: "Decisions", value: knowledgeStats.decisions || 0 },
        { label: "Edges", value: knowledgeStats.edge_total || 0 },
        { label: "Causal Edges", value: knowledgeStats.concept_causal_edges || 0 },
        { label: "Term Index", value: knowledgeStats.term_index || 0 },
      ]);
    }

    const dashboardData = this.shellSummary.dashboard || {};
    const dashboardCards = Array.isArray(dashboardData.cards) ? dashboardData.cards : [];
    if (dashboardCards.length) {
      const dashSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      dashSection.createEl("h3", { text: "Dashboard" });
      this.renderCardGrid(dashSection, dashboardCards.map((c) => ({
        label: c.label || c.id || "card",
        value: c.value != null ? c.value : 0,
      })));
    }

    const driftWarnings = Array.isArray(this.shellSummary.drift_warnings) ? this.shellSummary.drift_warnings : [];
    if (driftWarnings.length) {
      const driftSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      driftSection.createEl("h3", { text: "⚠️ Drift Warnings" });
      const driftList = driftSection.createEl("ul", { cls: "furnace-shell-list" });
      driftWarnings.slice(0, 8).forEach((warning) => {
        const item = driftList.createEl("li");
        if (typeof warning === "string") {
          item.createEl("span", { text: warning });
        } else {
          item.createEl("strong", { text: warning.title || warning.kind || "drift" });
          item.createDiv({ cls: "furnace-shell-meta", text: warning.message || warning.reason || JSON.stringify(warning) });
        }
      });
    }

    const suggestedActions = Array.isArray(this.shellSummary.suggested_next_actions) ? this.shellSummary.suggested_next_actions : [];
    if (suggestedActions.length) {
      const suggestedSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      suggestedSection.createEl("h3", { text: "Suggested Next Actions" });
      const suggestedList = suggestedSection.createEl("ul", { cls: "furnace-shell-list" });
      suggestedActions.slice(0, 6).forEach((action) => {
        const item = suggestedList.createEl("li");
        item.createEl("strong", { text: action.title || "action" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${action.kind || "unknown"} | ${action.reason || ""}`,
        });
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        if (action.path) {
          const openButton = actions.createEl("button", { text: "Open" });
          openButton.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(action.path), `Open suggested: ${action.path}`);
          });
        }
        if (action.command) {
          const runButton = actions.createEl("button", { text: "Run" });
          runButton.addEventListener("click", () => {
            this.runUiAction(() => this.runLauncherCommand(action.command, `Suggested: ${action.title || "action"}`), `Run suggested: ${action.title || "action"}`);
          });
        }
      });
    }

    const searchResults = this.shellSummary.search_results || {};
    const searchItems = Array.isArray(searchResults.results) ? searchResults.results : [];
    if (String(searchResults.query || "").trim()) {
      const searchSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      searchSection.createEl("h3", { text: "Search Results" });
      searchSection.createDiv({
        cls: "furnace-shell-meta",
        text: `Query: ${searchResults.query || ""} | results ${searchResults.result_count || 0}`,
      });
      if (!searchItems.length) {
        searchSection.createDiv({ cls: "furnace-shell-empty", text: "No matching pages in the compiled workspace." });
      } else {
        const searchList = searchSection.createEl("ul", { cls: "furnace-shell-list" });
        searchItems.slice(0, 8).forEach((result) => {
          const item = searchList.createEl("li");
          item.createEl("strong", { text: result.title || result.path || "result" });
          item.createDiv({
            cls: "furnace-shell-meta",
            text: `${result.kind || "page"} | score ${result.score || 0} | ${result.path || ""}`,
          });
          if (result.preview) {
            item.createDiv({ cls: "furnace-shell-meta", text: truncateText(result.preview, 180) });
          }
          if (result.path) {
            const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
            const openBtn = actions.createEl("button", { text: "Open" });
            openBtn.addEventListener("click", () => {
              this.runUiAction(() => this.openWorkspacePath(result.path), `Open search result: ${result.path}`);
            });
          }
        });
      }
    }

    const routeTelemetry = this.shellSummary.route_telemetry || {};
    const routeEntries = Array.isArray(routeTelemetry.entries) ? routeTelemetry.entries : [];
    if (routeEntries.length) {
      const routeSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      routeSection.createEl("h3", { text: "Recent Queries" });
      const routeList = routeSection.createEl("ul", { cls: "furnace-shell-list" });
      routeEntries.slice(0, 5).forEach((entry) => {
        const item = routeList.createEl("li");
        item.createEl("strong", { text: truncateText(entry.question_preview || "query", 120) });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${entry.protocol || "general"} | ${entry.selected_strategy || "default"} | ${entry.occurred_at || ""}`,
        });
      });
    }

    const judgmentSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    judgmentSection.createEl("h3", { text: "Judgment Focus" });
    this.renderCardGrid(judgmentSection, [
      { label: "Strong Assets", value: judgmentCounts.strong_assets || 0 },
      { label: "Attention Pages", value: judgmentCounts.attention_pages || 0 },
      { label: "Missing Counter Evidence", value: judgmentCounts.missing_counter_evidence || 0 },
      { label: "Missing Invalidation", value: judgmentCounts.missing_invalidation || 0 },
      { label: "Missing Next Signals", value: judgmentCounts.missing_next_signals || 0 },
      { label: "Citation Drift", value: judgmentCounts.citation_drift || 0 },
    ]);
    const focusPages = Array.isArray(judgmentAssets.attention_pages) ? judgmentAssets.attention_pages : [];
    if (!focusPages.length) {
      judgmentSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 judgment asset focus object。" });
    } else {
      const list = judgmentSection.createEl("ul", { cls: "furnace-shell-list" });
      focusPages.slice(0, 8).forEach((page) => {
        const item = list.createEl("li");
        const reviewControl = reviewControlsByPath.get(String(page.path || "").trim());
        item.createEl("strong", { text: page.title || page.path || "judgment-asset" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: reviewObjectMetaText(reviewControl || page) || "judgment asset",
        });
        if (page.latest_review_history_entry) {
          item.createDiv({
            cls: "furnace-shell-meta",
            text: truncateText(page.latest_review_history_entry, 180),
          });
        }
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const openButton = actions.createEl("button", { text: "Open" });
        openButton.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(page.path), `Open judgment focus page: ${page.path}`);
        });
        const reviewButton = actions.createEl("button", { text: "Review" });
        reviewButton.addEventListener("click", () => {
          this.runUiAction(
            () => (
              reviewControl
                ? this.openReviewPageTransitionPicker(reviewControl)
                : this.openReviewPageModal({ pagePath: page.path, status: page.current_status || page.status || "", confidence: page.confidence || "" })
            ),
            `Review judgment focus page: ${page.path}`
          );
        });
      });
    }

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
      ["judgment_assets_markdown", "Judgment Assets"],
      ["cognitive_history_markdown", "Cognitive History"],
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
        text: `Vault runtime unavailable. Missing scaffold or launcher: ${this.repoState.missingPaths.join(", ")}`,
      });
      return;
    }

    this.renderActionButtons(contentEl, [
      { label: "Refresh", cta: true, onClick: async () => this.refreshShellSummaryCommand() },
      { label: "Furnace Center", onClick: async () => this.openFurnaceCenterView() },
      { label: "Execution Center", onClick: async () => this.openExecutionCenterView() },
    ]);
    this.renderActionButtons(contentEl, [
      { label: "Review Next", onClick: async () => this.openReviewNextTransitionPicker() },
      { label: "Batch Review", onClick: async () => this.openReviewBatchSuggestionPicker() },
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
    const judgmentAssets = this.shellSummary.judgment_assets || {};
    const judgmentCounts = judgmentAssets.counts || {};
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

    const nextReview = this.nextReviewCandidate();
    const batchSuggestions = this.reviewBatchSuggestions();

    const nextSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    nextSection.createEl("h3", { text: "Next Review" });
    if (!nextReview) {
      nextSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有显式 next review item。" });
    } else {
      const nextCard = nextSection.createDiv({ cls: "furnace-shell-card" });
      nextCard.createEl("strong", { text: nextReview.label || nextReview.pagePath || "review-page" });
      nextCard.createDiv({
        cls: "furnace-shell-meta",
        text: nextReview.description || "review object",
      });
      if (nextReview.pagePath) {
        nextCard.createDiv({ cls: "furnace-shell-meta furnace-shell-code", text: nextReview.pagePath });
      }
      const actions = nextCard.createDiv({ cls: "furnace-shell-inline-actions" });
      const openButton = actions.createEl("button", { text: "Open page" });
      openButton.addEventListener("click", () => {
        this.runUiAction(() => this.openWorkspacePath(nextReview.pagePath), `Open next review page: ${nextReview.pagePath}`);
      });
      this.preferredTransitionOptions("page", nextReview).forEach((transition) => {
        const transitionButton = actions.createEl("button", { text: transition.label });
        transitionButton.addEventListener("click", () => {
          this.runUiAction(
            () => this.runReviewPageTransition(nextReview.pagePath, transition.value),
            `Next review quick action: ${nextReview.pagePath} -> ${transition.value}`
          );
        });
      });
      const moreButton = actions.createEl("button", { text: "More" });
      moreButton.addEventListener("click", () => {
        this.runUiAction(() => this.openReviewPageTransitionPicker(nextReview), `Open next review transitions: ${nextReview.pagePath}`);
      });
    }

    const batchSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    batchSection.createEl("h3", { text: "Batch Suggestions" });
    if (!batchSuggestions.length) {
      batchSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有共享推荐状态的批量 review 组。" });
    } else {
      const list = batchSection.createEl("ul", { cls: "furnace-shell-list" });
      batchSuggestions.slice(0, 6).forEach((suggestion) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: suggestion.label });
        item.createDiv({ cls: "furnace-shell-meta", text: suggestion.description });
        const preview = suggestion.pages
          .slice(0, 3)
          .map((page) => page.label || page.pagePath)
          .filter(Boolean)
          .join(" · ");
        if (preview) {
          item.createDiv({ cls: "furnace-shell-meta", text: truncateText(preview, 180) });
        }
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const batchButton = actions.createEl("button", { text: "Batch review" });
        batchButton.addEventListener("click", () => {
          this.runUiAction(() => this.openReviewPageBatchModal(suggestion), `Open batch review modal: ${suggestion.key}`);
        });
        const openFirstButton = actions.createEl("button", { text: "Open first" });
        openFirstButton.addEventListener("click", () => {
          const firstPath = suggestion.pagePaths[0] || "";
          if (!firstPath) {
            return;
          }
          this.runUiAction(() => this.openWorkspacePath(firstPath), `Open first batch review page: ${firstPath}`);
        });
      });
    }

    const judgmentSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    judgmentSection.createEl("h3", { text: "Judgment Assets" });
    this.renderCardGrid(judgmentSection, [
      { label: "Strong Assets", value: judgmentCounts.strong_assets || 0 },
      { label: "Attention Pages", value: judgmentCounts.attention_pages || 0 },
      { label: "Missing Counter Evidence", value: judgmentCounts.missing_counter_evidence || 0 },
      { label: "Missing Invalidation", value: judgmentCounts.missing_invalidation || 0 },
      { label: "Missing Review History", value: judgmentCounts.missing_review_history || 0 },
      { label: "Citation Drift", value: judgmentCounts.citation_drift || 0 },
    ]);

    const reviewControlObjects = this.reviewControlList("pages");
    const decisionControlObjects = this.reviewControlList("decision_pages").length
      ? this.reviewControlList("decision_pages")
      : reviewControlObjects.filter((page) => String(page.kind || "").trim() === "decision");
    const judgmentControlObjects = this.reviewControlList("judgment_pages").length
      ? this.reviewControlList("judgment_pages")
      : reviewControlObjects.filter((page) => String(page.kind || "").trim() === "judgment");
    const reviewControlsByPath = new Map(
      reviewControlObjects
        .filter((page) => page && typeof page === "object" && String(page.path || "").trim())
        .map((page) => [String(page.path || "").trim(), page])
    );
    const renderReviewObjectSection = (title, pages, emptyText) => {
      const section = contentEl.createDiv({ cls: "furnace-shell-section" });
      section.createEl("h3", { text: title });
      if (!pages.length) {
        section.createDiv({ cls: "furnace-shell-empty", text: emptyText });
        return;
      }
      const list = section.createEl("ul", { cls: "furnace-shell-list" });
      pages.slice(0, 10).forEach((page) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: page.title || page.path || "review-page" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: reviewObjectMetaText(page) || "review-object",
        });
        if (page.latest_review_history_entry) {
          item.createDiv({
            cls: "furnace-shell-meta",
            text: truncateText(page.latest_review_history_entry, 180),
          });
        }
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const openButton = actions.createEl("button", { text: "Open page" });
        openButton.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(page.path), `Open review control page: ${page.path}`);
        });
        if (page.can_refresh_review) {
          const refreshButton = actions.createEl("button", { text: "Re-review" });
          refreshButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.openReviewPageModal({ pagePath: page.path, status: page.current_status || page.status || "", confidence: page.confidence || "" }),
              `Re-review control page: ${page.path}`
            );
          });
        }
        this.preferredTransitionOptions("page", page).forEach((transition) => {
          const transitionButton = actions.createEl("button", { text: transition.label });
          transitionButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.runReviewPageTransition(page.path, transition.value),
              `Review control quick action: ${page.path} -> ${transition.value}`
            );
          });
        });
        if (Array.isArray(page.allowed_transitions) && page.allowed_transitions.length) {
          const reviewButton = actions.createEl("button", { text: "More" });
          reviewButton.addEventListener("click", () => {
            this.runUiAction(() => this.openReviewPageTransitionPicker(page), `Review control page: ${page.path}`);
          });
        }
      });
    };
    renderReviewObjectSection("Decision Objects", decisionControlObjects, "当前没有显式 decision review object。");
    renderReviewObjectSection("Judgment Objects", judgmentControlObjects, "当前没有显式 judgment review object。");

    const rewriteControlObjects = this.reviewControlList("rewrite_proposals");
    const rewriteSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    rewriteSection.createEl("h3", { text: "Rewrite Proposal Objects" });
    if (!rewriteControlObjects.length) {
      rewriteSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有显式 rewrite proposal object。" });
    } else {
      const list = rewriteSection.createEl("ul", { cls: "furnace-shell-list" });
      rewriteControlObjects.slice(0, 10).forEach((proposal) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: proposal.title || proposal.slug || "rewrite-proposal" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${displayRewriteStatus(proposal.status)} | priority ${proposal.priority || "medium"} | score ${proposal.score || 0}`,
        });
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        if (proposal.proposal_path) {
          const proposalButton = actions.createEl("button", { text: "Open proposal" });
          proposalButton.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(proposal.proposal_path), `Open rewrite proposal: ${proposal.proposal_path}`);
          });
        }
        if (proposal.target_path) {
          const targetButton = actions.createEl("button", { text: "Open target" });
          targetButton.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(proposal.target_path), `Open rewrite target: ${proposal.target_path}`);
          });
        }
        if (proposal.can_refresh_review) {
          const refreshButton = actions.createEl("button", { text: "Re-review" });
          refreshButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.openReviewRewriteModal({ slug: proposal.slug, status: proposal.current_status || proposal.status || "" }),
              `Re-review rewrite object: ${proposal.slug}`
            );
          });
        }
        this.preferredTransitionOptions("rewrite", proposal).forEach((transition) => {
          const transitionButton = actions.createEl("button", { text: transition.label });
          transitionButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.runReviewRewriteTransition(proposal.slug, transition.value),
              `Rewrite quick action: ${proposal.slug} -> ${transition.value}`
            );
          });
        });
        if (proposal.can_review && Array.isArray(proposal.allowed_transitions) && proposal.allowed_transitions.length) {
          const reviewButton = actions.createEl("button", { text: "More" });
          reviewButton.addEventListener("click", () => {
            this.runUiAction(() => this.openReviewRewriteTransitionPicker(proposal), `Review rewrite object: ${proposal.slug}`);
          });
        }
        if (proposal.can_apply) {
          const applyButton = actions.createEl("button", { text: "Apply rewrite" });
          applyButton.addEventListener("click", () => {
            this.runUiAction(() => this.openApplyRewriteModal({ slug: proposal.slug }), `Apply rewrite object: ${proposal.slug}`);
          });
        }
      });
    }

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
        const reviewControl = reviewControlsByPath.get(String(pagePath || "").trim());
        const openButton = actions.createEl("button", { text: "Open" });
        openButton.addEventListener("click", () => {
          this.runUiAction(() => this.openWorkspacePath(pagePath), `Open aging page: ${pagePath}`);
        });
        const reviewButton = actions.createEl("button", { text: "Review" });
        reviewButton.addEventListener("click", () => {
          this.runUiAction(
            () => (reviewControl ? this.openReviewPageTransitionPicker(reviewControl) : this.openReviewPageModal({ pagePath })),
            `Review aging page: ${pagePath}`
          );
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
        const reviewControl = reviewControlsByPath.get(String(entry.page_path || "").trim());
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
              () => (
                reviewControl
                  ? this.openReviewPageTransitionPicker(reviewControl)
                  : this.openReviewPageModal({ pagePath: entry.page_path, status: entry.status || "" })
              ),
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
      ["judgment_assets_markdown", "Judgment Assets"],
      ["cognitive_history_markdown", "Cognitive History"],
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
      { label: "Apply All Low-Risk", onClick: async () => this.runApplyAllAcceptedLowRiskCommand() },
      { label: "Revert Last Batch", onClick: async () => this.runRevertLastBatchCommand() },
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
    const actionControlsById = this.actionControlsById();
    const archiveControlsById = this.archiveControlsById();
    const actionControlObjects = this.executionControlList("actions");
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

    const planner = this.shellSummary.planner || {};
    const plannerCounts = planner.counts || {};
    const plannerQueue = Array.isArray(planner.priority_queue) ? planner.priority_queue : [];
    const plannerNextAction = planner.next_action || {};
    if (plannerQueue.length || plannerCounts.pending_proposals) {
      const plannerSection = contentEl.createDiv({ cls: "furnace-shell-section" });
      plannerSection.createEl("h3", { text: "Planner Queue" });
      this.renderCardGrid(plannerSection, [
        { label: "Pending Proposals", value: plannerCounts.pending_proposals || 0 },
        { label: "Executed", value: plannerCounts.executed_actions || 0 },
        { label: "Unblocked", value: plannerCounts.unblocked || 0 },
        { label: "Blocked", value: plannerCounts.blocked || 0 },
      ]);
      if (plannerNextAction.action_id) {
        const nextDiv = plannerSection.createDiv({ cls: "furnace-shell-section" });
        nextDiv.createEl("h4", { text: "Next Action" });
        const item = nextDiv.createDiv();
        item.createEl("strong", { text: plannerNextAction.title || plannerNextAction.action_id });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `score: ${plannerNextAction.priority_score || 0} | ${plannerNextAction.action_id || ""}`,
        });
        const nextActions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        const reviewBtn = nextActions.createEl("button", { text: "Review" });
        reviewBtn.addEventListener("click", () => {
          this.runUiAction(
            () => this.openReviewActionModal({ actionId: plannerNextAction.action_id, status: "accepted" }),
            `Review planner next: ${plannerNextAction.action_id}`
          );
        });
      }
      if (plannerQueue.length > 1) {
        const queueList = plannerSection.createEl("ul", { cls: "furnace-shell-list" });
        plannerQueue.slice(0, 8).forEach((queueItem) => {
          const item = queueList.createEl("li");
          item.createEl("strong", { text: queueItem.title || queueItem.action_id || "action" });
          item.createDiv({
            cls: "furnace-shell-meta",
            text: `score: ${queueItem.priority_score || 0} | ${queueItem.action_id || ""}`,
          });
        });
      }
    }

    const actionObjectsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    actionObjectsSection.createEl("h3", { text: "Action Control Objects" });
    if (!actionControlObjects.length) {
      actionObjectsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有显式 action control object。" });
    } else {
      const list = actionObjectsSection.createEl("ul", { cls: "furnace-shell-list" });
      actionControlObjects.slice(0, 10).forEach((action) => {
        const item = list.createEl("li");
        item.createEl("strong", { text: action.title || action.action_id || "action" });
        item.createDiv({
          cls: "furnace-shell-meta",
          text: `${displayActionStatus(action.status)} | ${action.priority || "medium"} | ${action.primary_path || ""}`,
        });
        const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
        if (action.primary_path) {
          const openPrimary = actions.createEl("button", { text: "Open primary" });
          openPrimary.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(action.primary_path), `Open action primary: ${action.primary_path}`);
          });
        }
        if (action.proposal_path) {
          const openProposal = actions.createEl("button", { text: "Open proposal" });
          openProposal.addEventListener("click", () => {
            this.runUiAction(() => this.openWorkspacePath(action.proposal_path), `Open action proposal: ${action.proposal_path}`);
          });
        }
        if (action.can_refresh_review) {
          const refreshButton = actions.createEl("button", { text: "Re-review" });
          refreshButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.openReviewActionModal({ actionId: action.action_id, status: action.current_status || action.status || "" }),
              `Re-review action object: ${action.action_id}`
            );
          });
        }
        this.preferredTransitionOptions("action", action).forEach((transition) => {
          const transitionButton = actions.createEl("button", { text: transition.label });
          transitionButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.runReviewActionTransition(action.action_id, transition.value),
              `Action quick transition: ${action.action_id} -> ${transition.value}`
            );
          });
        });
        if (action.can_review && Array.isArray(action.allowed_transitions) && action.allowed_transitions.length) {
          const moreButton = actions.createEl("button", { text: "More" });
          moreButton.addEventListener("click", () => {
            this.runUiAction(() => this.openReviewActionTransitionPicker(action), `Review action object: ${action.action_id}`);
          });
        }
        if (action.can_apply) {
          const applyButton = actions.createEl("button", { text: "Apply action" });
          applyButton.addEventListener("click", () => {
            this.runUiAction(
              () => this.openApplyActionModal({ actionId: action.action_id, bundle: action.bundle_path || "" }),
              `Apply action object: ${action.action_id}`
            );
          });
        }
        if (action.can_revert) {
          const revertButton = actions.createEl("button", { text: "Revert action" });
          revertButton.addEventListener("click", () => {
            this.runUiAction(() => this.openRevertActionModal({ actionId: action.action_id }), `Revert action object: ${action.action_id}`);
          });
        }
      });
    }

    const receiptsSection = contentEl.createDiv({ cls: "furnace-shell-section" });
    receiptsSection.createEl("h3", { text: "Recent Receipts" });
    if (!receipts.length) {
      receiptsSection.createDiv({ cls: "furnace-shell-empty", text: "当前没有 recent receipts。" });
    } else {
      const list = receiptsSection.createEl("ul", { cls: "furnace-shell-list" });
      receipts.slice(0, 8).forEach((receipt) => {
        const item = list.createEl("li");
        const actionId = this.inferActionIdFromReceipt(receipt);
        const actionControl = actionControlsById.get(actionId);
        const archiveEntryId = String(receipt.subject_id || "").trim();
        const archiveControl = archiveControlsById.get(archiveEntryId);
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
          if (String(receipt.subject_kind || "") === "material-archive" && archiveControl) {
            if (archiveControl.can_revert || archiveControl.can_apply) {
              const archiveButton = actions.createEl("button", {
                text: archiveControl.can_revert ? "Revert archive" : "Apply archive",
              });
              archiveButton.addEventListener("click", () => {
                this.runUiAction(
                  () =>
                    (archiveControl.can_revert
                      ? this.openRevertArchiveModal({ entryId: archiveControl.entry_id })
                      : this.openApplyArchiveModal({ entryId: archiveControl.entry_id })),
                  `Archive receipt action: ${archiveControl.entry_id}`
                );
              });
            }
          } else if (actionControl) {
            if (actionControl.can_review) {
              const reviewButton = actions.createEl("button", { text: "Review action" });
              reviewButton.addEventListener("click", () => {
                this.runUiAction(() => this.openReviewActionTransitionPicker(actionControl), `Review action from receipt: ${actionId}`);
              });
            }
            if (actionControl.can_revert || actionControl.can_apply) {
              const actionButton = actions.createEl("button", {
                text: actionControl.can_revert ? "Revert action" : "Apply action",
              });
              actionButton.addEventListener("click", () => {
                this.runUiAction(
                  () =>
                    (actionControl.can_revert
                      ? this.openRevertActionModal({ actionId })
                      : this.openApplyActionModal({ actionId, bundle: actionControl.bundle_path || "" })),
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
        const archiveEntryId = String(entry.entry_id || (Array.isArray(entry.source_ids) && entry.source_ids.length ? entry.source_ids[0] : "") || "");
        const archiveControl = archiveControlsById.get(archiveEntryId);
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
        if (["archive-apply", "archive-revert"].includes(String(entry.event_type || "")) && archiveControl) {
          if (archiveControl.can_revert || archiveControl.can_apply) {
            const archiveButton = actions.createEl("button", {
              text: archiveControl.can_revert ? "Revert archive" : "Apply archive",
            });
            archiveButton.addEventListener("click", () => {
              this.runUiAction(
                () =>
                  (archiveControl.can_revert
                    ? this.openRevertArchiveModal({ entryId: archiveControl.entry_id })
                    : this.openApplyArchiveModal({ entryId: archiveControl.entry_id })),
                `Archive event action: ${archiveControl.entry_id}`
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
