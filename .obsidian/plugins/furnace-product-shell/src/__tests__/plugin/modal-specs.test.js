"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadModalSpecContext() {
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
    Promise,
  };
  [
    "constants.js",
    "helpers.js",
    "plugin_helpers.js",
    "modal_specs.js",
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

function makePlugin(overrides = {}) {
  const calls = [];
  const notices = [];
  return {
    calls,
    notices,
    t: (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? "")),
    getActiveOutputPath: () => overrides.activeOutputPath || "output/reports/current.md",
    getActiveCuratedPagePath: () => overrides.activeCuratedPagePath || "wiki/decisions/current.md",
    getActiveConceptSlug: () => overrides.activeConceptSlug || "current-concept",
    transitionLabel: (_controlType, value) => `label:${value}`,
    runCliAction: async (label, command, args) => {
      calls.push({ label, command, args });
    },
    runApplyAllAcceptedLowRiskCommand: async () => {
      calls.push({ label: "apply-all-low-risk", command: "notice" });
    },
  };
}

function loadModalSpecContextWithNotice() {
  const context = loadModalSpecContext();
  context.Notice = (message) => {
    context.__lastNotice = message;
  };
  return context;
}

test("review page modal spec keeps fields and submit args stable", async () => {
  const context = loadModalSpecContext();
  const plugin = makePlugin();
  const spec = context.buildReviewPageModalSpec(plugin, { status: "accepted", confidence: "high" });

  expect(spec.title).toBe("Review Page");
  expect(spec.fields.map((field) => field.key)).toEqual(["page", "status", "note", "confidence"]);
  expect(spec.fields[0].initialValue()).toBe("wiki/decisions/current.md");

  await spec.onSubmit({
    page: "wiki/decisions/a.md",
    status: "accepted",
    note: "ok",
    confidence: "high",
  });
  expect(plugin.calls[0]).toEqual({
    label: "Review Page: accepted",
    command: "review-page",
    args: ["wiki/decisions/a.md", "--status", "accepted", "--note", "ok", "--confidence", "high"],
  });
});

test("apply action modal spec routes through removed-command notice hook", async () => {
  const context = loadModalSpecContext();
  const plugin = makePlugin();
  const spec = context.buildApplyActionModalSpec(plugin, { actionId: "act-1", bundle: "output/actions/act-1.json", dryRun: true });

  expect(spec.fields.map((field) => field.key)).toEqual(["action_id", "note", "bundle", "dry_run"]);
  await spec.onSubmit({
    action_id: "act-1",
    note: "safe",
    bundle: "output/actions/act-1.json",
    dry_run: true,
  });
  expect(plugin.calls[0]).toEqual({
    label: "apply-all-low-risk",
    command: "notice",
  });
});

test("file back modal submits judgment-only file-back args", async () => {
  const context = loadModalSpecContext();
  const plugin = makePlugin();
  const spec = context.buildFileBackModalSpec(plugin, {});

  expect(spec.fields.map((field) => field.key)).toEqual(["artifact", "title"]);
  await spec.onSubmit({
    artifact: "output/reports/current.md",
    title: "Follow-up",
  });
  expect(plugin.calls[0]).toEqual({
    label: "File Back",
    command: "file-back",
    args: ["output/reports/current.md", "--title", "Follow-up"],
  });
});

test("alchemy start modal spec submits corpus and topic args", async () => {
  const context = loadModalSpecContext();
  const plugin = makePlugin();
  const spec = context.buildAlchemyStartModalSpec(plugin, {
    corpusId: "corpus-a",
    topic: "Follow-up thesis",
    includeElixir: "elixir-old",
  });

  expect(spec.fields.map((field) => field.key)).toEqual(["corpus_id", "topic", "include_elixir"]);
  await spec.onSubmit({
    corpus_id: "corpus-a",
    topic: "Follow-up thesis",
    include_elixir: "elixir-old",
  });
  expect(plugin.calls[0]).toEqual({
    label: "Alchemy Start: corpus-a",
    command: "alchemy-start",
    args: ["corpus-a", "--topic", "Follow-up thesis", "--include-elixir", "elixir-old"],
  });
});
