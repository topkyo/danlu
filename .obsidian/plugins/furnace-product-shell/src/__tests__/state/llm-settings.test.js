"use strict";

const {
  DEFAULT_PRODUCT_LLM_BACKEND,
  DEFAULT_PRODUCT_LLM_MODEL,
  LLM_PROVIDER_PROFILES,
  buildLlmEnv,
  clearKnownLlmEnv,
  dropLegacyLlmSettings,
  llmProviderNeedsModel,
  llmProviderProfile,
} = require("../../llm_settings");

test("default Product Shell LLM provider is DeepSeek deepseek-v4-flash", () => {
  expect(DEFAULT_PRODUCT_LLM_BACKEND).toBe("deepseek-api");
  expect(DEFAULT_PRODUCT_LLM_MODEL).toBe("deepseek-v4-flash");
  expect(llmProviderProfile("").value).toBe("deepseek-api");
  expect(buildLlmEnv({})).toEqual({
    AIWIKI_LLM_BACKEND: "deepseek-api",
    AIWIKI_LLM_MODEL: "deepseek-v4-flash",
  });
});

test("provider list puts curated providers before advanced entries", () => {
  expect(LLM_PROVIDER_PROFILES.slice(0, 4).map((profile) => profile.value)).toEqual([
    "deepseek-api",
    "opencode-api",
    "anthropic-api",
    "openai-api",
  ]);
  expect(LLM_PROVIDER_PROFILES.every((profile) => profile.tier === "common")).toBe(true);
  expect(LLM_PROVIDER_PROFILES.every((profile) => !profile.cliHint)).toBe(true);
});

test("buildLlmEnv only emits the selected provider secret and base URL", () => {
  const env = buildLlmEnv({
    llmBackend: "deepseek-api",
    llmModel: "deepseek-chat",
    llmDeepseekApiKey: "sk-current",
    llmDeepseekBaseUrl: "https://deepseek.example",
    llmOpencodeApiKey: "opencode-stale",
  });

  expect(env).toEqual({
    AIWIKI_LLM_BACKEND: "deepseek-api",
    AIWIKI_LLM_MODEL: "deepseek-chat",
    AIWIKI_DEEPSEEK_API_KEY: "sk-current",
    AIWIKI_DEEPSEEK_BASE_URL: "https://deepseek.example",
  });
});

test("buildLlmEnv replaces stale default model when provider changes", () => {
  expect(buildLlmEnv({ llmBackend: "anthropic-api", llmModel: "deepseek-v4-pro" })).toEqual({
    AIWIKI_LLM_BACKEND: "anthropic-api",
    AIWIKI_LLM_MODEL: "claude-sonnet-4-20250514",
  });
});

test("removed providers migrate to the default API provider", () => {
  const profile = llmProviderProfile("codex-cli");
  expect(profile.value).toBe("deepseek-api");
  expect(llmProviderNeedsModel(profile)).toBe(true);
  expect(buildLlmEnv({ llmBackend: "codex-cli", llmModel: "gpt-5.5", llmDeepseekApiKey: "current" })).toEqual({
    AIWIKI_LLM_BACKEND: "deepseek-api",
    AIWIKI_LLM_MODEL: "gpt-5.5",
    AIWIKI_DEEPSEEK_API_KEY: "current",
  });
});

test("clearKnownLlmEnv removes stale provider keys before launcher spawn", () => {
  const env = {
    KEEP_ME: "1",
    AIWIKI_LLM_BACKEND: "deepseek-api",
    AIWIKI_MODEL_FALLBACK: "stale-model",
    AIWIKI_DEEPSEEK_API_KEY: "stale",
    AIWIKI_OPENCODE_API_KEY: "stale",
    DEEPSEEK_API_KEY: "stale-deepseek-fallback",
    OPENAI_API_KEY: "stale-openai-fallback",
    ANTHROPIC_API_KEY: "stale-anthropic-fallback",
  };
  clearKnownLlmEnv(env);
  expect(env).toEqual({ KEEP_ME: "1" });
});

test("OpenCode env does not inject hidden backend fallback", () => {
  const env = buildLlmEnv({ llmBackend: "opencode-api", llmModel: "deepseek-v4-pro" });

  expect(env).toEqual({
    AIWIKI_LLM_BACKEND: "opencode-api",
    AIWIKI_LLM_MODEL: "deepseek-v4-pro",
  });
  expect(env.AIWIKI_BACKEND_FALLBACK).toBeUndefined();
  expect(env.AIWIKI_BACKEND_FALLBACK_MODEL).toBeUndefined();
  expect(env.AIWIKI_MODEL_FALLBACK).toBeUndefined();
});

test("dropLegacyLlmSettings removes old unused key fields", () => {
  const settings = {
    llmGithubToken: "gh",
    llmGithubModelsBaseUrl: "https://models",
    llmApiKey: "old",
    llmNvidiaNimApiKey: "old-nim",
    llmOpenrouterApiKey: "old-router",
    llmAnthropicApiKey: "current-ant",
    llmOpencodeApiKey: "current",
  };
  expect(dropLegacyLlmSettings(settings)).toBe(true);
  expect(settings).toEqual({ llmAnthropicApiKey: "current-ant", llmOpencodeApiKey: "current" });
  expect(dropLegacyLlmSettings(settings)).toBe(false);
});

test("build.sh concatenates llm_settings before constants", () => {
  const fs = require("fs");
  const path = require("path");
  const build = fs.readFileSync(path.resolve(__dirname, "../../../build.sh"), "utf8");
  const match = build.match(/for module in ([^\n]+); do/);
  expect(match).toBeTruthy();
  const modules = match[1].trim().split(/\s+/);
  const settingsIndex = modules.indexOf("llm_settings");
  const constantsIndex = modules.indexOf("constants");
  expect(settingsIndex).toBeGreaterThanOrEqual(0);
  expect(constantsIndex).toBeGreaterThan(settingsIndex);
});

test("DEFAULT_SETTINGS LLM defaults resolve after llm_settings loads", () => {
  const fs = require("fs");
  const path = require("path");
  const vm = require("vm");
  const srcDir = path.resolve(__dirname, "../..");
  const context = { console, require };
  vm.createContext(context);
  const bundled = [
    fs.readFileSync(path.join(srcDir, "llm_settings.js"), "utf8"),
    fs.readFileSync(path.join(srcDir, "constants.js"), "utf8"),
    "this.DEFAULT_SETTINGS = DEFAULT_SETTINGS;",
    "this.DEFAULT_PRODUCT_LLM_BACKEND = DEFAULT_PRODUCT_LLM_BACKEND;",
    "this.DEFAULT_PRODUCT_LLM_MODEL = DEFAULT_PRODUCT_LLM_MODEL;",
  ].join("\n");
  vm.runInContext(bundled, context);
  expect(context.DEFAULT_SETTINGS.llmBackend).toBe(context.DEFAULT_PRODUCT_LLM_BACKEND);
  expect(context.DEFAULT_SETTINGS.llmModel).toBe(context.DEFAULT_PRODUCT_LLM_MODEL);
  expect(context.DEFAULT_SETTINGS.llmModel).toBe("deepseek-v4-flash");
});
