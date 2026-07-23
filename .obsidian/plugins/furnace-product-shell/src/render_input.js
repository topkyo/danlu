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

  const stickyMaterialsContainer = wrapper.createDiv({ cls: "furnace-input-sticky-materials" });
  stickyMaterialsContainer.style.display = "none";

  const attachmentsContainer = wrapper.createDiv({ cls: "furnace-input-attachments-container" });
  const atSuggest = wrapper.createDiv({ cls: "furnace-at-suggest" });
  atSuggest.style.display = "none";

  const composerActions = wrapper.createDiv({ cls: "furnace-input-composer-actions" });
  const quoteActiveBtn = composerActions.createEl("button", {
    cls: "furnace-input-quote-active-btn",
    text: plugin.t("Attach current file"),
    attr: { type: "button" },
  });

  let attachedFiles = [];
  let attachedVaultPaths = [];
  let submitting = false;
  let lastChordSubmitAt = 0;
  let activeMention = null;

  const listVaultMentionCandidates = () => {
    const vault = plugin.app && plugin.app.vault;
    const files = vault && typeof vault.getMarkdownFiles === "function" ? vault.getMarkdownFiles() : [];
    const paths = [];
    for (const file of Array.isArray(files) ? files : []) {
      const p = String(file && file.path || "").trim();
      if (p) paths.push(p);
    }
    const activePath = typeof plugin.getActiveFilePath === "function" ? String(plugin.getActiveFilePath() || "").trim() : "";
    if (activePath && isAskMaterialPathAllowed(activePath) && !paths.includes(activePath)) {
      paths.unshift(activePath);
    }
    return paths;
  };

  const hideAtSuggest = () => {
    activeMention = null;
    atSuggest.style.display = "none";
    atSuggest.empty();
  };

  const renderStickyMaterialChips = () => {
    stickyMaterialsContainer.empty();
    const paths = stickyMaterialDisplayPaths(plugin.settings);
    if (!paths.length) {
      stickyMaterialsContainer.style.display = "none";
      return;
    }
    stickyMaterialsContainer.style.display = "flex";
    stickyMaterialsContainer.createDiv({
      cls: "furnace-input-sticky-materials-label",
      text: plugin.t("Sticky materials (used on follow-up)"),
    });
    const chips = stickyMaterialsContainer.createDiv({ cls: "furnace-input-sticky-materials-chips" });
    for (const materialPath of paths) {
      chips.createSpan({
        cls: "furnace-input-sticky-chip",
        text: formatMaterialChipLabel(materialPath),
        attr: { title: materialPath },
      });
    }
  };
  renderStickyMaterialChips();

  const updateAttachmentPills = () => {
    attachmentsContainer.empty();
    if (!attachedFiles.length && !attachedVaultPaths.length) {
      attachmentsContainer.style.display = "none";
      return;
    }
    attachmentsContainer.style.display = "flex";
    attachedVaultPaths.forEach((materialPath, index) => {
      const pill = attachmentsContainer.createDiv({ cls: "furnace-input-attachment furnace-input-attachment-vault" });
      pill.createSpan({
        text: formatMaterialChipLabel(materialPath),
        cls: "furnace-input-attachment-name",
        attr: { title: materialPath },
      });
      const removeBtn = pill.createSpan({ text: "×", cls: "furnace-input-attachment-remove" });
      removeBtn.addEventListener("click", () => {
        attachedVaultPaths.splice(index, 1);
        updateAttachmentPills();
      });
    });
    attachedFiles.forEach((file, index) => {
      const pill = attachmentsContainer.createDiv({ cls: "furnace-input-attachment" });
      pill.createSpan({ text: file.name, cls: "furnace-input-attachment-name" });
      const removeBtn = pill.createSpan({ text: "×", cls: "furnace-input-attachment-remove" });
      removeBtn.addEventListener("click", () => {
        attachedFiles.splice(index, 1);
        updateAttachmentPills();
      });
    });
  };

  const addVaultPath = (rawPath) => {
    const path = String(rawPath || "").replace(/\\/g, "/").replace(/^\.\//, "").trim();
    if (!path) return false;
    if (!isAskMaterialPathAllowed(path)) {
      new Notice(plugin.t("Path is not an allowed ask material: {path}", { path }));
      return false;
    }
    attachedVaultPaths = normalizeMaterialPaths([...attachedVaultPaths, path]);
    updateAttachmentPills();
    return true;
  };

  const showAtSuggest = (mention) => {
    activeMention = mention;
    const candidates = filterVaultPathsForMention(listVaultMentionCandidates(), mention.query, 12);
    atSuggest.empty();
    if (!candidates.length) {
      atSuggest.style.display = "none";
      return;
    }
    atSuggest.style.display = "block";
    for (const candidate of candidates) {
      const item = atSuggest.createDiv({
        cls: "furnace-at-suggest-item",
        text: candidate,
        attr: { title: candidate },
      });
      item.addEventListener("mousedown", (event) => {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        const value = String(textarea.value || "");
        textarea.value = `${value.slice(0, mention.start)}${value.slice(mention.end)}`;
        addVaultPath(candidate);
        hideAtSuggest();
        autoResize();
        textarea.focus();
      });
    }
  };

  quoteActiveBtn.addEventListener("click", () => {
    const activePath = typeof plugin.getActiveFilePath === "function" ? String(plugin.getActiveFilePath() || "").trim() : "";
    if (!activePath) {
      new Notice(plugin.t("No active file to attach."));
      return;
    }
    addVaultPath(activePath);
  });

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
  textarea.addEventListener("input", () => {
    autoResize();
    const cursor = typeof textarea.selectionStart === "number" ? textarea.selectionStart : textarea.value.length;
    const mention = extractAtMentionQuery(textarea.value, cursor);
    if (mention) showAtSuggest(mention);
    else hideAtSuggest();
  });

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
    if (!value.trim() && attachedFiles.length === 0 && attachedVaultPaths.length === 0) return;
    submitting = true;

    const filesToProcess = [...attachedFiles];
    const vaultPathsToUse = normalizeMaterialPaths(attachedVaultPaths);
    const normalizedQuestion = String(value || "").trim();
    hideAtSuggest();

    // Lock UI during submit
    submitButton.disabled = true;
    textarea.disabled = true;
    const originalLabel = submitButton.textContent;
    submitButton.setText(plugin.t("处理中…"));
    hint.setText(plugin.t("已提交，进度会出现在上方对话流"));

    let succeeded = false;
    let materialDropCompleted = false;
    let askResultPayload = null;
    // R88: 立即推一个"处理中"卡片到 Today，构成视觉闭环
    let pendingId = "";
    try {
      // Single-flight: block a new ask while one is active; pure material drops stay allowed.
      const materialQuestionPreview = splitTextMaterialQuestion(value);
      const willAsk = filesToProcess.length > 0 || vaultPathsToUse.length > 0
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
          extraMaterialPaths: vaultPathsToUse,
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
          } else {
            askResultPayload = flowResult && flowResult.askPayload;
          }
        }
      } else if (vaultPathsToUse.length > 0 && normalizedQuestion) {
        const askFormat = inferAutoAskFormat(normalizedQuestion, vaultPathsToUse);
        const retryArgs = {
          kind: "auto-ask",
          question: normalizedQuestion,
          askQuestion: normalizedQuestion,
          format: askFormat,
          materialPaths: vaultPathsToUse,
        };
        pendingId = plugin.pushPendingSubmission(value, {
          title: normalizedQuestion,
          retryArgs,
        });
        askResultPayload = await plugin.runAskCommand({
          question: normalizedQuestion,
          format: askFormat,
          mode: "run-ask",
          excludePendingId: pendingId,
          materialPaths: vaultPathsToUse,
        });
        if (pendingId) {
          const usedPaths = Array.isArray(askResultPayload && askResultPayload.usedMaterialPaths)
            ? askResultPayload.usedMaterialPaths
            : vaultPathsToUse;
          plugin.updatePendingSubmissionRetryArgs(pendingId, {
            ...retryArgs,
            materialPaths: usedPaths,
            askQuestion: String(normalizedQuestion || ""),
            runNotesPath: String(askResultPayload && askResultPayload.run_notes_path || ""),
            runId: String(askResultPayload && askResultPayload.run_id || ""),
          });
        }
      } else if (vaultPathsToUse.length > 0) {
        new Notice(plugin.t("Attached vault paths need a question to ask."));
        return;
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
            askResultPayload = flowResult && flowResult.askPayload;
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
            materialPaths: [],
          };
          pendingId = plugin.pushPendingSubmission(value, {
            title: normalizedQuestion,
            retryArgs,
          });
          askResultPayload = await plugin.runAskCommand({
            question: normalizedQuestion,
            format: askFormat,
            mode: "run-ask",
            excludePendingId: pendingId,
          });
          if (pendingId) {
            const usedPaths = Array.isArray(askResultPayload && askResultPayload.usedMaterialPaths)
              ? askResultPayload.usedMaterialPaths
              : [];
            plugin.updatePendingSubmissionRetryArgs(pendingId, {
              ...retryArgs,
              materialPaths: usedPaths,
              askQuestion: String(normalizedQuestion || ""),
              runNotesPath: String(askResultPayload && askResultPayload.run_notes_path || ""),
              runId: String(askResultPayload && askResultPayload.run_id || ""),
            });
          }
        }
      }
      succeeded = true;
      // 纯投料已在 completePendingMaterialDrop 标 done(raw)；提问路径同步完成则直写 done(outputs)
      if (pendingId && !materialDropCompleted) finalizePendingAskSubmission(plugin, pendingId, askResultPayload);
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
        attachedVaultPaths = [];
        updateAttachmentPills();
        renderStickyMaterialChips();
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
