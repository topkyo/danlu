// Extracted from plugin.js

async function runCompileCommand(plugin) {
    await plugin.runPluginCommand(plugin.t("Compile"), ["compile"], { refreshAfter: true });
  }


async function runNightlyCommand(plugin) {
    await plugin.runPluginCommand(plugin.t("Nightly"), ["nightly"], { refreshAfter: true });
  }


async function runTodaySnoozeCommand(plugin, target, days = 1) {
    const normalizedTarget = String(target || "").trim();
    if (!normalizedTarget) {
      return;
    }
    await plugin.runPluginCommand(
      `${plugin.t("Snooze")}: ${truncateText(normalizedTarget, 48)}`,
      ["today-snooze", normalizedTarget, "--days", String(days)],
      { refreshAfter: true }
    );
  }


async function runApplyAllAcceptedLowRiskCommand(plugin) {
    await plugin.runCliAction(plugin.t("Apply All Low-Risk"), "apply-action", ["--all-accepted-low-risk"]);
  }


async function runRevertLastBatchCommand(plugin) {
    await plugin.runCliAction(plugin.t("Revert Last Batch"), "revert-action", ["--last-batch"]);
  }


async function openHomeNote(plugin) {
    await plugin.openWorkspacePath("HOME.md");
  }


async function runProtocolSetCommand(plugin, protocol) {
    await plugin.runPluginCommand(`${plugin.t("Set Protocol")}: ${protocol}`, ["protocol-set", protocol], { refreshAfter: true });
  }


async function runAskCommand(plugin, { question, format, mode, protocol }) {
    const args = [mode, question, "--format", format];
    if (protocol) {
      args.push("--protocol", protocol);
    }
    if (mode === "run-ask") {
      args.push("--fallback-to-ask");
    }
    return await plugin.runPluginCommand(`${plugin.t("Ask")}: ${truncateText(question, 48)}`, args, { refreshAfter: true });
  }


async function runDropUrlCommand(plugin, { url, title }) {
    const args = ["drop", "url", url];
    if (title) {
      args.push("--title", title);
    }
    await plugin.runPluginCommand(`${plugin.t("Drop URL")}: ${truncateText(title || url, 48)}`, args, { refreshAfter: true });
  }


async function runDropFileCommand(plugin, { mode, source, title, maxFiles }) {
    const normalizedMode = String(mode || "pdf").trim() === "repo" ? "repo" : "pdf";
    const args = ["drop", normalizedMode === "repo" ? "repo" : "pdf", source];
    if (title) {
      args.push("--title", title);
    }
    if (normalizedMode === "repo") {
      args.push("--max-files", String(Number.isFinite(Number(maxFiles)) && Number(maxFiles) > 0 ? Number(maxFiles) : 200));
    }
    await plugin.runPluginCommand(`${plugin.t("Drop File")}: ${truncateText(title || path.basename(source) || source, 48)}`, args, { refreshAfter: true });
  }


async function runDropImageCommand(plugin, { source, title, noVision }) {
    const args = ["drop", "image", source];
    if (title) {
      args.push("--title", title);
    }
    if (noVision) {
      args.push("--no-vision");
    }
    await plugin.runPluginCommand(`${plugin.t("Drop Image")}: ${truncateText(title || path.basename(source) || source, 48)}`, args, { refreshAfter: true });
  }


async function runDropNoteCommand(plugin, { text, title, kind }) {
    const args = ["drop", "note", "--text", text];
    if (title) {
      args.push("--title", title);
    }
    args.push("--kind", kind || "note");
    await plugin.runPluginCommand(`${plugin.t("Capture Note")}: ${truncateText(title || text, 48)}`, args, { refreshAfter: true });
  }


async function runCliAction(plugin, label, command, args = []) {
    await plugin.runPluginCommand(label, [command, ...args], { refreshAfter: true });
  }


async function runLauncherCommand(plugin, fullCommandStr, label = "Suggested Action") {
    // Extract CLI subcommand+args from a full command string like:
    //   "PYTHONPATH=src python3 -m aiwiki.cli --root . review-action foo --status accepted"
    // The launcher already sets PYTHONPATH and --root, so we strip the prefix.
    let trimmed = String(fullCommandStr || "").trim();
    const prefixPattern = /^(?:PYTHONPATH=\S+\s+)?(?:python3?\s+-m\s+aiwiki\.cli\s+)?(?:--root\s+\S+\s+)?/;
    trimmed = trimmed.replace(prefixPattern, "").trim();
    if (!trimmed) {
      new Notice(plugin.t("Cannot parse command: {command}", { command: truncateText(fullCommandStr, 80) }));
      return;
    }
    // Simple shell-like split respecting double quotes
    const args = [];
    let current = "";
    let inQuote = false;
    for (let i = 0; i < trimmed.length; i++) {
      const ch = trimmed[i];
      if (ch === '"') {
        inQuote = !inQuote;
      } else if (ch === " " && !inQuote) {
        if (current) {
          args.push(current);
          current = "";
        }
      } else {
        current += ch;
      }
    }
    if (current) {
      args.push(current);
    }
    await plugin.runPluginCommand(label, args, { refreshAfter: true });
  }


module.exports = { runCompileCommand, runNightlyCommand, runTodaySnoozeCommand, runApplyAllAcceptedLowRiskCommand, runRevertLastBatchCommand, openHomeNote, runProtocolSetCommand, runAskCommand, runDropUrlCommand, runDropFileCommand, runDropImageCommand, runDropNoteCommand, runCliAction, runLauncherCommand };
