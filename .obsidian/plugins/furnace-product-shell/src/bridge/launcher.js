// Bridge: CLI launcher integration.
// Extracted from plugin.js — wraps spawn/child_process calls to the aiwiki launcher.
// Note: spawn, fs, path, buildNotifyEnv, readJsonText are already in the build header.

const PRIMARY_SURFACE_COMMANDS = new Set(["drop", "today", "metrics", "advanced"]);
const PRIMARY_DROP_REPLACEMENTS = {
  "drop-url": ["drop", "url"],
  "drop-pdf": ["drop", "pdf"],
  "drop-image": ["drop", "image"],
  "drop-repo": ["drop", "repo"],
  "drop-note": ["drop", "markdown"],
};

function normalizeLauncherArgv(args) {
  const argv = Array.isArray(args) ? args.map((item) => String(item)) : [];
  const command = argv[0] || "";
  if (!command || PRIMARY_SURFACE_COMMANDS.has(command)) {
    return argv;
  }
  const dropReplacement = PRIMARY_DROP_REPLACEMENTS[command];
  if (dropReplacement) {
    return dropReplacement.concat(argv.slice(1));
  }
  return ["advanced", ...argv];
}

function execLauncher(plugin, args) {
  if (!plugin.repoState.valid) {
    throw new Error(plugin.t("Missing runtime paths: {missing}", { missing: plugin.repoState.missingPaths.join(", ") }));
  }
  const launcherArgs = normalizeLauncherArgv(args);
  return new Promise((resolve, reject) => {
    const env = Object.assign({}, process.env);
    clearKnownLlmEnv(env);
    Object.assign(env, buildLlmEnv(plugin.settings));
    Object.assign(env, buildNotifyEnv(plugin.settings));
    const child = spawn(plugin.repoState.launcherPath, launcherArgs, {
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

module.exports = { execLauncher, runUiAction, normalizeLauncherArgv };
