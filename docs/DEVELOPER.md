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
| `content/` | source / concept / material / archive / rewrite（**不得** import `memory`） |
| `corpus/` | 只读共享层：paths / scoring / ranks / parse / sections / snapshots / link_state（供 content+memory；**不得** import content/memory/execution/runner） |
| `render/` | views / packs / pilots / protocols |
| `memory/` | graph_* 子模块、query_routes、trace/recall（**不得** import `content`；共享符号走 corpus） |
| `execution/` | receipts、history、alchemy_*、review / gc_orphans / repair_plan 等治理执行面 |
| `runner/` | workflows（compile/lint/nightly）、workflows_ask*、watch、alchemy 编排 |
| `cache/`、`vault/` | cache 子系统、Obsidian bootstrap |
| `app_shell/` | Product Shell summary / controls / status（直引子模块；`__init__` 无 facade） |
| `app_linting/` | lint phases、repair backlog、nightly health（直引子模块；`__init__` 无 facade） |

热点（deferred seam）：`content/concepts.py`、`drop/url.py`（巨石单 seam 外提，节奏见 PROGRESS）；views/ask/io 已外提 ask_report / file_back / output_artifacts。

### 已知包级环（acknowledged debt）

`scripts/docs_consistency_check.sh` 只锁**已声明红线**（如 `content ↛ memory`、`memory ↛ content/execution`、corpus 隔离、facade 清零）；下列 import 环仍存在，本轮**不拆**：

- `compile` ↔ `content` / `render` / `memory` / `execution`
- `memory` ↔ `render`
- `cache` ↔ `*`（多域读 cache）
- `lifecycle` ↔ `memory`
- `app_shell` ↔ `*`（Product Shell 聚合读）
- `execution` ↔ `notify`

新增代码勿扩大环；拆环见 Post-Cleanup / PROGRESS。

### CLI taxonomy

| Layer | Commands |
|---|---|
| `primary` | `drop`, `today`, `advanced` |
| `advanced` | **日常/运维**：compile、lint、run-ask*、file-back、review-page、watch、run-nightly、gc-orphans、金丹链、shell-status、llm-check、trace… |
| `诊断` | `metrics`（复利指标快照；非日常主路径，复盘时再跑） |

## Release checklist（wheel 本地验收；非 PyPI upload）

发版前：`bash scripts/build_release_wheel.sh` → 干净 venv 安装 `dist/aiwiki-*.whl` → `aiwiki --help` + `default_prompts` 断言（步骤见 [INSTALL.md](./INSTALL.md) 方式三）；**禁止**在本任务流中 `twine upload` 或宣称已上架。

## 验证

```bash
bash scripts/verify_target_rules.sh          # 按改动路径选 target
bash scripts/verify.sh [target]              # scripts|smoke|python-static|unit|acceptance|llm-integration|cli-smoke|product-shell-static|coverage|all
bash scripts/docs_consistency_check.sh
```

**现行 verify gate**（`bash scripts/verify.sh all`）：

| Target | 内容 |
|---|---|
| `acceptance` | **25** tests — `tests/test_acceptance_loop.py`（`case_*` fixture + path safety + alchemy revert + provenance GC 等） |
| `llm-integration` | **84** tests — `tests/test_llm_integration.py`（mock backends） |
| `unit` | **176** tests — `tests/test_security.py` + `tests/test_vault_plugin.py` + `tests/test_library_surfaces.py`（含 content/memory 双向 ↛ / facade 清零契约）+ `tests/test_repair.py` + `tests/test_alchemy_revert.py` + `tests/test_cli_surfaces.py`（library + argv/dispatch：run-nightly / watch / review-queue / alchemy demote|revert / drop pdf|image） |
| `product-shell-static` | `node --check` + **bundle drift 硬门禁**（main.js 必须等于 src/ 现构建）+ Jest **203** hard-gate |
| `coverage` | informational 报告（**无门禁**；2026-08-05 实测全量 **71%**） |
| 其余 | scripts、cli-smoke、smoke、python-static |

本地开发常用：

```bash
bash scripts/verify.sh
PYTHONPATH=src python3 -m pytest tests/test_acceptance_loop.py -q
bash scripts/verify.sh llm-integration
PYTHONPATH=src python3 -m aiwiki.cli --root . advanced shell-status
```

coverage 只报告不卡线（`bash scripts/verify.sh coverage`，informational）；无 `tests/unit/` 目录，library 级单测为 `tests/test_security.py` / `tests/test_vault_plugin.py` / `tests/test_library_surfaces.py`，经 `unit` target 硬门禁。

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
