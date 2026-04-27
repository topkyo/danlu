/**
 * M6.3 B3 Today Feed builder — JS mirror of src/aiwiki/today_feed.py
 * 
 * MIRROR: 与 src/aiwiki/today_feed.py 同步排序契约与字段映射。
 * 修改任一侧时必须同步另一侧。
 */
"use strict";

const PRIORITY = {
  decision: 1,
  proposal: 2,
  report: 3,
  elixir: 4,
  action: 5,
};

function buildTodayFeed(summary) {
  if (!summary || typeof summary !== "object") return [];
  const todayDate = todayDateOf(summary);
  const entries = [];

  entries.push(...buildDecisionEntries(summary));
  entries.push(...buildProposalEntries(summary));
  entries.push(...buildReportEntries(summary, todayDate));
  entries.push(...buildElixirEntries(summary, todayDate));
  entries.push(...buildActionEntries(summary));

  entries.sort(compareEntries);
  return entries;
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
    entries.push({
      kind: "decision",
      title: `待审议: ${kindText}`,
      summary: `${count} 项待审`,
      target: `review:${kindText}`,
      timestamp,
      protocol: "",
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

function buildActionEntries(summary) {
  const entries = [];
  const generatedAt = String(summary.generated_at || "");
  for (const item of dictItems(summary.suggested_next_actions)) {
    const title = firstText(item, "title", "label", "name");
    const target = firstText(item, "command", "cli", "action", "path");
    if (!title || !target) continue;
    const reason = firstText(item, "reason", "kind");
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

function asCount(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return isNaN(value) ? 0 : Math.floor(value);
  const parsed = parseInt(String(value), 10);
  return isNaN(parsed) ? 0 : parsed;
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
  PRIORITY,
};
