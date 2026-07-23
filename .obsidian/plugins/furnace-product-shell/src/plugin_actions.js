async function runProductShellUniversalInputCommand(plugin, { payload, title }) {
  const normalizedPayload = String(payload || "").trim();
  if (!normalizedPayload) {
    new Notice(plugin.t("Universal input cannot be empty."));
    return;
  }
  const spec = buildUniversalInputCommandSpec({ payload: normalizedPayload, title });
  return await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
}

function persistStickyMaterialRefs(plugin) {
  if (!plugin || typeof plugin.savePluginState !== "function") {
    return;
  }
  try {
    const result = plugin.savePluginState();
    if (result && typeof result.then === "function") {
      void result.catch(() => {});
    }
  } catch (_error) {
    // Sticky persistence must not break drop/ask completion in partial test bundles.
  }
}

async function runProductShellAskCommand(plugin, { question, format, mode, excludePendingId, materialPaths }) {
  if (pendingHasActiveAsk(plugin.pendingSubmissions, excludePendingId)) {
    new Notice(plugin.t("已有进行中的提问，请等待完成后再试。"));
    return;
  }
  const explicit = normalizeMaterialPaths(materialPaths);
  const resolved = resolveAskMaterialPaths(explicit, plugin.settings && plugin.settings.stickyMaterialRefs);
  let askQuestion = String(question || "").trim();
  let usedPaths = resolved.paths;
  const fromSticky = Boolean(resolved.fromSticky);
  if (askQuestion && !questionAlreadyHasMaterialRoutingHint(askQuestion) && usedPaths.length) {
    askQuestion = buildAutoAskQuestion(askQuestion, usedPaths);
  }
  if (explicit.length) {
    setStickyMaterialRefs(plugin.settings, explicit, "explicit-@");
    persistStickyMaterialRefs(plugin);
  }
  const spec = buildAskCommandSpec({ question: askQuestion, format, mode });
  const payload = await plugin.runPluginCommand(commandLabel(plugin.t.bind(plugin), spec.labelKey, spec.labelSubject), spec.args, spec.options);
  if (!explicit.length && usedPaths.length && payload && (payload.report_path || payload.output_path || payload.ok !== false)) {
    setStickyMaterialRefs(
      plugin.settings,
      usedPaths,
      fromSticky ? (plugin.settings.stickyMaterialRefs && plugin.settings.stickyMaterialRefs.source) || "drop" : "ask",
    );
    persistStickyMaterialRefs(plugin);
  }
  if (payload && typeof payload === "object") {
    payload.usedMaterialPaths = usedPaths;
  }
  return payload;
}

async function runProductShellDroppedPayloadsWithAutoAsk(plugin, { payloads, question, excludePendingId, extraMaterialPaths }) {
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
  const dropPayloads = [];
  for (const payloadItem of normalizedPayloads) {
    const payload = await plugin.runUniversalInputCommand({ payload: payloadItem.path, title: payloadItem.title });
    dropPayloads.push(payload);
    collectMaterialPathsFromPayload(payload).forEach((item) => materialPaths.push(item));
    if (imageDropLacksReadableAnalysis(payload)) {
      new Notice(plugin.t("Image archived only; content analysis is unavailable for now."));
    }
  }
  const extraPaths = normalizeMaterialPaths(extraMaterialPaths);
  const normalizedMaterialPaths = normalizeMaterialPaths([...materialPaths, ...extraPaths]);
  if (normalizedMaterialPaths.length) {
    setStickyMaterialRefs(plugin.settings, normalizedMaterialPaths, extraPaths.length ? "explicit-@" : "drop");
    persistStickyMaterialRefs(plugin);
  }
  const askQuestion = normalizedQuestion
    ? buildAutoAskQuestion(normalizedQuestion, normalizedMaterialPaths)
    : "";
  let runNotesPath = "";
  let runId = "";
  let askFormat = "";
  let askPayload = null;
  if (normalizedQuestion) {
    askFormat = inferAutoAskFormat(normalizedQuestion, normalizedMaterialPaths);
    if (extraPaths.length) {
      askPayload = await plugin.runAskCommand({
        question: normalizedQuestion,
        format: askFormat,
        mode: "run-ask",
        excludePendingId,
        materialPaths: normalizedMaterialPaths,
      });
    } else {
      askPayload = await plugin.runAskCommand({
        question: askQuestion,
        format: askFormat,
        mode: "run-ask",
        excludePendingId,
      });
    }
    runNotesPath = String(askPayload && askPayload.run_notes_path || "");
    runId = String(askPayload && askPayload.run_id || "");
  }
  return {
    materialPaths: normalizedMaterialPaths,
    askQuestion,
    askFormat,
    runNotesPath,
    runId,
    askPayload,
    dropPayloads,
  };
}

function completeProductShellPendingMaterialDrop(plugin, id, materialPaths) {
  const paths = normalizeMaterialPaths(materialPaths);
  if (paths.length) {
    setStickyMaterialRefs(plugin.settings, paths, "drop");
    persistStickyMaterialRefs(plugin);
  }
  const rawPath = paths.find((item) => item.startsWith("raw/inbox/")) || paths[0] || "";
  if (id && rawPath) {
    plugin.markPendingSubmissionDone(id, "raw", rawPath);
    return true;
  }
  return false;
}

async function runProductShellDroppedFilesWithAutoAsk(plugin, { files, question, excludePendingId, extraMaterialPaths }) {
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
    excludePendingId,
    extraMaterialPaths,
  });
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
