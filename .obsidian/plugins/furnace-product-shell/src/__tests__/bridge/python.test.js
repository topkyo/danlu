"use strict";

// Set up globals that are provided by the build header in the concatenated main.js

const mockFs = { existsSync: jest.fn(() => true) };
const mockSpawnSync = jest.fn();
global.fs = mockFs;
global.path = require("path");
global.spawnSync = mockSpawnSync;

const {
  guiPatchedPath,
  pythonBinSupportsAiwiki,
  resolvePythonBin,
  resetResolvedPythonBinForTests,
} = require("../../bridge/python");

beforeEach(() => {
  jest.clearAllMocks();
  mockFs.existsSync.mockReturnValue(true);
  resetResolvedPythonBinForTests();
});

test("guiPatchedPath prepends existing candidate dirs without duplicates", () => {
  mockFs.existsSync.mockImplementation((entry) => entry !== "/home/u/bin");
  const patched = guiPatchedPath("/usr/bin:/home/u/.local/bin", "/home/u");
  const entries = patched.split(":");
  expect(entries.filter((entry) => entry === "/home/u/.local/bin")).toHaveLength(1);
  expect(entries).not.toContain("/home/u/bin");
  expect(entries[0]).toBe("/opt/homebrew/bin");
  expect(entries).toContain("/usr/bin");
});

test("pythonBinSupportsAiwiki accepts >=3.10 and rejects older or broken bins", () => {
  mockSpawnSync.mockImplementation((bin) => ({
    status: 0,
    stdout: bin === "python3-old" ? "3.9\n" : "3.12\n",
  }));
  expect(pythonBinSupportsAiwiki("python3-new", {})).toBe(true);
  expect(pythonBinSupportsAiwiki("python3-old", {})).toBe(false);
  mockSpawnSync.mockReturnValueOnce({ error: new Error("ENOENT") });
  expect(pythonBinSupportsAiwiki("missing-bin", {})).toBe(false);
});

test("resolvePythonBin prefers AIWIKI_PYTHON and caches the result", () => {
  mockSpawnSync.mockReturnValue({ status: 0, stdout: "3.12\n" });
  const env = { AIWIKI_PYTHON: "/custom/python3", HOME: "/home/u", PATH: "/usr/bin" };
  expect(resolvePythonBin(env)).toBe("/custom/python3");
  expect(mockSpawnSync).toHaveBeenCalledTimes(1);
  expect(resolvePythonBin(env)).toBe("/custom/python3");
  expect(mockSpawnSync).toHaveBeenCalledTimes(1);
});

test("resolvePythonBin skips old interpreters and falls through to the next candidate", () => {
  mockSpawnSync.mockImplementation((bin) => ({
    status: 0,
    stdout: bin === "/usr/local/bin/python3" ? "3.9\n" : "3.11\n",
  }));
  const env = { HOME: "/home/u", PATH: "/usr/bin" };
  expect(resolvePythonBin(env)).toBe("/opt/homebrew/bin/python3");
});

test("resolvePythonBin returns empty when no interpreter qualifies", () => {
  mockSpawnSync.mockReturnValue({ status: 1, stdout: "" });
  expect(resolvePythonBin({ HOME: "/home/u", PATH: "/usr/bin" })).toBe("");
});
