---
title: "炼丹炉开发者指南"
kind: "guide"
status: "active"
updated_at: "2026-07-20"
related_docs:
  - README.md
  - docs/INSTALL.md
  - AGENTS.md
---

# 炼丹炉开发者指南

面向贡献者与 operator。用户安装与日常使用见 [README.md](../README.md)、[INSTALL.md](./INSTALL.md)、[USER_GUIDE.md](./USER_GUIDE.md)。

## Owner map（P2-9 后）

顶层 `app_*.py` hub **归零**（0 文件）。新增逻辑必须直引 owner 模块，禁止再引入 facade 或顶层 hub。

| 包 | 职责 |
|---|---|
| `utils/` | io、security、markdown、text（CJK tokenize）、hash、audit 等 primitives |
| `state/` + 域 `paths.py` | 持久化 state I/O（best-effort / strict 双语义） |
| `protocol/` | 单 runtime layout、schema、review windows、runtime config |
| `lifecycle/` | judgment/decision lifecycle、aging、review queue |
| `cli/` | product-first surface：`drop` / `today` / `advanced` |
| `drop/` + `input_planner.py` + `executor.py` | raw materialization；universal drop LLM plan → deterministic execute |
| `compile/` | compile pipeline + ranking |
| `content/` | source / concept / material / archive / rewrite |
| `render/` | views / packs / pilots / protocols |
| `memory/` | graph_* 子模块、query_routes、trace/recall |
| `execution/` | receipts、history、alchemy_*、l3_proposals（library）、machine_memory_actions |
| `runner/` | workflows（compile/lint/nightly）、workflows_ask*、watch、alchemy 编排 |
| `cache/`、`vault/` | cache 子系统、Obsidian bootstrap |
| `app_shell/` | Product Shell summary / controls / status |
| `app_linting/` | lint phases、repair backlog、nightly health |

热点（deferred seam）：`execution/machine_memory_actions.py`、`runner/alchemy.py`、Product Shell `plugin.js`。

### CLI taxonomy

| Layer | Commands |
|---|---|
| `primary` | `drop`, `today`, `advanced` |
| `advanced` | compile、lint、run-ask、file-back、review-page、watch、run-nightly、金丹链、metrics、trace、shell-status、llm-check、gc-orphans 等（`advanced --help`） |

## 验证

```bash
bash scripts/verify_target_rules.sh          # 按改动路径选 target
bash scripts/verify.sh [target]              # scripts|smoke|python-static|acceptance|llm-integration|cli-smoke|product-shell-static|all
bash scripts/docs_consistency_check.sh
```

**现行 verify gate**（`bash scripts/verify.sh all`）：

| Target | 内容 |
|---|---|
| `acceptance` | **17** tests — `tests/test_acceptance_loop.py`（`case_*` fixture + path safety + provenance GC 等） |
| `llm-integration` | **76** tests — `tests/test_llm_integration.py`（mock backends） |
| `product-shell-static` | `node --check` + Jest **173** hard-gate |
| 其余 | scripts、cli-smoke、smoke、python-static |

本地开发常用：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -q
bash scripts/verify.sh llm-integration
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced shell-status
```

旧 144 pytest 单元测试已 retire；不以 `coverage run pytest` 为 gate。

## 自动化

- **watch**：`raw/inbox` 变化 → deterministic compile + lint；默认不 inline LLM。
- **run-nightly** / nightly timer：deterministic compile + lint + health write（W8：无 agent-loop / signals / debt LLM）。
- 安装：`AIWIKI_VAULT=/path/to/vault scripts/install_user_service.sh`（systemd）或 `install_launchd_service.sh`（macOS）。

W3 已删 `run-compile` / `run-lint` 与 AgentOS governance CLI。`auto_adopt.py` 已删；`AIWIKI_NIGHTLY_AUTO_ADOPT_*` env 为 legacy no-op。

## 图谱

**不要混用两种视图：**

1. **证据关系链（用户默认）**：Obsidian Graph — `output/reports` → `wiki/sources` → `raw/inbox`（+ 可选 judgment）。`compile` 会恢复 `.obsidian/graph.json`。
2. **机器记忆（维护用）**：`.aiwiki/cache/machine-memory-graph.json`（compile 写入的邻接导出）+ `.aiwiki/state/` 内 machine-memory JSON。**HTML 图谱（`output/graph/machine-memory.html`）已停写**；历史路径可能仍存在于 vault 模板，勿再当主维护入口。
3. **删报告后**：compile scrub 死 `output/reports` 引用（frontmatter + 正文）并写 `provenance_status`；清炉用 `aiwiki advanced gc-orphans`（默认 dry-run，见 spec）。
4. **概念硬度**：`hardness: soft|medium|hard`。≤1 个 source 的概念 compile 强制 `soft`；≥4 sources 的过载概念 lint 告警（拆分走 repair backlog / `split-overloaded-concept`）。勿手工把噪音概念升到 medium+。

详见 `wiki/indexes/README.md`（indexes 由 compile 生成）。

## LLM 后端

产品默认锁定 `opencode-api/deepseek-v4-pro`；无隐式 cross-backend fallback。开发者 escape hatch：`deepseek-api`、`openai-api`、`anthropic-api`（显式 `AIWIKI_LLM_BACKEND`）。

- `run-ask` / universal `drop` planner：主 LLM 路径
- `AIWIKI_LLM_PLANNER=0`：drop 退回确定性分类器
- `AIWIKI_LLM_DISTILL=0`：distill 退回 deterministic seed
- API key 不得进 git；推荐 `~/.aiwiki-secrets/<provider>.env`

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced llm-check --probe
```

## 模块边界（新增能力落位）

```text
cli/          命令入口
drop/         raw materialization
input_planner + executor   universal drop plan/execute
runner/       workflows + run-ask + watch + nightly
compile/      pipeline phases + ranking
content/      source / concept / material / archive
render/       views / packs / protocols
memory/       graph_* + query_routes
execution/    receipts / history / alchemy_*  （mutation 必须 receipt + hash + revert）
lifecycle/    knowledge + status
protocol/     layout / schema / runtime config
state/        持久化 I/O（best-effort vs strict）
utils/        底层 primitives
```

## 约定

- `raw/` 是唯一事实输入层。
- `wiki/sources/` 与 `wiki/judgments|decisions|concepts/` 分层；`wiki/derived/` 仅 legacy 锚点。
- 单 runtime `general` only；禁止恢复多 slug 切换。
- 事实层 mutation 必须走 `execution/`；receipt 写失败必须 rollback。
- 持久化 state 读取必须显式选 best-effort 或 strict（见架构文档 §9）。
