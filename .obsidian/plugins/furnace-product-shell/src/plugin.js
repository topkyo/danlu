// Main plugin class. Render methods delegate to standalone functions
// defined in render.js.

module.exports = class FurnaceProductShellPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
    this.pluginState = { recentRuns: [] };
    this.pendingSubmissions = []; // R89: 持久化 + runtime; status: running | done | failed | degraded; { id, payloadFingerprint, displayText, status, startedAt, finishedAt, error, reconcileTarget }
    this.shellSummary = null;
    this.repoState = { valid: false, root: "", runtimeRoot: "", missingPaths: ["vault-root"] };
    this.openViews = new Set();
    this.statusBarItem = this.addStatusBarItem();

    await this.loadPluginState();
    this.refreshRepoState();

    this.registerView(VIEW_TYPE_FURNACE_CENTER, (leaf) => new FurnaceCenterView(leaf, this));
    this.addSettingTab(new FurnaceProductShellSettingTab(this.app, this));

    this.addRibbonIcon("flask-conical", this.t("Open Furnace"), () => {
      this.runUiAction(() => this.openFurnaceCenterView(), this.t("Open Furnace"));
    });

    this.registerPublicCommands();
    this.registerAdvancedCommands();

    // Debounce vault change events: a compile burst writes many files in
    // seconds and would otherwise trigger dozens of full UI re-renders.
    this._vaultChangeTimer = null;
    this._debouncedVaultChange = (relativePath) => {
      if (this._vaultChangeTimer) {
        clearTimeout(this._vaultChangeTimer);
      }
      this._vaultChangeTimer = setTimeout(() => {
        this._vaultChangeTimer = null;
        void this.handleVaultChange(relativePath);
      }, 300);
    };

    this.registerEvent(this.app.vault.on("modify", (file) => {
      this._debouncedVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("create", (file) => {
      this._debouncedVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("delete", (file) => {
      this._debouncedVaultChange(file.path);
    }));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => {
      this._debouncedVaultChange(file.path || oldPath);
    }));

    await this.loadShellSummaryFromDisk();

    registerCuratedOutputLeafSync(this);

    this.updateStatusBar();
  }

  async onunload() {
    if (this._vaultChangeTimer) {
      clearTimeout(this._vaultChangeTimer);
      this._vaultChangeTimer = null;
    }
    this.openViews.clear();
  }

  registerPublicCommands() {
    this.addCommand({
      id: "open-furnace-center",
      name: this.t("Open Furnace"),
      callback: () => {
        this.runUiAction(() => this.openFurnaceCenterView(), this.t("Open Furnace"));
      },
    });
  }

  registerAdvancedCommands() {
    if (!this.settings.showAdvancedCommands) {
      return;
    }
    this.addCommand({
      id: "refresh-furnace-shell",
      name: this.t("Refresh Furnace Shell"),
      callback: () => {
        this.runUiAction(() => this.refreshShellSummaryCommand(), this.t("Refresh Furnace Shell"));
      },
    });
  }

  registerOpenView(view) {
    this.openViews.add(view);
  }

  unregisterOpenView(view) {
    this.openViews.delete(view);
  }

  locale() {
    return normalizeLocale(this.settings && this.settings.locale);
  }

  t(text, variables = {}) {
    return t(this.locale(), text, variables);
  }

  async loadPluginState() {
    return loadProductShellPluginState(this);
  }

  async savePluginState() {
    return saveProductShellPluginState(this);
  }

  getAdvancedSectionExpanded(key) {
    return getProductShellAdvancedSectionExpanded(this, key);
  }

  async setAdvancedSectionExpanded(key, value) {
    return setProductShellAdvancedSectionExpanded(this, key, value);
  }

  // R89: 持久化 pending（运行时不变；只在 save 时序列化）
  serializePendingSubmissions() {
    return serializePendingSubmissionList(this.pendingSubmissions);
  }

  // R89: 启动时从持久化 settings hydrate；超过 TTL 24h 的 running → failed；旧 received 迁移为 running
  // R90: done 状态加 7 天 TTL（避免无限堆积）
  hydratePendingSubmissions(raw) {
    return hydratePendingSubmissionList(raw);
  }

  trimRecentRuns() {
    this.pluginState.recentRuns = this.pluginState.recentRuns.slice(0, RECENT_RUNS_LIMIT);
  }

  normalizeLlmHealthState(value) {
    return normalizeLlmHealthState(this, value);
  }

  currentLlmHealth() {
    return currentLlmHealth(this);
  }

  latestLlmRun() {
    return latestLlmRun(this);
  }

  currentShellSyncState() {
    return currentShellSyncState(this);
  }

  selfCheckItems() {
    return selfCheckItems(this);
  }

  updateLlmHealth(nextState) {
    return updateLlmHealth(this, nextState);
  }

  recordLlmHealthFromRun(record, overrides = {}) {
    return recordLlmHealthFromRun(this, record, overrides);
  }

  refreshRepoState() { this.repoState = refreshRepoState(this); this.updateStatusBar(); this.refreshOpenViews(); }


  getActiveProtocol() {
    return getActiveProtocolFromSummary(this.shellSummary);
  }

  getActiveFilePath() {
    return getActiveFilePathFromApp(this.app);
  }

  getActiveConceptSlug() {
    return getConceptSlugForPath(this.getActiveFilePath());
  }

  getActiveCuratedPagePath() {
    return getCuratedPagePathForSummary(this.getActiveFilePath(), this.shellSummary);
  }

  openStructuredCommandModal(spec) {
    new StructuredCommandModal(this.app, this, spec).open();
  }

  openContextPicker(spec) {
    new ContextPickerModal(this.app, this, spec).open();
  }

  transitionLabel(controlType, transition) {
    return transitionLabel(this, controlType, transition);
  }

  transitionOptions(controlType, control) {
    return transitionOptions(this, controlType, control);
  }

  manualReviewOption() {
    return manualReviewOption(this);
  }

  openTransitionPicker({ title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice }) {
    return openTransitionPickerForControl(this, { title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice });
  }

  async runReviewPageTransition(pagePath, status) {
    await this.runCliAction(`Review Page: ${status}`, "review-page", [pagePath, "--status", status]);
  }

  visibleReviewPageCandidates() {
    return [];
  }

  openContextAwareAction(spec) {
    return openContextAwareActionForSpec(this, spec);
  }

  async handleVaultChange(relativePath) {
    return handleProductShellVaultChange(this, relativePath);
  }

  updateStatusBar() {
    return updateProductShellStatusBar(this);
  }

  async loadShellSummaryFromDisk() {
    return loadProductShellSummaryFromDisk(this);
  }

  async execLauncher(args) { return execLauncher(this, args); }
  createRuntimeClient() { return createRuntimeClient(this); }
  async executeRuntimeCommand(args) { return this.createRuntimeClient().exec(args); }

  runUiAction(action, label = "ui-action") { runUiAction(this, action, label); }

  currentLlmSelection() {
    const llmStatus = this.shellSummary && typeof this.shellSummary === "object" ? this.shellSummary.llm_status || {} : {};
    return {
      backend: String(llmStatus.effective_backend || llmStatus.backend || this.settings.llmBackend || "").trim(),
      model: String(llmStatus.effective_model || llmStatus.model || this.settings.llmModel || "").trim(),
      codexReasoningEffort: String(llmStatus.codex_reasoning_effort || "").trim(),
    };
  }

  resolveAbsoluteWorkspacePath(relativePath) {
    const normalized = String(relativePath || "").trim();
    const root = String(this.repoState.root || "").trim();
    if (!normalized || !root) {
      return "";
    }
    return path.join(root, normalized);
  }

  persistRunLog(record, details = {}) {
    // Run-log markdown persistence retired: canonical history lives in
    // .aiwiki/logs/runs.jsonl plus in-memory recentRuns.
    void details;
    if (record && typeof record === "object") {
      record.logPath = "";
    }
  }

  async copyText(value) {
    return copyProductShellText(this, value);
  }

  async revealWorkspacePath(relativePath) {
    return revealProductShellWorkspacePath(this, relativePath);
  }

  createRunRecord(label, args) {
    return createProductShellPluginRunRecord(this, label, args);
  }

  updateRunRecord(record, updates) {
    return updateProductShellPluginRunRecord(this, record, updates);
  }

  latestPluginRun() {
    return latestProductShellPluginRun(this);
  }

  async rerunRecord(record) {
    return rerunProductShellPluginRecord(this, record);
  }

  async runPluginCommand(label, args, options = {}) {
    return runProductShellPluginCommand(this, label, args, options);
  }

  async refreshShellSummarySilently() {
    return refreshProductShellSummarySilently(this);
  }

  
  processShellSummaryUpdates(summary) {
    return processProductShellSummaryUpdates(this, summary);
  }

  async refreshShellSummaryCommand() {
    return refreshProductShellSummaryCommand(this);
  }

  // R90: done 卡"打开报告/查看回执"统一入口；处理 path 缺失 + open 失败 + 用户反馈
  async openPendingDoneTarget(target, reconcilePath) {
    return openProductShellPendingDoneTarget(this, target, reconcilePath);
  }

  async readWorkspaceSnippet(relativePath, length = 420) {
    return readProductShellWorkspaceSnippet(this, relativePath, length);
  }

  quoteFileToComposer(relativePath) {
    return quoteProductShellFileToComposer(this, relativePath);
  }

  prefillComposer({ question, materialPaths } = {}) {
    return prefillProductShellComposer(this, { question, materialPaths });
  }


  async runCompileCommand() {
    await this.runPluginCommand(this.t("Compile"), ["compile"], { refreshAfter: true });
  }

  async runNightlyCommand() {
    await this.runPluginCommand(this.t("Nightly"), ["run-nightly"], { refreshAfter: true });
  }

  async openHomeNote() {
    return openProductShellHomeNote(this);
  }

  async openOutputsHub() {
    return openProductShellOutputsHub(this);
  }

  pushPendingSubmission(displayText, opts = {}) {
    return pushPendingSubmissionRuntime(this, displayText, opts);
  }

  resetPendingSubmissionForRetry(id) {
    return resetPendingSubmissionRuntimeForRetry(this, id);
  }

  markPendingSubmissionDone(id, reconcileTarget, reconcilePath) {
    return markPendingSubmissionRuntimeDone(this, id, reconcileTarget, reconcilePath);
  }

  markPendingSubmissionFailed(id, error) {
    return markPendingSubmissionRuntimeFailed(this, id, error);
  }

  removePendingSubmission(id) {
    if (removePendingSubmissionRuntimeEntry(this, id)) commitPendingSubmissionRuntimeChange(this);
  }

  _findPending(id) {
    return findPendingSubmissionRuntimeEntry(this, id);
  }

  updatePendingSubmissionRetryArgs(id, retryArgs) {
    return updatePendingSubmissionRuntimeRetryArgs(this, id, retryArgs);
  }

  updatePendingSubmissionRunNotes(id, runNotesPath, runId, opts = {}) {
    return updatePendingSubmissionRuntimeRunNotes(this, id, runNotesPath, runId, opts);
  }

  updatePendingSubmissionArtifactMeta(id, meta, opts = {}) {
    return updatePendingSubmissionRuntimeArtifactMeta(this, id, meta, opts);
  }

  hasActiveAskPending() {
    return pendingHasActiveAsk(this.pendingSubmissions);
  }

  getLastSummaryRefreshLabel() {
    return productShellLastSummaryRefreshLabel(this);
  }

  reconcilePendingSubmissions(summary) {
    return reconcilePendingSubmissionsRuntime(this, summary);
  }

  async runUniversalInputCommand({ payload, title }) {
    return runProductShellUniversalInputCommand(this, { payload, title });
  }

  async runAskCommand({ question, format, mode, excludePendingId, materialPaths }) {
    return runProductShellAskCommand(this, { question, format, mode, excludePendingId, materialPaths });
  }

  async runDroppedPayloadsWithAutoAsk({ payloads, question, excludePendingId, extraMaterialPaths }) {
    return runProductShellDroppedPayloadsWithAutoAsk(this, { payloads, question, excludePendingId, extraMaterialPaths });
  }

  completePendingMaterialDrop(id, materialPaths) {
    return completeProductShellPendingMaterialDrop(this, id, materialPaths);
  }

  async runDroppedFilesWithAutoAsk({ files, question, excludePendingId, extraMaterialPaths }) {
    return runProductShellDroppedFilesWithAutoAsk(this, { files, question, excludePendingId, extraMaterialPaths });
  }

  async runDropUrlCommand({ url, title }) {
    return runProductShellDropUrlCommand(this, { url, title });
  }

  async runDropFileCommand({ mode, source, title, maxFiles }) {
    return runProductShellDropFileCommand(this, { mode, source, title, maxFiles });
  }

  async runDropImageCommand({ source, title, noVision }) {
    return runProductShellDropImageCommand(this, { source, title, noVision });
  }

  async runDropNoteCommand({ text, title, kind }) {
    return runProductShellDropNoteCommand(this, { text, title, kind });
  }

  async runCliAction(label, command, args = []) {
    return runProductShellCliAction(this, label, command, args);
  }

  openAlchemyStartModal(prefill = {}) {
    this.openStructuredCommandModal(buildAlchemyStartModalSpec(this, prefill));
  }

  async runCompoundFileBack(suggest) {
    const item = suggest && typeof suggest === "object" ? suggest : {};
    const reportPath = String(item.report_path || item.reportPath || "").trim();
    if (!reportPath) {
      new Notice(this.t("缺少报告路径"));
      return;
    }
    if (this._compoundFileBackInFlight) {
      new Notice(this.t("沉淀进行中，请稍候"));
      return;
    }
    this._compoundFileBackInFlight = true;
    if (!(this._locallyFiledReports instanceof Set)) this._locallyFiledReports = new Set();
    this._locallyFiledReports.add(reportPath);
    const label = String(item.title || this.t("沉淀")).trim() || this.t("沉淀");
    try {
      await this.runCliAction(label, "file-back", [reportPath]);
      this.refreshOpenViews();
    } catch (error) {
      this._locallyFiledReports.delete(reportPath);
      throw error;
    } finally {
      this._compoundFileBackInFlight = false;
    }
  }

  openCompoundAlchemyStart(suggest) {
    const item = suggest && typeof suggest === "object" ? suggest : {};
    const linkedRefs = Array.isArray(item.linked_refs) ? item.linked_refs : Array.isArray(item.linkedRefs) ? item.linkedRefs : [];
    this.openAlchemyStartModal({
      corpusId: String(item.corpus_id || item.corpusId || "").trim(),
      topic: String(item.topic || "").trim(),
      includeElixir: elixirIdFromLinkedRefs(linkedRefs),
    });
  }

  openReviewPageModal(prefill = {}) {
    this.openStructuredCommandModal(buildReviewPageModalSpec(this, prefill));
  }

  openReviewPageContextPicker(options = this.visibleReviewPageCandidates()) {
    this.openContextAwareAction({
      title: this.t("Pick Review Page"),
      description: this.t("Prefer an explicit review control object before falling back to manual page entry."),
      keyName: "pagePath",
      options,
      emptyNotice: this.t("No visible review backlog item is available; fell back to the manual form."),
      onFallback: () => this.openReviewPageModal(),
      onSubmit: (option) => this.openReviewPageTransitionPicker(option),
    });
  }

  openReviewPageTransitionPicker(control) {
    const pagePath = String(control.pagePath || control.path || control.value || "").trim();
    const currentStatus = String(control.currentStatus || control.current_status || control.status || "").trim();
    const confidence = String(control.confidence || "").trim();
    this.openTransitionPicker({
      title: this.t("Pick Review Transition"),
      description: this.t("Choose a valid next status for this review page."),
      controlType: "page",
      control,
      emptyNotice: this.t("No explicit review transition is available; fell back to the manual form."),
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

  async openView(viewType, options = {}) {
    let leaf = this.app.workspace.getLeavesOfType(viewType)[0];
    if (!leaf) {
      leaf = options.preferMain
        ? this.app.workspace.getLeaf(true)
        : (this.app.workspace.getRightLeaf(false) || this.app.workspace.getLeaf(true));
    }
    await leaf.setViewState({ type: viewType, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  async openFurnaceCenterView() {
    await this.openView(VIEW_TYPE_FURNACE_CENTER, { preferMain: true });
  }

  async openWorkspacePath(relativePath) {
    return openProductShellWorkspacePath(this, relativePath);
  }


  // --- Render method wrappers (delegate to render.js standalone functions) ---

  renderPanel(container, title, description = "", options = {}) {
    return renderPanel(this, container, title, description, options);
  }

  renderInlineButtons(container, buttons, cls = "furnace-shell-panel-actions") {
    return renderInlineButtons(this, container, buttons, cls);
  }

  renderPill(container, text, extraClass = "") {
    return renderPill(this, container, text, extraClass);
  }

  renderStatusPanel(container) {
    renderStatusPanel(this, container);
  }

  renderAdvancedDrawer(container) {
    renderAdvancedDrawer(this, container);
  }

  renderFurnaceCenter(contentEl) {
    renderFurnaceCenter(this, contentEl);
  }

  refreshOpenViews() {
    this.openViews.forEach((view) => {
      if (view && typeof view.render === "function") {
        view.render();
      }
    });
  }
};
