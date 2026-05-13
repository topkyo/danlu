// Modal subclasses (AskCommand, CaptureNote, Protocol, Search, DropUrl,
// DropFile, DropImage, StructuredCommand, ContextPicker).

// Shared modal helpers
function modalSubmitRow(containerEl, submitLabel, cancelLabel, onSubmit, onCancel) {
  var row = containerEl.createDiv({ cls: "furnace-modal-submit-row" });
  if (onCancel) {
    var cancelBtn = row.createEl("button", { text: cancelLabel || "Cancel" });
    cancelBtn.addClass("furnace-shell-ghost-button");
    cancelBtn.addEventListener("click", function () { onCancel(); });
  }
  var submitBtn = row.createEl("button", { text: submitLabel || "Submit" });
  submitBtn.addClass("mod-cta");
  submitBtn.addEventListener("click", function () { onSubmit(submitBtn); });
  return { row: row, submitBtn: submitBtn };
}

function setSubmitLoading(button, loadingText) {
  button.disabled = true;
  button.setText(loadingText || "处理中…");
}

function setSubmitReady(button, text) {
  button.disabled = false;
  button.setText(text);
}

function showInlineError(el, text) {
  if (!el) return;
  el.setText(text);
  el.addClass("is-visible");
}

function clearInlineError(el) {
  if (!el) return;
  el.setText("");
  el.removeClass("is-visible");
}

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
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("输入一个问题，炉子会用 LLM 深度分析并生成报告。") });

    const questionSetting = new Setting(contentEl).setName(t("问题"));
    questionSetting.nameEl.addClass("furnace-modal-field-required");
    const questionInput = questionSetting.controlEl.createEl("textarea");
    questionInput.rows = 4;
    questionInput.placeholder = t("输入研究问题……");
    questionInput.addClass("furnace-shell-code");
    const questionError = questionSetting.controlEl.createDiv({ cls: "furnace-modal-error" });

    const formatSetting = new Setting(contentEl).setName(t("格式"));
    const formatSelect = formatSetting.controlEl.createEl("select");
    ["note", "report", "slides", "figure"].forEach((item) => {
      const option = formatSelect.createEl("option", { text: item, value: item });
      option.value = item;
    });
    formatSelect.value = this.plugin.settings.defaultAskFormat;

    const protocolSetting = new Setting(contentEl).setName(t("协议"));
    const protocolSelect = protocolSetting.controlEl.createEl("select");
    protocolSelect.createEl("option", { text: t("当前协议"), value: "" });
    this.plugin.getAvailableProtocols().forEach((protocol) => {
      const option = protocolSelect.createEl("option", { text: protocol, value: protocol });
      option.value = protocol;
    });

    const { submitBtn } = modalSubmitRow(contentEl, t("运行"), t("取消"), function (btn) {
      const question = String(questionInput.value || "").trim();
      if (!question) {
        showInlineError(questionError, t("问题不能为空。"));
        return;
      }
      clearInlineError(questionError);
      setSubmitLoading(btn, t("分析中…"));
      const self = this;
      const format = String(formatSelect.value || "note");
      const protocol = String(protocolSelect.value || "").trim();
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runAskCommand({ question, format, mode: "run-ask", protocol });
      }, t("Ask modal"));
    }.bind(this), function () { this.close(); }.bind(this));

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
    contentEl.createEl("h2", { text: t("记录笔记") });
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("快速记录一条笔记、会议纪要或观察，直接投入炉子的收件箱。") });

    const titleSetting = new Setting(contentEl).setName(t("标题"));
    titleSetting.nameEl.addClass("furnace-modal-field-optional");
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("可选笔记标题……");
    titleInput.addClass("furnace-shell-code");

    const kindSetting = new Setting(contentEl).setName(t("类型"));
    const kindSelect = kindSetting.controlEl.createEl("select");
    [
      ["note", "note"],
      ["transcript", "transcript"],
    ].forEach(([value, label]) => {
      const option = kindSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    kindSelect.value = "note";

    const textSetting = new Setting(contentEl).setName(t("正文"));
    textSetting.nameEl.addClass("furnace-modal-field-required");
    const textInput = textSetting.controlEl.createEl("textarea");
    textInput.rows = 8;
    textInput.placeholder = t("记录笔记、会议纪要或快速观察……");
    textInput.addClass("furnace-shell-code");
    const textError = textSetting.controlEl.createDiv({ cls: "furnace-modal-error" });

    const self = this;
    modalSubmitRow(contentEl, t("记录"), t("取消"), function (btn) {
      const text = String(textInput.value || "").trim();
      if (!text) {
        showInlineError(textError, t("正文不能为空。"));
        return;
      }
      clearInlineError(textError);
      setSubmitLoading(btn, t("记录中…"));
      const title = String(titleInput.value || "").trim();
      const kind = String(kindSelect.value || "note");
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runDropNoteCommand({ text, title, kind });
      }, t("记录笔记"));
    }, function () { self.close(); });

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
    contentEl.createEl("h2", { text: t("搜索知识库") });
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("搜索 wiki、概念、判断、决策和派生页面。") });

    const querySetting = new Setting(contentEl).setName(t("关键词"));
    querySetting.nameEl.addClass("furnace-modal-field-required");
    const queryInput = querySetting.controlEl.createEl("textarea");
    queryInput.rows = 3;
    queryInput.placeholder = t("输入关键词搜索……");
    queryInput.addClass("furnace-shell-code");
    const queryError = querySetting.controlEl.createDiv({ cls: "furnace-modal-error" });

    var tagsRow = contentEl.createDiv({ cls: "furnace-modal-tags" });
    ["来源", "概念", "判断", "决策", "报告"].forEach(function (tag) {
      var tagEl = tagsRow.createDiv({ cls: "furnace-modal-tag", text: tag });
      tagEl.addEventListener("click", function () {
        var current = String(queryInput.value || "").trim();
        queryInput.value = current ? current + " " + tag : tag;
        queryInput.focus();
      });
    });

    const limitSetting = new Setting(contentEl).setName(t("结果数量"));
    const limitInput = limitSetting.controlEl.createEl("input", { type: "text" });
    limitInput.value = "8";
    limitInput.addClass("furnace-shell-code");

    const self = this;
    modalSubmitRow(contentEl, t("搜索"), t("取消"), function (btn) {
      const query = String(queryInput.value || "").trim();
      if (!query) {
        showInlineError(queryError, t("搜索关键词不能为空。"));
        return;
      }
      clearInlineError(queryError);
      setSubmitLoading(btn, t("搜索中…"));
      const parsedLimit = Number.parseInt(String(limitInput.value || "8"), 10);
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runShellSearchCommand(query, Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 8);
      }, t("搜索"));
    }, function () { self.close(); });

    queryInput.focus();
  }
}

class DropUrlModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
    this.initialUrl = "";
  }

  setInitialUrl(value) {
    this.initialUrl = String(value || "").trim();
    return this;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("投网址") });
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("投一个网页地址，炉子会自动抓取内容并编译成知识。") });

    const sourceSetting = new Setting(contentEl).setName(t("网址"));
    sourceSetting.nameEl.addClass("furnace-modal-field-required");
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.placeholder = "https://example.com/article";
    sourceInput.addClass("furnace-shell-code");
    sourceInput.value = this.initialUrl;
    const sourceError = sourceSetting.controlEl.createDiv({ cls: "furnace-modal-error" });

    const titleSetting = new Setting(contentEl).setName(t("标题"));
    titleSetting.nameEl.addClass("furnace-modal-field-optional");
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("可选笔记标题……");
    titleInput.addClass("furnace-shell-code");

    const self = this;
    modalSubmitRow(contentEl, t("投网址"), t("取消"), function (btn) {
      const url = String(sourceInput.value || "").trim();
      if (!url) {
        showInlineError(sourceError, t("网址不能为空。"));
        return;
      }
      clearInlineError(sourceError);
      setSubmitLoading(btn, t("抓取中…"));
      const title = String(titleInput.value || "").trim();
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runDropUrlCommand({ url, title });
      }, t("投网址"));
    }, function () { self.close(); });

    sourceInput.focus();
  }
}

class DropFileModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
    this.initialMode = "pdf";
    this.initialSource = "";
  }

  setInitialMode(value) {
    this.initialMode = String(value || "pdf").trim() === "repo" ? "repo" : "pdf";
    return this;
  }

  setInitialSource(value) {
    this.initialSource = String(value || "");
    return this;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("投文件") });
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("投一个本地文件或远程地址：PDF 会抽取文本，Repo 会抓取代码快照。") });

    const kindSetting = new Setting(contentEl).setName(t("PDF 或 Repo"));
    const kindSelect = kindSetting.controlEl.createEl("select");
    [
      ["pdf", t("PDF")],
      ["repo", t("Repo")],
    ].forEach(([value, label]) => {
      const option = kindSelect.createEl("option", { text: label, value });
      option.value = value;
    });
    kindSelect.value = this.initialMode;

    const sourceSetting = new Setting(contentEl).setName(t("来源"));
    sourceSetting.nameEl.addClass("furnace-modal-field-required");
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.addClass("furnace-shell-code");
    sourceInput.value = this.initialSource;
    const pickerInput = sourceSetting.controlEl.createEl("input", { type: "file" });
    pickerInput.style.display = "none";
    let pickLocalButton = null;
    const self = this;
    sourceSetting.addButton(function (button) {
      pickLocalButton = button;
      button.setButtonText(t("选择本地文件")).onClick(function () {
        pickerInput.click();
      });
    });
    const sourceError = sourceSetting.controlEl.createDiv({ cls: "furnace-modal-error" });

    pickerInput.addEventListener("change", async function () {
      const file = pickerInput.files && pickerInput.files[0];
      if (!file) { return; }
      try {
        const nextPath = await resolvePluginFileSource(self.plugin, file);
        if (nextPath) { sourceInput.value = nextPath; }
      } catch (error) {
        showInlineError(sourceError, self.plugin.t("提交失败：{message}（输入已保留，可重试）", { message: error && error.message ? error.message : String(error) }));
      }
    });

    const titleSetting = new Setting(contentEl).setName(t("标题"));
    titleSetting.nameEl.addClass("furnace-modal-field-optional");
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("可选笔记标题……");
    titleInput.addClass("furnace-shell-code");

    const maxFilesSetting = new Setting(contentEl).setName(t("Repo 最大文件数"));
    const maxFilesInput = maxFilesSetting.controlEl.createEl("input", { type: "text" });
    maxFilesInput.value = "200";
    maxFilesInput.addClass("furnace-shell-code");

    const syncModeState = function () {
      const mode = String(kindSelect.value || "pdf");
      sourceInput.placeholder = mode === "repo" ? t("本地 repo 路径或远程 git URL。") : t("本地 PDF 路径或 PDF URL。");
      pickerInput.accept = mode === "pdf" ? ".pdf,application/pdf" : "";
      if (pickLocalButton) { pickLocalButton.buttonEl.style.display = mode === "pdf" ? "" : "none"; }
      maxFilesSetting.settingEl.style.display = mode === "repo" ? "" : "none";
    };
    kindSelect.addEventListener("change", syncModeState);
    syncModeState();

    modalSubmitRow(contentEl, t("投文件"), t("取消"), function (btn) {
      const source = String(sourceInput.value || "").trim();
      if (!source) {
        showInlineError(sourceError, t("来源不能为空。"));
        return;
      }
      clearInlineError(sourceError);
      setSubmitLoading(btn, t("投料中…"));
      const mode = String(kindSelect.value || "pdf");
      const title = String(titleInput.value || "").trim();
      const maxFiles = Number.parseInt(String(maxFilesInput.value || "200"), 10);
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runDropFileCommand({
          mode, source, title,
          maxFiles: Number.isFinite(maxFiles) && maxFiles > 0 ? maxFiles : 200,
        });
      }, t("投文件"));
    }, function () { self.close(); });

    sourceInput.focus();
  }
}

class DropImageModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
    this.initialSource = "";
  }

  setInitialSource(value) {
    this.initialSource = String(value || "");
    return this;
  }

  onOpen() {
    const { contentEl } = this;
    const t = this.plugin.t.bind(this.plugin);
    contentEl.empty();
    contentEl.addClass("furnace-shell-view");
    contentEl.createEl("h2", { text: t("投图片") });
    contentEl.createDiv({ cls: "furnace-modal-help", text: t("投一张图片，炉子会提取视觉信息并纳入知识库。") });

    const sourceSetting = new Setting(contentEl).setName(t("来源"));
    sourceSetting.nameEl.addClass("furnace-modal-field-required");
    const sourceInput = sourceSetting.controlEl.createEl("input", { type: "text" });
    sourceInput.placeholder = t("本地图片路径或图片 URL。");
    sourceInput.addClass("furnace-shell-code");
    sourceInput.value = this.initialSource;
    const pickerInput = sourceSetting.controlEl.createEl("input", { type: "file" });
    pickerInput.style.display = "none";
    pickerInput.accept = "image/*";
    sourceSetting.addButton(function (button) {
      button.setButtonText(t("选择本地文件")).onClick(function () {
        pickerInput.click();
      });
    });
    const sourceError = sourceSetting.controlEl.createDiv({ cls: "furnace-modal-error" });
    const self = this;
    pickerInput.addEventListener("change", async function () {
      const file = pickerInput.files && pickerInput.files[0];
      if (!file) { return; }
      try {
        const nextPath = await resolvePluginFileSource(self.plugin, file);
        if (nextPath) { sourceInput.value = nextPath; }
      } catch (error) {
        showInlineError(sourceError, self.plugin.t("提交失败：{message}（输入已保留，可重试）", { message: error && error.message ? error.message : String(error) }));
      }
    });

    const titleSetting = new Setting(contentEl).setName(t("标题"));
    titleSetting.nameEl.addClass("furnace-modal-field-optional");
    const titleInput = titleSetting.controlEl.createEl("input", { type: "text" });
    titleInput.placeholder = t("可选笔记标题……");
    titleInput.addClass("furnace-shell-code");

    let skipVision = false;
    new Setting(contentEl)
      .setName(t("跳过视觉分析"))
      .addToggle(function (toggle) {
        toggle.setValue(false).onChange(function (value) { skipVision = Boolean(value); });
      });

    modalSubmitRow(contentEl, t("投图片"), t("取消"), function (btn) {
      const source = String(sourceInput.value || "").trim();
      if (!source) {
        showInlineError(sourceError, t("来源不能为空。"));
        return;
      }
      clearInlineError(sourceError);
      setSubmitLoading(btn, t("投料中…"));
      const title = String(titleInput.value || "").trim();
      self.close();
      self.plugin.runUiAction(function () {
        return self.plugin.runDropImageCommand({ source, title, noVision: skipVision });
      }, t("投图片"));
    }, function () { self.close(); });

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
