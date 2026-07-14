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

  // 1. Today Feed / conversation stream
  renderTodayFeed(plugin, contentEl);

  // 2. Operator drawer stays out of the default product path.
  if (plugin.settings && plugin.settings.showAdvancedCommands) {
    renderAdvancedDrawer(plugin, contentEl);
  }

  // 3. Conversation Composer — keep it at the bottom of the shell surface.
  renderUniversalInput(plugin, contentEl);
}
