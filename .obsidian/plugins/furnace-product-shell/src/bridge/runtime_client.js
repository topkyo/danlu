// Bridge: runtime client for desktop launcher.

const RUNTIME_CLIENT_DESKTOP_LAUNCHER = "desktop-launcher";

function createRuntimeClient(plugin) {
  return new DesktopLauncherClient(plugin);
}

class DesktopLauncherClient {
  constructor(plugin) {
    this.plugin = plugin;
    this.mode = RUNTIME_CLIENT_DESKTOP_LAUNCHER;
  }

  async exec(args) {
    return execLauncher(this.plugin, args);
  }

  async ask(request) {
    return this.exec(runtimeClientRequestArgs("run-ask", request));
  }

  async drop(request) {
    return this.exec(runtimeClientRequestArgs("drop", request));
  }

  async summary() {
    return this.exec(["shell-status"]);
  }
}

function runtimeClientRequestArgs(command, request) {
  const payload = request && typeof request === "object" ? request : {};
  if (command === "ask" || command === "run-ask") {
    const question = String(payload.question || "").trim();
    const args = [command === "ask" ? "run-ask" : command, question];
    if (payload.format) args.push("--format", String(payload.format));
    return args;
  }
  const source = String(payload.source || payload.url || payload.path || "").trim();
  const args = ["drop", String(payload.kind || "markdown"), source];
  if (payload.title) args.push("--title", String(payload.title));
  return args;
}

module.exports = {
  DesktopLauncherClient,
  createRuntimeClient,
};
