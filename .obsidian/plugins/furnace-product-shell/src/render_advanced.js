// Advanced drawer and metrics rendering helpers.
// R91: 重组为 3 个可折叠 section（系统状态 / 运行与历史 / 开发者操作），降低首屏认知负担。
// 不再嵌外层 Advanced <details>；三组直接挂在 wrapper 上。
function renderAdvancedDrawer(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-advanced-drawer" });

  // 顶部抽屉外置 dev banner（R89 心理预期分隔；不进任一 section）
  wrapper.createEl("div", {
    cls: "furnace-advanced-dev-banner",
    text: plugin.t("以下为开发者诊断信息"),
  });

  // 三组 section 直接挂 wrapper（去掉 R90 之前的外层 Advanced 折叠层）
  const body = wrapper;

  renderAdvancedSection(plugin, body, {
    key: "status",
    title: plugin.t("系统状态"),
    summaryText: buildStatusSectionSummary(plugin),
    render: (el) => {
      plugin.renderMainHeader(el);
      plugin.renderStatusPanel(el);
      renderAdvancedMetricsPanel(plugin, el);
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

  renderAdvancedSection(plugin, body, {
    key: "devops",
    title: plugin.t("开发者操作"),
    summaryText: plugin.t("编译 / 同步 / 协议切换 / 日志等命令"),
    render: (el) => {
      plugin.renderLegacyAdvancedPanel(el);
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

// R91: 系统状态 section 摘要 — 协议 / LLM / 同步状态 一行
function buildStatusSectionSummary(plugin) {
  let protocolName = "";
  if (plugin.shellSummary && typeof plugin.shellSummary === "object") {
    protocolName = String(plugin.shellSummary.protocol || plugin.shellSummary.active_protocol || "").trim();
  }
  if (!protocolName) protocolName = plugin.t("未配置");

  let llmLabel = "";
  try {
    const llmHealth = plugin.currentLlmHealth();
    const backend = String((llmHealth && llmHealth.backend) || "").trim();
    const model = String((llmHealth && llmHealth.model) || "").trim();
    if (backend && model) llmLabel = `${backend}/${model}`;
    else if (backend) llmLabel = backend;
    else if (model) llmLabel = model;
  } catch (error) {
    llmLabel = "";
  }
  if (!llmLabel) llmLabel = plugin.t("未配置");

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

  return plugin.t("协议 {protocol} · LLM {llm} · 同步 {sync}", {
    protocol: protocolName,
    llm: llmLabel,
    sync: syncLabel,
  });
}

// R91: 运行与历史 section 摘要 — 最近运行数 + review/execution 待办
function buildHistorySectionSummary(plugin) {
  const counts = advancedDrawerCounts(plugin);
  return plugin.t("最近运行 {n} 条 · 待审 {review} · 待执行 {execution}", {
    n: counts.runs,
    review: counts.review,
    execution: counts.execution,
  });
}

// R91: 运行与历史 section 主体 — 入口按钮 + 最近 LLM 运行摘要
function renderHistorySectionBody(plugin, container) {
  const buttons = [
    {
      key: "open-recent-runs",
      label: plugin.t("Open Recent Runs"),
      onClick: () => {
        try {
          plugin.openRecentRunsView();
        } catch (error) {
          // surface via Notice if available
        }
      },
    },
    {
      key: "open-review-center",
      label: plugin.t("Open Review Center"),
      onClick: () => {
        try {
          plugin.openReviewCenterView();
        } catch (error) {}
      },
    },
    {
      key: "open-execution-center",
      label: plugin.t("Open Execution Center"),
      onClick: () => {
        try {
          plugin.openExecutionCenterView();
        } catch (error) {}
      },
    },
  ];
  if (typeof plugin.renderInlineButtons === "function") {
    plugin.renderInlineButtons(container, buttons, "furnace-advanced-section-actions");
  } else {
    const row = container.createDiv({ cls: "furnace-advanced-section-actions" });
    for (const btn of buttons) {
      const el = row.createEl("button", { cls: "furnace-shell-button", text: btn.label });
      el.addEventListener("click", btn.onClick);
    }
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
  const executionControls = summary.execution_controls && typeof summary.execution_controls === "object" ? summary.execution_controls : {};
  const actionCount = Array.isArray(executionControls.actions)
    ? executionControls.actions.filter((action) => action && typeof action === "object" && (action.can_apply || action.can_review || action.can_revert)).length
    : 0;
  const archiveCount = Array.isArray(executionControls.archives)
    ? executionControls.archives.filter((entry) => entry && typeof entry === "object" && (entry.can_apply || entry.can_revert)).length
    : 0;
  const runs = plugin.pluginState && Array.isArray(plugin.pluginState.recentRuns) ? plugin.pluginState.recentRuns.length : 0;
  return { review, execution: actionCount + archiveCount, runs };
}

function renderAdvancedMetricsPanel(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  if (!summary) return;
  
  const metrics = Array.isArray(summary.metrics) ? summary.metrics : [];
  
  const section = container.createDiv({ cls: "furnace-advanced-metrics" });
  section.createEl("h3", { text: plugin.t("Knowledge Compounding Metrics") });
  
  if (!metrics.length) {
    section.createEl("div", {
      cls: "furnace-advanced-metrics-empty",
      text: plugin.t("(metrics unavailable; run aiwiki metrics for details)"),
    });
    return;
  }
  
  const list = section.createEl("ul", { cls: "furnace-advanced-metrics-list" });
  
  const labels = {
    provenance_completeness: plugin.t("Provenance Completeness"),
    stale_ratio: plugin.t("Stale Page Ratio"),
    review_closure_rate: plugin.t("Review Closure Rate (7d)"),
    proposal_acceptance_rate: plugin.t("Proposal Acceptance Rate"),
    judgment_revisit_rate: plugin.t("Judgment Revisit Rate"),
    output_file_back_rate: plugin.t("Output File-back Rate"),
    elixir_reuse_count: plugin.t("Elixir Reuse Count"),
  };
  
  for (const m of metrics) {
    if (!m || typeof m !== "object") continue;
    const li = list.createEl("li", { cls: "furnace-advanced-metrics-item" });
    const labelText = labels[m.key] || m.key;
    li.createEl("span", { cls: "furnace-advanced-metrics-label", text: labelText });
    
    if (m.value === null || m.value === undefined) {
      li.createEl("span", {
        cls: "furnace-advanced-metrics-value furnace-advanced-metrics-unavailable",
        text: plugin.t("unavailable"),
      });
      if (m.reason) {
        li.createEl("span", {
          cls: "furnace-advanced-metrics-reason",
          text: ` — ${m.reason}`,
        });
      }
    } else {
      const formatted = formatMetricValue(m.value, m.unit);
      li.createEl("span", {
        cls: "furnace-advanced-metrics-value",
        text: formatted,
      });
      if (typeof m.sample_size === "number" && m.sample_size > 0) {
        li.createEl("span", {
          cls: "furnace-advanced-metrics-sample",
          text: ` (n=${m.sample_size})`,
        });
      }
    }
  }
  
  section.createEl("div", {
    cls: "furnace-advanced-metrics-hint",
    text: plugin.t("Run `aiwiki metrics --json` for full data."),
  });
}

function formatMetricValue(value, unit) {
  if (typeof value !== "number") return String(value);
  if (unit === "ratio") return (value * 100).toFixed(1) + "%";
  if (unit === "percent") return value.toFixed(1) + "%";
  if (unit === "count") return String(value);
  return String(value);
}
