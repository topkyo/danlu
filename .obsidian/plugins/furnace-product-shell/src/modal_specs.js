// Structured command modal specs for Product Shell operator actions.

function noticeRemovedCommand(plugin, message) {
  new Notice(plugin.t(message));
}

function buildFileBackModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("File Back"),
    description: plugin.t("File an output artifact back into wiki/judgments for thin review."),
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
    ],
    onSubmit: async (values) => {
      const args = [values.artifact];
      appendOptionalArg(args, "--title", values.title);
      await plugin.runCliAction(plugin.t("File Back"), "file-back", args);
    },
  };
}

function buildAlchemyStartModalSpec(plugin, prefill = {}) {
  return {
    title: plugin.t("Alchemy Start"),
    description: plugin.t("Start a new elixir draft from a promoted corpus."),
    fields: [
      {
        key: "corpus_id",
        label: plugin.t("Corpus id"),
        required: true,
        placeholder: plugin.t("corpus-id"),
        initialValue: prefill.corpusId || prefill.corpus_id || "",
      },
      {
        key: "topic",
        label: plugin.t("Topic"),
        required: true,
        placeholder: plugin.t("Elixir topic"),
        initialValue: prefill.topic || "",
      },
      {
        key: "include_elixir",
        label: plugin.t("Include elixir"),
        placeholder: plugin.t("Optional settled elixir id"),
        initialValue: prefill.includeElixir || prefill.include_elixir || "",
      },
    ],
    onSubmit: async (values) => {
      const args = [values.corpus_id, "--topic", values.topic];
      appendOptionalArg(args, "--include-elixir", values.include_elixir);
      await plugin.runCliAction(`Alchemy Start: ${values.corpus_id}`, "alchemy-start", args);
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
        placeholder: plugin.t("confirmed / discarded / pending-review"),
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
      noticeRemovedCommand(
        plugin,
        "Concept rewrite commands were removed in W3; use review-page on the concept page instead."
      );
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
    onSubmit: async () => {
      noticeRemovedCommand(
        plugin,
        "Concept rewrite commands were removed in W3; use review-page on the concept page instead."
      );
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
    onSubmit: async () => {
      noticeRemovedCommand(
        plugin,
        "Concept retire/reactivate commands were removed in W3; use review-page instead."
      );
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
    onSubmit: async () => {
      noticeRemovedCommand(
        plugin,
        "Concept retire/reactivate commands were removed in W3; use review-page instead."
      );
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
    onSubmit: async () => {
      noticeRemovedCommand(
        plugin,
        "Archive commands were removed in W3; inspect manifest pages manually."
      );
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
    onSubmit: async () => {
      noticeRemovedCommand(
        plugin,
        "Archive commands were removed in W3; inspect manifest pages manually."
      );
    },
  };
}
