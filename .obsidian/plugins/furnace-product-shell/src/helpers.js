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

function displayCuratedStatus(status, locale = DEFAULT_LOCALE) {
  return t(locale, CURATED_STATUS_LABELS[String(status || "").trim()] || String(status || "unknown"));
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

function groupReportsByDate(reports) {
  if (!Array.isArray(reports)) return [];
  const groups = {};
  for (const report of reports) {
    if (!report.created_at) continue;
    const dateStr = report.created_at.split("T")[0];
    if (!groups[dateStr]) groups[dateStr] = [];
    groups[dateStr].push(report);
  }
  return Object.entries(groups)
    .sort((a, b) => b[0].localeCompare(a[0])) // Descending dates
    .map(([date, items]) => ({ date, items }));
}

function countUnreadReports(reports, lastViewedTimestamp) {
  if (!Array.isArray(reports)) return 0;
  return reports.filter(r => {
    if (!r.created_at) return false;
    const ts = new Date(r.created_at).getTime();
    return !Number.isNaN(ts) && ts > lastViewedTimestamp;
  }).length;
}

function extractReportIds(reports) {
  if (!Array.isArray(reports)) return [];
  return reports.map(r => r.path || r.title || r.created_at).filter(Boolean);
}
