// Render today feed and report surfaces for Product Shell.

function renderTodayFeed(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;

  const section = container.createDiv({ cls: "furnace-today-feed" });
  // Slim head: title + quiet refresh (no "last updated" chrome on the default path).
  const headRow = section.createDiv({ cls: "furnace-today-feed-head" });
  headRow.createEl("h2", { text: plugin.t("Today"), cls: "furnace-today-feed-title" });
  const refreshBtn = headRow.createEl("button", {
    cls: "furnace-today-refresh-btn furnace-today-refresh-quiet",
    text: plugin.t("Refresh"),
  });
  refreshBtn.setAttr && refreshBtn.setAttr("aria-label", plugin.t("刷新炉子"));
  refreshBtn.title = plugin.getLastSummaryRefreshLabel() || plugin.t("刷新炉子");
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    try {
      await plugin.refreshShellSummaryCommand();
      refreshBtn.title = plugin.getLastSummaryRefreshLabel() || plugin.t("刷新炉子");
    } catch (e) { /* 已在 plugin 层 Notice */ }
    finally { refreshBtn.disabled = false; }
  });

  // Operator-only activity chrome; default product path stays conversation + reports.
  renderFurnaceActivityTimeline(plugin, section);

  if (!summary) {
    section.createEl("div", {
      cls: "furnace-today-feed-empty",
      text: plugin.t("数据还没就绪。先点上方刷新，或等首次任务跑完。"),
    });
    // R88 #1 (P1 fix): summary 缺失也提供 CTA
    renderTodayEmptyCta(plugin, section, container);
    renderPendingSubmissionsGroup(plugin, section);
    scrollTodayConversationToEnd(section);
    return;
  }

  const feed = buildTodayFeed(summary);

  if (!feed.length) {
    const hasPending = Array.isArray(plugin.pendingSubmissions) && plugin.pendingSubmissions.length > 0;
    if (!hasPending) {
      const empty = section.createDiv({ cls: "furnace-today-feed-empty" });
      empty.createEl("div", {
        cls: "furnace-today-feed-empty-title",
        text: plugin.t("今天还没有新报告"),
      });
      empty.createEl("div", {
        cls: "furnace-today-feed-empty-hint",
        text: plugin.t("拖入 URL / PDF / 图片 / repo，或在上方直接提一个问题；生成的报告会出现在这里。"),
      });
      renderTodayEmptyCta(plugin, empty, container);
    }
    renderPendingSubmissionsGroup(plugin, section);
    scrollTodayConversationToEnd(section);
    return;
  }
  
  const groups = { report: [], automation: [], decision: [], proposal: [], elixir: [], action: [] };
  for (const entry of feed) groups[entry.kind].push(entry);

  // Keep Today flat: only deliverable reports, no extra section chrome.
  if (groups.report.length) {
    const listEl = section.createEl("ul", { cls: "furnace-today-feed-list furnace-today-feed-reports" });
    for (const entry of groups.report) {
      renderTodayFeedItem(plugin, listEl, entry);
    }
  }

  // Pending ask bubbles last — newest activity sits next to the composer.
  renderPendingSubmissionsGroup(plugin, section);
  scrollTodayConversationToEnd(section);
}

function scrollTodayConversationToEnd(section) {
  if (!section || typeof section.querySelector !== "function") return;
  const targets = section.querySelectorAll(
    ".furnace-conversation-item, .furnace-today-feed-list > li, .furnace-feed-card, .furnace-loot-banner"
  );
  const last = targets.length ? targets[targets.length - 1] : null;
  if (!last || typeof last.scrollIntoView !== "function") return;
  try {
    last.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (_error) { /* ignore */ }
}

const REVIEW_BUCKET_LABELS = {
  counter_evidence_candidates: ["补充反证候选", "检查新来源是否足以反驳既有判断"],
  escalated_actions: ["处理升级动作", "处理已升级、需要人工确认的动作"],
  escalation_candidates: ["处理升级候选", "确认是否需要人工介入"],
  judgment_review_actions: ["复核研究判断", "处理需要重新判断的结论"],
  machine_memory_actions: ["修复机器记忆", "处理可审计的记忆修复动作"],
  overdue_actions: ["处理逾期动作", "确认是否继续执行或关闭"],
  overdue_reviews: ["处理逾期复审", "确认旧判断是否仍成立"],
  pending_decisions: ["处理待定决策", "确认待定判断与执行入口"],
  pending_judgments: ["复核待定判断", "推进仍在等待复核的判断"],
  ready_actions: ["确认待执行动作", "复核已经准备好的安全动作"],
};

function reviewBucketLabel(key) {
  const k = String(key || "");
  const entry = REVIEW_BUCKET_LABELS[k];
  if (entry) return { title: entry[0], hint: entry[1] };
  return { title: k, hint: "" };
}

function renderFurnaceActivityTimeline(plugin, parentEl) {
  if (!plugin.settings || !plugin.settings.showAdvancedCommands) {
    return;
  }
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  const feed = summary ? buildTodayFeed(summary) : [];
  const recentRuns = plugin.pluginState && Array.isArray(plugin.pluginState.recentRuns) ? plugin.pluginState.recentRuns : [];
  const items = [];
  const seenTargets = new Set();

  const addItem = (item) => {
    const kind = String(item.kind || "");
    const target = String(item.target || "");
    if (target && (kind === "elixir" || kind === "decision" || kind === "receipt" || kind === "review-backlog")) {
      if (seenTargets.has(target)) return;
      seenTargets.add(target);
    }
    const timestamp = String(item.timestamp || "");
    items.push({
      ...item,
      kind,
      title: String(item.title || ""),
      summary: String(item.summary || ""),
      target,
      timestamp,
      _epochMs: normalizeTs(timestamp),
    });
  };

  for (const entry of feed) {
    if (!entry || typeof entry !== "object") continue;
    addItem({
      kind: String(entry.kind || ""),
      title: String(entry.title || ""),
      summary: String(entry.summary || ""),
      timestamp: String(entry.timestamp || ""),
      target: String(entry.target || ""),
    });
  }

  for (const run of recentRuns) {
    if (!run || typeof run !== "object") continue;
    const timestamp = String(run.finishedAt || run.startedAt || "");
    const status = String(run.status || "");
    const protocol = String(run.protocol || "");
    addItem({
      kind: "plugin-run",
      title: String(run.label || run.command || "Plugin run"),
      summary: `${status} · ${protocol}`,
      timestamp,
    });
  }

  const receipts = summary && Array.isArray(summary.recent_receipts) ? summary.recent_receipts : [];
  for (const receipt of receipts) {
    if (!receipt || typeof receipt !== "object") continue;
    addItem({
      kind: "receipt",
      title: String(receipt.title || receipt.subject_id || receipt.action_id || "Receipt"),
      summary: String(receipt.operation || ""),
      timestamp: String(receipt.applied_at || receipt.generated_at || receipt.created_at || ""),
      target: String(receipt.receipt_path || receipt.path || ""),
    });
  }

  const backlog = summary && summary.review_backlog_counts && typeof summary.review_backlog_counts === "object"
    ? summary.review_backlog_counts
    : {};
  for (const [bucketKey, rawCount] of Object.entries(backlog)) {
    const count = Number(rawCount);
    if (!Number.isFinite(count) || count <= 0) continue;
    if (!isPrimaryReviewBacklogBucket(bucketKey)) continue;
    const target = `review:${bucketKey}`;
    const { title: bucketTitle, hint: bucketHint } = reviewBucketLabel(bucketKey);
    addItem({
      kind: "review-backlog",
      title: bucketTitle,
      summary: bucketHint ? `${count} 项待处理 · ${bucketHint}` : `${count} 项待处理`,
      timestamp: String(summary.generated_at || ""),
      target,
    });
  }

  items.sort((left, right) => right._epochMs - left._epochMs);
  const cappedItems = items.slice(0, 50);

  const section = parentEl.createDiv({ cls: "furnace-activity-timeline" });
  section.createEl("h3", { text: plugin.t("Furnace activity") });

  if (!cappedItems.length) {
    section.createDiv({ cls: "furnace-activity-timeline-empty", text: plugin.t("No recent furnace activity") });
    return;
  }

  const listEl = section.createEl("ul", { cls: "furnace-activity-list" });
  for (const item of cappedItems) {
    const li = listEl.createEl("li", { cls: `furnace-activity-item furnace-activity-item-${item.kind}` });
    li.createEl("span", { cls: "furnace-activity-kind", text: furnaceActivityKindLabel(plugin, item.kind) });
    li.createEl("span", { cls: "furnace-activity-title", text: item.title });
    li.createEl("span", { cls: "furnace-activity-summary", text: item.summary });
  }
}

function isPrimaryReviewBacklogBucket(bucketKey) {
  const key = String(bucketKey || "").trim();
  if (!key) return false;
  if (typeof PRIMARY_REVIEW_BUCKETS !== "undefined" && PRIMARY_REVIEW_BUCKETS && typeof PRIMARY_REVIEW_BUCKETS.has === "function") {
    return PRIMARY_REVIEW_BUCKETS.has(key);
  }
  return [
    "counter_evidence_candidates",
    "escalated_actions",
    "escalation_candidates",
    "judgment_review_actions",
    "pending_decisions",
    "pending_judgments",
  ].includes(key);
}

function furnaceActivityKindLabel(plugin, kind) {
  switch (kind) {
    case "plugin-run": return plugin.t("Plugin run");
    case "receipt": return plugin.t("Receipt");
    case "review-backlog": return plugin.t("Review backlog");
    case "report": return plugin.t("新报告");
    case "automation": return plugin.t("系统动态");
    case "decision":
    case "proposal": return plugin.t("需要你确认");
    case "elixir": return plugin.t("已完成");
    case "action": return plugin.t("下一步建议");
    default: return plugin.t(kind || "unknown");
  }
}

function normalizeTs(ts) {
  const parsed = Date.parse(ts);
  return Number.isFinite(parsed) ? parsed : 0;
}

// R88 #1: 空态 CTA — 聚焦上方 UniversalInput textarea
function renderTodayEmptyCta(plugin, parentEl, viewRoot) {
  const ctaRow = parentEl.createDiv({ cls: "furnace-today-feed-empty-cta" });
  const ctaBtn = ctaRow.createEl("button", {
    cls: "furnace-today-cta-submit mod-cta",
    text: plugin.t("投一份材料"),
  });
  ctaBtn.addEventListener("click", () => {
    // 优先在当前视图根内查找；不要跨 view 全局 fallback（避免误聚焦）
    const root = (viewRoot && viewRoot.closest && (viewRoot.closest(".furnace-shell-view") || viewRoot)) || viewRoot;
    const textarea = root && root.querySelector
      ? root.querySelector(".furnace-universal-input-textarea")
      : null;
    if (textarea) {
      textarea.focus();
      try { textarea.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
    }
  });
}

// R88 #2: 渲染"处理中"卡片（runtime-only pending submissions）
function todayReportPathsFromSummary(summary) {
  if (!summary || typeof summary !== "object") return new Set();
  const paths = new Set();
  for (const entry of buildTodayFeed(summary)) {
    if (entry.kind === "report") {
      const target = String(entry.target || "").trim();
      if (target) paths.add(target);
    }
  }
  return paths;
}

function shouldHidePendingDoneEntry(entry, todayReportPaths) {
  if (!entry || entry.status !== "done") return false;
  if (String(entry.reconcileTarget || "") !== "outputs") return false;
  const path = String(entry.reconcilePath || "").trim();
  return Boolean(path && todayReportPaths.has(path));
}

function renderPendingSubmissionsGroup(plugin, section) {
  const items = Array.isArray(plugin.pendingSubmissions) ? plugin.pendingSubmissions : [];
  if (!items.length) return;
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  const todayReportPaths = todayReportPathsFromSummary(summary);
  const groupEl = section.createDiv({ cls: "furnace-today-feed-group furnace-conversation-stream" });
  const renderNow = Date.now();
  for (const entry of items) {
    if (shouldHidePendingDoneEntry(entry, todayReportPaths)) continue;
    const streamItem = groupEl.createDiv({ cls: "furnace-conversation-item" });

    // User Bubble
    const userBubble = streamItem.createDiv({ cls: "furnace-conversation-bubble furnace-bubble-user" });
    userBubble.createDiv({ cls: "furnace-bubble-text", text: entry.displayText || entry.title || "" });
    if (entry.retryArgs && entry.retryArgs.kind === "files" && Array.isArray(entry.retryArgs.files) && entry.retryArgs.files.length > 0) {
      const attachments = userBubble.createDiv({ cls: "furnace-bubble-attachments" });
      for (const file of entry.retryArgs.files) {
        attachments.createSpan({ cls: "furnace-bubble-attachment-pill", text: file.name || file.path || "文件" });
      }
    }
    userBubble.createDiv({ cls: "furnace-bubble-time", text: formatDisplayTime(entry.startedAt, plugin.locale()) || "" });

    // AI Bubble
    const aiBubble = streamItem.createDiv({ cls: `furnace-conversation-bubble furnace-bubble-ai furnace-pending-${entry.status || "running"}` });

    const statusLabel = pendingSubmissionStageLabel(plugin, entry, renderNow);

    if (entry.status === "running") {
      const skeleton = aiBubble.createDiv({ cls: "furnace-bubble-shimmer" });
      skeleton.createDiv({ cls: "furnace-bubble-shimmer-line" });
      skeleton.createDiv({ cls: "furnace-bubble-shimmer-line short" });
    }

    aiBubble.createDiv({ cls: "furnace-bubble-status-text", text: statusLabel });

    if (entry.status === "failed") {
      const exceptionCard = aiBubble.createDiv({ cls: "furnace-inline-exception-card furnace-inline-exception-failed" });
      const failTitle = isPureMaterialPendingEntry(entry) ? plugin.t("投料失败") : plugin.t("生成被阻断");
      exceptionCard.createDiv({ cls: "furnace-inline-exception-title", text: failTitle });
      exceptionCard.createDiv({
        cls: "furnace-bubble-hint",
        text: plugin.t("这次没成功。可以点重试，或检查输入是否完整。"),
      });
      const errEl = exceptionCard.createDiv({ cls: "furnace-bubble-error", text: entry.error || plugin.t("失败") });
      errEl.setAttr && errEl.setAttr("title", entry.error || "");
      const actions = aiBubble.createDiv({ cls: "furnace-bubble-actions" });
      const retryBtn = actions.createEl("button", { cls: "mod-cta", text: plugin.t("重试") });
      retryBtn.addEventListener("click", async () => {
        const args = entry.retryArgs || {};
        plugin.resetPendingSubmissionForRetry(entry.id);
        try {
          let markAskDoneAfterRetry = false;
          let retryAskPayload = null;
          if (args.kind === "files" && Array.isArray(args.files)) {
            const flowResult = await plugin.runDroppedFilesWithAutoAsk({
              files: args.files,
              question: args.question || "",
              excludePendingId: entry.id,
            });
            const finalFormat = String(flowResult && flowResult.askFormat || args.format || "");
            plugin.updatePendingSubmissionRetryArgs(entry.id, {
              ...args,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : Array.isArray(args.materialPaths) ? args.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || args.askQuestion || ""),
              format: finalFormat,
              runNotesPath: String(flowResult && flowResult.runNotesPath || args.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || args.runId || ""),
            });
            if (!String(args.question || "").trim()) {
              plugin.completePendingMaterialDrop(entry.id, flowResult && flowResult.materialPaths);
            } else {
              markAskDoneAfterRetry = true;
              retryAskPayload = flowResult && flowResult.askPayload;
            }
          } else if (args.kind === "auto-ask") {
            markAskDoneAfterRetry = true;
            retryAskPayload = await plugin.runAskCommand({
              question: args.askQuestion || args.question || entry.displayText || "",
              format: args.format || "report",
              mode: "run-ask",
              protocol: args.protocol || "",
              excludePendingId: entry.id,
            });
          } else if (args.kind === "material-question") {
            const flowResult = await plugin.runDroppedPayloadsWithAutoAsk({
              payloads: [args.payload || ""],
              question: args.question || "",
              protocol: args.protocol || "",
              excludePendingId: entry.id,
            });
            const finalFormat = String(flowResult && flowResult.askFormat || args.format || "");
            plugin.updatePendingSubmissionRetryArgs(entry.id, {
              ...args,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : Array.isArray(args.materialPaths) ? args.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || args.askQuestion || ""),
              format: finalFormat,
              runNotesPath: String(flowResult && flowResult.runNotesPath || args.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || args.runId || ""),
            });
            markAskDoneAfterRetry = true;
            retryAskPayload = flowResult && flowResult.askPayload;
          } else {
            const retryText = String(args.payload || entry.displayText || "").trim();
            if (retryText && looksLikeUniversalMaterialPayload(retryText)) {
              const payload = await plugin.runUniversalInputCommand({ payload: retryText });
              const materialPaths = collectMaterialPathsFromPayload(payload);
              plugin.updatePendingSubmissionRetryArgs(entry.id, {
                ...args,
                kind: "material",
                payload: retryText,
                materialPaths,
                reused: Boolean(payload && payload.reused),
              });
              plugin.completePendingMaterialDrop(entry.id, materialPaths);
            } else {
              markAskDoneAfterRetry = true;
              retryAskPayload = await plugin.runAskCommand({
                question: retryText,
                format: args.format || inferAutoAskFormat(retryText, []),
                mode: "run-ask",
                protocol: args.protocol || "",
                excludePendingId: entry.id,
              });
            }
          }
          if (markAskDoneAfterRetry) finalizePendingAskSubmission(plugin, entry.id, retryAskPayload);
        } catch (e) {
          plugin.markPendingSubmissionFailed(entry.id, e);
        }
      });
      const dismissBtn = actions.createEl("button", { text: plugin.t("Dismiss") });
      dismissBtn.addEventListener("click", () => plugin.removePendingSubmission(entry.id));
    } else if (entry.status === "escalated") {
      const exceptionCard = aiBubble.createDiv({ cls: "furnace-inline-exception-card furnace-inline-exception-escalated" });
      exceptionCard.createDiv({ cls: "furnace-inline-exception-title", text: plugin.t("需要人工确认") });
      exceptionCard.createDiv({
        cls: "furnace-bubble-hint",
        text: entry.error || plugin.t("已进入 Exception Queue，需要人工确认后继续。"),
      });
      const actions = aiBubble.createDiv({ cls: "furnace-bubble-actions" });
      const openBtn = actions.createEl("button", { cls: "mod-cta furnace-pending-exception-btn", text: plugin.t("打开异常队列") });
      openBtn.addEventListener("click", async () => plugin.openReviewPageContextPicker());
      const dismissBtn = actions.createEl("button", { text: plugin.t("Dismiss") });
      dismissBtn.addEventListener("click", () => plugin.removePendingSubmission(entry.id));
    } else if (entry.status === "done" || entry.status === "degraded") {
      const target = String(entry.reconcileTarget || "");
      const reconcilePath = String(entry.reconcilePath || "");
      const resultCard = aiBubble.createDiv({ cls: "furnace-artifact-card furnace-bubble-result-card" });
      resultCard.createDiv({ cls: "furnace-artifact-eyebrow", text: pendingSubmissionArtifactKind(plugin, entry) });
      resultCard.createDiv({ cls: "furnace-bubble-result-title furnace-artifact-title", text: pendingSubmissionResultTitle(plugin, entry) });
      if (reconcilePath) {
        resultCard.createDiv({ cls: "furnace-bubble-result-path furnace-artifact-path", text: reconcilePath });
      }
      const snippet = resultCard.createDiv({ cls: "furnace-artifact-snippet", text: pendingSubmissionSnippetFallback(plugin, entry) });
      hydratePendingArtifactSnippet(plugin, snippet, entry);
      const meta = resultCard.createDiv({ cls: "furnace-artifact-meta" });
      meta.createSpan({ text: pendingSubmissionArtifactMeta(plugin, entry) });
      const materialPaths = normalizeMaterialPaths(entry.retryArgs && entry.retryArgs.materialPaths);
      if (materialPaths.length) {
        const materials = resultCard.createDiv({ cls: "furnace-bubble-materials" });
        for (const materialPath of materialPaths) {
          materials.createSpan({
            cls: "furnace-bubble-material-chip",
            text: formatMaterialChipLabel(materialPath),
            attr: { title: materialPath },
          });
        }
      }
      const actions = aiBubble.createDiv({ cls: "furnace-bubble-actions furnace-artifact-actions" });
      const degradedOutput = target === "outputs" && isPendingSubmissionDegradedEntry(entry);
      const openReceiptTarget = () => plugin.openPendingDoneTarget("receipts", reconcilePath);
      if (target === "outputs") {
        const openBtn = actions.createEl("button", { cls: "mod-cta furnace-pending-open-report-btn", text: degradedOutput ? plugin.t("打开产物") : plugin.t("打开报告") });
        openBtn.addEventListener("click", () => {
          plugin.openPendingDoneTarget("outputs", reconcilePath);
        });
        if (degradedOutput) {
          const retryBtn = actions.createEl("button", { cls: "furnace-pending-retry-report-btn", text: plugin.t("重试") });
          retryBtn.addEventListener("click", async () => {
            const args = entry.retryArgs || {};
            const question = pendingAskQuestionFromEntry(entry);
            const materialPaths = pendingAskMaterialPathsFromEntry(entry, plugin.settings);
            plugin.resetPendingSubmissionForRetry(entry.id);
            try {
              const retryPayload = await plugin.runAskCommand({
                question,
                format: args.format || "report",
                mode: "run-ask",
                protocol: args.protocol || "",
                excludePendingId: entry.id,
                materialPaths,
              });
              if (retryPayload && typeof plugin.updatePendingSubmissionRetryArgs === "function") {
                const usedPaths = coalesceAskUsedMaterialPaths(
                  retryPayload,
                  materialPaths,
                  plugin.settings,
                );
                plugin.updatePendingSubmissionRetryArgs(entry.id, Object.assign({}, args, {
                  question,
                  askQuestion: question,
                  materialPaths: usedPaths,
                  runId: retryPayload.run_id || retryPayload.runId || "",
                  runNotesPath: retryPayload.run_notes_path || retryPayload.runNotesPath || "",
                }));
              }
              finalizePendingAskSubmission(plugin, entry.id, retryPayload);
            } catch (e) {
              plugin.markPendingSubmissionFailed(entry.id, e);
            }
          });
        } else {
          const quoteBtn = actions.createEl("button", { cls: "furnace-pending-quote-report-btn", text: plugin.t("引用此报告追问") });
          quoteBtn.addEventListener("click", () => {
            if (typeof plugin.quoteFileToComposer === "function") {
              plugin.quoteFileToComposer(reconcilePath);
            }
          });
          const regenerateBtn = actions.createEl("button", { cls: "furnace-pending-regenerate-btn", text: plugin.t("Regenerate") });
          regenerateBtn.addEventListener("click", async () => {
            const args = entry.retryArgs || {};
            const question = pendingAskQuestionFromEntry(entry);
            const materialPaths = pendingAskMaterialPathsFromEntry(entry, plugin.settings);
            plugin.resetPendingSubmissionForRetry(entry.id);
            try {
              const retryPayload = await plugin.runAskCommand({
                question,
                format: args.format || "report",
                mode: "run-ask",
                protocol: args.protocol || "",
                excludePendingId: entry.id,
                materialPaths,
              });
              if (retryPayload && typeof plugin.updatePendingSubmissionRetryArgs === "function") {
                const usedPaths = coalesceAskUsedMaterialPaths(
                  retryPayload,
                  materialPaths,
                  plugin.settings,
                );
                plugin.updatePendingSubmissionRetryArgs(entry.id, Object.assign({}, args, {
                  question,
                  askQuestion: question,
                  materialPaths: usedPaths,
                  runId: retryPayload.run_id || retryPayload.runId || "",
                  runNotesPath: retryPayload.run_notes_path || retryPayload.runNotesPath || "",
                }));
              }
              finalizePendingAskSubmission(plugin, entry.id, retryPayload);
            } catch (e) {
              plugin.markPendingSubmissionFailed(entry.id, e);
            }
          });
          const editBtn = actions.createEl("button", { cls: "furnace-pending-edit-ask-btn", text: plugin.t("Edit question") });
          editBtn.addEventListener("click", () => {
            if (typeof plugin.prefillComposer === "function") {
              plugin.prefillComposer({
                question: pendingAskQuestionFromEntry(entry),
                materialPaths: pendingAskMaterialPathsFromEntry(entry, plugin.settings),
              });
            }
          });
        }
      } else if (target === "receipts") {
        const openBtn = actions.createEl("button", { cls: "mod-cta furnace-pending-open-receipt-btn", text: plugin.t("查看回执") });
        openBtn.addEventListener("click", openReceiptTarget);
      }
      const doneBtn = actions.createEl("button", { cls: "furnace-pending-done-btn", text: plugin.t("完成") });
      doneBtn.addEventListener("click", () => plugin.removePendingSubmission(entry.id));
    }
  }
}

function hydratePendingArtifactSnippet(plugin, snippetEl, entry) {
  const path = String(entry && entry.reconcilePath || "").trim();
  if (!path || !plugin || typeof plugin.readWorkspaceSnippet !== "function") return;
  plugin.readWorkspaceSnippet(path, 360).then((snippet) => {
    const text = String(snippet || "").trim();
    if (text) snippetEl.setText(text);
  }).catch(() => {});
}

function pendingSubmissionSnippetFallback(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (isPendingSubmissionDegradedEntry(entry)) return plugin.t("LLM 未完成；这是失败说明（非最终答案），可打开查看后重试。");
  if (target === "outputs") return plugin.t("报告已写入本地文件；摘要加载中…");
  if (target === "receipts") return plugin.t("回执已写入控制层，可用于审计与回滚追踪。");
  if (target === "raw") {
    if (entry && entry.retryArgs && entry.retryArgs.reused) {
      return plugin.t("已存在，未重复入库");
    }
    return plugin.t("原料已进入 raw/，等待后续编译沉淀。");
  }
  return plugin.t("任务已完成，结果已关联到本地工作区。");
}

function pendingSubmissionArtifactKind(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (isPendingSubmissionDegradedEntry(entry)) return plugin.t("失败说明 Artifact");
  if (target === "outputs") return plugin.t("本地报告 Artifact");
  if (target === "receipts") return plugin.t("执行回执 Receipt");
  if (target === "raw") return plugin.t("原料 Raw Input");
  return plugin.t("炼丹炉 Artifact");
}

function pendingSubmissionArtifactMeta(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (isPendingSubmissionDegradedEntry(entry)) return plugin.t("LLM 未完成；不是最终报告，可打开、查看进度或重试");
  if (target === "outputs") return plugin.t("文件是事实源，可打开继续阅读");
  if (target === "receipts") return plugin.t("保留 provenance / audit 线索");
  if (target === "raw") return plugin.t("后续 compile 会沉淀到 wiki/output");
  return plugin.t("本地可审计交付物");
}

function pendingSubmissionStageLabel(plugin, entry, now = Date.now()) {
  const status = String(entry && entry.status || "running");
  const pureMaterial = isPureMaterialPendingEntry(entry);
  if (status === "degraded") return plugin.t("LLM 未完成，已保留失败说明");
  if (status === "done") {
    if (isPendingSubmissionDegradedEntry(entry)) return plugin.t("LLM 未完成，已保留失败说明");
    if (entry && entry.reconcileTarget === "receipts") return plugin.t("已记录回执");
    if (entry && entry.reconcileTarget === "raw") return plugin.t("已收料");
    return plugin.t("报告已生成");
  }
  if (status === "running") {
    if (pureMaterial) return plugin.t("正在收料");
    return plugin.t("正在生成");
  }
  if (status === "failed") return plugin.t("失败");
  if (status === "escalated") return plugin.t("需要人工确认");
  if (pureMaterial) return plugin.t("正在收料");
  return plugin.t("正在整理材料与上下文");
}

function pendingSubmissionResultTitle(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (isPendingSubmissionDegradedEntry(entry)) return plugin.t("失败说明已就绪");
  if (target === "outputs") return plugin.t("报告卡片已就绪");
  if (target === "receipts") return plugin.t("回执已就绪");
  if (target === "raw") return plugin.t("原料已入库");
  return plugin.t("任务已完成");
}

function findPendingAskForReportPath(plugin, reportPath) {
  const path = String(reportPath || "").trim();
  if (!path) return null;
  const items = Array.isArray(plugin && plugin.pendingSubmissions) ? plugin.pendingSubmissions : [];
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const entry = items[i];
    if (!entry) continue;
    if (String(entry.reconcilePath || "").trim() !== path) continue;
    if (String(entry.reconcileTarget || "") !== "outputs") continue;
    if (isPendingSubmissionDegradedEntry(entry)) continue;
    if (!pendingAskQuestionFromEntry(entry)) continue;
    return entry;
  }
  return null;
}

async function regeneratePendingAskFromEntry(plugin, entry) {
  const args = (entry && entry.retryArgs) || {};
  const question = pendingAskQuestionFromEntry(entry);
  const materialPaths = pendingAskMaterialPathsFromEntry(entry, plugin.settings);
  plugin.resetPendingSubmissionForRetry(entry.id);
  try {
    const retryPayload = await plugin.runAskCommand({
      question,
      format: args.format || "report",
      mode: "run-ask",
      protocol: args.protocol || "",
      excludePendingId: entry.id,
      materialPaths,
    });
    if (retryPayload && typeof plugin.updatePendingSubmissionRetryArgs === "function") {
      const usedPaths = coalesceAskUsedMaterialPaths(
        retryPayload,
        materialPaths,
        plugin.settings,
      );
      plugin.updatePendingSubmissionRetryArgs(entry.id, Object.assign({}, args, {
        question,
        askQuestion: question,
        materialPaths: usedPaths,
        runId: retryPayload.run_id || retryPayload.runId || "",
        runNotesPath: retryPayload.run_notes_path || retryPayload.runNotesPath || "",
      }));
    }
    finalizePendingAskSubmission(plugin, entry.id, retryPayload);
  } catch (e) {
    plugin.markPendingSubmissionFailed(entry.id, e);
  }
}

async function readReportQueryForAsk(plugin, reportPath) {
  const path = String(reportPath || "").trim();
  if (!path || !plugin || !plugin.app || !plugin.app.vault) return "";
  try {
    const abstract = plugin.app.vault.getAbstractFileByPath(path);
    if (!abstract) return "";
    const text = await plugin.app.vault.read(abstract);
    const match = String(text || "").match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!match) return "";
    const queryLine = match[1].match(/^query:\s*(.+)$/m);
    if (!queryLine) return "";
    return String(queryLine[1] || "").trim().replace(/^["']|["']$/g, "");
  } catch (_error) {
    return "";
  }
}

async function regenerateAskForReportPath(plugin, reportPath, fallbackQuestion) {
  const pending = findPendingAskForReportPath(plugin, reportPath);
  if (pending) {
    await regeneratePendingAskFromEntry(plugin, pending);
    return;
  }
  let question = String(fallbackQuestion || "").trim();
  const fromReport = await readReportQueryForAsk(plugin, reportPath);
  if (fromReport) question = fromReport;
  if (!question) {
    new Notice(plugin.t("找不到可再生成的问题（报告无 query，且无会话记录）"));
    return;
  }
  if (typeof plugin.hasActiveAskPending === "function" && plugin.hasActiveAskPending()) {
    new Notice(plugin.t("已有进行中的提问，请等待完成后再试。"));
    return;
  }
  const materialPaths = stickyMaterialDisplayPaths(plugin.settings);
  const pendingId = plugin.pushPendingSubmission(question, {
    title: question,
    retryArgs: {
      kind: "auto-ask",
      question,
      askQuestion: question,
      format: "report",
      materialPaths,
    },
  });
  try {
    const retryPayload = await plugin.runAskCommand({
      question,
      format: "report",
      mode: "run-ask",
      excludePendingId: pendingId,
      materialPaths,
    });
    if (retryPayload && typeof plugin.updatePendingSubmissionRetryArgs === "function") {
      const usedPaths = coalesceAskUsedMaterialPaths(
        retryPayload,
        materialPaths,
        plugin.settings,
      );
      plugin.updatePendingSubmissionRetryArgs(pendingId, {
        kind: "auto-ask",
        question,
        askQuestion: question,
        format: "report",
        materialPaths: usedPaths,
        runId: retryPayload.run_id || retryPayload.runId || "",
        runNotesPath: retryPayload.run_notes_path || retryPayload.runNotesPath || "",
      });
    }
    finalizePendingAskSubmission(plugin, pendingId, retryPayload);
  } catch (e) {
    plugin.markPendingSubmissionFailed(pendingId, e);
  }
}

async function editAskForReportPath(plugin, reportPath, fallbackQuestion) {
  const pending = findPendingAskForReportPath(plugin, reportPath);
  if (pending && typeof plugin.prefillComposer === "function") {
    plugin.prefillComposer({
      question: pendingAskQuestionFromEntry(pending),
      materialPaths: pendingAskMaterialPathsFromEntry(pending, plugin.settings),
    });
    return;
  }
  let question = String(fallbackQuestion || "").trim();
  const fromReport = await readReportQueryForAsk(plugin, reportPath);
  if (fromReport) question = fromReport;
  if (!question) {
    new Notice(plugin.t("找不到可编辑的问题（报告无 query，且无会话记录）"));
    return;
  }
  if (typeof plugin.prefillComposer === "function") {
    plugin.prefillComposer({
      question,
      materialPaths: stickyMaterialDisplayPaths(plugin.settings),
    });
  }
}

function attachReportCardAskActions(plugin, cardEl, feedEntry) {
  const target = String(feedEntry && feedEntry.target || "").trim();
  if (!target || !cardEl) return;
  let actions = cardEl.querySelector
    ? cardEl.querySelector(".furnace-feed-card-actions")
    : null;
  if (!actions) {
    actions = cardEl.createDiv({ cls: "furnace-feed-card-actions" });
  }
  const quoteBtn = actions.createEl("button", {
    cls: "furnace-report-quote-btn",
    text: plugin.t("引用此报告追问"),
  });
  quoteBtn.addEventListener("click", () => {
    if (typeof plugin.quoteFileToComposer === "function") {
      plugin.quoteFileToComposer(target);
    }
  });
  const fallbackQuestion = String(feedEntry && feedEntry.title || "").trim();
  const regenerateBtn = actions.createEl("button", {
    cls: "furnace-report-regenerate-btn furnace-pending-regenerate-btn",
    text: plugin.t("Regenerate"),
  });
  regenerateBtn.addEventListener("click", () => {
    void regenerateAskForReportPath(plugin, target, fallbackQuestion);
  });
  const editBtn = actions.createEl("button", {
    cls: "furnace-report-edit-ask-btn furnace-pending-edit-ask-btn",
    text: plugin.t("Edit question"),
  });
  editBtn.addEventListener("click", () => {
    void editAskForReportPath(plugin, target, fallbackQuestion);
  });
}

function renderTodayFeedItem(plugin, listEl, entry) {
  const li = listEl.createEl("li", { cls: "furnace-today-feed-item" });
  const { card } = renderFeedCard(plugin, li, entry);

  if (entry.kind === "report") {
    renderReportCard(plugin, card, entry);
    attachReportCardAskActions(plugin, card, entry);
  } else if (entry.kind === "action" && (entry.compound_suggest || entry.compoundSuggest)) {
    renderCompoundSuggestActionCard(plugin, card, entry);
  } else if (entry.kind === "decision" || entry.kind === "proposal") {
    renderConfirmationCard(plugin, card, entry);
  } else if (entry.kind === "automation") {
    renderAutomationCard(plugin, card, entry);
  }

  // Fallback action buttons (for entries not handled by card renderers)
  if (
    entry.kind !== "report"
    && entry.kind !== "action"
    && entry.kind !== "decision"
    && entry.kind !== "proposal"
    && entry.kind !== "automation"
  ) {
    const targetLabel = todayFeedTargetLabel(plugin, entry);
    if (targetLabel && card.querySelector) {
      const meta = card.createDiv({ cls: "furnace-today-feed-target" });
      meta.setText(targetLabel);
    }
  }
}

function todayFeedTargetLabel(plugin, entry) {
  const target = String(entry && entry.target || "").trim();
  if (!target) {
    return "";
  }
  if (isReviewTarget(target)) {
    return reviewBucketDisplayLabel(plugin, target);
  }
  if (isWorkspaceTarget(target)) {
    return workspaceTargetDisplayLabel(plugin, target, entry);
  }
  if (entry.kind === "action" || looksLikeCommandTarget(target)) {
    if (target.startsWith("metric:")) {
      return plugin.t("指标提醒");
    }
    switch (entry.kind) {
      case "report": return plugin.t("新报告");
      case "automation": return plugin.t("自动维护");
      case "elixir": return plugin.t("金丹完成");
      default: return plugin.t("待确认操作");
    }
  }
  return target;
}

function reviewBucketDisplayLabel(plugin, target) {
  var kind = String(target || "").replace(/^review:/, "").trim();
  switch (kind) {
    case "counter_evidence_candidates": return plugin.t("新反证待审");
    case "judgment_review_actions": return plugin.t("判断需要复核");
    case "machine_memory_actions": return plugin.t("机器记忆待修复");
    case "pending_judgments": return plugin.t("待定判断");
    case "pending_decisions": return plugin.t("待定决策");
    case "ready_actions": return plugin.t("安全动作待确认");
    case "escalated_actions": return plugin.t("升级动作");
    case "escalation_candidates": return plugin.t("升级候选");
    case "overdue_actions": return plugin.t("逾期动作");
    case "overdue_reviews": return plugin.t("逾期复审");
    case "drift": return plugin.t("数据漂移");
    default: return plugin.t("待审队列");
  }
}

function workspaceTargetActionLabel(target, entry) {
  const text = String(target || "").trim();
  if (entry && entry.kind === "proposal") {
    return "Open proposal";
  }
  if (text.startsWith("output/reports/")) {
    return "Open report";
  }
  if (text.startsWith("wiki/decisions/")) {
    return "Open decision";
  }
  if (text.startsWith("wiki/judgments/")) {
    return "Open judgment";
  }
  return "Open page";
}

function workspaceTargetDisplayLabel(plugin, target, entry) {
  const text = String(target || "").trim();
  if (entry && entry.kind === "proposal") {
    return plugin.t("Proposal page");
  }
  if (text.startsWith("output/reports/")) {
    return plugin.t("Report");
  }
  if (text.startsWith("wiki/decisions/")) {
    return plugin.t("Decision page");
  }
  if (text.startsWith("wiki/judgments/")) {
    return plugin.t("Judgment page");
  }
  if (text.startsWith("wiki/rewrite-proposals/") || text.startsWith(".aiwiki/staging/proposals/") || text.startsWith("output/_proposals/")) {
    return plugin.t("Proposal page");
  }
  if (text.startsWith("output/graph/") || text.startsWith("wiki/indexes/graph")) {
    return plugin.t("Graph page");
  }
  if (text.startsWith("output/review/") || text.startsWith("wiki/indexes/review")) {
    return plugin.t("Review surface");
  }
  return plugin.t("Workspace page");
}

function isReviewTarget(target) {
  return String(target || "").startsWith("review:");
}

function isWorkspaceTarget(target) {
  const text = String(target || "").trim();
  if (!text || text.includes("\n")) {
    return false;
  }
  if (/^(?:raw|wiki|output|schema|docs|\.aiwiki)\//.test(text)) {
    return true;
  }
  return /\.(?:md|json|html|pdf|png|jpg|jpeg|webp|svg)$/i.test(text);
}

function looksLikeCommandTarget(target) {
  const text = String(target || "").trim();
  if (!text) {
    return false;
  }
  return /^(?:aiwiki|python3?|PYTHONPATH=|drop-|run-|ask\b|compile\b|nightly\b|review-|apply-|revert-|file-back\b|metrics\b|today\b)/.test(text);
}
