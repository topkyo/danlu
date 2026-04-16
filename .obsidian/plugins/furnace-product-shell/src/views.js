// ItemView subclasses for side panels.

class FurnaceCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_FURNACE_CENTER;
  }

  getDisplayText() {
    return this.plugin.t("Furnace");
  }

  getIcon() {
    return "flask-conical";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
    void this.plugin.refreshShellSummarySilently();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderFurnaceCenter(this.contentEl);
  }
}

class RecentRunsView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_RECENT_RUNS;
  }

  getDisplayText() {
    return this.plugin.t("Recent Runs");
  }

  getIcon() {
    return "history";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderRecentRuns(this.contentEl);
  }
}

class ReviewCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_REVIEW_CENTER;
  }

  getDisplayText() {
    return this.plugin.t("Review Center");
  }

  getIcon() {
    return "clipboard-check";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderReviewCenter(this.contentEl);
  }
}

class ExecutionCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE_EXECUTION_CENTER;
  }

  getDisplayText() {
    return this.plugin.t("Execution Center");
  }

  getIcon() {
    return "play-circle";
  }

  async onOpen() {
    this.plugin.registerOpenView(this);
    this.render();
  }

  async onClose() {
    this.plugin.unregisterOpenView(this);
  }

  render() {
    this.plugin.renderExecutionCenter(this.contentEl);
  }
}
