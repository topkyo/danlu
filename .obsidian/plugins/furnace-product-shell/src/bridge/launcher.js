// Bridge: CLI spawn integration.
// Extracted from plugin.js — wraps the `python -m aiwiki.cli` child_process spawn.
// Note: spawn, fs, path, buildNotifyEnv, readJsonText are already in the build header.

const PRIMARY_SURFACE_COMMANDS = new Set(["drop", "today", "advanced"]);

const EXEC_LAUNCHER_TIMEOUT_MS = 180_000;
const EXEC_LAUNCHER_MAX_OUTPUT_BYTES = 4 * 1024 * 1024;

function normalizeLauncherArgv(args) {
  const argv = Array.isArray(args) ? args.map((item) => String(item)) : [];
  const command = argv[0] || "";
  if (!command) {
    return argv;
  }
  if (PRIMARY_SURFACE_COMMANDS.has(command)) {
    return argv;
  }
  // Plugin buttons still pass operator verbs; prefix advanced explicitly.
  return ["advanced", ...argv];
}

function execLauncher(plugin, args) {
  if (!plugin.repoState.valid) {
    throw new Error(plugin.t("Missing runtime paths: {missing}", { missing: plugin.repoState.missingPaths.join(", ") }));
  }
  const launcherArgs = normalizeLauncherArgv(args);
  const runtimeRoot = String(plugin.repoState.runtimeRoot || "").trim();
  return new Promise((resolve, reject) => {
    const env = Object.assign({}, process.env);
    env.PATH = guiPatchedPath(env.PATH, env.HOME);
    clearKnownLlmEnv(env);
    Object.assign(env, buildLlmEnv(plugin.settings));
    Object.assign(env, buildNotifyEnv(plugin.settings));
    const vaultRoot = String(plugin.repoState.root || "").trim();
    if (vaultRoot) {
      env.AIWIKI_VAULT = vaultRoot;
    }
    env.PYTHONPATH = path.join(runtimeRoot, "src") + (env.PYTHONPATH ? `${path.delimiter}${env.PYTHONPATH}` : "");
    const pythonBin = resolvePythonBin(env);
    if (!pythonBin) {
      reject(
        new Error(
          plugin.t(
            "aiwiki needs Python >= 3.10, but none was found on PATH. Install a newer Python (for example brew install python@3.13) and retry."
          )
        )
      );
      return;
    }
    const child = spawn(pythonBin, ["-m", "aiwiki.cli", "--root", vaultRoot, ...launcherArgs], {
      cwd: runtimeRoot,
      env,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const killChild = () => {
      try {
        child.kill("SIGTERM");
      } catch (killError) {
        // The child may already be gone; the rejection still applies.
      }
    };
    const settleWithError = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeoutTimer);
      error.stdout = stdout;
      error.stderr = stderr;
      reject(error);
    };
    const timeoutTimer = setTimeout(() => {
      const error = new Error(plugin.t("Command timed out after {ms} ms", { ms: EXEC_LAUNCHER_TIMEOUT_MS }));
      error.code = "timeout";
      settleWithError(error);
      killChild();
    }, EXEC_LAUNCHER_TIMEOUT_MS);
    const failOutputOverflow = () => {
      if (settled) {
        return;
      }
      const error = new Error(plugin.t("Command output exceeded {bytes} bytes", { bytes: EXEC_LAUNCHER_MAX_OUTPUT_BYTES }));
      error.code = "output-overflow";
      settleWithError(error);
      killChild();
    };
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
      if (stdout.length > EXEC_LAUNCHER_MAX_OUTPUT_BYTES) {
        failOutputOverflow();
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
      if (stderr.length > EXEC_LAUNCHER_MAX_OUTPUT_BYTES) {
        failOutputOverflow();
      }
    });
    child.on("error", (error) => {
      settleWithError(error);
    });
    child.on("close", (code) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeoutTimer);
      let payload = null;
      let parseFailed = false;
      try {
        payload = readJsonText(stdout);
      } catch (error) {
        payload = null;
        parseFailed = true;
      }
      if (code === 0) {
        if (parseFailed) {
          console.warn("[furnace-product-shell] CLI returned non-JSON stdout", stdout.slice(0, 200));
        }
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
