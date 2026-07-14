// Pure command specs for launcher-backed Product Shell actions.

function commandLabel(t, key, subject) {
  const prefix = typeof t === "function" ? t(key) : key;
  return `${prefix}: ${truncateText(subject, 48)}`;
}

function buildUniversalInputCommandSpec({ payload, title }) {
  const normalizedPayload = String(payload || "").trim();
  const normalizedTitle = String(title || "").trim();
  const args = ["drop", normalizedPayload];
  if (normalizedTitle) {
    args.push("--title", normalizedTitle);
  }
  return {
    args,
    labelKey: "Universal Input",
    labelSubject: normalizedTitle || normalizedPayload,
    options: { refreshAfter: true },
  };
}

function buildAskCommandSpec({ question, format, mode, protocol }) {
  const finalFormat = "report";
  const longRunning = mode === "run-ask" && finalFormat === "report";
  const command = longRunning ? "run-ask-submit" : mode;
  const args = [command, question, "--format", finalFormat];
  if (protocol) {
    args.push("--protocol", protocol);
  }
  if (mode === "run-ask") {
    const directQuestion = String(question || "").trim();
    const canUseDirect = false
      && !directQuestion.includes("材料路径供系统路由使用：")
      && !directQuestion.includes("本次投喂材料路径：");
    if (canUseDirect) {
      args.push("--direct");
    }
    args.push("--lean");
  }
  return {
    args,
    labelKey: longRunning ? "Long Report" : "Ask",
    labelSubject: question,
    options: {
      refreshAfter: true,
      longRunning,
      backgroundSubmit: longRunning,
    },
  };
}

function buildReportSubgraphCommandSpec(reportPath) {
  const normalized = String(reportPath || "").trim();
  return {
    normalized,
    args: ["report-subgraph", "--report", normalized],
    labelKey: "View report graph",
    labelSubject: normalized,
    options: { refreshAfter: true },
  };
}

function buildDropUrlCommandSpec({ url, title }) {
  const args = ["drop", "url", url];
  if (title) {
    args.push("--title", title);
  }
  return {
    args,
    labelKey: "Drop URL",
    labelSubject: title || url,
    options: { refreshAfter: true },
  };
}

function buildDropFileCommandSpec({ mode, source, title, maxFiles }) {
  const pathApi = nodePath();
  const rawMode = String(mode || "pdf").trim();
  const normalizedMode = rawMode === "repo" || rawMode === "markdown" ? rawMode : "pdf";
  const args = ["drop", normalizedMode === "repo" ? "repo" : normalizedMode === "markdown" ? "markdown" : "pdf", source];
  if (title) {
    args.push("--title", title);
  }
  if (normalizedMode === "repo") {
    args.push("--max-files", String(Number.isFinite(Number(maxFiles)) && Number(maxFiles) > 0 ? Number(maxFiles) : 200));
  }
  return {
    args,
    labelKey: "Drop File",
    labelSubject: title || pathApi.basename(source) || source,
    options: { refreshAfter: true },
  };
}

function buildDropImageCommandSpec({ source, title, noVision }) {
  const pathApi = nodePath();
  const args = ["drop", "image", source];
  if (title) {
    args.push("--title", title);
  }
  if (noVision) {
    args.push("--no-vision");
  }
  return {
    args,
    labelKey: "Drop Image",
    labelSubject: title || pathApi.basename(source) || source,
    options: { refreshAfter: true },
  };
}

function buildDropNoteCommandSpec({ text, title, kind }) {
  const args = ["drop", "markdown", "--text", text];
  if (title) {
    args.push("--title", title);
  }
  args.push("--kind", kind === "markdown" ? "note" : kind || "note");
  return {
    args,
    labelKey: "Capture Material",
    labelSubject: title || text,
    options: { refreshAfter: true },
  };
}
