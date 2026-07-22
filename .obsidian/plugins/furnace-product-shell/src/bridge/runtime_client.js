// Bridge: runtime client abstraction for desktop launcher and vault queue.

const RUNTIME_CLIENT_DESKTOP_LAUNCHER = "desktop-launcher";
const RUNTIME_CLIENT_VAULT_QUEUE = "vault-queue";
const VAULT_QUEUE_DIR = ".aiwiki/queue";
const VAULT_QUEUE_SUPPORTED_COMMANDS = new Set(["run-ask", "drop"]);

function normalizeRuntimeClientMode(value) {
  return value === RUNTIME_CLIENT_VAULT_QUEUE ? RUNTIME_CLIENT_VAULT_QUEUE : RUNTIME_CLIENT_DESKTOP_LAUNCHER;
}

function createRuntimeClient(plugin) {
  const mode = normalizeRuntimeClientMode(plugin && plugin.settings && plugin.settings.runtimeClientMode);
  if (mode === RUNTIME_CLIENT_VAULT_QUEUE) {
    return new VaultQueueClient(plugin);
  }
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

class VaultQueueClient {
  constructor(plugin) {
    this.plugin = plugin;
    this.mode = RUNTIME_CLIENT_VAULT_QUEUE;
    this.queueDir = VAULT_QUEUE_DIR;
  }

  async exec(args) {
    const argv = normalizeRuntimeClientArgv(args);
    const command = argv[0] || "";
    if (command === "shell-status") {
      return this.readSummary();
    }
    if (!VAULT_QUEUE_SUPPORTED_COMMANDS.has(command)) {
      throw new Error(`Vault queue runtime cannot execute ${command || "empty command"}; only shell-status is read-only and run-ask/drop/note are queued.`);
    }
    return this.enqueue(runtimeClientQueueKind(argv), { argv });
  }

  async ask(request) {
    return this.enqueue("ask", { request, argv: runtimeClientRequestArgs("run-ask", request) });
  }

  async drop(request) {
    const payload = request && typeof request === "object" ? request : {};
    const kind = String(payload.kind || "markdown").trim().toLowerCase();
    const argv = runtimeClientRequestArgs("drop", payload);
    if (!kind || kind === "markdown" || kind === "note") {
      return this.enqueue("note", { request: payload, argv });
    }
    return this.enqueue("drop", { request: payload, argv });
  }

  async readSummary() {
    const payload = await readVaultJson(this.plugin, SHELL_SUMMARY_PATH);
    const stdout = payload ? `${JSON.stringify(payload, null, 2)}\n` : "";
    return { stdout, stderr: "", payload, code: 0 };
  }

  async enqueue(kind, payload) {
    const normalizedKind = kind === "ask" || kind === "note" ? kind : "drop";
    const id = createVaultQueueId();
    const queuePath = `${this.queueDir}/${id}.json`;
    const item = {
      version: 1,
      id,
      kind: normalizedKind,
      created_at: new Date().toISOString(),
      payload: payload && typeof payload === "object" ? payload : {},
      status: "pending",
      source: "companion",
    };
    await writeVaultJson(this.plugin, queuePath, item);
    const result = {
      kind: "vault-queue",
      status: "queued",
      queue_path: queuePath,
      id,
    };
    return {
      stdout: `${JSON.stringify(result, null, 2)}\n`,
      stderr: "",
      payload: result,
      code: 0,
    };
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

function normalizeRuntimeClientArgv(args) {
  return Array.isArray(args) ? args.map((value) => String(value || "")) : [];
}

function runtimeClientQueueKind(argv) {
  const command = argv[0] || "";
  if (command === "ask" || command === "run-ask") {
    return "ask";
  }
  if (command === "drop") {
    const subcommand = String(argv[1] || "").trim();
    if (!subcommand || subcommand === "markdown" || subcommand === "note") {
      return "note";
    }
    return "drop";
  }
  return "drop";
}

function createVaultQueueId() {
  const cryptoApi = typeof globalThis !== "undefined" && globalThis.crypto ? globalThis.crypto : null;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  return `queue-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function vaultAdapter(plugin) {
  return plugin && plugin.app && plugin.app.vault && plugin.app.vault.adapter
    ? plugin.app.vault.adapter
    : null;
}

async function ensureVaultDir(plugin, dirPath) {
  const adapter = vaultAdapter(plugin);
  if (adapter && typeof adapter.mkdir === "function") {
    const parts = String(dirPath || "").split("/").filter(Boolean);
    let current = "";
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      if (typeof adapter.exists === "function" && await adapter.exists(current)) {
        continue;
      }
      try {
        await adapter.mkdir(current);
      } catch (error) {
        if (!(typeof adapter.exists === "function" && await adapter.exists(current))) {
          throw error;
        }
      }
    }
    return;
  }
  const root = pluginVaultRoot(plugin);
  if (!root) {
    throw new Error("Vault root is unavailable; cannot create vault queue.");
  }
  nodeFs().mkdirSync(nodePath().join(root, dirPath), { recursive: true });
}

async function writeVaultJson(plugin, relativePath, value) {
  const content = `${JSON.stringify(value, null, 2)}\n`;
  const dir = relativePath.split("/").slice(0, -1).join("/");
  if (dir) {
    await ensureVaultDir(plugin, dir);
  }
  const adapter = vaultAdapter(plugin);
  if (adapter && typeof adapter.write === "function") {
    await adapter.write(relativePath, content);
    return;
  }
  const root = pluginVaultRoot(plugin);
  if (!root) {
    throw new Error("Vault root is unavailable; cannot write vault queue item.");
  }
  nodeFs().writeFileSync(nodePath().join(root, relativePath), content, "utf8");
}

async function readVaultJson(plugin, relativePath) {
  let text = "";
  const adapter = vaultAdapter(plugin);
  if (adapter && typeof adapter.read === "function") {
    if (typeof adapter.exists === "function" && !(await adapter.exists(relativePath))) {
      return null;
    }
    text = await adapter.read(relativePath);
  } else {
    const root = pluginVaultRoot(plugin);
    if (!root) return null;
    const absolute = nodePath().join(root, relativePath);
    if (!nodeFs().existsSync(absolute)) return null;
    text = nodeFs().readFileSync(absolute, "utf8");
  }
  if (!String(text || "").trim()) {
    return null;
  }
  return JSON.parse(text);
}

module.exports = {
  DesktopLauncherClient,
  VaultQueueClient,
  createRuntimeClient,
  normalizeRuntimeClientMode,
};
