// LLM provider profile helpers shared by settings UI and launcher bridge.

const DEFAULT_PRODUCT_LLM_BACKEND = "deepseek-api";
const DEFAULT_PRODUCT_LLM_MODEL = "deepseek-v4-flash";
const LEGACY_PRODUCT_LLM_MODEL = "deepseek-v4-pro";

const LLM_PROVIDER_PROFILES = [
  {
    value: "deepseek-api",
    label: "DeepSeek",
    tier: "common",
    apiKeySetting: "llmDeepseekApiKey",
    apiKeyEnv: "AIWIKI_DEEPSEEK_API_KEY",
    baseUrlSetting: "llmDeepseekBaseUrl",
    baseUrlEnv: "AIWIKI_DEEPSEEK_BASE_URL",
    defaultBaseUrl: "https://api.deepseek.com",
    defaultModel: DEFAULT_PRODUCT_LLM_MODEL,
    keyPlaceholder: "sk-...",
  },
  {
    value: "opencode-api",
    label: "OpenCode",
    tier: "common",
    apiKeySetting: "llmOpencodeApiKey",
    apiKeyEnv: "AIWIKI_OPENCODE_API_KEY",
    baseUrlSetting: "llmOpencodeBaseUrl",
    baseUrlEnv: "AIWIKI_OPENCODE_BASE_URL",
    defaultBaseUrl: "https://opencode.ai/zen/go/v1",
    defaultModel: "deepseek-v4-pro",
    keyPlaceholder: "opencode-...",
  },
  {
    value: "anthropic-api",
    label: "Claude",
    tier: "common",
    apiKeySetting: "llmAnthropicApiKey",
    apiKeyEnv: "AIWIKI_ANTHROPIC_API_KEY",
    baseUrlSetting: "llmAnthropicBaseUrl",
    baseUrlEnv: "AIWIKI_ANTHROPIC_BASE_URL",
    defaultBaseUrl: "https://api.anthropic.com",
    defaultModel: "claude-sonnet-4-20250514",
    keyPlaceholder: "sk-ant-...",
  },
  {
    value: "openai-api",
    label: "OpenAI",
    tier: "common",
    apiKeySetting: "llmCustomOpenaiApiKey",
    apiKeyEnv: "AIWIKI_LLM_API_KEY",
    baseUrlSetting: "llmCustomOpenaiBaseUrl",
    baseUrlEnv: "AIWIKI_LLM_BASE_URL",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4.1-mini",
    keyPlaceholder: "sk-...",
  },
];

const LLM_PROVIDER_BY_VALUE = Object.fromEntries(LLM_PROVIDER_PROFILES.map((profile) => [profile.value, profile]));
const LLM_PROVIDER_DEFAULT_MODELS = new Set(
  [
    ...LLM_PROVIDER_PROFILES.map((profile) => profile.defaultModel).filter(Boolean),
    LEGACY_PRODUCT_LLM_MODEL,
  ]
);
const LLM_ENV_KEYS = [
  "AIWIKI_LLM_BACKEND",
  "AIWIKI_LLM_MODEL",
  "AIWIKI_MODEL_FALLBACK",
  "AIWIKI_DEEPSEEK_API_KEY",
  "AIWIKI_DEEPSEEK_BASE_URL",
  "AIWIKI_OPENCODE_API_KEY",
  "AIWIKI_OPENCODE_BASE_URL",
  "AIWIKI_ANTHROPIC_API_KEY",
  "AIWIKI_ANTHROPIC_BASE_URL",
  "AIWIKI_LLM_API_KEY",
  "AIWIKI_LLM_BASE_URL",
  "DEEPSEEK_API_KEY",
  "DEEPSEEK_BASE_URL",
  "OPENAI_API_KEY",
  "OPENAI_BASE_URL",
  "OPENAI_MODEL",
  "ANTHROPIC_API_KEY",
  "ANTHROPIC_BASE_URL",
];
const LEGACY_LLM_SETTING_KEYS = [
  "llmGithubToken",
  "llmGithubModelsBaseUrl",
  "llmApiKey",
  "llmNvidiaNimApiKey",
  "llmNvidiaNimBaseUrl",
  "llmOpenrouterApiKey",
  "llmOpenrouterBaseUrl",
];

function llmProviderProfile(value) {
  return LLM_PROVIDER_BY_VALUE[String(value || "").trim()] || LLM_PROVIDER_BY_VALUE[DEFAULT_PRODUCT_LLM_BACKEND];
}

function llmProviderNeedsModel(profile) {
  return Boolean(profile);
}

function effectiveLlmModelForProvider(settings, profile) {
  const configured = String((settings && settings.llmModel) || "").trim();
  if (!configured) {
    return String((profile && profile.defaultModel) || "").trim();
  }
  const profileDefault = String((profile && profile.defaultModel) || "").trim();
  if (profileDefault && configured !== profileDefault && LLM_PROVIDER_DEFAULT_MODELS.has(configured)) {
    if (profile.value === "deepseek-api" && configured === LEGACY_PRODUCT_LLM_MODEL) {
      return configured;
    }
    return profileDefault;
  }
  return configured;
}

function buildLlmEnv(settings) {
  const profile = llmProviderProfile(settings && settings.llmBackend);
  const env = {
    AIWIKI_LLM_BACKEND: profile.value,
  };
  const model = effectiveLlmModelForProvider(settings, profile);
  if (model) {
    env.AIWIKI_LLM_MODEL = model;
  }
  if (profile.apiKeySetting && profile.apiKeyEnv) {
    const key = String((settings && settings[profile.apiKeySetting]) || "").trim();
    if (key) {
      env[profile.apiKeyEnv] = key;
    }
  }
  if (profile.baseUrlSetting && profile.baseUrlEnv) {
    const baseUrl = String((settings && settings[profile.baseUrlSetting]) || "").trim();
    if (baseUrl) {
      env[profile.baseUrlEnv] = baseUrl;
    }
  }
  return env;
}

function clearKnownLlmEnv(env) {
  for (const key of LLM_ENV_KEYS) {
    delete env[key];
  }
}

function dropLegacyLlmSettings(settings) {
  if (!settings || typeof settings !== "object") {
    return false;
  }
  let changed = false;
  for (const key of LEGACY_LLM_SETTING_KEYS) {
    if (Object.prototype.hasOwnProperty.call(settings, key)) {
      delete settings[key];
      changed = true;
    }
  }
  return changed;
}

if (typeof module !== "undefined") {
  module.exports = {
    DEFAULT_PRODUCT_LLM_BACKEND,
    DEFAULT_PRODUCT_LLM_MODEL,
    LEGACY_LLM_SETTING_KEYS,
    LLM_ENV_KEYS,
    LLM_PROVIDER_PROFILES,
    buildLlmEnv,
    clearKnownLlmEnv,
    dropLegacyLlmSettings,
    effectiveLlmModelForProvider,
    llmProviderNeedsModel,
    llmProviderProfile,
  };
}
