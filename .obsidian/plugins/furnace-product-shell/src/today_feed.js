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
  l3_proposals: ["处理 L3 提案", "确认采纳、拒绝或回滚提案"],
  l3_proposal_attention: ["处理 L3 提案", "确认采纳、拒绝或回滚提案"],
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

  entries.push(...buildDecisionEntries(summary));
  entries.push(...buildCounterEvidenceEntries(summary));
  entries.push(...buildDriftEntries(summary));
  entries.push(...buildProposalEntries(summary));
  entries.push(...buildReportEntries(summary, todayDate));
  entries.push(...buildCompoundSuggestEntries(summary));
  entries.push(...buildElixirEntries(summary, todayDate));
  // Routine metrics and automation status stay in Advanced/operator surfaces;
  // primary Today only keeps reports, decision exceptions, and necessary actions.
  entries.push(...buildActionEntries(summary, "primary"));
  entries.push(...buildRawInputEntries(summary, todayDate));

  const prioritized = entries.map((entry) => ({ ...entry, priority: priorityForKind(entry.kind) }));
  const filtered = applySnoozeFilter(prioritized, summary, todayDate);
  filtered.sort(compareEntries);
  return filtered;
}

function buildDecisionEntries(summary) {
  const counts = summary.review_backlog_counts;
  if (!counts || typeof counts !== "object") return [];
  const timestamp = String(summary.generated_at || "");
  const entries = [];
  
  const sortedKeys = Object.keys(counts).sort();
  for (const kind of sortedKeys) {
    const count = asCount(counts[kind]);
    if (count <= 0) continue;
    const kindText = String(kind).trim();
    if (!kindText) continue;
    if (!PRIMARY_REVIEW_BUCKETS.has(kindText)) continue;
    const [title, hint] = reviewBucketCopy(kindText);
    entries.push({
      kind: "decision",
      title,
      summary: `${count} 项待处理 · ${hint}`,
      target: `review:${kindText}`,
      timestamp,
      protocol: "",
    });
  }
  return entries;
}

function buildCounterEvidenceEntries(summary) {
  const pages = summary.counter_evidence_pages;
  if (!Array.isArray(pages)) return [];
  const entries = [];
  for (const item of dictItems(pages)) {
    const target = firstText(item, "path");
    if (!target) continue;
    const subject = firstText(item, "subject") || target;
    const pageSummary = firstText(item, "summary") || "judgment 被反驳";
    entries.push({
      kind: "decision",
      title: `反证待复核: ${subject}`,
      summary: pageSummary,
      target,
      timestamp: firstText(item, "detected_at"),
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
}

function buildDriftEntries(summary) {
  const warnings = summary.drift_warnings;
  if (!Array.isArray(warnings)) return [];
  const entries = [];
  for (const item of dictItems(warnings).slice(0, 8)) {
    const kindText = firstText(item, "kind");
    const target = firstText(item, "path");
    const message = firstText(item, "message");
    if (!target && !message) continue;
    const titleTarget = target || kindText || "drift";
    entries.push({
      kind: "decision",
      title: `知识漂移: ${titleTarget}`,
      summary: message || kindText || "证据已变",
      target: target || kindText,
      timestamp: firstText(item, "detected_at"),
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
}

function buildProposalEntries(summary) {
  const reviewControls = summary.review_controls;
  let source = null;
  if (reviewControls && typeof reviewControls === "object") {
    source = reviewControls.l3_proposals;
  } else {
    source = summary.l3_proposals;
  }
  const entries = [];
  for (const item of dictItems(source)) {
    if (!item.needs_attention) continue;
    const proposalId = firstText(item, "proposal_id", "id", "subject_id");
    const title = firstText(item, "title", "subject", "target_file", "proposal_id") || proposalId;
    const target = firstText(item, "proposal_path", "path", "target_file", "proposal_id");
    const timestamp = firstText(
      item,
      "updated_at",
      "created_at",
      "accepted_at",
      "rejected_at",
      "reverted_at",
      "stale_at",
      "revert_conflict_at"
    );
    if (!title || !target) continue;
    const kindText = firstText(item, "kind") || "proposal";
    const state = firstText(item, "state", "current_status") || "pending";
    entries.push({
      kind: "proposal",
      title,
      summary: `${kindText} 建议等待处理（${state}）`,
      target,
      timestamp,
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
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

function buildCompoundSuggestEntries(summary) {
  const timestamp = String(summary.generated_at || "");
  const entries = [];
  for (const item of compoundSuggestItems(summary)) {
    const title = firstText(item, "title", "report_title");
    const reportPath = firstText(item, "report_path");
    const reason = firstText(item, "reason", "signal") || "compound-suggest";
    if (!title) continue;
    entries.push({
      kind: "action",
      title,
      summary: `复利建议：${reason}`,
      target: reportPath || firstText(item, "command"),
      timestamp,
      protocol: firstText(item, "protocol"),
      compound_suggest: item,
    });
  }
  return entries;
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
  if (["submitted", "running", "degraded"].includes(backgroundStatus)) return false;
  if (["degraded", "placeholder"].includes(artifactQuality)) return false;
  if (["1", "true", "yes"].includes(placeholder)) return false;
  if (title.startsWith("LLM 未完成")) return false;
  return true;
}

function buildElixirEntries(summary, todayDate) {
  const entries = [];
  for (const item of dictItems(summary.recent_receipts)) {
    const timestamp = firstText(item, "applied_at", "generated_at", "created_at");
    if (datePart(timestamp) !== todayDate) continue;
    const operation = firstText(item, "operation");
    const subjectKind = firstText(item, "subject_kind");
    const subjectId = firstText(item, "subject_id");
    const actionId = firstText(item, "action_id");
    
    const elixirText = [operation, subjectKind, subjectId, actionId].join(" ").toLowerCase();
    const opLower = operation.toLowerCase();
    
    const hasElixir = elixirText.includes("elixir");
    const hasToken = ["promote", "demote", "revert", "finalize"].some(token => opLower.includes(token));
    
    if (!hasElixir && !hasToken) continue;
    
    const title = firstText(item, "title") || subjectId || actionId;
    const target = firstText(item, "receipt_path", "path");
    if (!title || !target) continue;
    
    entries.push({
      kind: "elixir",
      title,
      summary: `已完成 ${operation || '更新'}`,
      target,
      timestamp,
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
}

function buildMetricAlertEntries(summary) {
  const delta = summary.metrics_history_delta;
  if (!delta || typeof delta !== "object" || !delta.available) return [];
  const alerts = delta.alerts;
  if (!Array.isArray(alerts)) return [];
  const windowLabel = String(delta.window || "");
  const baselineTs = String(delta.baseline_ts || "");
  const entries = [];
  for (const item of dictItems(alerts)) {
    const key = firstText(item, "metric_key");
    if (!key) continue;
    const direction = firstText(item, "direction");
    const rawDiff = Number(item.diff || 0);
    const diffValue = Number.isFinite(rawDiff) ? rawDiff : 0;
    const arrow = direction === "up" ? "↑" : "↓";
    const sign = diffValue >= 0 ? "+" : "";
    entries.push({
      kind: "action",
      title: `指标变化: ${key} ${arrow}`,
      summary: `${windowLabel} 内 ${key} 变化 ${sign}${diffValue.toPrecision(3)}（vs ${baselineTs}）`,
      target: `metric:${key}`,
      timestamp: baselineTs,
      protocol: "",
    });
  }
  return entries;
}

function buildActionEntries(summary, audience = "primary") {
  const entries = [];
  const generatedAt = String(summary.generated_at || "");
  for (const item of dictItems(summary.suggested_next_actions)) {
    if (firstText(item, "kind") === "compound-suggest") continue;
    const title = firstText(item, "title", "label", "name");
    const target = firstText(item, "command", "cli", "action", "path");
    if (!title || !target) continue;
    const reason = firstText(item, "reason", "kind");
    if (audience === "primary" && isMaintenanceCommandAction(target, reason)) continue;
    entries.push({
      kind: "action",
      title,
      summary: `建议下一步：${reason || '继续处理'}`,
      target,
      timestamp: firstText(item, "timestamp", "updated_at", "created_at") || generatedAt,
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
}

function buildRawInputEntries(summary, todayDate) {
  const recentRawInputs = summary.recent_raw_inputs;
  if (!Array.isArray(recentRawInputs)) return [];
  const entries = [];
  for (const item of dictItems(recentRawInputs)) {
    const storedPath = firstText(item, "stored_path");
    if (!storedPath) continue;
    const occurredAt = firstText(item, "occurred_at");
    if (datePart(occurredAt) !== todayDate) continue;
    const originalPath = firstText(item, "original_path");
    const title = firstText(item, "title");
    const sourceType = firstText(item, "source_type");
    const sourceLabel = rawInputSourceTypeLabel(sourceType);
    entries.push({
      kind: "action",
      title: `已投料：${title || originalPath || storedPath}`,
      summary: `已接收 ${sourceLabel}，等待编译/刷新`,
      target: storedPath,
      timestamp: occurredAt,
      protocol: firstText(item, "protocol"),
    });
  }
  return entries;
}

function rawInputSourceTypeLabel(sourceType) {
  const normalized = String(sourceType || "").trim();
  const labels = {
    "note-drop": "文本材料",
    note: "文本材料",
    markdown: "Markdown 材料",
    "url-drop": "网页材料",
    "pdf-drop": "PDF 材料",
    "image-drop": "图片材料",
    "repo-drop": "代码仓库材料",
  };
  return labels[normalized] || "材料";
}

function isMaintenanceCommandAction(target, reason) {
  const targetText = ` ${String(target || "").trim()} `;
  const reasonText = String(reason || "").trim();
  if (reasonText.startsWith("batch-hint:")) return true;
  const maintenanceTokens = [
    " review-page ",
    " review-action ",
    " apply-action ",
    " revert-action ",
    " review-concept ",
    " retire-concept ",
    " reactivate-concept ",
    " apply-rewrite ",
    " review-rewrite ",
    " revert-rewrite ",
    " apply-archive ",
    " revert-archive ",
    " alchemy auto ",
  ];
  return maintenanceTokens.some((token) => targetText.includes(token));
}

function buildAgentLoopEntries(summary, todayDate) {
  const nightly = summary.nightly;
  if (!nightly || typeof nightly !== "object") return [];
  const agentLoop = nightly.agent_loop;
  if (!agentLoop || typeof agentLoop !== "object") return [];
  const timestamp = String(agentLoop.generated_at || nightly.generated_at || "");
  if (datePart(timestamp) !== todayDate) return [];
  const status = String(agentLoop.status || "");
  if (status !== "ok" && status !== "failed") return [];

  let title = "预演下一步维护";
  let summaryText = "今日维护预演完成，暂不需要自动执行";
  let target = "PYTHONPATH=src python3 -m aiwiki.cli --root . alchemy auto --dry-run";
  let autoState = "idle";
  if (status === "failed") {
    summaryText = "今日维护预演失败，需要人工查看";
    autoState = "attention";
  } else {
    const signals = agentLoop.signals && typeof agentLoop.signals === "object" ? agentLoop.signals : {};
    const planner = agentLoop.planner && typeof agentLoop.planner === "object" ? agentLoop.planner : {};
    const execute = planner.execute && typeof planner.execute === "object" ? planner.execute : {};
    const autoPreview = agentLoop.auto_preview && typeof agentLoop.auto_preview === "object" ? agentLoop.auto_preview : {};
    const autoApply = agentLoop.auto_apply && typeof agentLoop.auto_apply === "object" ? agentLoop.auto_apply : {};
    const autoAdoptL1 = agentLoop.auto_adopt_l1 && typeof agentLoop.auto_adopt_l1 === "object" ? agentLoop.auto_adopt_l1 : {};
    const autoAdoptL2 = agentLoop.auto_adopt_l2 && typeof agentLoop.auto_adopt_l2 === "object" ? agentLoop.auto_adopt_l2 : {};
    const autoAdoptJ = agentLoop.auto_adopt_judgments && typeof agentLoop.auto_adopt_judgments === "object" ? agentLoop.auto_adopt_judgments : {};
    // Planner decisions are derived from signals; don't double-count one change in user-facing copy.
    const newItems = Math.max(asCount(signals.new_count), asCount(execute.new_count));
    const appliedCount = asCount(autoApply.applied_count);
    const readyCount = asCount(autoPreview.ready_count);
    const l1Count = (Array.isArray(autoAdoptL1.items) ? autoAdoptL1.items : []).reduce(function(acc, item) { return acc + (typeof item.count === 'number' && item.count > 0 && !item.error ? item.count : 0); }, 0);
    const l2Count = (Array.isArray(autoAdoptL2.items) ? autoAdoptL2.items : []).reduce(function(acc, item) { return acc + (typeof item.count === 'number' && item.count > 0 && !item.error ? item.count : 0); }, 0);
    const jReviewed = typeof autoAdoptJ.reviewed === 'number' ? autoAdoptJ.reviewed : 0;
    const totalAdopted = appliedCount + l1Count + l2Count;
    if (totalAdopted > 0 || jReviewed > 0) {
      var parts = ["今日发现 " + newItems + " 个新变化"];
      if (appliedCount > 0) parts.push("已静默执行 " + appliedCount + " 条维护路径");
      if (l1Count > 0) parts.push("已自动消化 " + l1Count + " 条 L1 候选");
      if (l2Count > 0) parts.push("已自动处理 " + l2Count + " 条 L2 动作");
      if (jReviewed > 0) parts.push("LLM 已复核 " + jReviewed + " 条判断");
      title = "已自动维护";
      summaryText = parts.join("，");
      target = "wiki/indexes/execution-audit.md";
      autoState = "ok";
    } else if (readyCount > 0) {
      summaryText = `今日发现 ${newItems} 个新变化，${readyCount} 条维护路径可人工确认`;
      autoState = "pending";
    }
  }

  return [{
    kind: "automation",
    title,
    summary: summaryText,
    target,
    timestamp,
    protocol: String(summary.active_protocol || ""),
    autoState: autoState,
  }];
}

// Helpers

function todayDateOf(summary) {
  return datePart(String(summary.generated_at || ""));
}

function applySnoozeFilter(entries, summary, todayDate) {
  const state = summary && typeof summary === "object" ? summary.today_snooze : null;
  if (!state || typeof state !== "object" || !Array.isArray(state.items)) return entries;
  const activeTargets = new Set();
  for (const item of state.items) {
    if (!item || typeof item !== "object") continue;
    const target = String(item.target || "").trim();
    const until = datePart(String(item.snoozed_until || ""));
    if (target && until && until >= todayDate) activeTargets.add(target);
  }
  if (!activeTargets.size) return entries;
  return entries.filter((entry) => !activeTargets.has(String(entry.target || "")));
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

function asCount(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return isNaN(value) ? 0 : Math.floor(value);
  const parsed = parseInt(String(value), 10);
  return isNaN(parsed) ? 0 : parsed;
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
  const ta = a.timestamp || "";
  const tb = b.timestamp || "";
  if (ta !== tb) return ta < tb ? 1 : -1;
  return a.kind < b.kind ? -1 : (a.kind > b.kind ? 1 : 0);
}

module.exports = {
  buildTodayFeed,
  applySnoozeFilter,
  compareEntries,
  todayDateOf,
  reviewBucketCopy,
  priorityForKind,
  isMaintenanceCommandAction,
  compoundSuggestItems,
  compoundSuggestIndex,
  buildCompoundSuggestEntries,
  PRIORITY,
  PRIMARY_REVIEW_BUCKETS,
};
