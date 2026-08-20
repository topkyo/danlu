// State: repo detection and validation.
// Extracted from plugin.js to reduce monolithic Plugin class.
// Note: fs and path are already required in the build header.

function refreshRepoState(plugin) {
  const adapter = plugin.app.vault && plugin.app.vault.adapter;
  const root = adapter && typeof adapter.basePath === "string" ? adapter.basePath : "";
  const runtimeRoot = resolveRuntimeRoot(plugin.settings);
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
    if (!runtimeRootIsUsable(runtimeRoot)) {
      missingPaths.push("runtime-root");
    }
  }
  return {
    valid: missingPaths.length === 0,
    root,
    runtimeRoot,
    missingPaths,
  };
}

function resolveRuntimeRoot(settings) {
  return String((settings && settings.runtimeRoot) || "").trim();
}

function runtimeRootIsUsable(runtimeRoot) {
  if (!runtimeRoot) return false;
  try {
    return fs.existsSync(path.join(runtimeRoot, "src", "aiwiki", "cli", "__main__.py"));
  } catch (e) {
    return false;
  }
}

module.exports = { refreshRepoState, resolveRuntimeRoot, runtimeRootIsUsable };
