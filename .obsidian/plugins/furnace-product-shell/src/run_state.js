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
  return record;
}

function normalizeProductShellRecentRunRecord(record) {
  if (!record || typeof record !== "object") {
    return null;
  }
  const rewriteProposalObjects = normalizeRewriteProposalObjects(record.rewriteProposalObjects || record.updatedRewriteProposals || []);
  const rewriteRecoveryActions = normalizeRewriteRecoveryActions(record.rewriteRecoveryActions || []);
  const rewriteProposalPaths = normalizeRelativePathList(
    record.rewriteProposalPaths || rewriteProposalPathsFromObjects(rewriteProposalObjects)
  );
  const rewriteProposalSlugs = normalizeRelativePathList(
    record.rewriteProposalSlugs || rewriteProposalSlugsFromObjects(rewriteProposalObjects)
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
  return record && (record.command === "run-ask" || record.command === "run-ask-resume");
}

function productShellRunPayloadDeliveryMode(payload) {
  return productShellRunPayloadString(payload, "delivery_mode");
}

function productShellRunPayloadFallbackUsed(payload, record) {
  return productShellRunPayloadBoolean(payload, "fallback_used", record && record.fallbackUsed);
}

function isProductShellDegradedRun(record, payload) {
  if (!isProductShellAskRun(record)) {
    return false;
  }
  const deliveryMode = productShellRunPayloadDeliveryMode(payload);
  return productShellRunPayloadFallbackUsed(payload, record) || deliveryMode === "deterministic-fallback";
}

function buildProductShellBackgroundRunUpdates({ result, primaryPath }) {
  const payload = result && result.payload && typeof result.payload === "object" ? result.payload : {};
  return {
    status: "received",
    exitCode: 0,
    jobId: String(payload.job_id || ""),
    resultPath: primaryPath,
    runId: String(payload.run_id || ""),
    runNotesPath: String(payload.run_notes_path || ""),
    stdoutSummary: truncateText(result && result.stdout),
    stderrSummary: truncateText(result && result.stderr),
    stdoutRaw: trimDiagnosticText(result && result.stdout),
    stderrRaw: trimDiagnosticText(result && result.stderr),
  };
}

function buildProductShellCompletedRunUpdates({
  record,
  result,
  llm,
  primaryPath,
  receiptPath,
  rewriteProposalObjects,
  rewriteRecoveryActions,
  rewriteProposalPaths,
  rewriteProposalSlugs,
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
    rewriteProposalObjects,
    rewriteRecoveryActions,
    rewriteProposalPaths,
    rewriteProposalSlugs,
    stdoutSummary: truncateText(result && result.stdout),
    stderrSummary: truncateText(result && result.stderr),
    stdoutRaw: trimDiagnosticText(result && result.stdout),
    stderrRaw: trimDiagnosticText(result && result.stderr),
    resultPath: primaryPath,
    receiptPath,
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

function renderProductShellRunLog({ record, details = {}, t, repoRoot = "" }) {
  if (!record || typeof record !== "object") {
    return null;
  }
  const translate = typeof t === "function" ? t : (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? ""));
  const logPath = String(record.logPath || runLogRelativePath(record)).trim();
  if (!logPath) {
    return null;
  }
  const stdoutText = String(details.stdoutRaw || record.stdoutRaw || "").trim();
  const stderrText = String(details.stderrRaw || record.stderrRaw || "").trim();
  const rewriteProposalObjects = normalizeRewriteProposalObjects(record.rewriteProposalObjects || []);
  const rewriteProposalCount = rewriteProposalObjects.length || (Array.isArray(record.rewriteProposalPaths) ? record.rewriteProposalPaths.length : 0);
  const lines = [
    "# Product Shell Run Log",
    "",
    translate("Generated by Product Shell run logging."),
    "",
    `- ${translate("Status")}: ${translate(record.status || "unknown")}`,
    `- ${translate("Protocol")}: ${record.protocol ? translate(record.protocol) : translate("unknown")}`,
    `- ${translate("LLM Backend")}: ${record.backend || translate("unconfigured")}`,
    `- backend requested: ${record.backendRequested || "-"}`,
    `- backend effective: ${record.backendEffective || record.backend || "-"}`,
    `- ${translate("LLM Model")}: ${record.model || translate("default")}`,
    `- model selected: ${record.modelSelected || "-"}`,
    `- model final: ${record.modelFinal || record.model || "-"}`,
    `- ${translate("Codex effort")}: ${record.codexReasoningEffort || "-"}`,
    `- ${translate("Prompt profile")}: ${record.promptProfile || "-"}`,
    `- ${translate("Retry prompt")}: ${record.retryPromptProfile || "-"}`,
    `- fallback stage: ${record.fallbackStage || "-"}`,
    `- fallback reason: ${record.fallbackReason || "-"}`,
    `- contract validated: ${record.contractValidated ? "yes" : "no"}`,
    `- ${translate("Working directory")}: ${repoRoot || "."}`,
    `- ${translate("Arguments")}: ${record.args || record.command || ""}`,
    `- ${translate("Fallback from")}: ${record.fallbackFrom || "-"}`,
    `- ${translate("Result path")}: ${record.resultPath || "-"}`,
    `- ${translate("Receipt path")}: ${record.receiptPath || "-"}`,
    ...(rewriteProposalCount
      ? [`- ${translate("rewrite proposals: {count}", { count: rewriteProposalCount })}`]
      : []),
    `- ${translate("Log path")}: ${logPath}`,
    `- ${translate("Exit code")}: ${record.exitCode === "" ? "-" : String(record.exitCode)}`,
    `- started: ${record.startedAt || "-"}`,
    `- finished: ${record.finishedAt || "-"}`,
    "",
    "## Timeline",
    "",
  ];
  const timeline = Array.isArray(record.timeline) ? record.timeline : [];
  if (!timeline.length) {
    lines.push(`- ${translate("No stage events recorded.")}`);
  } else {
    timeline.forEach((event) => {
      lines.push(`- ${event.at || "-"} | ${translate(event.stage || "event")} | ${event.summary || "-"}`);
    });
  }
  if (record.resultPath || record.receiptPath || record.errorSummary) {
    lines.push("", "## Summary", "");
    if (record.resultPath) {
      lines.push(`- ${translate("Result path")}: ${record.resultPath}`);
    }
    if (record.receiptPath) {
      lines.push(`- ${translate("Receipt path")}: ${record.receiptPath}`);
    }
    if (record.errorSummary) {
      lines.push(`- error: ${record.errorSummary}`);
    }
    if (rewriteProposalObjects.length) {
      lines.push(`- ${translate("rewrite proposals: {count}", { count: rewriteProposalObjects.length })}`);
      rewriteProposalObjects.forEach((proposal) => {
        lines.push(`  - ${proposal.title || proposal.slug}: ${proposal.proposalPath || proposal.targetPath || proposal.slug}`);
      });
    } else if (Array.isArray(record.rewriteProposalPaths) && record.rewriteProposalPaths.length) {
      lines.push(`- ${translate("rewrite proposals: {count}", { count: record.rewriteProposalPaths.length })}`);
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
  return { logPath, content: `${lines.join("\n")}\n` };
}
