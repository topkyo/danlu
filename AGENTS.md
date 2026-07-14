# AGENTS.md

## 作用域与分层

- 本文件同时承担本项目的 agent protocol 和项目事实，默认不依赖用户 home 目录配置。
- 本仓库实现 `aiwiki`，即“炼丹炉”的 local-first runtime / CLI / 仓库本体。
- “炼丹炉”是产品/系统名；`aiwiki` 是实现内核、命令名和仓库名。
- `/Users/ht/github/danlu` 是当前 runtime 代码仓库。
- `/Users/ht/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉` 是当前真实 Obsidian dogfood vault。
- 代码修改、测试和 runtime 文档更新默认发生在 `/Users/ht/github/danlu`；只有用户要求验证真实 dogfood 行为、检查 Product Shell 产物或重跑坏产物时，才以 iCloud Obsidian vault 作为 `--root` 运行 runtime。
- 分析用户实际 Product Shell 提问、报告质量、LLM receipt、run notes 或 vault 内容时，默认查 iCloud Obsidian vault，不要误用当前代码仓库的 `output/control/shell-summary.json` 代替 dogfood 证据。
- iCloud vault 的 `scripts/aiwiki-launcher.sh` 是用户可见运行入口，当前应指向 runtime root `/Users/ht/github/danlu`；旧 `/home/tim/...` 路径只属于历史记录。
- 动态任务状态写 `PROGRESS.md`；跨对话仍然成立的项目知识写 `MEMORY.md`。
- 当前阶段性执行计划：`docs/Furnace Cleanup Commercial Audit Plan 2026-07.md`。

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
- 常用 target：`scripts`、`smoke`、`python-static`、`unit`、`acceptance`、`cli-smoke`、`product-shell-static`、`all`
- 按改动路径建议 target：`bash scripts/verify_target_rules.sh`
- 文档一致性：`bash scripts/docs_consistency_check.sh`

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
- 维持 deterministic baseline + 显式 LLM 执行层；Shell/CLI 默认主路由是 `opencode-api/deepseek-v4-pro`，不自动跨 backend fallback，也不写占位式 deterministic fallback 成功内容。
- 维持直接投喂入口：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo`。
- 维持协议 runtime：`general / investing / research / product / ops`。
- 维持治理与执行层：`review / aging / escalation / repair / nightly / apply / revert / audit`。
- 保持 `raw/ -> wiki/ -> output/` 分层，不引入 hosted service、multi-user sync、heavy RAG infra 或 fine-tuning。
- Product Shell 正式支持 Desktop Obsidian only；iPad/iOS 不做全功能直移植。

## Source Of Truth

- 项目规范：`README.md`
- 架构 / 契约 / 运行：`docs/README.md` Active 表
- 阶段性计划：`docs/Furnace Cleanup Commercial Audit Plan 2026-07.md`
- 任务状态：`PROGRESS.md`
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

### 彻底做干净 = 一次做完这些，不做中间态

1. 生产与测试全部改直引 owner（`content.*` / `render.*` / `memory.*` / `execution.*` / `compile.*`）。
2. 所有 `patch("aiwiki.app_content|app_render|app_surfaces|app_memory_surfaces|app_compile.<lazy>")` 改到真实 owner 模块。
3. 去掉 owner 为了 patch 又绕回 facade 的 `_facade` 回环（如 `content/*`、`memory/graph.py`）。
4. 删除纯 facade 文件：`app_content.py`、`app_render.py`、`app_surfaces.py`、`app_memory_surfaces.py`；`app.py` 若无外部硬依赖则删除或缩成极薄入口。
5. compat oracle（如 `tests/test_execution_compat.py`）与仅断言 re-export 的单测：删除或改成 owner 契约测试。
6. 本轮明确不动：有真实逻辑的 legacy hub（`app_utils` / `app_state` / `app_protocol` / `app_lifecycle` 等）——那是另一条搬迁线，不与纯 facade 清除混做。CLI 顶层双注册已取消：只保留 `drop/today/metrics/advanced`；旧顶层名靠 argv rewrite compat（见 `cli/legacy_argv.py`）。

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

- 先结论，再证据，再建议。
- 先回答问题，再做管理操作。
- 不主动 `git commit` / `git push`，除非用户明确要求；用户说“提交并推送”时，默认直接在当前分支提交并推送。
- 只有用户明确要求“开分支”或“开 PR”时，才新建分支或 PR。
- 不自动 `commit` 包含明显凭据、`.env`、大二进制等敏感/异常文件，遇到先停并汇报。
- 讨论产品时优先说“炼丹炉”；讨论仓库、CLI、runtime 时再说 `aiwiki`。
- 发现事实层污染、无来源结论或越层写入时必须明确指出。
- 关键假设、限制和风险必须明确说明。

## Cursor Cloud specific instructions

面向后续 cloud agent（假定 update script 已跑过、依赖已就绪）的运行态注意事项。标准命令见 `README.md`（`## 验证` / `## 开发说明`）和 `scripts/verify.sh`，这里只记非显而易见的坑。

- 技术栈是 stdlib-first，`pyproject.toml` 里 `dependencies = []`；开发依赖只有 `ruff` + `coverage`（`[project.optional-dependencies].dev`）。系统 Python 有 PEP 668 限制，pip 安装用 `--break-system-packages`（update script 已处理）。
- `bs4`（`beautifulsoup4`）是可选 HTML 抽取增强：不装时 `drop-url` 退化成 `regex-fallback`，且几个 drop/extract 测试会失败。update script 已一并安装。
- 入口：`bash scripts/verify.sh`（lint + compileall + coverage + CLI smoke）；单跑测试 `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`；跑应用 `PYTHONPATH=src python3 -m aiwiki.cli --root <vault> <cmd>`。
- 应用是纯 CLI，没有需要常驻的 web/GUI 服务；Obsidian 只是前端，cloud 里跑不起来，不用去起 server。
- 跑应用时用临时 `--root`（如 `/tmp/furnace-demo`）做冒烟，别直接写仓库里已提交的 `raw/wiki/output`（`single writer, many readers`）。确定性链路 `layout -> drop-note -> compile -> ask -> lint` 完全离线可跑；`run-compile` / `run-ask` 需要显式 `AIWIKI_LLM_BACKEND` 和对应凭据才行。
- 已知与环境/仓库状态耦合、跟依赖安装无关的失败（不要当成 setup 没做好）：
  - `test_app.py` 里有一批测试硬编码绝对路径 `/home/tim/ai-wiki/...`。update script 会建软链 `/home/tim/ai-wiki -> 仓库根`，让这些测试通过；不要删这个软链。
  - `test_obsidian_workspace.test_workspace_defaults_open_home_and_furnace_center`：已提交的 `.obsidian/workspace.json` 是被 Obsidian 保存过的真实布局，和测试期望的默认布局不一致，属既有失败，改它等于改已提交产物，超出 setup 范围。
  - `test_drop.test_fetch_url_raises_when_no_text_can_be_recovered`：环境里装了真实 `google-chrome`，该测试会真去渲染并在无网时 ~45s 超时，属环境/网络耦合的既有失败。

