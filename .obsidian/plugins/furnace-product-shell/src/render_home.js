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

  // 1. Universal Input
  renderUniversalInput(plugin, contentEl);

  // 2. Today Feed (统一 5 类)
  renderTodayFeed(plugin, contentEl);

  // 3. Advanced Drawer
  renderAdvancedDrawer(plugin, contentEl);
}
