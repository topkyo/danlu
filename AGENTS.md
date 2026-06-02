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
- 动态任务状态写 `PROGRESS.md`；跨对话仍然成立的项目知识写 `MEMORY.md` 或 `.agentstack/memory/project.md`。
- AgentStack 的当前执行上下文写 `.agentstack/context/active.md`；本地证据写 `.agentstack/evidence/`，该目录不入库。

禁止长期写进本文件：

- 临时调试日志
- 单轮任务才成立的中间结论
- 会频繁变化的执行过程细节

## AgentStack 工作流

- 本仓库使用 AgentStack 接管工程工作流，安装平台为 `codex,claude,opencode`。
- 小范围代码变更默认按 L1 处理：使用 `agentstack-devloop`，做最小正确修改，运行 targeted verify，再收口。
- 需求模糊、行为选择未定、UI/API 取舍或用户要求先讨论时，使用 `agentstack-brainstorming`。
- 多文件、多步骤且范围已明确时，先用 `agentstack-write-plan` 形成可执行计划。
- 已有已批准计划时，用 `agentstack-execute-plan` 按顺序执行。
- 结束阶段用 `agentstack-finish` 汇总变更、验证、审查状态、风险和后续事项。
- 未知代码区先做局部只读探索：列出相关文件、关键符号、建议局部命令、风险和待验证假设，再进入编辑。
- 可并行做只读探索，但主 agent 负责需求澄清、任务拆分、最终判断、集成和验证。
- 执行已批准计划后，且在提交或推送 L2+ / 复杂 diff 前，必须另起 read-only reviewer subagent 做独立审查。
- reviewer 只报告 correctness / security / scope / missing verification 风险，不改代码、不跑测试；主 agent 负责修复、集成、验证和最终判断。
- 独立审查结果用 `scripts/agentstack review --id independent --reviewer independent --handoff PATH --result pass|needs-fix|blocked` 记录；如 review 后发生实质代码修改，必须重新 targeted verify 并复审，或明确记录为何无需复审。
- 提交/推送前必须满足 targeted verify pass、独立 reviewer 无阻断问题、review evidence 已记录；除非用户明确要求跳过该 gate。
- 不把 AgentStack 当成 runtime 依赖；它只约束 agent/tooling 协议、验证入口和开发协作方式。

## 验证入口

- 安装健康检查：`scripts/agentstack doctor --platforms codex,claude,opencode`
- targeted verify：`scripts/agentstack verify --target auto`
- 全量 verify：`scripts/agentstack verify --full`
- 项目底层验证入口：`bash scripts/verify.sh [target]`
- 常用 target：`scripts`、`smoke`、`python-static`、`unit`、`acceptance`、`cli-smoke`、`product-shell-static`、`all`
- `scripts/verify_target_rules.sh` 是项目自有 target emitter，供 AgentStack auto verify 使用。

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
- 维持 deterministic baseline + 显式 LLM 执行层；Shell/CLI 默认主路由是 `opencode-api/deepseek-v4-pro`，不自动 fallback 到 `codex-cli/gpt-5.5` 或写占位式 deterministic fallback 内容。
- 维持直接投喂入口：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo`。
- 维持协议 runtime：`general / investing / research / product / ops`。
- 维持治理与执行层：`review / aging / escalation / repair / nightly / apply / revert / audit`。
- 保持 `raw/ -> wiki/ -> output/` 分层，不引入 hosted service、multi-user sync、heavy RAG infra 或 fine-tuning。

## Source Of Truth

- 项目规范：`README.md`
- AgentStack 当前上下文：`.agentstack/context/active.md`
- AgentStack 项目记忆：`.agentstack/memory/project.md`
- 任务状态：`PROGRESS.md`
- 本地验证入口：`scripts/agentstack verify --target auto`
- 底层验证入口：`bash scripts/verify.sh`
- 运行态验证入口：目前使用 `tests/` 中的 fixture-driven CLI smoke tests
- 部署入口：none
- Dogfood receipt 试运行期间，先 `source .envrc.dogfood` 再执行 CLI；该文件仅作 dogfood 加速器，runtime 默认值不变。

## 稳定约束

- 技术栈：Python 3.10+, stdlib-first, markdown + JSON manifest。
- 运行模型：`single writer, many readers`。
- `raw/` 是唯一事实输入层；`wiki/sources/` 与 `wiki/derived/` 必须严格分层。
- 派生输出不能覆盖原始 source pages；所有结论都应保留 provenance。
- `decision / judgment / execution` 层必须保持可审计、可回滚、可追溯。
- 非目标：hosted service, multi-user sync, heavy RAG infra, fine-tuning。

## 自主权边界

可直接做：

- 本地代码、文档、测试修改
- AgentStack 本地脚手架生成、清理和重建
- 目录结构调整与无副作用的本地验证
- 当前用户范围内的 `systemd --user` 服务安装与更新

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
