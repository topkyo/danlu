/**
 * M6.3 B3 Today Feed builder — JS mirror of src/aiwiki/today_feed.py
 * 
 * MIRROR: 与 src/aiwiki/today_feed.py 同步排序契约与字段映射。
 * Product Shell keeps backend health in Advanced/operator surfaces, not primary Today.
 */
"use strict";

// MIRROR of src/aiwiki/today_feed.py _PRIORITY; SoT is schema/today-feed.json kind_priority (both sides' tests pin against it).
const PRIORITY = {
  report: 1,
  automation: 2,
  decision: 3,
  elixir: 4,
  action: 5,
};

const PRIMARY_REVIEW_BUCKETS = new Set([
  "counter_evidence_candidates",
  "escalated_actions",
  "escalation_candidates",
  "judgment_review_actions",
  "pending_decisions",
  "pending_judgments",
]);

function buildTodayFeed(summary) {
  if (!summary || typeof summary !== "object") return [];
  const todayDate = todayDateOf(summary);
  const entries = [];

  entries.push(...buildReportEntries(summary, todayDate));
  entries.push(...buildCoverageGapEntries(summary, todayDate));
  entries.push(...buildWatcherStaleEntries(summary));
  // Primary Today: today's reports, coverage gaps, and a stale-watcher action.
  // Compound suggest stays on report cards; governance backlog stays in Advanced.

  const prioritized = entries.map((entry) => ({ ...entry, priority: priorityForKind(entry.kind) }));
  prioritized.sort(compareEntries);
  return prioritized;
}

function compoundSuggestItems(summary) {
  const compound = summary.compound_suggest;
  if (!compound || typeof compound !== "object" || !compound.available) return [];
  const items = compound.items;
  if (!Array.isArray(items)) return [];
  return items.filter((item) => item && typeof item === "object");
}

function compoundSuggestIndex(summary) {
  const index = {};
  for (const item of compoundSuggestItems(summary)) {
    const reportPath = firstText(item, "report_path");
    if (reportPath) index[reportPath] = item;
  }
  return index;
}

function buildReportEntries(summary, todayDate) {
  const entries = [];
  const suggestIndex = compoundSuggestIndex(summary);
  for (const item of dictItems(summary.recent_outputs)) {
    if (!isDeliverableReportOutput(item)) continue;
    const timestamp = firstText(item, "generated_at", "created_at");
    if (datePart(timestamp) !== todayDate) continue;
    const path = firstText(item, "path", "artifact_path");
    
    // JS rough equivalent of Path(path).name
    let defaultTitle = path;
    if (path) {
      const parts = path.split(/[/\\]/);
      defaultTitle = parts[parts.length - 1];
    }
    const title = firstText(item, "title") || defaultTitle;
    const outputFormat = firstText(item, "format") || "未知格式";
    if (!path || !title) continue;
    entries.push({
      kind: "report",
      title,
      summary: `${outputFormat} 输出`,
      target: path,
      timestamp,
      protocol: firstText(item, "protocol"),
      compound_suggest: suggestIndex[path] || null,
    });
  }
  return entries;
}

function buildCoverageGapEntries(summary, todayDate) {
  const entries = [];
  for (const item of dictItems(summary.recent_outputs)) {
    if (firstText(item, "artifact_quality") !== "no-evidence") continue;
    const timestamp = firstText(item, "generated_at", "created_at");
    if (datePart(timestamp) !== todayDate) continue;
    const path = firstText(item, "path", "artifact_path");
    let defaultTitle = path;
    if (path) {
      const parts = path.split(/[/\\]/);
      defaultTitle = parts[parts.length - 1];
    }
    const title = firstText(item, "title") || defaultTitle;
    if (!path || !title) continue;
    entries.push({
      kind: "action",
      title: `未覆盖：${title}`,
      summary: "知识库没有足够证据。可用 drop url 投喂来源后再问。",
      target: path,
      timestamp,
      protocol: firstText(item, "protocol"),
      compound_suggest: null,
    });
  }
  return entries;
}

function buildWatcherStaleEntries(summary) {
  const watcher = summary.watcher;
  if (!watcher || typeof watcher !== "object" || !watcher.stale) return [];
  return [
    {
      kind: "action",
      title: "投喂监视已停滞",
      summary: "新投喂可能不会被自动处理。检查 launchd com.aiwiki.watch，或运行 aiwiki advanced watch。",
      target: firstText(watcher, "state_path") || ".aiwiki/state/automation.json",
      timestamp: String(summary.generated_at || ""),
      protocol: "",
      compound_suggest: null,
    },
  ];
}

function isDeliverableReportOutput(item) {
  const deliveryMode = firstText(item, "delivery_mode");
  const llmStatus = firstText(item, "llm_status");
  const backgroundStatus = firstText(item, "background_status");
  const artifactQuality = firstText(item, "artifact_quality");
  const placeholder = firstText(item, "contains_llm_placeholder").toLowerCase();
  const title = firstText(item, "title");
  if (deliveryMode === "deterministic-fallback") return false;
  if (["timeout_or_unavailable", "validation_failed", "pending", "failed", "degraded"].includes(llmStatus)) return false;
  if (backgroundStatus === "degraded") return false;
  if (["degraded", "placeholder", "no-evidence"].includes(artifactQuality)) return false;
  if (["1", "true", "yes"].includes(placeholder)) return false;
  if (title.startsWith("LLM 未完成")) return false;
  return true;
}

// Helpers

function todayDateOf(summary) {
  return datePart(String(summary.generated_at || ""));
}

function datePart(value) {
  const text = String(value || "").trim();
  if (text.includes("T")) return text.split("T")[0];
  if (text.includes(" ")) return text.split(" ")[0];
  return text.substring(0, 10);
}

function dictItems(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(item => item && typeof item === "object");
}

function firstText(item, ...keys) {
  for (const key of keys) {
    const value = item[key];
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return "";
}

function priorityForKind(kind) {
  return PRIORITY[String(kind)] || 99;
}

function compareEntries(a, b) {
  const pa = priorityForKind(a.kind);
  const pb = priorityForKind(b.kind);
  if (pa !== pb) return pa - pb;
  const ta = a.timestamp || "\x7f";
  const tb = b.timestamp || "\x7f";
  // Ascending: older first, newest last (near the composer).
  if (ta !== tb) return ta < tb ? -1 : 1;
  return a.kind < b.kind ? -1 : (a.kind > b.kind ? 1 : 0);
}

module.exports = {
  buildTodayFeed,
  compareEntries,
  todayDateOf,
  priorityForKind,
  compoundSuggestItems,
  compoundSuggestIndex,
  PRIORITY,
  PRIMARY_REVIEW_BUCKETS,
};
