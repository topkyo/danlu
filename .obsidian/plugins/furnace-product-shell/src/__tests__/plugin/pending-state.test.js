"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadPendingStateContext() {
  const context = {
    console,
    require,
    fs,
    path,
    Date,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    Set,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../pending_state.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "pending_state.js" });
  return context;
}

test("pending entry creation and persistence keep degradation metadata", () => {
  const context = loadPendingStateContext();
  const entry = context.createPendingSubmissionEntry({
    id: "pending-1",
    displayText: "x".repeat(130),
    startedAt: "2026-05-25T00:00:00Z",
    opts: {
      title: "Ask",
      deliveryMode: "deterministic-fallback",
      backgroundStatus: "degraded",
      artifactQuality: "degraded",
      retryArgs: { longRunning: true },
    },
  });

  expect(entry.payloadFingerprint).toBe("x".repeat(80));
  expect(entry.displayText).toBe(`${"x".repeat(117)}…`);
  expect(entry).toMatchObject({
    id: "pending-1",
    title: "Ask",
    status: "running",
    deliveryMode: "deterministic-fallback",
    backgroundStatus: "degraded",
    artifactQuality: "degraded",
  });
  expect(context.isPendingSubmissionDegradedEntry(entry)).toBe(true);

  const serialized = context.serializePendingSubmissionList([entry])[0];
  expect(serialized.backgroundStatus).toBe("degraded");
  expect(serialized.artifactQuality).toBe("degraded");
  const hydrated = context.hydratePendingSubmissionList([serialized], Date.parse("2026-05-25T00:01:00Z"))[0];
  expect(hydrated.backgroundStatus).toBe("degraded");
  expect(hydrated.artifactQuality).toBe("degraded");
});

test("pending entry transitions preserve terminal and retry contracts", () => {
  const context = loadPendingStateContext();
  const entry = context.createPendingSubmissionEntry({
    id: "pending-1",
    displayText: "Run report",
    startedAt: "2026-05-25T00:00:00Z",
    opts: { retryArgs: { jobId: "job-1", runId: "run-1", runNotesPath: "notes.md", longRunning: true } },
  });

  expect(context.markPendingSubmissionEntryReceived(entry, "2026-05-25T00:00:01Z")).toBe(true);
  expect(entry.status).toBe("received");
  expect(context.markPendingSubmissionEntryDone(entry, "outputs", "output/reports/a.md", "2026-05-25T00:00:02Z")).toBe(true);
  expect(entry).toMatchObject({
    status: "done",
    reconcileTarget: "outputs",
    reconcilePath: "output/reports/a.md",
  });
  expect(context.markPendingSubmissionEntryDone(entry, "receipts", "receipt.json", "2026-05-25T00:00:03Z")).toBe(false);
  expect(entry.reconcileTarget).toBe("outputs");

  expect(context.resetPendingSubmissionEntryForRetry(entry, "2026-05-25T00:01:00Z")).toBe(true);
  expect(entry).toMatchObject({
    status: "running",
    error: "",
    jobId: "",
    runId: "",
    runNotesPath: "",
    deliveryMode: "",
    llmStatus: "",
    backgroundStatus: "",
    artifactQuality: "",
    _stale: false,
  });
  expect(entry.retryArgs).toMatchObject({ jobId: "", runId: "", runNotesPath: "", longRunning: true });
});

test("pending artifact metadata updates camel and snake case fields", () => {
  const context = loadPendingStateContext();
  const entry = context.createPendingSubmissionEntry({
    id: "pending-1",
    displayText: "Run report",
    startedAt: "2026-05-25T00:00:00Z",
  });

  expect(context.updatePendingSubmissionEntryArtifactMeta(entry, {
    run_notes_path: "output/control/runs/run-1/thinking.md",
    run_id: "run-1",
    delivery_mode: "llm-failed",
    llm_status: "failed",
    llm_backend: "opencode-api",
    llm_model: "deepseek-v4-pro",
    background_status: "degraded",
    artifact_quality: "degraded",
  })).toBe(true);

  expect(entry).toMatchObject({
    runNotesPath: "output/control/runs/run-1/thinking.md",
    runId: "run-1",
    deliveryMode: "llm-failed",
    llmStatus: "failed",
    llmBackend: "opencode-api",
    llmModel: "deepseek-v4-pro",
    backgroundStatus: "degraded",
    artifactQuality: "degraded",
  });
  expect(context.isPendingSubmissionDegradedEntry(entry)).toBe(true);
});
