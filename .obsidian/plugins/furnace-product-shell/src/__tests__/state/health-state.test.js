"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadHealthStateContext() {
  const context = {
    console,
    require,
    Date,
    Math,
    Number,
    String,
    Boolean,
    Object,
    module: { exports: {} },
    exports: {},
  };
  [
    "plugin_helpers.js",
    "state/health-state.js",
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

function makePlugin(context, options = {}) {
  const plugin = {
    shellSummary: options.shellSummary || null,
    settings: options.settings || { llmBackend: "opencode-api" },
    repoState: options.repoState || { valid: true, root: "/vault", missingPaths: [] },
    pluginState: {
      recentRuns: [],
      llmHealth: options.llmHealth || null,
    },
    t: jest.fn((text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? ""))),
    currentLlmSelection: jest.fn(() => options.selection || { backend: "opencode-api", model: "deepseek-v4-pro" }),
    updateStatusBar: jest.fn(),
    refreshOpenViews: jest.fn(),
    savePluginState: jest.fn(() => Promise.resolve()),
  };
  plugin.normalizeLlmHealthState = (value) => context.normalizeLlmHealthState(plugin, value);
  plugin.currentLlmHealth = () => context.currentLlmHealth(plugin);
  plugin.latestLlmRun = () => context.latestLlmRun(plugin);
  plugin.updateLlmHealth = (nextState) => context.updateLlmHealth(plugin, nextState);
  return plugin;
}

test("recordLlmHealthFromRun is visible before shell summary refresh", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    shellSummary: {
      generated_at: "2026-06-20T07:00:00Z",
      llm_status: { configured: true, backend: "opencode-api", model: "deepseek-v4-pro" },
      llm_health: {
        status: "healthy",
        reason: "Summary route is healthy.",
        checked_at: "2026-06-20T07:00:00Z",
      },
    },
  });

  context.recordLlmHealthFromRun(
    plugin,
    {
      command: "run-ask",
      backend: "opencode-api",
      model: "deepseek-v4-pro",
      finishedAt: "2026-06-20T08:00:00Z",
      resultPath: "output/reports/current.md",
    },
    {
      status: "warning",
      reason: "LLM completed via model retry (model-chain).",
      fallbackStage: "model-chain",
      fallbackCommand: "",
    }
  );

  expect(plugin.pluginState.llmHealth).toMatchObject({
    status: "warning",
    reason: "LLM completed via model retry (model-chain).",
    checkedAt: "2026-06-20T08:00:00Z",
    fallbackStage: "model-chain",
    fallbackCommand: "",
  });
  expect(plugin.updateStatusBar).toHaveBeenCalledTimes(1);
  expect(plugin.refreshOpenViews).toHaveBeenCalledTimes(1);
  expect(plugin.savePluginState).toHaveBeenCalledTimes(1);
  expect(context.currentLlmHealth(plugin)).toMatchObject({
    status: "warning",
    reason: "LLM completed via model retry (model-chain).",
    fallbackStage: "model-chain",
    backend: "opencode-api",
    model: "deepseek-v4-pro",
  });
});

test("recordLlmHealthFromRun preserves an explicit empty fallback command override", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context);

  context.recordLlmHealthFromRun(
    plugin,
    {
      command: "run-ask",
      backend: "opencode-api",
      model: "deepseek-v4-pro",
      finishedAt: "2026-06-20T08:00:00Z",
      fallbackCommand: "run-ask",
      fallbackFrom: "run-ask",
    },
    {
      status: "warning",
      reason: "LLM completed via model retry (model-chain).",
      fallbackCommand: "",
      fallbackStage: "model-chain",
    }
  );

  expect(plugin.pluginState.llmHealth).toMatchObject({
    status: "warning",
    fallbackCommand: "",
    fallbackStage: "model-chain",
  });
});

test("normalizeLlmHealthState lets camel-case empty fallback command override legacy snake-case", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context);

  expect(plugin.normalizeLlmHealthState({
    status: "degraded",
    fallbackCommand: "",
    fallback_command: "run-ask",
  })).toMatchObject({
    status: "degraded",
    fallbackCommand: "",
  });
});

test("latestLlmRun lets camel-case empty fallback lineage override legacy snake-case", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    shellSummary: {
      latest_llm_run: {
        event: "run-ask-frontdoor",
        delivery_mode: "llm-fallback-chain",
        fallbackFrom: "",
        fallback_from: "run-ask",
        fallbackCommand: "",
        fallback_command: "run-ask",
      },
    },
  });
  plugin.latestLlmRun = () => context.latestLlmRun(plugin);

  expect(plugin.latestLlmRun()).toMatchObject({
    command: "run-ask-frontdoor",
    deliveryMode: "llm-fallback-chain",
    fallbackFrom: "",
    fallbackCommand: "",
  });
});

test("latestLlmRun still normalizes legacy-only fallback lineage", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    shellSummary: {
      latest_llm_run: {
        event: "run-ask-frontdoor",
        delivery_mode: "deterministic-fallback",
        fallback_from: "ask",
        fallback_command: "ask",
      },
    },
  });
  plugin.latestLlmRun = () => context.latestLlmRun(plugin);

  expect(plugin.latestLlmRun()).toMatchObject({
    command: "run-ask-frontdoor",
    deliveryMode: "deterministic-fallback",
    fallbackFrom: "ask",
    fallbackCommand: "ask",
  });
});

test("selfCheckItems treats model retry delivery mode as healthy latest ask when run succeeded", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    shellSummary: {
      generated_at: new Date().toISOString(),
      llm_status: {
        backend: "opencode-api",
        backend_requested: "opencode-api",
        available_backends: ["opencode-api"],
        configured: true,
      },
      llm_health: {
        status: "healthy",
        checked_at: new Date().toISOString(),
      },
      latest_llm_run: {
        event: "run-ask-frontdoor",
        status: "success",
        delivery_mode: "llm-fallback-chain",
        fallback_used: true,
        backend: "opencode-api",
        result_path: "output/reports/current.md",
      },
    },
  });

  const latestAsk = context.selfCheckItems(plugin).find((item) => item.key === "latest-ask");

  expect(latestAsk).toMatchObject({
    status: "healthy",
    detail: "Latest run-ask succeeded. output/reports/current.md",
  });
});

test("selfCheckItems still treats legacy fallback without delivery mode as LLM failure notice", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    shellSummary: {
      generated_at: new Date().toISOString(),
      llm_status: {
        backend: "opencode-api",
        backend_requested: "opencode-api",
        available_backends: ["opencode-api"],
        configured: true,
      },
      llm_health: {
        status: "healthy",
        checked_at: new Date().toISOString(),
      },
      latest_llm_run: {
        event: "run-ask-frontdoor",
        status: "success",
        fallback_used: true,
        backend: "opencode-api",
        result_path: "output/reports/degraded.md",
      },
    },
  });

  const latestAsk = context.selfCheckItems(plugin).find((item) => item.key === "latest-ask");

  expect(latestAsk).toMatchObject({
    status: "warning",
    detail: "Latest run-ask produced an LLM failure notice. output/reports/degraded.md",
  });
});

test("newer shell summary remains the authoritative LLM health source", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    llmHealth: {
      status: "warning",
      reason: "LLM completed via model retry (model-chain).",
      checkedAt: "2026-06-20T08:00:00Z",
    },
    shellSummary: {
      generated_at: "2026-06-20T09:00:00Z",
      llm_status: { configured: true, backend: "opencode-api", model: "deepseek-v4-pro" },
      llm_health: {
        status: "healthy",
        reason: "Summary route recovered.",
        checked_at: "2026-06-20T09:00:00Z",
      },
    },
  });

  expect(context.currentLlmHealth(plugin)).toMatchObject({
    status: "healthy",
    reason: "Summary route recovered.",
    backend: "opencode-api",
    model: "deepseek-v4-pro",
  });
});

test("newer shell summary generated_at wins even when health checked_at is older", () => {
  const context = loadHealthStateContext();
  const plugin = makePlugin(context, {
    llmHealth: {
      status: "warning",
      reason: "LLM completed via model retry (model-chain).",
      checkedAt: "2026-06-20T08:00:00Z",
    },
    shellSummary: {
      generated_at: "2026-06-20T09:00:00Z",
      llm_status: { configured: true, backend: "opencode-api", model: "deepseek-v4-pro" },
      llm_health: {
        status: "healthy",
        reason: "Summary route recovered.",
        checked_at: "2026-06-20T07:00:00Z",
      },
    },
  });

  expect(context.currentLlmHealth(plugin)).toMatchObject({
    status: "healthy",
    reason: "Summary route recovered.",
  });
});
