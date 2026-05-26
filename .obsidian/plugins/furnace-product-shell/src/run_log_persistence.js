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
  const rendered = renderProductShellRunLog({
    record,
    details,
    t,
    repoRoot: repoRoot || ".",
  });
  if (!rendered) {
    return "";
  }
  const absolutePath = resolveProductShellRunLogPath(repoRoot, rendered.logPath);
  if (!absolutePath) {
    return "";
  }
  record.logPath = rendered.logPath;
  fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
  fs.writeFileSync(absolutePath, rendered.content, "utf8");
  return rendered.logPath;
}
