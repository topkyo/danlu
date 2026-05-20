# AGENTS.md

## 作用域与分层

- 本文件同时承担本项目的 agent protocol 和项目事实，默认不依赖任何用户 home 目录配置
- `open-harness` 仓库是外部模板源；炼丹炉仓库不提交 generic harness scaffold
- 当前工作区如需工程脚手架，优先使用 `bash scripts/setup_local_harness.sh --apply --tier standard --platforms claude,codex,opencode`；它只是 `/home/tim/open-harness/scripts/bootstrap_local_scaffold.sh` 的项目内便捷别名
- 本仓库实现 `aiwiki`，即“炼丹炉”的 local-first runtime / CLI / 仓库本体
- “炼丹炉”是产品/系统名；`aiwiki` 是实现内核、命令名和仓库名
- `open-harness` 负责工程闭环与质量护栏，不负责知识库 runtime 本身
- 动态任务状态写 `PROGRESS.md`
- 跨对话仍然成立的项目知识写 `MEMORY.md` 或等价记忆
- 设计边界和本轮执行约束默认写本地生成的 `.codex/contracts/active.md`
- 如果输入是一份过大的架构文档，先写本地生成的 `.codex/plans/active.md`，再物化当前 milestone 到 `.codex/contracts/active.md`

## 多平台 harness

- 本地可能同时存在 `.claude/`、`.codex/`、`.opencode/` 等 artifact root；这些 generic scaffold 通过 `.git/info/exclude` 保持 local-only
- `.open-harness.conf` 记录当前 tier / platforms；默认 primary 仍按 `.codex` active contract 使用，除非任务显式指定其他 `HARNESS_DIR`
- 共享 gate scripts 通过 `HARNESS_DIR` 区分平台，如 `HARNESS_DIR=.codex bash scripts/closed_loop.sh --require-contract`
- 不传 `HARNESS_DIR` 时，脚本按 `.open-harness.conf`、唯一 active contract、legacy fallback 自动探测；重要闭环建议显式传入
- 当前平台 artifact root 下的 skills/runbooks 属于 agent 侧适配层；共享 gate scripts 不读取其内容作为运行前提
- 根 `AGENTS.md` / `CLAUDE.md` 放全局架构、工程闭环、安全边界和跨目录约束；子目录协议文件放局部实现细节、同步要求和验证入口
- 冲突时，根协议的安全/边界/停止条件优先；子目录协议的实现细节、测试命令和局部约定优先
- 优先从最小相关目录启动 agent，让其向上加载根协议；跨目录协议、模板渲染、gate scripts 或全局文档改动才从仓库根启动
- 大仓库或未知区域默认先做局部只读探索：给出相关文件、关键符号、建议局部命令、风险和待验证假设，再进入编辑
- 优先符号、路径、局部 grep / 局部 read，不做全仓乱读；generated/vendor/build/third-party/secrets 默认排除，`*.env` 等敏感文件默认不读
- 宽任务、架构文档或高不确定需求，先走 `/planner` 或 contract 收敛范围，再开始编辑
- 可并行做只读探索，但编辑、contract writeback、验证和 debug 仍由主执行闭环负责，不把 harness 变成 orchestrator

禁止长期写进本文件:
- 临时调试日志
- 单轮任务才成立的中间结论
- 会频繁变化的执行过程细节

## 风格

- 与用户沟通默认中文；代码、命令、路径和 schema 保持原文
- 直率务实，KISS。追求根因最优解，不在症状上打补丁
- 不确定时直说；如果先做过渡实现，必须写明升级路径和删除条件
- 能做的不问，该问的不猜；可逆本地操作直接做，不可逆或影响共享状态的操作先确认
- 只改当前目标所必需的范围，不默认扩 scope

## 调试

- 并行优先，但只并行彼此独立、可单独验证的问题
- 默认小步试探；连续无新证据时停止扩查并汇报
- 优先否证当前假设，不做确认偏误

## 错误处理

- 不得静默吞错；边界层允许捕获、转换、记录并显式暴露失败
- 使用具体错误类型
- 错误消息应清晰且可操作
- 默认不做隐式降级；若必须降级，需写明触发条件、行为边界和退出条件

## 项目一句话

- `aiwiki` is the file-based runtime that powers 炼丹炉, compiling raw sources into structured wiki, machine memory, and reviewable outputs.

## 当前方向

- 维护炼丹炉五层主线：`raw / wiki / machine memory / schema / outputs`
- 维持 deterministic baseline + 多后端 LLM 执行层（`codex-cli` / `nvidia-nim-api` / `copilot-cli` / `claude-cli`），并保持显式手动 backend 选择
- 维持直接投喂入口：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo`
- 维持协议 runtime：`general / investing / research / product / ops`
- 维持治理与执行层：`review / aging / escalation / repair / nightly / apply / revert / audit`
- 保持 `raw/ -> wiki/ -> output/` 分层，不引入 hosted service、multi-user sync、heavy RAG infra 或 fine-tuning

## Source Of Truth

- 项目规范: `README.md`
- 设计与本轮范围: `.codex/contracts/active.md`；若架构文档过大，则先看 `.codex/plans/active.md`
- 任务状态: `PROGRESS.md`
- Harness 配置: `.open-harness.conf`
- 本地验证入口: `bash scripts/verify.sh`
- 运行态验证入口: 目前使用 `tests/` 中的 fixture-driven CLI smoke tests
- 部署入口: none
- Dogfood receipt 试运行期间，先 `source .envrc.dogfood` 再执行 CLI；该文件仅作 dogfood 加速器，runtime 默认值不变

## 稳定约束

- 技术栈: Python 3.10+, stdlib-first, markdown + JSON manifest
- 运行模型: `single writer, many readers`
- `raw/` 是唯一事实输入层；`wiki/sources/` 与 `wiki/derived/` 必须严格分层
- 派生输出不能覆盖原始 source pages；所有结论都应保留 provenance
- `decision / judgment / execution` 层必须保持可审计、可回滚、可追溯
- 非目标: hosted service, multi-user sync, heavy RAG infra, fine-tuning

## 自主权边界

可直接做:
- 本地代码、文档、测试修改
- 本地 harness 的生成、清理和重建（不提交 generic scaffold）
- 目录结构调整与无副作用的本地验证
- 当前用户范围内的 `systemd --user` 服务安装与更新
- 在当前执行环境允许且本地已生成 harness 时，使用 `closed_loop` / `finalize_task.sh` 收口本地闭环

需要先确认:
- 共享环境 / 远端环境操作
- 外部模型/服务接入
- 远端部署、共享环境改动、凭据配置
- 会改变 repo 事实分层规则的架构调整
- `push`、远端发布、PR 创建

## 默认实现闭环

- 默认自主执行 `开发 -> 验证 -> debug -> 再验证`
- 本地、可逆、无外部副作用的操作直接做，不逐步请求确认
- `verify` 或等价检查失败时，先自行 `debug -> 修复 -> re-verify`
- 沟通用于开工对齐、blocker 升级和收口汇报，不作为每一轮实现循环节点
- 默认 `ask_policy = blockers-only`
- 默认停止条件:
  - 共享环境 / 远端环境操作
  - 发布 / 数据迁移 / 凭据 / 付费或其他不可逆外部副作用
  - 外部接口、数据流、依赖或回滚复杂度发生高风险变化
  - 目标不清且继续推进有较高误判风险
  - 连续 3 轮调试仍未收敛

## 默认工程闭环

- 开工前先读 `README.md`、`PROGRESS.md` 和本地生成的 `.codex/contracts/active.md`
- 默认顺序: `项目规范 -> 读取已有状态 -> 验收标准 -> 模糊需求先澄清；宽方案先用 /planner 生成 HARNESS_DIR/plans/active.md；执行前可用 /plan_review 做建议型审查；再用 /run_plan 或 run_plan.sh 进入 Harness 执行 -> 实现闭环 -> 按 contract 跑 gate -> 回写状态`
- 未知代码区先做局部只读探索；探索输出至少包含相关文件、建议局部命令、风险和待验证假设
- `PROGRESS.md` 是当前动态执行源；存在就读写，不存在才降级为 blocker 记录
- 多文件、跨模块或运行态变更默认维护本地生成的 `.codex/contracts/active.md`；若任务指定其他平台，先显式设置 `HARNESS_DIR`
- 若当前工作区尚未生成 local harness，先执行 `bash scripts/setup_local_harness.sh --apply --tier standard --platforms claude,codex,opencode`；若需要直接验证上游入口，等价命令是 `bash /home/tim/open-harness/scripts/bootstrap_local_scaffold.sh --apply --tier standard --platforms claude,codex,opencode`
- 如果需求很模糊，先用 `/office_hours` 或等价澄清；如果方案较宽，先用 `/planner` 生成 plan，再将当前 milestone 物化为 contract
- 如果已经有 `.codex/plans/active.md`，进入执行前可先用 `/plan_review` 生成建议型 `.codex/plans/plan-review.md`；该文件不是 gate artifact，`scripts/run_plan.sh` 不依赖它
- 如果已经有 `.codex/plans/active.md`，优先执行 `HARNESS_DIR=.codex bash scripts/run_plan.sh --plan-file .codex/plans/active.md` 自动推进当前 milestone；只有需要强制指定某一轮时，才回退到 `HARNESS_DIR=.codex bash scripts/materialize_contract.sh --plan-file .codex/plans/active.md --milestone <ID>`
- 如果本地 harness 已生成，优先走 `scripts/run_qa_review.sh`、`scripts/closed_loop.sh` 等入口；否则退回项目自有验证入口
- 如果项目没有这些入口，就执行等价的本地检查，不凭空假设命令存在
- 当前平台 artifact root 下的阶段 runbook 属于 agent 侧适配层；共享 gate scripts 不读取其内容作为运行前提
- 验证默认 targeted-first：实现中优先运行最小相关验证入口；harness / protocol / scaffold-only 变更可用 `bash scripts/verify.sh scripts`
- `closed_loop.sh` 默认通过 `scripts/resolve_verify_targets.sh` 和项目自有 `scripts/verify_target_rules.sh` 按当前变更确定 target，再逐个执行 `scripts/verify.sh <target>`；缺 resolver 时 fallback 到 `scripts`
- 只有 runtime 行为变更、跨模块高风险、发布 / 推送前或 contract 明确要求时，才运行全量 `bash scripts/verify.sh`；需要全量闭环时显式使用 `HARNESS_DIR=.codex bash scripts/closed_loop.sh --verify-full --require-contract` 或 `HARNESS_VERIFY_TARGET=all`，需要固定范围时用 `--verify-target <target>`
- `verify` 失败时默认继续本地调试和重复验证，不把每一轮失败都升级成用户确认
- Standard tier 默认要求 `qa-review`；当前没有独立 reviewer 时要记录 fallback 原因
- 本地 end-to-end 收口默认可以继续到 `closed_loop -> finalize_task.sh`，前提是 local harness 已生成；是否自动 commit 以当前执行环境的更高优先级约束为准

## 沟通

- 先结论，再证据，再建议
- 先回答问题，再做管理操作
- 不主动 `git commit` / `git push`，除非用户明确要求；用户说“提交并推送”时，默认直接在当前分支提交并推送
- 只有用户明确要求“开分支”或“开 PR”时，才新建分支或 PR
- 不自动 `commit` 包含明显凭据、`.env`、大二进制等敏感/异常文件，遇到先停并汇报
- 讨论产品时优先说“炼丹炉”；讨论仓库、CLI、runtime 时再说 `aiwiki`
- 发现事实层污染、无来源结论或越层写入时必须明确指出
- 关键假设、限制和风险必须明确说明
