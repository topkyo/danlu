"use strict";

// Set up globals that are provided by the build header in the concatenated main.js

// ── Setup fs mock ────────────────────────────────────────────────────

const mockFs = {
  existsSync: jest.fn().mockReturnValue(true),
  accessSync: jest.fn(),
  constants: { X_OK: 1 },
};
global.fs = mockFs;
global.path = require("path");

const { refreshRepoState, resolveLauncherPath, launcherIsExecutable } = require("../../state/repo-state");

// ── Mock DEFAULT_SETTINGS ────────────────────────────────────────────

// Set global DEFAULT_SETTINGS (normally from constants.js, concatenated before this module)
global.DEFAULT_SETTINGS = {
  launcherPath: "scripts/aiwiki-launcher.sh",
  locale: "zh",
  showAdvancedCommands: true,
};

// ── Helpers ──────────────────────────────────────────────────────────

function makeMockPlugin(overrides = {}) {
  return {
    app: {
      vault: {
        adapter: { basePath: "/fake/vault" },
      },
    },
    settings: {
      launcherPath: "scripts/aiwiki-launcher.sh",
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
  mockFs.accessSync.mockImplementation(() => {});
});

test("refreshRepoState returns valid repo state when all paths exist", () => {
  const plugin = makeMockPlugin();
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(true);
  expect(state.root).toBe("/fake/vault");
  expect(state.launcherPath).toBe("/fake/vault/scripts/aiwiki-launcher.sh");
  expect(state.missingPaths).toEqual([]);
});

test("refreshRepoState detects missing paths", () => {
  const plugin = makeMockPlugin();
  mockFs.existsSync.mockImplementation((p) => !p.endsWith("wiki"));
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("wiki");
});

test("refreshRepoState detects missing vault root", () => {
  const plugin = {
    app: { vault: { adapter: null } },
    settings: { launcherPath: "scripts/launcher.sh" },
    updateStatusBar: jest.fn(),
    refreshOpenViews: jest.fn(),
    t: (key) => key,
  };
  const state = refreshRepoState(plugin);
  expect(state.valid).toBe(false);
  expect(state.missingPaths).toContain("vault-root");
});

test("resolveLauncherPath returns empty for missing root", () => {
  expect(resolveLauncherPath("", { launcherPath: "scripts/launcher.sh" })).toBe("");
});

test("resolveLauncherPath returns absolute paths as-is", () => {
  expect(resolveLauncherPath("/root", { launcherPath: "/absolute/launcher.sh" })).toBe("/absolute/launcher.sh");
});

test("resolveLauncherPath joins relative paths with root", () => {
  expect(resolveLauncherPath("/root", { launcherPath: "scripts/launcher.sh" })).toBe("/root/scripts/launcher.sh");
});

test("launcherIsExecutable returns false for empty path", () => {
  expect(launcherIsExecutable("")).toBe(false);
  expect(launcherIsExecutable(null)).toBe(false);
});

test("launcherIsExecutable returns true when access succeeds", () => {
  mockFs.accessSync.mockImplementation(() => {});
  expect(launcherIsExecutable("/bin/sh")).toBe(true);
});

test("launcherIsExecutable returns false when access throws", () => {
  mockFs.accessSync.mockImplementation(() => { throw new Error("ENOENT"); });
  expect(launcherIsExecutable("/nonexistent")).toBe(false);
});
