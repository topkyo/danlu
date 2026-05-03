/**
 * M6.3 B3 Today Feed builder — JS mirror of src/aiwiki/today_feed.py
 * 
 * MIRROR: 与 src/aiwiki/today_feed.py 同步排序契约与字段映射。
 * 修改任一侧时必须同步另一侧。
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
  "overdue_actions",
  "overdue_reviews",
  "pending_decisions",
  "pending_judgments",
  "ready_actions",
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
  entries.push(...buildElixirEntries(summary, todayDate));
  entries.push(...buildMetricAlertEntries(summary));
  entries.push(...buildAgentLoopEntries(summary, todayDate));
  entries.push(...buildActionEntries(summary, "primary"));
  entries.push(...buildLlmHealthEntry(summary));

  const filtered = applySnoozeFilter(entries, summary, todayDate);
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

function buildReportEntries(summary, todayDate) {
  const entries = [];
  for (const item of dictItems(summary.recent_outputs)) {
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
    });
  }
  return entries;
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
    // Planner decisions are derived from signals; don't double-count one change in user-facing copy.
    const newItems = Math.max(asCount(signals.new_count), asCount(execute.new_count));
    const appliedCount = asCount(autoApply.applied_count);
    const readyCount = asCount(autoPreview.ready_count);
    if (appliedCount > 0) {
      title = "已自动维护";
      summaryText = `今日发现 ${newItems} 个新变化，已静默执行 ${appliedCount} 条维护路径`;
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

function buildLlmHealthEntry(summary) {
  var health = summary.llm_health;
  if (!health || typeof health !== "object") return [];
  var status = String(health.status || "");
  if (status === "healthy" || status === "unknown") return [];
  var timestamp = String(health.checked_at || summary.generated_at || "");
  var reason = String(health.reason || "");
  var recovery = String(health.recovery_command || "");
  var title = "LLM 后端异常";
  var summaryText = reason || "LLM 后端暂时不可用，部分报告可能未生成";
  if (status === "degraded") {
    title = "LLM 后端降级";
    summaryText = reason || "LLM 后端当前以降级模式运行，报告质量可能受影响";
  }
  return [{
    kind: "automation",
    title: title,
    summary: summaryText,
    target: recovery || "scripts/aiwiki-launcher.sh llm-check",
    timestamp: timestamp,
    protocol: "",
    autoState: status === "degraded" ? "pending" : "attention",
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

function compareEntries(a, b) {
  const pa = PRIORITY[a.kind];
  const pb = PRIORITY[b.kind];
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
  isMaintenanceCommandAction,
  PRIORITY,
  PRIMARY_REVIEW_BUCKETS,
};
