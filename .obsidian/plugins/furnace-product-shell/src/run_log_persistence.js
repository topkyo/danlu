// Product Shell run-log persistence helpers.

function resolveProductShellRunLogPath(repoRoot, relativePath) {
  const normalized = String(relativePath || "").trim();
  const root = String(repoRoot || "").trim();
  if (!normalized || !root) {
    return "";
  }
  return path.join(root, normalized);
}

function persistProductShellRunLog({ record, details = {}, t, repoRoot = "" }) {
  // Retired: do not write Obsidian-visible output/control/plugin-runs/*.md.
  // Unbounded per-run markdown (stdout dumps) bloated the vault and fought
  // Obsidian indexing. Canonical run history lives in .aiwiki/logs/runs.jsonl
  // plus in-memory recentRuns; renderProductShellRunLog remains for tests.
  void details;
  void t;
  void repoRoot;
  if (record && typeof record === "object") {
    record.logPath = "";
  }
  return "";
}
