// Pure control-option builders for review and execution center context pickers.

function controlIdSet(plugin, key) {
  const executionControls = plugin.shellSummary && typeof plugin.shellSummary === "object"
    ? plugin.shellSummary.execution_controls
    : null;
  const values = executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
  return new Set(values.map((item) => String(item || "").trim()).filter(Boolean));
}

function reviewControlList(plugin, key) {
  const reviewControls = plugin.shellSummary && typeof plugin.shellSummary === "object"
    ? plugin.shellSummary.review_controls
    : null;
  return reviewControls && Array.isArray(reviewControls[key]) ? reviewControls[key] : [];
}

function executionControlList(plugin, key) {
  const executionControls = plugin.shellSummary && typeof plugin.shellSummary === "object"
    ? plugin.shellSummary.execution_controls
    : null;
  return executionControls && Array.isArray(executionControls[key]) ? executionControls[key] : [];
}

function reviewPageControlItems(plugin) {
  const pages = reviewControlList(plugin, "pages");
  return uniqueContextOptions(
    pages.map((page) => {
      const kind = String(page.kind || "").trim() || "page";
      const status = String(page.status || "").trim() || "unknown";
      const metaText = truncateText(reviewObjectMetaText(page, plugin.locale()) || "review object", 180);
      return {
        value: page.path,
        label: page.title || page.path || "review-page",
        description: metaText || `${plugin.t(kind)} | ${displayCuratedStatus(status, plugin.locale())} | ${plugin.t("review object")}`,
        pageId: String(page.page_id || ""),
        pagePath: String(page.path || ""),
        pageKind: kind,
        currentStatus: status,
        confidence: String(page.confidence || ""),
        canRefreshReview: Boolean(page.can_refresh_review),
        allowedTransitions: Array.isArray(page.allowed_transitions) ? page.allowed_transitions : [],
        preferredTransitions: Array.isArray(page.preferred_transitions) ? page.preferred_transitions : [],
        defaultTransition: String(page.default_transition || ""),
      };
    }),
    "pagePath"
  );
}

function reviewKindLabel(plugin, kind, count = 1) {
  const normalized = String(kind || "").trim();
  if (normalized === "decision") {
    return count === 1 ? plugin.t("decision") : plugin.t("decisions");
  }
  if (normalized === "judgment") {
    return count === 1 ? plugin.t("judgment") : plugin.t("judgments");
  }
  return count === 1 ? plugin.t("page") : plugin.t("pages");
}

function transitionLabel(plugin, controlType, transition) {
  if (controlType === "page") {
    return displayCuratedStatus(transition, plugin.locale());
  }
  if (controlType === "rewrite") {
    return displayRewriteStatus(transition, plugin.locale());
  }
  if (controlType === "action") {
    return displayActionStatus(transition, plugin.locale());
  }
  if (controlType === "archive") {
    return transition === "revert" ? plugin.t("Revert archive") : plugin.t("Apply archive");
  }
  return plugin.t(String(transition || "transition"));
}

function transitionOptions(plugin, controlType, control) {
  if (!control || typeof control !== "object") {
    return [];
  }
  const allowed = Array.isArray(control.allowedTransitions || control.allowed_transitions)
    ? (control.allowedTransitions || control.allowed_transitions)
    : [];
  const preferredSet = new Set(
    (Array.isArray(control.preferredTransitions || control.preferred_transitions)
      ? (control.preferredTransitions || control.preferred_transitions)
      : []
    ).map((item) => String(item || "").trim()).filter(Boolean)
  );
  const defaultTransition = String(control.defaultTransition || control.default_transition || "").trim();
  return allowed
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .map((value) => ({
      value,
      label: transitionLabel(plugin, controlType, value),
      description: preferredSet.has(value) ? plugin.t("preferred transition") : plugin.t("allowed transition"),
      isDefault: value === defaultTransition,
      isPreferred: preferredSet.has(value),
    }))
    .sort((left, right) => {
      if (left.isDefault !== right.isDefault) {
        return left.isDefault ? -1 : 1;
      }
      if (left.isPreferred !== right.isPreferred) {
        return left.isPreferred ? -1 : 1;
      }
      return String(left.label || "").localeCompare(String(right.label || ""));
    });
}

function preferredTransitionOptions(plugin, controlType, control) {
  return transitionOptions(plugin, controlType, control).filter((option) => option.isPreferred).slice(0, 2);
}

function commonReviewTransitionOptions(plugin, pages) {
  const controls = Array.isArray(pages) ? pages.filter((page) => page && typeof page === "object") : [];
  if (!controls.length) {
    return [];
  }
  const stats = new Map();
  controls.forEach((page) => {
    const seen = new Set();
    transitionOptions(plugin, "page", page).forEach((option) => {
      if (seen.has(option.value)) {
        return;
      }
      seen.add(option.value);
      const current = stats.get(option.value) || {
        value: option.value,
        label: option.label,
        sharedCount: 0,
        preferredCount: 0,
        defaultCount: 0,
      };
      current.label = option.label;
      current.sharedCount += 1;
      if (option.isPreferred) {
        current.preferredCount += 1;
      }
      if (option.isDefault) {
        current.defaultCount += 1;
      }
      stats.set(option.value, current);
    });
  });
  return Array.from(stats.values())
    .filter((option) => option.sharedCount === controls.length)
    .sort((left, right) => {
      if (left.defaultCount !== right.defaultCount) {
        return right.defaultCount - left.defaultCount;
      }
      if (left.preferredCount !== right.preferredCount) {
        return right.preferredCount - left.preferredCount;
      }
      return String(left.label || "").localeCompare(String(right.label || ""));
    });
}

function reviewBatchSuggestions(plugin) {
  const groups = new Map();
  reviewPageControlItems(plugin).forEach((page) => {
    const prioritized = preferredTransitionOptions(plugin, "page", page);
    const selectedOptions = prioritized.length
      ? prioritized
      : transitionOptions(plugin, "page", page).filter((option) => option.isDefault).slice(0, 1);
    selectedOptions.forEach((transition) => {
      const kind = String(page.pageKind || "page").trim() || "page";
      const key = `${kind}::${transition.value}`;
      const current = groups.get(key) || {
        key,
        kind,
        status: transition.value,
        transitionLabel: transition.label,
        pages: [],
      };
      current.pages.push(page);
      groups.set(key, current);
    });
  });
  return Array.from(groups.values())
    .filter((group) => group.pages.length >= 2)
    .map((group) => {
      const count = group.pages.length;
      const kindLabel = reviewKindLabel(plugin, group.kind, count);
      return {
        key: group.key,
        kind: group.kind,
        status: group.status,
        label: `${group.transitionLabel} · ${count} ${kindLabel}`,
        description: `${count} ${kindLabel} ${plugin.t("share the recommended transition")} ${String(group.transitionLabel || "").toLowerCase()}.`,
        pagePaths: group.pages.map((page) => page.pagePath).filter(Boolean),
        pages: group.pages,
        statusOptions: commonReviewTransitionOptions(plugin, group.pages),
      };
    })
    .sort((left, right) => {
      if (right.pagePaths.length !== left.pagePaths.length) {
        return right.pagePaths.length - left.pagePaths.length;
      }
      return String(left.label || "").localeCompare(String(right.label || ""));
    });
}

function rewriteControlItems(plugin, mode = "review") {
  const proposals = reviewControlList(plugin, "rewrite_proposals");
  return uniqueContextOptions(
    proposals
      .filter((proposal) => (mode === "apply" ? Boolean(proposal.can_apply) : Boolean(proposal.can_review)))
      .map((proposal) => {
        const status = String(proposal.status || "").trim() || "unknown";
        const priority = String(proposal.priority || "").trim() || "medium";
        return {
          value: proposal.slug,
          label: proposal.title || proposal.slug || "rewrite-proposal",
          description: `${displayRewriteStatus(status, plugin.locale())} | ${plugin.t("priority")} ${priority} | ${plugin.t("score")} ${proposal.score || 0}`,
          slug: String(proposal.slug || ""),
          status,
          currentStatus: String(proposal.current_status || status),
          proposalPath: String(proposal.proposal_path || ""),
          targetPath: String(proposal.target_path || ""),
          canApply: Boolean(proposal.can_apply),
          canRefreshReview: Boolean(proposal.can_refresh_review),
          allowedTransitions: Array.isArray(proposal.allowed_transitions) ? proposal.allowed_transitions : [],
          preferredTransitions: Array.isArray(proposal.preferred_transitions) ? proposal.preferred_transitions : [],
          defaultTransition: String(proposal.default_transition || ""),
        };
      }),
    "slug"
  );
}

function actionControlItems(plugin, mode = "review") {
  return uniqueContextOptions(
    executionControlList(plugin, "actions")
      .filter((action) => {
        if (mode === "apply") {
          return Boolean(action.can_apply);
        }
        if (mode === "revert") {
          return Boolean(action.can_revert);
        }
        return Boolean(action.can_review);
      })
      .map((action) => {
        const status = String(action.status || "").trim() || "unknown";
        const priority = String(action.priority || "").trim() || "medium";
        const primaryPath = String(action.primary_path || "").trim();
        return {
          value: action.action_id,
          label: action.title || action.action_id || "action",
          description: `${displayActionStatus(status, plugin.locale())} | ${plugin.t("priority")} ${priority}${primaryPath ? ` | ${primaryPath}` : ""}`,
          actionId: String(action.action_id || ""),
          status,
          currentStatus: String(action.current_status || status),
          bundlePath: String(action.bundle_path || ""),
          canRefreshReview: Boolean(action.can_refresh_review),
          allowedTransitions: Array.isArray(action.allowed_transitions) ? action.allowed_transitions : [],
          preferredTransitions: Array.isArray(action.preferred_transitions) ? action.preferred_transitions : [],
          defaultTransition: String(action.default_transition || ""),
        };
      }),
    "actionId"
  );
}

function archiveControlItems(plugin, mode = "apply") {
  return uniqueContextOptions(
    executionControlList(plugin, "archives")
      .filter((entry) => (mode === "revert" ? Boolean(entry.can_revert) : Boolean(entry.can_apply)))
      .map((entry) => {
        const candidateStatus = String(entry.candidate_status || "").trim();
        const currentTemperature = String(entry.current_temperature || "").trim();
        return {
          value: entry.entry_id,
          label: entry.title || entry.entry_id || "archive-entry",
          description: `${plugin.t(candidateStatus || currentTemperature || "archive")} | ${entry.source_path || ""}`,
          entryId: String(entry.entry_id || ""),
          allowedTransitions: Array.isArray(entry.allowed_transitions) ? entry.allowed_transitions : [],
          preferredTransitions: Array.isArray(entry.preferred_transitions) ? entry.preferred_transitions : [],
          defaultTransition: String(entry.default_transition || ""),
        };
      }),
    "entryId"
  );
}

function actionControlsById(plugin) {
  const controls = executionControlList(plugin, "actions");
  return new Map(
    controls
      .filter((action) => action && typeof action === "object" && String(action.action_id || "").trim())
      .map((action) => [String(action.action_id || "").trim(), action])
  );
}

function archiveControlsById(plugin) {
  const controls = executionControlList(plugin, "archives");
  return new Map(
    controls
      .filter((entry) => entry && typeof entry === "object" && String(entry.entry_id || "").trim())
      .map((entry) => [String(entry.entry_id || "").trim(), entry])
  );
}

function manualReviewOption(plugin, controlType) {
  const labelMap = {
    page: plugin.t("Manual review..."),
    rewrite: plugin.t("Manual rewrite review..."),
    action: plugin.t("Manual action review..."),
  };
  return {
    value: "__manual__",
    label: labelMap[controlType] || plugin.t("Manual review..."),
    description: plugin.t("keep current status and capture note / confidence in the full form"),
    isManual: true,
    isPreferred: false,
    isDefault: false,
  };
}

function openTransitionPickerForControl(plugin, { title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice }) {
  const transitionOptions = plugin.transitionOptions(controlType, control);
  if (!transitionOptions.length && typeof onManual !== "function") {
    if (emptyNotice) {
      new Notice(emptyNotice);
    }
    if (typeof onFallback === "function") {
      onFallback();
    }
    return;
  }
  if (!transitionOptions.length && typeof onManual === "function") {
    onManual();
    return;
  }
  if (transitionOptions.length === 1 && typeof onManual !== "function") {
    onSubmit(transitionOptions[0].value);
    return;
  }
  const options = transitionOptions.slice();
  if (typeof onManual === "function") {
    options.push(plugin.manualReviewOption(controlType));
  }
  plugin.openContextPicker({
    title,
    description,
    submitLabel: plugin.t("Use"),
    options,
    onSubmit: (option) => {
      if (option && option.isManual && typeof onManual === "function") {
        onManual();
        return;
      }
      onSubmit(option.value);
    },
  });
}

function openContextAwareActionForSpec(plugin, spec) {
  const options = uniqueContextOptions(spec.options || [], spec.keyName || "value");
  if (!options.length) {
    new Notice(spec.emptyNotice || plugin.t("No context is currently available; fell back to the manual form."));
    spec.onFallback();
    return;
  }
  if (options.length === 1) {
    spec.onSubmit(options[0]);
    return;
  }
  plugin.openContextPicker({
    title: spec.title,
    description: spec.description,
    submitLabel: spec.submitLabel || "Use",
    options,
    onSubmit: spec.onSubmit,
  });
}
