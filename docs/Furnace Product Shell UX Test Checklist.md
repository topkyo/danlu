# Furnace Product Shell UX Test Checklist

*Obsidian Shell 插件单元 / 功能 / 产品体验验证清单*

Status: draft checklist  
Owner: tim  
Related:
- `docs/Furnace Product Shell.md`
- `docs/Furnace Agent Architecture.md`
- `.obsidian/plugins/furnace-product-shell/`
- `scripts/product_shell_smoke.sh`

## 0. 验证原则

Product Shell 的验证目标不是证明每个 DOM 节点存在，而是证明炼丹炉用户面持续符合：

- 一个输入端：用户可以直接投料或提问，不需要理解 protocol / backend / lane / phase。
- 一个输出端：结果自然出现在 Today，不需要翻 `raw/`、`wiki/`、`output/`。
- 提交有反馈：用户提交后立即看到 pending / received / done / failed 状态。
- 失败可恢复：失败时输入不丢，错误可读，可重试。
- 运维不抢戏：review / execution / repair / recent runs 等只在 Advanced / 更多工具里出现。
- UI 不拥有 runtime state：插件只消费 CLI 和 `shell-summary`，不绕过 runtime 写事实。

## 1. 快速 Gate

每次改 Product Shell 相关文件后，至少跑：

```bash
cd .obsidian/plugins/furnace-product-shell
npm test -- --runInBand
cd ../../..
bash scripts/verify.sh
```

涉及 launcher、LLM settings、Universal Input、pending reconcile、真实 vault 时，再跑：

```bash
bash scripts/product_shell_smoke.sh
```

涉及真实投料写路径时，再跑：

```bash
bash scripts/product_shell_smoke.sh --with-note-write
```

## 2. 单元测试 Checklist

目标：覆盖纯函数和状态转换，保持快速、稳定、无 Obsidian/Electron 依赖。

- [ ] `buildTodayFeed()` 按产品优先级排序：report > automation > decision/proposal > elixir > action。
- [ ] `buildTodayFeed()` 只展示当天报告，过滤非当天输出。
- [ ] `buildTodayFeed()` 将 review backlog 映射成用户可读中文标题。
- [ ] `buildTodayFeed()` 过滤不应进入首屏的维护命令。
- [ ] snooze 逻辑按 `target` 和日期过滤，过期后自动恢复。
- [ ] LLM settings 默认 provider / model 与 runtime 默认一致。
- [ ] LLM env 构造只注入当前 provider 需要的 secret / base URL。
- [ ] 切换 provider 时清理 stale env key，避免隐式 backend 漂移。
- [ ] repo state 能识别 vault root、launcher、plugin path 缺失。
- [ ] launcher path 支持绝对路径和相对路径。
- [ ] `extractPrimaryPath()` 覆盖 `path / output_path / receipt_path / state_path / index_path / report_path / note_path / stored_path / asset_path`。
- [ ] i18n dictionary 包含首屏所有中文/英文 key。

参考现有测试：
- `.obsidian/plugins/furnace-product-shell/src/__tests__/feed/today-feed.test.js`
- `.obsidian/plugins/furnace-product-shell/src/__tests__/feed/snooze.test.js`
- `.obsidian/plugins/furnace-product-shell/src/__tests__/state/llm-settings.test.js`
- `.obsidian/plugins/furnace-product-shell/src/__tests__/state/repo-state.test.js`

## 3. DOM / 交互测试 Checklist

目标：用 Jest + jsdom 覆盖用户真实操作，不依赖完整 Obsidian Electron。

### Universal Input

- [ ] 空输入且无附件时不触发提交。
- [ ] 文本输入后点击 Submit 会调用 `runUniversalInputCommand()`。
- [ ] `Ctrl+Enter` / `Cmd+Enter` 会触发提交。
- [ ] 提交中按钮 disabled，输入框 disabled，按钮文案变为“处理中…”。
- [ ] 提交成功后输入框清空，附件清空。
- [ ] 提交成功后创建 pending 卡，并进入 received 状态。
- [ ] 提交失败后输入内容保留，附件保留。
- [ ] 提交失败后 pending 标记为 failed，并显示可读错误。
- [ ] 粘贴文件会生成 attachment pill。
- [ ] 拖拽文件会生成 attachment pill。
- [ ] 点击 attachment remove 后附件从 UI 和内部 state 移除。
- [ ] 拖拽纯文本 / URL 时填入 textarea，不误当作文件。
- [ ] 多文件提交时逐个调用 runtime drop 入口，pending 文案可读。

### Today

- [ ] 无 `shellSummary` 时显示“数据还没就绪”与刷新/输入 CTA。
- [ ] 空 feed 且无 pending 时显示“今天还没有新报告”与投料 CTA。
- [ ] 有 pending 时不显示冷空态，优先展示 pending 卡。
- [ ] 点击“刷新炉子”调用 `refreshShellSummaryCommand()`。
- [ ] 刷新期间按钮 disabled，完成后恢复。
- [ ] Today 分组标题使用产品语言：新报告 / 系统动态 / 需要你确认 / 已完成 / 下一步建议。
- [ ] 长中文标题不会挤出卡片或按钮。
- [ ] `target` 存在时点击打开对应工作区路径。
- [ ] `target` 缺失时不抛异常，按钮不可用或隐藏。

### Advanced / 更多工具

- [ ] Advanced 不在首屏展开大量运维细节。
- [ ] 展开状态可持久化。
- [ ] 三组高级入口存在：治理/执行、运行与历史、系统/配置。
- [ ] 老入口没有删除，只是降级到 Advanced。
- [ ] dev/debug banner 不混入普通用户首屏。

参考现有测试：
- `.obsidian/plugins/furnace-product-shell/src/__tests__/render/*.test.js`
- `tests/test_product_shell_advanced_sections.py`
- `tests/test_product_shell_today_feed.py`

## 4. Runtime Contract Checklist

目标：锁住 Product Shell 与 `aiwiki` runtime 的边界，避免 UI 猜状态。

- [ ] `aiwiki shell-status` 输出插件需要的 `shell-summary` contract。
- [ ] `shell-summary` 包含 active protocol、today reports、review controls、recent receipts、recent raw inputs。
- [ ] `drop note` 返回可 reconcile 的路径字段。
- [ ] `drop url` 返回可 reconcile 的路径字段。
- [ ] `drop pdf` 返回可 reconcile 的路径字段。
- [ ] `drop image` 返回可 reconcile 的路径字段。
- [ ] `drop repo` 返回可 reconcile 的路径字段。
- [ ] `run-ask` 成功后报告路径能进入 Today。
- [ ] `run-ask` LLM 失败能以 `llm-failed` / degraded 状态清晰呈现；UI 不把 deterministic placeholder 当成功答案。
- [ ] `llm-check` configured / unconfigured 两种状态都有稳定 JSON shape。
- [ ] `recent_raw_inputs` 能让 raw 投料 pending 卡从 received 变 done。
- [ ] runtime 不要求插件直接写 `.aiwiki/state/*`。
- [ ] runtime contract 改动时同步更新 JS tests 和 Python tests。

参考现有测试：
- `tests/test_app_shell_summary.py`
- `tests/test_feed_parity.py`
- `tests/test_product_shell_universal_input.py`
- `tests/test_product_shell_pending_card.py`
- `tests/test_cli_universal_input.py`

## 5. 真实 Vault Smoke Checklist

目标：验证插件通过 launcher 接真实 vault 时没有路径、环境、backend、JSON shape 问题。

基础 smoke：

- [ ] `shell-status` 可执行并返回 JSON。
- [ ] `llm-check` 可执行并返回 configured / unconfigured 状态。
- [ ] deterministic `ask` 可执行并返回 report path。
- [ ] `run-ask` 可执行；若 backend 不可用，smoke 能降级验证 deterministic ask fallback。
- [ ] smoke 不污染异常路径。

写路径 smoke：

- [ ] `drop note` 写入 raw inbox。
- [ ] `drop note` 后 `shell-status` 能看到 recent raw input。
- [ ] Product Shell pending reconcile 可命中 raw path。

命令：

```bash
bash scripts/product_shell_smoke.sh
bash scripts/product_shell_smoke.sh --with-note-write
```

## 6. 人工 UX Checklist

目标：自动测试之后，用真实视觉和操作判断产品体验是否成立。

### 首屏

- [ ] 打开 vault 后第一眼能看到输入框和 Today。
- [ ] 首屏没有 System Status / LLM Health / Repair Backlog / Recent Runs 的大面积噪声。
- [ ] 普通用户不需要理解 `raw/wiki/schema/output` 分层。
- [ ] 空态文案自然，能引导用户投料或提问。
- [ ] “刷新炉子”位置清晰，但不喧宾夺主。

### 输入体验

- [ ] 输入 URL 后用户能理解已经提交。
- [ ] 输入问题后用户能理解报告稍后出现。
- [ ] 拖入 PDF / image 后用户能看到附件已挂上。
- [ ] 提交失败时输入没有丢失。
- [ ] 重试路径明显，不需要重新输入。

### 输出体验

- [ ] 新报告在 Today 顶部出现。
- [ ] 报告卡标题、协议、时间、打开动作清晰。
- [ ] 长标题、中文标题、路径型标题都不破版。
- [ ] 用户看到的是“报告 / 判断页 / 提案页 / 关系图谱”等产品标签，不是 runtime 路径优先。
- [ ] 没有报告时界面安静，不像系统故障。

### Advanced

- [ ] Advanced / 更多工具能找到 review、execution、repair、recent runs。
- [ ] Advanced 信息密度高但不影响首屏主任务。
- [ ] 操作者能排障，普通用户可以忽略。

### 主题 / 布局

- [ ] Obsidian light theme 可读。
- [ ] Obsidian dark theme 可读。
- [ ] 窄宽度窗口下按钮和标题不重叠。
- [ ] 长中文、英文长单词、路径字符串不撑破容器。
- [ ] 左右侧栏折叠/展开时主面板仍可用。

### 错误与降级

- [ ] launcher 缺失时错误可读。
- [ ] vault root 配错时错误可读。
- [ ] LLM backend 未配置时不阻塞 deterministic 能力。
- [ ] run-ask timeout 时状态能回到可操作。
- [ ] JSON contract 缺字段时 UI fail-soft，不白屏。

## 7. 推荐补强测试

优先补以下测试，收益最高：

- [ ] `renderUniversalInput` 成功提交后：pending received、输入清空、按钮恢复。
- [ ] `renderUniversalInput` 失败后：pending failed、输入保留、attachment 保留。
- [ ] 拖拽 URL 文本：textarea 填入 URL，不误当文件。
- [ ] Today 空态三分支：无 summary / 空 feed / 有 pending。
- [ ] `shell-summary` fixture → JS `buildTodayFeed()` → DOM 渲染，断言首屏只出现输入、Today、Advanced。
- [ ] `recent_raw_inputs` fixture → pending reconcile done。
- [ ] `llm-check` unconfigured fixture → UI 显示可操作降级，不阻塞 ask/drop。
- [ ] 长标题 fixture → DOM 中按钮和标题都存在且未被截断到空文本。

## 8. Definition Of Done

一次 Product Shell UX / 产品改造可以认为完成，需要同时满足：

- [ ] `npm test -- --runInBand` PASS。
- [ ] `bash scripts/verify.sh` PASS。
- [ ] 涉及 runtime/launcher 时，`bash scripts/product_shell_smoke.sh` PASS。
- [ ] 涉及投料写路径时，`bash scripts/product_shell_smoke.sh --with-note-write` PASS。
- [ ] 首屏仍符合“一个输入端 + 一个输出端”。
- [ ] Advanced 能找到原 operator 能力。
- [ ] 失败时输入不丢，错误可读。
- [ ] 没有新增 runtime SoT 字段，除非 contract 和 tests 同步更新。
- [ ] 没有让 UI 绕过 CLI / receipt / audit 边界。
