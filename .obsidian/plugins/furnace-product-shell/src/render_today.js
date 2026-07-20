// Render today feed and report surfaces for Product Shell.

function renderTodayFeed(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;

  const section = container.createDiv({ cls: "furnace-today-feed" });
  // R90: Today 标题行 → 标题 + "刷新炉子"按钮 + last updated
  const headRow = section.createDiv({ cls: "furnace-today-feed-head" });
  headRow.createEl("h2", { text: plugin.t("Today"), cls: "furnace-today-feed-title" });
  const refreshWrap = headRow.createDiv({ cls: "furnace-today-feed-refresh" });
  const refreshBtn = refreshWrap.createEl("button", {
    cls: "furnace-today-refresh-btn",
    text: plugin.t("刷新炉子"),
  });
  refreshBtn.setAttr && refreshBtn.setAttr("aria-label", plugin.t("刷新炉子"));
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    try {
      await plugin.refreshShellSummaryCommand();
    } catch (e) { /* 已在 plugin 层 Notice */ }
    finally { refreshBtn.disabled = false; }
  });
  refreshWrap.createEl("span", {
    cls: "furnace-today-last-updated",
    text: plugin.getLastSummaryRefreshLabel(),
  });

  // R88: pending submissions（用户刚提交、流水线未落地的"处理中"卡片）
  // 始终在最前面渲染，独立于 shellSummary 状态，构成视觉闭环
  renderPendingSubmissionsGroup(plugin, section);

  renderFurnaceActivityTimeline(plugin, section);

  if (!summary) {
    section.createEl("div", {
      cls: "furnace-today-feed-empty",
      text: plugin.t("数据还没就绪。先点上方刷新，或等首次任务跑完。"),
    });
    // R88 #1 (P1 fix): summary 缺失也提供 CTA
    renderTodayEmptyCta(plugin, section, container);
    return;
  }

  const feed = buildTodayFeed(summary);

  if (!feed.length) {
    // 如果有 pending 卡片在上方，已经构成"投了在跑"的视觉反馈，不再渲染冷空态
    const hasPending = Array.isArray(plugin.pendingSubmissions) && plugin.pendingSubmissions.length > 0;
    if (hasPending) return;
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
    return;
  }
  
  const groups = { report: [], automation: [], decision: [], proposal: [], elixir: [], action: [] };
  for (const entry of feed) groups[entry.kind].push(entry);
  
  const groupSpecs = [
    ["report", plugin.t("新报告"), groups.report],
    ["compound", plugin.t("复利建议"), groups.action.filter((entry) => entry.compound_suggest || entry.compoundSuggest)],
  ];
  
  for (const [kind, heading, items] of groupSpecs) {
    if (!items.length) continue;
    const groupEl = section.createDiv({ cls: `furnace-today-feed-group furnace-today-feed-${kind}` });
    groupEl.createEl("h3", { text: heading });
    const listEl = groupEl.createEl("ul", { cls: "furnace-today-feed-list" });
    for (const entry of items) {
      renderTodayFeedItem(plugin, listEl, entry);
    }
  }
}

const REVIEW_BUCKET_LABELS = {
  counter_evidence_candidates: ["补充反证候选", "检查新来源是否足以反驳既有判断"],
  escalated_actions: ["处理升级动作", "处理已升级、需要人工确认的动作"],
  escalation_candidates: ["处理升级候选", "确认是否需要人工介入"],
  judgment_review_actions: ["复核研究判断", "处理需要重新判断的结论"],
  l3_proposals: ["处理 L3 提案", "确认采纳、拒绝或回滚提案"],
  l3_proposal_attention: ["处理 L3 提案", "确认采纳、拒绝或回滚提案"],
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

function activityTimelineTodayDateOf(summary) {
  return activityTimelineDatePart(String(summary.generated_at || ""));
}

function activityTimelineDatePart(value) {
  const text = String(value || "").trim();
  if (text.includes("T")) return text.split("T")[0];
  if (text.includes(" ")) return text.split(" ")[0];
  return text.substring(0, 10);
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
function renderPendingSubmissionsGroup(plugin, section) {
  const items = Array.isArray(plugin.pendingSubmissions) ? plugin.pendingSubmissions : [];
  if (!items.length) return;
  const groupEl = section.createDiv({ cls: "furnace-today-feed-group furnace-conversation-stream" });
  for (const entry of items) {
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

    const statusLabel = pendingSubmissionStageLabel(plugin, entry);

    if (entry.status === "running" || entry.status === "received") {
      const skeleton = aiBubble.createDiv({ cls: "furnace-bubble-shimmer" });
      skeleton.createDiv({ cls: "furnace-bubble-shimmer-line" });
      skeleton.createDiv({ cls: "furnace-bubble-shimmer-line short" });
    }

    aiBubble.createDiv({ cls: "furnace-bubble-status-text", text: statusLabel });
    renderPendingProgressSteps(plugin, aiBubble, entry);

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
          let markReceivedAfterRetry = true;
          if (args.kind === "files" && Array.isArray(args.files)) {
            const flowResult = await plugin.runDroppedFilesWithAutoAsk({
              files: args.files,
              question: args.question || "",
            });
            const finalFormat = String(flowResult && flowResult.askFormat || args.format || "");
            plugin.updatePendingSubmissionRetryArgs(entry.id, {
              ...args,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : Array.isArray(args.materialPaths) ? args.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || args.askQuestion || ""),
              format: finalFormat,
              longRunning: finalFormat === "report",
              runNotesPath: String(flowResult && flowResult.runNotesPath || args.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || args.runId || ""),
            });
            if (!String(args.question || "").trim()) {
              plugin.completePendingMaterialDrop(entry.id, flowResult && flowResult.materialPaths);
              markReceivedAfterRetry = false;
            }
          } else if (args.kind === "auto-ask") {
            await plugin.runAskCommand({
              question: args.askQuestion || args.question || entry.displayText || "",
              format: args.format || "report",
              mode: "run-ask",
              protocol: args.protocol || "",
            });
          } else if (args.kind === "material-question") {
            const flowResult = await plugin.runDroppedPayloadsWithAutoAsk({
              payloads: [args.payload || ""],
              question: args.question || "",
              protocol: args.protocol || "",
            });
            const finalFormat = String(flowResult && flowResult.askFormat || args.format || "");
            plugin.updatePendingSubmissionRetryArgs(entry.id, {
              ...args,
              materialPaths: Array.isArray(flowResult && flowResult.materialPaths) ? flowResult.materialPaths : Array.isArray(args.materialPaths) ? args.materialPaths : [],
              askQuestion: String(flowResult && flowResult.askQuestion || args.askQuestion || ""),
              format: finalFormat,
              longRunning: finalFormat === "report",
              runNotesPath: String(flowResult && flowResult.runNotesPath || args.runNotesPath || ""),
              runId: String(flowResult && flowResult.runId || args.runId || ""),
            });
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
              markReceivedAfterRetry = false;
            } else {
              await plugin.runAskCommand({
                question: retryText,
                format: args.format || inferAutoAskFormat(retryText, []),
                mode: "run-ask",
                protocol: args.protocol || "",
              });
            }
          }
          if (markReceivedAfterRetry) plugin.markPendingSubmissionReceived(entry.id);
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
    } else if (entry.status === "received" || entry.status === "running") {
      const actions = aiBubble.createDiv({ cls: "furnace-bubble-actions" });
      const refreshBtn = actions.createEl("button", { cls: "furnace-bubble-refresh-btn", text: plugin.t("刷新状态") });
      refreshBtn.addEventListener("click", async () => {
        refreshBtn.disabled = true;
        try { await plugin.refreshShellSummaryCommand(); } catch (e) {}
        finally { refreshBtn.disabled = false; }
      });
      if (entry.status === "received") {
         const dismissBtn = actions.createEl("button", { text: plugin.t("Dismiss") });
         dismissBtn.addEventListener("click", () => plugin.removePendingSubmission(entry.id));
      }
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
      const actions = aiBubble.createDiv({ cls: "furnace-bubble-actions furnace-artifact-actions" });
      const degradedOutput = target === "outputs" && pendingSubmissionIsDegraded(entry);
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
            plugin.resetPendingSubmissionForRetry(entry.id);
            try {
              const retryPayload = await plugin.runAskCommand({
                question: args.askQuestion || args.question || entry.displayText || "",
                format: args.format || "report",
                mode: "run-ask",
                protocol: args.protocol || "",
              });
              if (retryPayload && typeof plugin.updatePendingSubmissionRetryArgs === "function") {
                plugin.updatePendingSubmissionRetryArgs(entry.id, Object.assign({}, args, {
                  jobId: retryPayload.job_id || retryPayload.jobId || "",
                  runId: retryPayload.run_id || retryPayload.runId || "",
                  runNotesPath: retryPayload.run_notes_path || retryPayload.runNotesPath || "",
                  longRunning: true,
                }));
              }
              plugin.markPendingSubmissionReceived(entry.id);
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

function renderPendingProgressSteps(plugin, aiBubble, entry) {
  const status = String(entry && entry.status || "running");
  if (status !== "running" && status !== "received") return;
  const steps = pendingSubmissionProgressSteps(plugin, entry);
  if (!steps.length) return;
  const list = aiBubble.createDiv({ cls: "furnace-progress-steps" });
  steps.forEach((step, index) => {
    const item = list.createDiv({ cls: `furnace-progress-step ${index === steps.length - 1 ? "is-active" : "is-done"}` });
    item.createSpan({ cls: "furnace-progress-step-dot" });
    item.createSpan({ cls: "furnace-progress-step-label", text: step });
  });
}

function pendingSubmissionProgressSteps(plugin, entry) {
  if (entry && entry.retryArgs && entry.retryArgs.longRunning) {
    return [plugin.t("已接收长程报告任务"), plugin.t("LLM 正在生成结构化报告"), plugin.t("完成后会写入本地报告")];
  }
  if (isPureMaterialPendingEntry(entry)) {
    return [plugin.t("正在收料"), plugin.t("写入 raw/"), plugin.t("已收料")];
  }
  const startedMs = Date.parse(entry && entry.startedAt || "");
  const elapsed = Number.isFinite(startedMs) ? Math.max(0, Date.now() - startedMs) : 0;
  if (entry && entry.status === "received") {
    return [plugin.t("已接收请求"), plugin.t("等待产物写入"), plugin.t("刷新后关联报告")];
  }
  if (elapsed > 30 * 1000) {
    return [plugin.t("已接收请求"), plugin.t("交叉对比知识库"), plugin.t("整理报告结构")];
  }
  if (elapsed > 10 * 1000) {
    return [plugin.t("已接收请求"), plugin.t("提取材料与上下文"), plugin.t("交叉对比知识库")];
  }
  return [plugin.t("已接收请求"), plugin.t("提取材料与上下文")];
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
  if (pendingSubmissionIsDegraded(entry)) return plugin.t("LLM 未完成；这是保留 provenance 的本地恢复产物，可打开检查上下文后重试。");
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
  if (pendingSubmissionIsDegraded(entry)) return plugin.t("恢复产物 Artifact");
  if (target === "outputs") return plugin.t("本地报告 Artifact");
  if (target === "receipts") return plugin.t("执行回执 Receipt");
  if (target === "raw") return plugin.t("原料 Raw Input");
  return plugin.t("炼丹炉 Artifact");
}

function pendingSubmissionArtifactMeta(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (pendingSubmissionIsDegraded(entry)) return plugin.t("LLM 未完成；不是最终报告，可打开、查看进度或重试");
  if (target === "outputs") return plugin.t("文件是事实源，可打开继续阅读");
  if (target === "receipts") return plugin.t("保留 provenance / audit 线索");
  if (target === "raw") return plugin.t("后续 compile 会沉淀到 wiki/output");
  return plugin.t("本地可审计交付物");
}

function pendingSubmissionStageLabel(plugin, entry) {
  const status = String(entry && entry.status || "running");
  const pureMaterial = isPureMaterialPendingEntry(entry);
  if (status === "degraded") return plugin.t("LLM 未完成，已保留恢复产物");
  if (status === "done") {
    if (pendingSubmissionIsDegraded(entry)) return plugin.t("LLM 未完成，已保留恢复产物");
    if (entry && entry.reconcileTarget === "receipts") return plugin.t("已记录回执");
    if (entry && entry.reconcileTarget === "raw") return plugin.t("已收料");
    return plugin.t("报告已生成");
  }
  if (status === "received") {
    if (pureMaterial) {
      return entry && entry._stale ? plugin.t("可能已完成，刷新看看") : plugin.t("正在收料");
    }
    if (entry && entry.retryArgs && entry.retryArgs.longRunning) {
      return entry._stale ? plugin.t("长程报告可能已完成，刷新看看") : plugin.t("长程报告生成中，可稍后刷新");
    }
    return entry && entry._stale ? plugin.t("可能已完成，刷新看看") : plugin.t("已接收，正在排队生成报告");
  }
  if (status === "failed") return plugin.t("失败");
  if (status === "escalated") return plugin.t("需要人工确认");
  if (pureMaterial) return plugin.t("正在收料");
  return plugin.t("正在整理材料与上下文");
}

function pendingSubmissionResultTitle(plugin, entry) {
  const target = String(entry && entry.reconcileTarget || "");
  if (pendingSubmissionIsDegraded(entry)) return plugin.t("恢复产物已就绪");
  if (target === "outputs") return plugin.t("报告卡片已就绪");
  if (target === "receipts") return plugin.t("回执已就绪");
  if (target === "raw") return plugin.t("原料已入库");
  return plugin.t("任务已完成");
}

function pendingSubmissionIsDegraded(entry) {
  const status = String(entry && entry.status || "").trim();
  if (status === "degraded") return true;
  const deliveryMode = String(entry && entry.deliveryMode || entry && entry.delivery_mode || "").trim();
  const llmStatus = String(entry && entry.llmStatus || entry && entry.llm_status || "").trim();
  const backgroundStatus = String(entry && entry.backgroundStatus || entry && entry.background_status || "").trim();
  const artifactQuality = String(entry && entry.artifactQuality || entry && entry.artifact_quality || "").trim();
  return deliveryMode === "deterministic-fallback"
    || deliveryMode === "llm-failed"
    || llmStatus === "timeout_or_unavailable"
    || llmStatus === "validation_failed"
    || llmStatus === "failed"
    || llmStatus === "degraded"
    || backgroundStatus === "degraded"
    || artifactQuality === "degraded";
}

function renderTodayFeedItem(plugin, listEl, entry) {
  const li = listEl.createEl("li", { cls: "furnace-today-feed-item" });
  const { card } = renderFeedCard(plugin, li, entry);

  if (entry.kind === "report") {
    renderReportCard(plugin, card, entry);
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

function todayFeedActions(plugin, entry) {
  const target = String(entry && entry.target || "").trim();
  if (!target) {
    return [];
  }
  if (isReviewTarget(target)) {
    return [
      {
        label: "Review",
        description: `Review next item for: ${target}`,
        onClick: async () => plugin.openReviewPageContextPicker(),
      },
    ];
  }
  if (isWorkspaceTarget(target)) {
    return [
      {
        label: workspaceTargetActionLabel(target, entry),
        description: `Open today target: ${target}`,
        onClick: async () => plugin.openWorkspacePath(target),
      },
    ];
  }
  if (entry.kind === "action" || looksLikeCommandTarget(target)) {
    return [
      {
        label: "Copy command",
        description: `Copy today command: ${target}`,
        onClick: async () => plugin.copyText(target),
      },
    ];
  }
  return [
    {
      label: "Copy target",
      description: `Copy today target: ${target}`,
      onClick: async () => plugin.copyText(target),
    },
  ];
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
    case "l3_proposals": return plugin.t("L3 提案");
    case "l3_proposal_attention": return plugin.t("L3 提案需要关注");
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

function renderReportsPanel(plugin, container, reports) {
  const grouped = splitReportsByLocalDate(reports, { limitPreviousDays: 7 });
  const section = container.createDiv({ cls: "furnace-shell-reports-section" });

  const todaySection = section.createDiv({ cls: "furnace-shell-reports-group furnace-shell-reports-today" });
  todaySection.createEl("h3", { text: plugin.t("Today's Reports") });
  renderReportsGroup(plugin, todaySection, grouped.today, "(no reports today)");

  const previousSection = section.createDiv({ cls: "furnace-shell-reports-group furnace-shell-previous-reports" });
  previousSection.createEl("h3", { text: plugin.t("Previous Reports") });
  if (!grouped.previous.length) {
    previousSection.createDiv({ cls: "furnace-shell-empty", text: plugin.t("(no previous reports)") });
    return;
  }
  grouped.previous.forEach((group) => {
    const groupEl = previousSection.createDiv({ cls: "furnace-shell-date-group" });
    groupEl.createDiv({ cls: "furnace-shell-date-header", text: plugin.t(group.label) });
    renderReportsGroup(plugin, groupEl, group.items, "(no previous reports)");
  });
}

function renderReportsGroup(plugin, container, reports, emptyText) {
  const items = Array.isArray(reports) ? reports : [];
  if (!items.length) {
    container.createDiv({ cls: "furnace-shell-empty", text: plugin.t(emptyText) });
    return;
  }
  const list = container.createDiv({ cls: "furnace-shell-report-list" });
  items.forEach((report) => renderReportItem(plugin, list, report));
}

function renderReportItem(plugin, container, report) {
  const isUnread = isReportUnread(report, plugin.settings.lastViewedTimestamp);
  const titleText = report.title || report.path || plugin.t("output");
  const card = container.createDiv({ cls: "furnace-shell-report-card" });
  if (isUnread) {
    card.addClass("is-unread");
  }

  const openReport = async () => {
    if (!report.path) {
      return;
    }
    await plugin.openWorkspacePath(report.path);
    plugin.settings.lastViewedTimestamp = new Date().toISOString();
    await plugin.savePluginState();
    plugin.refreshOpenViews();
  };

  card.addEventListener("click", () => {
    plugin.runUiAction(() => openReport(), `Open output: ${report.path || titleText}`);
  });

  const content = card.createDiv({ cls: "furnace-shell-report-content" });
  content.createEl("span", { cls: "furnace-shell-report-dot", attr: { "aria-hidden": "true" } });
  const copy = content.createDiv({ cls: "furnace-shell-report-copy" });
  copy.createEl("span", { cls: "furnace-shell-report-title", text: titleText });
  copy.createDiv({
    cls: "furnace-shell-report-meta",
    text: `${plugin.t(report.protocol || "general")} · ${plugin.t(report.format || "markdown")} · ${formatDisplayTime(report.created_at, plugin.locale()) || report.created_at || plugin.t("unknown")}`,
  });

  const openBtn = card.createEl("button", { text: plugin.t("Open report") });
  openBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    plugin.runUiAction(() => openReport(), `Open output: ${report.path || titleText}`);
  });
}

function renderNeedsDecisionSection(plugin, container) {
  const summary = plugin.shellSummary && typeof plugin.shellSummary === "object" ? plugin.shellSummary : null;
  if (!summary) {
    return;
  }
  const suggested = Array.isArray(summary.suggested_next_actions) ? summary.suggested_next_actions : [];
  const drifts = Array.isArray(summary.drift_warnings) ? summary.drift_warnings : [];
  const rewrites = Array.isArray(summary.rewrite_followup_actions)
    ? summary.rewrite_followup_actions
    : Array.isArray(summary["rewrite_" + "recovery_actions"])
      ? summary["rewrite_" + "recovery_actions"]
      : [];
  const backlog = summary.review_backlog_counts && typeof summary.review_backlog_counts === "object" ? summary.review_backlog_counts : {};
  const backlogTotal = Object.values(backlog).reduce((acc, v) => acc + (Number.isFinite(Number(v)) ? Number(v) : 0), 0);

  if (!suggested.length && !drifts.length && !rewrites.length && backlogTotal <= 0) {
    return;
  }

  const section = container.createDiv({ cls: "furnace-shell-needs-section" });
  section.createEl("h3", { text: plugin.t("Needs your decision") });

  const maxItems = 5;
  if (suggested.length) {
    renderSuggestedNextActionsBlock(plugin, section, { maxItems: Math.min(suggested.length, maxItems) });
  }

  const renderItem = (item, kindLabel) => {
    const wrapper = section.createDiv({ cls: "furnace-shell-inline-list" });
    const row = wrapper.createDiv({ cls: "furnace-shell-inline-item" });
    const copy = row.createDiv({ cls: "furnace-shell-output-copy" });
    copy.createEl("strong", { text: item.title || item.path || item.message || plugin.t(kindLabel) });
    const metaParts = [plugin.t(kindLabel)];
    if (item.reason) {
      metaParts.push(plugin.t("reason {value}", { value: item.reason }));
    }
    if (item.path) {
      metaParts.push(item.path);
    }
    if (metaParts.length) {
      copy.createDiv({ cls: "furnace-shell-meta", text: metaParts.join(" | ") });
    }
    if (item.path) {
      const buttons = row.createDiv({ cls: "furnace-shell-inline-actions furnace-shell-inline-actions-compact" });
      const openButton = buttons.createEl("button", { text: plugin.t("Open") });
      openButton.addEventListener("click", () => {
        plugin.runUiAction(() => plugin.openWorkspacePath(item.path), `Open needs item: ${item.path}`);
      });
    }
  };

  let used = Math.min(suggested.length, maxItems);
  let truncated = Math.max(0, suggested.length - maxItems);
  for (const item of drifts) {
    if (used >= maxItems) {
      truncated += 1;
      continue;
    }
    renderItem(item, "drift warning");
    used += 1;
  }
  for (const item of rewrites) {
    if (used >= maxItems) {
      truncated += 1;
      continue;
    }
    renderItem(item, "rewrite recovery");
    used += 1;
  }

  if (backlogTotal > 0) {
    const backlogRow = section.createDiv({ cls: "furnace-shell-needs-backlog" });
    backlogRow.setText(plugin.t("Review backlog: {value} pending", { value: String(backlogTotal) }));
  }

  if (truncated > 0) {
    const more = section.createDiv({ cls: "furnace-shell-needs-more" });
    more.setText(plugin.t("+{value} more in Advanced", { value: String(truncated) }));
  }
}

function renderNextActionsPanel(plugin, container) {
  const panel = plugin.renderPanel(container, "Suggested Next Actions", "Keep the next safe action visible from the main surface.");
  if (!renderSuggestedNextActionsBlock(plugin, panel, { maxItems: 3 })) {
    panel.createDiv({ cls: "furnace-shell-empty", text: plugin.t("No suggested next action right now.") });
  }
}
