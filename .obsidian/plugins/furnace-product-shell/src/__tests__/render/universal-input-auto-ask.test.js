"use strict";

const fs = require("fs");
const path = require("path");

test("render input source wires drop+question into a single auto run-ask", () => {
  const inputSrc = fs.readFileSync(path.resolve(__dirname, "../../render_input.js"), "utf8");

  expect(inputSrc).toMatch(/autoAsk:\s*Boolean\(normalizedQuestion\)/);
  expect(inputSrc).toMatch(/question:\s*normalizedQuestion/);
  expect(inputSrc).toMatch(/await plugin\.runDroppedFilesWithAutoAsk\(\{/);
  expect(inputSrc).toMatch(/splitTextMaterialQuestion\(value\)/);
  expect(inputSrc).toMatch(/runDroppedPayloadsWithAutoAsk\(\{/);
  expect(inputSrc).not.toMatch(/for \(const file of resolvedFiles\)\s*\{\s*await plugin\.runAskCommand/);
});

test("retry source keeps auto ask metadata and replays unified flow", () => {
  const todaySrc = fs.readFileSync(path.resolve(__dirname, "../../render_today.js"), "utf8");

  expect(todaySrc).toMatch(/plugin\.runDroppedFilesWithAutoAsk\(\{/);
  expect(todaySrc).toMatch(/plugin\.runDroppedPayloadsWithAutoAsk\(\{/);
  expect(todaySrc).toMatch(/plugin\.updatePendingSubmissionRetryArgs\(entry\.id, \{/);
  expect(todaySrc).toMatch(/materialPaths:/);
  expect(todaySrc).toMatch(/askQuestion:/);
});

test("built main keeps drop+question auto run-ask markers", () => {
  const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

  expect(bundleSrc).toMatch(/function buildUniversalInputCommandSpec/);
  expect(bundleSrc).toMatch(/labelKey: "Universal Input"/);
  expect(bundleSrc).toMatch(/return await this\.runPluginCommand\(commandLabel\(this\.t\.bind\(this\), spec\.labelKey, spec\.labelSubject\)/);
  expect(bundleSrc).toMatch(/async runDroppedFilesWithAutoAsk\(/);
  expect(bundleSrc).toMatch(/async runDroppedPayloadsWithAutoAsk\(/);
  expect(bundleSrc).toMatch(/function splitTextMaterialQuestion\(/);
  expect(bundleSrc).toMatch(/collectMaterialPathsFromPayload\(payload\)/);
  expect(bundleSrc).toMatch(/buildAutoAskQuestion\(normalizedQuestion, normalizedMaterialPaths\)/);
  expect(bundleSrc).toMatch(/const canUseDirect = format === "note"/);
  expect(bundleSrc).toMatch(/!directQuestion\.includes\("材料路径供系统路由使用："\)/);
  expect(bundleSrc).toMatch(/--lean/);
  expect(bundleSrc).not.toMatch(/args\.push\("--timeout", "45"\)/);
  expect(bundleSrc).not.toMatch(/--fallback-to-ask/);
  expect(bundleSrc).toMatch(/材料路径供系统路由使用/);
});
