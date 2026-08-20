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
