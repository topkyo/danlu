// Main plugin class. Render methods delegate to standalone functions
// defined in render.js.

module.exports = class FurnaceProductShellPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
    this.pluginState = { recentRuns: [] };
    this.shellSummary = null;
    this.repoState = { valid: false, root: "", launcherPath: "", missingPaths: ["vault-root"] };
    this.openViews = new Set();
    this.statusBarItem = this.addStatusBarItem();

    await this.loadPluginState();
    this.refreshRepoState();

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

    this.updateStatusBar();
  }

  async onunload() {
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
    this.addCommand({
      id: "run-compile",
      name: this.t("Compile"),
      callback: () => {
        this.runUiAction(() => this.runCompileCommand(), this.t("Compile"));
      },
    });
    this.addCommand({
      id: "run-ask",
      name: this.t("Ask"),
      callback: () => {
        new AskCommandModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "capture-note",
      name: this.t("Capture Note"),
      callback: () => {
        new CaptureNoteModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "drop-url",
      name: this.t("Drop URL"),
      callback: () => {
        new DropUrlModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "drop-file",
      name: this.t("Drop File"),
      callback: () => {
        new DropFileModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "drop-image",
      name: this.t("Drop Image"),
      callback: () => {
        new DropImageModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "search-workspace",
      name: this.t("Search Workspace"),
      callback: () => {
        new SearchCommandModal(this.app, this).open();
      },
    });
  }

  registerAdvancedCommands() {
    if (!this.settings.showAdvancedCommands) {
      return;
    }
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
    this.addCommand({
      id: "run-nightly",
      name: this.t("Nightly"),
      callback: () => {
        this.runUiAction(() => this.runNightlyCommand(), this.t("Nightly"));
      },
    });
    this.addCommand({
      id: "set-protocol",
      name: this.t("Set Protocol"),
      callback: () => {
        new ProtocolCommandModal(this.app, this).open();
      },
    });
    this.addCommand({
      id: "file-back",
      name: this.t("File Back"),
      callback: () => {
        this.openFileBackModal();
      },
    });
    this.addCommand({
      id: "review-page",
      name: this.t("Review Page"),
      callback: () => {
        this.openReviewPageContextPicker();
      },
    });
    this.addCommand({
      id: "review-next-page",
      name: this.t("Review Next Page"),
      callback: () => {
        this.openReviewNextTransitionPicker();
      },
    });
    this.addCommand({
      id: "batch-review-pages",
      name: this.t("Batch Review Pages"),
      callback: () => {
        this.openReviewBatchSuggestionPicker();
      },
    });
    this.addCommand({
      id: "review-rewrite",
      name: this.t("Review Rewrite"),
      callback: () => {
        this.openReviewRewriteContextPicker();
      },
    });
    this.addCommand({
      id: "apply-rewrite",
      name: this.t("Apply Rewrite"),
      callback: () => {
        this.openApplyRewriteModal();
      },
    });
    this.addCommand({
      id: "retire-concept",
      name: this.t("Retire Concept"),
      callback: () => {
        this.openRetireConceptModal();
      },
    });
    this.addCommand({
      id: "reactivate-concept",
      name: this.t("Reactivate Concept"),
      callback: () => {
        this.openReactivateConceptModal();
      },
    });
    this.addCommand({
      id: "apply-archive",
      name: this.t("Apply archive"),
      callback: () => {
        this.openApplyArchiveContextPicker();
      },
    });
    this.addCommand({
      id: "revert-archive",
      name: this.t("Revert archive"),
      callback: () => {
        this.openRevertArchiveContextPicker();
      },
    });
    this.addCommand({
      id: "review-action",
      name: this.t("Review Action"),
      callback: () => {
        this.openReviewActionContextPicker();
      },
    });
    this.addCommand({
      id: "apply-action",
      name: this.t("Apply Action"),
      callback: () => {
        this.openApplyActionContextPicker();
      },
    });
    this.addCommand({
      id: "revert-action",
      name: this.t("Revert Action"),
      callback: () => {
        this.openRevertActionContextPicker();
      },
    });
    this.addCommand({
      id: "apply-all-accepted-low-risk",
      name: this.t("Apply All Accepted Low-Risk Actions"),
      callback: () => {
        this.runUiAction(() => this.runApplyAllAcceptedLowRiskCommand(), this.t("Apply All Accepted Low-Risk Actions"));
      },
    });
    this.addCommand({
      id: "revert-last-action-batch",
      name: this.t("Revert Last Action Batch"),
      callback: () => {
        this.runUiAction(() => this.runRevertLastBatchCommand(), this.t("Revert Last Action Batch"));
      },
    });
    this.addCommand({
      id: "open-home-note",
      name: this.t("Open Home Note"),
      callback: () => {
        this.runUiAction(() => this.openHomeNote(), this.t("Open Home Note"));
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
    const recentRuns = Array.isArray(data.recentRuns)
      ? data.recentRuns
        .filter((record) => record && typeof record === "object")
        .map((record) => {
          const rewriteProposalObjects = this.normalizeRewriteProposalObjects(record.rewriteProposalObjects || record.updatedRewriteProposals || []);
          const rewriteRecoveryActions = this.normalizeRewriteRecoveryActions(record.rewriteRecoveryActions || []);
          const rewriteProposalPaths = normalizeRelativePathList(
            record.rewriteProposalPaths || this.rewriteProposalPathsFromObjects(rewriteProposalObjects)
          );
          const rewriteProposalSlugs = normalizeRelativePathList(
            record.rewriteProposalSlugs || this.rewriteProposalSlugsFromObjects(rewriteProposalObjects)
          );
          return {
            ...record,
            argv: Array.isArray(record.argv) ? record.argv.map((value) => String(value || "")) : [],
            command: String(record.command || (Array.isArray(record.argv) && record.argv.length ? record.argv[0] : "")),
            protocol: String(record.protocol || ""),
            backend: String(record.backend || ""),
            backendRequested: String(record.backendRequested || ""),
            backendEffective: String(record.backendEffective || ""),
            model: String(record.model || ""),
            modelSelected: String(record.modelSelected || ""),
            modelFinal: String(record.modelFinal || ""),
            codexReasoningEffort: String(record.codexReasoningEffort || ""),
            promptProfile: String(record.promptProfile || ""),
            retryPromptProfile: String(record.retryPromptProfile || ""),
            fallbackStage: String(record.fallbackStage || ""),
            fallbackReason: String(record.fallbackReason || ""),
            contractValidated: Boolean(record.contractValidated),
            rewriteProposalObjects,
            rewriteRecoveryActions,
            rewriteProposalPaths,
            rewriteProposalSlugs,
            fallbackFrom: String(record.fallbackFrom || ""),
            fallbackCommand: String(record.fallbackCommand || ""),
            fallbackUsed: Boolean(record.fallbackUsed),
            deliveryMode: String(record.deliveryMode || ""),
            logPath: String(record.logPath || ""),
            stdoutRaw: trimDiagnosticText(record.stdoutRaw || ""),
            stderrRaw: trimDiagnosticText(record.stderrRaw || ""),
            exitCode: record.exitCode === 0 || Number.isFinite(Number(record.exitCode || NaN))
              ? Number(record.exitCode)
              : "",
            timeline: Array.isArray(record.timeline)
              ? record.timeline
                .filter((event) => event && typeof event === "object")
                .map((event) => ({
                  stage: String(event.stage || ""),
                  at: String(event.at || ""),
                  summary: String(event.summary || ""),
                  status: String(event.status || ""),
                }))
              : [],
          };
        })
      : [];
    this.pluginState = { recentRuns };
    this.trimRecentRuns();
    if (feishuWebhookUrlMigrated || wecomWebhookUrlMigrated || enabledChannelsMigrated || lastViewedTimestampMigrated) {
      await this.savePluginState();
    }
  }

  async savePluginState() {
    await this.saveData({
      settings: this.settings,
      recentRuns: this.pluginState.recentRuns,
    });
  }

  trimRecentRuns() {
    const limit = Math.max(1, Number.parseInt(String(this.settings.recentRunsLimit || DEFAULT_SETTINGS.recentRunsLimit), 10) || DEFAULT_SETTINGS.recentRunsLimit);
    this.pluginState.recentRuns = this.pluginState.recentRuns.slice(0, limit);
  }

  normalizeLlmHealthState(value) {
    if (!value || typeof value !== "object") {
      return null;
    }
    const status = String(value.status || "").trim() || "unknown";
    return {
      status,
      backend: String(value.backend || "").trim(),
      backendRequested: String(value.backendRequested || value.backend_requested || "").trim(),
      backendEffective: String(value.backendEffective || value.backend_effective || "").trim(),
      model: String(value.model || "").trim(),
      modelSelected: String(value.modelSelected || value.model_selected || "").trim(),
      modelFinal: String(value.modelFinal || value.model_final || "").trim(),
      reason: String(value.reason || "").trim(),
      checkedAt: String(value.checkedAt || value.checked_at || "").trim(),
      source: String(value.source || "").trim(),
      fallbackCommand: String(value.fallbackCommand || value.fallback_command || "").trim(),
      fallbackStage: String(value.fallbackStage || value.fallback_stage || "").trim(),
      fallbackReason: String(value.fallbackReason || value.fallback_reason || "").trim(),
      contractValidated: Object.prototype.hasOwnProperty.call(value, "contractValidated")
        ? Boolean(value.contractValidated)
        : Boolean(value.contract_validated),
      recoveryCommand: String(value.recoveryCommand || value.recovery_command || "").trim(),
      routeDrift: Boolean(value.routeDrift || value.route_drift),
      routeDriftReason: String(value.routeDriftReason || value.route_drift_reason || "").trim(),
      logPath: String(value.logPath || value.log_path || "").trim(),
      resultPath: String(value.resultPath || value.result_path || "").trim(),
      receiptPath: String(value.receiptPath || value.receipt_path || "").trim(),
      stderrSummary: String(value.stderrSummary || value.stderr_summary || "").trim(),
      stderrRaw: trimDiagnosticText(value.stderrRaw || value.stderr_raw || ""),
    };
  }

  currentLlmHealth() {
    const llmStatus = this.shellSummary && typeof this.shellSummary === "object" ? this.shellSummary.llm_status || {} : {};
    const summaryHealth = this.shellSummary && typeof this.shellSummary === "object"
      ? this.normalizeLlmHealthState(this.shellSummary.llm_health)
      : null;
    const selected = this.currentLlmSelection();
    if (!summaryHealth) {
      return {
        status: "unknown",
        backend: selected.backend || String(llmStatus.backend || ""),
        model: selected.model || String(llmStatus.effective_model || llmStatus.model || ""),
        reason: llmStatus.configured ? "No summary LLM health data available yet." : "LLM is not configured.",
        checkedAt: "",
        source: "",
        fallbackCommand: "",
        logPath: "",
        resultPath: "",
        receiptPath: "",
        stderrSummary: "",
        stderrRaw: "",
      };
    }
    return {
      ...summaryHealth,
      backend: summaryHealth.backend || selected.backend || String(llmStatus.backend || ""),
      model: summaryHealth.model || selected.model || String(llmStatus.effective_model || llmStatus.model || ""),
    };
  }

  latestLlmRun() {
    if (this.shellSummary && typeof this.shellSummary === "object" && this.shellSummary.latest_llm_run && typeof this.shellSummary.latest_llm_run === "object") {
      const summaryRun = this.shellSummary.latest_llm_run;
      return {
        ...summaryRun,
        command: String(summaryRun.command || summaryRun.event || "").trim(),
        backend: String(summaryRun.backend || summaryRun.backend_effective || summaryRun.backend_requested || "").trim(),
        model: String(summaryRun.model || summaryRun.model_final || summaryRun.model_selected || "").trim(),
        resultPath: String(summaryRun.resultPath || summaryRun.result_path || "").trim(),
        receiptPath: String(summaryRun.receiptPath || summaryRun.receipt_path || "").trim(),
        logPath: String(summaryRun.logPath || summaryRun.log_path || "").trim(),
        errorSummary: String(summaryRun.errorSummary || summaryRun.error || summaryRun.fallback_reason || "").trim(),
        fallbackFrom: String(summaryRun.fallbackFrom || summaryRun.fallback_from || "").trim(),
        fallbackCommand: String(summaryRun.fallbackCommand || summaryRun.fallback_command || "").trim(),
        fallbackUsed: Boolean(summaryRun.fallbackUsed || summaryRun.fallback_used),
        deliveryMode: String(summaryRun.deliveryMode || summaryRun.delivery_mode || "").trim(),
      };
    }
    return null;
  }

  // EP-015: latestShellSyncRun() removed. The sole authoritative source for
  // the last persisted shell-summary metadata is `shellSummary.latest_shell_sync_run`;
  // consumers should read it directly rather than going through a plugin
  // helper that could drift back into merging plugin-local recentRuns.
  currentShellSyncState() {
    // EP-015 Path 3: summary-only domain state.
    // 1. Own in-flight shell-status → running (only state recentRuns can
    //    legitimately contribute, since CLI snapshot cannot represent
    //    in-flight work).
    // 2. CLI snapshot present → healthy, using snapshot.generated_at.
    // 3. Otherwise → unknown.
    // We no longer synthesize a "failed" domain state from recentRuns;
    // recentRuns is plugin-local command history, not authoritative health.
    const runningRecord = this.pluginState.recentRuns.find(
      (record) => record && record.command === "shell-status" && record.status === "running"
    );
    if (runningRecord) {
      return {
        status: "running",
        reason: this.t("Refreshing shell summary."),
        checkedAt: runningRecord.startedAt || "",
        logPath: runningRecord.logPath || "",
      };
    }
    if (this.shellSummary && typeof this.shellSummary === "object") {
      const snapshot = this.shellSummary.latest_shell_sync_run;
      const hasSnapshot = snapshot && typeof snapshot === "object" && Object.keys(snapshot).length;
      const checkedAt = hasSnapshot
        ? String(snapshot.generated_at || this.shellSummary.generated_at || "")
        : String(this.shellSummary.generated_at || "");
      return {
        status: "healthy",
        reason: this.t("Summary ready."),
        checkedAt,
        logPath: "",
      };
    }
    return {
      status: "unknown",
      reason: this.t("shell-summary.json has not been generated yet. Run Refresh, Compile, or Nightly first."),
      checkedAt: "",
      logPath: "",
    };
  }

  /**
   * Builds diagnostic items for the Product Shell self-check panel.
   *
   * NOTE (EP-012): currently not wired to any UI call site. Kept so that
   * future self-check surfaces stay semantically correct (summary-only,
   * no repo-truth inference from recentRuns). See PROGRESS.md §96.
   */
  selfCheckItems() {
    const llmStatus = this.shellSummary && typeof this.shellSummary === "object" ? this.shellSummary.llm_status || {} : {};
    const health = this.currentLlmHealth();
    const latestLlmRun = this.latestLlmRun();
    const availableBackends = Array.isArray(llmStatus.available_backends) ? llmStatus.available_backends.filter(Boolean) : [];
    const requestedBackend = String(llmStatus.backend_requested || this.settings.llmBackend || "").trim();
    const effectiveBackend = String(llmStatus.backend || "").trim();
    const selected = this.currentLlmSelection();
    const summaryTimestamp = parseTimestampMs(this.shellSummary && this.shellSummary.generated_at);
    const summaryAgeMs = Number.isFinite(summaryTimestamp) ? Date.now() - summaryTimestamp : NaN;
    const items = [];

    items.push({
      key: "runtime",
      status: this.repoState.valid ? "healthy" : "failed",
      title: "Runtime contract",
      detail: this.repoState.valid
        ? this.t("launcher {launcher} · root {root}", { launcher: this.settings.launcherPath || "", root: this.repoState.root || "" })
        : this.t("Missing runtime paths: {missing}", { missing: this.repoState.missingPaths.join(", ") }),
    });

    if (!this.shellSummary) {
      items.push({
        key: "summary",
        status: "failed",
        title: "Shell summary",
        detail: this.t("shell-summary.json has not been generated yet. Run Refresh, Compile, or Nightly first."),
      });
    } else {
      items.push({
        key: "summary",
        status: Number.isFinite(summaryAgeMs) && summaryAgeMs > 15 * 60 * 1000 ? "warning" : "healthy",
        title: "Shell summary",
        detail: Number.isFinite(summaryAgeMs) && summaryAgeMs > 15 * 60 * 1000
          ? this.t("Summary is stale; refresh before trusting the home surface.")
          : this.t("Generated {time}", { time: String(this.shellSummary.generated_at || "") }),
      });
    }

    items.push({
      key: "route",
      status: requestedBackend && effectiveBackend && (!availableBackends.length || availableBackends.includes(effectiveBackend)) ? "healthy" : "failed",
      title: "LLM route",
      detail: this.t("requested {requested} · effective {effective} · available {available}", {
        requested: requestedBackend || this.t("unconfigured"),
        effective: effectiveBackend || this.t("unconfigured"),
        available: availableBackends.length ? availableBackends.join(", ") : this.t("none"),
      }),
    });

    if (!requestedBackend) {
      items.push({
        key: "backend-discovery",
        status: "warning",
        title: "Backend discovery",
        detail: this.t("No explicit LLM backend is selected. Choose one in Product Shell settings or set AIWIKI_LLM_BACKEND."),
      });
    } else {
      const backendVisible = availableBackends.includes(requestedBackend);
      items.push({
        key: "backend-discovery",
        status: backendVisible ? "healthy" : "warning",
        title: "Backend discovery",
        detail: backendVisible
          ? this.t("Product Shell runtime can see the selected backend {backend}.", { backend: requestedBackend })
          : this.t("Product Shell runtime cannot see the selected backend {backend}.", { backend: requestedBackend }),
      });
    }

    if (!latestLlmRun) {
      items.push({
        key: "latest-ask",
        status: "unknown",
        title: "Latest ask execution",
        detail: this.t("No summary latest LLM run data available."),
      });
    } else {
      const usedFallback = Boolean(latestLlmRun.fallbackUsed) || String(latestLlmRun.deliveryMode || "").trim() === "deterministic-fallback";
      const latestStatus = usedFallback
        ? "warning"
        : latestLlmRun.status === "success"
          ? "healthy"
          : "failed";
      const latestDetail = latestStatus === "healthy"
        ? this.t("Latest run-ask succeeded.")
        : latestStatus === "warning"
          ? this.t("Latest run-ask fell back to deterministic ask.")
          : this.t("Latest run-ask failed without deterministic fallback.");
      items.push({
        key: "latest-ask",
        status: latestStatus,
        title: "Latest ask execution",
        detail: `${latestDetail} ${latestLlmRun.errorSummary || latestLlmRun.resultPath || ""}`.trim(),
      });
    }

    if (latestLlmRun && latestLlmRun.backend && selected.backend && latestLlmRun.backend !== selected.backend) {
      items.push({
        key: "route-drift",
        status: "warning",
        title: "Route drift",
        detail: this.t("Latest Product Shell ask used {latest}; current route is {current}.", {
          latest: latestLlmRun.backend,
          current: selected.backend,
        }),
      });
    } else if (latestLlmRun && latestLlmRun.backend && selected.backend) {
      // Have data from both sides and they match — healthy.
      items.push({
        key: "route-drift",
        status: "healthy",
        title: "Route drift",
        detail: this.t("Latest Product Shell ask matches current route."),
      });
    } else {
      // Missing summary.latest_llm_run or its backend — cannot assert health.
      // Must not claim "healthy" just because we have no data (oracle round 6).
      items.push({
        key: "route-drift",
        status: "unknown",
        title: "Route drift",
        detail: this.t("No summary latest LLM run data available."),
      });
    }

    if (health.status === "degraded" || health.status === "failed") {
      items.push({
        key: "health",
        status: "warning",
        title: "LLM health",
        detail: health.reason || this.t("Recent run-ask fell back to deterministic ask."),
      });
    }

    return items;
  }

  updateLlmHealth(nextState) {
    this.updateStatusBar();
    this.refreshOpenViews();
    void this.savePluginState();
  }

  recordLlmHealthFromRun(record, overrides = {}) {
    if (!record || typeof record !== "object") {
      return;
    }
    this.updateLlmHealth({
      status: overrides.status || "unknown",
      backend: overrides.backend || record.backend,
      backendRequested: overrides.backendRequested || record.backendRequested || "",
      backendEffective: overrides.backendEffective || record.backendEffective || record.backend || "",
      model: overrides.model || record.modelFinal || record.model,
      modelSelected: overrides.modelSelected || record.modelSelected || "",
      modelFinal: overrides.modelFinal || record.modelFinal || record.model || "",
      reason: overrides.reason || record.errorSummary || "",
      checkedAt: overrides.checkedAt || record.finishedAt || record.startedAt || new Date().toISOString(),
      source: overrides.source || record.command || "",
      fallbackCommand: overrides.fallbackCommand || record.fallbackCommand || record.fallbackFrom || "",
      fallbackStage: overrides.fallbackStage || record.fallbackStage || "",
      fallbackReason: overrides.fallbackReason || record.fallbackReason || "",
      contractValidated: Object.prototype.hasOwnProperty.call(overrides, "contractValidated") ? Boolean(overrides.contractValidated) : Boolean(record.contractValidated),
      logPath: overrides.logPath || record.logPath || "",
      resultPath: overrides.resultPath || record.resultPath || "",
      receiptPath: overrides.receiptPath || record.receiptPath || "",
      stderrSummary: overrides.stderrSummary || record.stderrSummary || "",
      stderrRaw: overrides.stderrRaw || record.stderrRaw || "",
    });
  }

  refreshRepoState() {
    const adapter = this.app.vault && this.app.vault.adapter;
    const root = adapter && typeof adapter.basePath === "string" ? adapter.basePath : "";
    const launcherPath = this.resolveLauncherPath(root);
    const missingPaths = [];
    if (!root) {
      missingPaths.push("vault-root");
    } else {
      [
        "raw",
        "wiki",
        "schema",
        "output",
        ".aiwiki",
      ].forEach((relativePath) => {
        if (!fs.existsSync(path.join(root, relativePath))) {
          missingPaths.push(relativePath);
        }
      });
      if (!launcherIsExecutable(launcherPath)) {
        missingPaths.push(this.settings.launcherPath);
      }
    }
    this.repoState = {
      valid: missingPaths.length === 0,
      root,
      launcherPath,
      missingPaths,
    };
    this.updateStatusBar();
    this.refreshOpenViews();
  }

  resolveLauncherPath(root) {
    const launcherPath = String(this.settings.launcherPath || DEFAULT_SETTINGS.launcherPath).trim();
    if (!root || !launcherPath) {
      return "";
    }
    if (path.isAbsolute(launcherPath)) {
      return launcherPath;
    }
    return path.join(root, launcherPath);
  }

  getActiveProtocol() {
    return String(this.shellSummary && this.shellSummary.active_protocol ? this.shellSummary.active_protocol : "general");
  }

  getAvailableProtocols() {
    const fromSummary = this.shellSummary && Array.isArray(this.shellSummary.available_protocols)
      ? this.shellSummary.available_protocols.filter((item) => typeof item === "string" && item)
      : [];
    return fromSummary.length ? fromSummary : DEFAULT_PROTOCOLS;
  }

  getActiveFilePath() {
    const activeFile = this.app.workspace.getActiveFile ? this.app.workspace.getActiveFile() : null;
    return activeFile && typeof activeFile.path === "string" ? activeFile.path : "";
  }

  getActiveConceptSlug() {
    const activePath = this.getActiveFilePath();
    if (!activePath.startsWith("wiki/concepts/") || !activePath.endsWith(".md")) {
      return "";
    }
    return path.basename(activePath, ".md");
  }

  getActiveOutputPath() {
    const activePath = this.getActiveFilePath();
    if (activePath.startsWith("output/") && activePath.endsWith(".md")) {
      return activePath;
    }
    return "";
  }

  getActiveCuratedPagePath() {
    const activePath = this.getActiveFilePath();
    if (!activePath.endsWith(".md")) {
      return "";
    }
    // Curated-page prefixes come from the CLI summary (EP-015). Plugin no
    // longer hardcodes "wiki/decisions/" / "wiki/judgments/"; CLI is the
    // single source of truth for which repo-relative roots count as curated.
    const roots = (this.shellSummary && typeof this.shellSummary === "object")
      ? this.shellSummary.curated_page_roots
      : null;
    if (!roots || typeof roots !== "object") {
      return "";
    }
    for (const key of Object.keys(roots)) {
      const prefix = roots[key];
      if (typeof prefix === "string" && prefix && activePath.startsWith(prefix)) {
        return activePath;
      }
    }
    return "";
  }

  normalizeRewriteProposalObjects(value) {
    const items = Array.isArray(value) ? value : [value];
    const seen = new Set();
    return items
      .map((item) => normalizeRewriteProposalObject(item))
      .filter((item) => {
        if (!item) {
          return false;
        }
        if (seen.has(item.slug)) {
          return false;
        }
        seen.add(item.slug);
        return true;
      });
  }

  normalizeRewriteRecoveryActions(value) {
    const items = Array.isArray(value) ? value : [value];
    const seen = new Set();
    return items
      .map((item) => normalizeRewriteRecoveryAction(item))
      .filter((item) => {
        if (!item) {
          return false;
        }
        if (seen.has(item.command)) {
          return false;
        }
        seen.add(item.command);
        return true;
      });
  }

  rewriteProposalPathsFromObjects(objects) {
    return normalizeRelativePathList(
      (Array.isArray(objects) ? objects : []).map((item) => item && item.proposalPath ? item.proposalPath : "")
    );
  }

  rewriteProposalSlugsFromObjects(objects) {
    return normalizeRelativePathList(
      (Array.isArray(objects) ? objects : []).map((item) => item && item.slug ? item.slug : "")
    );
  }

  extractRewriteProposalObjects(payload) {
    if (!payload || typeof payload !== "object") {
      return [];
    }
    return this.normalizeRewriteProposalObjects(payload.updated_rewrite_proposals || []);
  }

  extractRewriteRecoveryActions(payload) {
    if (!payload || typeof payload !== "object") {
      return [];
    }
    return this.normalizeRewriteRecoveryActions(payload.rewrite_recovery_actions || []);
  }

  extractRewriteProposalPaths(payload) {
    if (!payload || typeof payload !== "object") {
      return [];
    }
    const objects = this.extractRewriteProposalObjects(payload);
    return objects.length
      ? this.rewriteProposalPathsFromObjects(objects)
      : normalizeRelativePathList(payload.updated_rewrite_proposal_pages);
  }

  extractRewriteProposalSlugs(paths) {
    return normalizeRelativePathList(paths).map((proposalPath) => path.basename(proposalPath, ".md"));
  }

  rewriteCandidatesForSlugs(slugs, mode = "review") {
    const normalized = new Set(normalizeRelativePathList(slugs));
    if (!normalized.size) {
      return [];
    }
    return this.rewriteControlItems(mode).filter((proposal) => normalized.has(String(proposal.slug || "").trim()));
  }

  rewriteProposalSummary(record) {
    const count = Array.isArray(record && record.rewriteProposalObjects) && record.rewriteProposalObjects.length
      ? record.rewriteProposalObjects.length
      : (Array.isArray(record && record.rewriteProposalPaths) ? record.rewriteProposalPaths.length : 0);
    if (!count) {
      return "";
    }
    return this.t("rewrite proposals: {count}", { count });
  }

  openRewriteRecovery(record) {
    const recoveryActions = Array.isArray(record && record.rewriteRecoveryActions)
      ? this.normalizeRewriteRecoveryActions(record.rewriteRecoveryActions)
      : [];
    const proposalObjects = Array.isArray(record && record.rewriteProposalObjects)
      ? this.normalizeRewriteProposalObjects(record.rewriteProposalObjects)
      : [];
    if (recoveryActions.length === 1) {
      const action = recoveryActions[0];
      const control = proposalObjects.find((item) => item.slug === action.slug) || action;
      if (action.kind === "apply-rewrite") {
        this.openApplyRewriteModal({ slug: action.slug });
        return;
      }
      this.openReviewRewriteTransitionPicker({
        ...control,
        slug: action.slug,
        status: action.status || control.status || control.currentStatus || "",
        currentStatus: action.currentStatus || control.currentStatus || control.status || "",
        allowedTransitions: action.allowedTransitions || control.allowedTransitions || [],
        preferredTransitions: action.preferredTransitions || control.preferredTransitions || [],
        defaultTransition: action.transition || action.defaultTransition || control.defaultTransition || "",
      });
      return;
    }
    if (proposalObjects.length > 1) {
      this.openReviewRewriteContextPicker(
        proposalObjects.map((proposal) => ({
          ...proposal,
          value: proposal.slug,
          label: proposal.title || proposal.slug || "rewrite-proposal",
          description: `${displayRewriteStatus(proposal.status || proposal.currentStatus || "unknown", this.locale())} | ${proposal.proposalPath || proposal.targetPath || ""}`,
        }))
      );
      return;
    }
    const rewriteControls = this.rewriteCandidatesForSlugs(record && record.rewriteProposalSlugs, "review");
    if (rewriteControls.length === 1) {
      this.openReviewRewriteTransitionPicker(rewriteControls[0]);
      return;
    }
    if (rewriteControls.length > 1) {
      this.openReviewRewriteContextPicker(rewriteControls);
      return;
    }
    const rewriteSlugs = normalizeRelativePathList(record && record.rewriteProposalSlugs);
    if (rewriteSlugs.length === 1) {
      this.openReviewRewriteModal({ slug: rewriteSlugs[0] });
      return;
    }
    this.runUiAction(() => this.openReviewCenterView(), this.t("Open Review Center"));
  }

  openStructuredCommandModal(spec) {
    new StructuredCommandModal(this.app, this, spec).open();
  }

  openContextPicker(spec) {
    new ContextPickerModal(this.app, this, spec).open();
  }

  controlIdSet(key) {
    const executionControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.execution_controls
      : null;
    const values = executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
    return new Set(values.map((item) => String(item || "").trim()).filter(Boolean));
  }

  reviewControlList(key) {
    const reviewControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.review_controls
      : null;
    return reviewControls && Array.isArray(reviewControls[key]) ? reviewControls[key] : [];
  }

  executionControlList(key) {
    const executionControls = this.shellSummary && typeof this.shellSummary === "object"
      ? this.shellSummary.execution_controls
      : null;
    return executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
  }

  reviewPageControlItems() {
    const pages = this.reviewControlList("pages");
    return uniqueContextOptions(
      pages.map((page) => {
        const kind = String(page.kind || "").trim() || "page";
        const status = String(page.status || "").trim() || "unknown";
        const metaText = truncateText(reviewObjectMetaText(page, this.locale()) || "review object", 180);
        return {
          value: page.path,
          label: page.title || page.path || "review-page",
          description: metaText || `${this.t(kind)} | ${displayCuratedStatus(status, this.locale())} | ${this.t("review object")}`,
          pageId: String(page.page_id || ""),
          pagePath: String(page.path || ""),
          pageKind: kind,
          currentStatus: status,
          confidence: String(page.confidence || ""),
          canRefreshReview: Boolean(page.can_refresh_review),
          allowedTransitions: Array.isArray(page.allowed_transitions) ? page.allowed_transitions : [],
          preferredTransitions: Array.isArray(page.preferred_transitions) ? page.preferred_transitions : [],
          defaultTransition: String(page.default_transition || ""),
        };
      }),
      "pagePath"
    );
  }

  nextReviewCandidate() {
    const candidates = this.visibleReviewPageCandidates();
    return candidates.length ? candidates[0] : null;
  }

  reviewKindLabel(kind, count = 1) {
    const normalized = String(kind || "").trim();
    if (normalized === "decision") {
      return count === 1 ? this.t("decision") : this.t("decisions");
    }
    if (normalized === "judgment") {
      return count === 1 ? this.t("judgment") : this.t("judgments");
    }
    return count === 1 ? this.t("page") : this.t("pages");
  }

  commonReviewTransitionOptions(pages) {
    const controls = Array.isArray(pages) ? pages.filter((page) => page && typeof page === "object") : [];
    if (!controls.length) {
      return [];
    }
    const stats = new Map();
    controls.forEach((page) => {
      const seen = new Set();
      this.transitionOptions("page", page).forEach((option) => {
        if (seen.has(option.value)) {
          return;
        }
        seen.add(option.value);
        const current = stats.get(option.value) || {
          value: option.value,
          label: option.label,
          sharedCount: 0,
          preferredCount: 0,
          defaultCount: 0,
        };
        current.label = option.label;
        current.sharedCount += 1;
        if (option.isPreferred) {
          current.preferredCount += 1;
        }
        if (option.isDefault) {
          current.defaultCount += 1;
        }
        stats.set(option.value, current);
      });
    });
    return Array.from(stats.values())
      .filter((option) => option.sharedCount === controls.length)
      .sort((left, right) => {
        if (left.defaultCount !== right.defaultCount) {
          return right.defaultCount - left.defaultCount;
        }
        if (left.preferredCount !== right.preferredCount) {
          return right.preferredCount - left.preferredCount;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  reviewBatchSuggestions() {
    const groups = new Map();
    this.visibleReviewPageCandidates().forEach((page) => {
      const prioritized = this.preferredTransitionOptions("page", page);
      const selectedOptions = prioritized.length
        ? prioritized
        : this.transitionOptions("page", page).filter((option) => option.isDefault).slice(0, 1);
      selectedOptions.forEach((transition) => {
        const kind = String(page.pageKind || "page").trim() || "page";
        const key = `${kind}::${transition.value}`;
        const current = groups.get(key) || {
          key,
          kind,
          status: transition.value,
          transitionLabel: transition.label,
          pages: [],
        };
        current.pages.push(page);
        groups.set(key, current);
      });
    });
    return Array.from(groups.values())
      .filter((group) => group.pages.length >= 2)
      .map((group) => {
        const count = group.pages.length;
        const kindLabel = this.reviewKindLabel(group.kind, count);
        return {
          key: group.key,
          kind: group.kind,
          status: group.status,
          label: `${group.transitionLabel} · ${count} ${kindLabel}`,
          description: `${count} ${kindLabel} ${this.t("share the recommended transition")} ${String(group.transitionLabel || "").toLowerCase()}.`,
          pagePaths: group.pages.map((page) => page.pagePath).filter(Boolean),
          pages: group.pages,
          statusOptions: this.commonReviewTransitionOptions(group.pages),
        };
      })
      .sort((left, right) => {
        if (right.pagePaths.length !== left.pagePaths.length) {
          return right.pagePaths.length - left.pagePaths.length;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  rewriteControlItems(mode = "review") {
    const proposals = this.reviewControlList("rewrite_proposals");
    return uniqueContextOptions(
      proposals
        .filter((proposal) => (mode === "apply" ? Boolean(proposal.can_apply) : Boolean(proposal.can_review)))
        .map((proposal) => {
          const status = String(proposal.status || "").trim() || "unknown";
          const priority = String(proposal.priority || "").trim() || "medium";
          return {
            value: proposal.slug,
            label: proposal.title || proposal.slug || "rewrite-proposal",
            description: `${displayRewriteStatus(status, this.locale())} | ${this.t("priority")} ${priority} | ${this.t("score")} ${proposal.score || 0}`,
            slug: String(proposal.slug || ""),
            status,
            currentStatus: String(proposal.current_status || status),
            proposalPath: String(proposal.proposal_path || ""),
            targetPath: String(proposal.target_path || ""),
            canApply: Boolean(proposal.can_apply),
            canRefreshReview: Boolean(proposal.can_refresh_review),
            allowedTransitions: Array.isArray(proposal.allowed_transitions) ? proposal.allowed_transitions : [],
            preferredTransitions: Array.isArray(proposal.preferred_transitions) ? proposal.preferred_transitions : [],
            defaultTransition: String(proposal.default_transition || ""),
          };
        }),
      "slug"
    );
  }

  actionControlItems(mode = "review") {
    return uniqueContextOptions(
      this.executionControlList("actions")
        .filter((action) => {
          if (mode === "apply") {
            return Boolean(action.can_apply);
          }
          if (mode === "revert") {
            return Boolean(action.can_revert);
          }
          return Boolean(action.can_review);
        })
        .map((action) => {
          const status = String(action.status || "").trim() || "unknown";
          const priority = String(action.priority || "").trim() || "medium";
          const primaryPath = String(action.primary_path || "").trim();
          return {
            value: action.action_id,
            label: action.title || action.action_id || "action",
            description: `${displayActionStatus(status, this.locale())} | ${this.t("priority")} ${priority}${primaryPath ? ` | ${primaryPath}` : ""}`,
            actionId: String(action.action_id || ""),
            status,
            currentStatus: String(action.current_status || status),
            bundlePath: String(action.bundle_path || ""),
            canRefreshReview: Boolean(action.can_refresh_review),
            allowedTransitions: Array.isArray(action.allowed_transitions) ? action.allowed_transitions : [],
            preferredTransitions: Array.isArray(action.preferred_transitions) ? action.preferred_transitions : [],
            defaultTransition: String(action.default_transition || ""),
          };
        }),
      "actionId"
    );
  }

  archiveControlItems(mode = "apply") {
    return uniqueContextOptions(
      this.executionControlList("archives")
        .filter((entry) => (mode === "revert" ? Boolean(entry.can_revert) : Boolean(entry.can_apply)))
        .map((entry) => {
          const candidateStatus = String(entry.candidate_status || "").trim();
          const currentTemperature = String(entry.current_temperature || "").trim();
          return {
            value: entry.entry_id,
            label: entry.title || entry.entry_id || "archive-entry",
            description: `${this.t(candidateStatus || currentTemperature || "archive")} | ${entry.source_path || ""}`,
            entryId: String(entry.entry_id || ""),
            allowedTransitions: Array.isArray(entry.allowed_transitions) ? entry.allowed_transitions : [],
            preferredTransitions: Array.isArray(entry.preferred_transitions) ? entry.preferred_transitions : [],
            defaultTransition: String(entry.default_transition || ""),
          };
        }),
      "entryId"
    );
  }

  actionControlsById() {
    const controls = this.executionControlList("actions");
    return new Map(
      controls
        .filter((action) => action && typeof action === "object" && String(action.action_id || "").trim())
        .map((action) => [String(action.action_id || "").trim(), action])
    );
  }

  archiveControlsById() {
    const controls = this.executionControlList("archives");
    return new Map(
      controls
        .filter((entry) => entry && typeof entry === "object" && String(entry.entry_id || "").trim())
        .map((entry) => [String(entry.entry_id || "").trim(), entry])
    );
  }

  transitionLabel(controlType, transition) {
    if (controlType === "page") {
      return displayCuratedStatus(transition, this.locale());
    }
    if (controlType === "rewrite") {
      return displayRewriteStatus(transition, this.locale());
    }
    if (controlType === "action") {
      return displayActionStatus(transition, this.locale());
    }
    if (controlType === "archive") {
      return transition === "revert" ? this.t("Revert archive") : this.t("Apply archive");
    }
    return this.t(String(transition || "transition"));
  }

  transitionOptions(controlType, control) {
    if (!control || typeof control !== "object") {
      return [];
    }
    const allowed = Array.isArray(control.allowedTransitions || control.allowed_transitions)
      ? (control.allowedTransitions || control.allowed_transitions)
      : [];
    const preferredSet = new Set(
      (Array.isArray(control.preferredTransitions || control.preferred_transitions)
        ? (control.preferredTransitions || control.preferred_transitions)
        : []
      ).map((item) => String(item || "").trim()).filter(Boolean)
    );
    const defaultTransition = String(control.defaultTransition || control.default_transition || "").trim();
    return allowed
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .map((value) => ({
        value,
        label: this.transitionLabel(controlType, value),
        description: preferredSet.has(value) ? this.t("preferred transition") : this.t("allowed transition"),
        isDefault: value === defaultTransition,
        isPreferred: preferredSet.has(value),
      }))
      .sort((left, right) => {
        if (left.isDefault !== right.isDefault) {
          return left.isDefault ? -1 : 1;
        }
        if (left.isPreferred !== right.isPreferred) {
          return left.isPreferred ? -1 : 1;
        }
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  preferredTransitionOptions(controlType, control) {
    return this.transitionOptions(controlType, control).filter((option) => option.isPreferred).slice(0, 2);
  }

  manualReviewOption(controlType) {
    const labelMap = {
      page: this.t("Manual review..."),
      rewrite: this.t("Manual rewrite review..."),
      action: this.t("Manual action review..."),
    };
    return {
      value: "__manual__",
      label: labelMap[controlType] || this.t("Manual review..."),
      description: this.t("keep current status and capture note / confidence in the full form"),
      isManual: true,
      isPreferred: false,
      isDefault: false,
    };
  }

  openTransitionPicker({ title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice }) {
    const transitionOptions = this.transitionOptions(controlType, control);
    if (!transitionOptions.length && typeof onManual !== "function") {
      if (emptyNotice) {
        new Notice(emptyNotice);
      }
      if (typeof onFallback === "function") {
        onFallback();
      }
      return;
    }
    if (!transitionOptions.length && typeof onManual === "function") {
      onManual();
      return;
    }
    if (transitionOptions.length === 1 && typeof onManual !== "function") {
      onSubmit(transitionOptions[0].value);
      return;
    }
    const options = transitionOptions.slice();
    if (typeof onManual === "function") {
      options.push(this.manualReviewOption(controlType));
    }
    this.openContextPicker({
      title,
      description,
      submitLabel: this.t("Use"),
      options,
      onSubmit: (option) => {
        if (option && option.isManual && typeof onManual === "function") {
          onManual();
          return;
        }
        onSubmit(option.value);
      },
    });
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
    const options = uniqueContextOptions(spec.options || [], spec.keyName || "value");
    if (!options.length) {
      new Notice(spec.emptyNotice || this.t("No context is currently available; fell back to the manual form."));
      spec.onFallback();
      return;
    }
    if (options.length === 1) {
      spec.onSubmit(options[0]);
      return;
    }
    this.openContextPicker({
      title: spec.title,
      description: spec.description,
      submitLabel: spec.submitLabel || "Use",
      options,
      onSubmit: spec.onSubmit,
    });
  }

  async handleVaultChange(relativePath) {
    if (!relativePath) {
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
    const summaryFile = this.app.vault.getAbstractFileByPath(SHELL_SUMMARY_PATH);
    if (!summaryFile) {
      this.shellSummary = null;
      this.updateStatusBar();
      this.refreshOpenViews();
      return null;
    }
    try {
      const text = await this.app.vault.cachedRead(summaryFile);
      this.shellSummary = readJsonText(text);
      this.processShellSummaryUpdates(this.shellSummary);
    } catch (error) {
      console.error("[furnace-product-shell] failed to read shell summary", error);
      this.shellSummary = null;
    }
    this.updateStatusBar();
    this.refreshOpenViews();
    return this.shellSummary;
  }

  async execLauncher(args) {
    if (!this.repoState.valid) {
      throw new Error(this.t("Missing runtime paths: {missing}", { missing: this.repoState.missingPaths.join(", ") }));
    }
    return await new Promise((resolve, reject) => {
      const env = Object.assign({}, process.env);
      if (this.settings.llmBackend) {
        env.AIWIKI_LLM_BACKEND = this.settings.llmBackend;
      }
      if (this.settings.llmModel) {
        env.AIWIKI_LLM_MODEL = this.settings.llmModel;
      }
      if (this.settings.llmNvidiaNimApiKey) {
        env.AIWIKI_NVIDIA_NIM_API_KEY = this.settings.llmNvidiaNimApiKey;
      }
      if (this.settings.llmNvidiaNimBaseUrl) {
        env.AIWIKI_NVIDIA_NIM_BASE_URL = this.settings.llmNvidiaNimBaseUrl;
      }
      Object.assign(env, buildNotifyEnv(this.settings));
      const child = spawn(this.repoState.launcherPath, args, {
        cwd: this.repoState.root,
        env,
      });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (chunk) => {
        stdout += String(chunk);
      });
      child.stderr.on("data", (chunk) => {
        stderr += String(chunk);
      });
      child.on("error", (error) => {
        reject(error);
      });
      child.on("close", (code) => {
        let payload = null;
        try {
          payload = readJsonText(stdout);
        } catch (error) {
          payload = null;
        }
        if (code === 0) {
          resolve({ stdout, stderr, payload, code });
          return;
        }
        const error = new Error(stderr.trim() || stdout.trim() || this.t("Command failed with exit code {code}", { code }));
        error.code = code;
        error.stdout = stdout;
        error.stderr = stderr;
        error.payload = payload;
        reject(error);
      });
    });
  }

  runUiAction(action, label = "ui-action") {
    Promise.resolve()
      .then(() => action())
      .catch((error) => {
        console.error(`[furnace-product-shell] ${label} failed`, error);
      });
  }

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
    if (!record || typeof record !== "object") {
      return;
    }
    const logPath = String(record.logPath || runLogRelativePath(record)).trim();
    const absolutePath = this.resolveAbsoluteWorkspacePath(logPath);
    if (!logPath || !absolutePath) {
      return;
    }
    record.logPath = logPath;
    const stdoutText = String(details.stdoutRaw || record.stdoutRaw || "").trim();
    const stderrText = String(details.stderrRaw || record.stderrRaw || "").trim();
    const rewriteProposalObjects = this.normalizeRewriteProposalObjects(record.rewriteProposalObjects || []);
    const rewriteProposalCount = rewriteProposalObjects.length || (Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths.length : 0);
    const lines = [
      "# Product Shell Run Log",
      "",
      this.t("Generated by Product Shell run logging."),
      "",
      `- ${this.t("Status")}: ${this.t(record.status || "unknown")}`,
      `- ${this.t("Protocol")}: ${record.protocol ? this.t(record.protocol) : this.t("unknown")}`,
      `- ${this.t("LLM Backend")}: ${record.backend || this.t("unconfigured")}`,
      `- backend requested: ${record.backendRequested || "-"}`,
      `- backend effective: ${record.backendEffective || record.backend || "-"}`,
      `- ${this.t("LLM Model")}: ${record.model || this.t("default")}`,
      `- model selected: ${record.modelSelected || "-"}`,
      `- model final: ${record.modelFinal || record.model || "-"}`,
      `- ${this.t("Codex effort")}: ${record.codexReasoningEffort || "-"}`,
      `- ${this.t("Prompt profile")}: ${record.promptProfile || "-"}`,
      `- ${this.t("Retry prompt")}: ${record.retryPromptProfile || "-"}`,
      `- fallback stage: ${record.fallbackStage || "-"}`,
      `- fallback reason: ${record.fallbackReason || "-"}`,
      `- contract validated: ${record.contractValidated ? "yes" : "no"}`,
      `- ${this.t("Working directory")}: ${this.repoState.root || "."}`,
      `- ${this.t("Arguments")}: ${record.args || record.command || ""}`,
      `- ${this.t("Fallback from")}: ${record.fallbackFrom || "-"}`,
      `- ${this.t("Result path")}: ${record.resultPath || "-"}`,
      `- ${this.t("Receipt path")}: ${record.receiptPath || "-"}`,
      ...(rewriteProposalCount
        ? [`- ${this.t("rewrite proposals: {count}", { count: rewriteProposalCount })}`]
        : []),
      `- ${this.t("Log path")}: ${logPath}`,
      `- ${this.t("Exit code")}: ${record.exitCode === "" ? "-" : String(record.exitCode)}`,
      `- started: ${record.startedAt || "-"}`,
      `- finished: ${record.finishedAt || "-"}`,
      "",
      "## Timeline",
      "",
    ];
    const timeline = Array.isArray(record.timeline) ? record.timeline : [];
    if (!timeline.length) {
      lines.push(`- ${this.t("No stage events recorded.")}`);
    } else {
      timeline.forEach((event) => {
        lines.push(`- ${event.at || "-"} | ${this.t(event.stage || "event")} | ${event.summary || "-"}`);
      });
    }
    if (record.resultPath || record.receiptPath || record.errorSummary) {
      lines.push("", "## Summary", "");
      if (record.resultPath) {
        lines.push(`- ${this.t("Result path")}: ${record.resultPath}`);
      }
      if (record.receiptPath) {
        lines.push(`- ${this.t("Receipt path")}: ${record.receiptPath}`);
      }
      if (record.errorSummary) {
        lines.push(`- error: ${record.errorSummary}`);
      }
      if (rewriteProposalObjects.length) {
        lines.push(`- ${this.t("rewrite proposals: {count}", { count: rewriteProposalObjects.length })}`);
        rewriteProposalObjects.forEach((proposal) => {
          lines.push(`  - ${proposal.title || proposal.slug}: ${proposal.proposalPath || proposal.targetPath || proposal.slug}`);
        });
      } else if (Array.isArray(record.rewriteProposalPaths) && record.rewriteProposalPaths.length) {
        lines.push(`- ${this.t("rewrite proposals: {count}", { count: record.rewriteProposalPaths.length })}`);
        record.rewriteProposalPaths.forEach((proposalPath) => {
          lines.push(`  - ${proposalPath}`);
        });
      }
    }
    if (stdoutText) {
      lines.push("", "## Standard output", "", "```text", stdoutText, "```");
    }
    if (stderrText) {
      lines.push("", "## Standard error", "", "```text", stderrText, "```");
    }
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, `${lines.join("\n")}\n`, "utf8");
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
    const llm = this.currentLlmSelection();
    const protocol = this.getActiveProtocol();
    const runId = `run-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const record = {
      id: runId,
      label,
      args: args.join(" "),
      argv: Array.isArray(args) ? args.slice() : [],
      command: Array.isArray(args) && args.length ? String(args[0] || "") : "",
      status: "running",
      startedAt: new Date().toISOString(),
      finishedAt: "",
      protocol,
      backend: llm.backend,
      backendRequested: llm.backend,
      backendEffective: llm.backend,
      model: llm.model,
      modelSelected: llm.model,
      modelFinal: llm.model,
      codexReasoningEffort: llm.codexReasoningEffort || "",
      promptProfile: "",
      retryPromptProfile: "",
      fallbackStage: "",
      fallbackReason: "",
      contractValidated: false,
      rewriteProposalObjects: [],
      rewriteRecoveryActions: [],
      rewriteProposalPaths: [],
      rewriteProposalSlugs: [],
      stdoutSummary: "",
      stderrSummary: "",
      stdoutRaw: "",
      stderrRaw: "",
      resultPath: "",
      receiptPath: "",
      logPath: `output/control/plugin-runs/${runId}.md`,
      exitCode: "",
      errorSummary: "",
      fallbackFrom: "",
      fallbackCommand: "",
      fallbackUsed: false,
      deliveryMode: "",
      timeline: [],
    };
    appendRunEvent(record, "Submitted", label || record.args || "command", "running");
    if (record.protocol || record.backend || record.model) {
      const context = [record.protocol, record.backend, record.model].filter(Boolean).join(" · ");
      appendRunEvent(record, "Runtime selected", context, "running");
    }
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
      appendRunEvent(record, "Completed", primaryPath || receiptPath || this.t("Command completed successfully."), "success");
      if (primaryPath || receiptPath) {
        appendRunEvent(record, "Artifacts", [primaryPath, receiptPath].filter(Boolean).join(" · "), "success");
      }
      if (rewriteProposalPaths.length) {
        appendRunEvent(record, "Rewrite proposals", this.rewriteProposalSummary({ rewriteProposalPaths }), "success");
      }
      this.updateRunRecord(record, {
        status: "success",
        finishedAt: new Date().toISOString(),
        exitCode: 0,
        backend: result.payload && typeof result.payload.backend_effective === "string" ? result.payload.backend_effective : (llm.backend || record.backend),
        backendRequested:
          result.payload && typeof result.payload.backend_requested === "string" ? result.payload.backend_requested : (record.backendRequested || llm.backend || record.backend),
        backendEffective:
          result.payload && typeof result.payload.backend_effective === "string" ? result.payload.backend_effective : (llm.backend || record.backend),
        model:
          result.payload && typeof result.payload.model_final === "string" ? result.payload.model_final : (llm.model || record.model),
        modelSelected:
          result.payload && typeof result.payload.model_selected === "string" ? result.payload.model_selected : (record.modelSelected || llm.model || record.model),
        modelFinal:
          result.payload && typeof result.payload.model_final === "string" ? result.payload.model_final : (llm.model || record.model),
        codexReasoningEffort: llm.codexReasoningEffort || record.codexReasoningEffort,
        promptProfile: result.payload && typeof result.payload.prompt_profile === "string" ? result.payload.prompt_profile : record.promptProfile,
        retryPromptProfile:
          result.payload && typeof result.payload.retry_prompt_profile === "string" ? result.payload.retry_prompt_profile : record.retryPromptProfile,
        fallbackStage: result.payload && typeof result.payload.fallback_stage === "string" ? result.payload.fallback_stage : record.fallbackStage,
        fallbackReason: result.payload && typeof result.payload.fallback_reason === "string" ? result.payload.fallback_reason : record.fallbackReason,
        fallbackFrom: result.payload && typeof result.payload.fallback_from === "string" ? result.payload.fallback_from : record.fallbackFrom,
        fallbackCommand: result.payload && typeof result.payload.fallback_command === "string" ? result.payload.fallback_command : (record.fallbackCommand || ""),
        fallbackUsed: result.payload && Object.prototype.hasOwnProperty.call(result.payload, "fallback_used")
          ? Boolean(result.payload.fallback_used)
          : Boolean(record.fallbackUsed),
        deliveryMode: result.payload && typeof result.payload.delivery_mode === "string" ? result.payload.delivery_mode : (record.deliveryMode || ""),
        contractValidated:
          result.payload && Object.prototype.hasOwnProperty.call(result.payload, "contract_validated")
            ? Boolean(result.payload.contract_validated)
            : record.contractValidated,
        rewriteProposalObjects,
        rewriteRecoveryActions,
        rewriteProposalPaths,
        rewriteProposalSlugs,
        stdoutSummary: truncateText(result.stdout),
        stderrSummary: truncateText(result.stderr),
        stdoutRaw: trimDiagnosticText(result.stdout),
        stderrRaw: trimDiagnosticText(result.stderr),
        resultPath: primaryPath,
        receiptPath,
      });
      if (record.command === "run-ask") {
        const usedFallback = Boolean(record.fallbackUsed) || String(record.deliveryMode || "").trim() === "deterministic-fallback";
        this.recordLlmHealthFromRun(record, {
          status: usedFallback ? "degraded" : "healthy",
          reason: usedFallback ? "Recent run-ask fell back to deterministic ask." : "Recent run-ask succeeded.",
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
        new Notice(`${this.t(label)} ${this.t("completed")}.`);
      }
      return result.payload;
    } catch (error) {
      appendRunEvent(record, "Failed", truncateText(error.message || "Command failed", 180), "failed");
      this.updateRunRecord(record, {
        status: "failed",
        finishedAt: new Date().toISOString(),
        exitCode: Number.isFinite(Number(error.code)) ? Number(error.code) : "",
        stdoutSummary: truncateText(error.stdout || ""),
        stderrSummary: truncateText(error.stderr || ""),
        stdoutRaw: trimDiagnosticText(error.stdout || ""),
        stderrRaw: trimDiagnosticText(error.stderr || ""),
        errorSummary: truncateText(error.message || "Command failed"),
      });
      if (record.command === "run-ask" && llmBackendUnavailable(error)) {
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
    if (!summary || !Array.isArray(summary.recent_outputs)) return;
    const outputs = summary.recent_outputs.filter((item) => item && typeof item === "object");
    const currentIds = outputs.map((r) => r.path || r.title || r.created_at).filter(Boolean);
    const lastIds = Array.isArray(this.settings.lastKnownReportIds) ? this.settings.lastKnownReportIds.filter(Boolean) : [];

    if (!currentIds.length) {
      this.settings.lastKnownReportIds = [];
      void this.savePluginState();
      return;
    }

    if (!lastIds.length && outputs.length > 0) {
      this.settings.lastKnownReportIds = currentIds;
      void this.savePluginState();
      return;
    }

    const newIds = currentIds.filter((id) => !lastIds.includes(id));
    if (!newIds.length) {
      if (currentIds.length !== lastIds.length || currentIds.some((id, i) => id !== lastIds[i])) {
        this.settings.lastKnownReportIds = currentIds;
        void this.savePluginState();
      }
      return;
    }

    this.settings.lastKnownReportIds = currentIds;
    void this.savePluginState();
  }

  async refreshShellSummaryCommand() {
    await this.runPluginCommand(this.t("Refresh Furnace Shell"), ["shell-status"], {
      refreshAfter: false,
      updateSummaryFromPayload: true,
      notice: false,
    });
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

  async runUniversalInputCommand({ payload, title }) {
    const normalizedPayload = String(payload || "").trim();
    if (!normalizedPayload) {
      new Notice(this.t("Universal input cannot be empty."));
      return;
    }
    const args = ["drop", normalizedPayload];
    const normalizedTitle = String(title || "").trim();
    if (normalizedTitle) {
      args.push("--title", normalizedTitle);
    }
    await this.runPluginCommand(`${this.t("Universal Input")}: ${truncateText(normalizedTitle || normalizedPayload, 48)}`, args, { refreshAfter: true });
  }

  async runAskCommand({ question, format, mode, protocol }) {
    const args = [mode, question, "--format", format];
    if (protocol) {
      args.push("--protocol", protocol);
    }
    if (mode === "run-ask") {
      args.push("--fallback-to-ask");
    }
    await this.runPluginCommand(`${this.t("Ask")}: ${truncateText(question, 48)}`, args, { refreshAfter: true });
  }

  async runDropUrlCommand({ url, title }) {
    const args = ["drop", "url", url];
    if (title) {
      args.push("--title", title);
    }
    await this.runPluginCommand(`${this.t("Drop URL")}: ${truncateText(title || url, 48)}`, args, { refreshAfter: true });
  }

  openDropUrlModal(initialUrl = "") {
    new DropUrlModal(this.app, this).setInitialUrl(initialUrl).open();
  }

  async runDropFileCommand({ mode, source, title, maxFiles }) {
    const normalizedMode = String(mode || "pdf").trim() === "repo" ? "repo" : "pdf";
    const args = ["drop", normalizedMode === "repo" ? "repo" : "pdf", source];
    if (title) {
      args.push("--title", title);
    }
    if (normalizedMode === "repo") {
      args.push("--max-files", String(Number.isFinite(Number(maxFiles)) && Number(maxFiles) > 0 ? Number(maxFiles) : 200));
    }
    await this.runPluginCommand(`${this.t("Drop File")}: ${truncateText(title || path.basename(source) || source, 48)}`, args, { refreshAfter: true });
  }

  async runDropImageCommand({ source, title, noVision }) {
    const args = ["drop", "image", source];
    if (title) {
      args.push("--title", title);
    }
    if (noVision) {
      args.push("--no-vision");
    }
    await this.runPluginCommand(`${this.t("Drop Image")}: ${truncateText(title || path.basename(source) || source, 48)}`, args, { refreshAfter: true });
  }

  async runDropNoteCommand({ text, title, kind }) {
    const args = ["drop", "note", "--text", text];
    if (title) {
      args.push("--title", title);
    }
    args.push("--kind", kind || "note");
    await this.runPluginCommand(`${this.t("Capture Note")}: ${truncateText(title || text, 48)}`, args, { refreshAfter: true });
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
    this.openStructuredCommandModal({
      title: this.t("File Back"),
      description: this.t("File an output artifact back into wiki/derived, wiki/decisions, or wiki/judgments."),
      fields: [
        {
          key: "artifact",
          label: this.t("Artifact path"),
          required: true,
          placeholder: this.t("output/reports/....md"),
          initialValue: () => prefill.artifact || this.getActiveOutputPath(),
        },
        {
          key: "title",
          label: this.t("Title"),
          placeholder: this.t("Optional filed-back title"),
          initialValue: prefill.title || "",
        },
        {
          key: "kind",
          label: this.t("Kind"),
          kind: "select",
          initialValue: prefill.kind || "derived",
          options: [
            ["derived", this.t("derived")],
            ["decision", this.t("decision")],
            ["judgment", this.t("judgment")],
          ],
        },
        {
          key: "protocol",
          label: this.t("Protocol"),
          kind: "select",
          initialValue: prefill.protocol || "",
          options: [["", this.t("current protocol")], ...this.getAvailableProtocols().map((item) => [item, item])],
        },
      ],
      onSubmit: async (values) => {
        const args = [values.artifact];
        appendOptionalArg(args, "--title", values.title);
        appendOptionalArg(args, "--kind", values.kind);
        appendOptionalArg(args, "--protocol", values.protocol);
        await this.runCliAction(`File Back: ${values.kind}`, "file-back", args);
      },
    });
  }

  openReviewPageModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Review Page"),
      description: this.t("Advance a decision or judgment page through the explicit review workflow."),
      fields: [
        {
          key: "page",
          label: this.t("Page path"),
          required: true,
          placeholder: this.t("wiki/decisions/... or wiki/judgments/..."),
          initialValue: () => prefill.pagePath || this.getActiveCuratedPagePath(),
        },
        {
          key: "status",
          label: this.t("Status"),
          required: true,
          placeholder: this.t("approved / confirmed / needs-revision ..."),
          initialValue: prefill.status || "",
        },
        {
          key: "note",
          label: this.t("Note"),
          kind: "textarea",
          placeholder: this.t("Optional review note"),
          rows: 4,
          initialValue: prefill.note || "",
        },
        {
          key: "confidence",
          label: this.t("Confidence"),
          placeholder: this.t("Optional confidence override"),
          initialValue: prefill.confidence || "",
        },
      ],
      onSubmit: async (values) => {
        const args = [values.page, "--status", values.status];
        appendOptionalArg(args, "--note", values.note);
        appendOptionalArg(args, "--confidence", values.confidence);
        await this.runCliAction(`Review Page: ${values.status}`, "review-page", args);
      },
    });
  }

  openReviewRewriteModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Review Rewrite"),
      description: this.t("Advance a concept rewrite proposal through the rewrite workflow."),
      fields: [
        { key: "slug", label: this.t("Concept slug"), required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "status", label: this.t("Status"), required: true, placeholder: this.t("accepted / rejected / needs-revision ..."), initialValue: prefill.status || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional review note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug, "--status", values.status];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Review Rewrite: ${values.slug}`, "review-rewrite", args);
      },
    });
  }

  openApplyRewriteModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Apply Rewrite"),
      description: this.t("Apply an accepted concept rewrite proposal."),
      fields: [
        { key: "slug", label: this.t("Concept slug"), required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional apply note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Apply Rewrite: ${values.slug}`, "apply-rewrite", args);
      },
    });
  }

  openRetireConceptModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Retire Concept"),
      description: this.t("Apply an explicit retired override for a concept."),
      fields: [
        { key: "slug", label: this.t("Concept slug"), required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Why retire this concept?"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Retire Concept: ${values.slug}`, "retire-concept", args);
      },
    });
  }

  openReactivateConceptModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Reactivate Concept"),
      description: this.t("Clear the explicit retired override for a concept."),
      fields: [
        { key: "slug", label: this.t("Concept slug"), required: true, initialValue: () => prefill.slug || this.getActiveConceptSlug() },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional reactivate note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.slug];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Reactivate Concept: ${values.slug}`, "reactivate-concept", args);
      },
    });
  }

  openApplyArchiveModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Apply Archive"),
      description: this.t("Apply a ready archive candidate and pin it to archived."),
      fields: [
        { key: "entry_id", label: this.t("Entry id"), required: true, placeholder: this.t("manifest/material entry id"), initialValue: prefill.entryId || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional apply note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.entry_id];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Apply Archive: ${values.entry_id}`, "apply-archive", args);
      },
    });
  }

  openRevertArchiveModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Revert Archive"),
      description: this.t("Revert the latest explicit archive transition."),
      fields: [
        { key: "entry_id", label: this.t("Entry id"), required: true, placeholder: this.t("manifest/material entry id"), initialValue: prefill.entryId || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional revert note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.entry_id];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Revert Archive: ${values.entry_id}`, "revert-archive", args);
      },
    });
  }

  openReviewActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Review Action"),
      description: this.t("Advance a machine-memory repair action through the explicit action workflow."),
      fields: [
        { key: "action_id", label: this.t("Action id"), required: true, placeholder: this.t("machine-memory action id"), initialValue: prefill.actionId || "" },
        { key: "status", label: this.t("Status"), required: true, placeholder: this.t("accepted / rejected / ready ..."), initialValue: prefill.status || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional action review note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id, "--status", values.status];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Review Action: ${values.action_id}`, "review-action", args);
      },
    });
  }

  openApplyActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Apply Action"),
      description: this.t("Apply an accepted low-risk machine-memory repair action."),
      fields: [
        { key: "action_id", label: this.t("Action id"), required: true, placeholder: this.t("machine-memory action id"), initialValue: prefill.actionId || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional apply note"), initialValue: prefill.note || "" },
        { key: "bundle", label: this.t("Bundle path"), placeholder: this.t("Optional execution bundle path"), initialValue: prefill.bundle || "" },
        { key: "dry_run", label: this.t("Dry run"), kind: "toggle", initialValue: Boolean(prefill.dryRun) },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id];
        appendOptionalArg(args, "--note", values.note);
        appendOptionalArg(args, "--bundle", values.bundle);
        if (values.dry_run) {
          args.push("--dry-run");
        }
        await this.runCliAction(`Apply Action: ${values.action_id}`, "apply-action", args);
      },
    });
  }

  openRevertActionModal(prefill = {}) {
    this.openStructuredCommandModal({
      title: this.t("Revert Action"),
      description: this.t("Revert the latest low-risk safe apply for a machine-memory action."),
      fields: [
        { key: "action_id", label: this.t("Action id"), required: true, placeholder: this.t("machine-memory action id"), initialValue: prefill.actionId || "" },
        { key: "note", label: this.t("Note"), kind: "textarea", rows: 4, placeholder: this.t("Optional revert note"), initialValue: prefill.note || "" },
      ],
      onSubmit: async (values) => {
        const args = [values.action_id];
        appendOptionalArg(args, "--note", values.note);
        await this.runCliAction(`Revert Action: ${values.action_id}`, "revert-action", args);
      },
    });
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
    const pagePaths = Array.isArray(prefill.pagePaths) ? prefill.pagePaths : [];
    const statusOptions = Array.isArray(prefill.statusOptions) ? prefill.statusOptions : [];
    const normalizedStatusOptions = statusOptions.map((option) => ({
      value: option.value,
      label: option.label || this.transitionLabel("page", option.value),
    }));
    const statusField = normalizedStatusOptions.length
      ? {
          key: "status",
          label: this.t("Status"),
          required: true,
          kind: "select",
          initialValue: prefill.status || normalizedStatusOptions[0].value || "",
          options: normalizedStatusOptions,
        }
      : {
          key: "status",
          label: this.t("Status"),
          required: true,
          placeholder: this.t("tracking / needs-revisit / approved ..."),
          initialValue: prefill.status || "",
        };
    this.openStructuredCommandModal({
      title: this.t("Batch Review Pages"),
      description: prefill.description || this.t("Advance multiple review pages that share a safe common transition."),
      submitLabel: this.t("Run batch"),
      fields: [
        {
          key: "pages",
          label: this.t("Page paths"),
          required: true,
          kind: "textarea",
          rows: 6,
          placeholder: this.t("wiki/judgments/... (one per line)"),
          initialValue: pagePaths.join("\n"),
        },
        statusField,
        {
          key: "note",
          label: this.t("Note"),
          kind: "textarea",
          rows: 4,
          placeholder: this.t("Optional shared batch note"),
          initialValue: prefill.note || "",
        },
        {
          key: "confidence",
          label: this.t("Confidence"),
          placeholder: this.t("Optional shared confidence override"),
          initialValue: prefill.confidence || "",
        },
      ],
      onSubmit: async (values) => {
        const paths = parseLineList(values.pages);
        if (!paths.length) {
          throw new Error(this.t("Batch review requires at least one page path."));
        }
        await this.runReviewPageBatchTransition(paths, values.status, values.note, values.confidence);
      },
    });
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
    const normalized = String(relativePath || "").trim();
    if (!normalized) {
      new Notice(this.t("No path to open."));
      return;
    }
    const abstractFile = this.app.vault.getAbstractFileByPath(normalized);
    if (abstractFile && normalized.endsWith(".md")) {
      const leaf = this.app.workspace.getLeaf(true);
      await leaf.openFile(abstractFile);
      return;
    }
    if (!this.repoState.root) {
      new Notice(this.t("Unable to open {path}", { path: normalized }));
      return;
    }
    const absolutePath = path.join(this.repoState.root, normalized);
    if (!fs.existsSync(absolutePath)) {
      new Notice(this.t("Path not found: {path}", { path: normalized }));
      return;
    }
    if (typeof this.app.vault.adapter.getResourcePath === "function") {
      const resourcePath = this.app.vault.adapter.getResourcePath(normalized);
      window.open(resourcePath, "_blank");
      return;
    }
    new Notice(this.t("Unable to open resource: {path}", { path: normalized }));
  }


  // --- Render method wrappers (delegate to render.js standalone functions) ---

  renderCardGrid(container, cards) {
    renderCardGrid(this, container, cards);
  }

  renderActionButtons(container, buttons) {
    renderActionButtons(this, container, buttons);
  }

  renderGettingStartedSection(container) {
    renderGettingStartedSection(this, container);
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

  latestInteractionEntry() {
    return latestInteractionEntry(this);
  }

  renderMainHeader(container) {
    renderMainHeader(this, container);
  }

  renderInteractionPanel(container) {
    renderInteractionPanel(this, container);
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

  
  renderAskBox(container) {
    renderAskBox(this, container);
  }
  renderReportsPanel(container, reports) {
    renderReportsPanel(this, container, reports);
  }
  renderReportsGroup(container, reports, emptyText) {
    renderReportsGroup(this, container, reports, emptyText);
  }
  renderDropZone(container) {
    renderDropZone(this, container);
  }
  renderAdvancedDrawer(container) {
    renderAdvancedDrawer(this, container);
  }

  renderLegacyAdvancedPanel(container) {
    renderLegacyAdvancedPanel(this, container);
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
