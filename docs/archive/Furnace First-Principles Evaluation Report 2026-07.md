---
title: "炼丹炉第一性原理评估报告 2026-07"
kind: "evaluation"
status: "active"
doc_role: "direction-context-not-execution-sot"
updated_at: 2026-07-15
related_docs:
  - docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md
  - docs/AGOS-9-Scorecard.md
  - docs/Furnace Agent Architecture.md
  - docs/commercial/COMPARE.md
  - docs/archive/Furnace Market Scan 2026Q2.md
  - PROGRESS.md
---

# 炼丹炉 / aiwiki — 第一性原理评估报告（2026-07-15）

> **角色**：方向上下文与交叉验证评估；**不是**当前执行 SoT。  
> **执行 SoT 仍是**：`docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` + `PROGRESS.md` + Scorecard。  
> **方法**：多 agent 全量扫描代码/文档 + 网络开源对标（含 Karpathy LLM Wiki 生态）+ 与仓库 SoT 交叉验证。

---

## 0. 结论先行

| 尺子 | 分/判 | 含义 |
|---|---|---|
| AgentOS 本地 release | **~9.05** | runtime / governance / Shell / docs 过 gate；**不能**对外说「商业可售 9 分」 |
| 商业可售 | **~7.6** | 过 cleanup gate；差 go-live 触点（邮箱/EULA/价格）与分发 |
| 品类定位 | **正确且稀缺** | 真正落地的「知识 compiler + 可审计治理」；不是 RAG 聊天壳 |
| 相对开源 LLM-Wiki 潮 | **工程深度领先，分发与入口落后** | 对手多是 prompt/plugin/编译器；炼丹炉是完整 single-writer runtime |
| 最优下一刀 | **不要再开 cleanup** | 执行 Commercial Go-Live WS1→WS2/WS3；技术上只做阻塞开售的最小缝 |

**一句话**：炼丹炉已经是「Karpathy LLM Wiki 模式」的重工业实现；当前最大价值在**分层 + 审计 + 确定性基线**，最大成本在**复杂度与商业触点真空**。最优解是**保住内核不变量、卖清边界、打通安装与询价**，而不是再拆 hub 或追 MCP/向量库潮。

---

## 1. 调研与交叉验证方法

### 1.1 多 agent 覆盖

| Agent | 范围 | 产出用途 |
|---|---|---|
| Explore A | SoT / PROGRESS / Post-Cleanup / Scorecard / 五层架构 | 现状与阶段事实 |
| Explore B | `src/aiwiki/` 162 模块、CLI、compile/LLM/protocol/Shell | 代码架构与债务热点 |
| Explore C | commercial pack / INSTALL / go-live D 项 | 商业与分发缺口 |
| 主 agent | 指标复核、竞品抓取、报告合成 | 否证与落盘 |

### 1.2 本机交叉验证（2026-07-15）

| 声称 | 验证结果 |
|---|---|
| `src/aiwiki` ≈ 162 `.py` / ~60–65k LOC | **162 文件 / 71600 LOC**（`wc -l`） |
| `dependencies = []` stdlib-first | `pyproject.toml` 确认 |
| 默认 `opencode-api` / `deepseek-v4-pro` | `config.py` 确认 |
| LLM 失败写 `llm-failed`，非假成功 | `workflows_ask.py` 多处 `delivery_mode=llm-failed` |
| acceptance ≈ 17 | **17 个 test_***；其中 **15** 个 `case_*` fixture + 2 个无 vault fixture 契约测 |
| 商务邮箱占位 | `commercial@example.com` / `support@example.com` 仍在 PRICING/SUPPORT/BOUNDARIES |
| 纯 facade 清除 | 已删；遗留 `app_*` 为**有逻辑的 hub**（符合 AGENTS 定案） |
| cleanup 收口 | Post-Cleanup + PROGRESS R13–R16；blocker = 无；下一波 Go-Live |

### 1.3 网络对标样本（2026-07）

| 项目 | 形态 | Stars 量级（公开页） | 与炼丹炉关系 |
|---|---|---|---|
| [Karpathy llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | 模式说明，非产品 | — | **思想原点**：raw / wiki / schema；ingest / query / lint / file-back |
| [atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler) | TS compiler + MCP + profiles | ~1.7k | 最近的「compiler」竞品；强在分发/MCP/导出，弱在治理深度 |
| [nvk/llm-wiki](https://github.com/nvk/llm-wiki) | Claude/Codex/OpenCode **技能包** | ~0.8k | 零依赖 agent 协议；无独立 deterministic runtime |
| [green-dalii/obsidian-llm-wiki](https://github.com/green-dalii/obsidian-llm-wiki) | Obsidian 插件 + PageRank 检索 | ~0.3k | 前端+图检索；弱 provenance/receipt |
| [kytmanov/obsidian-llm-wiki-local](https://github.com/kytmanov/obsidian-llm-wiki-local) | Ollama 本地 pipeline | ~0.8k | 本地优先；偏编译草稿，无 L3/金丹 |
| [xoai/sage-wiki](https://github.com/xoai/sage-wiki) | Go，分层 tier + compile-on-demand MCP | 活跃 | **规模化启发**：大库索引快、按需编译；与炼丹炉「全量 compile」哲学不同 |
| Reor / Khoj / Copilot / Smart Connections | 见 `COMPARE.md` + Market Scan | 更大社区 | RAG/聊天壳；非 compiler+治理 |

内部历史对标：`docs/archive/Furnace Market Scan 2026Q2.md`（Reor/Khoj/Letta 等）结论仍成立；**本轮新增**是 2026 春夏爆发的 Karpathy LLM-Wiki 实现潮。

---

## 2. 产品与现状（交叉验证后的事实）

### 2.1 是什么

- **炼丹炉**：面向投资研究 / 技术研发 / 高价值判断的 local-first **知识复利操作系统**。
- **aiwiki**：file-based runtime / CLI / 仓库实现内核。
- **主链路**：`raw → compile → wiki → ask → output → file-back → review / nightly`。
- **不是**：静态笔记库、一次性 RAG、hosted SaaS、多人同步、fine-tuning 平台。

### 2.2 五层（产品语言）与代码平面

| 产品层 | 落盘 | 硬约束 |
|---|---|---|
| raw | `raw/` | 唯一事实输入；派生层永不覆盖 |
| wiki | `wiki/sources|concepts|decisions|judgments|elixirs|…` | sources 与 derived 严格分层 |
| machine memory | `.aiwiki/state/*` + graph | 可自事实+历史重建；manifest/citation/sha256 |
| schema | `schema/` + `prompts/` | L3 proposal + human accept 才改核心契约 |
| outputs | `output/**` | candidates / proposals / reports / packs；带 receipt |

### 2.3 当前阶段

- Commercial Grade Cleanup：**executed-reviewed-pass**（已归档）。
- AgentOS ~9.05（本地 release）；商业 ~7.6。
- **无技术 blocker**；P0 是运营/法律触点（WS1）。
- 验证：`verify.sh all` ≈ 18–22s（scripts + product-shell-static + cli-smoke + smoke + python-static + acceptance）；**不再**跑 144 unit / coverage。
- Dogfood：3-day live PASS（历史）；**14/30-day natural proof = not-yet**（禁止伪造）。

### 2.4 代码形态快照

- Owner 拆分已落地：`content` / `compile` / `memory` / `execution` / `runner` / `cli` / `protocol` / `app_shell`…
- 复杂度集中区（单文件 >1.3k LOC）：`memory/graph.py`、`execution/alchemy.py`、`runner/workflows_ask.py`、`runner/auto_adopt.py` 等。
- 遗留 hub（评估时刻意未拆，2026-07-18 commit `145276a` 用户显式覆盖定案已下沉）：`app_state` / `app_utils` 已删除并下沉到 `utils/` + `state/` + owner 子包；`app_queries` / `app_lifecycle` / `app_routing` / `app_vault` 仍保留为 residual hub…

---

## 3. 第一性原理：问题空间与不变量

### 3.1 真正要解决的问题

从 Karpathy 模式与本仓库 Architecture 可压缩为四个不可约需求：

1. **复利**：知识要跨会话/跨周期沉淀，而不是每次 query 重新拼碎片（反 RAG-only）。
2. **真源**：原料不可被派生污染；结论必须可回溯到 `raw` / source page / hash。
3. **可纠错**：LLM 会错；系统必须 fail-closed、可审计、可回滚，而不是静默写成「看起来成功」。
4. **人机分工**：人管 sourcing / 判断 / 接受核心规则变更；机器管编译、交叉引用、bookkeeping。

### 3.2 炼丹炉已选择的解（且应继续守住）

| 不变量 | 为什么是第一性最优（在本品类内） |
|---|---|
| `raw/` 唯一输入 + 派生不覆盖 | 防止「第二大脑」变成不可信幻觉堆 |
| Deterministic baseline ⊕ 显式 LLM | 无 key 也能维护结构；LLM 是增值层不是生命线 |
| 显式 backend、无跨 backend 自动 fallback | 可复现、可归责；避免隐式路由污染证据 |
| Receipt + audit + revert + hash gate | 把 LLM 写入变成可治理事务，而非聊天副作用 |
| L3 proposal-only 改 schema/prompts | 核心规则变更必须人签；防自主权失控 |
| Desktop Obsidian Product Shell = 一输入一输出 | 降低认知负荷；运维进 Advanced |
| 非目标：SaaS / multi-user / heavy RAG / FT | 保护 local-first 与单人/小团队信任边界 |

### 3.3 第一性上**不必**追的潮流

| 潮流 | 为何不是本仓库最优解 |
|---|---|
| 向量库 + RAG 作为主路径 | 与「编译一次、复利使用」冲突；COMPARE/Architecture 已否决 heavy RAG |
| 把 runtime 缩成「AGENTS.md + Claude Code skill」 | 失去 deterministic baseline、receipt、CI 契约；变成不可测的提示词产品 |
| 默认 compile-on-demand（sage-wiki 风格） | 适合 10k–100k 文档库；炼丹炉当前 dogfood 规模与「判断资产」要求更适合**显式全量/增量 compile + nightly lint**；可作**远期可选策略**，不可替换主叙事 |
| 再开一轮 facade/hub 大拆 | Post-Cleanup 已定红线；ROI 低于 go-live |
| 用 AgentOS 9.05 营销成「可售 9 分」 | 尺子混标 = 信任破产 |

---

## 4. 开源对标：炼丹炉处在哪条曲线上

### 4.1 品类地图（2026）

```text
模式层: Karpathy LLM Wiki (gist)
    │
    ├─ 协议/技能层: nvk/llm-wiki, 各种 CLAUDE.md/AGENTS.md 实例化
    ├─ Obsidian 插件层: green-dalii, kytmanov, DyResearch 类
    ├─ Compiler/MCP 层: atomicstrata llm-wiki-compiler, xoai sage-wiki
    └─ Runtime/治理层: ★ 炼丹炉 / aiwiki
         （deterministic + receipt + protocol + elixir + Product Shell）
```

### 4.2 相对优势（相对 LLM-Wiki 潮与 COMPARE 对手）

1. **唯一把「compiler」做成可验证 runtime**：acceptance golden replay、strict corrupt state、single-writer lock——不是「让 agent 随便改 markdown」。
2. **治理深度断层领先**：L3 proposal apply/revert、execution receipts、kill switches、protocol multiplexing、金丹生命周期——开源同潮几乎没有等价物。
3. **Deterministic baseline**：关闭 LLM 仍能 `layout/drop/compile/ask骨架/lint/today`；多数竞品 LLM-off 即残废。
4. **产品面收敛**：`drop/today/metrics/advanced` + Shell 一输入一输出；比「命令森林」更接近可售形态。
5. **隐私叙事干净**：无 telemetry；egress 边界写进 PRIVACY；与 local-first 投资研究场景匹配。

### 4.3 相对劣势（应诚实承认）

1. **安装引力弱**：今天仍是 `git clone` + `PYTHONPATH=src`；`pip install aiwiki` 未闭环。竞品靠 `claude plugin install` / Obsidian Community / `npx` 获客。
2. **社区与心智占位落后**：Karpathy 潮的流量落在 plugin/compiler 名下；炼丹炉对外 COMPARE 仍以 Reor/Khoj 为主，**尚未把「重工业 LLM Wiki」讲清楚**。
3. **复杂度税高**：~72k LOC runtime + 大文件热点；新人/外部贡献者进入成本远高于 skill 包。
4. **检索规模路径未产品化**：index.md / machine-memory / Obsidian graph 够中小库；缺 sage-wiki 级 tiered index + 按需编译的**可选**扩展故事（不意味着要立刻做）。
5. **商业触点真空**：邮箱/EULA/价格占位 → 商业分被钉在 ~7.6。
6. **长期 live proof 缺口**：14/30-day dogfood not-yet；maturity 脚本已删，依赖 operator 手工记 PROGRESS。

### 4.4 可借鉴、但应**按边界吸收**的点

| 借鉴源 | 可吸收 | 吸收方式（最优） |
|---|---|---|
| nvk / Karpathy | 「AGENTS.md 即可上手」的叙事与 demo | 写清「最小体验路径」；**不**把 runtime 降级为纯技能包 |
| atomicstrata | MCP / OKF 导出 / profile | 仅在已有 vault 稳定后，作为 **agent 互操作出口**（非核心路径） |
| sage-wiki | tiered index + compile-on-demand 信号 | 仅当 vault 规模成为真实痛点时立项；默认仍全量 compile+lint |
| green-dalii | 零 embedding 图检索 | 可选增强；不替换 citation/machine-memory 主证据链 |
| Obsidian Web Clipper 生态 | 降低 raw 投喂摩擦 | 文档与 Demo 强调；不必自建 clipper |

---

## 5. 最有价值的优点（按「失去则品类坍塌」排序）

1. **事实/派生硬分层 + provenance**  
   没有这一条，产品退化为「会写笔记的聊天机器人」。这是对投资/研究场景的信任根基。

2. **Deterministic ⊕ 显式 LLM、fail-closed**  
   可复现、可离线维护、失败不伪装成功。相对「永远 online 的 agent wiki」是工程品类差异。

3. **Receipt / revert / L3 红线**  
   把自主权关进笼子。这是商业与专业场景敢用的前提；也是开源 LLM-Wiki 潮普遍缺失的护栏。

4. **Protocol + Elixir（跨周期判断资产）**  
   同一 substrate 多领域协议 + 金丹生命周期，超出「实体页/概念页」玩具 wiki。

5. **Product Shell 产品约束**  
   一输入一输出降低日常摩擦；Advanced 承载治理——比 CLI-only 或面板堆砌更接近可售。

6. **SoT 纪律与 cleanup 收口能力**  
   PROGRESS / Active Plans / archive / 分数不混标——降低多 agent 长期开发的自我污染。这是组织层优点，直接影响可持续性。

---

## 6. 最有价值的缺点（按「真实代价」排序）

1. **Go-live 触点缺失（P0）**  
   `@example.com`、无 EULA/价格 → 无法完成真实询价与许可。**商业价值损失最大，修复成本主要是运营/法律而非代码。**

2. **分发未闭环（P1）**  
   非开发者装不上 = 再强的 runtime 也进不了买家机器。相对 plugin-install 竞品是获客结构性劣势。

3. **复杂度 / 巨石模块（持续税）**  
   alchemy / auto_adopt / graph / workflows_ask 使演进与审查变贵；unit 网退休后回归粒度变粗——**正确的收缩，但提高了内部重构风险**。

4. **心智与对外叙事滞后于品类浪潮**  
   2026 市场已用「LLM Wiki」搜索；炼丹炉若仍只讲 vs Reor/Khoj，会错过「同模式重工业」定位红利。

5. **Jest soft-skip / 弱 JS 行为测 / 裸 write 残留**  
   verify 可绿但 UI 回归与原子写不完整——开售前的工程质量尾巴（WS5），不是品类方向错误。

6. **14/30-day natural dogfood 缺失**  
   不阻塞开售，但阻塞「长期复利已验证」的对外强声明。伪造比缺失更糟。

---

## 7. 最优解方案（建议）

### 7.1 战略层（第一性）

**保持品类定义不变**：  
「local-first 知识 compiler + 可审计治理」，不是「又一个 Obsidian AI 插件」或「又一个 MCP wiki」。

**双尺子永不混标**：AgentOS 证明工程；商业审计证明可售。开售门槛按 Post-Cleanup：商业综合诚实 ≥ **8.0**。

### 7.2 执行层（与 Post-Cleanup 对齐，不另起炉灶）

推荐顺序（与现计划一致，本报告仅加硬优先级理由）：

| 优先级 | Wave | 做什么 | 为什么是最优 |
|---|---|---|---|
| P0 | **WS1** | 真实邮箱、EULA/许可流程、价格或「仅询价」决策 | 不碰代码即可抬升商业分；否则一切 demo 无法成交 |
| P0/P1 | **WS2** | `pip install`（或诚实预览边界 + 一条非开发者路径） | 消灭「装不上」；对标竞品安装引力 |
| P1 | **WS3** | 脱敏截图/短录屏 + 合规 checklist | 把 Investing Demo Pack 变成可售资产 |
| 并行 | **WS4 残余** | SoT/文档卫生保持绿 | 低成本防自我污染 |
| 并行 | **WS5** | Jest hard-gate、原子写补洞、env 测隔离 | 开售工程质量底线 |
| 观测 | **WS6** | 14/30-day live dogfood | 不阻塞开售；有证据再升级声明 |

### 7.3 产品/技术层（可选增强，**有删除条件**）

仅在不破坏 §3.2 不变量时考虑：

1. **对外叙事补丁（低成本高杠杆）**  
   在 README / COMPARE / Demo 增加一节：「炼丹炉 = Karpathy LLM Wiki 的 production runtime（deterministic + receipt + protocols）」。  
   *删除条件*：若品类词退潮且转化无提升，缩回现有 COMPARE 口径。

2. **最小互操作出口（MCP read-only 或 export）**  
   让 Cursor/Claude 读 compiled wiki，而不是把 compile 主权交给外部 agent。  
   *删除条件*：若增加第二状态源或破坏 single-writer，立即撤回。

3. **规模策略预研（不做默认路径）**  
   文档化「何时需要 tiered index / compile-on-demand」的触发条件（例如 source 数、compile 时长）。  
   *删除条件*：dogfood 从未触及触发条件 → 不实现。

4. **Hub 搬迁**  
   维持「另线、有明确收益再做」；**禁止**与 go-live 捆做。

### 7.4 明确不做（红线复述）

- 不再开 Commercial Grade Cleanup 式全仓扫荡。  
- 不 SaaS / 全功能 iOS / Windows 一等公民（除非单独立项）。  
- 不扩 L3 无人值守改核心 prompt/policy/schema。  
- 不伪造 14/30-day dogfood PASS。  
- 不引入 AgentStack 或等价 scaffolding 回潮。

---

## 8. 评分口径建议（给决策者）

| 问题 | 诚实回答 |
|---|---|
| 能不能对内说「AgentOS 达标」？ | **能**（~9.05，证据分层需标注 historical/fixture/replay/live） |
| 能不能对外说「可售」？ | **还不能**（~7.6；WS1+WS2 是最短路径到 ≥8.0） |
| 要不要为追 LLM-Wiki stars 重写架构？ | **不要**；应借浪潮讲清定位，而不是把自己降级成 skill 包 |
| 最大杠杆在哪？ | **WS1 运营触点 + WS2 安装路径**；不是再重构 `app_state` |

---

## 9. 证据索引

| 主题 | 路径 |
|---|---|
| 当前执行计划 | `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` |
| 任务动态 | `PROGRESS.md` |
| 架构 / 契约 | `docs/Furnace Agent Architecture.md` · `docs/Furnace Evolution Mechanics.md` |
| 评分 | `docs/AGOS-9-Scorecard.md` |
| 对外竞品 | `docs/commercial/COMPARE.md` |
| 内部市场扫描 | `docs/archive/Furnace Market Scan 2026Q2.md` |
| 商业边界/隐私 | `docs/commercial/{PRICING,BOUNDARIES,PRIVACY,SUPPORT}.md` |
| 验证 | `bash scripts/verify.sh` · `tests/test_acceptance_loop.py` |
| 模式原点 | Karpathy gist `llm-wiki.md`（2026） |

---

## 10. 变更记录

- 2026-07-15：初版。多 agent 代码/文档全量扫描 + 开源 LLM-Wiki 生态网络调研 + SoT 交叉验证；结论对齐 Post-Cleanup Go-Live，不替代其执行地位。
