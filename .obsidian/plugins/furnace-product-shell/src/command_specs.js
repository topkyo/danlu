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

function buildAskCommandSpec({ question, format, mode }) {
  const finalFormat = "report";
  const command = mode === "run-ask" ? "run-ask" : mode;
  const args = [command, question, "--format", finalFormat];
  if (mode === "run-ask") {
    args.push("--lean");
  }
  return {
    args,
    labelKey: "Ask",
    labelSubject: question,
    options: {
      refreshAfter: true,
    },
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
