// Bridge: Python interpreter resolution for CLI spawns.
// Ported from the retired scripts/aiwiki-launcher.sh: Obsidian GUI launches often
// get a minimal PATH where `python3` is Apple /usr/bin/python3 (3.9), so we prefer
// an explicit >=3.10 interpreter.
// Note: spawnSync, fs, path are provided by the build header.

function guiPatchedPath(pathValue, homeDir) {
  const candidates = [];
  if (homeDir) {
    candidates.push(`${homeDir}/.local/bin`, `${homeDir}/.local/npm/bin`, `${homeDir}/bin`);
  }
  candidates.push("/usr/local/bin", "/opt/homebrew/bin");
  const entries = String(pathValue || "").split(":").filter(Boolean);
  for (const candidate of candidates) {
    if (!entries.includes(candidate) && fs.existsSync(candidate)) {
      entries.unshift(candidate);
    }
  }
  return entries.join(":");
}

function pythonBinSupportsAiwiki(bin, env) {
  try {
    const result = spawnSync(bin, ["-c", 'import sys; print("%d.%d" % sys.version_info[:2])'], {
      env,
      encoding: "utf8",
      timeout: 10000,
    });
    if (result.error || result.status !== 0) {
      return false;
    }
    const match = String(result.stdout || "").trim().match(/^(\d+)\.(\d+)$/);
    if (!match) {
      return false;
    }
    const major = Number(match[1]);
    const minor = Number(match[2]);
    return major > 3 || (major === 3 && minor >= 10);
  } catch (error) {
    return false;
  }
}

let cachedPythonBin = "";

function resolvePythonBin(env) {
  if (cachedPythonBin) {
    return cachedPythonBin;
  }
  const homeDir = String((env && env.HOME) || process.env.HOME || "").trim();
  const explicit = String((env && env.AIWIKI_PYTHON) || "").trim();
  const candidates = [
    explicit,
    "/usr/local/bin/python3",
    "/opt/homebrew/bin/python3",
    homeDir ? `${homeDir}/.local/bin/python3` : "",
    "python3.14",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3.10",
    "python3",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (pythonBinSupportsAiwiki(candidate, env)) {
      cachedPythonBin = candidate;
      return candidate;
    }
  }
  return "";
}

function resetResolvedPythonBinForTests() {
  cachedPythonBin = "";
}

if (typeof module !== "undefined") {
  module.exports = {
    guiPatchedPath,
    pythonBinSupportsAiwiki,
    resolvePythonBin,
    resetResolvedPythonBinForTests,
  };
}
