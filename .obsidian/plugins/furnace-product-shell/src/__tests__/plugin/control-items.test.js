"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadControlItemContext() {
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
    notices: [],
  };
  context.Notice = function Notice(message) {
    context.notices.push(String(message || ""));
  };
  [
    "constants.js",
    "helpers.js",
    "plugin_helpers.js",
    "control_items.js",
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

function makePlugin(shellSummary) {
  return {
    shellSummary,
    locale: () => "zh",
    t: (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? "")),
  };
}

test("control item builders normalize and dedupe review and execution controls", () => {
  const context = loadControlItemContext();
  const plugin = makePlugin({
    review_controls: {
      pages: [
        {
          path: "wiki/decisions/a.md",
          title: "Decision A",
          kind: "decision",
          status: "pending",
          confidence: "medium",
          allowed_transitions: ["accepted", "rejected"],
          preferred_transitions: ["accepted"],
          default_transition: "accepted",
        },
        { path: "wiki/decisions/a.md", title: "Duplicate" },
        {
          path: "wiki/judgments/b.md",
          title: "Judgment B",
          kind: "decision",
          status: "pending",
          allowed_transitions: ["accepted", "rejected"],
          preferred_transitions: ["accepted"],
          default_transition: "rejected",
        },
      ],
      rewrite_proposals: [
        {
          slug: "rewrite-a",
          title: "Rewrite A",
          status: "proposed",
          priority: "high",
          score: 7,
          can_review: true,
          can_apply: false,
          allowed_transitions: ["accepted"],
        },
        { slug: "rewrite-b", can_review: false, can_apply: true },
      ],
    },
    execution_controls: {
      actions: [
        {
          action_id: "act-1",
          title: "Action 1",
          status: "pending",
          priority: "high",
          can_review: true,
          can_apply: true,
          primary_path: "wiki/a.md",
          bundle_path: "output/actions/act-1.json",
        },
        { action_id: "act-2", can_review: false, can_revert: true },
      ],
      archives: [
        {
          entry_id: "arch-1",
          title: "Archive 1",
          candidate_status: "ready",
          source_path: "raw/a.md",
          can_apply: true,
        },
        { entry_id: "arch-2", can_apply: false, can_revert: true },
      ],
    },
  });

  expect(context.reviewPageControlItems(plugin).map((item) => item.pagePath)).toEqual([
    "wiki/decisions/a.md",
    "wiki/judgments/b.md",
  ]);
  expect(context.rewriteControlItems(plugin, "review").map((item) => item.slug)).toEqual(["rewrite-a"]);
  expect(context.rewriteControlItems(plugin, "apply").map((item) => item.slug)).toEqual(["rewrite-b"]);
  expect(context.actionControlItems(plugin, "apply").map((item) => item.actionId)).toEqual(["act-1"]);
  expect(context.actionControlItems(plugin, "revert").map((item) => item.actionId)).toEqual(["act-2"]);
});

test("transition options prioritize default, preferred, then label", () => {
  const context = loadControlItemContext();
  const plugin = makePlugin({});
  const options = context.transitionOptions(plugin, "page", {
    allowedTransitions: ["rejected", "accepted", "needs-review"],
    preferredTransitions: ["accepted"],
    defaultTransition: "rejected",
  });

  expect(options.map((option) => [option.value, option.isDefault, option.isPreferred])).toEqual([
    ["rejected", true, false],
    ["accepted", false, true],
    ["needs-review", false, false],
  ]);
  expect(context.manualReviewOption(plugin, "action")).toMatchObject({
    value: "__manual__",
    isManual: true,
  });
});

test("transition picker helper preserves direct, manual, and context picker branches", () => {
  const context = loadControlItemContext();
  const calls = [];
  const plugin = {
    t: (text) => text,
    transitionOptions: (_controlType, control) => control.options || [],
    manualReviewOption: (controlType) => ({ value: "__manual__", label: `manual ${controlType}`, isManual: true }),
    openContextPicker: (spec) => calls.push(["picker", spec]),
  };

  context.openTransitionPickerForControl(plugin, {
    title: "Empty",
    controlType: "page",
    control: { options: [] },
    emptyNotice: "No transitions",
    onFallback: () => calls.push(["fallback"]),
    onSubmit: (value) => calls.push(["submit", value]),
  });
  context.openTransitionPickerForControl(plugin, {
    title: "Manual",
    controlType: "page",
    control: { options: [] },
    onManual: () => calls.push(["manual"]),
    onSubmit: (value) => calls.push(["submit", value]),
  });
  context.openTransitionPickerForControl(plugin, {
    title: "One",
    controlType: "page",
    control: { options: [{ value: "accepted", label: "Accepted" }] },
    onSubmit: (value) => calls.push(["submit", value]),
  });
  context.openTransitionPickerForControl(plugin, {
    title: "Many",
    description: "Pick",
    controlType: "rewrite",
    control: { options: [{ value: "accepted" }, { value: "rejected" }] },
    onManual: () => calls.push(["manual-many"]),
    onSubmit: (value) => calls.push(["submit", value]),
  });

  expect(context.notices).toEqual(["No transitions"]);
  expect(calls[0]).toEqual(["fallback"]);
  expect(calls[1]).toEqual(["manual"]);
  expect(calls[2]).toEqual(["submit", "accepted"]);
  expect(calls[3][0]).toBe("picker");
  expect(calls[3][1].submitLabel).toBe("Use");
  expect(calls[3][1].options.map((option) => option.value)).toEqual(["accepted", "rejected", "__manual__"]);
  calls[3][1].onSubmit({ value: "__manual__", isManual: true });
  calls[3][1].onSubmit({ value: "rejected" });
  expect(calls.slice(4)).toEqual([["manual-many"], ["submit", "rejected"]]);
});

test("context-aware action helper dedupes options and falls back when empty", () => {
  const context = loadControlItemContext();
  const calls = [];
  const plugin = {
    t: (text) => text,
    openContextPicker: (spec) => calls.push(["picker", spec]),
  };

  context.openContextAwareActionForSpec(plugin, {
    options: [],
    emptyNotice: "Nothing here",
    onFallback: () => calls.push(["fallback"]),
    onSubmit: (option) => calls.push(["submit", option]),
  });
  context.openContextAwareActionForSpec(plugin, {
    options: [{ value: "one" }],
    onFallback: () => calls.push(["fallback"]),
    onSubmit: (option) => calls.push(["submit", option]),
  });
  context.openContextAwareActionForSpec(plugin, {
    title: "Pick item",
    description: "Choose",
    submitLabel: "Select",
    options: [{ value: "a" }, { value: "a" }, { value: "b" }],
    onFallback: () => calls.push(["fallback"]),
    onSubmit: (option) => calls.push(["submit", option]),
  });

  expect(context.notices).toEqual(["Nothing here"]);
  expect(calls[0]).toEqual(["fallback"]);
  expect(calls[1]).toEqual(["submit", { value: "one" }]);
  expect(calls[2][0]).toBe("picker");
  expect(calls[2][1].submitLabel).toBe("Select");
  expect(calls[2][1].options.map((option) => option.value)).toEqual(["a", "b"]);
});
