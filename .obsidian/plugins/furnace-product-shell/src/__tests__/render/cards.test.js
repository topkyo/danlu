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

const { renderFeedCard, isReportUnread } = require("../../render/cards");

function makeMockPlugin() {
  return {
    settings: { lastViewedTimestamp: null },
    t: (key) => key,
    goToReport: jest.fn(),
    viewReviewTodayEntry: jest.fn(),
    snoozeTodayEntry: jest.fn(),
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
