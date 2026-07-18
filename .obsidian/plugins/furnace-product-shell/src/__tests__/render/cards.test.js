"use strict";

// Obsidian extends HTMLElement with createDiv/createEl. Polyfill for jsdom.
if (!HTMLElement.prototype.createDiv) {
  HTMLElement.prototype.createDiv = function (opts) {
    const el = document.createElement("div");
    if (opts && typeof opts === "object") {
      if (opts.cls) el.className = opts.cls;
      if (opts.text) el.textContent = opts.text;
      if (opts.attr) {
        for (const [k, v] of Object.entries(opts.attr)) el.setAttribute(k, v);
      }
    }
    this.appendChild(el);
    return el;
  };
}
if (!HTMLElement.prototype.createEl) {
  HTMLElement.prototype.createEl = function (tag, opts) {
    const el = document.createElement(tag);
    if (opts && typeof opts === "object") {
      if (opts.cls) el.className = opts.cls;
      if (opts.text) el.textContent = opts.text;
      if (opts.attr) {
        for (const [k, v] of Object.entries(opts.attr)) el.setAttribute(k, v);
      }
    }
    this.appendChild(el);
    return el;
  };
}
if (!HTMLElement.prototype.addClass) {
  HTMLElement.prototype.addClass = function (cls) {
    if (cls) this.classList.add(cls);
  };
}

const { renderFeedCard, renderReportCard, renderConfirmationCard, renderCompoundSuggestActions, isReportUnread } = require("../../render/cards");

function makeMockPlugin() {
  return {
    settings: { lastViewedTimestamp: null },
    t: (key) => key,
    openWorkspacePath: jest.fn().mockResolvedValue(true),
    runReportSubgraphCommand: jest.fn().mockResolvedValue(),
    openReviewPageContextPicker: jest.fn().mockResolvedValue(),
    runCompoundFileBack: jest.fn().mockResolvedValue(),
    openCompoundAlchemyStart: jest.fn(),
  };
}

beforeEach(() => {
  document.body.innerHTML = "";
});

test("renderFeedCard creates a card with title and summary", () => {
  const plugin = makeMockPlugin();
  const container = document.createElement("div");
  const entry = {
    kind: "report",
    title: "Test Report",
    summary: "A test report",
    protocol: "research",
    target: "output/reports/test.md",
    timestamp: "2026-05-03T12:00:00Z",
  };

  const { card } = renderFeedCard(plugin, container, entry);

  expect(card.classList.contains("furnace-feed-card")).toBe(true);
  expect(card.classList.contains("furnace-protocol-research")).toBe(true);
  expect(card.querySelector(".furnace-feed-card-title").textContent).toBe("Test Report");
  expect(card.querySelector(".furnace-feed-card-summary").textContent).toBe("A test report");
});

test("renderFeedCard adds protocol class for known protocol", () => {
  const plugin = makeMockPlugin();
  const container = document.createElement("div");
  const entry = { kind: "report", title: "X", summary: "", protocol: "investing", target: "x", timestamp: "" };

  const { card } = renderFeedCard(plugin, container, entry);
  expect(card.classList.contains("furnace-protocol-investing")).toBe(true);
});

test("renderFeedCard does not add protocol class when protocol is empty", () => {
  const plugin = makeMockPlugin();
  const container = document.createElement("div");
  const entry = { kind: "report", title: "X", summary: "", protocol: "", target: "x", timestamp: "" };

  const { card } = renderFeedCard(plugin, container, entry);
  expect(card.classList.contains("furnace-protocol-")).toBe(false);
  expect(card.classList.contains("furnace-protocol-general")).toBe(false);
});

test("isReportUnread returns false when no lastViewedTimestamp", () => {
  const plugin = makeMockPlugin();
  expect(isReportUnread(plugin, { timestamp: "2026-05-03T12:00:00Z" })).toBe(false);
});

test("isReportUnread returns true when report is newer than last viewed", () => {
  const plugin = makeMockPlugin();
  plugin.settings.lastViewedTimestamp = "2026-05-01T00:00:00Z";
  expect(isReportUnread(plugin, { timestamp: "2026-05-03T12:00:00Z" })).toBe(true);
});

test("isReportUnread returns false when report is older", () => {
  const plugin = makeMockPlugin();
  plugin.settings.lastViewedTimestamp = "2026-05-05T00:00:00Z";
  expect(isReportUnread(plugin, { timestamp: "2026-05-03T12:00:00Z" })).toBe(false);
});

describe("renderReportCard", () => {
  test("does not render View graph button after W4 report-subgraph removal", () => {
    const plugin = makeMockPlugin();
    plugin.settings.showAdvancedCommands = true;
    const cardEl = document.createElement("div");

    renderReportCard(plugin, cardEl, { target: "output/reports/foo.md" });

    const graphBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "View graph");
    expect(graphBtn).toBeUndefined();
  });

  test("Open report button calls openWorkspacePath", () => {
    const plugin = makeMockPlugin();
    const cardEl = document.createElement("div");

    renderReportCard(plugin, cardEl, { target: "output/reports/foo.md" });

    const openBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "Open report");
    openBtn.click();

    expect(plugin.openWorkspacePath).toHaveBeenCalledWith("output/reports/foo.md");
  });

  test("renders compound suggest file-back CTA on report card", () => {
    const plugin = makeMockPlugin();
    const cardEl = document.createElement("div");
    const suggest = {
      action: "file-back-judgment",
      report_path: "output/reports/foo.md",
      title: "沉淀：Question",
    };

    renderReportCard(plugin, cardEl, { target: "output/reports/foo.md", compound_suggest: suggest });

    const fileBackBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "沉淀");
    expect(fileBackBtn).toBeTruthy();
    fileBackBtn.click();
    expect(plugin.runCompoundFileBack).toHaveBeenCalledWith(suggest);
  });

  test("renders compound suggest alchemy-start CTA on report card", () => {
    const plugin = makeMockPlugin();
    const cardEl = document.createElement("div");
    const suggest = {
      action: "alchemy-start",
      corpus_id: "corpus-a",
      topic: "Follow-up",
    };

    renderReportCard(plugin, cardEl, { target: "output/reports/foo.md", compound_suggest: suggest });

    const alchemyBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "凝丹");
    expect(alchemyBtn).toBeTruthy();
    alchemyBtn.click();
    expect(plugin.openCompoundAlchemyStart).toHaveBeenCalledWith(suggest);
  });
});

describe("renderConfirmationCard", () => {
  test("review button opens review-page picker without review-next", async () => {
    const plugin = makeMockPlugin();
    const cardEl = document.createElement("div");

    renderConfirmationCard(plugin, cardEl, { target: "review:pending-item" });

    const reviewBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "Review");
    const snoozeBtn = Array.from(cardEl.querySelectorAll("button")).find((btn) => btn.textContent === "Snooze");

    expect(reviewBtn).toBeTruthy();
    expect(snoozeBtn).toBeUndefined();

    reviewBtn.click();
    await Promise.resolve();

    expect(plugin.openReviewPageContextPicker).toHaveBeenCalled();
  });
});
