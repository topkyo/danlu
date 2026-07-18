// Main plugin class. Render methods delegate to standalone functions
// defined in render.js.

module.exports = class FurnaceProductShellPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
    this.pluginState = { recentRuns: [] };
    this.pendingSubmissions = []; // R89: 持久化 + runtime; status: running | received | done | failed | degraded; { id, payloadFingerprint, displayText, status, startedAt, finishedAt, error, reconcileTarget }
    this.longRunningPollTimer = null;
    this.longRunningPollRefreshInFlight = false;
    this.shellSummary = null;
    this.repoState = { valid: false, root: "", launcherPath: "", missingPaths: ["vault-root"] };
    this.openViews = new Set();
    this.statusBarItem = this.addStatusBarItem();

    await this.loadPluginState();
    this.refreshRepoState();
    if (typeof this.syncEvidenceGraphConfig === "function") {
      void this.syncEvidenceGraphConfig({ quiet: true }).catch(() => {});
    }

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
    this.updateLongRunningPoller();

    this.updateStatusBar();
  }

  async onunload() {
    this.stopLongRunningPoller();
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

  // R89: 启动时从持久化 settings hydrate；超过 TTL 24h 的 running/received → failed
  // R90: done 状态加 7 天 TTL（避免无限堆积）
  hydratePendingSubmissions(raw) {
    return hydratePendingSubmissionList(raw);
  }

  trimRecentRuns() {
    const limit = Math.max(1, Number.parseInt(String(this.settings.recentRunsLimit || DEFAULT_SETTINGS.recentRunsLimit), 10) || DEFAULT_SETTINGS.recentRunsLimit);
    this.pluginState.recentRuns = this.pluginState.recentRuns.slice(0, limit);
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

  getActiveOutputPath() {
    return getOutputPathForPath(this.getActiveFilePath());
  }

  getActiveCuratedPagePath() {
    return getCuratedPagePathForSummary(this.getActiveFilePath(), this.shellSummary);
  }

  normalizeRewriteProposalObjects(value) {
    return normalizeRewriteProposalObjects(value);
  }

  normalizeRewriteFollowupActions(value) {
    return normalizeRewriteFollowupActions(value);
  }

  rewriteProposalPathsFromObjects(objects) {
    return rewriteProposalPathsFromObjects(objects);
  }

  rewriteCandidatesForSlugs(slugs, mode = "review") {
    const normalized = new Set(normalizeRelativePathList(slugs));
    if (!normalized.size) {
      return [];
    }
    return this.rewriteControlItems(mode).filter((proposal) => normalized.has(String(proposal.slug || "").trim()));
  }

  rewriteProposalSummary(record) {
    return rewriteProposalSummary(this, record);
  }

  openRewriteFollowup(record) {
    return openRewriteFollowupForRecord(this, record);
  }

  openStructuredCommandModal(spec) {
    new StructuredCommandModal(this.app, this, spec).open();
  }

  openContextPicker(spec) {
    new ContextPickerModal(this.app, this, spec).open();
  }

  controlIdSet(key) {
    return controlIdSet(this, key);
  }

  reviewControlList(key) {
    return reviewControlList(this, key);
  }

  executionControlList(key) {
    return executionControlList(this, key);
  }

  reviewPageControlItems() {
    return reviewPageControlItems(this);
  }

  nextReviewCandidate() {
    const candidates = this.visibleReviewPageCandidates();
    return candidates.length ? candidates[0] : null;
  }

  reviewKindLabel(kind, count = 1) {
    return reviewKindLabel(this, kind, count);
  }

  commonReviewTransitionOptions(pages) {
    return commonReviewTransitionOptions(this, pages);
  }

  reviewBatchSuggestions() {
    return reviewBatchSuggestions(this);
  }

  rewriteControlItems(mode = "review") {
    return rewriteControlItems(this, mode);
  }

  actionControlItems(mode = "review") {
    return actionControlItems(this, mode);
  }

  archiveControlItems(mode = "apply") {
    return archiveControlItems(this, mode);
  }

  actionControlsById() {
    return actionControlsById(this);
  }

  archiveControlsById() {
    return archiveControlsById(this);
  }

  transitionLabel(controlType, transition) {
    return transitionLabel(this, controlType, transition);
  }

  transitionOptions(controlType, control) {
    return transitionOptions(this, controlType, control);
  }

  preferredTransitionOptions(controlType, control) {
    return preferredTransitionOptions(this, controlType, control);
  }

  manualReviewOption(controlType) {
    return manualReviewOption(this, controlType);
  }

  openTransitionPicker({ title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice }) {
    return openTransitionPickerForControl(this, { title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice });
  }

  async runReviewPageTransition(pagePath, status) {
    await this.runCliAction(`Review Page: ${status}`, "review-page", [pagePath, "--status", status]);
  }

  async runReviewRewriteTransition(slug, status) {
    new Notice(this.t("Concept rewrite commands were removed in W3; use review-page on the concept page instead."));
  }

  async runReviewActionTransition(actionId, status) {
    new Notice(this.t("Machine-memory action commands were removed in W3; use review-page instead."));
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
    return openContextAwareActionForSpec(this, spec);
  }

  async handleVaultChange(relativePath) {
    return handleProductShellVaultChange(this, relativePath);
  }

  async syncEvidenceGraphConfig({ quiet = true } = {}) {
    return syncProductShellEvidenceGraphConfig(this, { quiet });
  }

  async maybeRepairEvidenceGraphFilter() {
    return maybeRepairProductShellEvidenceGraphFilter(this);
  }

  async openEvidenceGraphView() {
    return openProductShellEvidenceGraphView(this);
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
    return resolveProductShellRunLogPath(this.repoState.root, relativePath);
  }

  persistRunLog(record, details = {}) {
    persistProductShellRunLog({
      record,
      details,
      t: this.t.bind(this),
      repoRoot: this.repoState.root || ".",
    });
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


  async runCompileCommand() {
    await this.runPluginCommand(this.t("Compile"), ["compile"], { refreshAfter: true });
  }

  async runNightlyCommand() {
    await this.runPluginCommand(this.t("Nightly"), ["nightly"], { refreshAfter: true });
  }

  async runTodaySnoozeCommand(target, days = 1) {
    new Notice(this.t("Today snooze was removed in W4; handle the item directly from Today."));
  }

  async runShellSearchCommand(query, limit = 8) {
    new Notice(this.t("Shell search was removed in W4; use Obsidian search and wiki pages instead."));
  }

  async runApplyAllAcceptedLowRiskCommand() {
    new Notice(this.t("Batch review was removed in W4; use review-page for explicit page transitions."));
  }

  async runRevertLastBatchCommand() {
    new Notice(this.t("Batch revert commands were removed in W3; inspect execution receipts manually."));
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

  markPendingSubmissionReceived(id) {
    return markPendingSubmissionRuntimeReceived(this, id);
  }

  markPendingSubmissionDone(id, reconcileTarget, reconcilePath) {
    return markPendingSubmissionRuntimeDone(this, id, reconcileTarget, reconcilePath);
  }

  isPendingSubmissionDegraded(entry) {
    return isPendingSubmissionDegradedEntry(entry);
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

  hasActiveLongRunningPending() {
    return pendingHasActiveLongRunning(this.pendingSubmissions);
  }

  updateLongRunningPoller() {
    return updateProductShellLongRunningPoller(this);
  }

  startLongRunningPoller() {
    return startProductShellLongRunningPoller(this);
  }

  stopLongRunningPoller() {
    return stopProductShellLongRunningPoller(this);
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

  async runAskCommand({ question, format, mode }) {
    return runProductShellAskCommand(this, { question, format, mode });
  }

  async runDroppedPayloadsWithAutoAsk({ payloads, question }) {
    return runProductShellDroppedPayloadsWithAutoAsk(this, { payloads, question });
  }

  completePendingMaterialDrop(id, materialPaths) {
    return completeProductShellPendingMaterialDrop(this, id, materialPaths);
  }

  async runDroppedFilesWithAutoAsk({ files, question }) {
    return runProductShellDroppedFilesWithAutoAsk(this, { files, question });
  }

  async runReportSubgraphCommand({ reportPath }) {
    new Notice(this.t("Report subgraph was removed in W4; open graph artifacts from output/ manually if needed."));
  }

  collectReportCandidates() {
    return [];
  }

  openReportSubgraphPicker() {
    this.runReportSubgraphCommand({ reportPath: "" });
  }

  async runDropUrlCommand({ url, title }) {
    return runProductShellDropUrlCommand(this, { url, title });
  }

  openDropUrlModal(initialUrl = "") {
    new DropUrlModal(this.app, this).setInitialUrl(initialUrl).open();
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

  async runLauncherCommand(fullCommandStr, label = "Suggested Action") {
    return runProductShellLauncherCommand(this, fullCommandStr, label);
  }

  openFileBackModal(prefill = {}) {
    this.openStructuredCommandModal(buildFileBackModalSpec(this, prefill));
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
    const label = String(item.title || this.t("沉淀")).trim() || this.t("沉淀");
    await this.runCliAction(label, "file-back", [reportPath]);
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

  openReviewRewriteModal(_prefill = {}) {
    new Notice(this.t("Concept rewrite commands were removed in W3; use review-page on the concept page instead."));
  }

  openApplyRewriteModal(_prefill = {}) {
    new Notice(this.t("Concept rewrite commands were removed in W3; use review-page on the concept page instead."));
  }

  openRetireConceptModal(_prefill = {}) {
    new Notice(this.t("Concept retire/reactivate commands were removed in W3; use review-page instead."));
  }

  openReactivateConceptModal(_prefill = {}) {
    new Notice(this.t("Concept retire/reactivate commands were removed in W3; use review-page instead."));
  }

  openApplyArchiveModal(_prefill = {}) {
    new Notice(this.t("Archive commands were removed in W3; inspect manifest pages manually."));
  }

  openRevertArchiveModal(_prefill = {}) {
    new Notice(this.t("Archive commands were removed in W3; inspect manifest pages manually."));
  }

  openReviewActionModal(prefill = {}) {
    this.openStructuredCommandModal(buildReviewActionModalSpec(this, prefill));
  }

  openApplyActionModal(prefill = {}) {
    this.openStructuredCommandModal(buildApplyActionModalSpec(this, prefill));
  }

  openRevertActionModal(prefill = {}) {
    this.openStructuredCommandModal(buildRevertActionModalSpec(this, prefill));
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

  openReviewRewriteContextPicker(_options = this.visibleRewriteCandidates()) {
    new Notice(this.t("Concept rewrite commands were removed in W3; use review-page on the concept page instead."));
  }

  openReviewActionContextPicker(_options = this.visibleActionCandidates("review")) {
    new Notice(this.t("Machine-memory action commands were removed in W3; use review-page instead."));
  }

  openApplyArchiveContextPicker(_options = this.visibleArchiveCandidates("apply")) {
    new Notice(this.t("Archive commands were removed in W3; inspect manifest pages manually."));
  }

  openRevertArchiveContextPicker(_options = this.visibleArchiveCandidates("revert")) {
    new Notice(this.t("Archive commands were removed in W3; inspect manifest pages manually."));
  }

  openApplyActionContextPicker(options = this.visibleActionCandidates("apply")) {
    this.openContextAwareAction({
      title: this.t("Pick Apply Action"),
      description: this.t("Prefer an explicit action control object before falling back to manual action id entry."),
      keyName: "actionId",
      options,
      emptyNotice: this.t("No visible machine-memory action context is available; fell back to the manual form."),
      onFallback: () => this.openApplyActionModal(),
      onSubmit: (option) => this.openApplyActionModal({ actionId: option.actionId || option.value || "", bundle: option.bundlePath || "" }),
    });
  }

  openRevertActionContextPicker(options = this.visibleActionCandidates("revert")) {
    this.openContextAwareAction({
      title: this.t("Pick Revert Action"),
      description: this.t("Prefer an explicit action control object before falling back to manual action id entry."),
      keyName: "actionId",
      options,
      emptyNotice: this.t("No visible machine-memory action context is available; fell back to the manual form."),
      onFallback: () => this.openRevertActionModal(),
      onSubmit: (option) => this.openRevertActionModal({ actionId: option.actionId || option.value || "" }),
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

  openReviewRewriteTransitionPicker(_control) {
    new Notice(this.t("Concept rewrite commands were removed in W3; use review-page on the concept page instead."));
  }

  openReviewActionTransitionPicker(_control) {
    new Notice(this.t("Machine-memory action commands were removed in W3; use review-page instead."));
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

  renderCardGrid(container, cards) {
    renderCardGrid(this, container, cards);
  }

  renderActionButtons(container, buttons) {
    renderActionButtons(this, container, buttons);
  }

  renderPanel(container, title, description = "", options = {}) {
    return renderPanel(this, container, title, description, options);
  }

  renderInlineButtons(container, buttons, cls = "furnace-shell-panel-actions") {
    return renderInlineButtons(this, container, buttons, cls);
  }

  renderPill(container, text, extraClass = "") {
    return renderPill(this, container, text, extraClass);
  }

  renderMainHeader(container) {
    renderMainHeader(this, container);
  }

  renderMaterialPanel(container) {
    renderMaterialPanel(this, container);
  }

  renderOutputsPanel(container) {
    renderOutputsPanel(this, container);
  }

  renderStatusPanel(container) {
    renderStatusPanel(this, container);
  }

  renderNextActionsPanel(container) {
    renderNextActionsPanel(this, container);
  }

  renderDigestRow(container, label, value) {
    renderDigestRow(this, container, label, value);
  }

  renderDigestPanel(container) {
    renderDigestPanel(this, container);
  }

  
  renderReportsPanel(container, reports) {
    renderReportsPanel(this, container, reports);
  }
  renderReportsGroup(container, reports, emptyText) {
    renderReportsGroup(this, container, reports, emptyText);
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
