// Render input controls for Product Shell.

function renderUniversalInput(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-universal-input-wrapper furnace-conversation-composer" });
  
  // Drag and drop overlay
  const dropOverlay = wrapper.createDiv({ cls: "furnace-universal-input-drop-overlay" });
  dropOverlay.createDiv({ text: plugin.t("Drop file here") });
  dropOverlay.style.display = "none";

  const form = wrapper.createDiv({ cls: "furnace-universal-input-form furnace-conversation-composer-form" });
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
      hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 结果会出现在“今天”"));

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
    if (file && (file.path || file.name || typeof file.arrayBuffer === "function")) {
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
    const normalizedQuestion = String(value || "").trim();

    // Lock UI during submit
    submitButton.disabled = true;
    textarea.disabled = true;
    const originalLabel = submitButton.textContent;
    submitButton.setText(plugin.t("处理中…"));
    hint.setText(plugin.t("已提交，进度会出现在上方对话流"));

    let succeeded = false;
    // R88: 立即推一个"处理中"卡片到 Today，构成视觉闭环
    let pendingId = "";
    try {
      if (filesToProcess.length > 0) {
        const resolvedFiles = [];
        for (const file of filesToProcess) {
          const source = await resolvePluginFileSource(plugin, file);
          resolvedFiles.push({ source, name: file.name || source });
        }
        const pendingDisplay = `${value || resolvedFiles.map((f) => f.name).join(", ")}`;
        const retryArgs = {
          kind: "files",
          files: resolvedFiles.map((f) => ({ path: f.source, name: f.name })),
          autoAsk: Boolean(normalizedQuestion),
          question: normalizedQuestion,
          materialPaths: [],
          askQuestion: "",
        };
        pendingId = plugin.pushPendingSubmission(pendingDisplay, {
          title: normalizedQuestion,
          retryArgs,
        });
        const flowResult = await plugin.runDroppedFilesWithAutoAsk({
          files: resolvedFiles.map((f) => ({ path: f.source, name: f.name })),
          question: normalizedQuestion,
        });
        if (pendingId) {
          plugin.updatePendingSubmissionRetryArgs(pendingId, {
            ...retryArgs,
            materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : [],
            askQuestion: String(flowResult && flowResult.askQuestion || ""),
            runNotesPath: String(flowResult && flowResult.runNotesPath || ""),
            runId: String(flowResult && flowResult.runId || ""),
          });
        }
      } else {
        const materialQuestion = splitTextMaterialQuestion(value);
        if (materialQuestion) {
          const retryArgs = {
            kind: "material-question",
            payload: materialQuestion.payload,
            question: materialQuestion.question,
            materialPaths: [],
            askQuestion: "",
          };
          pendingId = plugin.pushPendingSubmission(value, {
            title: materialQuestion.question,
            retryArgs,
          });
          const flowResult = await plugin.runDroppedPayloadsWithAutoAsk({
            payloads: [materialQuestion.payload],
            question: materialQuestion.question,
          });
          if (pendingId) {
            plugin.updatePendingSubmissionRetryArgs(pendingId, {
              ...retryArgs,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || ""),
              runNotesPath: String(flowResult && flowResult.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || ""),
            });
          }
        } else {
          pendingId = plugin.pushPendingSubmission(value, {
            title: "",
            retryArgs: { kind: "text", payload: value },
          });
          await plugin.runUniversalInputCommand({ payload: value });
        }
      }
      succeeded = true;
      // R89: 成功 ≠ 报告生成；先标 received（"已接收，等待生成报告"），等 reconcile 命中再 done
      if (pendingId) plugin.markPendingSubmissionReceived(pendingId);
    } catch (e) {
      if (pendingId) plugin.markPendingSubmissionFailed(pendingId, e);
      new Notice(plugin.t("提交失败：{message}（输入已保留，可重试）", { message: e && e.message ? e.message : String(e) }));
    } finally {
      submitButton.disabled = false;
      textarea.disabled = false;
      submitButton.setText(originalLabel || plugin.t("Submit"));
  hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 结果会出现在“今天”"));
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
        addFile(file);
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
        addFile(file);
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
        plugin.runUiAction(async () => {
          const source = await resolvePluginFileSource(plugin, file);
          new DropFileModal(plugin.app, plugin).setInitialMode("pdf").setInitialSource(source).open();
        }, plugin.t("Drop PDF"));
        return;
      }
      if (fileType.startsWith("image/")) {
        plugin.runUiAction(async () => {
          const source = await resolvePluginFileSource(plugin, file);
          new DropImageModal(plugin.app, plugin).setInitialSource(source).open();
        }, plugin.t("Drop Image"));
        return;
      }
      // For other file types, still try to open the drop file modal
      plugin.runUiAction(async () => {
        const source = await resolvePluginFileSource(plugin, file);
        new DropFileModal(plugin.app, plugin).setInitialMode("pdf").setInitialSource(source).open();
      }, plugin.t("Drop File"));
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
