# Knowledge Compounding Product Principles

**Date:** 2026-07-18  
**Status:** Approved (chat grill 2026-07-18; protocol cleanup = B; cut-list A/B/C evaluation added 2026-07-18)  
**Doc role:** Product principles + cut/keep scope + A/B/C 杂项采纳评估；**not** a byte-level implementation plan (follow with `writing-plans` before code).

## Goal

把炼丹炉收敛为 **知识复利** 系统：原料自动煅烧进 wiki，提问时由炉选型生成报告，人对稀缺的沉淀/凝丹建议一键确认；金丹是高杠杆复利节点与护城河场景，不是每条结论的必经关卡。

一句话主链：

```text
投料 →（自动）compile → 提问 →（炉选型）报告
              ↓ 稀缺建议
     人确认 file-back / 凝丹 → 下一炉默认吃到 → 复利
```

## Constraints

- 分层不变：`raw/ → wiki/ → output/`；`single writer, many readers`；stdlib-first。
- LLM 默认路由不变（本 spec 不改 backend/model）。
- 薄治理必留：provenance、失败诚实（无假成功）、关键晋升可回滚、receipt 可审计。
- Ask 自由 Markdown 报告契约已落地（见 `docs/specs/2026-07-18-freeform-ask-markdown-only.md`）；本 spec 不重开 format 辩论。
- **多协议：物理收敛为单一 runtime（选项 B）**——不是「藏 UI 留五套 schema」。
- 零兼容旧多协议切换：删除后 `protocol-set investing|research|product|ops` 必须失败或不再存在；不得 silent alias 到唯一协议。

## Design

### Product principles (grill lock)

| ID | 决议 |
|----|------|
| P1 | 本质用语：**知识复利**（不仅是「可复用」）。 |
| P2 | 成功标准：人能读资产 **且** 炉能在 ask 时 **默认引用** 相关 wiki/judgment/金丹；仅人能读不算护城河。 |
| P3 | **金丹** = judgment/decision 之上的可选浓缩层，用于跨多轮、需长期引用的主题；不是唯一终局户口。 |
| P4 | Ask **选型由炉决定**（machine-memory query + ranking）；用户日常无感。显式 `--corpus` / 手动挂载降为专家路径。 |
| P5 | 串题：接受偶发；靠更好 ranking + receipt 复盘；「忽略某资产」逃生舱后置，不挡主路径。 |
| P6 | 报告可全自动生成；**file-back / 凝丹 = 炉稀缺建议 + 人一键确认**。 |
| P7 | 建议触发：**稀缺规则**（如多轮同主题、衔接触已确认 judgment/金丹、冲突/可衔接）才出；展示在 Today / 报告卡，不每问弹窗。 |
| P8 | **默认 watch**：投料即确定性 compile（煅烧无感）。 |
| P9 | **多协议物理删除**：代码与 vault schema 只认 **一份** 协议 runtime；去掉五协议产品面与切换面。 |

### Architecture

```text
                    ┌──────────────┐
   drop / watch ───►│  compile     │──► wiki/sources + concepts
                    └──────────────┘
                           │
   ask / run-ask ──────────┤  furnace ranks:
                           │  sources + confirmed judgments + settled elixirs
                           ▼
                    output/reports/*.md  (+ used_refs in receipt/frontmatter)
                           │
              scarce suggest│
                           ▼
              human confirm ──► file-back (judgment) and/or alchemy distill→promote (elixir)
                           │
                           └──► next ask default-ranks them (compounding)
```

### Components

#### Keep (core)

- `drop`（url/pdf/image/repo/markdown）
- 确定性 `compile` + 默认 `watch`
- `ask` / `run-ask` / `run-ask-submit` / `run-ask-resume`（长报告后台仍属主链 UX）→ `output/reports/*.md`
- 薄 `file-back`（默认 judgment）+ 薄 `review-page`（确认/废弃）
- 金丹最小链路：`alchemy-start` / `alchemy-distill` / `alchemy-finalize` / `alchemy-promote`（+ `alchemy-revert` / `alchemy-demote` 薄层）
- Ask 自动 ranking / machine-memory query（**加强**，不是删）
- Product Shell：投料 + 提问 + Today（报告 + 稀缺「沉淀/凝丹」建议）
- Receipt / 失败诚实 / 可回滚晋升
- Desktop Obsidian 阅读面；`drop note` 投料语义；审阅备注字段 `note`
- `new-vault` / `sync-product-shell` / `llm-check` / 确定性 `lint`（运维最小集）

### Cut-list evaluation (A / B / C inventory)

评估对象：2026-07-18 第一性原理讨论中列出的「可删减杂项」A（整块可砍）/ B（可大幅瘦身）/ C（兼容与认知噪音）。  
评判尺子：P1–P9 + Keep(core)。  

| 裁决 | 含义 |
|------|------|
| **ADOPT** | 采纳删除/砍掉：原则允许且不伤主链；应进执行 plan |
| **THIN** | 采纳「削厚度」：保留最小能力，删掉矩阵/糖衣/重复面 |
| **KEEP** | **不采纳**删除：删了会伤复利主链或已锁定原则 |
| **OUT** | 非 runtime 产品能力（商业/史料/测试战役）；不纳入本产品砍削波，另处处理 |

推荐执行波（写入 plan 时用）：

| Wave | 主题 |
|------|------|
| **W1** | 协议物理单 runtime（P9-B）+ 依附多协议的 learnings / 文档 / fixture |
| **W2** | 复利选型加强 + `used_refs` + 稀缺沉淀/凝丹建议（P4–P7） |
| **W3** | 旁路治理整块删除（L3 / rewrite / repair / archive / signals…） |
| **W4** | 表面与兼容噪音（Shell Advanced、compat 双注册、HTML 控制台厂） |
| **W5** | 状态机/合同瘦身（review 三态、shell-summary、多视图合并） |

#### Tier A — 原先「整块可砍」逐项裁决

| # | 项 | 裁决 | 波 | 理由（对照原则） |
|---|-----|------|----|------------------|
| A1 | 五协议矩阵 + `protocol-set/status` | **ADOPT** | W1 | P9 已锁物理单 runtime |
| A2 | `protocol-learn-*` 全家桶 | **ADOPT** | W1 | 依附多协议偏置；保留会拖回五协议 |
| A3 | Alchemy **膨胀**（`alchemy` dry-run 宇宙、heavy/light lane、judge/propose preview、auto 调度） | **ADOPT** | W3 | 金丹最小四步保留（P3）；砍的是 AgentOS 炼丹操作系统 |
| A3b | 金丹最小链路 start/distill/finalize/promote(+revert/demote) | **KEEP** | — | P3 护城河；不可当杂项删 |
| A4 | L3 prompt/policy 提案 + apply/revert | **ADOPT** | W3 | 非复利主链；属自我修改 runtime |
| A5 | Concept rewrite 全链 | **ADOPT** | W3 | 不阻塞投料→报告→凝丹 |
| A6 | Concept retire/reactivate/review-concept | **ADOPT** | W3 | 生命周期覆盖过重；ranking 可后置简单过滤 |
| A7 | Machine-memory repair action 全链 | **ADOPT** | W3 | 修复矩阵 ≠ 复利；lint 报问题即可 |
| A8 | Archive 温度机 apply/revert-archive | **ADOPT** | W3 | 非主链 |
| A9 | Autonomy enable/disable/status | **ADOPT** | W4 | 运维开关；默认 watch（P8）用安装/文档约定即可 |
| A10 | `promote` / `demote` 候选层（相对 file-back） | **ADOPT** | W3 | 与「file-back judgment + 凝丹」重复；砍候选平面糖 |
| A11 | `report-subgraph` 一等入口 | **ADOPT** | W4 | 高级图玩具；非选型必需 |
| A12 | Mobile `vault-queue-drain` / companion | **ADOPT** | W4 | 非目标；Desktop-only |
| A13 | Investing Demo Pack 运营面 | **OUT** | — | 商业交付物，不进 runtime 砍削波 |
| A14 | `docs/commercial/*` | **OUT** | — | 商业触点 ≠ 炉芯功能 |
| A15 | `llm-telemetry` / `backend-telemetry` | **ADOPT** | W4 | 保留 `llm-check`；删浏览型遥测 CLI |
| A16 | signals / planner-log list/show/replay/rollback | **ADOPT** | W3 | AgentOS 运维面 |
| A17 | `audit-preview` / `audit-backfill` | **ADOPT** | W3 | 同上 |
| A18 | `cache` inspect/rebuild/drop | **ADOPT** | W4 | 实现细节；可留代码内隐式 cache，不暴露 CLI |
| A19 | `run-lint`（LLM semantic lint） | **ADOPT** | W3 | 保留确定性 `lint` |
| A20 | `today-snooze` | **ADOPT** | W4 | Today 糖；稀缺建议靠规则不靠 snooze |
| A21 | `batch-review` / `review-next` | **ADOPT** | W4 | 保留薄 `review-page` |
| A22 | 顶层 `metrics` | **ADOPT** | W4 | 非主链；需要时进 advanced 或删 |
| A23 | `dashboard` 合同 | **ADOPT** | W4 | 与 shell-status/Today 重叠 |
| A24 | `search` CLI | **ADOPT** | W4 | Obsidian 搜 + wiki 打开足够 |
| A25 | `trace` 证据树 | **KEEP** | — | 金丹 `derived_from` / 复利证明需要；可留 advanced |
| A26 | `sync-evidence-graph` | **ADOPT** | W4 | Graph 卫生命令，非复利 |
| A27 | legacy `ingest` | **ADOPT** | W4 | 已被 `drop` 覆盖 |
| A28 | 顶层 `drop-url/pdf/…` 双注册 | **ADOPT** | W4 | 只留 `drop …` |
| A29 | 独立 `layout` | **THIN** | W4 | 并入 `new-vault`，删独立入口 |
| A30 | Agent workbench / domain pilots / output packs 控制台 | **ADOPT** | W4 | 派生展示厂 |
| A31 | Execution Center / Execution Audit HTML 族 | **ADOPT** | W4 | 治理展示过剩 |
| A32 | Product Shell Advanced 命令海 | **THIN** | W4 | 抽屉可留极少专家项；默认藏 |
| A33 | `watch` | **KEEP** | — | P8 默认煅烧 |
| A33b | `auto-once` | **ADOPT** | W4 | 与 watch 重复 |
| A34 | Nightly **五层全开**（L2/L3/judgment auto-adopt） | **ADOPT** | W3 | 可留「可选 compile+lint」定时；砍自动 adopt |
| A34b | Nightly/定时确定性 compile+lint | **THIN** | W3 | 允许保留为 watch 补充，非 AgentOS |
| A35 | `run-ask-submit` / `run-ask-resume` | **KEEP** | — | 长报告无感生成需要；属主链 UX |
| A36 | machine-memory HTML 大图 + 索引页工厂 | **THIN** | W4/W5 | 留最小图/索引；砍批量遥测页 |
| A37 | Derived packs（decision-memos/sop-drafts 自动打包） | **ADOPT** | W3 | 非复利必需；judgment/金丹 md 即资产 |
| A38 | Protocol pilots / scorecard 舞台 | **ADOPT** | W1/W4 | 随多协议死 |
| A39 | `.aiwiki/derived/agents/*` 生成页 | **ADOPT** | W4 | 文档噪音 |
| A40 | Obsidian ignoreFilters / Graph 配色止血策略 | **OUT** | — | vault 卫生，非功能删项 |

#### Tier B — 原先「可大幅瘦身」逐项裁决

| # | 项 | 裁决 | 波 | 理由 |
|---|-----|------|----|------|
| B41 | Review 过细状态机 | **THIN** | W5 | 压成「待审 / 已确认 / 废弃」 |
| B42 | Aging / escalation / 自动产 repair 提案 | **ADOPT** | W3 | 自动提案厂；保留人读 lint 即可 |
| B43 | Planner / dry-run / execution-bundles 预览体系 | **ADOPT** | W3 | AgentOS 调度面 |
| B44 | 多 LLM backend 矩阵 | **THIN** | W5 | 产品锁单一默认；代码多后端可后置再删 |
| B45 | Protocol output guidance / learnings 注入 ask | **ADOPT** | W1 | 随协议收敛；自由 md 后更冗余 |
| B46 | File-back 三目标（derived/decision/judgment） | **THIN** | W5 | 默认只推 judgment；derived/decision 降级或删入口 |
| B47 | `run-compile`（LLM 摘要增强） | **ADOPT** | W3 | P8 要的是确定性煅烧 |
| B48 | Shell 多视图（Furnace/Review/Execution/Runs） | **THIN** | W5 | 收敛到「一页 Today + 必要打开」 |
| B49 | 巨型 `shell-summary.json` 合同 | **THIN** | W5 | 只保留 Today/报告/稀缺建议所需字段 |
| B50 | self-reach / 战役题库 | **OUT** | — | 工程验证手段，非产品功能 |

#### Tier C — 原先「兼容与认知噪音」逐项裁决

| # | 项 | 裁决 | 波 | 理由 |
|---|-----|------|----|------|
| C51 | `[compat]` 双入口 / argv rewrite 叙事 | **ADOPT** | W4 | 用户只见 `drop` / Today / ask 主路径 |
| C52 | 把 `docs/archive/**` 当现行能力 | **ADOPT**（文档） | W1/W4 | 史料保真；Active 文档去误读 |
| C53 | 已退役概念残留（六段报告、ask note format、run notes、wiki log 心智） | **ADOPT**（收尾） | W4 | 代码多已收敛；清 Active 文档与 UI 文案 |

#### Summary counts（采纳口径）

| 裁决 | 数量（约） | 含义 |
|------|------------|------|
| **ADOPT** | ~40 | 可进删除/砍削 plan |
| **THIN** | ~10 | 可进瘦身 plan，不是整文件消失 |
| **KEEP** | 5 | watch、金丹最小链、ask 后台、trace、ranking |
| **OUT** | 4 | 商业包、commercial 文档、ignoreFilters、战役题库 |

**明确不采纳删除的（KEEP）——防止误读「杂项清单」：**

1. 默认 `watch` + 确定性 `compile`  
2. 金丹最小晋升链与 settled 平面  
3. Ask 自动选型（应加强）与长报告 submit/resume  
4. `trace`（复利/金丹血缘）  
5. 薄 review + 稀缺「沉淀/凝丹」建议面（P6/P7 要建的是这个，不是删光治理）

#### Wave packing（把裁决映射到执行）

| Wave | ADOPT / THIN 打包 |
|------|-------------------|
| **W1** | A1 A2 A38* B45 C52(协议相关) + 单协议 fixture/文档 |
| **W2** | （建设项，非本表删除）ranking/`used_refs`/稀缺建议 UX |
| **W3** | A3膨胀 A4–A8 A10 A16 A17 A19 A34 A37 B42 B43 B47 |
| **W4** | A9 A11 A12 A15 A18 A20–A24 A26–A32 A33b A39 C51 C53 + A29/A32 THIN |
| **W5** | B41 B44 B46 B48 B49 + A36 THIN |

\*A38 随 W1 协议死；若有独立 pilots 代码可挂 W4。

### Data flow

1. **Ingest/compile：** watch 触发确定性 compile；用户不选手动「开炉」作为默认。
2. **Ask：** 炉从 wiki 排序截断上下文；receipt/`used_refs` 记录吃了什么；用户不选料。
3. **Suggest：** 仅当稀缺规则命中，写入 Today / 报告卡建议（file-back 和/或 凝丹）。
4. **Confirm：** 人一键执行；写 receipt；失败可 revert。
5. **Compound：** 已确认 judgment 与 settled 金丹进入后续 ask 默认候选池。

### Error handling

- 选型串题：不阻断成功报告；靠 receipt 复盘；不引入假成功。
- 晋升失败：候选不变、显式错误、可回滚；不得半写入 settled 金丹。
- 旧多协议命令/路径：删除后硬失败（非 0 / 明确错误），零 alias。

### Testing

- 单协议：acceptance fixtures 去掉多协议树；`protocol-set` 行为按删除后契约测。
- Ask：断言默认候选可含 settled elixir / confirmed judgment（在有数据时）；`used_refs` 或等价字段存在。
- Suggest：稀缺规则单测/acceptance；「每问必建议」不得成为默认。
- Watch→compile→ask 冒烟仍绿。
- `bash scripts/verify.sh all` 为协议收敛波最终门禁。

## Out of scope

- 本 spec **不直接改代码**；实施前须 `writing-plans` 按 **W1–W5** 拆波（见上表 Wave packing）。
- 不改默认 LLM backend/model。
- 不做 hosted / multi-user / 全功能 iOS。
- 不对 dogfood 历史多协议 frontmatter 做强制 bulk rewrite（可读时忽略未知 protocol 字段或规范化为唯一 slug——实现 plan 选定一种，须零 silent 跨协议行为）。
- 不把「串题否决逃生舱」纳入第一波。
- OUT 项（Demo Pack / commercial 文档 / ignoreFilters / 战役题库）不在本 runtime 砍削范围内。

## Open questions

(none — protocol cleanup = B；A/B/C 杂项采纳口径已写入 Cut-list evaluation)

## Grill trace

- 复用主语：C（人 + 炉）；用语改为知识复利  
- 金丹位置：B（可选浓缩）  
- 选型：炉决定；分析结论 = compile 复利 + query 自动选型 + receipt  
- 串题：A  
- 沉淀触发：B（建议+确认）  
- 建议时机：B 规则 + C 展示面  
- 煅烧：A（默认 watch）  
- 协议：B（物理单 runtime，可清理多协议）
