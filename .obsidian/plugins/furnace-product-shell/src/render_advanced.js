// Advanced drawer and metrics rendering helpers.
// Operator-only diagnostics/history surface; the default shell path does not render this drawer.
function renderAdvancedDrawer(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-advanced-drawer" });

  wrapper.createEl("div", {
    cls: "furnace-advanced-dev-banner",
    text: plugin.t("以下为运行诊断与历史"),
  });

  const body = wrapper;

  renderAdvancedSection(plugin, body, {
    key: "status",
    title: plugin.t("系统状态"),
    summaryText: buildStatusSectionSummary(plugin),
    render: (el) => {
      plugin.renderStatusPanel(el);
    },
  });

  renderAdvancedSection(plugin, body, {
    key: "history",
    title: plugin.t("运行与历史"),
    summaryText: buildHistorySectionSummary(plugin),
    render: (el) => {
      renderHistorySectionBody(plugin, el);
    },
  });

}

// R91: 单个 section 渲染。<details>/<summary> 原生折叠 + toggle 持久化。
function renderAdvancedSection(plugin, parentEl, spec) {
  const expanded = plugin.getAdvancedSectionExpanded(spec.key);
  const sectionAttr = { "data-section-key": spec.key };
  if (expanded) sectionAttr.open = "open";
  const sectionEl = parentEl.createEl("details", {
    cls: `furnace-advanced-section furnace-advanced-section-${spec.key}`,
    attr: sectionAttr,
  });
  const summaryEl = sectionEl.createEl("summary", {
    cls: "furnace-advanced-section-summary",
    attr: { tabindex: "0" },
  });
  summaryEl.createEl("span", {
    cls: "furnace-advanced-section-title",
    text: spec.title,
  });
  const summaryHint = String(spec.summaryText || "").trim() || plugin.t("点击展开查看详细信息");
  summaryEl.createEl("span", {
    cls: "furnace-advanced-section-hint",
    text: summaryHint,
  });
  sectionEl.addEventListener("toggle", () => {
    const isOpen = Boolean(sectionEl.open);
    if (isOpen === plugin.getAdvancedSectionExpanded(spec.key)) return;
    plugin.setAdvancedSectionExpanded(spec.key, isOpen);
  });
  const bodyEl = sectionEl.createDiv({ cls: "furnace-advanced-section-body" });
  try {
    spec.render(bodyEl);
  } catch (error) {
    bodyEl.createEl("div", {
      cls: "furnace-advanced-section-error",
      text: String(error && error.message ? error.message : error),
    });
  }
}

// R91: 系统状态 section 摘要。默认产品面不暴露 protocol/LLM/sync 机制名。
function buildStatusSectionSummary(plugin) {
  let syncLabel = plugin.t("未知");
  try {
    const sync = plugin.currentShellSyncState();
    const status = String((sync && sync.status) || "").trim();
    if (status === "healthy") syncLabel = plugin.t("正常");
    else if (status === "running") syncLabel = plugin.t("Refreshing shell summary.");
    else if (status === "unknown") syncLabel = plugin.t("未知");
    else syncLabel = plugin.t("异常");
  } catch (error) {
    // keep 未知
  }

  return plugin.t("运行诊断 · 同步 {sync}", {
    sync: syncLabel,
  });
}

// R91: 运行与历史 section 摘要 — 最近运行数 + review 待办
function buildHistorySectionSummary(plugin) {
  const counts = advancedDrawerCounts(plugin);
  return plugin.t("最近运行 {n} 条 · 待审 {review}", {
    n: counts.runs,
    review: counts.review,
  });
}

// R91: 运行与历史 section 主体 — inline plugin run history only
function renderHistorySectionBody(plugin, container) {
  container.createDiv({
    cls: "furnace-shell-panel-note",
    text: plugin.t("Recent plugin-triggered runs are listed here when available."),
  });

  const runs = plugin.pluginState && Array.isArray(plugin.pluginState.recentRuns) ? plugin.pluginState.recentRuns : [];
  const section = container.createDiv({ cls: "furnace-advanced-section-run-history" });
  section.createEl("h4", { text: plugin.t("Latest plugin runs") });
  if (!runs.length) {
    section.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No recent plugin runs.") });
  } else {
    const list = section.createEl("ul", { cls: "furnace-shell-list" });
    runs.slice(0, 5).forEach(function (record) {
      const item = list.createEl("li");
      const label = record.command || record.label || plugin.t("command");
      const status = record.status || "unknown";
      item.createEl("strong", { text: label });
      item.createDiv({
        cls: "furnace-shell-meta",
        text: plugin.t(status) + " | " + (record.finishedAt || record.startedAt || ""),
      });
    });
  }

  // 最近 LLM 运行摘要（若有）
  try {
    const latest = plugin.latestLlmRun();
    if (latest && (latest.command || latest.backend || latest.model)) {
      const card = container.createDiv({ cls: "furnace-advanced-section-latest-llm" });
      const head = card.createDiv({ cls: "furnace-advanced-section-latest-llm-head" });
      head.createEl("span", { cls: "furnace-advanced-section-latest-llm-label", text: plugin.t("Latest LLM run") });
      const parts = [];
      if (latest.command) parts.push(latest.command);
      if (latest.backend) parts.push(latest.backend);
      if (latest.model) parts.push(latest.model);
      if (latest.status) parts.push(latest.status);
      head.createEl("span", { cls: "furnace-advanced-section-latest-llm-meta", text: parts.join(" · ") });
      if (latest.errorSummary) {
        card.createEl("div", { cls: "furnace-advanced-section-latest-llm-error", text: latest.errorSummary });
      }
    }
  } catch (error) {
    // 静默
  }
}

function advancedDrawerCounts(plugin) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : {};
  const review = sumNumericValues(summary.review_backlog_counts || {});
  const runs = plugin.pluginState && Array.isArray(plugin.pluginState.recentRuns) ? plugin.pluginState.recentRuns.length : 0;
  return { review, runs };
}

