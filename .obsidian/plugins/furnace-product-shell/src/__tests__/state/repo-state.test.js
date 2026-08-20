"use strict";

// Set up globals that are provided by the build header in the concatenated main.js

const mockFs = {
  existsSync: jest.fn().mockReturnValue(true),
};
global.fs = mockFs;
global.path = require("path");

const { refreshRepoState, resolveRuntimeRoot, runtimeRootIsUsable } = require("../../state/repo-state");

// ── Helpers ──────────────────────────────────────────────────────────

function makeMockPlugin(overrides = {}) {
  return {
    app: {
      vault: {
        adapter: { basePath: "/fake/vault" },
      },
    },
    settings: {
      runtimeRoot: "/fake/runtime",
      ...overrides,
    },
    repoState: null,
    updateStatusBar: jest.fn(),
    refreshOpenViews: jest.fn(),
    t: (key) => key,
  };
}

// ── Tests ────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockFs.existsSync.mockReturnValue(true);
});

test("refreshRepoState returns valid repo state when scaffold and runtime root exist", () => {
  const plugin = makeMockPlugin();
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(true);
  expect(state.root).toBe("/fake/vault");
  expect(state.runtimeRoot).toBe("/fake/runtime");
  expect(state.missingPaths).toEqual([]);
});

test("refreshRepoState detects missing scaffold paths", () => {
  const plugin = makeMockPlugin();
  mockFs.existsSync.mockImplementation((p) => !p.endsWith("wiki"));
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("wiki");
});

test("refreshRepoState detects missing vault root", () => {
  const plugin = makeMockPlugin();
  plugin.app.vault.adapter = null;
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("vault-root");
});

test("refreshRepoState detects unusable runtime root", () => {
  const plugin = makeMockPlugin();
  mockFs.existsSync.mockImplementation((p) => !String(p).endsWith("__main__.py"));
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("runtime-root");
});

test("refreshRepoState detects unconfigured runtime root", () => {
  const plugin = makeMockPlugin({ runtimeRoot: "" });
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("runtime-root");
});

test("resolveRuntimeRoot trims the settings value and tolerates missing settings", () => {
  expect(resolveRuntimeRoot({ runtimeRoot: "  /repo " })).toBe("/repo");
  expect(resolveRuntimeRoot({})).toBe("");
  expect(resolveRuntimeRoot(null)).toBe("");
});

test("runtimeRootIsUsable requires the CLI marker file", () => {
  mockFs.existsSync.mockReturnValue(true);
  expect(runtimeRootIsUsable("/repo")).toBe(true);
  mockFs.existsSync.mockReturnValue(false);
  expect(runtimeRootIsUsable("/repo")).toBe(false);
  expect(runtimeRootIsUsable("")).toBe(false);
});
