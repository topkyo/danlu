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
    "opencode-api",
    "nvidia-nim-api",
    "openrouter-api",
    "anthropic-api",
  ]);
  expect(LLM_PROVIDER_PROFILES.slice(4).every((profile) => profile.tier === "advanced")).toBe(true);
});

test("buildLlmEnv only emits the selected provider secret and base URL", () => {
  const env = buildLlmEnv({
    llmBackend: "openrouter-api",
    llmModel: "anthropic/claude-sonnet-4",
    llmOpencodeApiKey: "opencode-stale",
    llmNvidiaNimApiKey: "nvapi-stale",
    llmOpenrouterApiKey: "sk-or-current",
    llmOpenrouterBaseUrl: "https://router.example/v1",
  });

  expect(env).toEqual({
    AIWIKI_LLM_BACKEND: "openrouter-api",
    AIWIKI_LLM_MODEL: "anthropic/claude-sonnet-4",
    AIWIKI_OPENROUTER_API_KEY: "sk-or-current",
    AIWIKI_OPENROUTER_BASE_URL: "https://router.example/v1",
  });
});

test("buildLlmEnv replaces stale default model when provider changes", () => {
  expect(buildLlmEnv({ llmBackend: "nvidia-nim-api", llmModel: "deepseek-v4-pro" })).toEqual({
    AIWIKI_LLM_BACKEND: "nvidia-nim-api",
    AIWIKI_LLM_MODEL: "openai/gpt-oss-120b",
  });
});

test("CLI providers do not require model or API key fields", () => {
  const profile = llmProviderProfile("codex-cli");
  expect(profile.cliHint).toContain("codex login");
  expect(llmProviderNeedsModel(profile)).toBe(false);
  expect(buildLlmEnv({ llmBackend: "codex-cli", llmModel: "gpt-5.5", llmOpencodeApiKey: "stale" })).toEqual({
    AIWIKI_LLM_BACKEND: "codex-cli",
    AIWIKI_LLM_MODEL: "gpt-5.5",
  });
});

test("clearKnownLlmEnv removes stale provider keys before launcher spawn", () => {
  const env = {
    KEEP_ME: "1",
    AIWIKI_LLM_BACKEND: "nvidia-nim-api",
    AIWIKI_NVIDIA_NIM_API_KEY: "stale",
    AIWIKI_OPENCODE_API_KEY: "stale",
  };
  clearKnownLlmEnv(env);
  expect(env).toEqual({ KEEP_ME: "1" });
});

test("dropLegacyLlmSettings removes old unused key fields", () => {
  const settings = {
    llmGithubToken: "gh",
    llmGithubModelsBaseUrl: "https://models",
    llmApiKey: "old",
    llmAnthropicApiKey: "old-ant",
    llmOpencodeApiKey: "current",
  };
  expect(dropLegacyLlmSettings(settings)).toBe(true);
  expect(settings).toEqual({ llmOpencodeApiKey: "current" });
  expect(dropLegacyLlmSettings(settings)).toBe(false);
});
