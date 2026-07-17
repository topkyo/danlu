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
  expect(record.logPath).toBe("");
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
      rewriteFollowupActions: [
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
  expect(runs[0].rewriteFollowupActions).toHaveLength(1);
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
      backend_effective: "opencode-api",
      model_selected: "deepseek-v4-pro",
      model_final: "deepseek-v4-pro",
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
    rewriteFollowupActions: [{ slug: "concept-a", command: "review-rewrite" }],
    rewriteProposalPaths: ["output/_proposals/rewrite/concept-a.md"],
    rewriteProposalSlugs: ["concept-a"],
  });

  expect(updates).toMatchObject({
    status: "degraded",
    exitCode: 0,
    backend: "opencode-api",
    backendRequested: "opencode-api",
    backendEffective: "opencode-api",
    model: "deepseek-v4-pro",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "deepseek-v4-pro",
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

test("run state helpers build command result context from payload artifacts", () => {
  const context = loadRunStateContext();

  const fromObjects = context.buildProductShellRunResultContext({
    payload: {
      path: "output/reports/a.md",
      receipt_path: "output/control/receipt.json",
      updated_rewrite_proposals: [
        {
          slug: "concept-a",
          proposal_path: "wiki/rewrite-proposals/concept-a.md",
          target_path: "wiki/concepts/concept-a.md",
        },
      ],
      rewrite_followup_actions: [{ slug: "concept-a", command: "review-rewrite concept-a --status accepted" }],
    },
  });

  expect(fromObjects).toMatchObject({
    primaryPath: "output/reports/a.md",
    receiptPath: "output/control/receipt.json",
    rewriteProposalPaths: ["wiki/rewrite-proposals/concept-a.md"],
    rewriteProposalSlugs: ["concept-a"],
  });
  expect(fromObjects.rewriteProposalObjects).toHaveLength(1);
  expect(fromObjects.rewriteFollowupActions).toHaveLength(1);

  const fromPaths = context.buildProductShellRunResultContext({
    payload: {
      output_path: "output/reports/b.md",
      updated_rewrite_proposal_pages: ["wiki/rewrite-proposals/concept-b.md"],
    },
  });

  expect(fromPaths).toMatchObject({
    primaryPath: "output/reports/b.md",
    receiptPath: "",
    rewriteProposalObjects: [],
    rewriteFollowupActions: [],
    rewriteProposalPaths: ["wiki/rewrite-proposals/concept-b.md"],
    rewriteProposalSlugs: ["concept-b"],
  });
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

test("run state helpers build failed run state with optional llm health", () => {
  const context = loadRunStateContext();
  const askRecord = {
    command: "run-ask",
    backendRequested: "opencode-api",
    backendEffective: "opencode-api",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "deepseek-v4-pro",
    fallbackStage: "",
    fallbackReason: "",
    contractValidated: false,
  };
  const error = {
    code: "2",
    message: "LLM backend timeout",
    stdout: "out",
    stderr: "backend unavailable",
  };

  const state = context.buildProductShellFailedRunState({
    record: askRecord,
    error,
    noticeMessage: "Ask failed",
  });

  expect(state.events).toEqual([
    { stage: "Failed", summary: "LLM backend timeout", status: "failed" },
  ]);
  expect(state.updates).toMatchObject({
    status: "failed",
    exitCode: 2,
    stdoutRaw: "out",
    stderrRaw: "backend unavailable",
    errorSummary: "LLM backend timeout",
  });
  expect(state.llmHealthOverrides).toMatchObject({
    status: "degraded",
    source: "run-ask",
    fallbackCommand: "ask",
    stderrRaw: "backend unavailable",
  });
  expect(state.logDetails).toEqual({ stdoutRaw: "out", stderrRaw: "backend unavailable" });
  expect(state.noticeMessage).toBe("Ask failed");

  const nonAsk = context.buildProductShellFailedRunState({
    record: { command: "compile" },
    error,
  });
  expect(nonAsk.llmHealthOverrides).toBeNull();
});

test("run state helpers build completion timeline events", () => {
  const context = loadRunStateContext();

  expect(context.buildProductShellCompletionRunEvents({
    degradedRun: true,
    primaryPath: "output/reports/a.md",
    receiptPath: "output/receipts/a.json",
    rewriteProposalPaths: ["output/_proposals/rewrite/concept-a.md"],
    rewriteProposalSummary: "1 rewrite proposal",
    fallbackSummary: "timeout",
    successSummary: "output/reports/a.md",
  })).toEqual([
    { stage: "LLM timeout", summary: "timeout", status: "degraded" },
    { stage: "Artifacts", summary: "output/reports/a.md · output/receipts/a.json", status: "success" },
    { stage: "Rewrite proposals", summary: "1 rewrite proposal", status: "success" },
  ]);

  expect(context.buildProductShellCompletionRunEvents({
    degradedRun: false,
    primaryPath: "",
    receiptPath: "",
    successSummary: "Command completed successfully.",
  })).toEqual([
    { stage: "Completed", summary: "Command completed successfully.", status: "success" },
  ]);
});

test("run state helpers build completed run state including health and notice", () => {
  const context = loadRunStateContext();
  const record = context.createProductShellRunRecord({
    label: "Ask: hello",
    args: ["run-ask", "hello"],
    llm: { backend: "opencode-api", model: "deepseek-v4-pro" },
    protocol: "product",
  });
  const result = {
    payload: {
      path: "output/reports/a.md",
      receipt_path: "output/receipts/a.json",
      fallback_used: true,
      delivery_mode: "deterministic-fallback",
      backend_requested: "opencode-api",
      backend_effective: "opencode-api",
      model_selected: "deepseek-v4-pro",
      model_final: "deepseek-v4-pro",
      fallback_stage: "primary",
      fallback_reason: "timeout",
      fallback_command: "ask",
    },
    stdout: "ok",
    stderr: "",
  };

  const state = context.buildProductShellCompletedRunState({
    record,
    result,
    llm: { backend: "opencode-api", model: "deepseek-v4-pro" },
    rewriteProposalSummary: "",
    fallbackSummary: "timeout",
    successSummary: "output/reports/a.md",
    degradedNotice: "degraded notice",
    successNotice: "success notice",
  });

  expect(state.degradedRun).toBe(true);
  expect(state.events[0]).toEqual({ stage: "LLM timeout", summary: "timeout", status: "degraded" });
  expect(state.updates).toMatchObject({
    status: "degraded",
    resultPath: "output/reports/a.md",
    receiptPath: "output/receipts/a.json",
    backendEffective: "opencode-api",
    modelFinal: "deepseek-v4-pro",
    fallbackUsed: true,
  });
  expect(state.llmHealthOverrides).toMatchObject({
    status: "degraded",
    fallbackCommand: "ask",
    backendEffective: "opencode-api",
    modelFinal: "deepseek-v4-pro",
  });
  expect(state.noticeMessage).toBe("degraded notice");

  const nonAsk = context.buildProductShellCompletedRunState({
    record: { ...record, command: "compile" },
    result: { payload: {}, stdout: "", stderr: "" },
    llm: {},
    successNotice: "compiled",
  });
  expect(nonAsk.llmHealthOverrides).toBeNull();
  expect(nonAsk.noticeMessage).toBe("compiled");
});

test("run state helpers build llm health overrides", () => {
  const context = loadRunStateContext();
  const record = {
    backendRequested: "opencode-api",
    backendEffective: "opencode-api",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "deepseek-v4-pro",
    fallbackStage: "primary",
    fallbackReason: "timeout",
    fallbackCommand: "ask",
    fallbackUsed: true,
    deliveryMode: "deterministic-fallback",
    contractValidated: true,
  };

  expect(context.buildProductShellLlmHealthOverrides(record)).toMatchObject({
    status: "degraded",
    reason: "Latest run-ask produced an LLM failure notice.",
    source: "run-ask",
    fallbackCommand: "ask",
    backendRequested: "opencode-api",
    backendEffective: "opencode-api",
    modelSelected: "deepseek-v4-pro",
    modelFinal: "deepseek-v4-pro",
    fallbackStage: "primary",
    fallbackReason: "timeout",
    contractValidated: true,
  });
  expect(context.buildProductShellLlmHealthOverrides({ deliveryMode: "" })).toMatchObject({
    status: "healthy",
    reason: "Recent run-ask succeeded.",
    fallbackCommand: "",
  });
  expect(context.buildProductShellLlmHealthOverrides({
    command: "run-ask",
    fallbackUsed: true,
    deliveryMode: "llm-fallback-chain",
    fallbackStage: "model-chain",
    fallbackCommand: "",
  })).toMatchObject({
    status: "warning",
    reason: "LLM completed via model retry.",
    fallbackCommand: "",
  });
  expect(context.isProductShellDegradedRun({ command: "run-ask" }, {
    fallback_used: true,
    delivery_mode: "llm-fallback-chain",
  })).toBe(false);
  expect(context.isProductShellDegradedRun({ command: "run-ask" }, {
    fallback_used: true,
    delivery_mode: "deterministic-fallback",
  })).toBe(true);
  expect(context.buildProductShellFailedLlmHealthOverrides(record, {
    message: "Backend unavailable",
    stderr: "stderr detail",
  })).toMatchObject({
    status: "degraded",
    reason: "Backend unavailable",
    source: "run-ask",
    fallbackCommand: "ask",
    stderrSummary: "stderr detail",
    stderrRaw: "stderr detail",
  });
});
