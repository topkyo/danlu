// Render input controls for Product Shell.

function renderUniversalInput(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-universal-input-wrapper furnace-conversation-composer" });
  
  // Drag and drop overlay
  const dropOverlay = wrapper.createDiv({ cls: "furnace-universal-input-drop-overlay" });
  dropOverlay.createDiv({ text: plugin.t("Drop file here") });
  dropOverlay.style.display = "none";

  const form = wrapper.createEl("form", { cls: "furnace-universal-input-form furnace-conversation-composer-form" });
  const textarea = form.createEl("textarea", { 
    cls: "furnace-universal-input-textarea",
    attr: { "aria-label": plugin.t("Universal input") }
  });
  
  textarea.placeholder = plugin.t("投 URL / PDF / Markdown / 图片 / repo；提问才会生成报告");
  textarea.rows = 1;

  const submitButton = form.createEl("button", { 
    cls: "furnace-universal-input-button", 
    text: plugin.t("Submit"),
    attr: { type: "submit" }
  });

  const hint = wrapper.createDiv({ cls: "furnace-universal-input-hint" });
      hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 投料入 raw，提问出报告"));

  const attachmentsContainer = wrapper.createDiv({ cls: "furnace-input-attachments-container" });
  
  let attachedFiles = [];
  let submitting = false;
  let lastChordSubmitAt = 0;

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
    textarea.style.height = Math.min(textarea.scrollHeight, 300) + 'px';
  };
  textarea.addEventListener('input', autoResize);

  const isSubmitChord = (event) => {
    const isEnter = event.key === "Enter" || event.key === "NumpadEnter" || event.code === "Enter" || event.code === "NumpadEnter" || event.keyCode === 13;
    return isEnter && (event.ctrlKey || event.metaKey);
  };

  const submitFromChord = (event) => {
    if (!isSubmitChord(event)) return false;
    if (typeof event.preventDefault === "function") event.preventDefault();
    if (typeof event.stopPropagation === "function") event.stopPropagation();
    const now = Date.now();
    if (now - lastChordSubmitAt < 800) return true;
    lastChordSubmitAt = now;
    if (submitting) return true;
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return true;
    }
    handleSubmit(event);
    return true;
  };

  const handleSubmit = async (event) => {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (submitting) return;
    const value = textarea.value;
    if (!value.trim() && attachedFiles.length === 0) return;
    submitting = true;

    const filesToProcess = [...attachedFiles];
    const normalizedQuestion = String(value || "").trim();

    // Lock UI during submit
    submitButton.disabled = true;
    textarea.disabled = true;
    const originalLabel = submitButton.textContent;
    submitButton.setText(plugin.t("处理中…"));
    hint.setText(plugin.t("已提交，进度会出现在上方对话流"));

    let succeeded = false;
    let materialDropCompleted = false;
    // R88: 立即推一个"处理中"卡片到 Today，构成视觉闭环
    let pendingId = "";
    try {
      // Single-flight: block a new ask while one is active; pure material drops stay allowed.
      const materialQuestionPreview = splitTextMaterialQuestion(value);
      const willAsk = filesToProcess.length > 0
        ? Boolean(normalizedQuestion)
        : Boolean(materialQuestionPreview)
          || (
            Boolean(normalizedQuestion)
            && !isObsidianOpenLink(normalizedQuestion)
            && !looksLikeUniversalMaterialPayload(normalizedQuestion)
          );
      if (willAsk && typeof plugin.hasActiveAskPending === "function" && plugin.hasActiveAskPending()) {
        new Notice(plugin.t("已有进行中的提问，请等待完成后再试。"));
        return;
      }
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
          excludePendingId: pendingId,
        });
        if (pendingId) {
          const finalFormat = String(flowResult && flowResult.askFormat || retryArgs.format || "");
          plugin.updatePendingSubmissionRetryArgs(pendingId, {
            ...retryArgs,
            materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : [],
            askQuestion: String(flowResult && flowResult.askQuestion || ""),
            format: finalFormat,
            runNotesPath: String(flowResult && flowResult.runNotesPath || ""),
            runId: String(flowResult && flowResult.runId || ""),
          });
          if (!normalizedQuestion) {
            materialDropCompleted = Boolean(
              plugin.completePendingMaterialDrop(pendingId, flowResult && flowResult.materialPaths)
            );
          }
        }
      } else {
        if (isObsidianOpenLink(normalizedQuestion)) {
          const targetPath = obsidianOpenLinkFilePath(normalizedQuestion);
          if (targetPath) {
            const opened = await plugin.openWorkspacePath(targetPath);
            succeeded = Boolean(opened);
            if (!opened) {
              new Notice(plugin.t("无法打开工作区路径：{path}", { path: targetPath }));
            }
          } else {
            new Notice(plugin.t("Obsidian 打开链接是导航目标，不会作为问题提交。"));
          }
          return;
        }
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
            excludePendingId: pendingId,
          });
          if (pendingId) {
            const finalFormat = String(flowResult && flowResult.askFormat || retryArgs.format || "");
            plugin.updatePendingSubmissionRetryArgs(pendingId, {
              ...retryArgs,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || ""),
              format: finalFormat,
              runNotesPath: String(flowResult && flowResult.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || ""),
            });
          }
        } else if (looksLikeUniversalMaterialPayload(normalizedQuestion)) {
          const retryArgs = {
            kind: "material",
            payload: normalizedQuestion,
            materialPaths: [],
          };
          pendingId = plugin.pushPendingSubmission(value, {
            title: normalizedQuestion,
            retryArgs,
          });
          const payload = await plugin.runUniversalInputCommand({ payload: normalizedQuestion });
          const materialPaths = collectMaterialPathsFromPayload(payload);
          if (pendingId) {
            plugin.updatePendingSubmissionRetryArgs(pendingId, {
              ...retryArgs,
              materialPaths,
              reused: Boolean(payload && payload.reused),
            });
            materialDropCompleted = Boolean(plugin.completePendingMaterialDrop(pendingId, materialPaths));
          }
        } else {
          const askFormat = inferAutoAskFormat(normalizedQuestion, []);
          const retryArgs = {
            kind: "auto-ask",
            question: normalizedQuestion,
            askQuestion: normalizedQuestion,
            format: askFormat,
          };
          pendingId = plugin.pushPendingSubmission(value, {
            title: normalizedQuestion,
            retryArgs,
          });
          const askPayload = await plugin.runAskCommand({
            question: normalizedQuestion,
            format: askFormat,
            mode: "run-ask",
            excludePendingId: pendingId,
          });
          if (pendingId) {
            plugin.updatePendingSubmissionRetryArgs(pendingId, {
              ...retryArgs,
              runNotesPath: String(askPayload && askPayload.run_notes_path || ""),
              runId: String(askPayload && askPayload.run_id || ""),
            });
          }
        }
      }
      succeeded = true;
      // 纯投料已在 completePendingMaterialDrop 标 done(raw)；提问路径才进入 received 等报告
      if (pendingId && !materialDropCompleted) plugin.markPendingSubmissionReceived(pendingId);
    } catch (e) {
      if (pendingId) plugin.markPendingSubmissionFailed(pendingId, e);
      new Notice(plugin.t("提交失败：{message}（输入已保留，可重试）", { message: e && e.message ? e.message : String(e) }));
    } finally {
      submitButton.disabled = false;
      textarea.disabled = false;
      submitting = false;
      submitButton.setText(originalLabel || plugin.t("Submit"));
  hint.setText(plugin.t("Ctrl+Enter 提交 · 拖入文件 · 投料入 raw，提问出报告"));
      if (succeeded) {
        textarea.value = '';
        autoResize();
        attachedFiles = [];
        updateAttachmentPills();
      }
      // 失败：保留 textarea.value 和 attachedFiles，便于用户修正后重试
    }
  };

  form.addEventListener("submit", handleSubmit);
  form.addEventListener("keydown", submitFromChord, true);
  form.addEventListener("keyup", submitFromChord, true);
  submitButton.addEventListener("click", (event) => {
    if (typeof event.preventDefault === "function") event.preventDefault();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return;
    }
    handleSubmit(event);
  });

  textarea.addEventListener("keydown", (e) => {
    submitFromChord(e);
  });
  textarea.addEventListener("keyup", (e) => {
    submitFromChord(e);
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
