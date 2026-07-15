# Round 62 — Product Shell UI Polish (Phase 1~3)

status: 完成
commit: 

Round 62 — Product Shell UI Polish (Phase 1~3) — 完成
- **目的**: 按 harness 流程将 Product Shell 从 "UX skeleton" 打磨到用户产品级标准，分首屏体验收敛 / 视觉与交互精修 / 产品完整性收口三阶段执行
- **方向 SoT**: `.codex/contracts/active.md`（本轮物化）
- **Phase 1 — 首屏体验收敛**:
  - 首屏空态引导卡片：全新 vault 显示三步骤引导（投料→等待编译→看报告），`onboardingShown` flag 确保关闭后不再现
  - Today feed 术语收敛：`reviewBucketDisplayLabel()` 将 `review:counter_evidence_candidates` 等机制词映射为"新反证待审"、"判断需要复核"等用户语言；动作标签改为"待确认操作"
  - Universal Input 分级引导：placeholder 简化为"投网址、文件、图片，或直接提问……"，下方增加 `Ctrl+Enter 提交 · 也可拖入文件` 提示
  - 运行时状态三态可视化：`automation` 卡片增加状态 pill（绿色=正常运行/蓝色=待确认/橙色=需要关注/灰色=空闲），`autoState` 字段由 `buildAgentLoopEntries` 推导
  - LLM 异常温和反馈：新增 `buildLlmHealthEntry()`，当 `llm_health.status` 为 degraded/failed 时在 automation 区展示温和提示而非 Notice 弹窗
- **Phase 2 — 视觉与交互精修**:
  - 设计令牌扩展：在 `.furnace-shell-view` 下新增 `--furnace-space-{xs/sm/md/lg/xl}`、`--furnace-radius-{sm/md/lg/xl/full}` 语义令牌
  - 报告卡视觉升级：V3 report card 增加协议色左侧条（3px）、hover lift（translateY + box-shadow）、unread 强化（左侧条 accent 色 + primary 背景）
  - Today feed 卡片增强：border-left 3px accent hover、微上浮过渡
  - 按钮语义三态：primary (filled accent) / secondary (outline) / tertiary (ghost transparent)，全局一致 CSS
  - 过渡动画：report card hover/focus、feed item hover、按钮 hover 均加 smooth transition
  - Advanced 内容分层：body 内 section 加 border-top 分隔
- **Phase 3 — 产品完整性收口**:
  - Settings 页重组为 5 组：语言与外观 / 炉子连接 / Ask 默认行为 / LLM 配置 / 通知，section header 使用 `.furnace-settings-section` 样式
  - 轻量 Onboarding：`renderStartGuide()` 在全新 vault 首屏展示，与 Phase 1.1 的引导卡片合并
  - 命令面板精简：public 命令从 8 减到 6（移除 drop-image 和 search-workspace 到 advanced，Compile 改名为"刷新炉子"）
  - Accessibility 基线：Advanced drawer summary 添加 `tabindex="0"`
  - 跨主题色彩兼容：Today feed decision/proposal 左侧色条 fallback 链使用 Obsidian 标准 token
  - 空态视觉统一：`.furnace-shell-empty` 增加 dashed border + 居中 "—" 分隔符
- **测试 / 指标**:
  - `build.sh`: 7960 lines main.js
  - `npx jest`: 4 suites, 48/48 passed
  - `bash scripts/verify.sh`: 1572 unit + 13 acceptance / 92% coverage / `All checks passed!`
  - Python test update: `test_product_shell_today_feed.py` 1 assertion updated（"Review queue" → "reviewBucketDisplayLabel" + "待审队列"）
- **文件修改**: 8 files (render_home.js, render_today.js, render_input.js, render/cards.js, today_feed.js, constants.js, settings.js, styles.css)
- **Stop Lines**: 0 shell-summary contract 扩展；0 runtime schema 新增；0 review/apply/revert/audit 边界改动；0 npm 依赖新增；0 已有功能破坏
- **UX 评估升级**: Product Shell 从 "UX skeleton (v0.2.0)" 推进到 "产品级首屏体验 + 视觉系统 + 完整设置页"；剩余产品化工作为长期：生产级通知验证、多周自然运行稳定性、大规模知识库下图谱性能
