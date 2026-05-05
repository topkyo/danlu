// Render input controls for Product Shell.

function renderUniversalInput(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-universal-input-wrapper" });
  
  // Drag and drop overlay
  const dropOverlay = wrapper.createDiv({ cls: "furnace-universal-input-drop-overlay" });
  dropOverlay.createDiv({ text: plugin.t("Drop file here") });
  dropOverlay.style.display = "none";

  const form = wrapper.createDiv({ cls: "furnace-universal-input-form" });
  const textarea = form.createEl("textarea", { 
    cls: "furnace-universal-input-textarea",
    attr: { "aria-label": plugin.t("Universal input") }
  });
  
  textarea.placeholder = plugin.t("投 URL / PDF / 图片 / repo，或直接问一个问题；炼丹炉会生成报告");
  textarea.rows = 1;

  const submitButton = form.createEl("button", { 
    cls: "furnace-universal-input-button", 
    text: plugin.t("Submit") 
  });

  const hint = wrapper.createDiv({ cls: "furnace-universal-input-hint" });
  hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 结果会出现在 Today"));

  const attachmentsContainer = wrapper.createDiv({ cls: "furnace-input-attachments-container" });
  
  let attachedFiles = [];

  const updateAttachmentPills = () => {
    attachmentsContainer.empty();
    if (attachedFiles.length === 0) {
      attachmentsContainer.style.display = "none";
      return;
    }
    attachmentsContainer.style.display = "flex";
    attachedFiles.forEach((file, index) => {
      const pill = attachmentsContainer.createDiv({ cls: "furnace-input-attachment" });
      const nameSpan = pill.createSpan({ text: file.name, cls: "furnace-input-attachment-name" });
      const removeBtn = pill.createSpan({ text: "×", cls: "furnace-input-attachment-remove" });
      
      removeBtn.addEventListener("click", () => {
        attachedFiles.splice(index, 1);
        updateAttachmentPills();
      });
    });
  };

  const addFile = (file) => {
    // Use path (Electron) or name as fallback
    if (file && (file.path || file.name)) {
      attachedFiles.push(file);
      updateAttachmentPills();
    }
  };

  const autoResize = () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
  };
  textarea.addEventListener('input', autoResize);

  const handleSubmit = async () => {
    const value = textarea.value;
    if (!value.trim() && attachedFiles.length === 0) return;

    const filesToProcess = [...attachedFiles];
    const originalValue = value;

    // Lock UI during submit
    submitButton.disabled = true;
    textarea.disabled = true;
    const originalLabel = submitButton.textContent;
    submitButton.setText(plugin.t("处理中…"));
    hint.setText(plugin.t("已提交，结果会出现在 Today"));

    let succeeded = false;
    // R88: 立即推一个"处理中"卡片到 Today，构成视觉闭环
    const pendingDisplay = filesToProcess.length > 0
      ? `${value || filesToProcess.map((f) => f.name).join(", ")}`
      : value;
    const retryArgs = filesToProcess.length > 0
      ? { kind: "files", files: filesToProcess.map((f) => ({ path: f.path, name: f.name })), title: value }
      : { kind: "text", payload: value };
    const pendingId = plugin.pushPendingSubmission(pendingDisplay, {
      title: filesToProcess.length > 0 ? value : "",
      retryArgs,
    });
    try {
      if (filesToProcess.length > 0) {
        for (const file of filesToProcess) {
          await plugin.runUniversalInputCommand({ payload: file.path || file.name || "", title: value });
        }
      } else {
        await plugin.runUniversalInputCommand({ payload: value });
      }
      succeeded = true;
      if (pendingId) plugin.markPendingSubmissionDone(pendingId);
    } catch (e) {
      if (pendingId) plugin.markPendingSubmissionFailed(pendingId, e);
      new Notice(plugin.t("提交失败：{message}（输入已保留，可重试）", { message: e && e.message ? e.message : String(e) }));
    } finally {
      submitButton.disabled = false;
      textarea.disabled = false;
      submitButton.setText(originalLabel || plugin.t("Submit"));
      hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 结果会出现在 Today"));
      if (succeeded) {
        textarea.value = '';
        autoResize();
        attachedFiles = [];
        updateAttachmentPills();
      }
      // 失败：保留 textarea.value 和 attachedFiles，便于用户修正后重试
    }
  };

  submitButton.addEventListener("click", () => {
    handleSubmit();
  });

  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  });

  textarea.addEventListener("paste", (e) => {
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      e.preventDefault();
      for (let i = 0; i < e.clipboardData.files.length; i++) {
        const file = e.clipboardData.files[i];
        addFile({ name: file.name, path: file.path, type: file.type });
      }
    }
  });

  // Drag and Drop handlers
  let dragCounter = 0;
  wrapper.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragCounter++;
    dropOverlay.style.display = "flex";
  });
  wrapper.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter === 0) {
      dropOverlay.style.display = "none";
    }
  });
  wrapper.addEventListener("dragover", (e) => {
    e.preventDefault();
  });
  wrapper.addEventListener("drop", (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.style.display = "none";
    
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      for (let i = 0; i < e.dataTransfer.files.length; i++) {
        const file = e.dataTransfer.files[i];
        addFile({ name: file.name, path: file.path, type: file.type });
      }
    } else if (e.dataTransfer) {
      const text = e.dataTransfer.getData("text/plain");
      if (text) {
        textarea.value = text;
        autoResize();
      }
    }
  });
}

function renderAskBox(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-shell-askbox-wrapper" });
  const form = wrapper.createDiv({ cls: "furnace-shell-askbox-form" });
  const input = form.createEl("input", { cls: "furnace-shell-askbox", type: "text" });
  input.placeholder = plugin.t("Ask / Command...");
  const askButton = form.createEl("button", { cls: "furnace-shell-askbox-button", text: plugin.t("Ask") });
  const status = wrapper.createDiv({ cls: "furnace-shell-askbox-status" });
  let isRunning = false;

  const setRunning = (nextRunning) => {
    isRunning = Boolean(nextRunning);
    input.disabled = isRunning;
    askButton.disabled = isRunning;
    askButton.setText(isRunning ? plugin.t("Asking...") : plugin.t("Ask"));
    status.setText(isRunning ? plugin.t("Asking...") : "");
  };

  const submitAsk = async () => {
    if (isRunning) {
      return;
    }
    const question = String(input.value || "").trim();
    if (!question) {
      return;
    }
    input.value = "";
    setRunning(true);
    try {
      await plugin.runAskCommand({
        question,
        format: plugin.settings.defaultAskFormat,
        mode: "run-ask",
        protocol: "",
      });
    } finally {
      setRunning(false);
    }
  };

  askButton.addEventListener("click", () => {
    plugin.runUiAction(() => submitAsk(), plugin.t("Ask"));
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      plugin.runUiAction(() => submitAsk(), plugin.t("Ask"));
    }
  });
}

function renderDropZone(plugin, container) {
  const zone = container.createDiv({ cls: "furnace-shell-dropzone" });
  zone.createDiv({ cls: "furnace-shell-dropzone-title", text: plugin.t("Drop URL / PDF / Image / Repo") });
  const actions = zone.createDiv({ cls: "furnace-shell-dropzone-actions" });
  [
    { label: "URL", actionLabel: "Drop URL", onClick: () => plugin.openDropUrlModal() },
    { label: "PDF", actionLabel: "Drop PDF", onClick: () => new DropFileModal(plugin.app, plugin).setInitialMode("pdf").open() },
    { label: "Image", actionLabel: "Drop Image", onClick: () => new DropImageModal(plugin.app, plugin).open() },
    { label: "Repo", actionLabel: "Drop Repo", onClick: () => new DropFileModal(plugin.app, plugin).setInitialMode("repo").open() },
  ].forEach((item) => {
    const button = actions.createEl("button", { text: plugin.t(item.label) });
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      plugin.runUiAction(() => item.onClick(), plugin.t(item.actionLabel));
    });
  });
  zone.addEventListener("click", () => {
    plugin.runUiAction(() => plugin.openDropUrlModal(), plugin.t("Drop URL"));
  });
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.addClass("is-drag-over");
  });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) {
      zone.removeClass("is-drag-over");
    }
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.removeClass("is-drag-over");
    const dataTransfer = event.dataTransfer;
    if (!dataTransfer) {
      return;
    }
    const file = dataTransfer.files && dataTransfer.files[0];
    if (file) {
      const fileName = String(file.name || file.path || "").toLowerCase();
      const fileType = String(file.type || "").toLowerCase();
      if (fileType === "application/pdf" || fileName.endsWith(".pdf")) {
        plugin.runUiAction(() => new DropFileModal(plugin.app, plugin).setInitialMode("pdf").setInitialSource(file.path || "").open(), plugin.t("Drop PDF"));
        return;
      }
      if (fileType.startsWith("image/")) {
        plugin.runUiAction(() => new DropImageModal(plugin.app, plugin).setInitialSource(file.path || "").open(), plugin.t("Drop Image"));
        return;
      }
      // For other file types, still try to open the drop file modal
      plugin.runUiAction(() => new DropFileModal(plugin.app, plugin).setInitialMode("pdf").setInitialSource(file.path || "").open(), plugin.t("Drop File"));
      return;
    }
    const uriList = String(dataTransfer.getData("text/uri-list") || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    const text = uriList[0] || String(dataTransfer.getData("text/plain") || "").trim();
    if (isHttpUrl(text)) {
      plugin.runUiAction(() => plugin.openDropUrlModal(text), plugin.t("Drop URL"));
      return;
    }
  });
}
