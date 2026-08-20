// Pure control-option builders for review page context pickers.

function transitionLabel(plugin, controlType, transition) {
  if (controlType === "page") {
    const thin = THIN_REVIEW_TRANSITION_LABELS[String(transition || "").trim()];
    if (thin) {
      return plugin.t(thin);
    }
    return displayCuratedStatus(transition, plugin.locale());
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

function manualReviewOption(plugin) {
  return {
    value: "__manual__",
    label: plugin.t("Manual review..."),
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
    options.push(plugin.manualReviewOption());
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
