// Runtime helpers for mutating plugin-owned pending submissions.

function ensurePendingSubmissionRuntimeList(plugin) {
  if (!plugin || typeof plugin !== "object") return [];
  if (!Array.isArray(plugin.pendingSubmissions)) plugin.pendingSubmissions = [];
  return plugin.pendingSubmissions;
}

function findPendingSubmissionRuntimeEntry(plugin, id) {
  const pendingSubmissions = plugin && Array.isArray(plugin.pendingSubmissions)
    ? plugin.pendingSubmissions
    : [];
  return pendingSubmissions.find((entry) => entry && entry.id === id) || null;
}

function removePendingSubmissionRuntimeEntry(plugin, id) {
  if (!plugin || !Array.isArray(plugin.pendingSubmissions) || !plugin.pendingSubmissions.length) {
    return false;
  }
  const before = plugin.pendingSubmissions.length;
  plugin.pendingSubmissions = plugin.pendingSubmissions.filter((entry) => entry && entry.id !== id);
  return plugin.pendingSubmissions.length !== before;
}

function commitPendingSubmissionRuntimeChange(plugin, opts = {}) {
  if (!plugin || typeof plugin !== "object") return;
  if (opts.save !== false && typeof plugin.savePluginState === "function") {
    void plugin.savePluginState();
  }
  if (opts.refresh !== false && typeof plugin.refreshOpenViews === "function") {
    plugin.refreshOpenViews();
  }
  if (opts.poller !== false && typeof plugin.updateLongRunningPoller === "function") {
    plugin.updateLongRunningPoller();
  }
}

function pushPendingSubmissionRuntime(plugin, displayText, opts = {}) {
  const text = String(displayText || "").trim();
  if (!text) return null;
  const pendingSubmissions = ensurePendingSubmissionRuntimeList(plugin);
  const fingerprint = text.slice(0, 80);
  const duplicate = pendingSubmissions.find((entry) => entry && entry.status === "running" && entry.payloadFingerprint === fingerprint);
  if (duplicate) return duplicate.id;
  const id = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const entry = createPendingSubmissionEntry({
    id,
    displayText: text,
    opts,
    startedAt: new Date().toISOString(),
  });
  if (!entry) return null;
  pendingSubmissions.unshift(entry);
  if (pendingSubmissions.length > 8) pendingSubmissions.length = 8;
  commitPendingSubmissionRuntimeChange(plugin);
  return id;
}

function resetPendingSubmissionRuntimeForRetry(plugin, id) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  resetPendingSubmissionEntryForRetry(entry, new Date().toISOString());
  commitPendingSubmissionRuntimeChange(plugin);
}

function markPendingSubmissionRuntimeReceived(plugin, id) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  if (!markPendingSubmissionEntryReceived(entry, new Date().toISOString())) return;
  commitPendingSubmissionRuntimeChange(plugin);
}

function markPendingSubmissionRuntimeDone(plugin, id, reconcileTarget, reconcilePath) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  if (!markPendingSubmissionEntryDone(entry, reconcileTarget, reconcilePath, new Date().toISOString())) return;
  commitPendingSubmissionRuntimeChange(plugin);
}

function markPendingSubmissionRuntimeFailed(plugin, id, error) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  markPendingSubmissionEntryFailed(
    entry,
    truncateText(String((error && error.message) || error || "失败"), 180),
    new Date().toISOString()
  );
  commitPendingSubmissionRuntimeChange(plugin);
}

function updatePendingSubmissionRuntimeRetryArgs(plugin, id, retryArgs) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  entry.retryArgs = retryArgs && typeof retryArgs === "object" ? retryArgs : null;
  if (retryArgs && typeof retryArgs === "object") {
    updatePendingSubmissionRuntimeRunNotes(plugin, id, retryArgs.runNotesPath, retryArgs.runId, { save: false, refresh: false });
    if (retryArgs.jobId) entry.jobId = String(retryArgs.jobId || "");
  }
  commitPendingSubmissionRuntimeChange(plugin);
}

function updatePendingSubmissionRuntimeRunNotes(plugin, id, runNotesPath, runId, opts = {}) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry) return;
  updatePendingSubmissionEntryRunNotes(entry, runNotesPath, runId);
  commitPendingSubmissionRuntimeChange(plugin, { save: opts.save, refresh: opts.refresh, poller: false });
}

function updatePendingSubmissionRuntimeArtifactMeta(plugin, id, meta, opts = {}) {
  const entry = findPendingSubmissionRuntimeEntry(plugin, id);
  if (!entry || !meta || typeof meta !== "object") return;
  updatePendingSubmissionEntryArtifactMeta(entry, meta);
  commitPendingSubmissionRuntimeChange(plugin, { save: opts.save, refresh: opts.refresh, poller: false });
}

function updateProductShellLongRunningPoller(plugin) {
  if (pendingHasActiveLongRunning(plugin && plugin.pendingSubmissions)) {
    plugin.startLongRunningPoller();
  } else {
    plugin.stopLongRunningPoller();
  }
}

function startProductShellLongRunningPoller(plugin) {
  if (!plugin || plugin.longRunningPollTimer) return;
  plugin.longRunningPollTimer = window.setInterval(() => {
    if (!pendingHasActiveLongRunning(plugin.pendingSubmissions)) {
      plugin.stopLongRunningPoller();
      return;
    }
    if (plugin.longRunningPollRefreshInFlight) {
      return;
    }
    plugin.longRunningPollRefreshInFlight = true;
    Promise.resolve(plugin.refreshShellSummarySilently())
      .catch(() => {})
      .finally(() => {
        plugin.longRunningPollRefreshInFlight = false;
      });
  }, 15000);
}

function stopProductShellLongRunningPoller(plugin) {
  if (!plugin || !plugin.longRunningPollTimer) return;
  window.clearInterval(plugin.longRunningPollTimer);
  plugin.longRunningPollTimer = null;
  plugin.longRunningPollRefreshInFlight = false;
}

function productShellLastSummaryRefreshLabel(plugin) {
  const ts = plugin && plugin.shellSummary && plugin.shellSummary.generated_at ? String(plugin.shellSummary.generated_at) : "";
  if (!ts) return plugin.t("未刷新");
  const ms = Date.parse(ts);
  if (!Number.isFinite(ms)) return plugin.t("未刷新");
  const diff = Math.max(0, Date.now() - ms);
  if (diff < 60 * 1000) return plugin.t("刚刚");
  const minutes = Math.floor(diff / (60 * 1000));
  if (minutes < 60) return plugin.t("{n} 分钟前", { n: minutes });
  const hours = Math.floor(diff / (60 * 60 * 1000));
  if (hours < 24) return plugin.t("{n} 小时前", { n: hours });
  const days = Math.floor(diff / (24 * 60 * 60 * 1000));
  return plugin.t("{n} 天前", { n: days });
}

function reconcilePendingSubmissionsRuntime(plugin, summary) {
  if (!plugin || !Array.isArray(plugin.pendingSubmissions) || !plugin.pendingSubmissions.length) return;
  const { remaining, hits } = reconcilePendingSubmissionList(plugin.pendingSubmissions, summary);
  if (remaining.length !== plugin.pendingSubmissions.length) {
    plugin.pendingSubmissions = remaining;
    plugin.refreshOpenViews();
  }
  for (const hit of hits) {
    if (hit.runNotesPath || hit.runId) {
      plugin.updatePendingSubmissionRunNotes(hit.id, hit.runNotesPath, hit.runId, { save: false, refresh: false });
    }
    plugin.updatePendingSubmissionArtifactMeta(hit.id, hit.meta || {}, { save: false, refresh: false });
    plugin.markPendingSubmissionDone(hit.id, hit.target, hit.path);
  }
  updateProductShellLongRunningPoller(plugin);
}
