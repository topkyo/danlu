---
title: "Full-Scan Evaluation 2026-08-04"
kind: "report"
status: "active"
created_at: "2026-08-04"
---

# 炼丹炉全量扫描评估报告（2026-08-04）

> **性质**：单 agent 只读全量扫描 + 本机实测的评分快照与收口清单。
> **非** Active SoT 替代物：架构以 `docs/Furnace Agent Architecture.md`、评分门禁以 `docs/AGOS-9-Scorecard.md`、执行计划以 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` 为准。
> **前序**：2026-08-03 六路 agent 审计（综合 7.4）+ `docs/plans/2026-08-03-multi-agent-audit-remediation.md`（W0–W6 已执行）。本报告是 W0–W6 之后的复评。

**HEAD**：`7f41ce9`（chore: execute multi-agent audit remediation waves W0-W6）
**工作树**：clean
**证据副本**：`.aiwiki-audit/2026-08-04-full-scan/`（`01-verify-all.log` / `02-coverage-report.txt` / `03-coverage-run.log` / `04-bundle-drift.diff`）

---

## 结论先行

**综合 6.8 / 10**（工程实测口径）。

系统是真做出来的，工程纪律高于同类个人项目平均线；但 Scorecard 的 **9.05** 撑不住三件事：

1. 全量测试实测语句覆盖只有 **58%**，20 个模块 0%；
2. 治理层 **4,064 行** mutation/revert 代码**没有任何入口、没有任何测试**；
3. 真正被 Obsidian 加载、也被 `sync-product-shell` 分发的 `main.js`，已经和被 Jest 门禁的 `src/` **漂移**。

`bash scripts/verify.sh all` 实跑 **EXIT=0**，acceptance **24** / llm-integration **82** / Jest **203**（26 suites）/ docs consistency 全 OK —— 文档计数与实测完全一致，这一点应当承认。

---

## 方法与证据口径

| 项 | 做法 |
|---|---|
| 静态扫描 | `src/` 201 个 `.py` / 49,470 行；Product Shell `src/` + bundle 共 21,825 行 JS；`.md` 84,902 行 |
| 动态验证 | `bash scripts/verify.sh all`（全绿） |
| 覆盖率 | `PYTHONPATH=src .venv/bin/python -m coverage run --source=src/aiwiki -m pytest tests/test_acceptance_loop.py tests/test_llm_integration.py`（106 passed） |
| 可达性 | 对每个 0% 模块反查 CLI / Product Shell / tests 三侧调用点，区分「无入口」与「有入口但未测」 |
| 产物一致性 | `OUT=/tmp/main.js.rebuilt bash build.sh` 后与 HEAD 提交的 `main.js` 逐行 diff |

**证据分层**：本报告全部结论为 `replay`（本机实测）或静态可复核，**不含** live dogfood 断言。

---

## 分维评分

| 维度 | 权重 | 本次 | Scorecard 自评 | Δ |
|---|---:|---:|---:|---:|
| 架构与分层 | 20% | 7.5 | 9.4 | −1.9 |
| 代码质量 / 可维护性 | 15% | 7.5 | 9.0 | −1.5 |
| 测试与验证 | 20% | **5.5** | 8.9 | −3.4 |
| 产物完整性 / 发布 | 10% | **4.5** | —（无此维） | — |
| 安全与治理 | 15% | 7.5 | 9.1 | −1.6 |
| 文档 SoT | 10% | 7.0 | 8.9 | −1.9 |
| 产品可用性（Shell） | 10% | 7.0 | 9.3 | −2.3 |
| **加权合计** | 100% | **6.8** | 9.05 | −2.25 |

与 2026-08-03 六路审计 **7.4** 的差异主要来自两条本轮新测的硬证据：产物漂移（新增维，4.5）与实测覆盖率 58%（此前无量化）。

---

## P0 / P1 缺陷

### F-1（P0，流程性）发布产物与被测源码漂移

**事实**：HEAD 提交的 `main.js` 仍是 2026-08-03 W4 修复**之前**的版本。

```
提交的 main.js:        report:1 automation:2 decision:3 proposal:4 elixir:5 action:6
src/today_feed.js:     report:1 automation:2 decision:3           elixir:4 action:5
schema/today-feed.json: priority maximum=5；kind enum 无 proposal
```

W4 修掉了 `src/today_feed.js` 的幻影 `proposal` kind 并补了双侧契约测试（Jest 203 全绿），但**未重建 bundle**。

**放大机制**：
- `src/aiwiki/vault/plugin.py:43 sync_product_shell_plugin()` 直接 `read_text` 仓库 `main.js` 后 `write_if_changed` 到目标 vault，**不 build**。`advanced sync-product-shell` 与 `new-vault` 都走这里 → 新用户 vault 拿到违反自身 schema 的产物。
- `scripts/verify.sh:91 verify_product_shell_static()` 只做 `node --check` + 对 `src/` 跑 Jest；AGENTS.md 明确记载「旧 bundle drift gating」已移除。
- `scripts/sync_product_shell_to_vault.sh:47` 会先 `bash build.sh`，所以 dogfood vault 侧被掩盖 —— 只有仓库和新建 vault 暴露。

**当前用户可见影响：低**。相对排序未变（report<automation<decision<elixir<action），`proposal` 分支 Python 端永不产生。**真正的缺陷是机制**：唯一被加载的文件是唯一没有门禁的文件，已经漂移了一次就会漂移第二次。

**Done 判据**：`verify.sh` 存在 bundle drift gate 且对当前 HEAD 失败 → 重建提交后转绿；`sync_product_shell_plugin` 拒绝分发与 `src/` 不一致的 bundle。

### F-2（P1，YAGNI 违约）4,064 行治理代码零入口零测试

反查调用链后确认，以下 8 个模块**只互相调用**，CLI / Product Shell / tests 三侧均无入口，且覆盖率 **0%**：

| 模块 | 行 | stmts |
|---|---:|---:|
| `execution/machine_memory_actions.py` | 994 | 427 |
| `execution/concept_rewrite.py` | 789 | 327 |
| `execution/lifecycle.py` | 549 | 173 |
| `execution/archive.py` | 451 | 148 |
| `execution/machine_memory_auto_resolution.py` | 424 | 165 |
| `execution/machine_memory_batch.py` | 338 | 143 |
| `execution/alchemy_cleanup.py` | 269 | 120 |
| `execution/alchemy_migration.py` | 250 | 114 |
| **合计** | **4,064** | **1,617** |

补充证据：
- `cli/dispatch.py:217 _handle_alchemy` 只导入 `run_alchemy_{start,distill,finalize,promote,revert,demote}`；`runner/alchemy.py:12-37` 的 `run_alchemy_legacy_migration_*` / `run_alchemy_superseded_cleanup_*` 四个 wrapper 无任何调用方。
- `execution/lifecycle.py` 唯一引用是 `machine_memory_actions.py:697` 的函数内 lazy import（本身也在无入口簇内）。
- `execution/concept_rewrite.py` 与 compile 链路无关：compile 用的是 `memory/execution_surfaces.py:289 reconcile_concept_rewrite_proposals`，Shell 用的是 `content/rewrite.load_concept_rewrite_state`。

**冲突点**：AGENTS.md 写「不为单次需求新增抽象、配置项或未来扩展点」，同时写「L3 apply/revert、apply-action/rewrite/archive 等产品 CLI 已删，library 与 receipt 语义保留」。保留的结果是 4 千行自称「可审计、可回滚」的 mutation 机器，没有入口，也没有任何测试证明回滚真的成立。Scorecard 把 Governance 记 **9.1** 且标 `blocking: yes`，证据写 `alchemy-revert / receipts` —— 但 revert 主体 0% 覆盖，该栏分数不成立。

**Done 判据**：二选一并写入 Scorecard —— (a) 接回入口 + 每个 apply/revert 至少 1 条 fixture 往返测试；(b) 整簇删除，`execution/__init__.py` 文档同步。**不接受第三种「继续保留待将来」**。

### F-3（P1）安全模块 39% 覆盖

`src/aiwiki/utils/security.py` 是全仓质量最高的一块，且是唯一的对外网络边界：

- `_resolve_and_check_host` 一次解析 + IP pin（`_PinnedHTTP{,S}Connection`），防 DNS 重绑定；
- IPv4-mapped IPv6（`::ffff:x.x.x.x`）归一化为 IPv4 后再判私网，防绕过；
- 跨 host 重定向剥离 `authorization` / `x-api-key` / `cookie`；
- `max_bytes` 硬上限 + 读取时逐块累计；重定向上限 5；最终 URL 二次校验；
- `safe_resolve_within` 在符号链接解析后做 root 包含校验。

**问题**：192 stmts 只测到 **39%**。SSRF 绕过属于「改一行静默失效」类缺陷，61% 的分支当前无人看守。同类：`trace.py` 30%、`drop/url.py` 32%、`autonomy_policy.py` 34%。

**Done 判据**：`utils/security.py` ≥ 80%，且至少覆盖：私网拒绝、DNS 重绑定 pin、跨 host 重定向剥 header、`max_bytes` 超限、`safe_resolve_within` 越界。

### F-4（P1，发布阻断）覆盖率 58% 且无任何 coverage 可见性

```
TOTAL  22517 stmts  9438 miss  58%
0% 模块：20 / 202
```

除 F-2 的无入口簇外，**有入口但 0% 覆盖**的还有：

| 模块 | stmts | 备注 |
|---|---:|---|
| `vault/bootstrap.py` | 46 | README 快速开始的 `new-vault` |
| `vault/plugin.py` | 36 | 即 F-1 的分发路径 |
| `render/cognitive_history.py` | 181 | `render/views.py` + `app_shell/meta.py` 在用 |
| `memory/topology.py` | 137 | `render/views.py` + `app_linting/nightly.py` 在用 |
| `lifecycle/protocol.py` | 79 | — |
| `cli/llm_check_render.py` | 75 | `advanced llm-check` 人读输出 |
| `app_linting/repair.py` | 261 | 3% |
| `memory/status.py` | 210 | 10% |

2026-07-15 退役 2,439 unit + 92% coverage 后**没有等价替代**，`verify.sh` 也不再产出任何覆盖率数字，导致这个维度长期只能靠自评。

**Done 判据**：`verify.sh` 增加**不带门禁**的 coverage 报告步骤（先要可见，不急着卡线），并把实测数字写入 Scorecard「测试与验证」维的证据栏。

---

## P2 / P3 清单

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| F-5 | `src/aiwiki/cli/__init__.py`（43 行） | `_CliModule.__setattr__` 双向同步 + `_export_module_symbols` 动态 re-export。全仓唯一消费者是 `tests/acceptance/case_runner.py:12 from aiwiki.cli import main`，**无任何测试 patch `aiwiki.cli.<symbol>`**。AGENTS.md「纯 facade 归零」的漏网者 | 删成 `from .dispatch import main` |
| F-6 | `pyproject.toml` classifiers | 声明 `Operating System :: OS Independent`，但 `src/aiwiki/utils/io.py:4` 顶层 `import fcntl`（POSIX-only），Windows 导入即崩 | 改成 POSIX 相关 classifier；**PyPI 发布前必修** |
| F-7 | `scripts/verify.sh:30` | usage 文本仍写 `llm-integration (79)`，实测 82。`docs_consistency_check.sh` 不覆盖脚本内自述数字 | 修正并把脚本纳入一致性检查 |
| F-8 | `src/aiwiki/llm.py` | `OpenAICompatClient.complete` 有 429/5xx 重试，`analyze_image` **没有**；两段约 60 行几近完全重复 | 抽公共 `_post_chat_completions`，重试逻辑单点 |
| F-9 | `src/aiwiki/llm.py:_write_raw_response` | 每次 LLM 调用（含成功）都落盘一个文件到 `.aiwiki/llm-responses/`，未见轮转/清理 | 加保留窗口或仅失败落盘 |
| F-10 | `src/aiwiki/utils/security.py` 末尾 | `class _NoRedirectHandler(__import__("urllib.request", fromlist=[...]).HTTPRedirectHandler)`，而 `urllib.request` 已在顶部 import | 直接继承 `urllib.request.HTTPRedirectHandler` |
| F-11 | 全库 | 1,489 个函数中 **193** 个 >50 行、**73** 个 >100 行；最长 413 行（`app_linting/repair.py:99 _render_backlog_markdown`），次之 `memory/health.py:11`（375）、`memory/graph_query.py:212`（374）、`app_linting/nightly.py:71`（356） | 沿用「单 seam 外提」节奏续刀，禁止 broad rewrite |
| F-12 | 文档 | `.md` 共 **84,902** 行（`docs/archive` 16,425 行 / 135 文件；docs active 4,611 行）> 代码 71,295 行 | 归档策略收紧；`PROGRESS.md` 头条限长 |
| F-13 | 契约 | `today_feed` 逻辑在 Python / JS 手工双写（`schema/today-feed.json` 只钉字段不钉排序），F-1 的漂移正由此而来 | 中期考虑单侧生成或把 PRIORITY 从 schema 读入 |

---

## 应当承认的优点

不让上述缺陷盖掉真实质量：

1. **verify 是诚实的**。24 / 82 / 203 逐个核对，文档无虚报。自评项目里少数派。
2. **Local Engineering vs Live Dogfood 双门禁** + `historical / fixture / replay / live` 四级证据分层 + 明文「不得宣称 live PASS」—— 这套自我约束比多数商业项目严格。
3. **fail-closed 不伪装成功**：LLM 失败不写占位 deterministic 内容、不隐式跨 backend fallback、失败也落 receipt。
4. **错误处理不吞错**：34 文件 94 处 `except Exception` 抽查全为 log + rollback + 抛具体类型（`AuditMirrorRollbackError` / `*HalfWriteError`）；仅 4 处裸 `pass`（`utils/io.py:133`、`cli/universal_input.py:52/118`、`llm.py:88`）且均在无害解析降级路径。
5. **写入安全有真功夫**：`utils/io.py` flock 可重入写锁（超时 + pid 元数据 + 深度计数）；audit mirror 追加失败会 durable truncate 回滚主文件（`execution/history.py:67-98`）；`atomic_write_text` 全链路铺开。
6. **W0–W6 的修复是实的**：F401 已在 ruff 生效、bridge launcher 有 180s 超时与输出上限、prompt 注入边界包装、rewrite-proposal 清理有 `kind` + `generated_by` 双判据守卫。

---

## 收口顺序建议

| 序 | 动作 | 对应 | 成本 | 换来 |
|---:|---|---|---|---|
| 1 | `verify.sh` 加 bundle drift gate；`sync_product_shell_plugin` 前置 build/hash 校验；重建并提交 `main.js` | F-1 | <1h | 堵住「发出去的 ≠ 测过的」 |
| 2 | 修 F-6 classifier、F-7 计数、F-5 facade、F-8 重试缺失 | F-5/6/7/8 | <1h | 清掉自身规则违反项 |
| 3 | 决断 4,064 行治理簇：接入口+测试 或 整簇删除 | F-2 | ~1d | Governance 分数变可信；体积 −8% |
| 4 | `utils/security.py` / `vault/plugin.py` / `vault/bootstrap.py` 补测试；verify 增加无门禁 coverage 报告 | F-3/F-4 | ~0.5d | 覆盖率进 SoT，不再靠自评 |
| 5 | 巨函数续刀（F-11）、文档归档收紧（F-12）、mirror 契约收敛（F-13） | F-11/12/13 | 持续 | 长期可维护性 |

**PyPI / 正式发布的硬前提：第 1 步与第 2 步。**
**Scorecard 修订前提：第 3 步与第 4 步**——在此之前 Governance 9.1 与 Dogfood/fixture 8.9 两栏应标注为「证据不足」。

---

## 复现命令

```bash
# 全量验证（EXIT=0，acceptance 24 / llm 82 / Jest 203）
bash scripts/verify.sh all

# 覆盖率实测（58%）
PYTHONPATH=src .venv/bin/python -m coverage run --source=src/aiwiki \
  -m pytest tests/test_acceptance_loop.py tests/test_llm_integration.py -q
PYTHONPATH=src .venv/bin/python -m coverage report --sort=cover

# 产物漂移复核
cd .obsidian/plugins/furnace-product-shell
OUT=/tmp/main.js.rebuilt bash build.sh && diff main.js /tmp/main.js.rebuilt
```

---

## 执行结果（2026-08-04，4-agent 收口）

**状态：收口顺序第 1–4 步全部完成，`bash scripts/verify.sh all` 全绿（EXIT=0）。** 第 5 步（F-11/12/13）按原计划属持续项，未纳入本轮；F-9/F-10 未做（见下）。

| 项 | 结果 | 证据 |
|---|---|---|
| F-1 产物漂移 | **done** | main.js 已重建（diff 即本报告 `04-bundle-drift.diff` 的 9 行）；`verify.sh product-shell-static` 新增 drift 硬门禁（重建+diff，正反向实测：污染 bundle → EXIT=1，恢复 → EXIT=0）；`sync_product_shell_plugin` 分发前强制执行 `build.sh`，失败 fail-loud |
| F-2 治理孤儿簇 | **done（整簇删除，用户裁定）** | 删除 8 模块 + runner 4 wrapper + receipts/paths/alchemy_helpers 死符号，合计 ~4.6k 行；保留 compile/Shell 在读的 `memory/actions.reconcile_machine_memory_actions` 等 query 侧；acceptance 24 + llm 83 回证无回归 |
| F-3 security 覆盖 | **done** | `tests/test_security.py` 56 例，`utils/security.py` 39%→**99%**（190/192；未覆盖 2 行为 urllib 内部入口，需真实 socket） |
| F-4 覆盖率可见性 | **done** | `tests/test_vault_plugin.py` 11 例（plugin sync / bootstrap）；verify 新增 `unit` 硬门禁（67 例）与 `coverage` 无门禁报告；全量覆盖 58%→**64%**（总语句 22517→20785，删除贡献为主） |
| F-5 cli facade | **done** | `cli/__init__.py` 43 行元编程 → 7 行显式 `from .dispatch import main`；改前 grep 证实全仓唯一消费者是 `main` |
| F-6 classifier | **done** | `OS Independent` → `POSIX`（fcntl 实锤） |
| F-7 verify 计数 | **done** | usage 与 SoT 文档统一为 llm **83** / Jest **203**，并新增计数钉进 `docs_consistency_check.sh` |
| F-8 重试缺失 | **done** | `OpenAICompatClient._post_chat_completions` 单点承载重试，`analyze_image` 获得 429/5xx parity 并有直接测试锁定；llm-integration 83 全绿 |
| F-9 llm-responses 轮转 | **deferred** | 每次调用落盘是 receipt 语义的一部分，改保留策略需单独决策 |
| F-10 `_NoRedirectHandler` 奇技 | **deferred** | 行为无害，1 行清理，随下次 security.py 改动顺带 |
| F-11/12/13 | **deferred（持续项）** | 巨函数续刀 / 文档归档 / mirror 契约收敛，按既定节奏 |

**本轮新发现（agent 回报，未修）**：`safe_fetch` 对 301/302/303 重定向会带原 method+body 重发（跨 host 已剥 auth header，但 body 不剥）；`_is_private_address` 靠错误消息子串判定，耦合脆弱。均为低危，记入下一轮候选。

**验证终态**：acceptance **24** / llm-integration **83** / Jest **203** / unit **67** / coverage **64%**（informational）/ docs consistency exit 0。

### 复审收尾（2026-08-04 同日，read-only reviewer 复审后）

复审结论 **ship（0 P0/P1）**，四条 P2 已当场修掉：

1. Active 文档残留引用：`docs/DEVELOPER.md` 的 `execution/` 行与热点行（仍列已删的 `machine_memory_actions` / 不存在的 `l3_proposals`）、`docs/Furnace Evolution Mechanics.md` 的 `build_execution_receipt`（实为 `build_elixir_*_receipt` 三件套）——已改。
2. `analyze_image` 重试 parity 此前只有间接覆盖——已在 `tests/test_llm_integration.py` 加直接测试（llm-integration 82→**83**）。
3. `scripts/verify_target_rules.sh` 不认识新 target——已映射 `utils/security.py` / `vault/*` / 两个新测试文件 → `unit`；`docs_consistency_check.sh` 新增计数钉（acceptance 24 / llm 83 / unit 67 / Jest 203 四组数字跨 verify.sh + AGENTS + Scorecard + DEVELOPER 一致性）。

4. F-2 删除造成的新孤儿 `src/aiwiki/autonomy_domains.py`（全仓零引用，apply 决策分类器）——已删；`autonomy_policy.py` 的 `disabled_reason` kill switch 仍存活（llm.py 在用），不动。

## 第二波执行结果（2026-08-05：F-11 部分 + F-9 + 安全加固）

| 项 | 状态 | 证据 |
| --- | --- | --- |
| F-9 llm-responses 无轮转 | **done** | `_write_raw_response` 内置 best-effort 轮转（`_LLM_RAW_RESPONSE_KEEP=500`；UTC 文件名前缀字典序=时序；prune 失败仅告警、不断写路径）；2 个直接测试锁定（保留最新 N / prune 失败不传播） |
| F-11 巨函数/巨石模块 | **partial done** | concepts.py 1197→**812**（质量簇 7 函数 → `content/concept_quality.py` 402 行；`detect_concept_*_signals` 因 concepts→quality 环风险留在原处）；views.py 1178→**942**（判断资产簇 5 函数并入既有 `render/judgment_assets.py` →440）；`app_linting/phases.py` 829→**307**（governance+curated → `phases_governance.py` 537 行，core/`__init__` 直引 owner，无 re-export seam）。剩余：views.py 仍 942、execution/runner 侧巨函数 |
| 复审低危安全项 | **done** | safe_fetch 301/302/303 对非 GET/HEAD 降级 GET 并丢 body/Content-*（307/308 保持方法+body）；`PrivateAddressError(FetchPolicyError)` 结构化检测替代消息子串匹配；3 个重定向测试 + 2 个结构化测试 |

**验证终态**：`verify.sh all` 绿——acceptance **24** / llm-integration **85** / Jest **203** / unit **72** / coverage **64%**（informational）/ docs consistency exit 0。
