"use strict";

const fs = require("fs");
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
    DropFileModal: function DropFileModal() {
      return {
        setInitialMode() { return this; },
        setInitialSource() { return this; },
        open() { return this; },
      };
    },
    DropImageModal: function DropImageModal() {
      return {
        setInitialSource() { return this; },
        open() { return this; },
      };
    },
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
    "today_feed.js",
    "render/cards.js",
    "render_primitives.js",
    "render_input.js",
    "render_today.js",
    "render_advanced.js",
    "render_home.js",
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
      onboardingShown: true,
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
    },
    getLastSummaryRefreshLabel: () => "刚刚",
    refreshShellSummaryCommand: jest.fn().mockResolvedValue(undefined),
    pushPendingSubmission: jest.fn(() => "pending-1"),
    markPendingSubmissionReceived: jest.fn(),
    markPendingSubmissionFailed: jest.fn(),
    updatePendingSubmissionRetryArgs: jest.fn(),
    completePendingMaterialDrop: jest.fn(),
    runDroppedFilesWithAutoAsk: jest.fn().mockResolvedValue({ materialPaths: ["raw/inbox/input.md"], askQuestion: "Q" }),
    runDroppedPayloadsWithAutoAsk: jest.fn().mockResolvedValue({ materialPaths: ["raw/inbox/input.md"], askQuestion: "Q" }),
    runUniversalInputCommand: jest.fn().mockResolvedValue({ note_path: "raw/inbox/url.md" }),
    runAskCommand: jest.fn().mockResolvedValue({}),
    renderMainHeader: jest.fn((el) => el.createDiv({ cls: "test-main-header", text: "header" })),
    renderLegacyAdvancedPanel: jest.fn((el) => el.createDiv({ cls: "test-legacy-advanced", text: "legacy" })),
    getAdvancedSectionExpanded: jest.fn(() => false),
    setAdvancedSectionExpanded: jest.fn(),
    savePluginState: jest.fn(),
    goToReport: jest.fn(),
    viewReviewTodayEntry: jest.fn(),
    snoozeTodayEntry: jest.fn(),
    openReviewCenterView: jest.fn(),
    runTodaySnoozeCommand: jest.fn(),
    openWorkspacePath: jest.fn(),
    openOutputsHub: jest.fn(),
    openRecentRunsView: jest.fn(),
    openHomeNote: jest.fn(),
    openPendingDoneTarget: jest.fn(),
    readWorkspaceSnippet: jest.fn().mockResolvedValue("这是报告摘要，会直接显示在交付物卡片里。"),
    quoteFileToComposer: jest.fn(),
    currentLlmHealth: jest.fn(() => ({ backend: "", model: "" })),
    currentShellSyncState: jest.fn(() => ({ status: "healthy" })),
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
    available_backends: ["opencode-api", "codex-cli"],
    backend_fallbacks: [
      {
        backend: "codex-cli",
        model: "gpt-5.5",
        configured: true,
        available: true,
        reason: "command found",
      },
    ],
  },
  suggested_next_actions: [],
  metrics_history_delta: { available: false },
  today_snooze: { items: [] },
  nightly: {
    generated_at: "2026-05-13T09:50:00Z",
    agent_loop: {
      generated_at: "2026-05-13T09:50:00Z",
      status: "ok",
      signals: { new_count: 2 },
      planner: { execute: { new_count: 1 } },
      auto_preview: { ready_count: 0 },
      auto_apply: { applied_count: 1 },
    },
  },
};

beforeAll(() => {
  installObsidianHTMLElementPolyfills();
});

beforeEach(() => {
  document.body.innerHTML = "";
  jest.restoreAllMocks();
});

test("renderUniversalInput success clears textarea and attachment pills after received", async () => {
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
  expect(plugin.markPendingSubmissionReceived).toHaveBeenCalledWith("pending-1");
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
  expect(plugin.markPendingSubmissionReceived).not.toHaveBeenCalled();
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
  });
  expect(plugin.runAskCommand).not.toHaveBeenCalled();
  expect(plugin.completePendingMaterialDrop).toHaveBeenCalledWith("pending-1", ["raw/inbox/image.md", "raw/assets/image.png"]);
});

test("plain question goes through run-ask instead of deterministic universal drop", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    settings: {
      onboardingShown: true,
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
      defaultAskFormat: "note",
    },
    runAskCommand: jest.fn().mockResolvedValue({ run_notes_path: "output/control/runs/ask/thinking.md", run_id: "ask-note" }),
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
    format: "note",
    mode: "run-ask",
  });
  expect(plugin.updatePendingSubmissionRetryArgs).toHaveBeenCalledWith("pending-1", expect.objectContaining({
    kind: "auto-ask",
    format: "note",
    runNotesPath: "output/control/runs/ask/thinking.md",
    runId: "ask-note",
  }));
});

test("plain question ignores persisted report default and stays note", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    settings: {
      onboardingShown: true,
      showAdvancedCommands: false,
      advancedSectionsExpanded: {},
      locale: "zh",
      defaultAskFormat: "report",
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
    format: "note",
    mode: "run-ask",
  });
});

test("explicit report question is marked as long running", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runAskCommand: jest.fn().mockResolvedValue({ run_notes_path: "output/control/runs/report/thinking.md", run_id: "ask-report" }),
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
  });
  expect(plugin.pushPendingSubmission).toHaveBeenCalledWith("请生成一份深度报告", expect.objectContaining({
    retryArgs: expect.objectContaining({ format: "report", longRunning: true }),
  }));
});

test("material question updates long running flag from final inferred format", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    runDroppedPayloadsWithAutoAsk: jest.fn().mockResolvedValue({
      materialPaths: ["raw/inbox/input.md"],
      askQuestion: "请生成一份深度报告\n\n请优先使用本次投喂材料回答；材料路径供系统路由使用：raw/inbox/input.md",
      askFormat: "report",
      run_notes_path: "output/control/runs/report/thinking.md",
      run_id: "ask-report",
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
    longRunning: true,
  }));
});

test("long running pending card uses report progress language", () => {
  const context = loadRenderContext();
  const container = document.createElement("div");

  context.renderTodayFeed(
    makePlugin({
      pendingSubmissions: [
        {
          id: "report-1",
          status: "received",
          displayText: "请生成一份深度报告",
          startedAt: "2026-05-13T09:00:00Z",
          retryArgs: { kind: "auto-ask", format: "report", longRunning: true },
        },
      ],
    }),
    container
  );

  expect(container.textContent).toContain("长程报告生成中，可稍后刷新");
  expect(container.textContent).toContain("已接收长程报告任务");
  expect(container.textContent).toContain("LLM 正在生成结构化报告");
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
    today_snooze: { items: [] },
  };
  const emptyContainer = document.createElement("div");
  context.renderTodayFeed(makePlugin({ shellSummary: emptySummary }), emptyContainer);
  expect(emptyContainer.textContent).toContain("今天还没有新报告");

  const pendingContainer = document.createElement("div");
  context.renderTodayFeed(
    makePlugin({
      shellSummary: emptySummary,
      pendingSubmissions: [{ id: "p1", status: "running", displayText: "等待编译", startedAt: "2026-05-13T09:00:00Z" }],
    }),
    pendingContainer
  );
  expect(pendingContainer.textContent).not.toContain("今天还没有新报告");
  expect(pendingContainer.querySelector(".furnace-conversation-bubble")).toBeTruthy();
  expect(pendingContainer.querySelector(".furnace-bubble-user").textContent).toContain("等待编译");
  expect(pendingContainer.querySelector(".furnace-bubble-ai").textContent).toContain("正在整理材料与上下文");
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
      today_snooze: { items: [] },
    },
    pendingSubmissions: [
      { id: "done-output", status: "done", displayText: "生成报告", reconcileTarget: "outputs", reconcilePath: "output/reports/r.md", runNotesPath: "output/control/runs/ask-r/thinking.md", runId: "ask-r" },
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
  const outputBubble = container.querySelector(".furnace-conversation-item .furnace-bubble-ai");
  const resultCard = outputBubble.querySelector(".furnace-artifact-card");
  const actions = outputBubble.querySelector(".furnace-artifact-actions");
  expect(resultCard).toBeTruthy();
  expect(actions).toBeTruthy();
  expect(resultCard.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(container.querySelector(".furnace-pending-open-report-btn")).toBeTruthy();
  container.querySelector(".furnace-pending-quote-report-btn").click();
  expect(plugin.quoteFileToComposer).toHaveBeenCalledWith("output/reports/r.md");
  expect(container.textContent).toContain("查看进度笔记");
  expect(container.textContent).toContain("只包含外部化阶段记录，不包含模型内部过程。");
  container.querySelector(".furnace-run-notes-open-btn").click();
  expect(plugin.openWorkspacePath).toHaveBeenCalledWith("output/control/runs/ask-r/thinking.md");
  expect(container.textContent).toContain("回执已就绪");
  expect(container.textContent).toContain("执行回执 Receipt");
  expect(container.querySelector(".furnace-pending-open-receipt-btn")).toBeTruthy();
  expect(container.textContent).toContain("生成被阻断");
  expect(container.textContent).toContain("backend unavailable");
  expect(container.textContent).toContain("重试");
  expect(container.textContent).toContain("需要人工确认");
  expect(container.querySelector(".furnace-pending-exception-btn")).toBeTruthy();
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
      today_snooze: { items: [] },
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

  expect(container.textContent).toContain("恢复产物已就绪");
  expect(container.textContent).toContain("恢复产物 Artifact");
  expect(container.textContent).toContain("打开产物");
  expect(container.textContent).toContain("重试");
  expect(container.textContent).not.toContain("引用此报告追问");
  expect(container.querySelector(".furnace-pending-quote-report-btn")).toBeNull();
  expect(container.querySelector(".furnace-pending-open-report-btn").textContent).toBe("打开产物");
});

test("degraded output retry clears stale run id and records new background job", async () => {
  const context = loadRenderContext();
  const plugin = makePlugin({
    shellSummary: {
      generated_at: "2026-05-13T10:00:00Z",
      review_backlog_counts: {},
      recent_outputs: [],
      recent_receipts: [],
      suggested_next_actions: [],
      metrics_history_delta: { available: false },
      today_snooze: { items: [] },
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
  plugin.runAskCommand = jest.fn().mockResolvedValue({ job_id: "job-new", run_id: "new-run", run_notes_path: "output/control/runs/new/thinking.md" });
  const container = document.createElement("div");

  context.renderTodayFeed(plugin, container);
  await flushAsyncWork();
  container.querySelector(".furnace-pending-retry-report-btn").click();
  await flushAsyncWork();

  expect(plugin.runAskCommand).toHaveBeenCalledWith(expect.objectContaining({ question: "重试问题", format: "report", mode: "run-ask" }));
  expect(plugin.pendingSubmissions[0]).toEqual(expect.objectContaining({
    status: "received",
    jobId: "job-new",
    runId: "new-run",
    runNotesPath: "output/control/runs/new/thinking.md",
  }));
  expect(plugin.pendingSubmissions[0].retryArgs).toEqual(expect.objectContaining({
    jobId: "job-new",
    runId: "new-run",
    runNotesPath: "output/control/runs/new/thinking.md",
    longRunning: true,
  }));
});

test("reconcile pending report prefers run_id and stores delivery metadata", () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  Object.assign(plugin, makePlugin());
  plugin.savePluginState = jest.fn();
  plugin.refreshOpenViews = jest.fn();
  plugin.updateLongRunningPoller = jest.fn();
  plugin.pendingSubmissions = [
    {
      id: "p-report",
      status: "received",
      payloadFingerprint: "unmatched text fingerprint",
      displayText: "生成报告",
      startedAt: "2026-05-13T08:59:00Z",
      runId: "ask-report-1",
      retryArgs: { runId: "ask-report-1", longRunning: true, format: "report" },
    },
  ];

  plugin.reconcilePendingSubmissions({
    recent_outputs: [
      {
        path: "output/reports/final.md",
        title: "完全不同标题",
        created_at: "2026-05-13T09:00:00Z",
        run_id: "ask-report-1",
        run_notes_path: "output/control/runs/ask-report-1/thinking.md",
        delivery_mode: "deterministic-fallback",
        llm_status: "timeout_or_unavailable",
        llm_backend: "codex-cli",
        llm_model: "gpt-5.5",
      },
    ],
    recent_receipts: [],
    recent_raw_inputs: [],
  });

  expect(plugin.pendingSubmissions).toHaveLength(1);
  expect(plugin.pendingSubmissions[0]).toEqual(expect.objectContaining({
    id: "p-report",
    status: "done",
    reconcileTarget: "outputs",
    reconcilePath: "output/reports/final.md",
    runId: "ask-report-1",
    runNotesPath: "output/control/runs/ask-report-1/thinking.md",
    deliveryMode: "deterministic-fallback",
    llmStatus: "timeout_or_unavailable",
    llmBackend: "codex-cli",
    llmModel: "gpt-5.5",
  }));
});

test("runAskCommand uses background submit for report mode", async () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  plugin.t = (text) => text;
  plugin.runPluginCommand = jest.fn().mockResolvedValue({ payload: { kind: "run-ask-background-job", job_id: "job-1" } });

  const payload = await plugin.runAskCommand({
    question: "请生成一份深度报告",
    format: "report",
    mode: "run-ask",
    protocol: "research",
  });

  expect(plugin.runPluginCommand).toHaveBeenCalledWith(
    expect.stringContaining("Long Report"),
    ["run-ask-submit", "请生成一份深度报告", "--format", "report", "--protocol", "research", "--lean", "--fallback-to-ask"],
    expect.objectContaining({ refreshAfter: true, longRunning: true, backgroundSubmit: true })
  );
  expect(payload).toEqual({ kind: "run-ask-background-job", job_id: "job-1" });
});

test("shell summary fixture builds today DOM headings and furnace center keeps only primary entry surfaces", () => {
  const context = loadRenderContext();
  const feed = context.buildTodayFeed(SHELL_SUMMARY_FIXTURE);
  expect(feed.some((entry) => entry.kind === "report")).toBe(true);
  expect(feed.some((entry) => entry.kind === "automation")).toBe(true);
  expect(feed.some((entry) => entry.kind === "decision")).toBe(true);

  const todayContainer = document.createElement("div");
  context.renderTodayFeed(makePlugin({ shellSummary: SHELL_SUMMARY_FIXTURE }), todayContainer);
  expect(todayContainer.textContent).toContain("新报告");
  expect(todayContainer.textContent).toContain("系统动态");
  expect(todayContainer.textContent).toContain("需要你确认");

  const homeContainer = document.createElement("div");
  context.renderFurnaceCenter(makePlugin({ shellSummary: SHELL_SUMMARY_FIXTURE }), homeContainer);
  expect(homeContainer.querySelector(".furnace-universal-input-textarea")).toBeTruthy();
  expect(homeContainer.querySelector(".furnace-today-feed")).toBeTruthy();
  expect(homeContainer.querySelector(".furnace-advanced-drawer")).toBeTruthy();
  expect(homeContainer.lastElementChild.classList.contains("furnace-conversation-composer")).toBe(true);
  expect(homeContainer.querySelector(".furnace-shell-dropzone")).toBeNull();
  expect(homeContainer.textContent).not.toContain("Drop URL / PDF / Image / Repo");
  expect(homeContainer.textContent).not.toContain("System Status");
  expect(homeContainer.textContent).not.toContain("LLM Health");
  expect(homeContainer.textContent).not.toContain("Repair Backlog");
  expect(homeContainer.querySelector(".furnace-advanced-drawer").textContent).toContain("Open Recent Runs");
});

test("advanced status panel renders backup LLM fallback readiness", () => {
  const context = loadRenderContext();
  const container = document.createElement("div");
  const plugin = makePlugin({
    shellSummary: SHELL_SUMMARY_FIXTURE,
    getAdvancedSectionExpanded: jest.fn((key) => key === "status"),
    currentLlmHealth: jest.fn(() => ({ status: "healthy", backend: "opencode-api", model: "deepseek-v4-pro" })),
    currentShellSyncState: jest.fn(() => ({ status: "healthy", reason: "Summary ready." })),
  });

  context.renderFurnaceCenter(plugin, container);

  expect(container.textContent).toContain("Backup LLM route ready: 1/1");
  expect(container.textContent).toContain("codex-cli/gpt-5.5: available");
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
    today_snooze: { items: [] },
  };
  const container = document.createElement("div");

  context.renderFurnaceCenter(makePlugin({ shellSummary: unconfiguredSummary }), container);

  expect(container.textContent).toContain("LLM 未配置");
  expect(container.querySelector(".furnace-universal-input-textarea")).toBeTruthy();
  expect(container.querySelector(".furnace-universal-input-button").disabled).toBe(false);
  expect(container.textContent).toContain("今天还没有新报告");
  expect(container.querySelector(".furnace-today-cta-submit")).toBeTruthy();
});

test("recent raw inputs reconcile received pending card to done with raw target", () => {
  const context = loadRenderContext();
  const plugin = new context.FurnaceProductShellPlugin();
  Object.assign(plugin, makePlugin());
  plugin.pendingSubmissions = [
    {
      id: "p-raw",
      status: "received",
      payloadFingerprint: "raw/inbox/product-shell-smoke.md",
      title: "Product Shell smoke",
      startedAt: "2026-05-13T08:59:00Z",
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
        occurred_at: "2026-05-13T09:00:00Z",
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
