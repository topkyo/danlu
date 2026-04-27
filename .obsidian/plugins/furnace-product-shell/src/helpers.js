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

function normalizeLastViewedTimestamp(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Date(value).toISOString();
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return "";
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

function isReportUnread(report, lastViewedTimestamp) {
  const createdAt = reportDate(report && report.created_at);
  if (!createdAt) {
    return false;
  }
  const normalizedLastViewed = normalizeLastViewedTimestamp(lastViewedTimestamp);
  if (!normalizedLastViewed) {
    return true;
  }
  const lastViewed = reportDate(normalizedLastViewed);
  if (!lastViewed) {
    return true;
  }
  return createdAt.getTime() > lastViewed.getTime();
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
