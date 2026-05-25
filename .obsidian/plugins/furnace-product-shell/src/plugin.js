// Main plugin class. Render methods delegate to standalone functions
// defined in render.js.

module.exports = class FurnaceProductShellPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
    this.pluginState = { recentRuns: [] };
    this.pendingSubmissions = []; // R89: 持久化 + runtime; status: running | received | done | failed | degraded; { id, payloadFingerprint, displayText, status, startedAt, finishedAt, error, reconcileTarget }
    this.longRunningPollTimer = null;
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
    this.registerView(VIEW_TYPE_RECENT_RUNS, (leaf) => new RecentRunsView(leaf, this));
    this.registerView(VIEW_TYPE_REVIEW_CENTER, (leaf) => new ReviewCenterView(leaf, this));
    this.registerView(VIEW_TYPE_EXECUTION_CENTER, (leaf) => new ExecutionCenterView(leaf, this));
    this.addSettingTab(new FurnaceProductShellSettingTab(this.app, this));

    this.addRibbonIcon("flask-conical", this.t("Open Furnace"), () => {
      this.runUiAction(() => this.openFurnaceCenterView(), this.t("Open Furnace"));
    });

    this.registerPublicCommands();
    this.registerAdvancedCommands();

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
    this.updateLongRunningPoller();

    this.updateStatusBar();
  }

  async onunload() {
    this.stopLongRunningPoller();
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
    // EP-005: kept for backward compatibility — these views can still be opened individually,
    // but Furnace Center now also surfaces a unified activity timeline.
    this.addCommand({
      id: "open-recent-runs",
      name: this.t("Open Recent Runs"),
      callback: () => {
        this.runUiAction(() => this.openRecentRunsView(), this.t("Open Recent Runs"));
      },
    });
    this.addCommand({
      id: "open-review-center",
      name: this.t("Open Review Center"),
      callback: () => {
        this.runUiAction(() => this.openReviewCenterView(), this.t("Open Review Center"));
      },
    });
    this.addCommand({
      id: "open-execution-center",
      name: this.t("Open Execution Center"),
      callback: () => {
        this.runUiAction(() => this.openExecutionCenterView(), this.t("Open Execution Center"));
      },
    });
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
    const data = (await this.loadData()) || {};
    const rawSettings = data.settings && typeof data.settings === "object" ? data.settings : {};
    this.rawPluginData = data;
    this.settings = Object.assign({}, DEFAULT_SETTINGS, rawSettings);
    if (this.settings.defaultAskFormat === "report") {
      this.settings.defaultAskFormat = "note";
    }
    const legacyShowHtmlShortcutsMigrated = Object.prototype.hasOwnProperty.call(this.settings, "showHtmlShortcuts");
    delete this.settings.showHtmlShortcuts;
    const legacyDefaultAskModeMigrated = Object.prototype.hasOwnProperty.call(this.settings, "defaultAskMode");
    delete this.settings.defaultAskMode;
    const rawAdvancedSectionsExpanded = this.settings.advancedSectionsExpanded && typeof this.settings.advancedSectionsExpanded === "object"
      ? this.settings.advancedSectionsExpanded
      : {};
    const migratedAdvancedSectionsExpanded = {
      status: Boolean(rawAdvancedSectionsExpanded.status),
      history: Boolean(rawAdvancedSectionsExpanded.history),
    };
    const advancedSectionsExpandedMigrated = JSON.stringify(this.settings.advancedSectionsExpanded || {}) !== JSON.stringify(migratedAdvancedSectionsExpanded);
    this.settings.advancedSectionsExpanded = migratedAdvancedSectionsExpanded;
    const legacyLlmSettingsMigrated = dropLegacyLlmSettings(this.settings);
    this.settings.locale = normalizeLocale(this.settings.locale);
    const migratedFeishuWebhookUrl = String(this.settings.feishuWebhookUrl || this.settings.feishu_webhook_url || "").trim();
    const feishuWebhookUrlMigrated = this.settings.feishuWebhookUrl !== migratedFeishuWebhookUrl;
    this.settings.feishuWebhookUrl = migratedFeishuWebhookUrl;
    const migratedWecomWebhookUrl = String(this.settings.wecomWebhookUrl || this.settings.wecom_webhook_url || "").trim();
    const wecomWebhookUrlMigrated = this.settings.wecomWebhookUrl !== migratedWecomWebhookUrl;
    this.settings.wecomWebhookUrl = migratedWecomWebhookUrl;
    const rawEnabledChannels = Array.isArray(rawSettings.enabledChannels)
      ? rawSettings.enabledChannels
      : rawSettings.enabled_channels;
    const migratedEnabledChannels = normalizeEnabledChannels(rawEnabledChannels);
    const enabledChannelsMigrated = JSON.stringify(this.settings.enabledChannels || []) !== JSON.stringify(migratedEnabledChannels);
    this.settings.enabledChannels = migratedEnabledChannels;
    const migratedLastViewedTimestamp = normalizeLastViewedTimestamp(this.settings.lastViewedTimestamp);
    const lastViewedTimestampMigrated = this.settings.lastViewedTimestamp !== migratedLastViewedTimestamp;
    this.settings.lastViewedTimestamp = migratedLastViewedTimestamp;
    // R89: hydrate pendingSubmissions from settings; TTL 24h stale running → failed
    this.pendingSubmissions = this.hydratePendingSubmissions(this.settings.persistedPendingSubmissions);
    const recentRuns = normalizeProductShellRecentRuns(data.recentRuns);
    this.pluginState = { recentRuns };
    this.trimRecentRuns();
    const defaultAskFormatMigrated = rawSettings.defaultAskFormat === "report";
    if (feishuWebhookUrlMigrated || wecomWebhookUrlMigrated || enabledChannelsMigrated || lastViewedTimestampMigrated || legacyLlmSettingsMigrated || defaultAskFormatMigrated || legacyShowHtmlShortcutsMigrated || legacyDefaultAskModeMigrated || advancedSectionsExpandedMigrated) {
      await this.savePluginState();
    }
  }

  async savePluginState() {
    await this.saveData({
      settings: Object.assign({}, this.settings, {
        // R89: 把 pending 持久化到 settings；只存最近 8 条 running/received/failed/done
        persistedPendingSubmissions: this.serializePendingSubmissions(),
      }),
      recentRuns: this.pluginState.recentRuns,
    });
  }

  // R91: Advanced 抽屉子 section 折叠态读写。默认全折叠（status/history）。
  getAdvancedSectionExpanded(key) {
    const s = this.settings && this.settings.advancedSectionsExpanded;
    if (!s || typeof s !== "object") return false;
    return Boolean(s[key]);
  }

  async setAdvancedSectionExpanded(key, value) {
    if (key !== "status" && key !== "history") {
      return;
    }
    const current = this.settings && this.settings.advancedSectionsExpanded;
    // 强制 own object，避免与 DEFAULT_SETTINGS 共享引用导致默认值被 mutate
    const next = {
      status: Boolean(current && typeof current === "object" && current.status),
      history: Boolean(current && typeof current === "object" && current.history),
    };
    next[key] = Boolean(value);
    this.settings.advancedSectionsExpanded = next;
    try {
      await this.savePluginState();
    } catch (error) {
      // 折叠态写失败不影响 UI
    }
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

  getAvailableProtocols() {
    return getAvailableProtocolsFromSummary(this.shellSummary);
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

  normalizeRewriteRecoveryActions(value) {
    return normalizeRewriteRecoveryActions(value);
  }

  rewriteProposalPathsFromObjects(objects) {
    return rewriteProposalPathsFromObjects(objects);
  }

  rewriteProposalSlugsFromObjects(objects) {
    return rewriteProposalSlugsFromObjects(objects);
  }

  extractRewriteProposalObjects(payload) {
    return extractRewriteProposalObjects(payload);
  }

  extractRewriteRecoveryActions(payload) {
    return extractRewriteRecoveryActions(payload);
  }

  extractRewriteProposalPaths(payload) {
    return extractRewriteProposalPaths(payload);
  }

  extractRewriteProposalSlugs(paths) {
    return extractRewriteProposalSlugs(paths);
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

  openRewriteRecovery(record) {
    return openRewriteRecoveryForRecord(this, record);
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

  async runReviewPageBatchTransition(pagePaths, status, note = "", confidence = "") {
    const normalizedPaths = Array.isArray(pagePaths)
      ? Array.from(new Set(pagePaths.map((pagePath) => String(pagePath || "").trim()).filter(Boolean)))
      : [];
    if (!normalizedPaths.length) {
      throw new Error(this.t("Batch review requires at least one page path."));
    }
    const args = ["--batch", ...normalizedPaths, "--status", status];
    appendOptionalArg(args, "--note", note);
    appendOptionalArg(args, "--confidence", confidence);
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
    return openContextAwareActionForSpec(this, spec);
  }

  async handleVaultChange(relativePath) {
    if (!relativePath) {
      return;
    }
    if (relativePath === ".obsidian/graph.json" && typeof this.maybeRepairEvidenceGraphFilter === "function") {
      void this.maybeRepairEvidenceGraphFilter().catch(() => {});
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

  async syncEvidenceGraphConfig({ quiet = true } = {}) {
    if (!this.repoState.valid) {
      return null;
    }
    try {
      return await this.execLauncher(["sync-evidence-graph"]);
    } catch (error) {
      if (!quiet) {
        console.error("[furnace-product-shell] sync-evidence-graph failed", error);
      }
      return null;
    }
  }

  async maybeRepairEvidenceGraphFilter() {
    const adapter = this.app.vault.adapter;
    const graphPath = ".obsidian/graph.json";
    if (!(await adapter.exists(graphPath))) {
      return;
    }
    try {
      const raw = await adapter.read(graphPath);
      const parsed = JSON.parse(raw);
      const search = String(parsed.search || "").trim();
      if (!search || search.includes("wiki/concepts")) {
        await this.syncEvidenceGraphConfig({ quiet: true });
      }
    } catch {
      await this.syncEvidenceGraphConfig({ quiet: true });
    }
  }

  async openEvidenceGraphView() {
    await this.syncEvidenceGraphConfig({ quiet: false });
    await this.openWorkspacePath("wiki/evidence-graph.md");
    if (this.app.commands?.executeCommandById) {
      await this.app.commands.executeCommandById("graph:open");
    }
  }

  updateStatusBar() {
    if (!this.statusBarItem) {
      return;
    }
    const runningCount = this.pluginState.recentRuns.filter((entry) => entry.status === "running").length;
    if (!this.repoState.valid) {
      this.statusBarItem.setText(this.t("Furnace shell unavailable"));
      this.statusBarItem.setAttribute("aria-label", this.t("Missing runtime paths: {missing}", { missing: this.repoState.missingPaths.join(", ") }));
      return;
    }
    const protocol = this.getActiveProtocol();
    const llmHealth = this.currentLlmHealth();
    const syncState = this.currentShellSyncState();
    const llmSuffix = llmHealth.status === "degraded" ? this.t(" | llm degraded") : "";
    const syncSuffix = syncState.status === "running" ? this.t(" | syncing") : "";
    const suffix = runningCount ? this.t(" | running {count}", { count: runningCount }) : "";
    this.statusBarItem.setText(`${this.t("Furnace")} ${protocol}${llmSuffix}${syncSuffix}${suffix}`);
    this.statusBarItem.setAttribute("aria-label", this.t("Furnace Product Shell active protocol {protocol}", { protocol }));
  }

  async loadShellSummaryFromDisk() {
    if (!this.repoState.valid) {
      this.shellSummary = null;
      this.updateStatusBar();
      this.refreshOpenViews();
      return null;
    }
    let text = null;
    const summaryFile = this.app.vault.getAbstractFileByPath(SHELL_SUMMARY_PATH);
    if (summaryFile) {
      try {
        text = await this.app.vault.cachedRead(summaryFile);
      } catch (error) {
        console.error("[furnace-product-shell] vault read failed for shell summary, falling back to fs", error);
        text = null;
      }
    }
    // Fallback: vault may exclude output/control/ via userIgnoreFilters,
    // so getAbstractFileByPath returns null. Read from fs directly.
    if (text === null && this.repoState.root) {
      const absPath = path.join(this.repoState.root, SHELL_SUMMARY_PATH);
      try {
        if (fs.existsSync(absPath)) {
          text = fs.readFileSync(absPath, "utf8");
        }
      } catch (error) {
        console.error("[furnace-product-shell] fs read failed for shell summary", error);
        text = null;
      }
    }
    if (text === null) {
      this.shellSummary = null;
      this.updateStatusBar();
      this.refreshOpenViews();
      return null;
    }
    try {
      this.shellSummary = readJsonText(text);
      this.processShellSummaryUpdates(this.shellSummary);
    } catch (error) {
      console.error("[furnace-product-shell] failed to parse shell summary", error);
      this.shellSummary = null;
    }
    this.updateStatusBar();
    this.refreshOpenViews();
    return this.shellSummary;
  }

  async execLauncher(args) { return execLauncher(this, args); }

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
    if (!normalized || !this.repoState.root) {
      return "";
    }
    return path.join(this.repoState.root, normalized);
  }

  persistRunLog(record, details = {}) {
    const rendered = renderProductShellRunLog({
      record,
      details,
      t: this.t.bind(this),
      repoRoot: this.repoState.root || ".",
    });
    if (!rendered) return;
    const absolutePath = this.resolveAbsoluteWorkspacePath(rendered.logPath);
    if (!absolutePath) return;
    record.logPath = rendered.logPath;
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, rendered.content, "utf8");
  }

  async copyText(value) {
    const text = String(value || "").trim();
    if (!text) {
      new Notice(this.t("Nothing to copy."));
      return false;
    }
    if (clipboard && typeof clipboard.writeText === "function") {
      clipboard.writeText(text);
      new Notice(this.t("Copied to clipboard."));
      return true;
    }
    if (window.navigator && window.navigator.clipboard && typeof window.navigator.clipboard.writeText === "function") {
      await window.navigator.clipboard.writeText(text);
      new Notice(this.t("Copied to clipboard."));
      return true;
    }
    new Notice(this.t("Clipboard is not available in this environment."));
    return false;
  }

  async revealWorkspacePath(relativePath) {
    const normalized = String(relativePath || "").trim();
    const absolutePath = this.resolveAbsoluteWorkspacePath(normalized);
    if (!normalized || !absolutePath || !fs.existsSync(absolutePath)) {
      new Notice(this.t("Path not found: {path}", { path: normalized || relativePath || "" }));
      return;
    }
    if (shell && typeof shell.showItemInFolder === "function") {
      shell.showItemInFolder(absolutePath);
      return;
    }
    if (shell && typeof shell.openPath === "function") {
      await shell.openPath(path.dirname(absolutePath));
      return;
    }
    new Notice(this.t("Unable to reveal {path}", { path: normalized }));
  }

  createRunRecord(label, args) {
    const record = createProductShellRunRecord({
      label,
      args,
      llm: this.currentLlmSelection(),
      protocol: this.getActiveProtocol(),
    });
    this.pluginState.recentRuns.unshift(record);
    this.trimRecentRuns();
    this.persistRunLog(record);
    this.updateStatusBar();
    this.refreshOpenViews();
    void this.savePluginState();
    return record;
  }

  updateRunRecord(record, updates) {
    Object.assign(record, updates);
    this.trimRecentRuns();
    this.persistRunLog(record);
    this.updateStatusBar();
    this.refreshOpenViews();
    void this.savePluginState();
  }

  latestPluginRun() {
    return this.pluginState.recentRuns.length ? this.pluginState.recentRuns[0] : null;
  }

  async rerunRecord(record) {
    const argv = record && Array.isArray(record.argv) ? record.argv.map((value) => String(value || "")) : [];
    if (!argv.length) {
      new Notice(this.t("Cannot re-run this entry because argv was not recorded."));
      return null;
    }
    return await this.runPluginCommand(record.label || record.args || this.t("command"), argv, { refreshAfter: true });
  }

  async runPluginCommand(label, args, options = {}) {
    const record = this.createRunRecord(label, args);
    appendRunEvent(record, "Executing", args.join(" "), "running");
    if (options.longRunning) {
      appendRunEvent(
        record,
        "Long report task",
        this.t("Report generation can take several minutes; keep this card open and refresh status if needed."),
        "running"
      );
    }
    this.updateRunRecord(record, {});
    try {
      const result = await this.execLauncher(args);
      const primaryPath = extractPrimaryPath(result.payload);
      const receiptPath = result.payload && typeof result.payload.receipt_path === "string" ? result.payload.receipt_path : "";
      const rewriteProposalObjects = this.extractRewriteProposalObjects(result.payload);
      const rewriteRecoveryActions = this.extractRewriteRecoveryActions(result.payload);
      const rewriteProposalPaths = this.extractRewriteProposalPaths(result.payload);
      const rewriteProposalSlugs = rewriteProposalObjects.length
        ? this.rewriteProposalSlugsFromObjects(rewriteProposalObjects)
        : this.extractRewriteProposalSlugs(rewriteProposalPaths);
      if (options.updateSummaryFromPayload && result.payload && result.payload.kind === "product-shell-summary") {
        this.shellSummary = result.payload;
        this.processShellSummaryUpdates(this.shellSummary);
        this.updateStatusBar();
        this.refreshOpenViews();
      } else if (options.refreshAfter !== false) {
        await this.refreshShellSummarySilently();
      }
      const llm = this.currentLlmSelection();
      if (options.backgroundSubmit && result.payload && result.payload.kind === "run-ask-background-job") {
        appendRunEvent(
          record,
          "Background job submitted",
          result.payload.job_id || result.payload.path || this.t("Long report job accepted."),
          "running"
        );
        this.updateRunRecord(record, buildProductShellBackgroundRunUpdates({ result, primaryPath }));
        this.persistRunLog(record, { stdoutRaw: result.stdout, stderrRaw: result.stderr });
        this.updateLongRunningPoller();
        if (options.notice !== false) {
          new Notice(this.t("Long report job accepted. The report card will update after background completion."));
        }
        return result.payload;
      }
      const degradedRun = isProductShellDegradedRun(record, result.payload);
      appendRunEvent(
        record,
        degradedRun ? "LLM timeout" : "Completed",
        degradedRun
          ? (result.payload && (result.payload.primary_error || result.payload.fallback_reason) || this.t("LLM timed out; deterministic fallback only."))
          : (primaryPath || receiptPath || this.t("Command completed successfully.")),
        degradedRun ? "degraded" : "success"
      );
      if (primaryPath || receiptPath) {
        appendRunEvent(record, "Artifacts", [primaryPath, receiptPath].filter(Boolean).join(" · "), "success");
      }
      if (rewriteProposalPaths.length) {
        appendRunEvent(record, "Rewrite proposals", this.rewriteProposalSummary({ rewriteProposalPaths }), "success");
      }
      this.updateRunRecord(record, buildProductShellCompletedRunUpdates({
        record,
        result,
        llm,
        primaryPath,
        receiptPath,
        rewriteProposalObjects,
        rewriteRecoveryActions,
        rewriteProposalPaths,
        rewriteProposalSlugs,
      }));
      if (record.command === "run-ask" || record.command === "run-ask-resume") {
        const usedFallback = Boolean(record.fallbackUsed) || String(record.deliveryMode || "").trim() === "deterministic-fallback";
        this.recordLlmHealthFromRun(record, {
          status: usedFallback ? "degraded" : "healthy",
          reason: usedFallback ? "LLM timed out or failed; only deterministic fallback is available." : "Recent run-ask succeeded.",
          source: "run-ask",
          fallbackCommand: usedFallback ? (record.fallbackCommand || "ask") : "",
          backendRequested: record.backendRequested,
          backendEffective: record.backendEffective,
          modelSelected: record.modelSelected,
          modelFinal: record.modelFinal,
          fallbackStage: record.fallbackStage,
          fallbackReason: record.fallbackReason,
          contractValidated: record.contractValidated,
        });
      }
      this.persistRunLog(record, { stdoutRaw: result.stdout, stderrRaw: result.stderr });
      if (options.notice !== false) {
        new Notice(
          degradedRun
            ? this.t("LLM timed out; deterministic fallback only. Open the artifact for local context, then retry or switch model.")
            : `${this.t(label)} ${this.t("completed")}.`
        );
      }
      return result.payload;
    } catch (error) {
      appendRunEvent(record, "Failed", truncateText(error.message || "Command failed", 180), "failed");
      this.updateRunRecord(record, buildProductShellFailedRunUpdates(error));
      if ((record.command === "run-ask" || record.command === "run-ask-resume") && llmBackendUnavailable(error)) {
        this.recordLlmHealthFromRun(record, {
          status: "degraded",
          reason: truncateText(error.message || error.stderr || error.stdout || "LLM backend unavailable", 240),
          source: "run-ask",
          fallbackCommand: "ask",
          backendRequested: record.backendRequested,
          backendEffective: record.backendEffective,
          modelSelected: record.modelSelected,
          modelFinal: record.modelFinal,
          fallbackStage: record.fallbackStage,
          fallbackReason: record.fallbackReason,
          contractValidated: record.contractValidated,
          stderrSummary: truncateText(error.stderr || ""),
          stderrRaw: trimDiagnosticText(error.stderr || error.stdout || ""),
        });
      }
      this.persistRunLog(record, {
        stdoutRaw: error.stdout || "",
        stderrRaw: error.stderr || "",
      });
      new Notice(`${this.t(label)} ${this.t("failed: {message}", { message: truncateText(error.message || this.t("unknown error"), 120) })}`);
      throw error;
    }
  }

  async refreshShellSummarySilently() {
    try {
      const result = await this.execLauncher(["shell-status"]);
      if (result.payload && result.payload.kind === "product-shell-summary") {
        this.shellSummary = result.payload;
        this.processShellSummaryUpdates(this.shellSummary);
        this.updateStatusBar();
        this.refreshOpenViews();
        return result.payload;
      }
    } catch (error) {
      console.error("[furnace-product-shell] shell-status refresh failed", error);
    }
    return await this.loadShellSummaryFromDisk();
  }

  
  processShellSummaryUpdates(summary) {
    // R88: shellSummary 刷新时尝试消解已落地的 pending submissions（视觉闭环）
    this.reconcilePendingSubmissions(summary);
    const update = knownReportIdsUpdateFromSummary(summary, this.settings.lastKnownReportIds);
    if (update.shouldSave) {
      this.settings.lastKnownReportIds = update.ids;
      void this.savePluginState();
    }
  }

  async refreshShellSummaryCommand() {
    // R90 P1: 保证无论 payload 形态如何，都重新基于磁盘 summary 触发 reconcile。
    // updateSummaryFromPayload 仅在 payload.kind === "product-shell-summary" 时生效；
    // 若 launcher 返回旧/异常 payload，显式 fallback loadShellSummaryFromDisk()。
    try {
      await this.runPluginCommand(this.t("Refresh Furnace Shell"), ["shell-status"], {
        refreshAfter: false,
        updateSummaryFromPayload: true,
        notice: false,
      });
    } catch (error) {
      // 失败也尝试基于磁盘 summary 推进 reconcile，避免"刷新状态"完全无反馈
    }
    await this.loadShellSummaryFromDisk();
  }

  // R90: done 卡"打开报告/查看回执"统一入口；处理 path 缺失 + open 失败 + 用户反馈
  async openPendingDoneTarget(target, reconcilePath) {
    const normalizedPath = String(reconcilePath || "").trim();
    const normalizedTarget = String(target || "").trim();
    if (normalizedPath) {
      let opened = false;
      try {
        // openWorkspacePath 返回 boolean：path 缺失 / repo missing / not found / no adapter 时为 false
        opened = await this.openWorkspacePath(normalizedPath);
      } catch (error) {
        opened = false;
      }
      if (opened) return;
    }
    // 退化：outputs → Outputs Hub；receipts → Recent Runs；其余 → HOME.md
    try {
      if (normalizedTarget === "outputs" && typeof this.openOutputsHub === "function") {
        await this.openOutputsHub();
        new Notice(this.t("已打开输出汇总（找不到具体报告路径）"));
        return;
      }
      if (normalizedTarget === "receipts" && typeof this.openRecentRunsView === "function") {
        await this.openRecentRunsView();
        new Notice(this.t("已打开运行记录（找不到具体回执路径）"));
        return;
      }
      if (typeof this.openHomeNote === "function") {
        await this.openHomeNote();
        return;
      }
    } catch (error) {
      // 最后兜底：通知失败
    }
    new Notice(this.t("无法打开目标，可能尚未生成"));
  }

  async readWorkspaceSnippet(relativePath, length = 420) {
    const resolvedPath = resolveWorkspaceSnippetPath(this.repoState.root, relativePath);
    if (!resolvedPath) return "";
    try {
      const raw = await fs.promises.readFile(resolvedPath, "utf8");
      return workspaceSnippetFromMarkdown(raw, length);
    } catch (error) {
      return "";
    }
  }

  quoteFileToComposer(relativePath) {
    const normalized = String(relativePath || "").trim();
    if (!normalized) return false;
    const textarea = document.querySelector(".furnace-universal-input-textarea");
    if (!textarea) {
      new Notice(this.t("找不到输入框，无法引用报告"));
      return false;
    }
    const quoteLine = this.t("引用报告：{path}", { path: normalized });
    const update = appendComposerReportQuote(textarea.value, quoteLine);
    if (update.changed) {
      textarea.value = update.value;
    }
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.focus();
    try { textarea.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (error) {}
    return true;
  }


  async runCompileCommand() {
    await this.runPluginCommand(this.t("Compile"), ["compile"], { refreshAfter: true });
  }

  async runNightlyCommand() {
    await this.runPluginCommand(this.t("Nightly"), ["nightly"], { refreshAfter: true });
  }

  async runTodaySnoozeCommand(target, days = 1) {
    const normalizedTarget = String(target || "").trim();
    if (!normalizedTarget) {
      return;
    }
    await this.runPluginCommand(
      `${this.t("Snooze")}: ${truncateText(normalizedTarget, 48)}`,
      ["today-snooze", normalizedTarget, "--days", String(days)],
      { refreshAfter: true }
    );
  }

  async runShellSearchCommand(query, limit = 8) {
    const normalizedQuery = String(query || "").trim();
    if (!normalizedQuery) {
      new Notice(this.t("Search query cannot be empty."));
      return;
    }
    const parsedLimit = Number.parseInt(String(limit || 8), 10);
    await this.runPluginCommand(
      `${this.t("Search")}: ${truncateText(normalizedQuery, 48)}`,
      ["search", normalizedQuery, "--limit", String(Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 8)],
      { refreshAfter: false, notice: false }
    );
    await this.loadShellSummaryFromDisk();
    new Notice(this.t("Search completed: {query}", { query: truncateText(normalizedQuery, 60) }));
  }

  async runApplyAllAcceptedLowRiskCommand() {
    await this.runCliAction(this.t("Apply All Low-Risk"), "apply-action", ["--all-accepted-low-risk"]);
  }

  async runRevertLastBatchCommand() {
    await this.runCliAction(this.t("Revert Last Batch"), "revert-action", ["--last-batch"]);
  }

  async openHomeNote() {
    await this.openWorkspacePath("HOME.md");
  }

  async openOutputsHub() {
    const links = this.shellSummary && typeof this.shellSummary === "object" ? this.shellSummary.links || {} : {};
    const preferredPath = String(links.output_packs_markdown || "docs/Outputs.md").trim();
    await this.openWorkspacePath(preferredPath);
  }

  async runProtocolSetCommand(protocol) {
    await this.runPluginCommand(`${this.t("Set Protocol")}: ${protocol}`, ["protocol-set", protocol], { refreshAfter: true });
  }

  // ---------------- Pending submissions (R88 + R89 持久化 + 两段式) ----------------
  // 用户提交后立即出现的"处理中"卡片，独立于 recentRuns（命令历史）和
  // shellSummary（事实层）。R89: 持久化到 plugin state；status = running | received | done | failed | degraded。
  pushPendingSubmission(displayText, opts = {}) {
    const text = String(displayText || "").trim();
    if (!text) return null;
    if (!Array.isArray(this.pendingSubmissions)) this.pendingSubmissions = [];
    const fingerprint = text.slice(0, 80);
    // R88 P2 fix: 同 fingerprint 仍在 running 的 pending 直接复用
    const dup = this.pendingSubmissions.find((e) => e && e.status === "running" && e.payloadFingerprint === fingerprint);
    if (dup) return dup.id;
    const id = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const entry = createPendingSubmissionEntry({
      id,
      displayText: text,
      opts,
      startedAt: new Date().toISOString(),
    });
    if (!entry) return null;
    this.pendingSubmissions.unshift(entry);
    if (this.pendingSubmissions.length > 8) this.pendingSubmissions.length = 8;
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
    return id;
  }

  resetPendingSubmissionForRetry(id) {
    const entry = this._findPending(id);
    if (!entry) return;
    resetPendingSubmissionEntryForRetry(entry, new Date().toISOString());
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
  }

  // R89: handleSubmit 成功 → received（"已接收，等待生成报告"）；不自动消失
  // 防御：仅在 running 时切换；若 reconcile 已抢先把它升到 done，不要回退
  markPendingSubmissionReceived(id) {
    const entry = this._findPending(id);
    if (!entry) return;
    if (!markPendingSubmissionEntryReceived(entry, new Date().toISOString())) return;
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
  }

  // R90: reconcile 命中 → done/degraded（"报告已生成" / "恢复产物已保留" / "已记录"）
  // reconcileTarget: "outputs" | "receipts" | "raw"; reconcilePath: cand.path / stored_path（可空）
  // 不再 4s 自动消失：done 卡变行动卡，由用户点"打开报告/查看回执/完成"主动 dismiss
  // 防御：terminal states 不应再被升到 done
  markPendingSubmissionDone(id, reconcileTarget, reconcilePath) {
    const entry = this._findPending(id);
    if (!entry) return;
    if (!markPendingSubmissionEntryDone(entry, reconcileTarget, reconcilePath, new Date().toISOString())) return;
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
  }

  isPendingSubmissionDegraded(entry) {
    return isPendingSubmissionDegradedEntry(entry);
  }

  markPendingSubmissionFailed(id, error) {
    const entry = this._findPending(id);
    if (!entry) return;
    markPendingSubmissionEntryFailed(entry, truncateText(String((error && error.message) || error || "失败"), 180), new Date().toISOString());
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
  }

  removePendingSubmission(id) {
    if (!Array.isArray(this.pendingSubmissions) || !this.pendingSubmissions.length) return;
    const before = this.pendingSubmissions.length;
    this.pendingSubmissions = this.pendingSubmissions.filter((e) => e && e.id !== id);
    if (this.pendingSubmissions.length !== before) {
      void this.savePluginState();
      this.refreshOpenViews();
      this.updateLongRunningPoller();
    }
  }

  _findPending(id) {
    if (!Array.isArray(this.pendingSubmissions)) return null;
    return this.pendingSubmissions.find((e) => e && e.id === id) || null;
  }

  updatePendingSubmissionRetryArgs(id, retryArgs) {
    const entry = this._findPending(id);
    if (!entry) return;
    entry.retryArgs = retryArgs && typeof retryArgs === "object" ? retryArgs : null;
    if (retryArgs && typeof retryArgs === "object") {
      this.updatePendingSubmissionRunNotes(id, retryArgs.runNotesPath, retryArgs.runId, { save: false, refresh: false });
      if (retryArgs.jobId) entry.jobId = String(retryArgs.jobId || "");
    }
    void this.savePluginState();
    this.refreshOpenViews();
    this.updateLongRunningPoller();
  }

  updatePendingSubmissionRunNotes(id, runNotesPath, runId, opts = {}) {
    const entry = this._findPending(id);
    if (!entry) return;
    updatePendingSubmissionEntryRunNotes(entry, runNotesPath, runId);
    if (opts.save !== false) void this.savePluginState();
    if (opts.refresh !== false) this.refreshOpenViews();
  }

  updatePendingSubmissionArtifactMeta(id, meta, opts = {}) {
    const entry = this._findPending(id);
    if (!entry || !meta || typeof meta !== "object") return;
    updatePendingSubmissionEntryArtifactMeta(entry, meta);
    if (opts.save !== false) void this.savePluginState();
    if (opts.refresh !== false) this.refreshOpenViews();
  }

  hasActiveLongRunningPending() {
    return pendingHasActiveLongRunning(this.pendingSubmissions);
  }

  updateLongRunningPoller() {
    if (this.hasActiveLongRunningPending()) {
      this.startLongRunningPoller();
    } else {
      this.stopLongRunningPoller();
    }
  }

  startLongRunningPoller() {
    if (this.longRunningPollTimer) return;
    this.longRunningPollTimer = window.setInterval(() => {
      if (!this.hasActiveLongRunningPending()) {
        this.stopLongRunningPoller();
        return;
      }
      void this.refreshShellSummarySilently();
    }, 15000);
  }

  stopLongRunningPoller() {
    if (!this.longRunningPollTimer) return;
    window.clearInterval(this.longRunningPollTimer);
    this.longRunningPollTimer = null;
  }

  // R90: 顶部"刷新炉子"按钮的 last updated 文案
  // 源：shellSummary.generated_at；返回"刚刚 / N 分钟前 / N 小时前 / N 天前 / 未刷新"
  getLastSummaryRefreshLabel() {
    const ts = this.shellSummary && this.shellSummary.generated_at ? String(this.shellSummary.generated_at) : "";
    if (!ts) return this.t("未刷新");
    const ms = Date.parse(ts);
    if (!Number.isFinite(ms)) return this.t("未刷新");
    const diff = Math.max(0, Date.now() - ms);
    if (diff < 60 * 1000) return this.t("刚刚");
    const m = Math.floor(diff / (60 * 1000));
    if (m < 60) return this.t("{n} 分钟前", { n: m });
    const h = Math.floor(diff / (60 * 60 * 1000));
    if (h < 24) return this.t("{n} 小时前", { n: h });
    const d = Math.floor(diff / (24 * 60 * 60 * 1000));
    return this.t("{n} 天前", { n: d });
  }

  // 当 shellSummary 刷新后，匹配 pending → recent_outputs/recent_receipts
  // R88 P1 fix:
  //   - candidate 必须有时间戳，且时间戳 >= entry.startedAt（带 60s skew 容忍时钟漂移）
  //   - 短指纹（< 16 字符）使用 normalized exact 匹配；长指纹至少匹配 60 字符前缀
  //   - 匹配字段扩到 receipt_path / output_path / query / target
  //   - running 卡片超过 5 分钟仅停止 reconcile（不删，避免长任务消失）
  reconcilePendingSubmissions(summary) {
    if (!Array.isArray(this.pendingSubmissions) || !this.pendingSubmissions.length) return;
    const { remaining, hits } = reconcilePendingSubmissionList(this.pendingSubmissions, summary);
    if (remaining.length !== this.pendingSubmissions.length) {
      this.pendingSubmissions = remaining;
      this.refreshOpenViews();
    }
    // R90: markDone 不再设置 setTimeout，done 卡保留等用户行动
    for (const h of hits) {
      if (h.runNotesPath || h.runId) {
        this.updatePendingSubmissionRunNotes(h.id, h.runNotesPath, h.runId, { save: false, refresh: false });
      }
      this.updatePendingSubmissionArtifactMeta(h.id, h.meta || {}, { save: false, refresh: false });
      this.markPendingSubmissionDone(h.id, h.target, h.path);
    }
    this.updateLongRunningPoller();
  }

  async runUniversalInputCommand({ payload, title }) {
    const normalizedPayload = String(payload || "").trim();
    if (!normalizedPayload) {
      new Notice(this.t("Universal input cannot be empty."));
      return;
    }
    const spec = buildUniversalInputCommandSpec({ payload: normalizedPayload, title });
    return await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  }

  async runAskCommand({ question, format, mode, protocol }) {
    const spec = buildAskCommandSpec({ question, format, mode, protocol });
    return await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  }

  async runDroppedPayloadsWithAutoAsk({ payloads, question, protocol }) {
    const normalizedPayloads = Array.isArray(payloads)
      ? payloads
        .map((payload) => {
          if (payload && typeof payload === "object") {
            return {
              path: String(payload.path || payload.source || payload.payload || "").trim(),
              title: String(payload.title || payload.name || "").trim(),
            };
          }
          return { path: String(payload || "").trim(), title: "" };
        })
        .filter((payload) => payload.path)
      : [];
    const normalizedQuestion = String(question || "").trim();
    const materialPaths = [];
    for (const payloadItem of normalizedPayloads) {
      const payload = await this.runUniversalInputCommand({ payload: payloadItem.path, title: payloadItem.title });
      collectMaterialPathsFromPayload(payload).forEach((item) => materialPaths.push(item));
    }
    const normalizedMaterialPaths = normalizeMaterialPaths(materialPaths);
    const askQuestion = normalizedQuestion
      ? buildAutoAskQuestion(normalizedQuestion, normalizedMaterialPaths)
      : "";
    let runNotesPath = "";
    let runId = "";
    let jobId = "";
    let askFormat = "";
    if (normalizedQuestion) {
      askFormat = inferAutoAskFormat(normalizedQuestion, normalizedMaterialPaths);
      const askPayload = await this.runAskCommand({
        question: askQuestion,
        format: askFormat,
        mode: "run-ask",
        protocol,
      });
      runNotesPath = String(askPayload && askPayload.run_notes_path || "");
      runId = String(askPayload && askPayload.run_id || "");
      jobId = String(askPayload && askPayload.job_id || "");
    }
    return {
      materialPaths: normalizedMaterialPaths,
      askQuestion,
      askFormat,
      runNotesPath,
      runId,
      jobId,
    };
  }

  completePendingMaterialDrop(id, materialPaths) {
    const paths = normalizeMaterialPaths(materialPaths);
    const rawPath = paths.find((item) => item.startsWith("raw/inbox/")) || paths[0] || "";
    if (id && rawPath) {
      this.markPendingSubmissionDone(id, "raw", rawPath);
      return true;
    }
    return false;
  }

  async runDroppedFilesWithAutoAsk({ files, question, protocol }) {
    const normalizedFiles = Array.isArray(files)
      ? files
        .map((file) => ({
          path: String(file && (file.path || file.source) || "").trim(),
          name: String(file && file.name || "").trim(),
        }))
        .filter((file) => file.path)
      : [];
    return await this.runDroppedPayloadsWithAutoAsk({
      payloads: normalizedFiles.map((file) => ({ path: file.path, title: file.name })),
      question,
      protocol,
    });
  }

  async runReportSubgraphCommand({ reportPath }) {
    const spec = buildReportSubgraphCommandSpec(reportPath);
    if (!spec.normalized) {
      new Notice(this.t("Report path cannot be empty."));
      return;
    }
    const payload = await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
    const outputPath = payload && typeof payload.output_path === "string" ? payload.output_path.trim() : "";
    if (outputPath) {
      await this.openWorkspacePath(outputPath);
    }
    return payload;
  }

  collectReportCandidates() {
    const summary = this.shellSummary && typeof this.shellSummary === "object" ? this.shellSummary : null;
    if (!summary) return [];
    const outputs = Array.isArray(summary.recent_outputs) ? summary.recent_outputs : [];
    const seen = new Set();
    const candidates = [];
    for (const item of outputs) {
      if (!item || typeof item !== "object") continue;
      const candidatePath = String(item.path || "").trim();
      if (!candidatePath || !candidatePath.startsWith("output/reports/")) continue;
      const deliveryMode = String(item.delivery_mode || "").trim();
      const llmStatus = String(item.llm_status || "").trim();
      const backgroundStatus = String(item.background_status || "").trim();
      const artifactQuality = String(item.artifact_quality || "").trim();
      const containsPlaceholder = String(item.contains_llm_placeholder || "").trim().toLowerCase();
      const rawTitle = String(item.title || "").trim();
      if (deliveryMode === "deterministic-fallback" || deliveryMode === "llm-failed") continue;
      if (["timeout_or_unavailable", "pending", "failed", "degraded"].includes(llmStatus)) continue;
      if (["submitted", "running", "degraded"].includes(backgroundStatus)) continue;
      if (["degraded", "placeholder"].includes(artifactQuality)) continue;
      if (["1", "true", "yes"].includes(containsPlaceholder)) continue;
      if (rawTitle.startsWith("LLM 未完成")) continue;
      if (seen.has(candidatePath)) continue;
      seen.add(candidatePath);
      const title = rawTitle || candidatePath;
      candidates.push({ value: candidatePath, label: `${title} — ${candidatePath}` });
    }
    return candidates;
  }

  openReportSubgraphPicker() {
    const candidates = this.collectReportCandidates();
    this.openStructuredCommandModal(buildReportSubgraphModalSpec(this, candidates));
  }

  async runDropUrlCommand({ url, title }) {
    const spec = buildDropUrlCommandSpec({ url, title });
    await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  }

  openDropUrlModal(initialUrl = "") {
    new DropUrlModal(this.app, this).setInitialUrl(initialUrl).open();
  }

  async runDropFileCommand({ mode, source, title, maxFiles }) {
    const spec = buildDropFileCommandSpec({ mode, source, title, maxFiles });
    await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  }

  async runDropImageCommand({ source, title, noVision }) {
    const spec = buildDropImageCommandSpec({ source, title, noVision });
    await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  }

  async runDropNoteCommand({ text, title, kind }) {
    const spec = buildDropNoteCommandSpec({ text, title, kind });
    await this.runPluginCommand(commandLabel(this.t.bind(this), spec.labelKey, spec.labelSubject), spec.args, spec.options);
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
      new Notice(this.t("Cannot parse command: {command}", { command: truncateText(fullCommandStr, 80) }));
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
    this.openStructuredCommandModal(buildFileBackModalSpec(this, prefill));
  }

  openReviewPageModal(prefill = {}) {
    this.openStructuredCommandModal(buildReviewPageModalSpec(this, prefill));
  }

  openReviewRewriteModal(prefill = {}) {
    this.openStructuredCommandModal(buildReviewRewriteModalSpec(this, prefill));
  }

  openApplyRewriteModal(prefill = {}) {
    this.openStructuredCommandModal(buildApplyRewriteModalSpec(this, prefill));
  }

  openRetireConceptModal(prefill = {}) {
    this.openStructuredCommandModal(buildRetireConceptModalSpec(this, prefill));
  }

  openReactivateConceptModal(prefill = {}) {
    this.openStructuredCommandModal(buildReactivateConceptModalSpec(this, prefill));
  }

  openApplyArchiveModal(prefill = {}) {
    this.openStructuredCommandModal(buildApplyArchiveModalSpec(this, prefill));
  }

  openRevertArchiveModal(prefill = {}) {
    this.openStructuredCommandModal(buildRevertArchiveModalSpec(this, prefill));
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

  openReviewNextTransitionPicker() {
    const nextReview = this.nextReviewCandidate();
    if (!nextReview) {
      new Notice(this.t("No reviewable page is available."));
      return;
    }
    this.openReviewPageTransitionPicker(nextReview);
  }

  openReviewPageBatchModal(prefill = {}) {
    this.openStructuredCommandModal(buildReviewPageBatchModalSpec(this, prefill));
  }

  openReviewBatchSuggestionPicker() {
    const suggestions = this.reviewBatchSuggestions();
    if (!suggestions.length) {
      new Notice(this.t("No shared batch review suggestion is available."));
      return;
    }
    if (suggestions.length === 1) {
      this.openReviewPageBatchModal(suggestions[0]);
      return;
    }
    this.openContextPicker({
      title: this.t("Pick Batch Review"),
      description: this.t("Batch review is only offered when multiple pages share the same preferred or default transition."),
      submitLabel: this.t("Batch review"),
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
      title: this.t("Pick Rewrite Context"),
      description: this.t("Prefer an explicit rewrite proposal object before falling back to manual slug entry."),
      keyName: "slug",
      options,
      emptyNotice: this.t("No visible concept context is available; fell back to the manual form."),
      onFallback: () => this.openReviewRewriteModal(),
      onSubmit: (option) => this.openReviewRewriteTransitionPicker(option),
    });
  }

  openReviewActionContextPicker(options = this.visibleActionCandidates("review")) {
    this.openContextAwareAction({
      title: this.t("Pick Review Action"),
      description: this.t("Prefer an explicit action control object before falling back to manual action id entry."),
      keyName: "actionId",
      options,
      emptyNotice: this.t("No visible machine-memory action context is available; fell back to the manual form."),
      onFallback: () => this.openReviewActionModal(),
      onSubmit: (option) => this.openReviewActionTransitionPicker(option),
    });
  }

  openApplyArchiveContextPicker(options = this.visibleArchiveCandidates("apply")) {
    this.openContextAwareAction({
      title: this.t("Pick Archive Target"),
      description: this.t("Prefer an explicit archive control object before falling back to manual entry id."),
      keyName: "entryId",
      options,
      emptyNotice: this.t("No visible archive context is available; fell back to the manual form."),
      onFallback: () => this.openApplyArchiveModal(),
      onSubmit: (option) => this.openApplyArchiveModal({ entryId: option.entryId || option.value || "" }),
    });
  }

  openRevertArchiveContextPicker(options = this.visibleArchiveCandidates("revert")) {
    this.openContextAwareAction({
      title: this.t("Pick Archive Revert Target"),
      description: this.t("Prefer an explicit archive control object before falling back to manual entry id."),
      keyName: "entryId",
      options,
      emptyNotice: this.t("No visible archive context is available; fell back to the manual form."),
      onFallback: () => this.openRevertArchiveModal(),
      onSubmit: (option) => this.openRevertArchiveModal({ entryId: option.entryId || option.value || "" }),
    });
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

  openReviewRewriteTransitionPicker(control) {
    const slug = String(control.slug || control.value || "").trim();
    const currentStatus = String(control.currentStatus || control.current_status || control.status || "").trim();
    this.openTransitionPicker({
      title: this.t("Pick Rewrite Transition"),
      description: this.t("Choose a valid next status for this rewrite proposal."),
      controlType: "rewrite",
      control,
      emptyNotice: this.t("No explicit rewrite transition is available; fell back to the manual form."),
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
      title: this.t("Pick Action Transition"),
      description: this.t("Choose a valid next status for this machine-memory action."),
      controlType: "action",
      control,
      emptyNotice: this.t("No explicit action transition is available; fell back to the manual form."),
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
    // R90 P1-1: 返回 boolean —— true 成功打开；false 失败（无 path / repo missing / path not found / no adapter）
    // 既有调用方不读返回值，无破坏；openPendingDoneTarget 据此判断是否进退化路径
    const requestedPath = String(relativePath || "").trim();
    const normalized = normalizeWorkspaceRelativePath(requestedPath);
    if (!requestedPath) {
      new Notice(this.t("No path to open."));
      return false;
    }
    if (!normalized) {
      new Notice(this.t("Unable to open {path}", { path: requestedPath }));
      return false;
    }
    const abstractFile = this.app.vault.getAbstractFileByPath(normalized);
    if (abstractFile && normalized.endsWith(".md")) {
      const leaf = this.app.workspace.getLeaf(true);
      await leaf.openFile(abstractFile);
      return true;
    }
    if (!this.repoState.root) {
      new Notice(this.t("Unable to open {path}", { path: normalized }));
      return false;
    }
    const absolutePath = resolveWorkspaceSnippetPath(this.repoState.root, normalized);
    if (!fs.existsSync(absolutePath)) {
      new Notice(this.t("Path not found: {path}", { path: normalized }));
      return false;
    }
    if (typeof this.app.vault.adapter.getResourcePath === "function") {
      const resourcePath = this.app.vault.adapter.getResourcePath(normalized);
      window.open(resourcePath, "_blank");
      return true;
    }
    new Notice(this.t("Unable to open resource: {path}", { path: normalized }));
    return false;
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

  renderRecentRuns(contentEl) {
    renderRecentRuns(this, contentEl);
  }

  renderReviewCenter(contentEl) {
    renderReviewCenter(this, contentEl);
  }

  renderExecutionCenter(contentEl) {
    renderExecutionCenter(this, contentEl);
  }

  refreshOpenViews() {
    this.openViews.forEach((view) => {
      if (view && typeof view.render === "function") {
        view.render();
      }
    });
  }
};
