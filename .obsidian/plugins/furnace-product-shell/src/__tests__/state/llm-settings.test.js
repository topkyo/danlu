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

test("default Product Shell LLM provider is OpenCode deepseek-v4-pro", () => {
  expect(DEFAULT_PRODUCT_LLM_BACKEND).toBe("opencode-api");
  expect(DEFAULT_PRODUCT_LLM_MODEL).toBe("deepseek-v4-pro");
  expect(llmProviderProfile("").value).toBe("opencode-api");
  expect(buildLlmEnv({})).toEqual({
    AIWIKI_LLM_BACKEND: "opencode-api",
    AIWIKI_LLM_MODEL: "deepseek-v4-pro",
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
  expect(profile.value).toBe("opencode-api");
  expect(llmProviderNeedsModel(profile)).toBe(true);
  expect(buildLlmEnv({ llmBackend: "codex-cli", llmModel: "gpt-5.5", llmOpencodeApiKey: "current" })).toEqual({
    AIWIKI_LLM_BACKEND: "opencode-api",
    AIWIKI_LLM_MODEL: "gpt-5.5",
    AIWIKI_OPENCODE_API_KEY: "current",
  });
});

test("clearKnownLlmEnv removes stale provider keys before launcher spawn", () => {
  const env = {
    KEEP_ME: "1",
    AIWIKI_LLM_BACKEND: "deepseek-api",
    AIWIKI_MODEL_FALLBACK: "stale-model",
    AIWIKI_DEEPSEEK_API_KEY: "stale",
    AIWIKI_OPENCODE_API_KEY: "stale",
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
