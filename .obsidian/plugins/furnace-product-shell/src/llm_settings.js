// LLM provider profile helpers shared by settings UI and launcher bridge.

const DEFAULT_PRODUCT_LLM_BACKEND = "opencode-api";
const DEFAULT_PRODUCT_LLM_MODEL = "deepseek-v4-pro";

const LLM_PROVIDER_PROFILES = [
  {
    value: "opencode-api",
    label: "OpenCode",
    tier: "common",
    apiKeySetting: "llmOpencodeApiKey",
    apiKeyEnv: "AIWIKI_OPENCODE_API_KEY",
    baseUrlSetting: "llmOpencodeBaseUrl",
    baseUrlEnv: "AIWIKI_OPENCODE_BASE_URL",
    defaultBaseUrl: "https://opencode.ai/zen/go/v1",
    defaultModel: DEFAULT_PRODUCT_LLM_MODEL,
    keyPlaceholder: "opencode-...",
  },
  {
    value: "nvidia-nim-api",
    label: "NVIDIA NIM",
    tier: "common",
    apiKeySetting: "llmNvidiaNimApiKey",
    apiKeyEnv: "AIWIKI_NVIDIA_NIM_API_KEY",
    baseUrlSetting: "llmNvidiaNimBaseUrl",
    baseUrlEnv: "AIWIKI_NVIDIA_NIM_BASE_URL",
    defaultBaseUrl: "https://integrate.api.nvidia.com/v1",
    defaultModel: "openai/gpt-oss-120b",
    keyPlaceholder: "nvapi-...",
  },
  {
    value: "openrouter-api",
    label: "OpenRouter",
    tier: "common",
    apiKeySetting: "llmOpenrouterApiKey",
    apiKeyEnv: "AIWIKI_OPENROUTER_API_KEY",
    baseUrlSetting: "llmOpenrouterBaseUrl",
    baseUrlEnv: "AIWIKI_OPENROUTER_BASE_URL",
    defaultBaseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "",
    keyPlaceholder: "sk-or-...",
  },
  {
    value: "anthropic-api",
    label: "Anthropic",
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
    value: "codex-cli",
    label: "Codex CLI",
    tier: "advanced",
    cliHint: "Run `codex login` in a terminal session visible to Obsidian.",
  },
  {
    value: "copilot-cli",
    label: "Copilot CLI",
    tier: "advanced",
    cliHint: "Run `copilot login`; org policy and seat availability are checked by `llm-check --probe`.",
  },
  {
    value: "claude-cli",
    label: "Claude CLI",
    tier: "advanced",
    cliHint: "Run `claude` login/session setup before using this backend.",
  },
  {
    value: "openai-api",
    label: "Custom OpenAI-compatible",
    tier: "advanced",
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
  LLM_PROVIDER_PROFILES.map((profile) => profile.defaultModel).filter(Boolean)
);
const LLM_ENV_KEYS = [
  "AIWIKI_LLM_BACKEND",
  "AIWIKI_LLM_MODEL",
  "AIWIKI_OPENCODE_API_KEY",
  "AIWIKI_OPENCODE_BASE_URL",
  "AIWIKI_NVIDIA_NIM_API_KEY",
  "AIWIKI_NVIDIA_NIM_BASE_URL",
  "AIWIKI_OPENROUTER_API_KEY",
  "AIWIKI_OPENROUTER_BASE_URL",
  "AIWIKI_ANTHROPIC_API_KEY",
  "AIWIKI_ANTHROPIC_BASE_URL",
  "AIWIKI_LLM_API_KEY",
  "AIWIKI_LLM_BASE_URL",
];
const LEGACY_LLM_SETTING_KEYS = [
  "llmGithubToken",
  "llmGithubModelsBaseUrl",
  "llmApiKey",
  "llmAnthropicApiKey",
];

function llmProviderProfile(value) {
  return LLM_PROVIDER_BY_VALUE[String(value || "").trim()] || LLM_PROVIDER_BY_VALUE[DEFAULT_PRODUCT_LLM_BACKEND];
}

function llmProviderNeedsModel(profile) {
  return Boolean(profile && !profile.cliHint);
}

function effectiveLlmModelForProvider(settings, profile) {
  const configured = String((settings && settings.llmModel) || "").trim();
  if (!configured) {
    return String((profile && profile.defaultModel) || "").trim();
  }
  const profileDefault = String((profile && profile.defaultModel) || "").trim();
  if (profileDefault && configured !== profileDefault && LLM_PROVIDER_DEFAULT_MODELS.has(configured)) {
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
