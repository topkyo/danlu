"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadRunStateContext() {
  const context = {
    console,
    require,
    fs,
    path,
    Date,
    Math,
    Intl,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    RegExp,
    Set,
    Map,
  };
  [
    "constants.js",
    "helpers.js",
    "plugin_helpers.js",
    "rewrite_state.js",
    "run_state.js",
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

const t = (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? ""));

test("createProductShellRunRecord initializes command context and timeline", () => {
  const context = loadRunStateContext();
  const record = context.createProductShellRunRecord({
    label: "Ask: hello",
    args: ["run-ask", "hello", "--format", "note"],
    llm: { backend: "opencode-api", model: "deepseek-v4-pro", codexReasoningEffort: "high" },
    protocol: "research",
  });

  expect(record.id).toMatch(/^run-\d+-[0-9a-f]+$/);
  expect(record).toMatchObject({
    label: "Ask: hello",
    args: "run-ask hello --format note",
    argv: ["run-ask", "hello", "--format", "note"],
    command: "run-ask",
    status: "running",
    protocol: "research",
    backend: "opencode-api",
    model: "deepseek-v4-pro",
    codexReasoningEffort: "high",
    exitCode: "",
    deliveryMode: "",
  });
  expect(record.logPath).toBe(`output/control/plugin-runs/${record.id}.md`);
  expect(record.timeline.map((event) => event.stage)).toEqual(["Submitted", "Runtime selected"]);
});

test("normalizeProductShellRecentRuns hydrates persisted run records", () => {
  const context = loadRunStateContext();
  const runs = context.normalizeProductShellRecentRuns([
    null,
    {
      argv: ["run-ask", 7],
      protocol: "product",
      backend: "opencode-api",
      model: "deepseek-v4-pro",
      updatedRewriteProposals: [
        {
          slug: "concept-a",
          title: "Concept A",
          proposal_path: "wiki/rewrite-proposals/concept-a.md",
          target_path: "wiki/concepts/concept-a.md",
        },
      ],
      rewriteRecoveryActions: [
        { slug: "concept-a", command: "review-rewrite concept-a --status accepted" },
        { slug: "concept-a", command: "review-rewrite concept-a --status accepted" },
      ],
      stdoutRaw: "ok",
      stderrRaw: "warn",
      exitCode: "0",
      timeline: [
        { stage: "Submitted", at: "2026-05-25T00:00:00Z", summary: "run-ask", status: "running" },
        "bad-event",
      ],
    },
  ]);

  expect(runs).toHaveLength(1);
  expect(runs[0]).toMatchObject({
    argv: ["run-ask", "7"],
    command: "run-ask",
    protocol: "product",
    backend: "opencode-api",
    model: "deepseek-v4-pro",
    rewriteProposalPaths: ["wiki/rewrite-proposals/concept-a.md"],
    rewriteProposalSlugs: ["concept-a"],
    stdoutRaw: "ok",
    stderrRaw: "warn",
    exitCode: 0,
  });
  expect(runs[0].rewriteProposalObjects).toHaveLength(1);
  expect(runs[0].rewriteRecoveryActions).toHaveLength(1);
  expect(runs[0].timeline).toEqual([
    { stage: "Submitted", at: "2026-05-25T00:00:00Z", summary: "run-ask", status: "running" },
  ]);
});

test("renderProductShellRunLog writes summary, proposals, and captured streams", () => {
  const context = loadRunStateContext();
  const record = {
    id: "run-1",
    status: "success",
    protocol: "research",
    backend: "opencode-api",
    backendRequested: "opencode-api",
    backendEffective: "opencode-api",
    model: "deepseek-v4-pro",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "deepseek-v4-pro",
    codexReasoningEffort: "high",
    args: "review-rewrite concept-a",
    resultPath: "output/reports/a.md",
    receiptPath: "output/receipts/a.json",
    exitCode: 0,
    startedAt: "2026-05-25T00:00:00Z",
    finishedAt: "2026-05-25T00:00:01Z",
    rewriteProposalObjects: [
      {
        slug: "concept-a",
        title: "Concept A",
        proposalPath: "output/_proposals/rewrite/concept-a.md",
      },
    ],
    timeline: [
      { at: "2026-05-25T00:00:00Z", stage: "Submitted", summary: "review-rewrite concept-a" },
      { at: "2026-05-25T00:00:01Z", stage: "Completed", summary: "output/reports/a.md" },
    ],
  };

  const rendered = context.renderProductShellRunLog({
    record,
    details: { stdoutRaw: "ok", stderrRaw: "warn" },
    t,
    repoRoot: "/vault",
  });

  expect(rendered.logPath).toBe("output/control/plugin-runs/run-1.md");
  expect(rendered.content).toContain("# Product Shell Run Log");
  expect(rendered.content).toContain("- Working directory: /vault");
  expect(rendered.content).toContain("- Result path: output/reports/a.md");
  expect(rendered.content).toContain("- rewrite proposals: 1");
  expect(rendered.content).toContain("  - Concept A: output/_proposals/rewrite/concept-a.md");
  expect(rendered.content).toContain("## Standard output");
  expect(rendered.content).toContain("ok");
  expect(rendered.content).toContain("## Standard error");
  expect(rendered.content).toContain("warn");
});

test("run state helpers classify degraded ask runs and build completed updates", () => {
  const context = loadRunStateContext();
  const record = context.createProductShellRunRecord({
    label: "Ask: hello",
    args: ["run-ask", "hello"],
    llm: { backend: "opencode-api", model: "deepseek-v4-pro", codexReasoningEffort: "medium" },
    protocol: "product",
  });
  const result = {
    payload: {
      fallback_used: true,
      delivery_mode: "deterministic-fallback",
      backend_requested: "opencode-api",
      backend_effective: "codex-cli",
      model_selected: "deepseek-v4-pro",
      model_final: "gpt-5.5",
      prompt_profile: "default",
      retry_prompt_profile: "fallback",
      fallback_stage: "primary",
      fallback_reason: "timeout",
      fallback_from: "run-ask",
      fallback_command: "ask",
      contract_validated: true,
    },
    stdout: "ok",
    stderr: "warn",
  };

  expect(context.isProductShellDegradedRun(record, result.payload)).toBe(true);
  const updates = context.buildProductShellCompletedRunUpdates({
    record,
    result,
    llm: { backend: "opencode-api", model: "deepseek-v4-pro", codexReasoningEffort: "high" },
    primaryPath: "output/reports/a.md",
    receiptPath: "output/receipts/a.json",
    rewriteProposalObjects: [{ slug: "concept-a" }],
    rewriteRecoveryActions: [{ slug: "concept-a", command: "review-rewrite" }],
    rewriteProposalPaths: ["output/_proposals/rewrite/concept-a.md"],
    rewriteProposalSlugs: ["concept-a"],
  });

  expect(updates).toMatchObject({
    status: "degraded",
    exitCode: 0,
    backend: "codex-cli",
    backendRequested: "opencode-api",
    backendEffective: "codex-cli",
    model: "gpt-5.5",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "gpt-5.5",
    codexReasoningEffort: "high",
    promptProfile: "default",
    retryPromptProfile: "fallback",
    fallbackStage: "primary",
    fallbackReason: "timeout",
    fallbackFrom: "run-ask",
    fallbackCommand: "ask",
    fallbackUsed: true,
    deliveryMode: "deterministic-fallback",
    contractValidated: true,
    resultPath: "output/reports/a.md",
    receiptPath: "output/receipts/a.json",
    rewriteProposalSlugs: ["concept-a"],
  });
  expect(updates.finishedAt).toBeTruthy();
});

test("run state helpers build background and failed updates", () => {
  const context = loadRunStateContext();

  const background = context.buildProductShellBackgroundRunUpdates({
    primaryPath: "output/reports/pending.md",
    result: {
      payload: {
        job_id: "job-1",
        run_id: "run-1",
        run_notes_path: "output/control/runs/run-1/thinking.md",
      },
      stdout: "submitted",
      stderr: "",
    },
  });
  expect(background).toMatchObject({
    status: "received",
    exitCode: 0,
    jobId: "job-1",
    runId: "run-1",
    runNotesPath: "output/control/runs/run-1/thinking.md",
    resultPath: "output/reports/pending.md",
    stdoutSummary: "submitted",
  });

  const failed = context.buildProductShellFailedRunUpdates({
    code: "7",
    message: "backend unavailable",
    stdout: "out",
    stderr: "err",
  });
  expect(failed).toMatchObject({
    status: "failed",
    exitCode: 7,
    stdoutSummary: "out",
    stderrSummary: "err",
    errorSummary: "backend unavailable",
  });
  expect(failed.finishedAt).toBeTruthy();
});
