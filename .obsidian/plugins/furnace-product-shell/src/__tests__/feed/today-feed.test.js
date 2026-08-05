"use strict";

const {
  buildTodayFeed,
  compareEntries,
  todayDateOf,
  priorityForKind,
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
    recent_outputs: [],
    recent_receipts: [],
    suggested_next_actions: [],
    metrics_history_delta: { available: false },
    ...overrides,
  };
}

// ── PRIORITY ──────────────────────────────────────────────────────────

test("PRIORITY defines correct ordering", () => {
  // Behavior pin; values are cross-checked against schema kind_priority in the schema contract block below.
  expect(PRIORITY.report).toBe(1);
  expect(PRIORITY.automation).toBe(2);
  expect(PRIORITY.decision).toBe(3);
  expect(PRIORITY.elixir).toBe(4);
  expect(PRIORITY.action).toBe(5);
  expect(Object.keys(PRIORITY)).toHaveLength(5);
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

test("compareEntries same priority sorts by timestamp ascending", () => {
  const a = { kind: "report", timestamp: "2026-05-01" };
  const b = { kind: "report", timestamp: "2026-05-03" };
  // older (A) should come before newer (B) — newest sits near composer
  expect(compareEntries(a, b)).toBeLessThan(0);
  expect(compareEntries(b, a)).toBeGreaterThan(0);
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

test("buildTodayFeed keeps governance backlog out of primary feed", () => {
  const summary = makeSummary({
    review_backlog_counts: {
      counter_evidence_candidates: 3,
      escalated_actions: 1,
      escalation_candidates: 1,
      judgment_review_actions: 1,
      pending_decisions: 1,
      pending_judgments: 1,
      overdue_actions: 2,
      overdue_reviews: 2,
      ready_actions: 2,
      machine_memory_actions: 5,
    },
  });
  const feed = buildTodayFeed(summary);
  expect(feed.filter((e) => e.kind === "decision")).toHaveLength(0);
});

test("buildTodayFeed keeps counter evidence out of primary feed", () => {
  const summary = makeSummary({
    counter_evidence_pages: [
      { path: "wiki/judgments/nvda.md", subject: "NVDA Thesis", summary: "3 new sources found", Detected_at: "2026-05-03T08:00:00Z", protocol: "investing" },
    ],
  });
  const feed = buildTodayFeed(summary);
  expect(feed.filter((e) => e.title.includes("反证"))).toHaveLength(0);
});

test("buildTodayFeed keeps drift warnings out of primary feed", () => {
  const summary = makeSummary({
    drift_warnings: [
      { kind: "judgment-stale", path: "wiki/judgments/old.md", message: "证据已过时", Detected_at: "2026-05-03T08:00:00Z" },
    ],
  });
  const feed = buildTodayFeed(summary);
  expect(feed.filter((e) => e.title.includes("漂移"))).toHaveLength(0);
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

test("buildTodayFeed keeps raw input drops out of primary feed", () => {
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
  expect(feed.filter((e) => e.target === "raw/inbox/readme.md")).toHaveLength(0);
});

test("buildTodayFeed hides degraded and placeholder reports", () => {
  const summary = makeSummary({
    recent_outputs: [
      { path: "output/reports/final.md", title: "Final", generated_at: "2026-05-03T08:00:00Z", format: "report" },
      { path: "output/reports/degraded.md", title: "LLM 未完成：Q", generated_at: "2026-05-03T08:00:00Z", format: "report", delivery_mode: "deterministic-fallback", llm_status: "timeout_or_unavailable" },
      { path: "output/reports/literal-degraded.md", title: "Literal degraded", generated_at: "2026-05-03T08:00:00Z", format: "report", llm_status: "degraded" },
      { path: "output/reports/placeholder.md", title: "Template", generated_at: "2026-05-03T08:00:00Z", format: "report", artifact_quality: "placeholder", contains_llm_placeholder: "true" },
    ],
  });
  const feed = buildTodayFeed(summary);
  const reports = feed.filter((e) => e.kind === "report");
  expect(reports.map((entry) => entry.target)).toEqual(["output/reports/final.md"]);
});

test("buildTodayFeed keeps elixir receipts out of primary feed", () => {
  const summary = makeSummary({
    recent_receipts: [
      { title: "Elixir NVDA settled", operation: "promote-elixir", subject_kind: "elixir", subject_id: "nvda", receipt_path: ".aiwiki/state/execution-receipts/X.json", applied_at: "2026-05-03T08:00:00Z" },
      { title: "Old receipt", operation: "compile", subject_kind: "source", subject_id: "src1", receipt_path: ".aiwiki/state/execution-receipts/Y.json", applied_at: "2026-05-01T08:00:00Z" },
    ],
  });
  const feed = buildTodayFeed(summary);
  expect(feed.filter((e) => e.kind === "elixir")).toHaveLength(0);
});

test("buildTodayFeed keeps standalone compound suggest actions out of primary feed", () => {
  const summary = makeSummary({
    compound_suggest: {
      available: true,
      count: 1,
      items: [
        {
          report_path: "output/reports/today.md",
          title: "沉淀：Today question",
          action: "file-back-judgment",
          reason: "multi-turn-same-corpus,links-confirmed-judgment",
          signal: "extend",
          protocol: "research",
        },
      ],
    },
    suggested_next_actions: [
      {
        kind: "compound-suggest",
        title: "沉淀：Today question",
        command: "PYTHONPATH=src python3 -m aiwiki.cli --root . file-back output/reports/today.md",
        path: "output/reports/today.md",
        reason: "multi-turn-same-corpus",
        action: "file-back-judgment",
      },
    ],
  });

  const feed = buildTodayFeed(summary);
  const compoundActions = feed.filter((entry) => entry.kind === "action" && entry.compound_suggest);
  expect(compoundActions).toHaveLength(0);
});

test("buildTodayFeed attaches compound suggest to today report entries", () => {
  const summary = makeSummary({
    compound_suggest: {
      available: true,
      count: 1,
      items: [
        {
          report_path: "output/reports/today.md",
          title: "凝丹：衔接旧丹",
          action: "alchemy-start",
          corpus_id: "corpus-a",
          topic: "Follow-up question",
          reason: "extend",
        },
      ],
    },
    recent_outputs: [
      { path: "output/reports/today.md", title: "Today Report", generated_at: "2026-05-03T08:00:00Z", format: "report" },
    ],
  });

  const feed = buildTodayFeed(summary);
  const reports = feed.filter((entry) => entry.kind === "report");
  expect(reports).toHaveLength(1);
  expect(reports[0].compound_suggest).toMatchObject({
    action: "alchemy-start",
    corpus_id: "corpus-a",
  });
});

test("buildTodayFeed keeps nightly automation out of primary Today", () => {
  const summary = makeSummary({
    nightly: {
      generated_at: "2026-05-03T12:00:00Z",
      lint_counts: { errors: 1 },
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

test("buildTodayFeed keeps generic suggested actions out of primary feed", () => {
  const summary = makeSummary({
    suggested_next_actions: [
      { title: "Run compile", command: " review-page wiki/judgments/X.md ", reason: "batch-hint:judgment", protocol: "research" },
      { title: "Ask anything", command: " PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask ", reason: "query", protocol: "research" },
    ],
  });
  const feed = buildTodayFeed(summary);
  expect(feed.filter((e) => e.kind === "action")).toHaveLength(0);
});

test("buildTodayFeed keeps reports when compound suggest exists without standalone action rows", () => {
  const summary = makeSummary({
    compound_suggest: {
      available: true,
      count: 1,
      items: [
        {
          report_path: "output/reports/R.md",
          title: "沉淀：R",
          action: "file-back-judgment",
          reason: "extend",
        },
      ],
    },
    recent_outputs: [
      { path: "output/reports/R.md", title: "R", generated_at: "2026-05-03T08:00:00Z", format: "report" },
    ],
  });
  const feed = buildTodayFeed(summary);
  expect(feed.map((e) => e.kind)).toEqual(["report"]);
  expect(feed[0].compound_suggest).toMatchObject({ action: "file-back-judgment" });
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

// ── schema/today-feed.json contract ─────────────────────────────────

const fs = require("fs");
const path = require("path");

const TODAY_FEED_SCHEMA = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../../../../../../schema/today-feed.json"), "utf8")
);

describe("today-feed schema contract (schema/today-feed.json)", () => {
  test("PRIORITY keys match schema kind enum exactly", () => {
    expect([...TODAY_FEED_SCHEMA.properties.kind.enum].sort()).toEqual(Object.keys(PRIORITY).sort());
    // kind_priority values are the shared ordering SoT (Python side pinned in tests/test_llm_integration.py).
    expect(PRIORITY).toEqual(TODAY_FEED_SCHEMA.kind_priority);
  });

  test("buildTodayFeed entries conform to schema", () => {
    const summary = makeSummary({
      recent_outputs: [
        {
          path: "output/reports/2026-05-03-report.md",
          title: "报告 A",
          format: "report",
          generated_at: "2026-05-03T10:00:00Z",
        },
      ],
    });
    const entries = buildTodayFeed(summary);
    expect(entries.length).toBeGreaterThan(0);
    for (const entry of entries) {
      for (const key of TODAY_FEED_SCHEMA.required) {
        expect(entry).toHaveProperty(key);
      }
      expect(TODAY_FEED_SCHEMA.properties.kind.enum).toContain(entry.kind);
      expect(typeof entry.title).toBe("string");
      expect(typeof entry.summary).toBe("string");
      expect(typeof entry.target).toBe("string");
      expect(typeof entry.timestamp).toBe("string");
      expect(Number.isInteger(entry.priority)).toBe(true);
      expect(entry.priority).toBeGreaterThanOrEqual(TODAY_FEED_SCHEMA.properties.priority.minimum);
      expect(entry.priority).toBeLessThanOrEqual(TODAY_FEED_SCHEMA.properties.priority.maximum);
      expect(entry.priority).toBe(priorityForKind(entry.kind));
      expect(typeof entry.protocol).toBe("string");
    }
  });
});
