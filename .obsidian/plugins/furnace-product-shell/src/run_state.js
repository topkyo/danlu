// Pure run-record and run-log helpers for Product Shell command execution.

function createProductShellRunRecord({ label, args, llm, protocol }) {
  const argv = Array.isArray(args) ? args.slice() : [];
  const runId = `run-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const record = {
    id: runId,
    label,
    args: argv.join(" "),
    argv,
    command: argv.length ? String(argv[0] || "") : "",
    status: "running",
    startedAt: new Date().toISOString(),
    finishedAt: "",
    protocol: String(protocol || ""),
    backend: String(llm && llm.backend || ""),
    backendRequested: String(llm && llm.backend || ""),
    backendEffective: String(llm && llm.backend || ""),
    model: String(llm && llm.model || ""),
    modelSelected: String(llm && llm.model || ""),
    modelFinal: String(llm && llm.model || ""),
    codexReasoningEffort: String(llm && llm.codexReasoningEffort || ""),
    promptProfile: "",
    retryPromptProfile: "",
    fallbackStage: "",
    fallbackReason: "",
    contractValidated: false,
    stdoutSummary: "",
    stderrSummary: "",
    stdoutRaw: "",
    stderrRaw: "",
    resultPath: "",
    receiptPath: "",
    logPath: "",
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
  return record;
}

function normalizeProductShellRecentRunRecord(record) {
  if (!record || typeof record !== "object") {
    return null;
  }
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
}

function normalizeProductShellRecentRuns(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((record) => normalizeProductShellRecentRunRecord(record))
    .filter(Boolean);
}

function productShellRunPayloadString(payload, key) {
  return payload && typeof payload[key] === "string" ? payload[key] : "";
}

function productShellRunPayloadBoolean(payload, key, fallback = false) {
  if (payload && Object.prototype.hasOwnProperty.call(payload, key)) {
    return Boolean(payload[key]);
  }
  return Boolean(fallback);
}

function isProductShellAskRun(record) {
  return record && record.command === "run-ask";
}

function productShellRunPayloadDeliveryMode(payload) {
  return productShellRunPayloadString(payload, "delivery_mode");
}

function productShellRunPayloadFallbackUsed(payload, record) {
  return productShellRunPayloadBoolean(payload, "fallback_used", record && record.fallbackUsed);
}

function isProductShellFailureNoticeDeliveryMode(deliveryMode) {
  return deliveryMode === "deterministic-fallback" || deliveryMode === "llm-failed";
}

function isProductShellModelRetryDeliveryMode(deliveryMode) {
  return deliveryMode === "llm-fallback-chain";
}

function isProductShellDegradedRun(record, payload) {
  if (!isProductShellAskRun(record)) {
    return false;
  }
  const deliveryMode = productShellRunPayloadDeliveryMode(payload)
    || String(record && record.deliveryMode || "").trim();
  if (isProductShellFailureNoticeDeliveryMode(deliveryMode)) {
    return true;
  }
  if (isProductShellModelRetryDeliveryMode(deliveryMode) || deliveryMode === "llm-success") {
    return false;
  }
  // Historical: fallbackUsed without an explicit delivery mode is a failure notice.
  return productShellRunPayloadFallbackUsed(payload, record);
}

function buildProductShellRunResultContext(result) {
  const payload = result && result.payload;
  const primaryPath = extractPrimaryPath(payload);
  const receiptPath = payload && typeof payload.receipt_path === "string" ? payload.receipt_path : "";
  return {
    primaryPath,
    receiptPath,
  };
}

function buildProductShellCompletedRunUpdates({
  record,
  result,
  llm,
  primaryPath,
  receiptPath,
}) {
  const payload = result && result.payload && typeof result.payload === "object" ? result.payload : {};
  const deliveryMode = productShellRunPayloadDeliveryMode(payload);
  const fallbackUsed = productShellRunPayloadFallbackUsed(payload, record);
  const degradedRun = isProductShellDegradedRun(record, payload);
  return {
    status: degradedRun ? "degraded" : "success",
    finishedAt: new Date().toISOString(),
    exitCode: 0,
    backend: productShellRunPayloadString(payload, "backend_effective") || (llm && llm.backend) || record.backend,
    backendRequested: productShellRunPayloadString(payload, "backend_requested") || record.backendRequested || (llm && llm.backend) || record.backend,
    backendEffective: productShellRunPayloadString(payload, "backend_effective") || (llm && llm.backend) || record.backend,
    model: productShellRunPayloadString(payload, "model_final") || (llm && llm.model) || record.model,
    modelSelected: productShellRunPayloadString(payload, "model_selected") || record.modelSelected || (llm && llm.model) || record.model,
    modelFinal: productShellRunPayloadString(payload, "model_final") || (llm && llm.model) || record.model,
    codexReasoningEffort: (llm && llm.codexReasoningEffort) || record.codexReasoningEffort,
    promptProfile: productShellRunPayloadString(payload, "prompt_profile") || record.promptProfile,
    retryPromptProfile: productShellRunPayloadString(payload, "retry_prompt_profile") || record.retryPromptProfile,
    fallbackStage: productShellRunPayloadString(payload, "fallback_stage") || record.fallbackStage,
    fallbackReason: productShellRunPayloadString(payload, "fallback_reason") || record.fallbackReason,
    fallbackFrom: productShellRunPayloadString(payload, "fallback_from") || record.fallbackFrom,
    fallbackCommand: productShellRunPayloadString(payload, "fallback_command") || record.fallbackCommand || "",
    fallbackUsed,
    deliveryMode: deliveryMode || record.deliveryMode || "",
    contractValidated: productShellRunPayloadBoolean(payload, "contract_validated", record.contractValidated),
    stdoutSummary: truncateText(result && result.stdout),
    stderrSummary: truncateText(result && result.stderr),
    stdoutRaw: trimDiagnosticText(result && result.stdout),
    stderrRaw: trimDiagnosticText(result && result.stderr),
    resultPath: primaryPath,
    receiptPath,
  };
}

function buildProductShellCompletionRunEvents({
  degradedRun,
  primaryPath,
  receiptPath,
  fallbackSummary = "",
  successSummary = "",
}) {
  const events = [{
    stage: degradedRun ? "LLM timeout" : "Completed",
    summary: degradedRun ? fallbackSummary : successSummary,
    status: degradedRun ? "degraded" : "success",
  }];
  if (primaryPath || receiptPath) {
    events.push({
      stage: "Artifacts",
      summary: [primaryPath, receiptPath].filter(Boolean).join(" · "),
      status: "success",
    });
  }
  return events;
}

function buildProductShellCompletedRunState({
  record,
  result,
  llm,
  runContext,
  fallbackSummary = "",
  successSummary = "",
  degradedNotice = "",
  successNotice = "",
}) {
  const context = runContext || buildProductShellRunResultContext(result);
  const degradedRun = isProductShellDegradedRun(record, result && result.payload);
  const events = buildProductShellCompletionRunEvents({
    degradedRun,
    primaryPath: context.primaryPath,
    receiptPath: context.receiptPath,
    fallbackSummary,
    successSummary,
  });
  const updates = buildProductShellCompletedRunUpdates({
    record,
    result,
    llm,
    primaryPath: context.primaryPath,
    receiptPath: context.receiptPath,
  });
  const projectedRecord = { ...record, ...updates };
  return {
    degradedRun,
    events,
    updates,
    llmHealthOverrides: isProductShellAskRun(record) ? buildProductShellLlmHealthOverrides(projectedRecord) : null,
    noticeMessage: degradedRun ? degradedNotice : successNotice,
  };
}

function buildProductShellFailedRunUpdates(error) {
  return {
    status: "failed",
    finishedAt: new Date().toISOString(),
    exitCode: Number.isFinite(Number(error && error.code)) ? Number(error.code) : "",
    stdoutSummary: truncateText(error && error.stdout || ""),
    stderrSummary: truncateText(error && error.stderr || ""),
    stdoutRaw: trimDiagnosticText(error && error.stdout || ""),
    stderrRaw: trimDiagnosticText(error && error.stderr || ""),
    errorSummary: truncateText(error && error.message || "Command failed"),
  };
}

function buildProductShellFailedRunState({
  record,
  error,
  noticeMessage = "",
}) {
  const message = error && error.message || "Command failed";
  const events = [{
    stage: "Failed",
    summary: truncateText(message, 180),
    status: "failed",
  }];
  return {
    events,
    updates: buildProductShellFailedRunUpdates(error),
    llmHealthOverrides: isProductShellAskRun(record) && llmBackendUnavailable(error)
      ? buildProductShellFailedLlmHealthOverrides(record, error)
      : null,
    logDetails: {
      stdoutRaw: error && error.stdout || "",
      stderrRaw: error && error.stderr || "",
    },
    noticeMessage,
  };
}

function buildProductShellLlmHealthOverrides(record) {
  const deliveryMode = String(record && record.deliveryMode || "").trim();
  const failureNotice = isProductShellFailureNoticeDeliveryMode(deliveryMode)
    || (!deliveryMode && Boolean(record && record.fallbackUsed));
  const modelRetry = isProductShellModelRetryDeliveryMode(deliveryMode);
  return {
    status: failureNotice ? "degraded" : modelRetry ? "warning" : "healthy",
    reason: failureNotice
      ? "Latest run-ask produced an LLM failure notice."
      : modelRetry
        ? "LLM completed via model retry."
        : "Recent run-ask succeeded.",
    source: "run-ask",
    fallbackCommand: failureNotice ? (record.fallbackCommand || "run-ask") : String((record && record.fallbackCommand) || ""),
    backendRequested: record.backendRequested,
    backendEffective: record.backendEffective,
    modelSelected: record.modelSelected,
    modelFinal: record.modelFinal,
    fallbackStage: record.fallbackStage,
    fallbackReason: record.fallbackReason,
    contractValidated: record.contractValidated,
  };
}

function buildProductShellFailedLlmHealthOverrides(record, error) {
  return {
    status: "degraded",
    reason: truncateText(error && (error.message || error.stderr || error.stdout) || "LLM backend unavailable", 240),
    source: "run-ask",
    fallbackCommand: "run-ask",
    backendRequested: record.backendRequested,
    backendEffective: record.backendEffective,
    modelSelected: record.modelSelected,
    modelFinal: record.modelFinal,
    fallbackStage: record.fallbackStage,
    fallbackReason: record.fallbackReason,
    contractValidated: record.contractValidated,
    stderrSummary: truncateText(error && error.stderr || ""),
    stderrRaw: trimDiagnosticText(error && (error.stderr || error.stdout) || ""),
  };
}
