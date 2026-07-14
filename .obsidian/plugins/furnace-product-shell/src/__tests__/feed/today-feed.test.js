"use strict";

const {
  buildTodayFeed,
  applySnoozeFilter,
  compareEntries,
  todayDateOf,
  reviewBucketCopy,
  priorityForKind,
  isMaintenanceCommandAction,
  PRIORITY,
  PRIMARY_REVIEW_BUCKETS,
} = require("../../today_feed");

// ── Helpers ──────────────────────────────────────────────────────────

function makeSummary(overrides = {}) {
  return {
    generated_at: "2026-05-03T12:00:00Z",
    active_protocol: "research",
    review_backlog_counts: {},
    counter_evidence_pages: [],
    drift_warnings: [],
    l3_proposals: null,
    review_controls: { l3_proposals: [] },
    recent_outputs: [],
    recent_receipts: [],
    suggested_next_actions: [],
    metrics_history_delta: { available: false },
    today_snooze: { items: [] },
    ...overrides,
  };
}

// ── PRIORITY ──────────────────────────────────────────────────────────

test("PRIORITY defines correct ordering", () => {
  expect(PRIORITY.report).toBe(1);
  expect(PRIORITY.automation).toBe(2);
  expect(PRIORITY.decision).toBe(3);
  expect(PRIORITY.proposal).toBe(4);
  expect(PRIORITY.elixir).toBe(5);
  expect(PRIORITY.action).toBe(6);
  // Lower number = higher priority
  expect(PRIORITY.report).toBeLessThan(PRIORITY.action);
});

test("priorityForKind mirrors feed entry priority", () => {
  expect(priorityForKind("report")).toBe(1);
  expect(priorityForKind("unknown")).toBe(99);
});

// ── compareEntries ────────────────────────────────────────────────────

test("compareEntries sorts by priority (kind)", () => {
  const report = { kind: "report", timestamp: "" };
  const decision = { kind: "decision", timestamp: "" };
  const action = { kind: "action", timestamp: "" };
  expect(compareEntries(report, decision)).toBeLessThan(0);
  expect(compareEntries(decision, action)).toBeLessThan(0);
  expect(compareEntries(action, report)).toBeGreaterThan(0);
});

test("compareEntries same priority sorts by timestamp descending", () => {
  const a = { kind: "report", timestamp: "2026-05-01" };
  const b = { kind: "report", timestamp: "2026-05-03" };
  // newer (B) should come before older (A)
  expect(compareEntries(a, b)).toBeGreaterThan(0);
  expect(compareEntries(b, a)).toBeLessThan(0);
});

test("compareEntries handles missing timestamps", () => {
  const a = { kind: "report", timestamp: "" };
  const b = { kind: "report", timestamp: "" };
  expect(compareEntries(a, b)).toBe(0);
});

// ── todayDateOf ───────────────────────────────────────────────────────

test("todayDateOf extracts date from ISO timestamp", () => {
  expect(todayDateOf({ generated_at: "2026-05-03T12:00:00Z" })).toBe("2026-05-03");
});

test("todayDateOf handles empty summary", () => {
  expect(todayDateOf({})).toBe("");
});

// ── reviewBucketCopy ──────────────────────────────────────────────────

test("reviewBucketCopy returns known chinese labels", () => {
  const [title, hint] = reviewBucketCopy("counter_evidence_candidates");
  expect(title).toBe("补充反证候选");
  expect(hint).toBeTruthy();
});

test("reviewBucketCopy falls back for unknown kind", () => {
  const [title] = reviewBucketCopy("unknown_kind");
  expect(title).toContain("unknown kind");
});

test("PRIMARY_REVIEW_BUCKETS contains expected keys", () => {
  expect(PRIMARY_REVIEW_BUCKETS.has("counter_evidence_candidates")).toBe(true);
  expect(PRIMARY_REVIEW_BUCKETS.has("escalated_actions")).toBe(true);
  expect(PRIMARY_REVIEW_BUCKETS.has("escalation_candidates")).toBe(true);
  expect(PRIMARY_REVIEW_BUCKETS.has("judgment_review_actions")).toBe(true);
  expect(PRIMARY_REVIEW_BUCKETS.has("pending_decisions")).toBe(true);
  expect(PRIMARY_REVIEW_BUCKETS.has("pending_judgments")).toBe(true);
  // Routine or low-level buckets should NOT be in this set
  expect(PRIMARY_REVIEW_BUCKETS.has("overdue_actions")).toBe(false);
  expect(PRIMARY_REVIEW_BUCKETS.has("overdue_reviews")).toBe(false);
  expect(PRIMARY_REVIEW_BUCKETS.has("ready_actions")).toBe(false);
  expect(PRIMARY_REVIEW_BUCKETS.has("machine_memory_actions")).toBe(false);
});

// ── isMaintenanceCommandAction ────────────────────────────────────────

test("isMaintenanceCommandAction detects batch-hint prefix", () => {
  expect(isMaintenanceCommandAction(" review-page foo.md ", "batch-hint:concept")).toBe(true);
});

test("isMaintenanceCommandAction detects maintenance tokens", () => {
  expect(isMaintenanceCommandAction(" review-page foo.md ", "")).toBe(true);
  expect(isMaintenanceCommandAction(" apply-action ", "")).toBe(true);
  expect(isMaintenanceCommandAction(" alchemy auto --dry-run ", "")).toBe(true);
});

test("isMaintenanceCommandAction returns false for user commands", () => {
  expect(isMaintenanceCommandAction(" PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask ", "")).toBe(false);
  expect(isMaintenanceCommandAction(" compile ", "")).toBe(false);
});

// ── applySnoozeFilter ─────────────────────────────────────────────────

test("applySnoozeFilter removes snoozed entries", () => {
  const entries = [
    { kind: "decision", title: "A", target: "review:foo" },
    { kind: "decision", title: "B", target: "review:bar" },
  ];
  const summary = {
    today_snooze: {
      items: [{ target: "review:foo", snoozed_until: "2026-05-04T00:00:00Z" }],
    },
  };
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  expect(filtered).toHaveLength(1);
  expect(filtered[0].title).toBe("B");
});

test("applySnoozeFilter keeps entries with expired snooze", () => {
  const entries = [
    { kind: "decision", title: "A", target: "review:foo" },
  ];
  const summary = {
    today_snooze: {
      items: [{ target: "review:foo", snoozed_until: "2026-05-01T00:00:00Z" }],
    },
  };
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  expect(filtered).toHaveLength(1);
});

test("applySnoozeFilter returns all entries when no snooze state", () => {
  const entries = [{ kind: "report", title: "A", target: "output/reports/A.md" }];
  const filtered = applySnoozeFilter(entries, {}, "2026-05-03");
  expect(filtered).toHaveLength(1);
});

// ── buildTodayFeed ────────────────────────────────────────────────────

test("buildTodayFeed returns empty for null/undefined", () => {
  expect(buildTodayFeed(null)).toEqual([]);
  expect(buildTodayFeed(undefined)).toEqual([]);
  expect(buildTodayFeed("not-object")).toEqual([]);
});

test("buildTodayFeed returns empty for empty summary", () => {
  const feed = buildTodayFeed(makeSummary());
  expect(feed).toEqual([]);
});

test("buildTodayFeed surfaces decision entries from review_backlog_counts", () => {
  const summary = makeSummary({
    review_backlog_counts: {
      counter_evidence_candidates: 3,
      escalated_actions: 1,
      escalation_candidates: 1,
      judgment_review_actions: 1,
      pending_decisions: 1,
      pending_judgments: 1,
      // Routine/low-level buckets should be filtered out
      overdue_actions: 2,
      overdue_reviews: 2,
      ready_actions: 2,
      machine_memory_actions: 5,
    },
  });
  const feed = buildTodayFeed(summary);
  const decisions = feed.filter((e) => e.kind === "decision");
  expect(decisions).toHaveLength(6);
  expect(decisions.every((entry) => entry.priority === PRIORITY.decision)).toBe(true);
  expect(decisions.map((entry) => entry.target)).toEqual([
    "review:counter_evidence_candidates",
    "review:escalated_actions",
    "review:escalation_candidates",
    "review:judgment_review_actions",
    "review:pending_decisions",
    "review:pending_judgments",
  ]);
});

test("buildTodayFeed surfaces counter evidence entries", () => {
  const summary = makeSummary({
    counter_evidence_pages: [
      { path: "wiki/judgments/nvda.md", subject: "NVDA Thesis", summary: "3 new sources found", Detected_at: "2026-05-03T08:00:00Z", protocol: "investing" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const entries = feed.filter((e) => e.title.includes("反证"));
  expect(entries).toHaveLength(1);
  expect(entries[0].kind).toBe("decision");
  expect(entries[0].target).toBe("wiki/judgments/nvda.md");
});

test("buildTodayFeed surfaces drift warnings", () => {
  const summary = makeSummary({
    drift_warnings: [
      { kind: "judgment-stale", path: "wiki/judgments/old.md", message: "证据已过时", Detected_at: "2026-05-03T08:00:00Z" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const drifts = feed.filter((e) => e.title.includes("漂移"));
  expect(drifts).toHaveLength(1);
});

test("buildTodayFeed surfaces today reports only", () => {
  const summary = makeSummary({
    recent_outputs: [
      { path: "output/reports/today.md", title: "Today Report", generated_at: "2026-05-03T08:00:00Z", format: "report" },
      { path: "output/reports/old.md", title: "Old Report", generated_at: "2026-05-01T08:00:00Z", format: "report" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const reports = feed.filter((e) => e.kind === "report");
  expect(reports).toHaveLength(1);
  expect(reports[0].title).toBe("Today Report");
});

test("buildTodayFeed renders user-facing raw input source labels", () => {
  const summary = makeSummary({
    recent_raw_inputs: [
      {
        stored_path: "raw/inbox/readme.md",
        title: "README.md",
        source_type: "note-drop",
        occurred_at: "2026-05-03T08:00:00Z",
      },
    ],
  });

  const feed = buildTodayFeed(summary);
  const rawInputs = feed.filter((e) => e.target === "raw/inbox/readme.md");

  expect(rawInputs).toHaveLength(1);
  expect(rawInputs[0].summary).toBe("已接收 文本材料，等待编译/刷新");
  expect(rawInputs[0].summary).not.toContain("note-drop");
});

test("buildTodayFeed hides degraded and placeholder reports", () => {
  const summary = makeSummary({
    recent_outputs: [
      { path: "output/reports/final.md", title: "Final", generated_at: "2026-05-03T08:00:00Z", format: "report" },
      { path: "output/reports/degraded.md", title: "LLM 未完成：Q", generated_at: "2026-05-03T08:00:00Z", format: "report", delivery_mode: "deterministic-fallback", llm_status: "timeout_or_unavailable" },
      { path: "output/reports/literal-degraded.md", title: "Literal degraded", generated_at: "2026-05-03T08:00:00Z", format: "report", llm_status: "degraded" },
      { path: "output/reports/placeholder.md", title: "Template", generated_at: "2026-05-03T08:00:00Z", format: "report", artifact_quality: "placeholder", contains_llm_placeholder: "true" },
      { path: "output/reports/pending.md", title: "Pending", generated_at: "2026-05-03T08:00:00Z", format: "report", background_status: "running" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const reports = feed.filter((e) => e.kind === "report");
  expect(reports.map((entry) => entry.target)).toEqual(["output/reports/final.md"]);
});

test("buildTodayFeed surfaces elixir entries for today", () => {
  const summary = makeSummary({
    recent_receipts: [
      { title: "Elixir NVDA settled", operation: "promote-elixir", subject_kind: "elixir", subject_id: "nvda", receipt_path: "output/control/execution-receipts/X.json", applied_at: "2026-05-03T08:00:00Z" },
      { title: "Old receipt", operation: "compile", subject_kind: "source", subject_id: "src1", receipt_path: "output/control/execution-receipts/Y.json", applied_at: "2026-05-01T08:00:00Z" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const elixirs = feed.filter((e) => e.kind === "elixir");
  expect(elixirs).toHaveLength(1);
  expect(elixirs[0].title).toBe("Elixir NVDA settled");
});

test("buildTodayFeed keeps agent loop automation out of primary Today", () => {
  const summary = makeSummary({
    nightly: {
      generated_at: "2026-05-03T12:00:00Z",
      agent_loop: {
        generated_at: "2026-05-03T12:00:00Z",
        status: "ok",
        signals: { new_count: 3 },
        planner: { execute: { new_count: 2 } },
        auto_preview: { ready_count: 0 },
        auto_apply: { applied_count: 2 },
      },
    },
  });
  const feed = buildTodayFeed(summary);
  const automations = feed.filter((e) => e.kind === "automation");
  expect(automations).toHaveLength(0);
});

test("buildTodayFeed keeps degraded LLM health out of primary Today", () => {
  const summary = makeSummary({
    llm_health: {
      status: "degraded",
      reason: "probe timeout",
      checked_at: "2026-05-03T11:00:00Z",
      rerun_command: "aiwiki llm-check",
    },
  });

  const feed = buildTodayFeed(summary);

  expect(feed).toHaveLength(0);
});

test("buildTodayFeed surfaces proposal entries needing attention", () => {
  const summary = makeSummary({
    review_controls: {
      l3_proposals: [
        { proposal_id: "p1", title: "Improve prompt X", target_file: "prompts/ask.md", needs_attention: true, state: "pending", kind: "prompt", updated_at: "2026-05-03T08:00:00Z", protocol: "research" },
        { proposal_id: "p2", title: "Improve prompt Y", target_file: "prompts/compile.md", needs_attention: false, state: "stale", kind: "prompt", updated_at: "2026-05-01T08:00:00Z" },
      ],
    },
  });
  const feed = buildTodayFeed(summary);
  const proposals = feed.filter((e) => e.kind === "proposal");
  expect(proposals).toHaveLength(1);
  expect(proposals[0].title).toBe("Improve prompt X");
});

test("buildTodayFeed filters out maintenance commands from primary feed", () => {
  const summary = makeSummary({
    suggested_next_actions: [
      { title: "Run compile", command: " review-page wiki/judgments/X.md ", reason: "batch-hint:judgment", protocol: "research" },
      { title: "Ask anything", command: " PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask ", reason: "query", protocol: "research" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const actions = feed.filter((e) => e.kind === "action");
  expect(actions).toHaveLength(1);
  expect(actions[0].title).toBe("Ask anything");
});

test("buildTodayFeed sorts entries correctly: report > decision > proposal > elixir > action", () => {
  const summary = makeSummary({
    review_backlog_counts: { counter_evidence_candidates: 1 },
    recent_outputs: [
      { path: "output/reports/R.md", title: "R", generated_at: "2026-05-03T08:00:00Z", format: "report" },
    ],
    suggested_next_actions: [
      { title: "Act", command: " PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask --ask ", reason: "query", protocol: "research" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const kinds = feed.map((e) => e.kind);
  const reportIdx = kinds.indexOf("report");
  const decisionIdx = kinds.indexOf("decision");
  const actionIdx = kinds.indexOf("action");
  expect(reportIdx).toBeLessThan(decisionIdx);
  expect(decisionIdx).toBeLessThan(actionIdx);
});

test("buildTodayFeed keeps metric trend alerts out of primary Today", () => {
  const summary = makeSummary({
    metrics_history_delta: {
      available: true,
      window: "7d",
      baseline_ts: "2026-04-26T00:00:00Z",
      alerts: [
        { metric_key: "provenance_completeness", direction: "down", diff: -0.15 },
      ],
    },
  });
  const feed = buildTodayFeed(summary);
  const metrics = feed.filter((e) => e.title.startsWith("指标变化"));
  expect(metrics).toHaveLength(0);
});
