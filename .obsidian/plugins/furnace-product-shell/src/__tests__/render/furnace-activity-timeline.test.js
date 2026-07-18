"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

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

function loadRenderer(buildTodayFeed) {
  const src = fs.readFileSync(
    path.resolve(__dirname, "../../render_today.js"),
    "utf8"
  );
  const context = {
    buildTodayFeed,
    module: { exports: {} },
    exports: {},
    Date,
    String,
    Array,
  };
  vm.runInNewContext(
    `${src}\nmodule.exports = { renderFurnaceActivityTimeline };`,
    context
  );
  return context.module.exports.renderFurnaceActivityTimeline;
}

function makePlugin({ summary = null, recentRuns = [], showAdvancedCommands = true } = {}) {
  return {
    shellSummary: summary,
    pluginState: { recentRuns },
    settings: { showAdvancedCommands },
    t: (key) => ({
      "Furnace activity": "炉子动态",
      "No recent furnace activity": "暂无炉子动态",
      "Plugin run": "插件运行",
      Receipt: "回执",
      "Review backlog": "待处理积压",
      "新报告": "新报告",
      "系统动态": "系统动态",
      "需要你确认": "需要你确认",
      "已完成": "已完成",
      "下一步建议": "下一步建议",
    }[key] || key),
  };
}

beforeEach(() => {
  document.body.innerHTML = "";
});

test("hides furnace activity for normal users", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({ showAdvancedCommands: false }), container);

  expect(container.querySelector(".furnace-activity-timeline")).toBeNull();
});

test("renders heading and empty element when both sources are empty", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin(), container);

  expect(container.querySelector(".furnace-activity-timeline h3").textContent).toBe("炉子动态");
  expect(container.querySelector(".furnace-activity-timeline-empty").textContent).toBe("暂无炉子动态");
});

test("renders plugin-run items when only recentRuns are populated", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    recentRuns: [{ label: "Compile", status: "success", protocol: "general", finishedAt: "2026-05-11T10:00:00Z" }],
  }), container);

  const item = container.querySelector("li.furnace-activity-item-plugin-run");
  expect(item).toBeTruthy();
  expect(item.querySelector(".furnace-activity-kind").textContent).toBe("插件运行");
  expect(item.querySelector(".furnace-activity-title").textContent).toBe("Compile");
});

test("sorts mixed feed and recentRuns descending by timestamp", () => {
  const feed = [
    { kind: "report", title: "Old report", summary: "", timestamp: "2026-05-11T09:00:00Z" },
    { kind: "action", title: "New action", summary: "", timestamp: "2026-05-11T11:00:00Z" },
  ];
  const renderFurnaceActivityTimeline = loadRenderer(() => feed);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: { generated_at: "2026-05-11T12:00:00Z" },
    recentRuns: [{ label: "Middle run", status: "success", finishedAt: "2026-05-11T10:00:00Z" }],
  }), container);

  const titles = Array.from(container.querySelectorAll(".furnace-activity-title")).map((el) => el.textContent);
  expect(titles).toEqual(["New action", "Middle run", "Old report"]);
});

test("caps rendered activity items at 50", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");
  const recentRuns = Array.from({ length: 60 }, (_, index) => ({
    label: `Run ${index}`,
    status: "success",
    finishedAt: `2026-05-11T10:${String(index).padStart(2, "0")}:00Z`,
  }));

  renderFurnaceActivityTimeline(makePlugin({ recentRuns }), container);

  expect(container.querySelectorAll("li.furnace-activity-item")).toHaveLength(50);
});

test("renders off-day non-elixir recent receipt", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: {
      generated_at: "2026-05-11T12:00:00Z",
      recent_receipts: [{
        title: "Archive applied",
        operation: "archive-apply",
        created_at: "2026-05-09T08:00:00Z",
        receipt_path: "output/receipts/archive.json",
      }],
    },
  }), container);

  const item = container.querySelector("li.furnace-activity-item-receipt");
  expect(item).toBeTruthy();
  expect(item.querySelector(".furnace-activity-kind").textContent).toBe("回执");
  expect(item.querySelector(".furnace-activity-title").textContent).toBe("Archive applied");
});

test("renders only exception review backlog buckets", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: {
      generated_at: "2026-05-11T12:00:00Z",
      review_backlog_counts: { counter_evidence_candidates: 3, overdue_actions: 2, ready_actions: 1, empty_bucket: 0 },
    },
  }), container);

  const items = container.querySelectorAll("li.furnace-activity-item-review-backlog");
  expect(items).toHaveLength(1);
  expect(items[0].querySelector(".furnace-activity-title").textContent).toBe("补充反证候选");
  expect(items[0].querySelector(".furnace-activity-summary").textContent).toBe("3 项待处理 · 检查新来源是否足以反驳既有判断");
});

test("hides unknown review backlog buckets from primary timeline", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => []);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: {
      generated_at: "2026-05-11T12:00:00Z",
      review_backlog_counts: { unknown_made_up_bucket: 1 },
    },
  }), container);

  const item = container.querySelector("li.furnace-activity-item-review-backlog");
  expect(item).toBeFalsy();
});

test("deduplicates feed elixir and raw receipt with the same target", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => [{
    kind: "elixir",
    title: "Curated elixir",
    summary: "done",
    timestamp: "2026-05-11T12:00:00Z",
    target: "output/receipts/shared.json",
  }]);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: {
      generated_at: "2026-05-11T12:00:00Z",
      recent_receipts: [{
        title: "Raw receipt",
        operation: "elixir",
        created_at: "2026-05-11T11:00:00Z",
        receipt_path: "output/receipts/shared.json",
      }],
    },
  }), container);

  expect(container.querySelectorAll("li.furnace-activity-item")).toHaveLength(1);
  expect(container.querySelector(".furnace-activity-title").textContent).toBe("Curated elixir");
});

test("keeps empty and invalid timestamps rendered and sorted to the bottom", () => {
  const renderFurnaceActivityTimeline = loadRenderer(() => [
    { kind: "report", title: "Valid", summary: "", timestamp: "2026-05-11T12:00:00Z" },
    { kind: "action", title: "Empty timestamp", summary: "", timestamp: "" },
    { kind: "automation", title: "Invalid timestamp", summary: "", timestamp: "not-a-date" },
  ]);
  const container = document.createElement("div");

  renderFurnaceActivityTimeline(makePlugin({
    summary: { generated_at: "2026-05-11T12:00:00Z" },
  }), container);

  const titles = Array.from(container.querySelectorAll(".furnace-activity-title")).map((el) => el.textContent);
  expect(titles).toEqual(["Valid", "Empty timestamp", "Invalid timestamp"]);
});
