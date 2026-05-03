// Bridge: CLI launcher integration.
// Extracted from plugin.js — wraps spawn/child_process calls to the aiwiki launcher.
// Note: spawn, fs, path, buildNotifyEnv, readJsonText are already in the build header.

function execLauncher(plugin, args) {
  if (!plugin.repoState.valid) {
    throw new Error(plugin.t("Missing runtime paths: {missing}", { missing: plugin.repoState.missingPaths.join(", ") }));
  }
  return new Promise((resolve, reject) => {
    const env = Object.assign({}, process.env);
    if (plugin.settings.llmBackend) {
      env.AIWIKI_LLM_BACKEND = plugin.settings.llmBackend;
    }
    if (plugin.settings.llmModel) {
      env.AIWIKI_LLM_MODEL = plugin.settings.llmModel;
    }
    if (plugin.settings.llmNvidiaNimApiKey) {
      env.AIWIKI_NVIDIA_NIM_API_KEY = plugin.settings.llmNvidiaNimApiKey;
    }
    if (plugin.settings.llmNvidiaNimBaseUrl) {
      env.AIWIKI_NVIDIA_NIM_BASE_URL = plugin.settings.llmNvidiaNimBaseUrl;
    }
    Object.assign(env, buildNotifyEnv(plugin.settings));
    const child = spawn(plugin.repoState.launcherPath, args, {
      cwd: plugin.repoState.root,
      env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", (error) => {
      reject(error);
    });
    child.on("close", (code) => {
      let payload = null;
      try {
        payload = readJsonText(stdout);
      } catch (error) {
        payload = null;
      }
      if (code === 0) {
        resolve({ stdout, stderr, payload, code });
        return;
      }
      const error = new Error(stderr.trim() || stdout.trim() || plugin.t("Command failed with exit code {code}", { code }));
      error.code = code;
      error.stdout = stdout;
      error.stderr = stderr;
      error.payload = payload;
      reject(error);
    });
  });
}

function runUiAction(plugin, action) {
  const label = arguments[2] || "ui-action";
  Promise.resolve()
    .then(() => action())
    .catch((error) => {
      console.error(`[furnace-product-shell] ${label} failed`, error);
    });
}

module.exports = { execLauncher, runUiAction };
