// Furnace center render entrypoint.
function renderFurnaceCenter(plugin, contentEl) {
  contentEl.empty();
  contentEl.addClass("furnace-shell-view");
  contentEl.addClass("furnace-shell-main-view");
  contentEl.addClass("furnace-shell-v3");

  if (!plugin.repoState.valid) {
    contentEl.createDiv({
      cls: "furnace-shell-empty",
      text: plugin.t("Vault runtime unavailable. Missing scaffold or launcher: {missing}", {
        missing: plugin.repoState.missingPaths.join(", "),
      }),
    });
    return;
  }

  // 1. Start guide (fresh vault onboarding)
  renderStartGuide(plugin, contentEl);

  // 2. Today Feed / conversation stream
  renderTodayFeed(plugin, contentEl);

  // 3. Advanced Drawer
  renderAdvancedDrawer(plugin, contentEl);

  // 4. Conversation Composer — keep it at the bottom of the shell surface.
  renderUniversalInput(plugin, contentEl);
}

function renderStartGuide(plugin, container) {
  var summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;

  var stats = summary && summary.knowledge_stats;
  var hasConcepts = stats && typeof stats.concept_nodes === "number" && stats.concept_nodes > 0;
  var hasSources = stats && typeof stats.source_nodes === "number" && stats.source_nodes > 0;
  var reports = summary && Array.isArray(summary.todays_reports) ? summary.todays_reports : [];
  var hasReports = reports.length > 0;
  var recentOutputs = summary && Array.isArray(summary.recent_outputs) ? summary.recent_outputs : [];
  var hasOutputs = recentOutputs.length > 0;
  var isEmptyVault = !(hasConcepts || hasSources || hasReports || hasOutputs);

  // dismiss 仅作用于"非空 vault"的 onboarding；空 vault 下始终保留引导
  if (plugin.settings && plugin.settings.onboardingShown && !isEmptyVault) return;

  // 非空 vault 且 onboarding 未关闭 → 自动 dismiss
  if (!isEmptyVault && summary) {
    plugin.settings.onboardingShown = true;
    plugin.savePluginState();
    return;
  }

  var guide = container.createDiv({ cls: "furnace-start-guide" });

  var header = guide.createDiv({ cls: "furnace-start-guide-header" });
  header.createEl("span", { cls: "furnace-start-guide-icon", text: "🔥" });
  header.createEl("span", { cls: "furnace-start-guide-title", text: plugin.t("欢迎使用炼丹炉") });

  var steps = guide.createDiv({ cls: "furnace-start-guide-steps" });
  var stepData = [
    [plugin.t("投料"), plugin.t("拖入 URL、PDF 或图片，或直接在输入框提问")],
    [plugin.t("等待编译"), plugin.t("炉子会自动处理原料，抽概念、建关联")],
    [plugin.t("看报告"), plugin.t("每天回到炉子，Today 里就是你需要看的")],
  ];
  stepData.forEach(function (item, i) {
    var step = steps.createDiv({ cls: "furnace-start-guide-step" });
    step.createEl("span", { cls: "furnace-start-guide-step-num", text: String(i + 1) });
    var copy = step.createDiv({ cls: "furnace-start-guide-step-copy" });
    copy.createEl("strong", { text: item[0] });
    copy.createEl("div", { cls: "furnace-start-guide-step-desc", text: item[1] });
  });

  var dismissBtn = guide.createEl("button", { cls: "furnace-start-guide-dismiss", text: plugin.t("知道了，开始使用") });
  dismissBtn.addEventListener("click", function () {
    guide.remove();
    plugin.settings.onboardingShown = true;
    plugin.savePluginState();
  });
}
