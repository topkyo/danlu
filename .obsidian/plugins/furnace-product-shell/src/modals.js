// Modal subclasses (AskCommand, CaptureNote, Protocol, Search, DropUrl,
// DropFile, DropImage, StructuredCommand, ContextPicker).

class AskCommandModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Ask 炼丹炉") });

    const questionSetting = new Setting(contentEl).setName(t("Question"));
    const questionInput = questionSetting.controlEl.createEl("textarea");
    questionInput.rows = 5;
    questionInput.placeholder = t("Enter the research question...");
    questionInput.addClass("furnace-shell-code");

    const formatSetting = new Setting(contentEl).setName(t("Format"));
    const formatSelect = formatSetting.controlEl.createEl("select");
    ["report", "slides", "figure"].forEach((item) => {
      const option = formatSelect.createEl("option", { text: item, value: item });
      option.value = item;
    });
    formatSelect.value = this.plugin.settings.defaultAskFormat;

    const modeSetting = new Setting(contentEl).setName(t("Mode"));
    const modeSelect = modeSetting.controlEl.createEl("select");
    [
      ["ask", "ask"],
      ["run-ask", "run-ask"],
    ].forEach(([value, label]) => {
      const option = modeSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    modeSelect.value = this.plugin.settings.defaultAskMode;

    const protocolSetting = new Setting(contentEl).setName(t("Protocol"));
    const protocolSelect = protocolSetting.controlEl.createEl("select");
    protocolSelect.createEl("option", { text: t("current protocol"), value: "" });
    this.plugin.getAvailableProtocols().forEach((protocol) => {
      const option = protocolSelect.createEl("option", { text: protocol, value: protocol });
      option.value = protocol;
    });

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Run")).setCta().onClick(async () => {
        const question = String(questionInput.value || "").trim();
        if (!question) {
          new Notice(t("Question cannot be empty."));
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
          t("Ask modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
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
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Capture Note") });

    const titleSetting = new Setting(contentEl).setName(t("Title"));
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("Optional note title...");
    titleInput.addClass("furnace-shell-code");

    const kindSetting = new Setting(contentEl).setName(t("Kind"));
    const kindSelect = kindSetting.controlEl.createEl("select");
    [
      ["note", "note"],
      ["transcript", "transcript"],
    ].forEach(([value, label]) => {
      const option = kindSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    kindSelect.value = "note";

    const textSetting = new Setting(contentEl).setName(t("Text"));
    const textInput = textSetting.controlEl.createEl("textarea");
    textInput.rows = 10;
    textInput.placeholder = t("Capture a note, meeting log, or quick observation...");
    textInput.addClass("furnace-shell-code");

    const hint = contentEl.createDiv({ cls: "furnace-shell-meta" });
    hint.setText(t("This writes into raw/inbox through the same launcher/runtime used by CLI commands."));

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Capture")).setCta().onClick(async () => {
        const text = String(textInput.value || "").trim();
        if (!text) {
          new Notice(t("Text cannot be empty."));
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
          t("Capture note modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
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
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Set Protocol") });

    const setting = new Setting(contentEl).setName(t("Protocol"));
    const select = setting.controlEl.createEl("select");
    this.plugin.getAvailableProtocols().forEach((protocol) => {
      const option = select.createEl("option", { text: protocol, value: protocol });
      option.value = protocol;
    });
    select.value = this.plugin.getActiveProtocol();

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Apply")).setCta().onClick(async () => {
        const protocol = String(select.value || "").trim();
        if (!protocol) {
          new Notice(t("Choose a protocol."));
          return;
        }
        this.close();
        this.plugin.runUiAction(() => this.plugin.runProtocolSetCommand(protocol), t("Set protocol modal"));
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
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
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Search 炼丹炉") });

    const querySetting = new Setting(contentEl).setName(t("Query"));
    const queryInput = querySetting.controlEl.createEl("textarea");
    queryInput.rows = 4;
    queryInput.placeholder = t("Search wiki/sources, concepts, judgments, decisions, and derived pages...");
    queryInput.addClass("furnace-shell-code");

    const limitSetting = new Setting(contentEl).setName(t("Limit"));
    const limitInput = limitSetting.controlEl.createEl("input", { type: "text" });
    limitInput.value = "8";
    limitInput.addClass("furnace-shell-code");

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Search")).setCta().onClick(async () => {
        const query = String(queryInput.value || "").trim();
        if (!query) {
          new Notice(t("Search query cannot be empty."));
          return;
        }
        const parsedLimit = Number.parseInt(String(limitInput.value || "8"), 10);
        this.close();
        this.plugin.runUiAction(
          () => this.plugin.runShellSearchCommand(query, Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 8),
          t("Search modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
        this.close();
      })
    );

    queryInput.focus();
  }
}

class DropUrlModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Drop URL") });

    const description = contentEl.createDiv({ cls: "furnace-shell-meta" });
    description.setText(t("Drop this web page into raw/inbox."));

    const sourceSetting = new Setting(contentEl).setName(t("Web URL"));
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.placeholder = "https://example.com/article";
    sourceInput.addClass("furnace-shell-code");

    const titleSetting = new Setting(contentEl).setName(t("Title"));
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("Optional note title...");
    titleInput.addClass("furnace-shell-code");

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Drop URL")).setCta().onClick(async () => {
        const url = String(sourceInput.value || "").trim();
        if (!url) {
          new Notice(t("URL cannot be empty."));
          return;
        }
        const title = String(titleInput.value || "").trim();
        this.close();
        this.plugin.runUiAction(
          () => this.plugin.runDropUrlCommand({ url, title }),
          t("Drop URL modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
        this.close();
      })
    );

    sourceInput.focus();
  }
}

class DropFileModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Drop File") });

    const description = contentEl.createDiv({ cls: "furnace-shell-meta" });
    description.setText(t("Import a PDF or repo snapshot into raw/inbox."));

    const kindSetting = new Setting(contentEl).setName(t("PDF or Repo"));
    const kindSelect = kindSetting.controlEl.createEl("select");
    [
      ["pdf", t("PDF")],
      ["repo", t("Repo")],
    ].forEach(([value, label]) => {
      const option = kindSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    kindSelect.value = "pdf";

    const sourceSetting = new Setting(contentEl).setName(t("Source"));
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.addClass("furnace-shell-code");
    const pickerInput = sourceSetting.controlEl.createEl("input", { type: "file" });
    pickerInput.style.display = "none";
    let pickLocalButton = null;
    sourceSetting.addButton((button) => {
      pickLocalButton = button;
      button.setButtonText(t("Select local file")).onClick(() => {
        pickerInput.click();
      });
    });

    pickerInput.addEventListener("change", () => {
      const file = pickerInput.files && pickerInput.files[0];
      const nextPath = file ? String(file.path || file.name || "") : "";
      if (nextPath) {
        sourceInput.value = nextPath;
      }
    });

    const titleSetting = new Setting(contentEl).setName(t("Title"));
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("Optional note title...");
    titleInput.addClass("furnace-shell-code");

    const maxFilesSetting = new Setting(contentEl).setName(t("Repo max files"));
    const maxFilesInput = maxFilesSetting.controlEl.createEl("input", { type: "text" });
    maxFilesInput.value = "200";
    maxFilesInput.addClass("furnace-shell-code");

    const syncModeState = () => {
      const mode = String(kindSelect.value || "pdf");
      sourceInput.placeholder = mode === "repo" ? t("Local repo path or remote git URL.") : t("Local PDF path or PDF URL.");
      pickerInput.accept = mode === "pdf" ? ".pdf,application/pdf" : "";
      if (pickLocalButton) {
        pickLocalButton.buttonEl.style.display = mode === "pdf" ? "" : "none";
      }
      maxFilesSetting.settingEl.style.display = mode === "repo" ? "" : "none";
    };
    kindSelect.addEventListener("change", syncModeState);
    syncModeState();

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Drop File")).setCta().onClick(async () => {
        const source = String(sourceInput.value || "").trim();
        if (!source) {
          new Notice(t("Source cannot be empty."));
          return;
        }
        const mode = String(kindSelect.value || "pdf");
        const title = String(titleInput.value || "").trim();
        const maxFiles = Number.parseInt(String(maxFilesInput.value || "200"), 10);
        this.close();
        this.plugin.runUiAction(
          () =>
            this.plugin.runDropFileCommand({
              mode,
              source,
              title,
              maxFiles: Number.isFinite(maxFiles) && maxFiles > 0 ? maxFiles : 200,
            }),
          t("Drop File modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
        this.close();
      })
    );

    sourceInput.focus();
  }
}

class DropImageModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("Drop Image") });

    const description = contentEl.createDiv({ cls: "furnace-shell-meta" });
    description.setText(t("Import an image into raw/inbox."));

    const sourceSetting = new Setting(contentEl).setName(t("Source"));
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.placeholder = t("Local image path or image URL.");
    sourceInput.addClass("furnace-shell-code");
    const pickerInput = sourceSetting.controlEl.createEl("input", { type: "file" });
    pickerInput.style.display = "none";
    pickerInput.accept = "image/*";
    sourceSetting.addButton((button) =>
      button.setButtonText(t("Select local file")).onClick(() => {
        pickerInput.click();
      })
    );
    pickerInput.addEventListener("change", () => {
      const file = pickerInput.files && pickerInput.files[0];
      const nextPath = file ? String(file.path || file.name || "") : "";
      if (nextPath) {
        sourceInput.value = nextPath;
      }
    });

    const titleSetting = new Setting(contentEl).setName(t("Title"));
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("Optional note title...");
    titleInput.addClass("furnace-shell-code");

    let skipVision = false;
    new Setting(contentEl)
      .setName(t("Skip vision analysis"))
      .addToggle((toggle) =>
        toggle.setValue(false).onChange((value) => {
          skipVision = Boolean(value);
        })
      );

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t("Drop Image")).setCta().onClick(async () => {
        const source = String(sourceInput.value || "").trim();
        if (!source) {
          new Notice(t("Source cannot be empty."));
          return;
        }
        const title = String(titleInput.value || "").trim();
        this.close();
        this.plugin.runUiAction(
          () =>
            this.plugin.runDropImageCommand({
              source,
              title,
              noVision: skipVision,
            }),
          t("Drop Image modal")
        );
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
        this.close();
      })
    );

    sourceInput.focus();
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
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t(this.spec.title || "Run command") });
    if (this.spec.description) {
      contentEl.createDiv({ cls: "furnace-shell-meta", text: t(this.spec.description) });
    }

    (this.spec.fields || []).forEach((field) => {
      const setting = new Setting(contentEl).setName(t(field.label));
      if (field.description) {
        setting.setDesc(t(field.description));
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
          const element = control.createEl("option", { text: t(option.label), value: option.value });
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
        control.placeholder = t(field.placeholder);
      }
      if (field.kind !== "toggle") {
        control.addClass("furnace-shell-code");
      }
      this.controls[field.key] = control;
    });

    const actionSetting = new Setting(contentEl);
    actionSetting.addButton((button) =>
      button.setButtonText(t(this.spec.submitLabel || "Run")).setCta().onClick(() => {
        const values = {};
        for (const field of this.spec.fields || []) {
          const control = this.controls[field.key];
          const value = field.kind === "toggle" ? Boolean(control.checked) : String(control.value || "").trim();
          if (field.required && !value) {
            new Notice(t("{field} cannot be empty.", { field: t(field.label) }));
            return;
          }
          values[field.key] = value;
        }
        this.close();
        this.plugin.runUiAction(() => this.spec.onSubmit(values), t(this.spec.title || "command modal"));
      })
    );
    actionSetting.addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
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
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t(this.spec.title || "Pick context") });
    if (this.spec.description) {
      contentEl.createDiv({ cls: "furnace-shell-meta", text: t(this.spec.description) });
    }

    const options = Array.isArray(this.spec.options) ? this.spec.options : [];
    if (!options.length) {
      contentEl.createDiv({ cls: "furnace-shell-empty", text: t("No context is currently available.") });
      new Setting(contentEl).addButton((button) =>
        button.setButtonText(t("Close")).onClick(() => {
          this.close();
        })
      );
      return;
    }

    const list = contentEl.createEl("ul", { cls: "furnace-shell-list" });
    options.forEach((option) => {
      const item = list.createEl("li");
      item.createEl("strong", { text: t(option.label || option.value || "context") });
      if (option.description) {
        item.createDiv({ cls: "furnace-shell-meta", text: t(option.description) });
      }
      const actions = item.createDiv({ cls: "furnace-shell-inline-actions" });
      const button = actions.createEl("button", { text: t(this.spec.submitLabel || "Use") });
      button.addEventListener("click", () => {
        this.close();
        this.plugin.runUiAction(() => this.spec.onSubmit(option), t(this.spec.title || "context picker"));
      });
    });

    new Setting(contentEl).addButton((button) =>
      button.setButtonText(t("Cancel")).onClick(() => {
        this.close();
      })
    );
  }
}
