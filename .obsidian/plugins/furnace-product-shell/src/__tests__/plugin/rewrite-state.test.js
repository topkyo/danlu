"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadRewriteStateContext() {
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
  ].forEach((relativePath) => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
  });
  return context;
}

test("rewrite state helpers normalize, dedupe, and extract proposal fields", () => {
  const context = loadRewriteStateContext();
  const payload = {
    updated_rewrite_proposals: [
      {
        slug: "concept-a",
        title: "Concept A",
        status: "proposed",
        proposal_path: "wiki/rewrite-proposals/concept-a.md",
        target_path: "wiki/concepts/a.md",
        can_review: true,
      },
      {
        slug: "concept-a",
        title: "Duplicate",
        proposal_path: "wiki/rewrite-proposals/duplicate.md",
      },
    ],
    rewrite_followup_actions: [
      { slug: "concept-a", command: "review-rewrite concept-a --status accepted", transition: "accepted" },
      { slug: "concept-a", command: "review-rewrite concept-a --status accepted", transition: "accepted" },
    ],
  };

  const proposals = context.extractRewriteProposalObjects(payload);
  expect(proposals).toHaveLength(1);
  expect(proposals[0]).toMatchObject({
    slug: "concept-a",
    proposalPath: "wiki/rewrite-proposals/concept-a.md",
    targetPath: "wiki/concepts/a.md",
    canReview: true,
  });
  expect(context.extractRewriteProposalPaths(payload)).toEqual(["wiki/rewrite-proposals/concept-a.md"]);
  expect(context.extractRewriteProposalSlugs(["wiki/rewrite-proposals/concept-a.md"])).toEqual(["concept-a"]);
  expect(context.extractRewriteFollowupActions(payload)).toHaveLength(1);
});

test("rewrite summary prefers proposal object count over path count", () => {
  const context = loadRewriteStateContext();
  const plugin = {
    t: (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? "")),
  };

  expect(context.rewriteProposalSummary(plugin, {
    rewriteProposalObjects: [{ slug: "a" }, { slug: "b" }],
    rewriteProposalPaths: ["a.md"],
  })).toBe("rewrite proposals: 2");
  expect(context.rewriteProposalSummary(plugin, { rewriteProposalPaths: ["a.md"] })).toBe("rewrite proposals: 1");
  expect(context.rewriteProposalSummary(plugin, {})).toBe("");
});

test("open rewrite recovery helper routes to the narrowest available UI action", () => {
  const context = loadRewriteStateContext();
  const calls = [];
  const plugin = {
    locale: () => "en",
    t: (text) => text,
    normalizeRewriteFollowupActions: context.normalizeRewriteFollowupActions,
    normalizeRewriteProposalObjects: context.normalizeRewriteProposalObjects,
    rewriteCandidatesForSlugs: (slugs) => context.normalizeRelativePathList(slugs).map((slug) => ({ slug, title: `Control ${slug}` })),
    openApplyRewriteModal: (payload) => calls.push(["apply", payload]),
    openReviewRewriteTransitionPicker: (payload) => calls.push(["transition", payload]),
    openReviewRewriteContextPicker: (payload) => calls.push(["context", payload]),
    openReviewRewriteModal: (payload) => calls.push(["modal", payload]),
    openReviewNextTransitionPicker: () => calls.push(["review-next"]),
    runUiAction: (action, label) => {
      calls.push(["run-ui", label]);
      action();
    },
  };

  context.openRewriteFollowupForRecord(plugin, {
    rewriteFollowupActions: [{ slug: "concept-a", kind: "apply-rewrite", command: "apply concept-a" }],
  });
  context.openRewriteFollowupForRecord(plugin, {
    rewriteFollowupActions: [{ slug: "concept-b", status: "accepted", transition: "resolved", command: "review concept-b" }],
    rewriteProposalObjects: [{ slug: "concept-b", title: "Concept B", currentStatus: "proposed" }],
  });
  context.openRewriteFollowupForRecord(plugin, {
    rewriteProposalObjects: [
      { slug: "concept-c", title: "Concept C", status: "proposed", proposalPath: "wiki/rewrite-proposals/c.md" },
      { slug: "concept-d", title: "Concept D", status: "accepted", proposalPath: "wiki/rewrite-proposals/d.md" },
    ],
  });
  context.openRewriteFollowupForRecord(plugin, {
    rewriteProposalSlugs: ["concept-e"],
  });
  context.openRewriteFollowupForRecord(plugin, {});

  expect(calls[0]).toEqual(["apply", { slug: "concept-a" }]);
  expect(calls[1][0]).toBe("transition");
  expect(calls[1][1]).toMatchObject({ slug: "concept-b", status: "accepted", currentStatus: "accepted", defaultTransition: "resolved" });
  expect(calls[2][0]).toBe("context");
  expect(calls[2][1]).toHaveLength(2);
  expect(calls[2][1][0]).toMatchObject({ value: "concept-c", label: "Concept C" });
  expect(calls[2][1][0].description).toContain("wiki/rewrite-proposals/c.md");
  expect(calls[3]).toEqual(["transition", { slug: "concept-e", title: "Control concept-e" }]);
  expect(calls[4]).toEqual(["run-ui", "Review Next Page"]);
  expect(calls[5]).toEqual(["review-next"]);
});
