"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadHelpersContext() {
  const context = {
    console,
    require,
    Array,
    String,
    Number,
    Object,
    Set,
    Date,
    RegExp,
    JSON,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "helpers.js" });
  return context;
}

test("normalizeStickyMaterialRefs recovers from corrupt values", () => {
  const { normalizeStickyMaterialRefs } = loadHelpersContext();
  expect(normalizeStickyMaterialRefs(null)).toEqual({ paths: [], updatedAt: "", source: "" });
  expect(normalizeStickyMaterialRefs({ paths: "raw/inbox/a.md", updatedAt: 1, source: null })).toEqual({
    paths: ["raw/inbox/a.md"],
    updatedAt: "1",
    source: "",
  });
});

test("setStickyMaterialRefs replaces paths and stamps metadata", () => {
  const { setStickyMaterialRefs, normalizeStickyMaterialRefs } = loadHelpersContext();
  const settings = {};
  const first = setStickyMaterialRefs(settings, ["raw/inbox/a.md", "raw/inbox/b.md"], "drop");
  expect(first.paths).toEqual(["raw/inbox/a.md", "raw/inbox/b.md"]);
  expect(first.source).toBe("drop");
  expect(first.updatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  setStickyMaterialRefs(settings, ["raw/inbox/c.md"], "drop");
  expect(normalizeStickyMaterialRefs(settings.stickyMaterialRefs).paths).toEqual(["raw/inbox/c.md"]);
});

test("resolveAskMaterialPaths prefers explicit paths over sticky", () => {
  const { resolveAskMaterialPaths } = loadHelpersContext();
  const sticky = { paths: ["raw/inbox/old.md"], updatedAt: "t", source: "drop" };
  expect(resolveAskMaterialPaths(["raw/inbox/new.md"], sticky)).toEqual({
    paths: ["raw/inbox/new.md"],
    fromSticky: false,
  });
  expect(resolveAskMaterialPaths([], sticky)).toEqual({
    paths: ["raw/inbox/old.md"],
    fromSticky: true,
  });
  expect(resolveAskMaterialPaths([], { paths: [] })).toEqual({ paths: [], fromSticky: false });
});

test("questionAlreadyHasMaterialRoutingHint detects injected ask questions", () => {
  const { questionAlreadyHasMaterialRoutingHint, buildAutoAskQuestion } = loadHelpersContext();
  const injected = buildAutoAskQuestion("有什么区别吗?", ["raw/inbox/a.md"]);
  expect(questionAlreadyHasMaterialRoutingHint(injected)).toBe(true);
  expect(questionAlreadyHasMaterialRoutingHint("有什么区别吗?")).toBe(false);
});

test("imageDropLacksReadableAnalysis detects image drops without vision analysis", () => {
  const { imageDropLacksReadableAnalysis } = loadHelpersContext();
  expect(imageDropLacksReadableAnalysis({
    material: "image",
    visual_analysis_present: false,
    vision_status: "skipped",
  })).toBe(true);
  expect(imageDropLacksReadableAnalysis({
    material: "image",
    visual_analysis_present: true,
    vision_status: "generated",
  })).toBe(false);
  expect(imageDropLacksReadableAnalysis({ material: "url" })).toBe(false);
});

test("stickyMaterialDisplayPaths and formatMaterialChipLabel", () => {
  const { stickyMaterialDisplayPaths, formatMaterialChipLabel } = loadHelpersContext();
  expect(stickyMaterialDisplayPaths({
    stickyMaterialRefs: { paths: ["raw/inbox/a.md", "output/reports/r.md"], updatedAt: "t", source: "drop" },
  })).toEqual(["raw/inbox/a.md", "output/reports/r.md"]);
  expect(formatMaterialChipLabel("raw/inbox/codex-goal.md")).toBe("codex-goal.md");
  expect(formatMaterialChipLabel("")).toBe("");
});

test("isAskMaterialPathAllowed matches runtime material hint prefixes", () => {
  const { isAskMaterialPathAllowed } = loadHelpersContext();
  expect(isAskMaterialPathAllowed("raw/inbox/a.md")).toBe(true);
  expect(isAskMaterialPathAllowed("wiki/sources/x.md")).toBe(true);
  expect(isAskMaterialPathAllowed("wiki/elixirs/e.md")).toBe(true);
  expect(isAskMaterialPathAllowed("output/reports/r.md")).toBe(true);
  expect(isAskMaterialPathAllowed(".aiwiki/state/x.md")).toBe(true);
  expect(isAskMaterialPathAllowed("notes/root.md")).toBe(false);
  expect(isAskMaterialPathAllowed("raw/inbox/a.png")).toBe(false);
});

test("extractAtMentionQuery finds trailing @token", () => {
  const { extractAtMentionQuery } = loadHelpersContext();
  expect(extractAtMentionQuery("see @wiki/sou", 13)).toEqual({ start: 4, end: 13, query: "wiki/sou" });
  expect(extractAtMentionQuery("@raw/inbox/a", 12)).toEqual({ start: 0, end: 12, query: "raw/inbox/a" });
  expect(extractAtMentionQuery("hello world", 11)).toBeNull();
  expect(extractAtMentionQuery("email@x.com more", 10)).toBeNull();
});

test("filterVaultPathsForMention keeps allowed prefixes and query", () => {
  const { filterVaultPathsForMention } = loadHelpersContext();
  expect(filterVaultPathsForMention([
    "raw/inbox/a.md",
    "notes/root.md",
    "wiki/sources/foo.md",
    "output/reports/r.md",
  ], "foo", 12)).toEqual(["wiki/sources/foo.md"]);
});
