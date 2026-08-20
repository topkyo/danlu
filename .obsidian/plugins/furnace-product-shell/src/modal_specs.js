// Structured command modal specs for Product Shell operator actions.

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
      await plugin.runCliAction(`Alchemy Start: ${values.corpus_id}`, "alchemy", ["start", ...args]);
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
