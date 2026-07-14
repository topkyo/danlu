// Structured command modal specs for Product Shell operator actions.

function buildReportSubgraphModalSpec(plugin, candidates) {
  const reportCandidates = Array.isArray(candidates) ? candidates : [];
  const fieldSpec = {
    key: "reportPath",
    label: plugin.t("Report path"),
    placeholder: "output/reports/...md",
    required: true,
  };
  if (reportCandidates.length) {
    fieldSpec.kind = "select";
    fieldSpec.options = reportCandidates;
    fieldSpec.initialValue = reportCandidates[0].value;
  }
  return {
    title: plugin.t("View report graph"),
    description: reportCandidates.length
      ? plugin.t("Choose a recent report.")
      : plugin.t("No recent reports available; enter a path manually."),
    fields: [fieldSpec],
    onSubmit: async (values) => {
      await plugin.runReportSubgraphCommand({ reportPath: values.reportPath });
    },
  };
}

function buildFileBackModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("File Back"),
    description: plugin.t("File an output artifact back into wiki/derived, wiki/decisions, or wiki/judgments."),
    fields: [
      {
        key: "artifact",
        label: plugin.t("Artifact path"),
        required: true,
        placeholder: plugin.t("output/reports/....md"),
        initialValue: () => prefill.artifact || plugin.getActiveOutputPath(),
      },
      {
        key: "title",
        label: plugin.t("Title"),
        placeholder: plugin.t("Optional filed-back title"),
        initialValue: prefill.title || "",
      },
      {
        key: "kind",
        label: plugin.t("Kind"),
        kind: "select",
        initialValue: prefill.kind || "derived",
        options: [
          ["derived", plugin.t("derived")],
          ["decision", plugin.t("decision")],
          ["judgment", plugin.t("judgment")],
        ],
      },
      {
        key: "protocol",
        label: plugin.t("Protocol"),
        kind: "select",
        initialValue: prefill.protocol || "",
        options: [["", plugin.t("current protocol")], ...plugin.getAvailableProtocols().map((item) => [item, item])],
      },
    ],
    onSubmit: async (values) => {
      const args = [values.artifact];
      appendOptionalArg(args, "--title", values.title);
      appendOptionalArg(args, "--kind", values.kind);
      appendOptionalArg(args, "--protocol", values.protocol);
      await plugin.runCliAction(`File Back: ${values.kind}`, "file-back", args);
    },
  };
}

function buildReviewPageModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Review Page"),
    description: plugin.t("Advance a decision or judgment page through the explicit review workflow."),
    fields: [
      {
        key: "page",
        label: plugin.t("Page path"),
        required: true,
        placeholder: plugin.t("wiki/decisions/... or wiki/judgments/..."),
        initialValue: () => prefill.pagePath || plugin.getActiveCuratedPagePath(),
      },
      {
        key: "status",
        label: plugin.t("Status"),
        required: true,
        placeholder: plugin.t("approved / confirmed / needs-revision ..."),
        initialValue: prefill.status || "",
      },
      {
        key: "note",
        label: plugin.t("Note"),
        kind: "textarea",
        placeholder: plugin.t("Optional review note"),
        rows: 4,
        initialValue: prefill.note || "",
      },
      {
        key: "confidence",
        label: plugin.t("Confidence"),
        placeholder: plugin.t("Optional confidence override"),
        initialValue: prefill.confidence || "",
      },
    ],
    onSubmit: async (values) => {
      const args = [values.page, "--status", values.status];
      appendOptionalArg(args, "--note", values.note);
      appendOptionalArg(args, "--confidence", values.confidence);
      await plugin.runCliAction(`Review Page: ${values.status}`, "review-page", args);
    },
  };
}

function buildReviewRewriteModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Review Rewrite"),
    description: plugin.t("Advance a concept rewrite proposal through the rewrite workflow."),
    fields: [
      { key: "slug", label: plugin.t("Concept slug"), required: true, initialValue: () => prefill.slug || plugin.getActiveConceptSlug() },
      { key: "status", label: plugin.t("Status"), required: true, placeholder: plugin.t("accepted / rejected / needs-revision ..."), initialValue: prefill.status || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional review note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.slug, "--status", values.status];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Review Rewrite: ${values.slug}`, "review-rewrite", args);
    },
  };
}

function buildApplyRewriteModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Apply Rewrite"),
    description: plugin.t("Apply an accepted concept rewrite proposal."),
    fields: [
      { key: "slug", label: plugin.t("Concept slug"), required: true, initialValue: () => prefill.slug || plugin.getActiveConceptSlug() },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional apply note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.slug];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Apply Rewrite: ${values.slug}`, "apply-rewrite", args);
    },
  };
}

function buildRetireConceptModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Retire Concept"),
    description: plugin.t("Apply an explicit retired override for a concept."),
    fields: [
      { key: "slug", label: plugin.t("Concept slug"), required: true, initialValue: () => prefill.slug || plugin.getActiveConceptSlug() },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Why retire this concept?"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.slug];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Retire Concept: ${values.slug}`, "retire-concept", args);
    },
  };
}

function buildReactivateConceptModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Reactivate Concept"),
    description: plugin.t("Clear the explicit retired override for a concept."),
    fields: [
      { key: "slug", label: plugin.t("Concept slug"), required: true, initialValue: () => prefill.slug || plugin.getActiveConceptSlug() },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional reactivate note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.slug];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Reactivate Concept: ${values.slug}`, "reactivate-concept", args);
    },
  };
}

function buildApplyArchiveModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Apply Archive"),
    description: plugin.t("Apply a ready archive candidate and pin it to archived."),
    fields: [
      { key: "entry_id", label: plugin.t("Entry id"), required: true, placeholder: plugin.t("manifest/material entry id"), initialValue: prefill.entryId || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional apply note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.entry_id];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Apply Archive: ${values.entry_id}`, "apply-archive", args);
    },
  };
}

function buildRevertArchiveModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Revert Archive"),
    description: plugin.t("Revert the latest explicit archive transition."),
    fields: [
      { key: "entry_id", label: plugin.t("Entry id"), required: true, placeholder: plugin.t("manifest/material entry id"), initialValue: prefill.entryId || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional revert note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.entry_id];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Revert Archive: ${values.entry_id}`, "revert-archive", args);
    },
  };
}

function buildReviewActionModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Review Action"),
    description: plugin.t("Advance a machine-memory repair action through the explicit action workflow."),
    fields: [
      { key: "action_id", label: plugin.t("Action id"), required: true, placeholder: plugin.t("machine-memory action id"), initialValue: prefill.actionId || "" },
      { key: "status", label: plugin.t("Status"), required: true, placeholder: plugin.t("accepted / rejected / ready ..."), initialValue: prefill.status || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional action review note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.action_id, "--status", values.status];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Review Action: ${values.action_id}`, "review-action", args);
    },
  };
}

function buildApplyActionModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Apply Action"),
    description: plugin.t("Apply an accepted low-risk machine-memory repair action."),
    fields: [
      { key: "action_id", label: plugin.t("Action id"), required: true, placeholder: plugin.t("machine-memory action id"), initialValue: prefill.actionId || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional apply note"), initialValue: prefill.note || "" },
      { key: "bundle", label: plugin.t("Bundle path"), placeholder: plugin.t("Optional execution bundle path"), initialValue: prefill.bundle || "" },
      { key: "dry_run", label: plugin.t("Dry run"), kind: "toggle", initialValue: Boolean(prefill.dryRun) },
    ],
    onSubmit: async (values) => {
      const args = [values.action_id];
      appendOptionalArg(args, "--note", values.note);
      appendOptionalArg(args, "--bundle", values.bundle);
      if (values.dry_run) {
        args.push("--dry-run");
      }
      await plugin.runCliAction(`Apply Action: ${values.action_id}`, "apply-action", args);
    },
  };
}

function buildRevertActionModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Revert Action"),
    description: plugin.t("Revert the latest low-risk safe apply for a machine-memory action."),
    fields: [
      { key: "action_id", label: plugin.t("Action id"), required: true, placeholder: plugin.t("machine-memory action id"), initialValue: prefill.actionId || "" },
      { key: "note", label: plugin.t("Note"), kind: "textarea", rows: 4, placeholder: plugin.t("Optional revert note"), initialValue: prefill.note || "" },
    ],
    onSubmit: async (values) => {
      const args = [values.action_id];
      appendOptionalArg(args, "--note", values.note);
      await plugin.runCliAction(`Revert Action: ${values.action_id}`, "revert-action", args);
    },
  };
}

function buildReviewPageBatchModalSpec(plugin, prefill = {}) {
  const pagePaths = Array.isArray(prefill.pagePaths) ? prefill.pagePaths : [];
  const statusOptions = Array.isArray(prefill.statusOptions) ? prefill.statusOptions : [];
  const normalizedStatusOptions = statusOptions.map((option) => ({
    value: option.value,
    label: option.label || plugin.transitionLabel("page", option.value),
  }));
  const statusField = normalizedStatusOptions.length
    ? {
        key: "status",
        label: plugin.t("Status"),
        required: true,
        kind: "select",
        initialValue: prefill.status || normalizedStatusOptions[0].value || "",
        options: normalizedStatusOptions,
      }
    : {
        key: "status",
        label: plugin.t("Status"),
        required: true,
        placeholder: plugin.t("tracking / needs-revisit / approved ..."),
        initialValue: prefill.status || "",
      };
  return {
    title: plugin.t("Batch Review Pages"),
    description: prefill.description || plugin.t("Advance multiple review pages that share a safe common transition."),
    submitLabel: plugin.t("Run batch"),
    fields: [
      {
        key: "pages",
        label: plugin.t("Page paths"),
        required: true,
        kind: "textarea",
        rows: 6,
        placeholder: plugin.t("wiki/judgments/... (one per line)"),
        initialValue: pagePaths.join("\n"),
      },
      statusField,
      {
        key: "note",
        label: plugin.t("Note"),
        kind: "textarea",
        rows: 4,
        placeholder: plugin.t("Optional shared batch note"),
        initialValue: prefill.note || "",
      },
      {
        key: "confidence",
        label: plugin.t("Confidence"),
        placeholder: plugin.t("Optional shared confidence override"),
        initialValue: prefill.confidence || "",
      },
    ],
    onSubmit: async (values) => {
      const paths = parseLineList(values.pages);
      if (!paths.length) {
        throw new Error(plugin.t("Batch review requires at least one page path."));
      }
      await plugin.runReviewPageBatchTransition(paths, values.status, values.note, values.confidence);
    },
  };
}
