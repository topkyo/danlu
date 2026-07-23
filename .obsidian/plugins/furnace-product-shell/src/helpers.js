// Standalone helper functions used across the plugin.

function truncateText(value, limit = 240) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}…`;
}

function sanitizeDropFileName(value) {
  const raw = String(value || "attachment").trim() || "attachment";
  const sanitized = raw.replace(/[\\/:*?"<>|\0\r\n\t]/g, "_").replace(/^\.+$/, "attachment");
  return sanitized.slice(0, 160) || "attachment";
}

function nodeFs() {
  if (typeof fs !== "undefined") return fs;
  if (typeof require === "function") return require("fs");
  throw new Error("File-system access is unavailable in this Obsidian runtime.");
}

function nodePath() {
  if (typeof path !== "undefined") return path;
  if (typeof require === "function") return require("path");
  throw new Error("Path utilities are unavailable in this Obsidian runtime.");
}

function pluginVaultRoot(plugin) {
  const repoRoot = plugin && plugin.repoState && typeof plugin.repoState.root === "string" ? plugin.repoState.root.trim() : "";
  if (repoRoot) return repoRoot;
  const adapter = plugin && plugin.app && plugin.app.vault && plugin.app.vault.adapter;
  return adapter && typeof adapter.basePath === "string" ? adapter.basePath.trim() : "";
}

function normalizeMaterialPaths(values) {
  const items = Array.isArray(values) ? values : [values];
  const seen = new Set();
  const out = [];
  items.forEach((value) => {
    const text = String(value || "").trim();
    if (!text || seen.has(text)) {
      return;
    }
    seen.add(text);
    out.push(text);
  });
  return out;
}

async function resolvePluginFileSource(plugin, file) {
  const fileName = String(file && file.name || "").trim();
  const rawPath = String(file && file.path || "").trim();
  const pathApi = nodePath();
  if (rawPath && (pathApi.isAbsolute(rawPath) || rawPath.includes("/") || rawPath.includes("\\")) && rawPath !== fileName) {
    return rawPath;
  }
  if (!file || typeof file.arrayBuffer !== "function") {
    if (rawPath) return rawPath;
    throw new Error("Cannot access dropped file contents; please choose a local file again.");
  }
  const root = pluginVaultRoot(plugin);
  if (!root) {
    throw new Error("Cannot save dropped file because the vault root is unavailable.");
  }
  const fsApi = nodeFs();
  const targetDir = pathApi.join(root, ".aiwiki", "tmp", "product-shell-drop");
  fsApi.mkdirSync(targetDir, { recursive: true });
  const safeName = sanitizeDropFileName(fileName || "attachment");
  const parsedName = pathApi.parse(safeName);
  const safeStem = parsedName.name || "attachment";
  const stamp = `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  const targetPath = pathApi.join(targetDir, `${safeStem}-${stamp}${parsedName.ext || ""}`);
  const buffer = await file.arrayBuffer();
  fsApi.writeFileSync(targetPath, new Uint8Array(buffer));
  return targetPath;
}

function collectMaterialPathsFromPayload(payload) {
  const out = [];
  const seenObjects = new Set();
  const directKeys = [
    "note_path",
    "asset_path",
    "path",
    "output_path",
    "report_path",
    "receipt_path",
    "state_path",
    "index_path",
    "stored_path",
  ];
  const listKeys = [
    "asset_paths",
    "note_paths",
    "paths",
    "output_paths",
    "report_paths",
    "receipt_paths",
    "state_paths",
    "index_paths",
    "stored_paths",
    "material_paths",
  ];
  const pushValue = (value) => {
    normalizeMaterialPaths(value).forEach((item) => out.push(item));
  };
  const visit = (value, depth = 0) => {
    if (!value || depth > 3) {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, depth + 1));
      return;
    }
    if (typeof value !== "object") {
      return;
    }
    if (seenObjects.has(value)) {
      return;
    }
    seenObjects.add(value);
    directKeys.forEach((key) => pushValue(value[key]));
    listKeys.forEach((key) => {
      const items = value[key];
      if (Array.isArray(items)) {
        items.forEach((item) => pushValue(item));
      }
    });
    ["material", "materials", "result", "results", "artifacts", "items"].forEach((key) => {
      if (value[key]) {
        visit(value[key], depth + 1);
      }
    });
  };
  visit(payload);
  return normalizeMaterialPaths(out);
}

function buildAutoAskQuestion(question, materialPaths) {
  const normalizedQuestion = String(question || "").trim();
  if (!normalizedQuestion) {
    return "";
  }
  const paths = normalizeMaterialPaths(materialPaths);
  const sourceHint = paths.length
    ? `\n\n请优先使用本次投喂材料回答；材料路径供系统路由使用：${paths.join("、")}`
    : "";
  return `${normalizedQuestion}${sourceHint}`;
}

function questionAlreadyHasMaterialRoutingHint(question) {
  return /材料路径供系统路由使用/.test(String(question || ""));
}

function normalizeStickyMaterialRefs(value) {
  const raw = value && typeof value === "object" ? value : {};
  return {
    paths: normalizeMaterialPaths(raw.paths),
    updatedAt: String(raw.updatedAt || "").trim(),
    source: String(raw.source || "").trim(),
  };
}

function setStickyMaterialRefs(settings, paths, source) {
  if (!settings || typeof settings !== "object") {
    return null;
  }
  const next = {
    paths: normalizeMaterialPaths(paths),
    updatedAt: new Date().toISOString(),
    source: String(source || "drop").trim() || "drop",
  };
  settings.stickyMaterialRefs = next;
  return next;
}

function resolveAskMaterialPaths(explicitPaths, sticky) {
  const explicit = normalizeMaterialPaths(explicitPaths);
  if (explicit.length) {
    return { paths: explicit, fromSticky: false };
  }
  const stickyPaths = normalizeStickyMaterialRefs(sticky).paths;
  return { paths: stickyPaths, fromSticky: stickyPaths.length > 0 };
}

function imageDropLacksReadableAnalysis(payload) {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const material = String(payload.material || "").trim().toLowerCase();
  const looksLikeImage =
    material === "image"
    || Boolean(payload.mime_type && String(payload.mime_type).startsWith("image/"))
    || Object.prototype.hasOwnProperty.call(payload, "visual_analysis_present")
    || Object.prototype.hasOwnProperty.call(payload, "vision_status");
  if (!looksLikeImage) {
    return false;
  }
  if (payload.visual_analysis_present === true) {
    return false;
  }
  const status = String(payload.vision_status || "").trim().toLowerCase();
  if (status === "generated") {
    return false;
  }
  return true;
}

function stripQuotedReportLinesForIntent(question) {
  return String(question || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*引用报告\s*[:：]\s*\S+\s*/i, ""))
    .join("\n")
    .trim();
}

function inferAutoAskFormat(question, materialPaths) {
  void question;
  void materialPaths;
  return "report";
}

function buildAutoAskQuestionLegacy(question, materialPaths) {
  const normalizedQuestion = String(question || "").trim();
  if (!normalizedQuestion) {
    return "";
  }
  const paths = normalizeMaterialPaths(materialPaths);
  const pathBlock = paths.length ? `- ${paths.join("\n- ")}` : "- (drop payload 未返回可用路径)";
  return [
    "请基于以下本次投喂材料回答用户问题。",
    "",
    "本次投喂材料路径：",
    pathBlock,
    "",
    "用户问题：",
    normalizedQuestion,
  ].join("\n");
}

function looksLikeUniversalMaterialPayload(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  if (/^\s*引用报告\s*[:：]/im.test(text)) return false;
  const lower = text.toLowerCase();
  if (lower.startsWith("obsidian://open")) return false;
  if (lower.startsWith("http://") || lower.startsWith("https://")) return true;
  if (lower.startsWith("git@") || lower.startsWith("ssh://")) return true;
  if (lower.startsWith("note:") && lower.slice("note:".length).trim()) return true;
  if (lower.endsWith(".git")) return true;
  if (lower.endsWith(".pdf")) return true;
  if ([".md", ".markdown", ".txt"].some((suffix) => lower.endsWith(suffix))) return true;
  if ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].some((suffix) => lower.endsWith(suffix))) return true;
  return false;
}

function isObsidianOpenLink(value) {
  return String(value || "").trim().toLowerCase().startsWith("obsidian://open");
}

function obsidianOpenLinkFilePath(value) {
  const text = String(value || "").trim();
  if (!isObsidianOpenLink(text)) return "";
  try {
    const url = new URL(text);
    const file = String(url.searchParams.get("file") || "").trim();
    return normalizeWorkspaceLinkTarget(file);
  } catch (e) {
    const match = text.match(/[?&]file=([^&]+)/i);
    if (!match) return "";
    try {
      return normalizeWorkspaceLinkTarget(decodeURIComponent(match[1].replace(/\+/g, " ")));
    } catch (_decodeError) {
      return "";
    }
  }
}

function normalizeWorkspaceLinkTarget(value) {
  const text = String(value || "").trim().replace(/\\/g, "/");
  if (!text || text.startsWith("/") || text.startsWith("../") || text.includes("/../")) {
    return "";
  }
  return text;
}

function splitTextMaterialQuestion(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  if (/^\s*引用报告\s*[:：]/im.test(text)) return null;
  const nonEmptyLines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (nonEmptyLines.length >= 2 && looksLikeUniversalMaterialPayload(nonEmptyLines[0])) {
    return {
      payload: nonEmptyLines[0],
      question: nonEmptyLines.slice(1).join("\n"),
    };
  }
  const oneLine = text.match(/^(\S+)\s+([\s\S]+)$/);
  if (oneLine && looksLikeUniversalMaterialPayload(oneLine[1])) {
    return {
      payload: oneLine[1],
      question: oneLine[2].trim(),
    };
  }
  return null;
}

function readJsonText(rawText) {
  const text = String(rawText || "").trim();
  if (!text) {
    return null;
  }
  return JSON.parse(text);
}

function normalizeLocale(locale) {
  return locale === "en" ? "en" : DEFAULT_LOCALE;
}

function t(locale, text, variables = {}) {
  const base = String(text || "");
  const template = normalizeLocale(locale) === "zh" ? ZH_TEXT[base] || base : base;
  return template.replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? ""));
}

function formatDisplayTime(value, locale = DEFAULT_LOCALE) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return new Intl.DateTimeFormat(normalizeLocale(locale) === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function sumNumericValues(values) {
  return Object.values(values || {}).reduce((total, value) => {
    const number = Number(value || 0);
    return total + (Number.isFinite(number) ? number : 0);
  }, 0);
}

function thinCuratedStatusGroup(status) {
  const normalized = String(status || "").trim();
  if (["proposed", "needs-revisit", "tentative", "tracking"].includes(normalized)) {
    return "pending-review";
  }
  if (["approved", "confirmed"].includes(normalized)) {
    return "confirmed";
  }
  if (["superseded", "rejected"].includes(normalized)) {
    return "discarded";
  }
  return normalized;
}

function displayCuratedStatus(status, locale = DEFAULT_LOCALE) {
  const thin = thinCuratedStatusGroup(status);
  const label = THIN_CURATED_STATUS_LABELS[thin]
    || CURATED_STATUS_LABELS[String(status || "").trim()]
    || String(status || "unknown");
  return t(locale, label);
}

function displayActionStatus(status, locale = DEFAULT_LOCALE) {
  return t(locale, ACTION_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown"));
}

function displayRewriteStatus(status, locale = DEFAULT_LOCALE) {
  return t(locale, REWRITE_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown"));
}

function displayReviewReason(reason, locale = DEFAULT_LOCALE) {
  const normalized = String(reason || "").trim();
  return t(locale, REVIEW_REASON_LABELS[normalized] || normalized);
}

function displayReviewReasonList(reasons, locale = DEFAULT_LOCALE) {
  if (!Array.isArray(reasons) || !reasons.length) {
    return "";
  }
  return reasons.map((reason) => displayReviewReason(reason, locale)).filter(Boolean).join(", ");
}

function reviewObjectMetaText(control, locale = DEFAULT_LOCALE) {
  const parts = [
    t(locale, String(control.kind || "").trim() || "page"),
    displayCuratedStatus(control.status, locale),
  ];
  const confidence = String(control.confidence || "").trim();
  if (confidence) {
    parts.push(t(locale, "confidence {value}", { value: confidence }));
  }
  if (String(control.kind || "").trim() === "decision" || String(control.kind || "").trim() === "judgment") {
    parts.push(t(locale, "asset {value}/4", { value: Number(control.asset_score || 0) }));
  }
  const reviewHistoryEntries = Number(control.review_history_entries || 0);
  if (reviewHistoryEntries) {
    parts.push(t(locale, "history {value}", { value: reviewHistoryEntries }));
  }
  if (control.citation_drift) {
    parts.push(t(locale, "drift {value}", { value: Number(control.citation_drift_count || 0) || 1 }));
  }
  const snapshotGapCount = Number(control.citation_snapshot_gap_count || 0);
  if (snapshotGapCount) {
    parts.push(t(locale, "snapshot gaps {value}", { value: snapshotGapCount }));
  }
  const reasons = displayReviewReasonList(control.reasons, locale);
  if (reasons) {
    parts.push(reasons);
  }
  return parts.join(" | ");
}

function buildNotifyEnv(settings) {
  const env = {};
  const channels = [];
  const feishuWebhookUrl = String((settings && settings.feishuWebhookUrl) || "").trim();
  if (feishuWebhookUrl) {
    env.AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL = feishuWebhookUrl;
    channels.push("feishu");
  }
  const wecomWebhookUrl = String((settings && settings.wecomWebhookUrl) || "").trim();
  if (wecomWebhookUrl) {
    env.AIWIKI_NOTIFY_WECOM_WEBHOOK_URL = wecomWebhookUrl;
    channels.push("wecom");
  }
  if (channels.length) {
    env.AIWIKI_NOTIFY_ENABLED_CHANNELS = channels.join(",");
  }
  return env;
}

function reportDate(value) {
  const date = new Date(String(value || ""));
  return Number.isNaN(date.getTime()) ? null : date;
}

function localDateKey(date) {
  return date instanceof Date && !Number.isNaN(date.getTime()) ? date.toDateString() : "";
}

function localDateLabel(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return "unknown";
  }
  const yesterday = new Date();
  yesterday.setHours(0, 0, 0, 0);
  yesterday.setDate(yesterday.getDate() - 1);
  const target = new Date(date);
  target.setHours(0, 0, 0, 0);
  if (target.toDateString() === yesterday.toDateString()) {
    return "Yesterday";
  }
  const year = target.getFullYear();
  const month = String(target.getMonth() + 1).padStart(2, "0");
  const day = String(target.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function splitReportsByLocalDate(reports, options = {}) {
  const limitPreviousDays = Number.isFinite(Number(options.limitPreviousDays))
    ? Math.max(1, Number(options.limitPreviousDays))
    : 7;
  const todayKey = localDateKey(new Date());
  const today = [];
  const previousGroups = new Map();

  (Array.isArray(reports) ? reports : [])
    .filter((report) => report && typeof report === "object")
    .map((report) => ({ report, date: reportDate(report.created_at) }))
    .filter((entry) => entry.date)
    .sort((left, right) => right.date.getTime() - left.date.getTime())
    .forEach((entry) => {
      const key = localDateKey(entry.date);
      if (key === todayKey) {
        today.push(entry.report);
        return;
      }
      if (!previousGroups.has(key)) {
        previousGroups.set(key, { key, label: localDateLabel(entry.date), date: entry.date, items: [] });
      }
      previousGroups.get(key).items.push(entry.report);
    });

  return {
    today,
    previous: Array.from(previousGroups.values())
      .sort((left, right) => right.date.getTime() - left.date.getTime())
      .slice(0, limitPreviousDays),
  };
}

function resolveAskOutputPath(payload) {
  if (!payload || typeof payload !== "object") return "";
  const reportPath = String(payload.report_path || payload.reportPath || "").trim();
  if (reportPath) return reportPath;
  const outputPath = String(payload.output_path || payload.outputPath || "").trim();
  if (outputPath && outputPath.startsWith("output/")) return outputPath;
  const path = String(payload.path || "").trim();
  if (path && path.startsWith("output/")) return path;
  for (const nestedKey of ["payload", "result", "ask_result", "ask"]) {
    const nested = payload[nestedKey];
    if (nested && typeof nested === "object") {
      const nestedPath = resolveAskOutputPath(nested);
      if (nestedPath) return nestedPath;
    }
  }
  return "";
}

function finalizePendingAskSubmission(plugin, pendingId, payload) {
  if (!pendingId) return;
  const outputPath = resolveAskOutputPath(payload);
  if (outputPath) {
    plugin.markPendingSubmissionDone(pendingId, "outputs", outputPath);
    return;
  }
  plugin.markPendingSubmissionFailed(
    pendingId,
    new Error(plugin.t("提问成功但未返回报告路径"))
  );
}

function elixirIdFromLinkedRefs(linkedRefs) {
  const refs = Array.isArray(linkedRefs) ? linkedRefs : [];
  for (const ref of refs) {
    const text = String(ref || "").trim();
    if (!text) continue;
    const normalized = text.replace(/\\/g, "/");
    if (normalized.startsWith("wiki/elixirs/") && normalized.endsWith(".md")) {
      const base = normalized.slice("wiki/elixirs/".length, -".md".length);
      if (base) return base;
    }
  }
  return "";
}
