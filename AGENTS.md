# AGENTS.md

## 作用域与分层

- 本文件同时承担本项目的 agent protocol 和项目事实，默认不依赖用户 home 目录配置。
- 本仓库实现 `aiwiki`，即“炼丹炉”的 local-first runtime / CLI / 包名。
- “炼丹炉”是产品/系统名；`aiwiki` 是实现内核与命令名。
- Runtime checkout 就是当前 git 工作树根。代码修改、测试和 runtime 文档默认发生在这里；不要把本仓库已提交的 `raw/wiki/output` 当用户 vault 来写。
- 真实 dogfood vault **不在本仓库内**。维护者本机路径写在 gitignored 的 `AGENTS.local.md`（从 `AGENTS.local.md.example` 复制）。若该文件存在，分析真实 Product Shell 提问、报告、LLM receipt 或同步插件时先读它，不要用仓库内 `output/control/shell-summary.json` 代替。
- 贡献者用 `aiwiki advanced new-vault <path>` 建自己的 vault。同步 Product Shell 到已有 vault 必须显式设置 `FURNACE_DOGFOOD_VAULT`（见 `CONTRIBUTING.md`）；脚本不再内置任何人的家目录。
- Product Shell 直接 spawn runtime checkout 的 `python -m aiwiki.cli`；runtime root 记录在插件 `data.json` 的 `settings.runtimeRoot`。
- 贡献约定见 `CONTRIBUTING.md`；安全披露见 `SECURITY.md`。

禁止长期写进本文件：

- 临时调试日志
- 单轮任务才成立的中间结论
- 会频繁变化的执行过程细节

## 工作流

- 小范围代码变更：最小正确修改 → targeted verify → 收口。
- 需求模糊或行为未定时：先短设计/选项，再实现。
- 多文件多步骤且范围已明确：先写可执行计划，再按序执行。
- 未知代码区先做局部只读探索：相关文件、关键符号、建议命令、风险和待验证假设，再编辑。
- 可并行做只读探索，但主 agent 负责需求澄清、任务拆分、最终判断、集成和验证。
- L2+ / 复杂 diff 提交前：另起 read-only reviewer 报告 correctness / security / scope / missing verification；主 agent 负责修复与验证。
- 不引入 AgentStack 或等价 scaffolding；验证与协作直接用本仓库 `scripts/verify.sh` 与文档 SoT。

## 验证入口

- 主验证入口：`bash scripts/verify.sh [target]`
- build + 同步 Product Shell 到已有 vault：`FURNACE_DOGFOOD_VAULT=<vault>/.obsidian/plugins/furnace-product-shell bash scripts/sync_product_shell_to_vault.sh`（`build.sh` 重建 `main.js`，并把 vault 端的 `main.js` / `styles.css` 重新 link 到仓库；`manifest.json` / `data.json` 保持本地不动；**必须**设 `FURNACE_DOGFOOD_VAULT`，无默认家目录）
- 常用 target：`scripts`、`smoke`、`python-static`、`unit`、`acceptance`、`llm-integration`、`cli-smoke`、`product-shell-static`、`coverage`、`all`
  - 日常：`scripts` + `python-static` + `smoke`（无 coverage，单次常 ~25s）；用 `bash scripts/verify_target_rules.sh` 按改动路径自动选
  - `all` 走 `scripts + product-shell-static + cli-smoke + smoke + python-static + unit + acceptance + llm-integration + coverage`（常约 1–2 min，**含 acceptance 25 fixture replay + Product Shell Jest 209 + LLM integration 88 + unit 172**）；`product-shell-static` 含 main.js bundle drift 硬门禁；`coverage` 仅打印报告（informational），**不设门禁**
- 按改动路径建议 target：`bash scripts/verify_target_rules.sh`
- 已移除：`cache_benchmark.py` / `compile_benchmark.py` / `dogfood_maturity_gate.py` / `agos9_*.sh` 等耗时辅助脚本、`verify.sh` 内的 `coverage run pytest` 段（释放 12 min）以及旧 bundle drift gating；`product-shell-static` 现为 `node --check` + Jest hard-gate（可用 `AIWIKI_SKIP_PRODUCT_SHELL_JS_TESTS=1` 紧急旁路）；脚本侧只保留 vault/runtime/install/uninstall 核心
- 文档一致性：`bash scripts/docs_consistency_check.sh`
- `tests/` = acceptance + llm-integration + library 级单测：`tests/test_acceptance_loop.py` + `tests/acceptance/` + `tests/fixtures/` + `tests/test_llm_integration.py` + `tests/test_security.py` + `tests/test_vault_plugin.py` + `tests/test_library_surfaces.py` + `tests/test_repair.py` + `tests/test_alchemy_revert.py` + `tests/test_cli_surfaces.py`；`verify.sh all` 跑 **25** acceptance + **88** llm-integration（含 plan/execute / CJK / distill / GitHub raw / path 契约）+ **172** unit。coverage 仅 informational 报告，无门禁

## 风格

- 与用户沟通默认中文；代码、命令、路径和 schema 保持原文。
- 直率务实，KISS/YAGNI。追求根因最优解，不在症状上打补丁。
- 优先分析数据结构、接口边界和真实执行路径。
- 不确定时直说；如果先做过渡实现，必须写明升级路径和删除条件。
- 能做的不问，该问的不猜；可逆本地操作直接做，不可逆或影响共享状态的操作先确认。
- 只改当前目标所必需的范围，不默认扩 scope。
- 不为单次需求新增抽象、配置项或未来扩展点；确有复用压力时再提炼。
- 每个改动行都应能追溯到本轮目标；不做顺手重构、顺手改格式或顺手清理。
- 发现无关坏味道、死代码或历史问题时先记录/汇报，不擅自纳入本轮修改。

## 调试

- 并行优先，但只并行彼此独立、可单独验证的问题。
- 默认小步试探；连续无新证据时停止扩查并汇报。
- 优先否证当前假设，不做确认偏误。
- `verify` 或等价检查失败时，先自行 `debug -> 修复 -> re-verify`。

## 错误处理

- 不得静默吞错；边界层允许捕获、转换、记录并显式暴露失败。
- 使用具体错误类型。
- 错误消息应清晰且可操作。
- 默认不做隐式降级；若必须降级，需写明触发条件、行为边界和退出条件。

## 项目一句话

- `aiwiki` is the file-based runtime that powers 炼丹炉, compiling raw sources into structured wiki, machine memory, and reviewable outputs.

## 当前方向

- 维护炼丹炉五层主线：`raw / wiki / machine memory / schema / outputs`。
- `aiwiki.corpus` 是 content 与 memory 的只读共享层（paths / scoring / ranks / parse / sections / snapshots / link_state）；**禁止** content↔memory 互 import，也禁止 corpus import content/memory/execution/runner。
- 维持 deterministic baseline + 显式 LLM 执行层；Shell/CLI 默认主路由是 `deepseek-api/deepseek-v4-flash`（DeepSeek 官方 API 直连；Ask 在 flash 下可走 DeepSeek Responses `web_search`）；`deepseek-v4-pro` 仅 Shell/设置手动选（V1 无提供商 web_search）；不自动跨 backend fallback，也不做同 backend model fallback，也不写占位式 deterministic fallback 成功内容；`opencode-api` 等其余 backend 仅作显式 escape hatch。
- 维持直接投喂入口：万能 `drop <payload>`（默认 LLM plan → deterministic execute；`AIWIKI_LLM_PLANNER=0` 可关）与 typed `drop url|pdf|image|repo|markdown|plan`。
- 维持单协议 runtime：`general` only。
- 维持治理与执行层（CLI 入口经 W3 后收敛为 `advanced` 子命令或 library API）：`review-page`、`file-back`、金丹 `alchemy start|distill|finalize|promote|revert|demote`、`run-nightly`、`watch`、`trace`、`shell-status` 等；L3 apply/revert、signals/planner-log、apply-action/rewrite/archive 等产品 CLI 已删；2026-08-04 起其背后的无入口 library 簇（machine_memory_actions / concept_rewrite / archive / lifecycle / alchemy_migration / alchemy_cleanup 等 8 模块）也已整簇删除，git 历史可回查。
- 保持 `raw/ -> wiki/ -> output/` 分层，不引入 hosted service、multi-user sync、heavy RAG infra 或 fine-tuning。
- Product Shell 正式支持 Desktop Obsidian only；iPad/iOS 不做全功能直移植。

## Source Of Truth

- **Active 文档唯一枚举**：`docs/README.md` Active 表（架构 / 契约 / 运行 / Product Shell / 商业 / 安装与用户指南）
- **评分与 release gate**：`docs/AGOS-9-Scorecard.md`
- 项目规范：`README.md`
- 验证入口：`bash scripts/verify.sh`
- 运行态验证：`tests/` fixture-driven CLI smoke / acceptance
- 部署入口：none
- Dogfood 试运行可 `source .envrc.dogfood`；该文件仅作加速器，runtime 默认值不变。

## 稳定约束

- 技术栈：Python 3.10+, stdlib-first, markdown + JSON manifest。
- 运行模型：`single writer, many readers`。
- `raw/` 是唯一事实输入层；`wiki/sources/` 与 `wiki/derived/` 必须严格分层。
- 派生输出不能覆盖原始 source pages；所有结论都应保留 provenance。
- `decision / judgment / execution` 层必须保持可审计、可回滚、可追溯。
- 非目标：hosted service, multi-user sync, heavy RAG infra, fine-tuning。

## 架构清理定案：纯 facade 一次做干净

**定案（最优解）**：纯 re-export facade 对产品运行几乎无价值，只服务历史 import / `patch("aiwiki.app_*")` 习惯。  
**禁止**“再迁一批（可选）”式半迁移；要做就一轮做完，不留中间态尾巴。

### 已落地（勿回退）

- 生产/测试直引 owner（`content.*` / `render.*` / `memory.*` / `execution.*` / `compile.*`）；根级 `app_*.py` 与纯 facade **归零**。
- CLI 顶层仅 `drop/today/advanced`；无顶层旧命令 argv rewrite。
- 验证口径见上文（acceptance **25** + llm-integration **88** + Jest **209**）。

### 禁止

- 只删 facade 文件、不改 patch / import 目标。
- 把大 hub 搬迁与纯 facade 清除捆成“顺便清一下”。
- 新增业务逻辑进任何 re-export facade。
- 写“保留 facade 作为永久架构层”或“低风险再迁一点”的新计划条目。

## 自主权边界

可直接做：

- 本地代码、文档、测试修改
- 目录结构调整与无副作用的本地验证
- 当前用户范围内的 `systemd --user` / launchd 服务安装与更新

需要先确认：

- 共享环境 / 远端环境操作
- 外部模型/服务接入
- 远端部署、共享环境改动、凭据配置
- 会改变 repo 事实分层规则的架构调整
- `push`、远端发布、PR 创建

## 默认实现闭环

- 默认自主执行 `开发 -> 验证 -> debug -> 再验证`。
- 本地、可逆、无外部副作用的操作直接做，不逐步请求确认。
- 默认 `ask_policy = blockers-only`。
- 默认停止条件：
  - 共享环境 / 远端环境操作
  - 发布 / 数据迁移 / 凭据 / 付费或其他不可逆外部副作用
  - 外部接口、数据流、依赖或回滚复杂度发生高风险变化
  - 目标不清且继续推进有较高误判风险
  - 连续 3 轮调试仍未收敛

## 沟通

- **说人话**（全局默认见 `~/.cursor/AGENTS.md`）：先说人听得懂的结论，再补证据；少堆术语与内部代号；命令/路径可保留原文，但要用白话包住含义。
- 先结论，再证据，再建议。
- 先回答问题，再做管理操作。
- 不主动 `git commit` / `git push`，除非用户明确要求；用户说“提交并推送”时，默认直接在当前分支提交并推送。
- 只有用户明确要求“开分支”或“开 PR”时，才新建分支或 PR。
- 不自动 `commit` 包含明显凭据、`.env`、大二进制等敏感/异常文件，遇到先停并汇报。
- 讨论产品时优先说“炼丹炉”；讨论仓库、CLI、runtime 时再说 `aiwiki`。
- 发现事实层污染、无来源结论或越层写入时必须明确指出。
- 关键假设、限制和风险必须明确说明。

## Cursor Cloud specific instructions

面向后续 cloud agent（假定 update script 已跑过、依赖已就绪）的运行态注意事项。标准命令见 `README.md`、`CONTRIBUTING.md` 和 `scripts/verify.sh`，这里只记非显而易见的坑。

- 技术栈是 stdlib-first，`pyproject.toml` 里 `dependencies = []`；开发依赖 `ruff` + `pytest` (+ `beautifulsoup4` 可选)。系统 Python 有 PEP 668 限制，pip 安装用 `--break-system-packages`（update script 已处理）。
- `bs4`（`beautifulsoup4`）是可选 HTML 抽取增强：不装时 `drop-url` 退化成 `regex-fallback`。update script 已一并安装。
- 入口：`bash scripts/verify.sh [target]`；单跑 acceptance：`PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py`；单跑 LLM：`bash scripts/verify.sh llm-integration`；跑应用 `PYTHONPATH=src python3 -m aiwiki.cli --root <vault> <cmd>`。pytest 只跑 `tests/test_acceptance_loop.py` / `tests/test_llm_integration.py` / `tests/test_security.py` / `tests/test_vault_plugin.py` / `tests/test_library_surfaces.py` / `tests/test_repair.py` / `tests/test_alchemy_revert.py`，勿再找 `tests/unit/`。
- 应用是纯 CLI，没有需要常驻的 web/GUI 服务；Obsidian 只是前端，云端跑不起来，不用起 server。
- 跑应用时用临时 `--root`（如 `/tmp/furnace-demo`）做冒烟，别直接写仓库里已提交的 `raw/wiki/output`（`single writer, many readers`）。确定性链路 `layout -> drop markdown -> compile -> lint` 完全离线可跑；**LLM 路径**需要凭据（`AIWIKI_LLM_BACKEND` 可省略，默认 `deepseek-api`）；`AIWIKI_LLM_PLANNER=0` / `AIWIKI_LLM_DISTILL=0` 可关对应侧门。

