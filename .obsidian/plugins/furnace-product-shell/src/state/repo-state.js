// State: repo detection and validation.
// Extracted from plugin.js to reduce monolithic Plugin class.
// Note: fs and path are already required in the build header.

function refreshRepoState(plugin) {
  const adapter = plugin.app.vault && plugin.app.vault.adapter;
  const root = adapter && typeof adapter.basePath === "string" ? adapter.basePath : "";
  const launcherPath = resolveLauncherPath(root, plugin.settings);
  const missingPaths = [];
  if (!root) {
    missingPaths.push("vault-root");
  } else {
    [
      "raw",
      "wiki",
      "schema",
      "output",
      ".aiwiki",
    ].forEach((relativePath) => {
      if (!fs.existsSync(path.join(root, relativePath))) {
        missingPaths.push(relativePath);
      }
    });
    if (!launcherIsExecutable(launcherPath)) {
      missingPaths.push(plugin.settings.launcherPath);
    }
  }
  return {
    valid: missingPaths.length === 0,
    root,
    launcherPath,
    missingPaths,
  };
}

function resolveLauncherPath(root, settings) {
  const launcherPath = String((settings && settings.launcherPath) || (typeof DEFAULT_SETTINGS !== "undefined" ? DEFAULT_SETTINGS.launcherPath : "")).trim();
  if (!root || !launcherPath) {
    return "";
  }
  if (path.isAbsolute(launcherPath)) {
    return launcherPath;
  }
  return path.join(root, launcherPath);
}

function launcherIsExecutable(launcherPath) {
  if (!launcherPath) return false;
  try {
    fs.accessSync(launcherPath, fs.constants.X_OK);
    return true;
  } catch (e) {
    return false;
  }
}

module.exports = { refreshRepoState, resolveLauncherPath, launcherIsExecutable };
