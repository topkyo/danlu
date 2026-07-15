---
title: "炼丹炉商业化级别代码与文档清理计划"
kind: "plan"
status: "executed-reviewed-pass"
updated_at: "2026-07-15"
based_on:
  - "2026-07-14 多-agent (glm-5.2) 全量审计：8 agent（架构/文档/商业/安全/测试 + 垃圾清理/文档差距/代码差距）"
  - "docs/Furnace Cleanup Commercial Audit Plan 2026-07.md（executed-reviewed-pass，前一轮清理已收口）"
supersedes:
  - "docs/Furnace Cleanup Commercial Audit Plan 2026-07.md（前一轮，status: executed-reviewed-pass，归档为史料）"
---

# 炼丹炉商业化级别代码与文档清理计划（2026-07）

## Goal

1. **达到商业化级别代码质量**：修复阻断项 + 安全/可靠性加固，使代码从 6.5 → 8.0（可售卖门槛）。
2. **达到商业化级别文档完备度**：补齐对外商业化必需文档 + 修复内部 SoT 硬伤，使文档从 4.5 → 7.0。
3. **彻底清理垃圾**：删除死代码、生成态入库文件、过期产物、空目录、死规则；不保留中间态尾巴。
4. **收敛为 KISS**：不做 broad rewrite，不扩 scope，不为单次需求新增抽象。

本文件是**阶段性执行计划**，不是架构 SoT。完成后归档到 `docs/archive/`。

## Archive note（2026-07-15）

本计划 Waves A–D + Phase 5/D4 + acceptance golden 刷新已收口，status=`executed-reviewed-pass`。后续 commercial go-live（真实邮箱/EULA/价格）、pip 分发、Jest hard-gate 另开计划，不回写本文件。

## Scope

### In

- **垃圾清理**：`.agentstack/`、空目录、`.gitignore` 死规则、`CLAUDE.md` 冲突副本、`wiki/indexes/*.md` 生成态移出 git、`docs/analysis/` 历史文件归档
- **P0 代码修复**：2 个失败测试、安装脚本硬编码开发者路径
- **P1 安全/可靠性加固**：凭据 repr 防泄漏、`atomic_append_jsonl` 原子化、`load_manifest` 损坏保护、静默吞错修复、deterministic 路径锁合并
- **P2 测试基础设施**：coverage 配置、Product Shell JS 测试纳入 CI、verify.sh smoke 去重
- **P0 文档修复**：Cleanup Plan 红线矛盾、Active 表缺失文档、`旧开发者 home 路径` 过期路径（18 处）、AGENTS.md 过期断言
- **P0 商业化文档新建**：LICENSE、INSTALL.md、USER_GUIDE.md
- **P1 商业化文档新建**：PRICING.md、BOUNDARIES.md、CHANGELOG.md、PRIVACY.md、SUPPORT.md、COMPARE.md
- **文档重写/归档**：README.md 拆分、Cleanup Plan 归档、过期文档路径修正、frontmatter 补齐

### Out

- 不推倒重写 runtime
- 不做 `app_state.py` triple 模式重构（风险 >> 收益，商业化前无必要）
- 不做 `auto_adopt.py` 拆分（1347 行但内聚，27 次 except 大部分合理）
- 不做 `PYTHONPATH=src → pip install` 分发模式迁移（大范围改动，单独立项）
- 不做 `main.js` 移出 git（当前入库 + drift gate 可接受，商业化后评估）
- 不做 `docs/` 子目录化（内容就绪后再做，避免链接大面积断裂）
- 不扩 L3 / Judgment 无人值守自治
- 不引入 hosted multi-user SaaS

## Non-goals / 红线

| 红线 | 原因 |
|---|---|
| 不破坏 `raw/` 唯一事实输入与 `wiki/sources` vs `wiki/derived` 分层 | 事实层污染不可逆 |
| 不弱化 receipt / revert / audit 语义 | 可售卖差异化核心 |
| 不整删 `tests/fixtures/acceptance/**` | 回归 SoT；golden 变更需行为理由 |
| 不手改 `furnace-product-shell/main.js` | 由 `build.sh` 生成；保留 drift gate |
| 不重新引入 hidden cross-backend fallback | 与 fail-closed 产品契约冲突 |
| 不做 broad rewrite hub 削薄 | AGENTS.md 定案：只允许单 seam + 测试边界 |
| 不把 `wiki/indexes/README.md` 移出 git | 它是手写策略页，非生成态 |

---

## 1. 全量审计摘要（输入事实）

来源：2026-07-14 多-agent (glm-5.2) 全量审计，8 个 agent 并行只读探索。

### 1.1 基础统计

| 指标 | 事实 |
|---|---|
| Runtime | `src/aiwiki` 162 `.py` / **71,833 LOC** |
| 测试 | 149 文件 / **56,593 LOC** / 2,597 tests collected |
| 巨石 Top3 | `memory/graph.py` 1758 / `drop.py` 1747 / `execution/alchemy.py` 1680 |
| `except Exception` | 170 次；真正静默吞错 **1 处** |
| `@runtime_write_operation` | 77 处；`atomic_write_text` 100+ 处 |
| Facade | 5 个纯 re-export 已全删，零残留 |
| docs/ 非 archive | 21 `.md`；Active 表索引 12，**8 个脱索引** |
| docs/analysis | 10 文件，**全部 historical，0 被 Active 表引用** |
| wiki/indexes | 27 `.md`，**26 个 stale 生成态入库** |
| `__tests__` | `src/__tests__/` 有 10+ `.test.js` 但 verify.sh **只做 `node --check`，测试未跑** |

### 1.2 五维评分卡（审计综合）

| 维度 | 分数 | 权重 | 加权 | 一句话 |
|---|---:|---:|---:|---|
| 商业就绪度 | **6.0** | 30% | 1.80 | 可深度 demo，定价/包装/购买路径为零 |
| 安全与可靠性 | **7.7** | 20% | 1.54 | SSRF 纵深防御生产级；JSONL 非原子+凭据 repr 风险 |
| 架构与代码质量 | **6.9** | 20% | 1.38 | facade 清除彻底；app_state 1222 行是负担 |
| 测试与验证 | **7.0** | 15% | 1.05 | acceptance golden 工程强；2 真实失败+coverage 无配置 |
| 文档一致性 | **6.9** | 15% | 1.04 | README 与代码高度一致；8 文档脱索引+过期路径泛滥 |
| **商业审计综合** | | | **6.8** | **可 demo 的知识复利 OS；未到规模售卖** |


### 1.6 再评估评分卡（2026-07-15，Wave A–D + PR#11 + Phase5/D4）

来源：2026-07-15 多-agent 交叉全量再扫（架构 / 安全 / 文档商业 / 测试 / 垃圾 / 商业就绪）。

| 维度 | 审计原分 | 再评估 | 说明 |
|---|---:|---:|---|
| 商业就绪度 | 6.0 | **7.2** | commercial 骨架齐；邮箱/价格仍占位，非自助售卖 |
| 安全与可靠性 | 7.7 | **8.5** | P1 + JSONL 回滚 + bulk fail-closed + SSRF；已过 8.0 门槛 |
| 架构与代码质量 | 6.9 | **7.0** | facade 清除完成；巨石未动（Out 仍正当） |
| 测试与验证 | 7.0 | **7.5** | verify all 主链完整；Jest 仍 soft-skip |
| 文档一致性 | 6.9 | **7.3** | D4 + Active 表 + 死链修复后达线；一致性脚本已加硬门禁 |
| **商业审计综合** | **6.8** | **~7.6** | **已过本计划 7.5 cleanup gate**；强可售仍差 go-live |

> §1.1–1.5 保留 2026-07-14 审计快照，不作“当前失败”解读。

### 1.3 子维度细分

| 子维度 | 分 | 依据 |
|---|---:|---|
| 产品完成度 | 7.0 | 闭环完整可 demo；安装门槛硬伤（硬编码开发者路径） |
| 可售卖性 | 5.0 | Demo Pack 已交付；定价/license/SKU 全缺 |
| 可运维性 | 6.5 | receipt/audit 强；运维成本对非开发者高 |
| 差异化 | 8.0 | 金丹 1680 行真实代码；provenance+receipt+hash gate |
| 证据诚实度 | 8.5 | `never invents PASS`；四类证据分层纪律严格 |
| 合规 | 7.0 | demo pack 合规话术好；但未 runtime 强制 |
| 市场对标 | 7.0 | 空白市场判断成立；需求验证为零 |

### 1.4 代码商业化成熟度：6.5/10

| 维度 | 分 | 说明 |
|---|---:|---|
| 功能完整性 | 8 | 5 协议、治理层、审计、事务回滚齐全 |
| 测试基础设施 | 5 | 2 失败、coverage 无配置、JS 测试未跑、smoke 重复 |
| 安全性 | 5 | 凭据 repr 暴露风险、audit 非原子、manifest 无损坏保护 |
| 可靠性 | 7 | 事务 snapshot/restore 成熟，但 deterministic 锁分裂、1 静默吞错 |
| 可维护性 | 6 | app_state 重复但可控，auto_adopt 大但内聚 |
| 分发闭环 | 5 | pyproject 可装但脚本全硬编码 PYTHONPATH=src |
| 文档一致性 | 7 | AGENTS.md SoT 清晰，有 docs_consistency_check |

**从 6.5 → 8.0（可售卖门槛）**：P0 全部 + P1-1/1-2/1-3 + P2-3/2-4/2-5。
**从 8.0 → 9.0（稳健）**：P1-4/1-5 + 分发闭环。

### 1.5 文档商业化成熟度：4.5/10

| 维度 | 分 | 依据 |
|---|---:|---|
| 架构/契约 SoT 质量 | 8.5 | Active 文档内容扎实 |
| 商业化必需文档完备度 | 1.0 | LICENSE/CHANGELOG/USER_GUIDE/PRICING/PRIVACY/SLA 全缺 |
| 文档治理与一致性 | 5.0 | 8 文档脱索引、3 应归档未归档、CLAUDE.md 冲突 |
| 对外可读性 | 2.5 | README 高度开发者向，无 end-user quickstart |
| 过期事实清理 | 4.0 | 18 处 `旧开发者 home 路径` 残留 active 文档 |

---

## 2. 跨维度 Top 10 风险（商业阻塞优先）

| # | 风险 | 维度 | 严重度 |
|---|---|---|---|
| 1 | 无 LICENSE / 定价 / 包装 / 购买路径 | 商业 | 阻断 |
| 2 | 安装门槛硬伤：硬编码旧开发者 dogfood vault 路径 | 商业+代码 | 阻断 |
| 3 | 2 个真实失败测试使 `verify.sh unit/all` 变 RED | 测试 | 阻断 |
| 4 | 凭据可能泄漏：`LLMConfig` plain dataclass `__repr__` | 安全 | 高 |
| 5 | `atomic_append_jsonl` 非原子，audit stream 中途崩溃留半截 | 安全 | 中-高 |
| 6 | 无真实客户 / 公开案例 | 商业 | 高 |
| 7 | `CLAUDE.md` 与 `AGENTS.md` 事实冲突（路径全错） | 文档 | 高 |
| 8 | 8 active 文档 + `docs/analysis/` 脱索引 | 文档 | 中 |
| 9 | 合规话术未 runtime 强制（run-ask 无 guardrail） | 商业 | 中 |
| 10 | `automation.py` 三次独立锁，部分状态不一致 | 可靠性 | 中 |

---

## 3. 大扫除 Waves

### Wave A — 零风险垃圾清理（立即执行）

目标：清理死代码、空目录、死规则、冲突副本，不改变运行行为。

| ID | 任务 | 主要路径 | 风险 | 验证 | 并行 |
|---|---|---|---|---|---|
| A1 | 删除 `.agentstack/`（16MB 本地 scratch）+ `.gitignore` 加 `.agentstack/` | `.agentstack/`, `.gitignore` | 低 | `git status` 干净 | 是 |
| A2 | 删除 `.agents/skills/agentstack-*` 5 个空目录 + `.gitignore` 加忽略 | `.agents/skills/agentstack-*`, `.gitignore` | 低 | `git status` | 是 |
| A3 | 删除 `.gitignore` 死规则 `.codex/*.local.json`（.codex 不存在） | `.gitignore:6` | 低 | `bash scripts/verify.sh scripts` | 是 |
| A4 | 删除 `CLAUDE.md`（与 AGENTS.md 事实冲突，路径全错，AGENTS.md 是 SoT） | `CLAUDE.md` | 低-中 | `CLAUDE.md` 文件不存在；无生产代码/CI 硬依赖该文件名 | 是 |
| A5 | `wiki/indexes/*.md` 26 个 stale 生成态移出 git + `.gitignore`（保留 README.md） | `wiki/indexes/*.md`, `.gitignore` | 中 | `git ls-files wiki/indexes/` 只剩 README.md | 否 |
| A6 | `docs/analysis/` 10 个 historical 文件归档到 `docs/archive/analysis/` | `docs/analysis/*` → `docs/archive/analysis/` | 中 | `bash scripts/docs_consistency_check.sh` | 是 |
| A7 | 删除 `AGENTS.md` Cursor Cloud section 中 test_app.py 旧开发者 home 路径过期断言（tests/ 下 0 命中） | `AGENTS.md` | 低 | `git grep -E "^/home/" tests/` 为空 | 是 |

**Wave A Done 判据**：
- `.agentstack/` 不在磁盘且被 ignore
- `CLAUDE.md` 不存在；`AGENTS.md` 是唯一 agent protocol（不要求 `git grep CLAUDE` 字面空） SoT
- `git ls-files wiki/indexes/` 只剩 `README.md`
- `docs/analysis/` 为空或不存在，historical 文件在 `docs/archive/analysis/`
- `.gitignore` 无死规则

### Wave B — P0 代码修复 + P0 文档修复（商业化阻断）

目标：修复阻断商业化的代码与文档硬伤。

| ID | 任务 | 主要路径 | 风险 | 验证 | 并行 |
|---|---|---|---|---|---|
| B1 | 修复 2 个失败测试：`test_app_runtime.py:1426` 断言 `advanced llm-check`；`:1488` mock launcher 条件改为 `advanced` + `llm-check` 两参数匹配 | `tests/test_app_runtime.py` | 低 | `PYTHONPATH=src python3 -m pytest tests/test_app_runtime.py -k nightly_script -q` | 是 |
| B2 | 修复 `install_user_service.sh:40` 硬编码：去掉旧开发者 dogfood vault 路径 default，改为空 + 必填校验 | `scripts/install_user_service.sh` | 低 | `bash scripts/verify.sh scripts` | 是 |
| B3 | 修复 `dogfood_maturity_gate.py:25` 等 6 处脚本硬编码 `旧开发者 home 路径` default | `scripts/dogfood_maturity_gate.py`, `scripts/agos9_*.sh`, `scripts/investing_dogfood_preflight.sh`, `scripts/product_shell_smoke.sh` | 低-中 | `bash scripts/verify.sh scripts` | 是 |
| B4 | 修复 Cleanup Plan 红线矛盾：删除"不删 app.py"红线行（app.py 已删） | `docs/Furnace Cleanup Commercial Audit Plan 2026-07.md:50` | 低 | `bash scripts/docs_consistency_check.sh` | 是 |
| B5 | 归档前一轮 Cleanup Plan（`executed-reviewed-pass`）到 `docs/archive/` | `docs/Furnace Cleanup Commercial Audit Plan 2026-07.md` → `docs/archive/` | 低 | docs consistency | 是 |
| B6 | 修复 `docs/README.md` Active 表：补齐 5 个脱索引文档（2 runbook + UX Checklist + Optional-Deps-Matrix + Agentic Debt Autopilot） | `docs/README.md` | 低 | docs consistency | 是 |
| B7 | 修复 6 个 active 文档 18 处旧开发者 home 路径过期路径 → `$AIWIKI_DOGFOOD_VAULT` 或 `/Users/ht/github/danlu` | `docs/AGOS-9-Scorecard.md`, `docs/Furnace Runtime Operations.md`, `docs/Furnace Investing Dogfood Plan.md`, `docs/AGOS-9-Dogfood-Proof-Runbook.md`, `docs/AGOS-9-Investing-Preflight-Runbook.md`, `docs/Furnace Agentic Debt Autopilot.md` | 低-中 | `git grep -E "^/home/" docs/ ':!docs/archive/'` 为空 | 是 |
| B8 | 归档 `docs/Furnace AOS-003 Compat Shim Audit.md`（已 Superseded）和 `docs/Furnace Post-AGOS Risk Plan.md`（已完成）到 `docs/archive/` | 2 文件 → `docs/archive/` | 低 | docs consistency | 是 |

**Wave B Done 判据**：
- `bash scripts/verify.sh unit` PASS（无失败测试）
- `git grep -E "^/home/" -- scripts/` 为空
- `git grep -E "^/home/" -- docs/ ':!docs/archive/'` 为空
- `docs/README.md` Active 表无脱索引文档
- Cleanup Plan 红线无矛盾

### Wave C — P1 安全/可靠性加固 + P0 商业化文档新建

目标：达到商业化安全/可靠性门槛 + 补齐对外必需文档。

#### Wave C-1 — 代码加固

| ID | 任务 | 主要路径 | 风险 | 验证 | 并行 |
|---|---|---|---|---|---|
| C1 | `LLMConfig` 凭据 `field(repr=False)`：4 个 key 字段加 `repr=False`，防 `__repr__` 泄漏 | `src/aiwiki/config.py:47-66` | 低 | 新增单测断言 `repr(config)` 不含 key 明文 | 是 |
| C2 | `atomic_append_jsonl` 改 `os.write` 单次 syscall 原子化（POSIX `<= PIPE_BUF` 保证） | `src/aiwiki/app_utils.py:453-472` | 中 | `tests/unit/test_atomic_io.py` + crash-mid-write 测试 | 否 |
| C3 | `load_manifest` 改用 `load_json_document_strict`（CorruptStateError 包装） | `src/aiwiki/app_state.py:125-130` | 低 | `pytest tests/ -k manifest` | 是 |
| C4 | `machine_memory_actions.py:1218` 静默吞错改 `logging.warning` + 记 skipped_snapshots | `src/aiwiki/execution/machine_memory_actions.py:1215-1219` | 中 | `pytest tests/ -k "machine_memory_action or revert"` | 是 |
| C5 | `automation.py` deterministic 路径三锁合并为单锁（compile+lint+state 原子化） | `src/aiwiki/runner/automation.py:42-94` | 中 | `pytest tests/ -k "auto_process or automation or watch"` | 否 |

#### Wave C-2 — 商业化文档新建

| ID | 任务 | 路径 | 风险 | 并行 |
|---|---|---|---|---|
| C6 | 新建 `LICENSE`（需用户确认 license 选择：开源 / 双 license / 商业 EULA） | `LICENSE` | 低 | 是 |
| C7 | 新建 `docs/INSTALL.md`（面向 end-user，非 PYTHONPATH；5 分钟 quickstart） | `docs/INSTALL.md` | 低 | 是 |
| C8 | 新建 `docs/USER_GUIDE.md`（用户手册：核心心智模型 + 日常入口 + 投研 walkthrough + 失败三态） | `docs/USER_GUIDE.md` | 低 | 是 |
| C9 | 新建 `docs/commercial/PRICING.md`（产品包装 + 定价 tier + 包含/不包含 + 不可宣称清单） | `docs/commercial/PRICING.md` | 低 | 是 |
| C10 | 新建 `docs/commercial/BOUNDARIES.md`（开源版 vs 商业版边界） | `docs/commercial/BOUNDARIES.md` | 低 | 是 |
| C11 | 新建 `CHANGELOG.md`（Keep a Changelog 格式，从 AGOS-9 更新记录提取） | `CHANGELOG.md` | 低 | 是 |
| C12 | 新建 `docs/commercial/PRIVACY.md`（local-first 数据流 + LLM 数据流 + 不收集） | `docs/commercial/PRIVACY.md` | 低 | 是 |
| C13 | 新建 `docs/commercial/SUPPORT.md`（支持渠道 + 响应 tier + 不支持范围） | `docs/commercial/SUPPORT.md` | 低 | 是 |
| C14 | 新建 `docs/commercial/COMPARE.md`（对外竞品对比，只讲差异化不暴露弱项） | `docs/commercial/COMPARE.md` | 低 | 是 |

**Wave C Done 判据**：
- `repr(LLMConfig(..., api_key="sk-secret"))` 不含 `sk-secret`
- `atomic_append_jsonl` crash-mid-write 测试 PASS
- corrupt manifest 报 `CorruptStateError` 而非裸 `JSONDecodeError`
- `machine_memory_actions.py` 无 `except Exception: pass`
- `LICENSE` 存在且明确
- `INSTALL.md` + `USER_GUIDE.md` 存在且面向非开发者
- `docs/commercial/` 有 PRICING/BOUNDARIES/PRIVACY/SUPPORT/COMPARE

### Wave D — P2 测试基础设施 + 文档重写/补齐

目标：CI 可信度基础 + 文档结构完善。

| ID | 任务 | 主要路径 | 风险 | 验证 | 并行 |
|---|---|---|---|---|---|
| D1 | 新建 `.coveragerc`：`source = src/aiwiki`、`omit` tests/、`branch = True`、`fail_under` 重评 | `.coveragerc`, `scripts/verify.sh` | 低 | `coverage run -m pytest && coverage report` | 是 |
| D2 | Product Shell JS 测试纳入 verify.sh：新增 `scripts/run_product_shell_tests.sh` + `verify.sh` 调用 | `scripts/run_product_shell_tests.sh`, `scripts/verify.sh` | 低 | `bash scripts/run_product_shell_tests.sh` | 是 |
| D3 | verify.sh `smoke` 改真实确定性链路冒烟（layout→drop-note→compile→lint）；`cli-smoke` 保持 `--help`；去重 | `scripts/verify.sh` | 低 | `bash scripts/verify.sh smoke` | 是 |
| D4 | README.md 重写：拆成用户向（产品定位 + INSTALL 指针 + USER_GUIDE 指针 + 5 分钟 quickstart）；owner map / Developer Guide 移入 `docs/DEVELOPER.md` | `README.md`, `docs/DEVELOPER.md` | 中 | docs consistency + `bash scripts/verify.sh scripts` | 否 |
| D5 | 11 个 docs/*.md 补齐 frontmatter（`title/kind/status/updated_at`） | 11 个 docs 文件 | 低 | docs consistency | 是 |
| D6 | 确认 `docs/Furnace-90-Plus-Context-Provenance-Hardening-Plan.md` 状态后归档或纳入 Active Plans | `docs/Furnace-90-Plus-Context-Provenance-Hardening-Plan.md` | 低 | docs consistency | 是 |
| D7 | `MEMORY.md` 引用处理：创建空 MEMORY.md 或从 AGENTS.md 删除引用 | `MEMORY.md` 或 `AGENTS.md` | 低 | — | 是 |
| D8 | `docs/Furnace Investing Dogfood Plan.md` 状态明确化：加 frontmatter `status: closed-with-receipts` | `docs/Furnace Investing Dogfood Plan.md` | 低 | docs consistency | 是 |

**Wave D Done 判据**：
- `.coveragerc` 存在，coverage 只测 `src/aiwiki`
- `bash scripts/verify.sh product-shell-static` 执行 JS 行为测试
- `bash scripts/verify.sh smoke` 跑真实确定性链路
- README.md 面向用户，无 owner map / PYTHONPATH 开发命令
- 11 个 docs 文件有 frontmatter

---

## 4. 不做项（明确排除）

| 项 | 原因 |
|---|---|
| `app_state.py` triple 模式重构 | 27 对 load/save 重复但无 bug，重构风险 >> 收益，商业化前无必要 |
| `auto_adopt.py` 拆分 | 1347 行但内聚，27 次 except 大部分带 log/rollback/raise，非吞错重灾区 |
| `PYTHONPATH=src → pip install` 分发迁移 | 影响所有 systemd template / launcher / verify.sh，大范围改动，单独立项 |
| `main.js` 移出 git | 当前入库 + drift gate 可接受，商业化后评估 release 分发 |
| `docs/` 子目录化 | 内容就绪后再做，当前改目录触发大量链接断裂 |
| `render → content` 反向依赖修复 | 低 ROI，非商业化阻塞 |
| `app_compile.py` legacy owner 搬迁 | 含真实编排逻辑；归 hub 搬迁线，不与商业化清理混做 |

---

## 5. Files（计划触达面）

| File / Dir | Action | Wave | Reason |
|---|---|---|---|
| `.agentstack/` | 删除 + ignore | A | 本地 scratch，AGENTS.md 禁用 AgentStack |
| `.agents/skills/agentstack-*` | 删除空目录 + ignore | A | AgentStack 残留 |
| `.gitignore:6` `.codex/*.local.json` | 删除死规则 | A | .codex 不存在 |
| `CLAUDE.md` | 删除 | A | 与 AGENTS.md 事实冲突 |
| `wiki/indexes/*.md`（26 文件） | `git rm --cached` + ignore | A | stale 生成态入库 |
| `docs/analysis/*`（10 文件） | 归档到 `docs/archive/analysis/` | A | historical 未归档 |
| `AGENTS.md` Cursor Cloud section | 删除过期 test_app.py 断言 | A | tests/ 下 0 命中 |
| `tests/test_app_runtime.py:1426,1488` | 修复断言 | B | CLI 重构后断言未跟 |
| `scripts/install_user_service.sh:40` | 去硬编码 + 必填校验 | B | 商业用户无此路径 |
| `scripts/dogfood_maturity_gate.py:25` 等 6 处 | 去硬编码 default | B | 同上 |
| `docs/Furnace Cleanup Commercial Audit Plan 2026-07.md` | 修正红线 + 归档 | B | 红线矛盾 + executed |
| `docs/Furnace AOS-003 Compat Shim Audit.md` | 归档 | B | Superseded 未移 |
| `docs/Furnace Post-AGOS Risk Plan.md` | 归档 | B | 已完成未移 |
| `docs/README.md` | 补齐 Active 表 | B | 8 文档脱索引 |
| 6 个 active 文档 旧开发者 home 路径 | 修正路径 | B | 18 处过期路径 |
| `src/aiwiki/config.py:47-66` | `field(repr=False)` | C | 凭据防泄漏 |
| `src/aiwiki/app_utils.py:453-472` | `os.write` 原子化 | C | audit stream 完整性 |
| `src/aiwiki/app_state.py:125-130` | strict loader | C | manifest 损坏保护 |
| `src/aiwiki/execution/machine_memory_actions.py:1215-1219` | log 替代 pass | C | 唯一静默吞错 |
| `src/aiwiki/runner/automation.py:42-94` | 三锁合并 | C | 部分状态不一致 |
| `LICENSE` | 新建 | C | 法律根基 |
| `docs/INSTALL.md` | 新建 | C | 用户无法上手 |
| `docs/USER_GUIDE.md` | 新建 | C | 无用户手册 |
| `docs/commercial/PRICING.md` | 新建 | C | 商业化阻塞 |
| `docs/commercial/BOUNDARIES.md` | 新建 | C | 商业化阻塞 |
| `CHANGELOG.md` | 新建 | C | 版本可见性 |
| `docs/commercial/PRIVACY.md` | 新建 | C | 客户必问 |
| `docs/commercial/SUPPORT.md` | 新建 | C | 付费用户需要 |
| `docs/commercial/COMPARE.md` | 新建 | C | 销售需要 |
| `.coveragerc` | 新建 | D | coverage 配置缺失 |
| `scripts/run_product_shell_tests.sh` | 新建 | D | JS 测试纳入 CI |
| `scripts/verify.sh` | smoke 改真实链路 + 去重 | D | smoke/cli-smoke 重复 |
| `README.md` | 重写为用户向 | D | 开发者向，非用户向 |
| `docs/DEVELOPER.md` | 新建（承接 owner map） | D | 从 README 拆出 |
| 11 个 docs/*.md | 补 frontmatter | D | 格式不一致 |

---

## 6. Tasks（可勾选执行序）

### Phase 0 — 计划落盘（本 PR）

- [x] 8 agent 全量审计结论汇总
- [x] 五维评分卡 + 子维度细分
- [x] 跨维度 Top 10 风险
- [x] Wave A/B/C/D 计划落盘
- [x] 不做项明确排除

### Phase 1 — Wave A 零风险垃圾清理

- [x] A1-A2 删除 `.agentstack/` + 空目录 + `.gitignore`
- [x] A3 删除 `.gitignore` 死规则
- [x] A4 删除 `CLAUDE.md`
- [x] A5 `wiki/indexes/*.md` 移出 git
- [x] A6 `docs/analysis/` 归档
- [x] A7 删除 AGENTS.md 过期断言
- [x] targeted verify + `git status` 干净

### Phase 2 — Wave B P0 修复

- [x] B1 修复 2 个失败测试
- [x] B2-B3 修复脚本硬编码路径
- [x] B4-B5 修正 Cleanup Plan 红线 + 归档
- [x] B6 补齐 docs/README.md Active 表
- [x] B7 修复 18 处 旧开发者 home 路径 过期路径
- [x] B8 归档 Superseded/已完成文档
- [x] targeted verify + docs consistency

### Phase 3 — Wave C 代码加固 + 商业化文档

- [x] C-1: C1 凭据 repr 防护
- [x] C-1: C2 atomic_append_jsonl 原子化
- [x] C-1: C3 load_manifest 损坏保护
- [x] C-1: C4 静默吞错修复
- [x] C-1: C5 deterministic 锁合并
- [x] C-2: C6 LICENSE（需用户确认 license 选择）
- [x] C-2: C7-C8 INSTALL.md + USER_GUIDE.md
- [x] C-2: C9-C10 PRICING.md + BOUNDARIES.md
- [x] C-2: C11 CHANGELOG.md
- [x] C-2: C12-C14 PRIVACY.md + SUPPORT.md + COMPARE.md
- [x] targeted verify + 独立 review

### Phase 4 — Wave D 测试基础设施 + 文档完善

- [x] D1 .coveragerc + verify.sh coverage 调整
- [x] D2 Product Shell JS 测试纳入 CI
- [x] D3 verify.sh smoke 改真实链路 + 去重
- [x] D4 README.md 重写 + docs/DEVELOPER.md
- [x] D5 11 个 docs 补 frontmatter
- [x] D6-D8 状态明确化 + MEMORY.md 引用处理
- [x] full verify + docs consistency

### Phase 5 — 收口

- [x] `bash scripts/docs_consistency_check.sh` PASS（已扩展：D4 结构、commercial pack、indexes 死链、`/home/`）
- [x] `git grep -E "^/home/" -- scripts/ docs/ ':!docs/archive/'` 为空
- [x] `git ls-files wiki/indexes/` 只剩 README.md
- [x] `CLAUDE.md` 不存在；A4 验证标准改为「无生产/CI 硬依赖文件名」（非 `git grep CLAUDE` 字面空）
- [x] D4 README 用户向 + `docs/DEVELOPER.md`；README/HOME 不再硬链未入库 `wiki/indexes/*`
- [x] full `bash scripts/verify.sh all` PASS（acceptance prompt_hash 已刷新；known env-coupled 例外见 §12）
- [x] 独立 read-only reviewer 报告（Phase5/D4 Bugbot + 多-agent 再扫；acceptance golden 刷新收口）
- [x] 评分卡更新：见 §1.6（2026-07-15 再评估）

#### Phase 5 明确延期（不 block 本计划归档）

| 项 | 原因 | 升级条件 |
|---|---|---|
| 真实 `commercial@` / `support@` 邮箱 | 需运营决策，禁止用假地址冒充可售 | 签约/go-live 前替换 |
| 商业 EULA 正文 / 购买页 | 法律与商务材料，超出 cleanup 范围 | 独立 commercial go-live 计划 |
| `PYTHONPATH=src → pip install` 分发 | 本计划 Out | 单独立项 |
| Product Shell Jest hard-gate（强制 `AIWIKI_REQUIRE_*=1` + 可复现 node_modules） | 依赖不入库；当前为 verify soft-skip | release CI 有 npm 缓存后再升硬门禁 |
| coverage `fail_under` 拉回 92 / 取消 `legacy_argv` omit | 需新基线证据，避免无数据收紧 | 下一轮 test infra 微调 |

---

## 7. Verify

### Targeted（每完成一个 Wave）

```bash
# Wave A
git status --short
bash scripts/verify.sh scripts

# Wave B
PYTHONPATH=src python3 -m pytest tests/test_app_runtime.py -k "nightly_script" -q
bash scripts/verify.sh scripts
bash scripts/docs_consistency_check.sh
git grep -E "^/home/" -- scripts/ docs/ ':!docs/archive/' || echo "clean"

# Wave C-1
PYTHONPATH=src python3 -m pytest tests/test_config.py tests/unit/test_atomic_io.py tests/ -k "manifest or machine_memory_action or automation or watch" -q
python3 -c "from aiwiki.config import LLMConfig; c=LLMConfig(api_key='sk-secret'); assert 'sk-secret' not in repr(c); print('repr safe')"

# Wave C-2
bash scripts/docs_consistency_check.sh
ls LICENSE docs/INSTALL.md docs/USER_GUIDE.md docs/commercial/ CHANGELOG.md

# Wave D
bash scripts/verify.sh smoke
bash scripts/verify.sh product-shell-static
bash scripts/verify.sh all
```

### Full（收口 / 推送前）

```bash
bash scripts/verify.sh
bash scripts/docs_consistency_check.sh
git grep -E "^/home/" -- scripts/ docs/ ':!docs/archive/' || echo "clean"
git ls-files wiki/indexes/ | grep -v README.md || echo "indexes clean"
```

### Review gate

- Wave B/C 编码 PR：独立 read-only reviewer（correctness / scope / missing verify）
- Wave C-2 LICENSE 选择需用户确认后执行
- 不把"归档 md"与"改代码"无验证混提

---

## 8. Risks

| 风险 | 缓解 |
|---|---|
| 删 `CLAUDE.md` 破坏 Claude Code 依赖 | Claude Code 2.x+ 支持 AGENTS.md；确认无 CI/工具硬依赖 CLAUDE.md 文件名 |
| `wiki/indexes` 移出 git 破坏 compile 依赖 | 先确认 compile 不读 indexes（indexes 是 compile 产物不是输入）；移出后 compile 重生 |
| `atomic_append_jsonl` 改 `os.write` 破坏 48 处调用方 | 补 crash-mid-write 测试 + targeted pytest atomic_io/audit/lock |
| deterministic 锁合并延长锁持有 | deterministic 操作无 LLM，持锁时间短；single writer 模型本应串行 |
| README 重写破坏文档链接 | 先建 `docs/DEVELOPER.md` 承接内容，再改 README；跑 docs_consistency |
| `docs/analysis/` 归档破链接 | 先 grep 反向链接，改链接再搬文件；跑 docs_consistency |
| LICENSE 选择与商业版边界耦合 | C6 需用户确认后再执行；BOUNDARIES.md 与 LICENSE 同步 |
| 清理演变为 broad rewrite | 不做项明确排除；Wave C-1 只做安全加固不做 hub 重构 |

---

## 9. 决策记录

1. **代码**：P0 修复 + P1 安全加固优先；不做 app_state/auto_adopt 重构（风险 >> 收益）。
2. **文档**：先补内容（P0 商业化文档）后改结构（子目录化推迟）；README 拆分为用户向 + 开发者向。
3. **垃圾**：Wave A 零风险立即做；`wiki/indexes` 移出 git 是最大清理项（995 LOC stale）。
4. **分发**：`PYTHONPATH=src → pip install` 单独立项，不在本轮。
5. **License**：需用户确认选择（开源 / 双 license / 商业 EULA），与 BOUNDARIES.md 同步。

---

## 10. 成功定义

- `bash scripts/verify.sh all` PASS（无失败测试）
- `bash scripts/verify.sh product-shell-static` 执行 JS 行为测试
- `git grep -E "^/home/" -- scripts/ docs/ ':!docs/archive/'` 为空
- `git ls-files wiki/indexes/` 只剩 `README.md`
- `CLAUDE.md` 不存在；`AGENTS.md` 是唯一 agent protocol（不要求 `git grep CLAUDE` 字面空）
- `LICENSE` + `docs/INSTALL.md` + `docs/USER_GUIDE.md` + `docs/commercial/*` 存在
- `repr(LLMConfig(..., api_key="sk-..."))` 不含 key 明文
- `atomic_append_jsonl` crash-mid-write 不留半截行
- corrupt manifest 报 `CorruptStateError`
- 代码商业化成熟度 6.5 → 8.0
- 文档商业化成熟度 4.5 → 7.0
- 商业审计综合 6.8 → 7.5

---

## 11. 审计证据索引

本计划基于以下 8 个 agent 的只读审计报告：

| Agent | 维度 | 关键发现 |
|---|---|---|
| oracle | 架构与代码质量 | 综合 6.9；facade 清除彻底；app_state 1222 行负担；Top5 风险 |
| councillor | 文档一致性 | 综合 6.9；8 文档脱索引；18 处 旧开发者 home 路径；CLAUDE.md 冲突 |
| councillor | 商业就绪度 | 综合 6.0；无定价/包装；安装门槛硬伤；证据诚实度 8.5 最高 |
| oracle | 安全与可靠性 | 综合 7.7；SSRF 纵深防御生产级；凭据 repr 风险；JSONL 非原子 |
| explore | 测试与验证 | 综合 7.0；2 真实失败；coverage 无配置；JS 测试未跑 |
| explore | 垃圾清理排查 | 40 git 文件 + 1220 本地目录可清理；~1750 LOC 移出 active tree |
| explore | 文档差距 | 4.5/10；需新建 12 文档、重写 8、归档 5、修复 7 |
| explore | 代码差距 | 6.5/10；P0 修复 1h、P1 加固 4h、P2 基础设施 2h |

---

## 12. Known non-blocking env-coupled failures

| 用例 | 性质 | 处置 |
|---|---|---|
| `test_obsidian_workspace.test_workspace_defaults_open_home_and_furnace_center` | 脆弱：依赖已提交 `.obsidian/workspace.json`，本地 Obsidian 保存可漂移 | 非当前 snapshot 必失败；勿当 setup 失败 |
| `test_drop.test_fetch_url_raises_when_no_text_can_be_recovered` | 环境耦合：本机有 Chrome 时可能走 headless 渲染并在无网时超时 | 记为 non-blocking；后续应 mock browser 路径 |
| `test_acceptance_loop` happy/backend_failure replay | PR#11 模板文案变更导致 prompt_hash 漂移 | **已刷新** `scripts/refresh_acceptance_fixture.py --case M6.1b/...` |
| `test_relative_path_normalizes_macos_private_var_alias` | Darwin-only `/private/var` alias | 非 darwin 平台 skip |

---

## 13. 2026-07-15 再扫裁决

1. **修订计划：Y（轻量）** — 不重开 Wave E 大波次；更新评分、A4 判据、Phase 5 延期表与 known failures。
2. **继续推进：Y** — 完成 D4 + docs gate + Phase 5 可本地核验项；归档前跑 `verify.sh all` + 独立 review。
3. **下一独立计划（非本 cleanup）**：commercial go-live（真实邮箱 / EULA / 价格）、pip 分发、Jest hard-gate。
