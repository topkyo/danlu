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
    runDroppedFilesWithAutoAsk: jest.fn().mockResolvedValue({ materialPaths: ["raw/inbox/input.md"], askQuestion: "Q" }),
    runDroppedPayloadsWithAutoAsk: jest.fn().mockResolvedValue({ materialPaths: ["raw/inbox/input.md"], askQuestion: "Q" }),
    runUniversalInputCommand: jest.fn().mockResolvedValue({ note_path: "raw/inbox/url.md" }),
    runAskCommand: jest.fn().mockResolvedValue({}),
    renderMainHeader: jest.fn((el) => el.createDiv({ cls: "test-main-header", text: "header" })),
    renderStatusPanel: jest.fn((el) => el.createDiv({ cls: "test-status-panel", text: "status" })),
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
  expect(pendingContainer.querySelector(".furnace-pending-card")).toBeTruthy();
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
  expect(homeContainer.querySelector(".furnace-shell-dropzone")).toBeNull();
  expect(homeContainer.textContent).not.toContain("Drop URL / PDF / Image / Repo");
  expect(homeContainer.textContent).not.toContain("System Status");
  expect(homeContainer.textContent).not.toContain("LLM Health");
  expect(homeContainer.textContent).not.toContain("Repair Backlog");
  expect(homeContainer.querySelector(".furnace-advanced-drawer").textContent).toContain("Open Recent Runs");
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
