// Pure helpers extracted from plugin.js (no class state).

// extracted from plugin.js lines 382-391
function trimDiagnosticText(value, limit = 16000) {
  const text = String(value || "");
  if (!text) {
    return "";
  }
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit)}\n...[truncated]`;
}

// extracted from plugin.js lines 426-432
function isLlmRelevantRecord(record) {
  if (!record || typeof record !== "object") {
    return false;
  }
  const command = String(record.command || "").trim();
  return command === "run-ask" || command === "run-ask-frontdoor" || String(record.fallbackFrom || "").trim() === "run-ask";
}

// extracted from plugin.js lines 529-532
function parseTimestampMs(value) {
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp : NaN;
}

// extracted from plugin.js lines 711-721
function launcherIsExecutable(launcherPath) {
  if (!launcherPath || !fs.existsSync(launcherPath)) {
    return false;
  }
  try {
    fs.accessSync(launcherPath, fs.constants.X_OK);
    return true;
  } catch (error) {
    return false;
  }
}

// extracted from plugin.js lines 822-829
function appendOptionalArg(args, flag, value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return args;
  }
  args.push(flag, normalized);
  return args;
}

// extracted from plugin.js lines 831-840
function parseLineList(value) {
  return Array.from(
    new Set(
      String(value || "")
        .split(/\r?\n/)
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    )
  );
}

// extracted from plugin.js lines 842-851
function normalizeRelativePathList(value) {
  const items = Array.isArray(value) ? value : [value];
  return Array.from(
    new Set(
      items
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    )
  );
}

// extracted from plugin.js lines 853-882
function normalizeRewriteProposalObject(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const slug = String(value.slug || "").trim();
  if (!slug) {
    return null;
  }
  return {
    slug,
    title: String(value.title || slug).trim(),
    status: String(value.status || value.current_status || "").trim(),
    currentStatus: String(value.currentStatus || value.current_status || value.status || "").trim(),
    proposalPath: String(value.proposalPath || value.proposal_path || "").trim(),
    targetPath: String(value.targetPath || value.target_path || "").trim(),
    canApply: Boolean(value.canApply || value.can_apply),
    canReview: Boolean(value.canReview || value.can_review),
    canRevert: Boolean(value.canRevert || value.can_revert),
    canRefreshReview: Boolean(value.canRefreshReview || value.can_refresh_review),
    allowedTransitions: Array.isArray(value.allowedTransitions || value.allowed_transitions)
      ? (value.allowedTransitions || value.allowed_transitions).map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    preferredTransitions: Array.isArray(value.preferredTransitions || value.preferred_transitions)
      ? (value.preferredTransitions || value.preferred_transitions).map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    defaultTransition: String(value.defaultTransition || value.default_transition || "").trim(),
    reason: String(value.reason || "").trim(),
    command: String(value.command || "").trim(),
  };
}

// extracted from plugin.js lines 901-933
function normalizeRewriteRecoveryAction(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const slug = String(value.slug || "").trim();
  const command = String(value.command || "").trim();
  if (!slug || !command) {
    return null;
  }
  return {
    slug,
    kind: String(value.kind || "review-rewrite").trim(),
    title: String(value.title || slug).trim(),
    command,
    path: String(value.path || value.proposal_path || value.target_path || "").trim(),
    reason: String(value.reason || "").trim(),
    transition: String(value.transition || value.default_transition || "").trim(),
    status: String(value.status || value.current_status || "").trim(),
    currentStatus: String(value.currentStatus || value.current_status || value.status || "").trim(),
    proposalPath: String(value.proposalPath || value.proposal_path || "").trim(),
    targetPath: String(value.targetPath || value.target_path || "").trim(),
    canApply: Boolean(value.canApply || value.can_apply),
    canReview: Boolean(value.canReview || value.can_review),
    canRevert: Boolean(value.canRevert || value.can_revert),
    allowedTransitions: Array.isArray(value.allowedTransitions || value.allowed_transitions)
      ? (value.allowedTransitions || value.allowed_transitions).map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    preferredTransitions: Array.isArray(value.preferredTransitions || value.preferred_transitions)
      ? (value.preferredTransitions || value.preferred_transitions).map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    defaultTransition: String(value.defaultTransition || value.default_transition || "").trim(),
  };
}

// extracted from plugin.js lines 1093-1106
function uniqueContextOptions(options, keyName = "value") {
  const seen = new Set();
  return (Array.isArray(options) ? options : []).filter((option) => {
    if (!option || typeof option !== "object") {
      return false;
    }
    const key = String(option[keyName] || option.value || option.pagePath || option.actionId || option.entryId || "").trim();
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

// extracted from plugin.js lines 1108-1113
function inferActionIdFromReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") {
    return "";
  }
  return String(receipt.action_id || "").trim();
}

// extracted from plugin.js lines 1657-1659
function runLogRelativePath(record) {
  return `output/control/plugin-runs/${String(record && record.id ? record.id : "").trim()}.md`;
}

// extracted from plugin.js lines 1872-1884
function extractPrimaryPath(payload) {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const candidateKeys = ["path", "output_path", "receipt_path", "state_path", "index_path", "report_path", "note_path", "stored_path", "asset_path"];
  for (const key of candidateKeys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

// extracted from plugin.js lines 2132-2146
function llmBackendUnavailable(error) {
  const text = String(error && error.message ? error.message : error || "").toLowerCase();
  return [
    "usage limit",
    "no quota",
    "upgrade to pro",
    "purchase more credits",
    "organization does not have access",
    "login again",
    "timed out",
    "timeout",
    "authentication",
    "auth",
  ].some((pattern) => text.includes(pattern));
}

// extracted from plugin.js lines 1631-1644
function appendRunEvent(record, stage, summary = "", status = "") {
  if (!record || typeof record !== "object") {
    return;
  }
  if (!Array.isArray(record.timeline)) {
    record.timeline = [];
  }
  record.timeline.push({
    stage: String(stage || "").trim(),
    at: new Date().toISOString(),
    summary: String(summary || "").trim(),
    status: String(status || "").trim(),
  });
}
