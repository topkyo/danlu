---
title: "炼丹炉大扫除 / 商业审计 / 全平台 Obsidian 移植计划"
kind: "plan"
status: "executed-reviewed-pass"
updated_at: 2026-07-14
supersedes:
  - "docs/archive/Furnace Next Direction Post-P4.md (direction context only)"
  - "docs/archive/Furnace Agent OS Slimdown Plan.md (campaign completed)"
  - "docs/archive/Furnace AgentOS Completion Plan.md (C1-C8 completed)"
  - "docs/archive/AGOS-9-Execution-Plan.md (execution history; scorecard remains SoT)"
based_on:
  - "2026-07-14 multi-agent full-repo scan (architecture / debt / garbage / commercial / mobile)"
---

# 炼丹炉 Cleanup + Commercial Audit + Obsidian 全平台计划（2026-07）

## Goal

1. **商业审计落盘**：基于全量代码扫描，明确可卖 / 不可卖 / 证据层级，避免把机制完备误读成可规模售卖。
2. **彻底扫清垃圾**：清理代码死路径、隐式兜底、文档 SoT 污染、生成态仓库膨胀；不局限“现有文件名”，按事实价值决定删 / 归档 / 移出 / 保留。
3. **收敛为 KISS**：无隐式兜底、无伪成功、无跨 backend 自动 failover；产品面保持 `drop/today`，operator 面不膨胀。
4. **回答全平台问题**：Product Shell 作为 Obsidian 插件，是否适合移植到 **Mac / iPad / iOS**；若否，给出可执行架构拆分。

本文件是**阶段性执行计划**，不是架构 SoT。完成后归档到 `docs/archive/`。

## Scope

### In

- 文档 SoT / Active 表修正与历史 plan 归档
- 代码隐式兜底与死 fallback 字段清理
- facade / CLI 兼容面受控削薄（分批，可验证）
- `wiki/indexes` 生成态、`PROGRESS.md` 切档、scripts 工具箱分层
- Product Shell desktop-only 边界固化 + 全平台 thin-client 路线图
- 商业评分卡、ICP、不可宣称清单、Demo Pack 定义

### Out

- 不推倒重写 runtime
- 不扩 L3 / Judgment 无人值守自治
- 不引入 hosted multi-user SaaS 作为本轮前提
- 不伪造 14/30-day natural proof
- 不直接把当前 Product Shell 标记为移动端可用
- 不做投资建议 / 行情 / 回测 / 自动交易能力

## Non-goals / 红线

| 红线 | 原因 |
|---|---|
| 不删 `src/aiwiki/app.py` shim | README / AOS-003 外部兼容承诺 |
| 不破坏 `raw/` 唯一事实输入与 `wiki/sources` vs `wiki/derived` 分层 | 事实层污染不可逆 |
| 不弱化 receipt / revert / audit 语义 | 可售卖差异化核心 |
| 不整删 `tests/fixtures/acceptance/**` | 回归 SoT；golden 变更需行为理由 |
| 不手改 `furnace-product-shell/main.js` | 由 `build.sh` 生成；保留 drift gate |
| 不重新引入 hidden cross-backend fallback | 与 fail-closed 产品契约冲突 |

---

## 1. 全量扫描摘要（输入事实）

来源：2026-07-14 多 agent 只读扫描 + 主进程定量交叉验证。

| 指标 | 事实 |
|---|---|
| Runtime | `src/aiwiki` ≈ 163 `.py` / **~72k LOC** |
| Tests | ≈ **61k LOC** |
| CLI | `add_parser` ≈ **108**；Primary 仅 `drop/today/metrics/advanced` |
| Top hubs | `drop.py` 1769 / `memory/graph.py` 1762 / `execution/alchemy.py` 1706 |
| `except Exception` | ≈ 169；真 `except Exception: pass` 极少（如 `machine_memory_actions.py`） |
| 架构评分（扫描） | 机制 8.5 / 结构 6.0 / KISS 5.0 / 综合 ≈ **6.8** |
| Product Shell | `manifest.isDesktopOnly=true`；依赖 `child_process.spawn` + `fs` + `electron` + launcher → Python CLI |

关键发现（必须进入清理）：

1. `runner/automation.py`：LLM compile/lint 失败后 **deterministic 继续**（隐式降级）。
2. `config.py`：`backend_fallback_*` 空字段 / 空函数残留。
3. 测试仍保护 `backend-failover` / 旧 `codex-cli` 成功路径语义。
4. `docs/README.md` Active 表仍把已完成 AGOS/AOS/Post-P4 当当前方向 SoT。
5. `wiki/indexes/` 生成态入库；`PROGRESS.md` 动态段过胖。
6. Product Shell **不能**直接跑在 iPad/iOS Obsidian。

---

## 2. 商业审计（代码现实口径）

### 2.1 一句话定位

> 炼丹炉是面向单人投资研究 / 技术研发的 **local-first 判断资产操作系统**：把原料编译成可追溯、可复审、可回滚、可跨周期复用的 judgment / elixir，而不是 RAG 问答器或投研数据终端。

### 2.2 证据层级（禁止混标）

| 层级 | 状态 | 可对外说法 |
|---|---|---|
| Fixture | 强（unit/acceptance/verify） | “机制可测、可回归” |
| Historical dogfood | 强（investing v0–v2.1；真中文 PDF） | “曾在真实材料上跑通闭环” |
| Live 3-day maturity | 历史 PASS 有记录；本仓库不能代替 dogfood vault 复算 | 仅在当前 vault 可复算时宣称 |
| 14/30-day natural run | **未完成** | 不得宣称 |
| 可售卖 Demo Pack | **缺失** | 不得假装已有公开案例 |

### 2.3 商业评分卡（2026-07）

| 维度 | 分 | 理由 |
|---|---:|---|
| 产品完成度 | 7.5 | 核心闭环与 Product Shell 可 demo；普通用户安装仍重 |
| 可售卖性 | 5.5 | ICP/价格/包装/公开案例不足 |
| 可运维性 | 6.5 | receipt/audit 强；本机 API key / vault / timer 支持成本高 |
| 差异化 | 8.0 | provenance + receipt + 金丹 vs Obsidian+AI / RAG |
| 风险可控 | 6.0 | 合规措辞、LLM 成本、移动端缺口 |
| **商业就绪** | **6.3** | **可深度 demo，未到规模售卖** |

### 2.4 可售卖

- local-first 投研 / 研发判断资产沉淀
- `raw → wiki → ask → output → file-back → review/nightly`
- 显式 LLM、失败可审计、apply/revert
- Obsidian Desktop Product Shell：一个输入端 + 一个输出端
- Investing protocol：thesis / catalyst / risk / invalidation 组织方式

### 2.5 不可售卖 / 不可宣称

- 投资建议、自动交易、组合优化、实时行情、回测
- hosted SaaS、多用户实时协作、企业权限中台
- “插件已支持 iPhone/iPad 全功能”
- “完全无人值守自改 prompt/policy”
- “14/30 天无人值守已证明”
- “LLM 失败会自动换后端保证成功”

### 2.6 ICP 与付费包装（建议）

**首发 ICP**：单人 / 小团队 fundamental researcher；痛点 = thesis drift、证据散落、AI 输出不可审计、跨季度复盘困难。

**付费点候选**（选 1 主打，勿全推）：

1. Desktop runtime license + Product Shell（工具）
2. Investing Demo Pack / 模板 vault（内容）
3. 安装与 dogfood 陪跑（服务）

### 2.7 商业优先动作（非技术洁癖）

1. **Investing Demo Pack**：脱敏 vault + 跨季度 thesis 故事 + 截图/receipt 链（10 分钟看懂复利）
2. **合规 onboarding**：非投资建议话术 + LLM 数据流说明 + 3 态失败（未配置 / 生成中 / 需处理）
3. **桌面安装收敛**：Mac/Linux 一键 vault + launcher + API key；不要先做移动端全功能

---

## 3. Obsidian 全平台移植评估

### 3.1 现状证据

| 证据 | 路径 |
|---|---|
| Desktop-only | `.obsidian/plugins/furnace-product-shell/manifest.json` → `isDesktopOnly: true` |
| Node spawn CLI | `src/bridge/launcher.js` → `spawn(launcherPath, args)` |
| Node fs/path + Electron | `main.js` header：`child_process` / `fs` / `path` / `electron` |
| Runtime 假设 | `scripts/aiwiki-launcher.sh` → `PYTHONPATH` + `python3 -m aiwiki.cli` |
| 常驻自动化 | systemd / launchd（桌面），移动端无等价 |

运行模型：

```text
Obsidian UI → Node spawn → aiwiki-launcher.sh → Python CLI → vault writes
```

这不是纯前端插件，而是 **桌面 runtime 控制台**。

### 3.2 平台矩阵

| 平台 | 结论 | 改动量 | 说明 |
|---|---|---|---|
| **Mac desktop Obsidian** | **适合（当前目标）** | 小–中 | 已有 launchd；需处理好 iCloud vault 权限与 launcher 路径 |
| **Windows/Linux desktop** | 适合（同模型） | 小–中 | Linux systemd 已有；Windows 需单独评估 launcher |
| **iPad Obsidian** | **不适合直接移植** | 高 | 无 Node/shell/Python；只能 thin client |
| **iOS Obsidian** | **不适合直接移植** | 很高 | 同 iPad，交互与文件选择更受限 |

### 3.3 为什么不能“把插件搬到 iPad 就能用”

移动端 Obsidian 插件环境缺少：

- `child_process.spawn` / 任意 shell
- Node `fs` 读写绝对路径并 exec
- Electron clipboard/shell
- 本机 Python runtime / launchd watcher
- 把拖拽文件绝对路径交给 CLI 的能力

即便 UI CSS 已有窄屏 media query，**阻塞点在 runtime bridge，不在排版**。

### 3.4 若要全平台：推荐架构（计划级，本轮不实现）

```text
                    +-------------------------+
                    |  Obsidian Plugin (all)  |
                    |  pure UI + vault adapter |
                    |  no spawn/fs/electron   |
                    +-----------+-------------+
                                |
                          RuntimeClient
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
 DesktopLauncherClient   VaultQueueClient      RemoteHttpClient
 (Mac/Linux now)         (mobile offline)      (optional later)
          |                     |                     |
          v                     v                     v
   aiwiki Python CLI      desktop/cloud         hosted/private
   local vault write      watcher drains queue  runtime API
```

**拆分原则：**

| 必须留在 desktop/cloud runtime | 可进纯插件（含移动端） |
|---|---|
| drop ingest / PDF / repo | Today feed / report 列表 UI |
| compile / run-ask / nightly / watch | 打开 vault 内 markdown |
| LLM 调用与凭据 | composer 文本输入（提交进 queue/API） |
| apply / revert / review 写操作 | pending 状态展示 |
| shell-summary 生成 | 只读 receipts / outputs |

**产品结论：**

- **现在**：只承诺 Desktop（优先 Mac）全功能。
- **移动端**：最多做“只读 + 投递请求”的 companion，不宣称炼丹炉在 iPad 本地炼化。
- **不要**为了移动端把 local-first 核心改成强制 SaaS；若做 RemoteHttp，必须是可选伴随 runtime。

### 3.5 全平台里程碑（独立于 Wave A/B）

- [x] **M-MOBILE-0**：文档与 README 明确 Desktop-only；设置页写清 iPad/iOS 不支持全功能
- [x] **M-MOBILE-1（design-done）**：`RuntimeClient` 三实现设计短文已落地；DesktopLauncher 仍是唯一全功能实现
- [ ] **M-MOBILE-2**：VaultQueue 协议（`.aiwiki/queue/*.json`）+ desktop watcher drain（可选）
- [ ] **M-MOBILE-3**：移动端 thin plugin（`isDesktopOnly: false` 或独立包）只读 summary + 提交 queue
- [ ] **M-MOBILE-4**：商业包装：Mac 主产品；iPad 为 companion，不单卖“全功能移动炼丹”

---

## 4. 大扫除 Waves

### Wave A — 低风险：清误导面与死兜底（优先执行）

目标：让新人 / agent / 客户不再被过期 SoT 和隐式降级误导。

| ID | 任务 | 主要路径 | 风险 | 验证 | 并行 |
|---|---|---|---|---|---|
| A1 | 修正 `docs/README.md` Active：Scorecard 进 Active；Post-P4 / AGOS Execution / AOS Completion / Slimdown 降级或移 archive | `docs/README.md`, `docs/archive/README.md` | 低 | `bash scripts/docs_consistency_check.sh`; `bash scripts/verify.sh scripts` | 是 |
| A2 | 归档已完成计划文件到 `docs/archive/`（或保留原地但改 status + 索引） | `AGOS-9-Execution-Plan.md`, `Furnace AgentOS Completion Plan.md`, `Furnace Agent OS Slimdown Plan.md`, `Furnace Next Direction Post-P4.md`, `deepseek-comprehensive-evaluation-*.md`, 可选 `Furnace Post-AGOS Risk Plan.md` | 低 | docs consistency + scripts | 是 |
| A3 | analysis 文档加 historical 标记；修正过期 LOC（如 `app_surfaces.py` 已 facade） | `docs/analysis/*` | 低 | scripts | 是 |
| A4 | `automation.py` LLM 失败改为 **fail-closed**（或仅在显式 `deterministic_only` 时 deterministic）；去掉“失败后假装继续成功” | `src/aiwiki/runner/automation.py`, 相关 tests | 中 | `pytest` automation/runner/watch 相关；`verify --target auto` | 否 |
| A5 | 删除 `backend_fallback_*` 死字段/空函数；同步 shell summary / preflight / tests | `config.py`, `preflight.py`, `app_shell/summary.py`, tests | 中 | `pytest tests/test_config.py tests/test_preflight.py tests/test_app_shell.py` | 否 |
| A6 | 清理跨 backend failover 测试保护；旧 backend fixture 改名为 stub/historical，避免伪装生产路径 | `tests/test_runner.py` 等 | 中 | runner/llm/preflight pytest + acceptance 抽样 | 否 |
| A7 | `PROGRESS.md` 切档：只留近期 active；旧 AGOS/C 段进 `archive/rounds/` | `PROGRESS.md`, `archive/rounds/*` | 中 | scripts | 否 |
| A8 | `wiki/indexes/` 策略：生成态不入 SoT；破链修复或改为 compile 产物 / fixture，不手写维护 | `wiki/indexes/*` | 中 | compile smoke 或明确移出 | 否 |
| A9 | AgentStack scaffold 已移除；文档与验证入口改回 canonical verify | `.agentstack/*`, `scripts/agentstack*`, docs | 低 | `bash scripts/verify.sh scripts` | 是 |
| A10 | Product Shell README / 商业文档写明 Desktop-only 与移动端非目标（本阶段） | Product Shell docs + 本计划 §3 | 低 | product-shell-static | 是 |

**Wave A Done 判据：**

- Active docs 无“已完成 plan 伪装当前方向”
- 无生产路径 LLM 失败后隐式 deterministic 伪成功
- 无 `AIWIKI_BACKEND_FALLBACK` 死 API 表面
- Desktop-only 对内对外口径一致

### Wave B — 中风险：兼容面削薄与仓库膨胀治理

| ID | 任务 | 说明 | 风险 | 验证 |
|---|---|---|---|---|
| B1 | facade 调用迁移：`app_content` / `app_memory_surfaces` / `app_render` / `app_surfaces` → owner 直引；保留必要 patch seam | 分批，禁止一次删光 | 中 | 对应 unit + compile/shell tests |
| B2 | CLI：停止双注册扩张；文档/help 只推 primary；legacy top-level 标 compat | 不删命令以免破 dogfood 脚本 | 中 | `tests/test_cli.py` |
| B3 | protocol SoT：明确 `protocol/*` = defaults，`schema/protocols/*` = vault override；加 drift check 或生成说明 | 防双源漂移 | 中 | protocol unit + docs |
| B4 | scripts 分层：canonical verify 保留；p0/p1/dogfood-watch/extract_rounds 等进 `scripts/archive/` 或 runbook | 降工具箱噪音 | 低 | scripts verify |
| B5 | acceptance golden 瘦身策略：shared base + 字段断言（不降关键审计覆盖） | 多轮 | 中 | `run_acceptance.sh` |
| B6 | `main.js` 策略决策：短期继续入库 + drift gate；中期改为 install/release 生成 | 记录决策即可 | 中 | product-shell-static |

**B6 decision**：短期继续把 Product Shell release bundle `main.js` 入库，原因是 Obsidian 实际加载路径需要可审查的 release artifact；`scripts/check_product_shell_bundle.sh` 作为 drift gate，确保 bundle 与 `src/` 构建输出一致。中期目标是把 `main.js` 改为 install/release 阶段生成并同步到 vault，源码仍以 Product Shell `src/` 为编辑面，只有发布产物进入目标 vault。

### Wave C — 高风险 / 长期：hub 削薄与商业证明

| ID | 任务 | 说明 | 风险 |
|---|---|---|---|
| C1 | `runner/alchemy.py` / `execution/alchemy.py` 按 seam 小切片 | **deferred**：本轮不做 hub broad rewrite；进入条件 = 单 seam + 有测试边界 + 非商业阻塞；禁止为 LOC 盲拆 | 高 |
| C2 | `drop.py` / `memory/graph.py` / `workflows_ask.py` 按 owner 拆 | **deferred**：只在单 owner seam 清晰、测试可锁边界、且不是商业证明阻塞时动；禁止为 LOC 盲拆 | 高 |
| C3 | Investing Demo Pack + 合规话术落地 | **done as spec**：见 `docs/Furnace Investing Demo Pack Spec.md`；规格即可，不伪造真实 demo vault 数据 | 中 |
| C4 | 14/30-day natural proof：只等真实 wall-clock | **not-yet**：只能等待真实 wall-clock；当前不得宣称 PASS | 高 |
| C5 | RuntimeClient + VaultQueue 移动端 companion（见 §3.5） | **partial**：M-MOBILE-0 done；M-MOBILE-1 design-done；M-MOBILE-2/3/4 未实现 | 高 |

---

## 5. Files（计划触达面）

| File | Action | Reason |
|---|---|---|
| `docs/Furnace Cleanup Commercial Audit Plan 2026-07.md` | **Add（本文件）** | 执行 SoT（阶段性） |
| `docs/README.md` | Update Active / Plans 索引 | 避免 SoT 误导 |
| `docs/Furnace Investing Demo Pack Spec.md` | Add | C3 Demo Pack 规格与合规话术 |
| `docs/Furnace RuntimeClient Mobile Companion Design.md` | Add | C5 / M-MOBILE-1 设计短文 |
| `docs/archive/README.md` | Update 归档表 + 替代指针 | 归档可导航 |
| `docs/archive/AGOS-9-Execution-Plan.md` 等已完成 plan | Archived / historical | 清文档垃圾 |
| `src/aiwiki/runner/automation.py` | Fix fail-closed | 清隐式兜底 |
| `src/aiwiki/config.py` (+ callers/tests) | Remove dead backend_fallback | 清死代码 |
| `tests/test_runner.py` 等 | Retarget fixtures | 防死路径复活 |
| `PROGRESS.md` / `archive/rounds/*` | Slim + archive | 清状态噪音 |
| `wiki/indexes/*` | Policy + cleanup | 清生成态污染 |
| `.obsidian/plugins/furnace-product-shell/manifest.json` + docs | Keep desktop-only; document | 全平台边界 |
| Product Shell `src/bridge/*`（未来） | Extract RuntimeClient | 移动端前置，不在 Wave A 强制 |

---

## 6. Tasks（可勾选执行序）

### Phase 0 — 计划与口径（本 PR）

- [x] 多 agent 全量扫描结论汇总
- [x] 商业审计评分卡与不可宣称清单
- [x] Obsidian Mac / iPad / iOS 可行性矩阵
- [x] Wave A/B/C 计划落盘
- [x] `docs/README.md` 挂上本计划（Active Plans）
- [x] `docs/archive/README.md` 预留归档入口说明

### Phase 1 — Wave A 执行（下一编码 PR）

- [x] A1–A3 文档归档与 Active 修正（Wave A docs-only slice：完成意图）
- [x] A4 automation fail-closed
- [x] A5–A6 死 fallback 与测试清理
- [x] A7–A9 AgentStack 移除；PROGRESS 切档 + wiki/indexes 策略
- [x] A10 Desktop-only 口径同步
- [x] targeted verify + 独立 review（verdict: pass，仅 minor 非阻断）

### Phase 2 — Wave B

- [x] facade / CLI / protocol drift / scripts 分层（facade 低风险批迁移；CLI primary/compat；protocol SoT；scripts/archive）
- [x] acceptance 瘦身策略试点文档（`docs/analysis/Acceptance-Golden-Slimdown-Strategy.md`；未大规模改 golden）
- [x] main.js 策略：短期入库 + drift gate；中期 install/release 生成

### Phase 3 — Wave C / 商业

- [x] Demo Pack 规格与最小素材清单（C3 spec-only）
- [x] hub 削薄 deferred 决策：不做 broad rewrite；只允许单 seam + 测试边界 + 非商业阻塞
- [x] RuntimeClient 设计短文 + M-MOBILE-1（design-done；未实现 mobile plugin）
- [x] 14/30-day natural proof 边界落盘（只能等真实 wall-clock；当前明确不得宣称 PASS）

### Residual after execution（非本计划阻断项）

- C1/C2 hub 削薄未实现；后续必须满足单 seam、测试边界、非商业阻塞三条件。
- C4 14/30-day natural proof 未完成；不能把本仓库 fixture、历史 dogfood 或 3-day 记录冒充长期 PASS。
- C3 只有 Demo Pack 规格；尚无真实脱敏 demo vault、截图或视频。
- C5 只有 Desktop-only 文案和 M-MOBILE-1 设计；M-MOBILE-2/3/4 仍未实现。
- facade 全量迁移未做完：保留 facade 文件与测试 patch seam；剩余 hub import 后续分批。

---

## 7. Verify

### AgentStack removal note

AgentStack 已从仓库移除；当前验证入口改为 `bash scripts/verify.sh [target]`。历史 `scripts/agentstack ...` 命令不再作为本计划 gate。

### Targeted（每完成一个 Wave A 切片）

```bash
bash scripts/docs_consistency_check.sh
bash scripts/verify.sh scripts
PYTHONPATH=src python3 -m pytest tests/test_config.py tests/test_preflight.py tests/test_runner.py -q -k "fallback or backend or automation or watch"
bash scripts/verify.sh product-shell-static
```

### Full（Wave A 收口 / 推送前）

```bash
bash scripts/verify.sh
bash scripts/docs_consistency_check.sh
# 若触及 dogfood 宣称：仅在真实 vault 上
# python3 scripts/dogfood_maturity_gate.py --root "$AIWIKI_DOGFOOD_VAULT" summarize --days 3
```

### Review gate

- Wave A/B 编码 PR：独立 read-only reviewer（correctness / scope / missing verify）
- 不把“归档 md”与“改 automation fail-closed”无验证混提

---

## 8. Risks

| 风险 | 缓解 |
|---|---|
| 删 docs 导致链接断裂 | 先改索引再搬文件；跑 docs_consistency |
| fail-closed 破坏依赖隐式降级的本地 watch 习惯 | 变更说明 + 显式 `deterministic_only`；release note |
| 删 backend_fallback 字段破 shell-summary 消费者 | 同步 Product Shell / summary schema tests |
| 把 wiki/indexes 当可删静态页 | 先确认 compile/tests 依赖，再移或重生 |
| 移动端预期管理失败 | README/商业文案锁定 Desktop-only；companion 另里程碑 |
| 清理演变为 broad rewrite | Wave C hub 必须单 seam + 测试；超 scope 停 |

---

## 9. 决策记录（建议默认）

1. **架构**：不重写；减 hub / 清兜底 / 定 SoT。
2. **商业**：先 Demo Pack + 合规 onboarding，再谈规模售卖。
3. **移动端**：**不做**当前插件直移植；Mac desktop 为主产品；iPad/iOS 仅未来 thin client。
4. **清理**：Wave A 两周内可落地；Wave B 分批；Wave C 不与 A 捆绑。

---

## 10. 成功定义

- 文档 Active 面只含真实现行 SoT + 本计划
- 生产路径无“LLM 失败 → deterministic 伪成功”
- 无跨 backend 自动 failover 死 API / 被测试保护的复活路径
- 对外口径：Desktop Obsidian 全功能；iPad/iOS 非全功能目标
- 商业口径：可 demo 的知识复利 OS；不可宣称投资建议 / 长期无人值守 / 移动全功能
