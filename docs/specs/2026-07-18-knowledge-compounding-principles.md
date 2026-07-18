# Knowledge Compounding Product Principles

**Date:** 2026-07-18  
**Status:** Approved (chat grill 2026-07-18; protocol cleanup = option B physical single-runtime)  
**Doc role:** Product principles + cut/keep scope; **not** a byte-level implementation plan (follow with `writing-plans` before code).

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
- `ask` / `run-ask`（及必要的 submit/resume）→ `output/reports/*.md`
- 薄 `file-back`（至少 judgment）+ 薄 `review-page`（确认/废弃即可起步）
- 金丹最小链路：`alchemy-start/distill/finalize/promote`（+ revert/demote 薄层）
- Product Shell：投料 + 提问 + Today（报告 + 稀缺「沉淀/凝丹」建议）
- Receipt / 失败诚实 / 可回滚晋升

#### Cut / delete (aligned with principles; execute in phased plans)

**Must in protocol-B wave（本 spec 锁定）：**

- 删除多协议库与切换：`schema/protocols/{investing,research,product,ops}/`（及索引中的多协议枚举）
- 代码只保留单一协议 runtime（可保留内部 slug 如 `general` 或改名 `default`，但 **无切换 API/UI**）
- 删除或废止：`protocol-set`、`protocol-status` 多协议列表、Shell 协议选择器、`PROTOCOL_LIBRARY` 多条目
- `protocol-learn-*` 全家桶（依赖多协议偏置的学习层一并评估删除；不得为「保留 learnings」而复活多协议）
- Acceptance / vault 模板中的多协议树收敛为单协议 fixture
- Active 文档去掉「五协议主线」叙事

**Should cut in follow-on waves（原则允许，另开 plan）：**

- L3 prompt/policy 提案宇宙、concept rewrite 全链、machine-memory repair action 全链、archive 温度机
- Autonomy kill-switch 套件、signals/planner-log replay、audit backfill、cache 运维 CLI
- Mobile vault-queue、report-subgraph 一等入口、metrics/dashboard 重复面、Agent workbench/pilots 展示厂
- Nightly 里自动 L2/L3/adopt（保留可选 compile+lint）
- 顶层 legacy `drop-*` 双注册与 `[compat]` 噪音（保留 `drop` 统一入口）

**Do not cut（误伤）：**

- 金丹 settled 平面与 `derived_from` 复利引用
- Ask 自动 ranking / machine-memory query（应加强，不是删）
- `drop note` 投料语义、审阅备注字段 `note`
- Desktop Obsidian 作为阅读面

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

- 本 spec **不直接改代码**；实施前须 `writing-plans` 拆波（至少：协议物理收敛波 / 复利选型+建议波 / 旁路治理砍削波）。
- 不改默认 LLM backend/model。
- 不做 hosted / multi-user / 全功能 iOS。
- 不对 dogfood 历史多协议 frontmatter 做强制 bulk rewrite（可读时忽略未知 protocol 字段或规范化为唯一 slug——实现 plan 选定一种，须零 silent 跨协议行为）。
- 不把「串题否决逃生舱」纳入第一波。

## Open questions

(none — protocol cleanup depth locked to B)

## Grill trace

- 复用主语：C（人 + 炉）；用语改为知识复利  
- 金丹位置：B（可选浓缩）  
- 选型：炉决定；分析结论 = compile 复利 + query 自动选型 + receipt  
- 串题：A  
- 沉淀触发：B（建议+确认）  
- 建议时机：B 规则 + C 展示面  
- 煅烧：A（默认 watch）  
- 协议：B（物理单 runtime，可清理多协议）
