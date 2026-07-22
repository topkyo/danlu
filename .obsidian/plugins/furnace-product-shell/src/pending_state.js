// Pure pending-submission state helpers.

function serializePendingSubmissionList(pendingSubmissions) {
  if (!Array.isArray(pendingSubmissions)) return [];
  return pendingSubmissions.slice(0, 8).map((e) => ({
    id: String(e.id || ""),
    payloadFingerprint: String(e.payloadFingerprint || ""),
    displayText: String(e.displayText || ""),
    title: String(e.title || ""),
    status: String(e.status || "running"),
    startedAt: String(e.startedAt || ""),
    finishedAt: String(e.finishedAt || ""),
    error: String(e.error || ""),
    reconcileTarget: String(e.reconcileTarget || ""),
    reconcilePath: String(e.reconcilePath || ""),
    runId: String(e.runId || ""),
    runNotesPath: String(e.runNotesPath || ""),
    jobId: String(e.jobId || ""),
    deliveryMode: String(e.deliveryMode || ""),
    llmStatus: String(e.llmStatus || ""),
    llmBackend: String(e.llmBackend || ""),
    llmModel: String(e.llmModel || ""),
    backgroundStatus: String(e.backgroundStatus || ""),
    artifactQuality: String(e.artifactQuality || ""),
    retryArgs: e.retryArgs && typeof e.retryArgs === "object" ? e.retryArgs : null,
  }));
}

function hydratePendingSubmissionList(raw, now = Date.now()) {
  if (!Array.isArray(raw) || !raw.length) return [];
  const TTL_MS = 24 * 60 * 60 * 1000;
  const RECEIVED_STALE_MS = 12 * 60 * 60 * 1000;
  const DONE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const out = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const startedAt = String(item.startedAt || "");
    const finishedAt = String(item.finishedAt || "");
    const startMs = Date.parse(startedAt);
    const finishedMs = Date.parse(finishedAt);
    const status = String(item.status || "running");
    // R90: done 卡 7 天后自动 drop
    // P2: 旧数据缺 finishedAt 时回退 startedAt，避免无 TTL 永久保留
    if (status === "done") {
      const ttlBase = Number.isFinite(finishedMs)
        ? finishedMs
        : (Number.isFinite(startMs) ? startMs : null);
      if (ttlBase !== null && now - ttlBase > DONE_TTL_MS) continue;
    }
    let nextStatus = status;
    let error = String(item.error || "");
    if (Number.isFinite(startMs)) {
      const age = now - startMs;
      if ((status === "running") && age > TTL_MS) {
        nextStatus = "failed";
        error = "上次提交可能仍在处理或已完成，点上方刷新查看结果";
      } else if (status === "received" && age > RECEIVED_STALE_MS) {
        item._stale = true;
      }
    }
    out.push({
      id: String(item.id || `pending-${now}-${out.length}`),
      payloadFingerprint: String(item.payloadFingerprint || ""),
      displayText: String(item.displayText || ""),
      title: String(item.title || ""),
      status: nextStatus,
      startedAt,
      finishedAt: String(item.finishedAt || (nextStatus === "failed" ? new Date().toISOString() : "")),
      error,
      reconcileTarget: String(item.reconcileTarget || ""),
      reconcilePath: String(item.reconcilePath || ""),
      runId: String(item.runId || ""),
      runNotesPath: String(item.runNotesPath || ""),
      jobId: String(item.jobId || ""),
      deliveryMode: String(item.deliveryMode || ""),
      llmStatus: String(item.llmStatus || ""),
      llmBackend: String(item.llmBackend || ""),
      llmModel: String(item.llmModel || ""),
      backgroundStatus: String(item.backgroundStatus || ""),
      artifactQuality: String(item.artifactQuality || ""),
      retryArgs: item.retryArgs && typeof item.retryArgs === "object" ? item.retryArgs : null,
      _stale: Boolean(item._stale),
    });
    if (out.length >= 8) break;
  }
  return out;
}

function isPendingSubmissionDegradedEntry(entry) {
  if (!entry || typeof entry !== "object") return false;
  if (entry.status === "degraded") return true;
  const deliveryMode = String(entry.deliveryMode || entry.delivery_mode || "").trim();
  const llmStatus = String(entry.llmStatus || entry.llm_status || "").trim();
  const backgroundStatus = String(entry.backgroundStatus || entry.background_status || "").trim();
  const artifactQuality = String(entry.artifactQuality || entry.artifact_quality || "").trim();
  return deliveryMode === "deterministic-fallback"
    || deliveryMode === "llm-failed"
    || llmStatus === "timeout_or_unavailable"
    || llmStatus === "validation_failed"
    || llmStatus === "failed"
    || llmStatus === "degraded"
    || backgroundStatus === "degraded"
    || artifactQuality === "degraded";
}

function createPendingSubmissionEntry({ displayText, opts = {}, id, startedAt }) {
  const text = String(displayText || "").trim();
  if (!text) {
    return null;
  }
  return {
    id: String(id || ""),
    payloadFingerprint: text.slice(0, 80),
    displayText: text.length > 120 ? text.slice(0, 117) + "…" : text,
    title: String(opts.title || "").trim(),
    status: "running",
    startedAt: String(startedAt || ""),
    finishedAt: "",
    error: "",
    reconcileTarget: "",
    runId: String(opts.runId || "").trim(),
    runNotesPath: String(opts.runNotesPath || "").trim(),
    jobId: String(opts.jobId || "").trim(),
    deliveryMode: String(opts.deliveryMode || "").trim(),
    llmStatus: String(opts.llmStatus || "").trim(),
    llmBackend: String(opts.llmBackend || "").trim(),
    llmModel: String(opts.llmModel || "").trim(),
    backgroundStatus: String(opts.backgroundStatus || "").trim(),
    artifactQuality: String(opts.artifactQuality || "").trim(),
    retryArgs: opts.retryArgs && typeof opts.retryArgs === "object" ? opts.retryArgs : null,
  };
}

function resetPendingSubmissionEntryForRetry(entry, nowIso) {
  if (!entry || typeof entry !== "object") return false;
  entry.status = "running";
  entry.error = "";
  entry.startedAt = String(nowIso || "");
  entry.finishedAt = "";
  entry.reconcileTarget = "";
  entry.reconcilePath = "";
  entry.jobId = "";
  entry.runId = "";
  entry.runNotesPath = "";
  entry.deliveryMode = "";
  entry.llmStatus = "";
  entry.llmBackend = "";
  entry.llmModel = "";
  entry.backgroundStatus = "";
  entry.artifactQuality = "";
  if (entry.retryArgs && typeof entry.retryArgs === "object") {
    entry.retryArgs = Object.assign({}, entry.retryArgs, { jobId: "", runId: "", runNotesPath: "" });
  }
  entry._stale = false;
  return true;
}

function markPendingSubmissionEntryReceived(entry, nowIso) {
  if (!entry || typeof entry !== "object" || entry.status !== "running") return false;
  entry.status = "received";
  entry.finishedAt = String(nowIso || "");
  return true;
}

function markPendingSubmissionEntryDone(entry, reconcileTarget, reconcilePath, nowIso) {
  if (!entry || typeof entry !== "object") return false;
  if (entry.status === "done" || entry.status === "failed" || entry.status === "degraded") return false;
  entry.status = isPendingSubmissionDegradedEntry(entry) ? "degraded" : "done";
  entry.finishedAt = String(nowIso || "");
  if (reconcileTarget) entry.reconcileTarget = String(reconcileTarget);
  if (reconcilePath) entry.reconcilePath = String(reconcilePath);
  return true;
}

function markPendingSubmissionEntryFailed(entry, errorText, nowIso) {
  if (!entry || typeof entry !== "object") return false;
  entry.status = "failed";
  entry.finishedAt = String(nowIso || "");
  entry.error = String(errorText || "失败");
  return true;
}

function updatePendingSubmissionEntryRunNotes(entry, runNotesPath, runId) {
  if (!entry || typeof entry !== "object") return false;
  const notes = String(runNotesPath || "").trim();
  const rid = String(runId || "").trim();
  let changed = false;
  if (notes) {
    entry.runNotesPath = notes;
    changed = true;
  }
  if (rid) {
    entry.runId = rid;
    changed = true;
  }
  return changed;
}

function updatePendingSubmissionEntryArtifactMeta(entry, meta) {
  if (!entry || typeof entry !== "object" || !meta || typeof meta !== "object") return false;
  let changed = false;
  if (meta.runNotesPath || meta.run_notes_path || meta.runId || meta.run_id) {
    changed = updatePendingSubmissionEntryRunNotes(
      entry,
      meta.runNotesPath || meta.run_notes_path,
      meta.runId || meta.run_id
    ) || changed;
  }
  const fields = [
    ["deliveryMode", "delivery_mode"],
    ["llmStatus", "llm_status"],
    ["llmBackend", "llm_backend"],
    ["llmModel", "llm_model"],
    ["backgroundStatus", "background_status"],
    ["artifactQuality", "artifact_quality"],
  ];
  for (const [camelKey, snakeKey] of fields) {
    if (meta[camelKey] || meta[snakeKey]) {
      entry[camelKey] = String(meta[camelKey] || meta[snakeKey] || "");
      changed = true;
    }
  }
  return changed;
}

function pendingHasActiveAsk(pendingSubmissions, excludeId = "") {
  if (!Array.isArray(pendingSubmissions)) return false;
  const skip = String(excludeId || "").trim();
  return pendingSubmissions.some((entry) => {
    if (!entry || (entry.status !== "running" && entry.status !== "received")) return false;
    if (skip && String(entry.id || "") === skip) return false;
    return !isPureMaterialPendingEntry(entry);
  });
}

function isPureMaterialPendingEntry(entry) {
  const args = entry && entry.retryArgs;
  if (!args || typeof args !== "object") return false;
  const kind = String(args.kind || "").trim();
  if (kind === "material") return true;
  if (kind === "files") {
    const question = String(args.question || args.askQuestion || "").trim();
    if (question) return false;
    if (args.autoAsk === true) return false;
    return true;
  }
  return false;
}

function reconcilePendingSubmissionList(pendingSubmissions, summary, now = Date.now()) {
  const pending = Array.isArray(pendingSubmissions) ? pendingSubmissions : [];
  if (!pending.length || !summary || typeof summary !== "object") {
    return { remaining: pending, hits: [] };
  }
  const outputCands = Array.isArray(summary.recent_outputs) ? summary.recent_outputs : [];
  const receiptCands = Array.isArray(summary.recent_receipts) ? summary.recent_receipts : [];
  const rawCands = Array.isArray(summary.recent_raw_inputs) ? summary.recent_raw_inputs : [];
  if (!outputCands.length && !receiptCands.length && !rawCands.length) {
    return { remaining: pending, hits: [] };
  }
  const SKEW_MS = 60 * 1000;
  const RECONCILE_WINDOW_MS = 5 * 60 * 1000;
  const remaining = [];
  const hits = [];
  for (const entry of pending) {
    if (!entry) { continue; }
    // failed/done/degraded 保留（done/degraded 等用户处理）
    if (entry.status === "failed" || entry.status === "done" || entry.status === "degraded") {
      remaining.push(entry);
      continue;
    }
    const startMs = Date.parse(entry.startedAt || "") || now;
    // 超窗（仅对 running 生效；received 长期等待 reconcile，不超窗）
    if (entry.status === "running" && now - startMs > RECONCILE_WINDOW_MS) {
      remaining.push(entry);
      continue;
    }
    const fp = String(entry.payloadFingerprint || "").trim().toLowerCase();
    const title = String(entry.title || "").trim().toLowerCase();
    const fpKey = fp.length >= 60 ? fp.slice(0, 60) : fp;
    const useExact = fp.length > 0 && fp.length < 16;
    const matchAgainst = (cand) => {
      if (!cand || typeof cand !== "object") return false;
      const candTimeStr = cand.created_at || cand.generated_at || cand.applied_at || cand.occurred_at || cand.timestamp || "";
      const candMs = Date.parse(candTimeStr);
      if (!Number.isFinite(candMs)) return false;
      if (candMs + SKEW_MS < startMs) return false;
      const fields = [
        cand.title,
        cand.path,
        cand.summary,
        cand.payload,
        cand.receipt_path,
        cand.output_path,
        cand.stored_path,
        cand.original_path,
        cand.note_path,
        cand.query,
        cand.target,
      ].map((v) => String(v || "").trim().toLowerCase()).filter(Boolean);
      if (!fields.length) return false;
      if (useExact) {
        return fields.some((f) => f === fp || (title && f === title));
      }
      const haystack = fields.join(" \u0001 ");
      if (fpKey && haystack.includes(fpKey)) return true;
      if (title && title.length >= 4 && haystack.includes(title)) return true;
      return false;
    };
    let target = "";
    let targetPath = "";
    let hitRunNotesPath = "";
    let hitRunId = "";
    let hitMeta = null;
    const entryRunId = String(entry.runId || (entry.retryArgs && entry.retryArgs.runId) || "").trim();
    const findRunIdHit = (cands) => entryRunId ? cands.find((cand) => cand && String(cand.run_id || cand.runId || "").trim() === entryRunId) : null;
    const findHit = (cands) => cands.find(matchAgainst);
    const pureMaterial = isPureMaterialPendingEntry(entry);
    if (!pureMaterial) {
      let hitCand = findRunIdHit(outputCands) || findHit(outputCands);
      if (hitCand) {
        target = "outputs";
        targetPath = String(hitCand.path || "");
        hitRunNotesPath = String(hitCand.run_notes_path || "");
        hitRunId = String(hitCand.run_id || "");
        hitMeta = {
          runNotesPath: hitRunNotesPath,
          runId: hitRunId,
          deliveryMode: String(hitCand.delivery_mode || ""),
          llmStatus: String(hitCand.llm_status || ""),
          llmBackend: String(hitCand.llm_backend || ""),
          llmModel: String(hitCand.llm_model || ""),
          backgroundStatus: String(hitCand.background_status || ""),
          artifactQuality: String(hitCand.artifact_quality || ""),
        };
      } else {
        hitCand = findRunIdHit(receiptCands) || findHit(receiptCands);
        if (hitCand) {
          target = "receipts";
          targetPath = String(hitCand.path || hitCand.receipt_path || "");
          hitRunNotesPath = String(hitCand.run_notes_path || "");
          hitRunId = String(hitCand.run_id || "");
          hitMeta = { runId: hitRunId, runNotesPath: hitRunNotesPath };
        }
      }
      if (!target) {
        const rawHit = findHit(rawCands);
        if (rawHit) {
          target = "raw";
          targetPath = String(rawHit.stored_path || rawHit.path || "");
        }
      }
    } else {
      let hitCand = findRunIdHit(receiptCands) || findHit(receiptCands);
      if (hitCand) {
        target = "receipts";
        targetPath = String(hitCand.path || hitCand.receipt_path || "");
        hitRunNotesPath = String(hitCand.run_notes_path || "");
        hitRunId = String(hitCand.run_id || "");
        hitMeta = { runId: hitRunId, runNotesPath: hitRunNotesPath };
      } else {
        hitCand = findHit(rawCands);
        if (hitCand) {
          target = "raw";
          targetPath = String(hitCand.stored_path || hitCand.path || "");
        }
      }
    }
    if (target) {
      hits.push({ id: entry.id, target, path: targetPath, runNotesPath: hitRunNotesPath, runId: hitRunId, meta: hitMeta || {} });
      remaining.push(entry);
    } else {
      remaining.push(entry);
    }
  }
  return { remaining, hits };
}
