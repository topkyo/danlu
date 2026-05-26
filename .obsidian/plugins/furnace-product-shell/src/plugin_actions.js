async function runProductShellUniversalInputCommand(plugin, { payload, title }) {
  const normalizedPayload = String(payload || "").trim();
  if (!normalizedPayload) {
    new Notice(plugin.t("Universal input cannot be empty."));
    return;
  }
  const spec = buildUniversalInputCommandSpec({ payload: normalizedPayload, title });
  return await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellAskCommand(plugin, { question, format, mode, protocol }) {
  const spec = buildAskCommandSpec({ question, format, mode, protocol });
  return await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellDroppedPayloadsWithAutoAsk(plugin, { payloads, question, protocol }) {
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
    const payload = await plugin.runUniversalInputCommand({ payload: payloadItem.path, title: payloadItem.title });
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
    const askPayload = await plugin.runAskCommand({
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

function completeProductShellPendingMaterialDrop(plugin, id, materialPaths) {
  const paths = normalizeMaterialPaths(materialPaths);
  const rawPath = paths.find((item) => item.startsWith("raw/inbox/")) || paths[0] || "";
  if (id && rawPath) {
    plugin.markPendingSubmissionDone(id, "raw", rawPath);
    return true;
  }
  return false;
}

async function runProductShellDroppedFilesWithAutoAsk(plugin, { files, question, protocol }) {
  const normalizedFiles = Array.isArray(files)
    ? files
      .map((file) => ({
        path: String(file && (file.path || file.source) || "").trim(),
        name: String(file && file.name || "").trim(),
      }))
      .filter((file) => file.path)
    : [];
  return await plugin.runDroppedPayloadsWithAutoAsk({
    payloads: normalizedFiles.map((file) => ({ path: file.path, title: file.name })),
    question,
    protocol,
  });
}

async function runProductShellReportSubgraphCommand(plugin, { reportPath }) {
  const spec = buildReportSubgraphCommandSpec(reportPath);
  if (!spec.normalized) {
    new Notice(plugin.t("Report path cannot be empty."));
    return;
  }
  const payload = await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  const outputPath = payload && typeof payload.output_path === "string" ? payload.output_path.trim() : "";
  if (outputPath) {
    await plugin.openWorkspacePath(outputPath);
  }
  return payload;
}

function collectProductShellReportCandidates(plugin) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
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

function openProductShellReportSubgraphPicker(plugin) {
  const candidates = plugin.collectReportCandidates();
  plugin.openStructuredCommandModal(buildReportSubgraphModalSpec(plugin, candidates));
}

async function runProductShellDropUrlCommand(plugin, { url, title }) {
  const spec = buildDropUrlCommandSpec({ url, title });
  await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellDropFileCommand(plugin, { mode, source, title, maxFiles }) {
  const spec = buildDropFileCommandSpec({ mode, source, title, maxFiles });
  await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellDropImageCommand(plugin, { source, title, noVision }) {
  const spec = buildDropImageCommandSpec({ source, title, noVision });
  await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellDropNoteCommand(plugin, { text, title, kind }) {
  const spec = buildDropNoteCommandSpec({ text, title, kind });
  await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

async function runProductShellCliAction(plugin, label, command, args = []) {
  await plugin.runPluginCommand(label, [command, ...args], { refreshAfter: true });
}

async function runProductShellLauncherCommand(plugin, fullCommandStr, label = "Suggested Action") {
  let trimmed = String(fullCommandStr || "").trim();
  const prefixPattern = /^(?:PYTHONPATH=\S+\s+)?(?:python3?\s+-m\s+aiwiki\.cli\s+)?(?:--root\s+\S+\s+)?/;
  trimmed = trimmed.replace(prefixPattern, "").trim();
  if (!trimmed) {
    new Notice(plugin.t("Cannot parse command: {command}", { command: truncateText(fullCommandStr, 80) }));
    return;
  }
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
  await plugin.runPluginCommand(label, args, { refreshAfter: true });
}
