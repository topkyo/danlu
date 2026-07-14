"use strict";

const { applySnoozeFilter } = require("../../today_feed");

// ── applySnoozeFilter ─────────────────────────────────────────────────

test("filters entries whose target matches active snooze", () => {
  const entries = [
    { kind: "decision", title: "Review judgment", target: "review:counter_evidence_candidates" },
    { kind: "decision", title: "Check drift", target: "review:drift" },
  ];
  const summary = {
    today_snooze: {
      items: [
        { target: "review:counter_evidence_candidates", snoozed_until: "2026-05-10T00:00:00Z" },
      ],
    },
  };
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  expect(filtered).toHaveLength(1);
  expect(filtered[0].title).toBe("Check drift");
});

test("does not filter when snoozed_until is before today", () => {
  const entries = [
    { kind: "decision", title: "Review", target: "review:old" },
  ];
  const summary = {
    today_snooze: {
      items: [
        { target: "review:old", snoozed_until: "2026-04-30T00:00:00Z" },
      ],
    },
  };
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  expect(filtered).toHaveLength(1);
});

test("does not filter when snoozed_until is exactly today", () => {
  const entries = [
    { kind: "decision", title: "Review", target: "review:foo" },
  ];
  const summary = {
    today_snooze: {
      items: [
        { target: "review:foo", snoozed_until: "2026-05-03T00:00:00Z" },
      ],
    },
  };
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  // snoozed_until >= today, so it should be filtered
  expect(filtered).toHaveLength(0);
});

test("returns all entries when snooze state is missing", () => {
  const entries = [
    { kind: "report", title: "A", target: "output/A.md" },
    { kind: "report", title: "B", target: "output/B.md" },
  ];
  expect(applySnoozeFilter(entries, {}, "2026-05-03")).toHaveLength(2);
  expect(applySnoozeFilter(entries, { today_snooze: null }, "2026-05-03")).toHaveLength(2);
  expect(applySnoozeFilter(entries, { today_snooze: {} }, "2026-05-03")).toHaveLength(2);
  expect(applySnoozeFilter(entries, { today_snooze: { items: [] } }, "2026-05-03")).toHaveLength(2);
});

test("returns all entries when no active snoozes match today", () => {
  const entries = [
    { kind: "decision", title: "X", target: "review:x" },
  ];
  const summary = {
    today_snooze: {
      items: [
        { target: "review:y", snoozed_until: "2026-05-10T00:00:00Z" },
      ],
    },
  };
  expect(applySnoozeFilter(entries, summary, "2026-05-03")).toHaveLength(1);
});

test("handles malformed snooze items gracefully", () => {
  const entries = [
    { kind: "decision", title: "A", target: "review:a" },
  ];
  const summary = {
    today_snooze: {
      items: [
        null,
        { target: "", snoozed_until: "2026-05-10T00:00:00Z" },
        { target: "review:a", snoozed_until: "" },
        {},
        "not-an-object",
      ],
    },
  };
  // None should match due to empty target or until
  const filtered = applySnoozeFilter(entries, summary, "2026-05-03");
  expect(filtered).toHaveLength(1);
});
