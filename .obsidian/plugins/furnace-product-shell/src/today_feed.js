/**
 * M6.3 B3 Today Feed builder — JS mirror of src/aiwiki/today_feed.py
 * 
 * MIRROR: 与 src/aiwiki/today_feed.py 同步排序契约与字段映射。
 * Product Shell keeps backend health in Advanced/operator surfaces, not primary Today.
 */
"use strict";

const PRIORITY = {
  report: 1,
  automation: 2,
  decision: 3,
  proposal: 4,
  elixir: 5,
  action: 6,
};

const REVIEW_BUCKET_COPY = {
  counter_evidence_candidates: ["补充反证候选", "检查新来源是否足以反驳既有判断"],
  escalated_actions: ["处理升级动作", "处理已升级、需要人工确认的动作"],
  escalation_candidates: ["处理升级候选", "确认是否需要人工介入"],
  judgment_review_actions: ["复核研究判断", "处理需要重新判断的结论"],
  machine_memory_actions: ["修复机器记忆", "处理可审计的记忆修复动作"],
  overdue_actions: ["处理逾期动作", "确认是否继续执行或关闭"],
  overdue_reviews: ["处理逾期复审", "确认旧判断是否仍成立"],
  pending_decisions: ["处理待定决策", "确认待定判断与执行入口"],
  pending_judgments: ["复核待定判断", "推进仍在等待复核的判断"],
  ready_actions: ["确认待执行动作", "复核已经准备好的安全动作"],
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
  // Primary Today: today's reports only. Compound suggest stays on report cards;
  // governance backlog and operator maintenance stay in Advanced / operator feed.

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
  if (["degraded", "placeholder"].includes(artifactQuality)) return false;
  if (["1", "true", "yes"].includes(placeholder)) return false;
  if (title.startsWith("LLM 未完成")) return false;
  return true;
}

function isMaintenanceCommandAction(target, reason) {
  const targetText = ` ${String(target || "").trim()} `;
  const reasonText = String(reason || "").trim();
  if (reasonText.startsWith("batch-hint:")) return true;
  const maintenanceTokens = [
    " review-page ",
    " review-queue ",
    " --batch ",
    " --next ",
  ];
  return maintenanceTokens.some((token) => targetText.includes(token));
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

function reviewBucketCopy(kindText) {
  const copy = REVIEW_BUCKET_COPY[kindText];
  if (copy) return copy;
  const label = String(kindText || "").replace(/[_-]/g, " ").trim();
  return [label ? `处理审阅队列：${label}` : "处理审阅队列", "进入审阅中心确认下一步"];
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
  reviewBucketCopy,
  priorityForKind,
  isMaintenanceCommandAction,
  compoundSuggestItems,
  compoundSuggestIndex,
  PRIORITY,
  PRIMARY_REVIEW_BUCKETS,
};
