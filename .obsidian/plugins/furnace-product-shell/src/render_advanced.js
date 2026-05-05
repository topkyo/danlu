// Advanced drawer and metrics rendering helpers.
function renderAdvancedDrawer(plugin, container) {
  const wrapper = container.createDiv({ cls: "furnace-advanced-drawer" });
  const details = wrapper.createEl("details", { cls: "furnace-shell-advanced" });
  const summaryEl = details.createEl("summary", { cls: "furnace-shell-advanced-summary", attr: { tabindex: "0" } });
  const summaryCopy = summaryEl.createDiv({ cls: "furnace-shell-advanced-copy" });
  summaryCopy.createEl("span", { cls: "furnace-shell-advanced-title", text: plugin.t("Advanced") });
  const counts = advancedDrawerCounts(plugin);
  const totalActive = counts.review + counts.execution + counts.runs;
  const descText = totalActive === 0
    ? plugin.t("系统状态、模型、运行历史等高级面板")
    : plugin.t("待复核 {review_count} · 待执行 {execution_count} · 近期运行 {run_count}", {
        review_count: counts.review,
        execution_count: counts.execution,
        run_count: counts.runs,
      });
  summaryCopy.createEl("span", {
    cls: "furnace-shell-advanced-description",
    text: descText,
  });
  const body = details.createDiv({ cls: "furnace-shell-advanced-body" });

  // R89: 开发者层心理预期分隔
  body.createEl("div", {
    cls: "furnace-advanced-dev-banner",
    text: plugin.t("以下为开发者诊断信息"),
  });

  plugin.renderMainHeader(body);
  plugin.renderStatusPanel(body);
  plugin.renderLegacyAdvancedPanel(body);

  renderAdvancedMetricsPanel(plugin, body);
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
