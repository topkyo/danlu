# AGENTS.md

## 作用域与分层

- 本仓库实现 `aiwiki`，一个 local-first 的知识编译器原型
- `open-harness` 负责工程闭环与质量护栏，不负责知识库 runtime 本身
- 动态任务状态写 `PROGRESS.md`
- 设计边界和本轮执行约束写 `.codex/contracts/active.md`

禁止长期写进本文件:
- 临时调试日志
- 单轮任务才成立的中间推理
- 会频繁变化的 gate 结果

## 风格

- 与用户沟通默认中文；代码、命令、路径和 schema 保持原文
- 直率务实，优先可验证的最小实现
- 不确定时直说；如果先做过渡实现，必须写明升级路径
- 非必要不扩 scope；可逆本地操作直接做

## 项目一句话

- `aiwiki` is a file-based knowledge compiler that turns raw sources into structured markdown wiki artifacts.

## 当前方向

- 搭建 MVP: `ingest`, `compile`, `ask`, `file-back`, `lint`
- 增量接入多后端 LLM 执行层（`codex-cli` / `claude-cli` / `openai-api`），但保持 deterministic 路径可独立运行
- 提供 4 个直接投喂入口：`drop-url` / `drop-pdf` / `drop-image` / `drop-repo`
- 保持 `raw/ -> wiki/ -> output/` 分层，先不接向量库、服务化部署或 fine-tuning

## Source Of Truth

- 项目规范: `README.md`
- 设计与本轮范围: `.codex/contracts/active.md`
- 任务状态: `PROGRESS.md`
- 本地验证入口: `bash scripts/verify.sh`
- 运行态验证入口: 目前使用 `tests/` 中的 fixture-driven CLI smoke tests
- 部署入口: none

## 稳定约束

- 技术栈: Python 3.10+, stdlib-first, markdown + JSON manifest
- `raw/` 是唯一事实输入层；`wiki/sources/` 与 `wiki/derived/` 必须严格分层
- 派生输出不能覆盖原始 source pages；所有结论都应保留 provenance
- 非目标: hosted service, multi-user sync, OCR, heavy RAG infra, fine-tuning

## 自主权边界

可直接做:
- 本地代码、文档、测试、prompts、harness 文件修改
- 目录结构调整与无副作用的本地验证
- 当前用户范围内的 `systemd --user` 服务安装与更新
- 在 `closed_loop` 通过后执行本地自动提交，前提是没有命中 stop conditions 且没有外部副作用
- 使用 `scripts/finalize_task.sh` 收口本地闭环并生成 commit

需要先确认:
- 外部模型/服务接入
- 远端部署、共享环境改动、凭据配置
- 会改变 repo 事实分层规则的架构调整
- `push`、远端发布、PR 创建

## Harness 闭环

- 开工前先读 `PROGRESS.md` 和 `.codex/contracts/active.md`
- 非 trivial 任务默认维护 active contract
- 默认顺序: `contract -> implement -> verify -> qa-review -> update PROGRESS`
- 本地 end-to-end 收口默认可以继续到 `closed_loop -> finalize_task.sh`
- `verify` 入口统一为 `bash scripts/verify.sh`
- Standard tier 默认要求 `qa-review`; 当前没有独立 reviewer 时要记录 fallback 原因

## 沟通

- 先结论，再证据，再建议
- 默认不主动 `push`
- 本地 `commit` 允许在 `closed_loop` 通过后自动进行；如果当前执行环境有更高优先级限制，以更高优先级限制为准
- 发现事实层污染、无来源结论或越层写入时必须明确指出
