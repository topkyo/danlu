---
title: "Furnace RuntimeClient Mobile Companion Design"
kind: "design"
status: "design-done"
updated_at: 2026-07-14
---

# Furnace RuntimeClient Mobile Companion Design

## Context

当前 Product Shell 是 Obsidian Desktop runtime 控制台：UI 调用 Node / Electron bridge，spawn vault-local launcher，再进入 Python CLI。iPad / iOS Obsidian 不提供等价的 shell、Node spawn、Electron 或本机 Python runtime，因此不能把现有插件直接标成移动端全功能。

本设计只完成 M-MOBILE-1 的接口草图；不实现完整 mobile plugin，不改变当前 `isDesktopOnly: true` 主产品边界。

## RuntimeClient 三实现

```text
Product Shell UI
      |
      v
RuntimeClient
  |-- DesktopLauncherClient
  |-- VaultQueueClient
  `-- RemoteHttpClient
```

### 1. DesktopLauncherClient

当前桌面实现的抽象外壳。

- 平台：Mac / Linux / Windows Desktop Obsidian。
- 能力：调用 `scripts/aiwiki-launcher.sh` 或绝对 launcher，执行 drop / ask / compile / nightly / review 等本机 runtime 命令。
- 数据边界：读写本地 vault；API key 和 LLM provider 配置仍在本机插件 / runtime 配置中。
- 状态：M-MOBILE-1 后仍是唯一全功能实现。

### 2. VaultQueueClient

移动 companion 的 local-first 请求投递协议。

- 平台：iPad / iOS / 受限 Obsidian 环境。
- 能力：只把请求写入 vault 内 queue，例如 `.aiwiki/queue/*.json`；由桌面 watcher 或未来私有 runtime drain。
- 数据边界：移动端只写请求和读 summary / reports；不执行 Python、LLM、apply、revert 或 filesystem-heavy ingest。
- 失败模式：queue pending 可见；未被桌面 drain 时不得显示为成功执行。

### 3. RemoteHttpClient

可选的远程 runtime companion。

- 平台：移动端或桌面均可。
- 能力：把请求发送到用户自管或私有 hosted runtime API。
- 数据边界：必须显式说明哪些 vault 内容会离开本机；local-first 仍指 vault / receipt / output 的文件 SoT，不等于所有计算离线。
- 状态：不是本轮前提，不作为默认路线。

## 边界

RuntimeClient 只抽象 Product Shell 到 runtime 的调用方式，不改变核心 runtime 事实分层：

- `raw/` 仍是事实输入层。
- `wiki/sources/` 与 `wiki/derived/` 继续分层。
- `output/control/execution-receipts/` 继续作为执行证据。
- success receipt 只能由真正执行成功的 runtime 写出，VaultQueue pending 不能冒充 success。

## 非目标

- 不把当前 Desktop plugin 改成移动端全功能插件。
- 不在 iPad / iOS 本地运行 Python CLI、PDF ingest、repo ingest、nightly watcher 或 LLM worker。
- 不为移动端强制引入 hosted SaaS。
- 不实现自动交易、行情、回测或投资建议能力。
- 不为了 LOC 指标拆 `drop` / `alchemy` / `graph` 大 hub；移动端设计不驱动 broad rewrite。

## M-MOBILE-1 接口草图

伪代码如下，具体实现可按现有 `src/bridge/launcher.js` 和 run state 模型落地：

```javascript
class RuntimeClient {
  async health() {
    throw new Error("not implemented");
  }

  async ask(request) {
    throw new Error("not implemented");
  }

  async drop(request) {
    throw new Error("not implemented");
  }

  async openArtifact(ref) {
    throw new Error("not implemented");
  }
}

class DesktopLauncherClient extends RuntimeClient {
  constructor({ launcherPath, vaultRoot, settings }) {
    super();
    this.launcherPath = launcherPath;
    this.vaultRoot = vaultRoot;
    this.settings = settings;
  }

  async ask(request) {
    return runLauncher(this.launcherPath, ["ask", request.question, "--format", request.format]);
  }

  async drop(request) {
    return runLauncher(this.launcherPath, ["drop", request.kind, request.source]);
  }
}

class VaultQueueClient extends RuntimeClient {
  constructor({ vaultAdapter, queueDir = ".aiwiki/queue" }) {
    super();
    this.vaultAdapter = vaultAdapter;
    this.queueDir = queueDir;
  }

  async ask(request) {
    return this.enqueue({ type: "ask", request });
  }

  async drop(request) {
    return this.enqueue({ type: "drop", request });
  }

  async enqueue(envelope) {
    const id = crypto.randomUUID();
    const path = `${this.queueDir}/${id}.json`;
    await this.vaultAdapter.write(path, JSON.stringify({
      id,
      status: "pending",
      created_at: new Date().toISOString(),
      ...envelope,
    }, null, 2));
    return { status: "queued", queuePath: path };
  }
}

class RemoteHttpClient extends RuntimeClient {
  constructor({ endpoint, tokenProvider }) {
    super();
    this.endpoint = endpoint;
    this.tokenProvider = tokenProvider;
  }

  async ask(request) {
    return postJson(`${this.endpoint}/ask`, request, await this.tokenProvider());
  }

  async drop(request) {
    return postJson(`${this.endpoint}/drop`, request, await this.tokenProvider());
  }
}
```

## Product wording

- 主产品：Desktop Obsidian + local aiwiki runtime。
- iPad / iOS：未来 companion，只读 summary / reports + 投递请求。
- 不单卖“全功能移动炼丹炉”。
