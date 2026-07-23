"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

function installObsidianHTMLElementPolyfills() {
  if (!HTMLElement.prototype.createDiv) {
    HTMLElement.prototype.createDiv = function (opts = {}) {
      const el = document.createElement("div");
      if (opts.cls) el.className = opts.cls;
      if (opts.text) el.textContent = opts.text;
      if (opts.attr) {
        Object.entries(opts.attr).forEach(([key, value]) => el.setAttribute(key, value));
      }
      this.appendChild(el);
      return el;
    };
  }
  if (!HTMLElement.prototype.createEl) {
    HTMLElement.prototype.createEl = function (tag, opts = {}) {
      const el = document.createElement(tag);
      if (opts.cls) el.className = opts.cls;
      if (opts.text) el.textContent = opts.text;
      if (opts.attr) {
        Object.entries(opts.attr).forEach(([key, value]) => el.setAttribute(key, value));
      }
      this.appendChild(el);
      return el;
    };
  }
  if (!HTMLElement.prototype.createSpan) {
    HTMLElement.prototype.createSpan = function (opts = {}) {
      return this.createEl("span", opts);
    };
  }
  if (!HTMLElement.prototype.setText) {
    HTMLElement.prototype.setText = function (text) {
      this.textContent = String(text || "");
      return this;
    };
  }
  if (!HTMLElement.prototype.empty) {
    HTMLElement.prototype.empty = function () {
      this.innerHTML = "";
      return this;
    };
  }
  if (!HTMLElement.prototype.addClass) {
    HTMLElement.prototype.addClass = function (cls) {
      this.classList.add(cls);
      return this;
    };
  }
  if (!HTMLElement.prototype.removeClass) {
    HTMLElement.prototype.removeClass = function (cls) {
      this.classList.remove(cls);
      return this;
    };
  }
  if (!HTMLElement.prototype.setAttr) {
    HTMLElement.prototype.setAttr = function (key, value) {
      this.setAttribute(key, value);
      return this;
    };
  }
}

function loadRenderContext() {
  const notices = [];
  const context = {
    console,
    require,
    fs,
    path,
    window,
    document,
    navigator,
    HTMLElement,
    Node,
    Event: window.Event,
    KeyboardEvent: window.KeyboardEvent,
    Date,
    Math,
    Intl,
    Array,
    String,
    Boolean,
    Number,
    Object,
    JSON,
    RegExp,
    Promise,
    setTimeout,
    clearTimeout,
    module: { exports: {} },
    exports: {},
    DEFAULT_LOCALE: "zh",
    ZH_TEXT: {},
    CURATED_STATUS_LABELS: {},
    ACTION_STATUS_LABELS: {},
    REWRITE_STATUS_LABELS: {},
    REVIEW_REASON_LABELS: {},
    Notice: class Notice {
      constructor(message) {
        this.message = message;
        notices.push(message);
      }
    },
    Plugin: class Plugin {},
    isHttpUrl(value) {
      return /^https?:\/\//i.test(String(value || "").trim());
    },
  };

  const loadFile = (relativePath) => {
    context.module = { exports: {} };
    context.exports = context.module.exports;
    const source = fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
    vm.runInNewContext(source, context, { filename: relativePath });
    if (context.module && typeof context.module.exports === "function") {
      context.FurnaceProductShellPlugin = context.module.exports;
    } else if (context.module && context.module.exports && typeof context.module.exports === "object") {
      Object.assign(context, context.module.exports);
    }
  };

  [
    "helpers.js",
    "command_specs.js",
    "pending_state.js",
    "pending_runtime.js",
    "today_feed.js",
    "render/cards.js",
    "render_primitives.js",
    "render_input.js",
    "render_today.js",
    "render_advanced.js",
    "render_home.js",
    "rewrite_state.js",
    "control_items.js",
    "modal_specs.js",
    "run_state.js",
    "state/health-state.js",
    "plugin_helpers.js",
    "plugin_lifecycle.js",
    "plugin_actions.js",
    "plugin.js",
  ].forEach(loadFile);

  context.__notices = notices;
  return context;
}

function makePlugin(overrides = {}) {
  return {
    t: (text, variables = {}) => String(text || "").replace(/\{(\w+)\}/g, (_, key) => String(variables[key] ?? "")),
    locale: () => "zh",
    repoState: { valid: true, root: "/vault", launcherPath: "/vault/scripts/aiwiki-launcher.sh", missingPaths: [] },
    shellSummary: null,
    pendingSubmissions: [],
    pluginState: { recentRuns: [] },
    settings: {
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
    },
    getLastSummaryRefreshLabel: () => "刚刚",
    refreshShellSummaryCommand: jest.fn().mockResolvedValue(undefined),
    hasActiveAskPending: jest.fn(() => false),
    pushPendingSubmission: jest.fn(() => "pending-1"),
    markPendingSubmissionDone: jest.fn(function(id, target, path) {
      const entry = (this.pendingSubmissions || overrides.pendingSubmissions || []).find((item) => item && item.id === id);
      if (!entry) return;
      entry.reconcileTarget = target;
      entry.reconcilePath = path;
      const degraded = entry.deliveryMode === "deterministic-fallback"
        || entry.llmStatus === "timeout_or_unavailable"
        || entry.llmStatus === "validation_failed"
        || entry.llmStatus === "failed"
        || entry.llmStatus === "degraded"
        || entry.backgroundStatus === "degraded"
        || entry.artifactQuality === "degraded";
      entry.status = degraded ? "degraded" : "done";
    }),
    markPendingSubmissionFailed: jest.fn(),
    updatePendingSubmissionRetryArgs: jest.fn((id, retryArgs) => {
      const entry = (overrides.pendingSubmissions || []).find((item) => item && item.id === id);
      if (entry) {
        entry.retryArgs = retryArgs;
        entry.runId = retryArgs.runId || "";
        entry.runNotesPath = retryArgs.runNotesPath || "";
      }
    }),
    resetPendingSubmissionForRetry: jest.fn(function(id) {
      const entry = (this.pendingSubmissions || overrides.pendingSubmissions || []).find((item) => item && item.id === id);
      if (entry) {
        entry.status = "running";
        entry.error = "";
        entry.reconcileTarget = "";
        entry.reconcilePath = "";
        entry.runId = "";
        entry.runNotesPath = "";
        entry.deliveryMode = "";
        entry.llmStatus = "";
        entry.llmBackend = "";
        entry.llmModel = "";
        entry.backgroundStatus = "";
        entry.artifactQuality = "";
      }
    }),
    completePendingMaterialDrop: jest.fn(() => true),
    runDroppedFilesWithAutoAsk: jest.fn().mockResolvedValue({
      materialPaths: ["raw/inbox/input.md"],
      askQuestion: "Q",
      askPayload: { report_path: "output/reports/q.md" },
    }),
    runDroppedPayloadsWithAutoAsk: jest.fn().mockResolvedValue({ materialPaths: ["raw/inbox/input.md"], askQuestion: "Q" }),
    runUniversalInputCommand: jest.fn().mockResolvedValue({ note_path: "raw/inbox/url.md" }),
    runAskCommand: jest.fn().mockResolvedValue({ report_path: "output/reports/default.md" }),
    renderMainHeader: jest.fn((el) => el.createDiv({ cls: "test-main-header", text: "header" })),
    renderLegacyAdvancedPanel: jest.fn((el) => el.createDiv({ cls: "test-legacy-advanced", text: "legacy" })),
    getAdvancedSectionExpanded: jest.fn(() => false),
    setAdvancedSectionExpanded: jest.fn(),
    savePluginState: jest.fn(),
    goToReport: jest.fn(),
    viewReviewTodayEntry: jest.fn(),
    snoozeTodayEntry: jest.fn(),
    runTodaySnoozeCommand: jest.fn(),
    openWorkspacePath: jest.fn(),
    openOutputsHub: jest.fn(),
    openHomeNote: jest.fn(),
    openPendingDoneTarget: jest.fn(),
    readWorkspaceSnippet: jest.fn().mockResolvedValue("这是报告摘要，会直接显示在交付物卡片里。"),
    quoteFileToComposer: jest.fn(),
    currentLlmHealth: jest.fn(() => ({ backend: "", model: "" })),
    currentShellSyncState: jest.fn(() => ({ status: "healthy" })),
    renderStatusPanel(container) {
      const status = (this.shellSummary && this.shellSummary.llm_status) || {};
      const fallbacks = Array.isArray(status.backend_fallbacks) ? status.backend_fallbacks : [];
      const available = fallbacks.filter((item) => item && item.available).length;
      if (fallbacks.length) {
        container.createDiv({ text: `Backup LLM route ready: ${available}/${fallbacks.length}` });
        fallbacks.forEach((item) => {
          container.createDiv({ text: `${item.backend}/${item.model}: ${item.available ? "available" : "unavailable"}` });
        });
      }
      return container;
    },
    ...overrides,
  };
}

function makeDropEvent(dataTransfer) {
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
  return event;
}

async function flushAsyncWork() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

const SHELL_SUMMARY_FIXTURE = {
  generated_at: "2026-05-13T10:00:00Z",
  active_protocol: "product",
  review_backlog_counts: { counter_evidence_candidates: 1 },
  counter_evidence_pages: [],
  drift_warnings: [],
  review_controls: { l3_proposals: [] },
  l3_proposals: [],
  recent_outputs: [
    {
      path: "output/reports/product-shell-summary.md",
      title: "Product shell summary report",
      generated_at: "2026-05-13T09:30:00Z",
      format: "report",
      protocol: "product",
    },
  ],
  recent_receipts: [],
  llm_status: {
    configured: true,
    backend: "opencode-api",
    model: "deepseek-v4-pro",
    available_backends: ["opencode-api"],
    backend_fallbacks: [],
  },
  suggested_next_actions: [],
  metrics_history_delta: { available: false },
  nightly: {
    generated_at: "2026-05-13T09:50:00Z",
    lint_counts: { errors: 0 },
  },
};

beforeAll(() => {
  installObsidianHTMLElementPolyfills();
});

beforeEach(() => {
  document.body.innerHTML = "";
  jest.restoreAllMocks();
});

test("renderUniversalInput success clears textarea and attachment pills after ask done", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin();
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const wrapper = container.querySelector(".furnace-universal-input-wrapper");
  expect(wrapper.classList.contains("furnace-conversation-composer")).toBe(true);
  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "请整理这个附件";
  wrapper.dispatchEvent(makeDropEvent({
    files: [{ name: "deck.pdf", path: "/tmp/deck.pdf" }],
    getData: () => "",
  }));

  expect(container.querySelectorAll(".furnace-input-attachment")).toHaveLength(1);

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.pushPendingSubmission).toHaveBeenCalledTimes(1);
  expect(plugin.markPendingSubmissionDone).toHaveBeenCalledWith("pending-1", "outputs", "output/reports/q.md");
  expect(plugin.markPendingSubmissionFailed).not.toHaveBeenCalled();
  expect(plugin.runDroppedFilesWithAutoAsk).toHaveBeenCalledTimes(1);
  expect(textarea.value).toBe("");
  expect(container.querySelectorAll(".furnace-input-attachment")).toHaveLength(0);
  expect(submitButton.disabled).toBe(false);
  expect(submitButton.textContent).toBe("Submit");
});

test("renderUniversalInput failure keeps textarea and attachment pills while restoring button", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runDroppedFilesWithAutoAsk: jest.fn().mockRejectedValue(new Error("boom")),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const wrapper = container.querySelector(".furnace-universal-input-wrapper");
  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "请再试一次";
  wrapper.dispatchEvent(makeDropEvent({
    files: [{ name: "deck.pdf", path: "/tmp/deck.pdf" }],
    getData: () => "",
  }));

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.markPendingSubmissionFailed).toHaveBeenCalledWith("pending-1", expect.any(Error));
  expect(textarea.value).toBe("请再试一次");
  expect(container.querySelectorAll(".furnace-input-attachment")).toHaveLength(1);
  expect(submitButton.disabled).toBe(false);
  expect(submitButton.textContent).toBe("Submit");
});

test("drop pure URL text fills textarea and does not enter file flow", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin();
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const wrapper = container.querySelector(".furnace-universal-input-wrapper");
  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  wrapper.dispatchEvent(makeDropEvent({
    files: [],
    getData: (type) => (type === "text/plain" ? "https://example.com/post" : ""),
  }));

  expect(textarea.value).toBe("https://example.com/post");
  expect(container.querySelectorAll(".furnace-input-attachment")).toHaveLength(0);

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.runDroppedFilesWithAutoAsk).not.toHaveBeenCalled();
  expect(plugin.runUniversalInputCommand).toHaveBeenCalledWith({ payload: "https://example.com/post" });
  expect(plugin.runAskCommand).not.toHaveBeenCalled();
  expect(plugin.completePendingMaterialDrop).toHaveBeenCalledWith("pending-1", ["raw/inbox/url.md"]);
});

test("obsidian open links navigate instead of submitting ask", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    openWorkspacePath: jest.fn().mockResolvedValue(true),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "obsidian://open?vault=%E7%82%BC%E4%B8%B9%E7%82%89&file=output%2Freports%2Fdemo.md";

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.openWorkspacePath).toHaveBeenCalledWith("output/reports/demo.md");
  expect(plugin.runAskCommand).not.toHaveBeenCalled();
  expect(plugin.runUniversalInputCommand).not.toHaveBeenCalled();
  expect(plugin.pushPendingSubmission).not.toHaveBeenCalled();
  expect(textarea.value).toBe("");
});

test("file-only submission completes as raw material instead of staying queued", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runDroppedFilesWithAutoAsk: jest.fn().mockResolvedValue({
      materialPaths: ["raw/inbox/image.md", "raw/assets/image.png"],
      askQuestion: "",
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const wrapper = container.querySelector(".furnace-universal-input-wrapper");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  wrapper.dispatchEvent(makeDropEvent({
    files: [{ name: "image.png", path: "/tmp/image.png" }],
    getData: () => "",
  }));

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.runDroppedFilesWithAutoAsk).toHaveBeenCalledWith({
    files: [{ path: "/tmp/image.png", name: "image.png" }],
    question: "",
    excludePendingId: "pending-1",
  });
  expect(plugin.runAskCommand).not.toHaveBeenCalled();
  expect(plugin.completePendingMaterialDrop).toHaveBeenCalledWith("pending-1", ["raw/inbox/image.md", "raw/assets/image.png"]);
});

test("pure material pending card shows 已收料 and never 排队生成报告", () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    pendingSubmissions: [
      {
        id: "p-material",
        status: "done",
        displayText: "https://example.com/post",
        reconcileTarget: "raw",
        reconcilePath: "raw/inbox/url.md",
        startedAt: "2026-05-13T09:00:00Z",
        retryArgs: { kind: "material", payload: "https://example.com/post", materialPaths: ["raw/inbox/url.md"] },
      },
    ],
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);

  expect(container.textContent).toContain("已收料");
  expect(container.textContent).not.toContain("排队生成报告");
  expect(container.textContent).not.toContain("已接收，正在排队生成报告");
});

test("ask pending running card shows generic generation copy", () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    pendingSubmissions: [
      {
        id: "p-ask",
        status: "running",
        displayText: "请总结这篇文章",
        startedAt: new Date(Date.now() - 5000).toISOString(),
        retryArgs: { kind: "auto-ask", question: "请总结这篇文章", format: "report" },
      },
    ],
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);

  expect(container.textContent).toContain("正在生成");
  expect(container.textContent).not.toContain("长程报告");
  expect(container.querySelector(".furnace-bubble-refresh-btn")).toBeNull();
});

test("pure material failure card uses 投料失败 title", () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    pendingSubmissions: [
      {
        id: "p-fail-material",
        status: "failed",
        displayText: "https://example.com/broken",
        error: "fetch failed",
        retryArgs: { kind: "material", payload: "https://example.com/broken" },
      },
    ],
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);

  expect(container.textContent).toContain("投料失败");
  expect(container.textContent).not.toContain("生成被阻断");
});

test("plain question goes through run-ask instead of deterministic universal drop", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    settings: {
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
    },
    runAskCommand: jest.fn().mockResolvedValue({
      report_path: "output/reports/ask.md",
      run_notes_path: "output/control/runs/ask/thinking.md",
      run_id: "ask-report",
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "问你个问题，你是什么大模型？";

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.runUniversalInputCommand).not.toHaveBeenCalled();
  expect(plugin.runAskCommand).toHaveBeenCalledWith({
    question: "问你个问题，你是什么大模型？",
    format: "report",
    mode: "run-ask",
    excludePendingId: "pending-1",
  });
  expect(plugin.updatePendingSubmissionRetryArgs).toHaveBeenCalledWith("pending-1", expect.objectContaining({
    kind: "auto-ask",
    format: "report",
    materialPaths: [],
    runNotesPath: "output/control/runs/ask/thinking.md",
    runId: "ask-report",
  }));
});

test("composer shows read-only sticky material chips without remove controls", () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    settings: {
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
      stickyMaterialRefs: {
        paths: ["raw/inbox/sticky.md", "output/reports/r.md"],
        updatedAt: "2026-07-23T00:00:00Z",
        source: "drop",
      },
    },
  });
  const container = document.createElement("div");
  context.renderUniversalInput(plugin, container);
  expect(container.querySelector(".furnace-input-sticky-materials")).toBeTruthy();
  expect(container.textContent).toContain("Sticky materials (used on follow-up)");
  const chips = container.querySelectorAll(".furnace-input-sticky-chip");
  expect(chips).toHaveLength(2);
  expect(chips[0].getAttribute("title")).toBe("raw/inbox/sticky.md");
  expect(container.querySelector(".furnace-input-sticky-chip-remove")).toBeNull();
  expect(container.querySelector(".furnace-input-sticky-materials .furnace-input-attachment-remove")).toBeNull();
});

test("pure ask writes usedMaterialPaths into retryArgs.materialPaths", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runAskCommand: jest.fn().mockResolvedValue({
      report_path: "output/reports/ask.md",
      run_notes_path: "output/control/runs/ask/thinking.md",
      run_id: "ask-report",
      usedMaterialPaths: ["raw/inbox/sticky.md"],
    }),
  });
  const container = document.createElement("div");
  context.renderUniversalInput(plugin, container);
  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "继续分析";
  submitButton.click();
  await flushAsyncWork();
  expect(plugin.updatePendingSubmissionRetryArgs).toHaveBeenCalledWith("pending-1", expect.objectContaining({
    kind: "auto-ask",
    materialPaths: ["raw/inbox/sticky.md"],
  }));
});

test("ctrl enter submits the composer through the form path", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runAskCommand: jest.fn().mockResolvedValue({
      report_path: "output/reports/ask.md",
      run_notes_path: "output/control/runs/ask/thinking.md",
      run_id: "ask-report",
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  textarea.value = "请回答这个问题";
  const event = new KeyboardEvent("keydown", {
    key: "Enter",
    code: "Enter",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });

  textarea.dispatchEvent(event);
  await flushAsyncWork();

  expect(event.defaultPrevented).toBe(true);
  expect(plugin.runAskCommand).toHaveBeenCalledTimes(1);
  expect(plugin.runAskCommand).toHaveBeenCalledWith({
    question: "请回答这个问题",
    format: "report",
    mode: "run-ask",
    excludePendingId: "pending-1",
  });
  expect(plugin.markPendingSubmissionDone).toHaveBeenCalledWith("pending-1", "outputs", "output/reports/ask.md");
  expect(textarea.value).toBe("");
});

test("ctrl enter keyup fallback submits once when requestSubmit is unavailable", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runAskCommand: jest.fn().mockResolvedValue({
      report_path: "output/reports/ask.md",
      run_notes_path: "output/control/runs/ask/thinking.md",
      run_id: "ask-note",
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const form = container.querySelector(".furnace-universal-input-form");
  const textarea = container.querySelector(".furnace-universal-input-textarea");
  form.requestSubmit = undefined;
  textarea.value = "请确认 keyup fallback 可提交";
  const event = new KeyboardEvent("keyup", {
    key: "NumpadEnter",
    code: "NumpadEnter",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  });

  textarea.dispatchEvent(event);
  await flushAsyncWork();

  expect(event.defaultPrevented).toBe(true);
  expect(plugin.runAskCommand).toHaveBeenCalledTimes(1);
  expect(plugin.markPendingSubmissionDone).toHaveBeenCalledWith("pending-1", "outputs", "output/reports/ask.md");
  expect(textarea.value).toBe("");
});

test("plain question ignores stale persisted format and stays report", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    settings: {
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
    },
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "你是什么大模型？";

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.runUniversalInputCommand).not.toHaveBeenCalled();
  expect(plugin.runAskCommand).toHaveBeenCalledWith({
    question: "你是什么大模型？",
    format: "report",
    mode: "run-ask",
    excludePendingId: "pending-1",
  });
});

test("explicit report question uses sync ask pending metadata", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runAskCommand: jest.fn().mockResolvedValue({
      report_path: "output/reports/report-q.md",
      run_notes_path: "output/control/runs/report/thinking.md",
      run_id: "ask-report",
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "请生成一份深度报告";

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.runAskCommand).toHaveBeenCalledWith({
    question: "请生成一份深度报告",
    format: "report",
    mode: "run-ask",
    excludePendingId: "pending-1",
  });
  expect(plugin.pushPendingSubmission).toHaveBeenCalledWith("请生成一份深度报告", expect.objectContaining({
    retryArgs: expect.objectContaining({ format: "report", kind: "auto-ask" }),
  }));
});

test("material question stores final inferred format without long running flag", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runDroppedPayloadsWithAutoAsk: jest.fn().mockResolvedValue({
      materialPaths: ["raw/inbox/input.md"],
      askQuestion: "请生成一份深度报告\n\n请优先使用本次投喂材料回答；材料路径供系统路由使用：raw/inbox/input.md",
      askFormat: "report",
      run_notes_path: "output/control/runs/report/thinking.md",
      run_id: "ask-report",
      askPayload: { report_path: "output/reports/material-q.md" },
    }),
  });
  const container = document.createElement("div");

  context.renderUniversalInput(plugin, container);

  const textarea = container.querySelector(".furnace-universal-input-textarea");
  const submitButton = container.querySelector(".furnace-universal-input-button");
  textarea.value = "https://example.com/article\n请生成一份深度报告";

  submitButton.click();
  await flushAsyncWork();

  expect(plugin.updatePendingSubmissionRetryArgs).toHaveBeenCalledWith("pending-1", expect.objectContaining({
    format: "report",
  }));
});

test("ask pending card uses generic generation language", () => {
  const context = loadRenderContext();
  const container = document.createElement("div");

  context.renderTodayFeed(
    makePlugin({
      pendingSubmissions: [
        {
          id: "report-1",
          status: "running",
          displayText: "请生成一份深度报告",
          startedAt: new Date(Date.now() - 5000).toISOString(),
          retryArgs: { kind: "auto-ask", format: "report" },
        },
      ],
    }),
    container
  );

  expect(container.textContent).toContain("正在生成");
  expect(container.textContent).not.toContain("已接收请求");
  expect(container.textContent).not.toContain("长程报告");
  expect(container.querySelector(".furnace-progress-steps")).toBeNull();
  expect(container.querySelector(".furnace-bubble-refresh-btn")).toBeNull();
});

test("renderTodayFeed covers no-summary empty-feed and pending branches", () => {
  const context = loadRenderContext();

  const noSummaryContainer = document.createElement("div");
  context.renderTodayFeed(makePlugin({ shellSummary: null }), noSummaryContainer);
  expect(noSummaryContainer.textContent).toContain("数据还没就绪");
  expect(noSummaryContainer.querySelector(".furnace-today-cta-submit").textContent).toBe("投一份材料");

  const emptySummary = {
    generated_at: "2026-05-13T10:00:00Z",
    review_backlog_counts: {},
    counter_evidence_pages: [],
    drift_warnings: [],
    review_controls: { l3_proposals: [] },
    recent_outputs: [],
    recent_receipts: [],
    suggested_next_actions: [],
    metrics_history_delta: { available: false },
  };
  const emptyContainer = document.createElement("div");
  context.renderTodayFeed(makePlugin({ shellSummary: emptySummary }), emptyContainer);
  expect(emptyContainer.textContent).toContain("今天还没有新报告");

  const pendingContainer = document.createElement("div");
  context.renderTodayFeed(
    makePlugin({
      shellSummary: emptySummary,
      pendingSubmissions: [{ id: "p1", status: "running", displayText: "等待编译", startedAt: new Date(Date.now() - 5000).toISOString(), retryArgs: { kind: "auto-ask", format: "report" } }],
    }),
    pendingContainer
  );
  expect(pendingContainer.textContent).not.toContain("今天还没有新报告");
  expect(pendingContainer.querySelector(".furnace-conversation-bubble")).toBeTruthy();
  expect(pendingContainer.querySelector(".furnace-bubble-user").textContent).toContain("等待编译");
  expect(pendingContainer.querySelector(".furnace-bubble-ai").textContent).toContain("正在生成");
  expect(pendingContainer.querySelector(".furnace-bubble-shimmer-line")).toBeTruthy();
});

test("chat-style pending stream covers artifact cards failed and escalated bubbles", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    shellSummary: {
      generated_at: "2026-05-13T10:00:00Z",
      review_backlog_counts: {},
      recent_outputs: [],
      recent_receipts: [],
      suggested_next_actions: [],
      metrics_history_delta: { available: false },
    },
    pendingSubmissions: [
      {
        id: "done-output",
        status: "done",
        displayText: "生成报告",
        reconcileTarget: "outputs",
        reconcilePath: "output/reports/r.md",
        runNotesPath: "output/control/runs/ask-r/thinking.md",
        runId: "ask-r",
        retryArgs: { kind: "auto-ask", materialPaths: ["raw/inbox/a.md"] },
      },
      { id: "done-receipt", status: "done", displayText: "写回执", reconcileTarget: "receipts", reconcilePath: "output/control/r.json" },
      { id: "failed", status: "failed", displayText: "失败任务", error: "backend unavailable", retryArgs: { kind: "text", payload: "retry" } },
      { id: "escalated", status: "escalated", displayText: "需要确认" },
    ],
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);
  await flushAsyncWork();

  expect(container.querySelectorAll(".furnace-conversation-item")).toHaveLength(4);
  expect(container.textContent).toContain("报告卡片已就绪");
  expect(container.textContent).toContain("本地报告 Artifact");
  expect(container.textContent).toContain("这是报告摘要，会直接显示在交付物卡片里。");
  expect(container.textContent).toContain("引用此报告追问");
  expect(container.querySelector(".furnace-bubble-materials")).toBeTruthy();
  expect(container.querySelector(".furnace-bubble-material-chip").getAttribute("title")).toBe("raw/inbox/a.md");
  const outputBubble = container.querySelector(".furnace-conversation-item .furnace-bubble-ai");
  const resultCard = outputBubble.querySelector(".furnace-artifact-card");
  const actions = outputBubble.querySelector(".furnace-artifact-actions");
  expect(resultCard).toBeTruthy();
  expect(actions).toBeTruthy();
  expect(resultCard.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(container.querySelector(".furnace-pending-open-report-btn")).toBeTruthy();
  container.querySelector(".furnace-pending-quote-report-btn").click();
  expect(plugin.quoteFileToComposer).toHaveBeenCalledWith("output/reports/r.md");
  expect(container.textContent).toContain("回执已就绪");
  expect(container.textContent).toContain("执行回执 Receipt");
  expect(container.querySelector(".furnace-pending-open-receipt-btn")).toBeTruthy();
  expect(container.textContent).toContain("生成被阻断");
  expect(container.textContent).toContain("backend unavailable");
  expect(container.textContent).toContain("重试");
  expect(container.textContent).toContain("需要人工确认");
  expect(container.querySelector(".furnace-pending-exception-btn")).toBeTruthy();
});

test("renderTodayFeed hides done pending bubble when report already appears in Today feed", () => {
  const context = loadRenderContext();
  const container = document.createElement("div");
  context.renderTodayFeed(
    makePlugin({
      shellSummary: {
        generated_at: "2026-05-13T10:00:00Z",
        review_backlog_counts: {},
        recent_outputs: [
          {
            path: "output/reports/r.md",
            title: "Today report",
            generated_at: "2026-05-13T09:30:00Z",
            format: "report",
          },
        ],
        recent_receipts: [],
        suggested_next_actions: [],
        metrics_history_delta: { available: false },
      },
      pendingSubmissions: [
        {
          id: "done-dup",
          status: "done",
          displayText: "生成报告",
          reconcileTarget: "outputs",
          reconcilePath: "output/reports/r.md",
        },
        {
          id: "done-other",
          status: "done",
          displayText: "其他报告",
          reconcileTarget: "outputs",
          reconcilePath: "output/reports/other.md",
        },
      ],
    }),
    container
  );

  expect(container.querySelectorAll(".furnace-conversation-item")).toHaveLength(1);
  expect(container.textContent).toContain("其他报告");
  expect(container.textContent).not.toContain("生成报告");
  expect(container.textContent).toContain("Today report");
});

test("degraded output card hides quote action and keeps recovery semantics", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    shellSummary: {
      generated_at: "2026-05-13T10:00:00Z",
      review_backlog_counts: {},
      recent_outputs: [],
      recent_receipts: [],
      suggested_next_actions: [],
      metrics_history_delta: { available: false },
    },
    pendingSubmissions: [
      {
        id: "done-degraded",
        status: "done",
        displayText: "生成报告",
        reconcileTarget: "outputs",
        reconcilePath: "output/reports/degraded.md",
        deliveryMode: "deterministic-fallback",
        llmStatus: "timeout_or_unavailable",
        runNotesPath: "output/control/runs/ask-r/thinking.md",
        runId: "ask-r",
        retryArgs: { kind: "auto-ask", format: "report", question: "重试问题" },
      },
    ],
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);
  await flushAsyncWork();

  expect(container.textContent).toContain("失败说明已就绪");
  expect(container.textContent).toContain("失败说明 Artifact");
  expect(container.textContent).toContain("打开产物");
  expect(container.textContent).toContain("重试");
  expect(container.textContent).not.toContain("引用此报告追问");
  expect(container.querySelector(".furnace-pending-quote-report-btn")).toBeNull();
  expect(container.querySelector(".furnace-pending-open-report-btn").textContent).toBe("打开产物");
});

test("degraded output retry clears stale run id and records new sync ask metadata", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    shellSummary: {
      generated_at: "2026-05-13T10:00:00Z",
      review_backlog_counts: {},
      recent_outputs: [],
      recent_receipts: [],
      suggested_next_actions: [],
      metrics_history_delta: { available: false },
    },
    pendingSubmissions: [
      {
        id: "done-degraded",
        status: "done",
        displayText: "生成报告",
        reconcileTarget: "outputs",
        reconcilePath: "output/reports/degraded.md",
        deliveryMode: "deterministic-fallback",
        llmStatus: "timeout_or_unavailable",
        runNotesPath: "output/control/runs/old/thinking.md",
        runId: "old-run",
        retryArgs: { kind: "auto-ask", format: "report", question: "重试问题", runId: "old-run", runNotesPath: "output/control/runs/old/thinking.md" },
      },
    ],
  });
  plugin.runAskCommand = jest.fn().mockResolvedValue({
    run_id: "new-run",
    run_notes_path: "output/control/runs/new/thinking.md",
    report_path: "output/reports/degraded-retry.md",
  });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);
  await flushAsyncWork();
  container.querySelector(".furnace-pending-retry-report-btn").click();
  await flushAsyncWork();

  expect(plugin.runAskCommand).toHaveBeenCalledWith(expect.objectContaining({ question: "重试问题", format: "report", mode: "run-ask", excludePendingId: "done-degraded" }));
  expect(plugin.pendingSubmissions[0]).toEqual(expect.objectContaining({
    status: "done",
    reconcileTarget: "outputs",
    reconcilePath: "output/reports/degraded-retry.md",
    runId: "new-run",
    runNotesPath: "output/control/runs/new/thinking.md",
  }));
  expect(plugin.pendingSubmissions[0].retryArgs).toEqual(expect.objectContaining({
    runId: "new-run",
    runNotesPath: "output/control/runs/new/thinking.md",
  }));
});

test("reconcile pending report prefers run_id and stores delivery metadata", () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  Object.assign(plugin, makePlugin());
  plugin.savePluginState = jest.fn();
  plugin.refreshOpenViews = jest.fn();
  const startedAt = new Date(Date.now() - 2 * 60 * 1000).toISOString();
  const createdAt = new Date(Date.now() - 60 * 1000).toISOString();
  plugin.pendingSubmissions = [
    {
      id: "p-report",
      status: "running",
      payloadFingerprint: "unmatched text fingerprint",
      displayText: "生成报告",
      startedAt,
      runId: "ask-report-1",
      retryArgs: { runId: "ask-report-1", format: "report", kind: "auto-ask" },
    },
  ];

  plugin.reconcilePendingSubmissions({
    recent_outputs: [
      {
        path: "output/reports/final.md",
        title: "完全不同标题",
        created_at: createdAt,
        run_id: "ask-report-1",
        run_notes_path: "output/control/runs/ask-report-1/thinking.md",
        delivery_mode: "deterministic-fallback",
        llm_status: "timeout_or_unavailable",
        llm_backend: "opencode-api",
        llm_model: "deepseek-v4-pro",
      },
    ],
    recent_receipts: [],
    recent_raw_inputs: [],
  });

  expect(plugin.pendingSubmissions).toHaveLength(1);
  expect(plugin.pendingSubmissions[0]).toEqual(expect.objectContaining({
    id: "p-report",
    status: "degraded",
    reconcileTarget: "outputs",
    reconcilePath: "output/reports/final.md",
    runId: "ask-report-1",
    runNotesPath: "output/control/runs/ask-report-1/thinking.md",
    deliveryMode: "deterministic-fallback",
    llmStatus: "timeout_or_unavailable",
    llmBackend: "opencode-api",
    llmModel: "deepseek-v4-pro",
  }));
});

test("quoteFileToComposer does not duplicate an existing report quote", () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text, vars = {}) => String(text).replace("{path}", vars.path || "");
  document.body.innerHTML = '<textarea class="furnace-universal-input-textarea"></textarea>';
  const textarea = document.querySelector(".furnace-universal-input-textarea");
  textarea.scrollIntoView = jest.fn();

  expect(plugin.quoteFileToComposer("output/reports/r.md")).toBe(true);
  expect(plugin.quoteFileToComposer("output/reports/r.md")).toBe(true);

  expect(textarea.value.split("\n").filter((line) => line === "引用报告：output/reports/r.md")).toHaveLength(1);
});

test("openWorkspacePath rejects absolute and escaping paths before vault lookup", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text, vars = {}) => String(text).replace("{path}", vars.path || "");
  plugin.repoState = { root: "/vault" };
  plugin.app = {
    vault: {
      getAbstractFileByPath: jest.fn(),
      adapter: { getResourcePath: jest.fn() },
    },
    workspace: { getLeaf: jest.fn() },
  };

  await expect(plugin.openWorkspacePath("/tmp/secret.md")).resolves.toBe(false);
  await expect(plugin.openWorkspacePath("../secret.md")).resolves.toBe(false);

  expect(plugin.app.vault.getAbstractFileByPath).not.toHaveBeenCalled();
  expect(context.__notices).toEqual([
    "Unable to open /tmp/secret.md",
    "Unable to open ../secret.md",
  ]);
});

test("openWorkspacePath notices when file exists but Obsidian did not index it", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text, vars = {}) => String(text).replace("{path}", vars.path || "");
  const vaultRoot = fs.mkdtempSync(path.join(os.tmpdir(), "furnace-open-"));
  const reportRel = "output/reports/demo.md";
  fs.mkdirSync(path.join(vaultRoot, "output/reports"), { recursive: true });
  fs.writeFileSync(path.join(vaultRoot, reportRel), "# demo\n");
  plugin.repoState = { root: vaultRoot };
  const openFile = jest.fn();
  plugin.app = {
    vault: {
      getAbstractFileByPath: jest.fn().mockReturnValue(null),
      adapter: { getResourcePath: jest.fn() },
    },
    workspace: { getLeaf: jest.fn(() => ({ openFile })) },
  };

  await expect(plugin.openWorkspacePath(reportRel)).resolves.toBe(false);

  expect(openFile).not.toHaveBeenCalled();
  expect(plugin.app.vault.adapter.getResourcePath).not.toHaveBeenCalled();
  expect(context.__notices).toEqual([
    "File exists but Obsidian has not indexed it (check Excluded files / userIgnoreFilters): output/reports/demo.md",
  ]);
});

test("runAskCommand uses sync run-ask for report mode", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text) => text;
  plugin.pendingSubmissions = [];
  plugin.runPluginCommand = jest.fn().mockResolvedValue({ report_path: "output/reports/r.md" });

  const payload = await plugin.runAskCommand({
    question: "请生成一份深度报告",
    format: "report",
    mode: "run-ask",
  });

  expect(plugin.runPluginCommand).toHaveBeenCalledWith(
    expect.stringContaining("Ask"),
    ["run-ask", "请生成一份深度报告", "--format", "report", "--lean"],
    expect.objectContaining({ refreshAfter: true })
  );
  expect(payload).toEqual({ report_path: "output/reports/r.md", usedMaterialPaths: [] });
});

test("runAskCommand rejects a second ask while one is active", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text) => text;
  plugin.pendingSubmissions = [
    {
      id: "ask-active",
      status: "running",
      retryArgs: { kind: "auto-ask", question: "first", format: "report" },
    },
  ];
  plugin.runPluginCommand = jest.fn();

  const payload = await plugin.runAskCommand({
    question: "second question",
    format: "report",
    mode: "run-ask",
  });

  expect(plugin.runPluginCommand).not.toHaveBeenCalled();
  expect(payload).toBeUndefined();
  expect(context.__notices).toContain("已有进行中的提问，请等待完成后再试。");
});

test("runAskCommand still allows ask while only material drop is active", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text) => text;
  plugin.pendingSubmissions = [
    {
      id: "material-active",
      status: "running",
      retryArgs: { kind: "material", payload: "https://example.com" },
    },
  ];
  plugin.runPluginCommand = jest.fn().mockResolvedValue({ report_path: "output/reports/r.md" });

  await plugin.runAskCommand({
    question: "follow up question",
    format: "report",
    mode: "run-ask",
  });

  expect(plugin.runPluginCommand).toHaveBeenCalledTimes(1);
});

test("runAskCommand excludes its own pending card (no self-block after push)", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text) => text;
  plugin.savePluginState = jest.fn();
  plugin.pendingSubmissions = [
    {
      id: "self-ask",
      status: "running",
      retryArgs: { kind: "auto-ask", question: "自问", askQuestion: "自问", format: "report" },
    },
  ];
  plugin.runPluginCommand = jest.fn().mockResolvedValue({ report_path: "output/reports/r.md", run_id: "ask-1" });

  expect(plugin.hasActiveAskPending()).toBe(true);

  const payload = await plugin.runAskCommand({
    question: "自问",
    format: "report",
    mode: "run-ask",
    excludePendingId: "self-ask",
  });

  expect(plugin.runPluginCommand).toHaveBeenCalledTimes(1);
  expect(payload).toEqual({ report_path: "output/reports/r.md", run_id: "ask-1", usedMaterialPaths: [] });
  expect(context.__notices).not.toContain("已有进行中的提问，请等待完成后再试。");
});

test("shell summary fixture builds today DOM headings and furnace center keeps only primary entry surfaces", () => {
  const context = loadRenderContext();
  const feed = context.buildTodayFeed(SHELL_SUMMARY_FIXTURE);
  expect(feed.some((entry) => entry.kind === "report")).toBe(true);
  expect(feed.some((entry) => entry.kind === "automation")).toBe(false);
  expect(feed.some((entry) => entry.kind === "decision")).toBe(false);
  expect(feed.some((entry) => entry.kind === "proposal")).toBe(false);
  expect(feed.some((entry) => entry.kind === "elixir")).toBe(false);

  const todayContainer = document.createElement("div");
  context.renderTodayFeed(makePlugin({ shellSummary: SHELL_SUMMARY_FIXTURE }), todayContainer);
  expect(todayContainer.textContent).toContain("新报告");
  expect(todayContainer.textContent).not.toContain("需要你确认");

  const homeContainer = document.createElement("div");
  context.renderFurnaceCenter(makePlugin({ shellSummary: SHELL_SUMMARY_FIXTURE }), homeContainer);
  expect(homeContainer.querySelector(".furnace-universal-input-textarea")).toBeTruthy();
  expect(homeContainer.querySelector(".furnace-today-feed")).toBeTruthy();
  expect(homeContainer.querySelector(".furnace-advanced-drawer")).toBeNull();
  expect(homeContainer.lastElementChild.classList.contains("furnace-conversation-composer")).toBe(true);
  expect(homeContainer.querySelector(".furnace-shell-dropzone")).toBeNull();
  expect(homeContainer.textContent).not.toContain("Drop URL / PDF / Image / Repo");
  expect(homeContainer.textContent).not.toContain("System Status");
  expect(homeContainer.textContent).not.toContain("LLM Health");
  expect(homeContainer.textContent).not.toContain("Repair Backlog");
});

test("advanced status panel omits backup LLM fallback readiness when no fallback is configured", () => {
  const context = loadRenderContext();
  const container = document.createElement("div");
  const plugin = makePlugin({
    shellSummary: SHELL_SUMMARY_FIXTURE,
    getAdvancedSectionExpanded: jest.fn((key) => key === "status"),
    currentLlmHealth: jest.fn(() => ({ status: "healthy", backend: "opencode-api", model: "deepseek-v4-pro" })),
    currentShellSyncState: jest.fn(() => ({ status: "healthy", reason: "Summary ready." })),
  });
  plugin.settings.showAdvancedCommands = true;

  context.renderFurnaceCenter(plugin, container);

  expect(container.textContent).not.toContain("Backup LLM route ready");
  expect(container.textContent).not.toContain("codex-cli");
});

test("llm-check unconfigured summary renders operable UI degradation", () => {
  const context = loadRenderContext();
  const unconfiguredSummary = {
    generated_at: "2026-05-13T10:00:00Z",
    active_protocol: "product",
    llm_status: {
      configured: false,
      backend: "",
      model: "",
      available_backends: [],
      missing: ["AIWIKI_LLM_BACKEND"],
      message: "LLM is not configured.",
    },
    review_backlog_counts: {},
    counter_evidence_pages: [],
    drift_warnings: [],
    review_controls: { l3_proposals: [] },
    recent_outputs: [],
    recent_receipts: [],
    recent_raw_inputs: [],
    suggested_next_actions: [],
    metrics_history_delta: { available: false },
  };
  const container = document.createElement("div");

  const plugin = makePlugin({ shellSummary: unconfiguredSummary });
  plugin.settings.showAdvancedCommands = true;
  plugin.renderStatusPanel = jest.fn((el) => el.createDiv({ text: "LLM 未配置" }));
  context.renderFurnaceCenter(plugin, container);

  expect(container.textContent).toContain("LLM 未配置");
  expect(container.querySelector(".furnace-universal-input-textarea")).toBeTruthy();
  expect(container.querySelector(".furnace-universal-input-button").disabled).toBe(false);
  expect(container.textContent).toContain("今天还没有新报告");
  expect(container.querySelector(".furnace-today-cta-submit")).toBeTruthy();
});

test("recent raw inputs reconcile running pending card to done with raw target", () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  Object.assign(plugin, makePlugin());
  const startedAt = new Date(Date.now() - 2 * 60 * 1000).toISOString();
  const occurredAt = new Date(Date.now() - 60 * 1000).toISOString();
  plugin.pendingSubmissions = [
    {
      id: "p-raw",
      status: "running",
      payloadFingerprint: "raw/inbox/product-shell-smoke.md",
      title: "Product Shell smoke",
      startedAt,
    },
  ];
  plugin.markPendingSubmissionDone = jest.fn();
  plugin.refreshOpenViews = jest.fn();

  plugin.reconcilePendingSubmissions({
    recent_outputs: [],
    recent_receipts: [],
    recent_raw_inputs: [
      {
        stored_path: "raw/inbox/product-shell-smoke.md",
        title: "Product Shell smoke",
        occurred_at: occurredAt,
      },
    ],
  });

  expect(plugin.markPendingSubmissionDone).toHaveBeenCalledWith(
    "p-raw",
    "raw",
    "raw/inbox/product-shell-smoke.md"
  );
});

test("long title fixture keeps non-empty title and button text", () => {
  const context = loadRenderContext();
  const longSummary = {
    ...SHELL_SUMMARY_FIXTURE,
    recent_outputs: [
      {
        path: "output/reports/very-long-title.md",
        title: "超长标题超长标题超长标题超长标题超长标题超长标题超长标题超长标题超长标题超长标题",
        generated_at: "2026-05-13T09:30:00Z",
        format: "report",
        protocol: "product",
      },
    ],
    review_backlog_counts: {},
    nightly: null,
  };
  const container = document.createElement("div");

  context.renderTodayFeed(makePlugin({ shellSummary: longSummary }), container);

  const title = container.querySelector(".furnace-feed-card-title");
  const button = container.querySelector(".furnace-feed-card-actions button");
  expect(title).toBeTruthy();
  expect(title.textContent.trim()).not.toBe("");
  expect(button).toBeTruthy();
  expect(button.textContent.trim()).not.toBe("");
});
