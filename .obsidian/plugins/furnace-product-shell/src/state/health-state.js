// Extracted from plugin.js

const LLM_HEALTH_FAILURE_NOTICE_DELIVERY_MODES = {
    "deterministic-fallback": true,
    "llm-failed": true,
  };

function normalizeLlmHealthState(plugin, value) {
    if (!value || typeof value !== "object") {
      return null;
    }
    const status = String(value.status || "").trim() || "unknown";
    const fallbackCommandValue = preferredObjectField(value, "fallbackCommand", "fallback_command");
    const recoveryCommandValue = preferredObjectField(value, "recoveryCommand", "recovery_command");
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
      fallbackCommand: String(fallbackCommandValue || "").trim(),
      fallbackStage: String(value.fallbackStage || value.fallback_stage || "").trim(),
      fallbackReason: String(value.fallbackReason || value.fallback_reason || "").trim(),
      contractValidated: Object.prototype.hasOwnProperty.call(value, "contractValidated")
        ? Boolean(value.contractValidated)
        : Boolean(value.contract_validated),
      recoveryCommand: String(recoveryCommandValue || "").trim(),
      routeDrift: Boolean(value.routeDrift || value.route_drift),
      routeDriftReason: String(value.routeDriftReason || value.route_drift_reason || "").trim(),
      logPath: String(value.logPath || value.log_path || "").trim(),
      resultPath: String(value.resultPath || value.result_path || "").trim(),
      receiptPath: String(value.receiptPath || value.receipt_path || "").trim(),
      stderrSummary: String(value.stderrSummary || value.stderr_summary || "").trim(),
      stderrRaw: trimDiagnosticText(value.stderrRaw || value.stderr_raw || ""),
    };
  }


function preferredObjectField(value, preferredKey, legacyKey) {
    return Object.prototype.hasOwnProperty.call(value, preferredKey)
      ? value[preferredKey]
      : value[legacyKey];
  }


function llmHealthTimestamp(value) {
    const timestamp = Date.parse(String(value || "").trim());
    return Number.isFinite(timestamp) ? timestamp : 0;
  }


function shellSummaryHealthTimestamp(plugin, summaryHealth) {
    if (!plugin.shellSummary || typeof plugin.shellSummary !== "object") {
      return 0;
    }
    return Math.max(
      llmHealthTimestamp(summaryHealth && summaryHealth.checkedAt),
      llmHealthTimestamp(plugin.shellSummary.generated_at)
    );
  }


function shouldUsePluginLlmHealth(plugin, pluginHealth, summaryHealth) {
    if (!pluginHealth) {
      return false;
    }
    if (!summaryHealth) {
      return true;
    }
    const pluginTimestamp = llmHealthTimestamp(pluginHealth.checkedAt);
    const summaryTimestamp = shellSummaryHealthTimestamp(plugin, summaryHealth);
    return Boolean(pluginTimestamp) && pluginTimestamp > summaryTimestamp;
  }


function fillLlmHealthRoute(plugin, health, selected, llmStatus) {
    return {
      ...health,
      backend: health.backend || selected.backend || String(llmStatus.backend || ""),
      model: health.model || selected.model || String(llmStatus.effective_model || llmStatus.model || ""),
    };
  }


function currentLlmHealth(plugin) {
    const llmStatus = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.llm_status || {} : {};
    const summaryHealth = plugin.shellSummary && typeof plugin.shellSummary === "object"
      ? plugin.normalizeLlmHealthState(plugin.shellSummary.llm_health)
      : null;
    const pluginHealth = plugin.pluginState && typeof plugin.pluginState === "object"
      ? plugin.normalizeLlmHealthState(plugin.pluginState.llmHealth)
      : null;
    const selected = plugin.currentLlmSelection();
    if (shouldUsePluginLlmHealth(plugin, pluginHealth, summaryHealth)) {
      return fillLlmHealthRoute(plugin, pluginHealth, selected, llmStatus);
    }
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
    return fillLlmHealthRoute(plugin, summaryHealth, selected, llmStatus);
  }


function latestLlmRun(plugin) {
    if (plugin.shellSummary && typeof plugin.shellSummary === "object" && plugin.shellSummary.latest_llm_run && typeof plugin.shellSummary.latest_llm_run === "object") {
      const summaryRun = plugin.shellSummary.latest_llm_run;
      const fallbackFromValue = preferredObjectField(summaryRun, "fallbackFrom", "fallback_from");
      const fallbackCommandValue = preferredObjectField(summaryRun, "fallbackCommand", "fallback_command");
      return {
        ...summaryRun,
        command: String(summaryRun.command || summaryRun.event || "").trim(),
        backend: String(summaryRun.backend || summaryRun.backend_effective || summaryRun.backend_requested || "").trim(),
        model: String(summaryRun.model || summaryRun.model_final || summaryRun.model_selected || "").trim(),
        resultPath: String(summaryRun.resultPath || summaryRun.result_path || "").trim(),
        receiptPath: String(summaryRun.receiptPath || summaryRun.receipt_path || "").trim(),
        logPath: String(summaryRun.logPath || summaryRun.log_path || "").trim(),
        errorSummary: String(summaryRun.errorSummary || summaryRun.error || summaryRun.fallback_reason || "").trim(),
        fallbackFrom: String(fallbackFromValue || "").trim(),
        fallbackCommand: String(fallbackCommandValue || "").trim(),
        fallbackUsed: Boolean(summaryRun.fallbackUsed || summaryRun.fallback_used),
        deliveryMode: String(summaryRun.deliveryMode || summaryRun.delivery_mode || "").trim(),
      };
    }
    return null;
  }


function latestLlmRunLocalDegradedArtifact(latestLlmRun) {
    const deliveryMode = String(latestLlmRun && latestLlmRun.deliveryMode || "").trim();
    if (Object.prototype.hasOwnProperty.call(LLM_HEALTH_FAILURE_NOTICE_DELIVERY_MODES, deliveryMode)) return true;
    return !deliveryMode && Boolean(latestLlmRun && latestLlmRun.fallbackUsed);
  }

  // EP-015: latestShellSyncRun() removed. The sole authoritative source for
  // the last persisted shell-summary metadata is `shellSummary.latest_shell_sync_run`;
  // consumers should read it directly rather than going through a plugin
  // helper that could drift back into merging plugin-local recentRuns.

function currentShellSyncState(plugin) {
    // EP-015 Path 3: summary-only domain state.
    // 1. Own in-flight shell-status → running (only state recentRuns can
    //    legitimately contribute, since CLI snapshot cannot represent
    //    in-flight work).
    // 2. CLI snapshot present → healthy, using snapshot.generated_at.
    // 3. Otherwise → unknown.
    // We no longer synthesize a "failed" domain state from recentRuns;
    // recentRuns is plugin-local command history, not authoritative health.
    const runningRecord = plugin.pluginState.recentRuns.find(
      (record) => record && record.command === "shell-status" && record.status === "running"
    );
    if (runningRecord) {
      return {
        status: "running",
        reason: plugin.t("Refreshing shell summary."),
        checkedAt: runningRecord.startedAt || "",
        logPath: runningRecord.logPath || "",
      };
    }
    if (plugin.shellSummary && typeof plugin.shellSummary === "object") {
      const snapshot = plugin.shellSummary.latest_shell_sync_run;
      const hasSnapshot = snapshot && typeof snapshot === "object" && Object.keys(snapshot).length;
      const checkedAt = hasSnapshot
        ? String(snapshot.generated_at || plugin.shellSummary.generated_at || "")
        : String(plugin.shellSummary.generated_at || "");
      return {
        status: "healthy",
        reason: plugin.t("Summary ready."),
        checkedAt,
        logPath: "",
      };
    }
    return {
      status: "unknown",
      reason: plugin.t("数据还没生成。先点刷新，或等首次任务跑完。"),
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

function selfCheckItems(plugin) {
    const llmStatus = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary.llm_status || {} : {};
    const health = plugin.currentLlmHealth();
    const latestLlmRun = plugin.latestLlmRun();
    const availableBackends = Array.isArray(llmStatus.available_backends) ? llmStatus.available_backends.filter(Boolean) : [];
    const requestedBackend = String(llmStatus.backend_requested || plugin.settings.llmBackend || "").trim();
    const effectiveBackend = String(llmStatus.backend || "").trim();
    const selected = plugin.currentLlmSelection();
    const summaryTimestamp = parseTimestampMs(plugin.shellSummary && plugin.shellSummary.generated_at);
    const summaryAgeMs = Number.isFinite(summaryTimestamp) ? Date.now() - summaryTimestamp : NaN;
    const items = [];

    items.push({
      key: "runtime",
      status: plugin.repoState.valid ? "healthy" : "failed",
      title: "Runtime contract",
      detail: plugin.repoState.valid
        ? plugin.t("launcher {launcher} · root {root}", { launcher: plugin.settings.launcherPath || "", root: plugin.repoState.root || "" })
        : plugin.t("Missing runtime paths: {missing}", { missing: plugin.repoState.missingPaths.join(", ") }),
    });

    if (!plugin.shellSummary) {
      items.push({
        key: "summary",
        status: "failed",
        title: "Shell summary",
        detail: plugin.t("数据还没生成。先点刷新，或等首次任务跑完。"),
      });
    } else {
      items.push({
        key: "summary",
        status: Number.isFinite(summaryAgeMs) && summaryAgeMs > 15 * 60 * 1000 ? "warning" : "healthy",
        title: "Shell summary",
        detail: Number.isFinite(summaryAgeMs) && summaryAgeMs > 15 * 60 * 1000
          ? plugin.t("Summary is stale; refresh before trusting the home surface.")
          : plugin.t("Generated {time}", { time: String(plugin.shellSummary.generated_at || "") }),
      });
    }

    items.push({
      key: "route",
      status: requestedBackend && effectiveBackend && (!availableBackends.length || availableBackends.includes(effectiveBackend)) ? "healthy" : "failed",
      title: "LLM route",
      detail: plugin.t("requested {requested} · effective {effective} · available {available}", {
        requested: requestedBackend || plugin.t("unconfigured"),
        effective: effectiveBackend || plugin.t("unconfigured"),
        available: availableBackends.length ? availableBackends.join(", ") : plugin.t("none"),
      }),
    });

    if (!requestedBackend) {
      items.push({
        key: "backend-discovery",
        status: "warning",
        title: "Backend discovery",
        detail: plugin.t("No explicit LLM backend is selected. Choose one in Product Shell settings or set AIWIKI_LLM_BACKEND."),
      });
    } else {
      const backendVisible = availableBackends.includes(requestedBackend);
      items.push({
        key: "backend-discovery",
        status: backendVisible ? "healthy" : "warning",
        title: "Backend discovery",
        detail: backendVisible
          ? plugin.t("Product Shell runtime can see the selected backend {backend}.", { backend: requestedBackend })
          : plugin.t("Product Shell runtime cannot see the selected backend {backend}.", { backend: requestedBackend }),
      });
    }

    if (!latestLlmRun) {
      items.push({
        key: "latest-ask",
        status: "unknown",
        title: "Latest ask execution",
        detail: plugin.t("No summary latest LLM run data available."),
      });
    } else {
      const localDegradedArtifact = latestLlmRunLocalDegradedArtifact(latestLlmRun);
      const latestStatus = localDegradedArtifact
        ? "warning"
        : latestLlmRun.status === "success"
          ? "healthy"
          : "failed";
      const latestDetail = latestStatus === "healthy"
        ? plugin.t("Latest run-ask succeeded.")
        : latestStatus === "warning"
          ? plugin.t("Latest run-ask produced an LLM failure notice.")
          : plugin.t("Latest run-ask failed before producing an LLM result.");
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
        detail: plugin.t("Latest Product Shell ask used {latest}; current route is {current}.", {
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
        detail: plugin.t("Latest Product Shell ask matches current route."),
      });
    } else {
      // Missing summary.latest_llm_run or its backend — cannot assert health.
      // Must not claim "healthy" just because we have no data (oracle round 6).
      items.push({
        key: "route-drift",
        status: "unknown",
        title: "Route drift",
        detail: plugin.t("No summary latest LLM run data available."),
      });
    }

    if (health.status === "degraded" || health.status === "failed") {
      items.push({
        key: "health",
        status: "warning",
        title: "LLM health",
        detail: health.reason || plugin.t("Latest run-ask produced an LLM failure notice."),
      });
    }

    return items;
  }


function updateLlmHealth(plugin, nextState) {
    const normalized = plugin.normalizeLlmHealthState(nextState);
    if (normalized) {
      if (!plugin.pluginState || typeof plugin.pluginState !== "object") {
        plugin.pluginState = { recentRuns: [], llmHealth: null };
      }
      if (!Array.isArray(plugin.pluginState.recentRuns)) {
        plugin.pluginState.recentRuns = [];
      }
      plugin.pluginState.llmHealth = normalized;
    }
    plugin.updateStatusBar();
    plugin.refreshOpenViews();
    void plugin.savePluginState();
  }


function recordLlmHealthFromRun(plugin, record, overrides = {}) {
    if (!record || typeof record !== "object") {
      return;
    }
    const fallbackCommand = Object.prototype.hasOwnProperty.call(overrides, "fallbackCommand")
      ? overrides.fallbackCommand
      : record.fallbackCommand || record.fallbackFrom || "";
    plugin.updateLlmHealth({
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
      fallbackCommand,
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


module.exports = { normalizeLlmHealthState, currentLlmHealth, latestLlmRun, currentShellSyncState, selfCheckItems, updateLlmHealth, recordLlmHealthFromRun };
