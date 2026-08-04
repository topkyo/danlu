// Modal subclasses (StructuredCommand, ContextPicker).

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
