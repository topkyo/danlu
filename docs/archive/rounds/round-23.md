# Round 23 — M-UX.2 Dogfood Vault Shell-first Migration

status: 完成
commit: 

Round 23 — M-UX.2 Dogfood Vault Shell-first Migration — 完成
- **目的**: 根据真机 Obsidian 截图确认 M-UX.1 尚未实际迁移 `/home/tim/danlu/炼丹炉`；继续把 dogfood vault 改为 Product Shell-first，并修正首屏 universal input 中文化缺口
- **截图结论**:
  - 主区仍是 `README`，Product Shell 在右侧宽栏
  - 左侧仍暴露 raw/output/schema 等 runtime 入口
  - universal input placeholder 与 Submit 仍是英文
- **设计核心**:
  - 插件 `ZH_TEXT` 增加 `Universal input`、`Universal Input`、`Universal input cannot be empty.`、`Drop URL, PDF, image, repo, note, or question...`、`Drop file here`、`Submit`、`Invalid input: {message}` 中文翻译
  - `render_input.js` 的 aria-label 和错误 Notice 走 `plugin.t()`；提交后的 recent run label 也不再漏英文
  - 重新 build `main.js`；dogfood vault 插件文件与 repo 插件文件为同一文件对象，因此中文化自动落到 dogfood vault
  - `/home/tim/danlu/炼丹炉/.obsidian/workspace.json` 改为主区 Product Shell，左侧文件列表+书签，右侧 Outline+Backlinks
  - `/home/tim/danlu/炼丹炉/HOME.md` 与 `README.md` 改成 research dogfood 的 Product Shell-first 说明
  - 修正 dogfood `scripts/aiwiki-launcher.sh` 旧自检路径，从 `src/aiwiki/cli.py` 改为 `src/aiwiki/cli/__main__.py`
- **验证**:
  - `node --check .obsidian/plugins/furnace-product-shell/main.js`
  - dogfood workspace JSON valid；结构检查显示 active=`main-furnace-center`，main=`furnace-product-shell-furnace-center` + markdown，left=`文件列表/书签`，right=`outline/backlink`
  - dogfood `scripts/aiwiki-launcher.sh shell-status` exit 0；active protocol=`research`
  - focused unittest: `tests.test_product_shell_today_feed tests.test_obsidian_workspace tests.test_vault` 17/17
  - `bash scripts/verify.sh` exit 0；1503 unit + 13 acceptance；coverage 92%
- **当前评估**: 真机 dogfood vault 已从右侧辅助面板切到主区 Product Shell；重启/重载 Obsidian 后应进入新的 shell-first 布局。下一步应做截图复核和按钮语义精修，而不是继续移动 runtime 层。
