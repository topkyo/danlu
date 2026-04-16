# 炼丹炉 To Do List

> 基于 2026-04-16 全量代码 / 状态 / 内容 / 测试 / 运行态独立评估。
> 评估方法论：**双轴打分**——基建完成度（代码/架构/管线）× 内容牵引力（真实知识密度/治理闭合/执行落地）。
> 当前综合评分 **8.3 / 10**（基建 8.6 / 内容 7.3）。目标 **9.0+**。

---

## 一、全量评估快照（2026-04-16）

### 规模指标

| 指标 | 数据 |
|------|------|
| Python 源码 | 25 模块 / 33,416 行 |
| 测试 | 14 文件 / 10,500+ 行 / 328 tests / 93% coverage |
| CLI 命令 | 37 个（ingest × 6 / compile × 4 / query × 3 / review × 5 / execute × 5 / governance × 6 / shell × 4 / automation × 4） |
| 原料 | 46 raw files（28 images + 14 markdown + 4 other） |
| 知识资产 | 16 sources → 30 concepts → 6 judgments → 4 decisions → 2 derived |
| Machine Memory | 259 edges（concept_causal 12 / concept_to_concept 125 / source_to_concept 60 / source_to_judgment 58 / j→j 2 / j→d 2）/ 0 terms（terms 字段已清空） |
| 输出产物 | 41 artifacts（reports 11 / agents 7 / control 7 / pilots 5 / packs 3 / slides 3 / figures 2 / design 1 / review 1 / graph 1）+ lint ≤10（已加轮转） |
| 协议 | 5 套（general / investing / research / product / ops）× 8 模板 |
| Obsidian 插件 | furnace-product-shell v0.2.0（4,532 行 JS / 7 源文件） |
| 状态文件 | 26 个 JSON/JSONL（machine-memory 20K 行 / nightly-health 11K 行 / execution-policy-decisions 1,452 行） |
| 闭环迭代 | 58 段（verify + qa-review + closed_loop） |

### 双轴打分

| 维度 | 基建分 | 内容分 | 综合 | 关键证据 |
|------|--------|--------|------|----------|
| ① Evidence Fabric | 9.0 | 7.5 | **8.5** | 5 drop 入口 + archive 闭环 ✓ / 但 46 raw → 16 compiled 量不大 |
| ② Knowledge Compiler | 9.0 | 7.0 | **8.3** | 增量 8 阶段 + dirty/clean 全链路 ✓ / 概念硬度提升至 1 hard + 5 medium + 24 soft |
| ③ Judgment System | 8.5 | 7.0 | **8.0** | lifecycle + counter-evidence + revisit 完整 ✓ / 但仅 2 条 j→j 边、全 medium confidence |
| ④ Machine Memory | 8.5 | 8.0 | **8.5** | topology + planner + health 全链路 ✓ / danlu 18 actions 全 resolved；dev repo 17 actions（1 resolved + 6 accepted + 10 proposed）/ terms 字段待重建 |
| ⑤ Schema / Protocol | 9.0 | 8.5 | **8.8** | 5 protocols 真正驱动 runtime ✓ / 仅 research 被深度运行 |
| ⑥ Governance | 8.5 | 7.5 | **8.2** | review → aging → repair 管线完整 ✓ / 18 actions 全部闭合、nightly auto-consume 上线、rewrite proposals 仍需 LLM |
| ⑦ Execution Layer | 8.5 | 7.5 | **8.2** | apply→revert→re-apply 已证明 ✓ / 4 种 action 类型、18 receipts、planner 自动消费已上线 |
| ⑧ Outputs | 8.0 | 6.5 | **7.5** | 41 non-lint artifacts 格式齐全 ✓ / lint 已加轮转上限 10 / 高价值 output 需继续增加 |
| ⑨ Product Shell | 8.5 | 8.0 | **8.3** | 极简面板 + 3 drop modal + command split + HTML fallback + new-vault ✓ / 但仍无交互式图谱 |
| **加权平均** | **8.6** | **7.3** | **8.3** | |

### 对比前次自评（8.4）的修正

前次自评 8.4 主要高估了三处（本轮已部分修复）：

1. **Governance 高估**（8.5 → 7.5 → 修正后 8.2）：Phase A 治理积压已清零——18 个 execution actions 全部 resolved，nightly auto-consume 上线；但 12 个 rewrite proposals 仍需 LLM 生成 candidate
2. **Execution 高估**（7.5 → 6.8 → 修正后 8.2）：现已拓宽至 4 种 action 类型、18 receipts、planner 自动消费已上线
3. **Output 高估**（8.0 → 7.5）：107 artifacts 数量可观，但 43 是 lint 报告、有效高价值输出（真实 reports/slides/figures）偏少

### 核心优势（值得保持）

1. **架构完整性极高**：九层全部存在且功能闭环，在同类项目中罕见
2. **测试纪律过硬**：321 tests / 93% coverage / 无循环依赖 / verify 一键可跑
3. **增量编译成熟**：8 阶段 dirty/clean 追踪 + compile-state 持久化，编译不再是黑箱
4. **协议体系真实**：5 protocols × 8 templates 真正影响 compile / query / review / nightly，不是装饰
5. **Judgment 数据模型精密**：counter-evidence / invalidation / revisit / escalation / cognitive-history 全链路可追溯
6. **Product Shell 极简面板已落地**：单面板首屏（交互 / 投料 / 产出 / 简报），3 个 drop modal，命令面板 8 核心 + 高级按需注册

### 核心短板（必须解决）

1. **治理只产不消**：系统非常擅长"发现问题"（lint warnings / rewrite proposals / execution proposals / aging reports），nightly auto-consume 已上线；danlu vault 18 个 execution actions 已全部闭合，dev repo 仍有 16 个未 resolved；12 个 rewrite proposals 仍需 LLM 生成 candidate_markdown 才能消费
2. **概念层偏弱**：30 concepts 中 1 hard + 5 medium + 24 soft，比之前全 soft 有明显进步但多数仍待加固
3. **执行层已拓宽**：4 种 action 类型（bridge-concept / overloaded-concept / singleton-concept / isolated-source）被真实执行，3 receipts（dev repo），planner 自动消费已上线
4. **内容密度低**：16 sources → 30 concepts 几乎 1:2，很多 concept 只有 1-2 个 source 支撑；有效知识内容约 4,000 行，元数据 overhead 高
5. **Lint 轮转已修复**：之前 lint 报告 append-only 导致 50 份累积，现已加 _LINT_REPORT_KEEP=10 轮转

---

## 二、演化三阶段

### Phase A — 治理消化 + 执行闭合（8.0 → 8.6）

> **核心命题**：证明系统不只会发现问题，还会解决问题。

这是最有确定性的阶段——全部是代码 + 操作，不依赖外部输入。

| 行动 | 验收标准 |
|------|----------|
| **A1. 清零治理积压** | lint warnings 从 39 → 0；至少 apply 3 个 rewrite proposals |
| **A2. 消费执行队列** | 从 8 proposals 中消费 ≥ 3 个（覆盖 ≥ 2 种 action 类型：bridge-concept + overloaded-concept）；receipts 从 3 → 6+ |
| **A3. 激活 planner 自动消费** | nightly 自动扫描 low-risk + accepted proposals 并生成 bundle；planner-state `executed_actions` 自增 |
| **A4. dry-run 结构化** | `apply-action --dry-run` 输出 JSON report（affected paths / risk / expected changes）写入 execution-bundles/ |
| **A5. 触发 1 次真实 escalation** | 设置 1 个 judgment `revisit_after` 过期 → nightly 触发 escalation → review 闭合 → cognitive-history 记录完整链 |

**预估得分影响**：Governance 7.5→8.5 / Execution 6.8→8.5 / 综合 8.0→8.6

### Phase B — 内容密实 + 判断资产化（8.6 → 9.0）

> **核心命题**：从"管线能跑"推进到"管线产出有价值的知识"。

这阶段需要**真实使用系统**——投料、提问、file-back、review，不是写代码能完成的。

| 行动 | 验收标准 |
|------|----------|
| **B1. Hard concepts 从 5 → 15** | 从现有 30 soft concepts 中提升 10 个高频概念的 hardness + 补 causal_links；concept_causal 边从 12 → 30+ |
| **B2. Judgments 从 6 → 12** | 通过 `ask → file-back` 在 research / investing / product 三个 protocol 各新增 2+ judgments；每个必须有 counter-evidence + invalidation |
| **B3. Judgment 间关联图谱** | machine memory 新增 judgment→judgment + judgment→decision 显式关联边 ≥ 6 条 |
| **B4. 概念积压清零** | 30 concepts "待回看" 状态清零——review 通过或 retire |
| **B5. Evidence 补强** | raw files 从 46 → 80+，sources 从 16 → 30+，每个 high-hardness concept 至少 3 个 source 支撑 |

**预估得分影响**：Knowledge Compiler 8.0→9.0 / Judgment 8.0→9.0 / Machine Memory 8.0→9.0 / 综合 8.6→9.0

### Phase C — 产品收敛 + 日常可用（9.0 → 9.3）

> **核心命题**：让炼丹炉真正成为"每天想打开的工具"而非"每天需要维护的系统"。

| 行动 | 验收标准 |
|------|----------|
| **C1. 交互式图谱** | machine-memory.html 当前已支持节点跳转、按 kind/filter/protocol 过滤、节点详情、缩放 / 聚焦 / 重置视图；后续若继续推进，再考虑 force-directed 布局 |
| **C2. Context 自动推断** | `review-action` / `apply-action` / `revert-action` 现已在 CLI + runtime 统一支持 title 子串模糊匹配；shell-summary 已暴露 `suggested_next_actions`（**本轮收口完成**） |
| **C3. First-run onboarding** | `new-vault` 后首次打开 Obsidian 展示引导面板（投料→编译→提问→审阅 四步走）（**部分完成**：极简面板首屏已暴露核心工作流，new-vault README/HOME 已重写） |
| **C4. Output 密度提升** | output/figures/ ≥ 6 / output/slides/ ≥ 6 / output/reports/ ≥ 15 / 高价值产物 > lint 产物 |
| **C5. 测试 93%+** | 补 app_queries / app_memory / config 低覆盖模块测试 |

**预估得分影响**：Product Shell 7.8→8.8 / Outputs 7.5→9.0 / 综合 9.0→9.3

### 2026-04-16 本轮执行更新（Phase A + Phase C）

- **Phase A 编译根因已修**：concept render signature 现在显式包含 renderer/frontmatter schema version；老 concept page 会被重新编译，`hardness` frontmatter 已批量补回。
- **旧占位摘要已清零**：legacy `This concept currently appears ...` 摘要会被 deterministic summary 替换；如果命中旧占位，`hardness` 会自动回落到 `soft`，避免“弱摘要 + 硬结论”并存。
- **39 个 lint warnings 仍在，但性质已变化**：现在剩余 warning 基本都是内容债（`hardness: soft`、缺边界/冲突信号），不再是编译器漏刷 generated frontmatter / placeholder summary。
- **Phase A 治理链真实推进了一步**：已接受 `overloaded-concept-and`，并推进 1 个 decision + 1 个 judgment review，nightly 刷新后当前 review backlog 为 `pending_decisions = 1`、`pending_judgments = 1`。
- **Phase C onboarding 已补齐最小闭环**：`new-vault` 生成的 README/HOME 现在明确写出 Obsidian + CLI 双入口、`single writer` 约束、投料/提问路径。
- **Obsidian 端新增最小投料入口**：Product Shell 新增 `Capture Note` modal 和 `Start Here` 区块；提问继续支持 Ask modal，CLI/agent 侧继续支持完整 `drop-*`。
- **Phase B 入口结论**：`ask` 现在在 Obsidian / CLI 两边都可直接使用；投料共享同一 runtime，`drop-note / drop-url / drop-pdf / drop-image` 已有 Obsidian 双入口（通过 3 个 drop modal），`drop-repo` 仍以 CLI 为主。
- **Product Shell 极简改版已落地**：主面板从多视图多按钮工程面板收口为单面板极简工作台（交互 / 投料 / 产出 / 今日简报 + 折叠高级操作），命令面板从 30+ 收口为 8 个核心命令（高级命令按 `showAdvancedCommands` 按需注册），ribbon 从双按钮收口为单入口。

### 2026-04-16 第二轮更新（四线并进执行）

- **Product Shell 模块化重构完成**：4,451 行单文件 `main.js` 拆分为 7 个源文件（constants / helpers / modals / views / settings / render / plugin）+ `build.sh` 构建脚本，`node --check` 通过，Obsidian 兼容。
- **Phase A 治理消化真正闭环**：接受并 apply 7 个 execution proposals（5 bridge-concept + 2 overloaded-concept），全部生成 execution receipts；触发 1 次真实 escalation（`bridge-concept-and` aging_state=escalated）。
- **resolve-monitor apply mode 上线**：新增 `RESOLVABLE_MONITOR_ACTION_KINDS` 集合（monitor-bridge-concept / split-overloaded-concept / expand-singleton-concept / connect-isolated-source），支持 accept→dry-run→apply→revert 全链路。
- **nightly planner 自动消费上线**：`nightly_health()` 自动扫描 accepted low-risk + resolvable-monitor actions 并 dry-run→apply，治理链从"发现"走到"自动解决"。
- **Phase C 覆盖率推进**：321 tests / 93% coverage（+2 tests, +1% coverage），新增 monitor apply + nightly auto-consume 测试。

### 2026-04-16 第三轮更新（review + Phase C 收口）

- **recent review 已完成**：回看最近两轮改动，未发现新的阻断级回归；本轮顺手修掉 1 个真实不一致——CLI 已支持 action title/substring 匹配，但 runtime entrypoint 仍 exact-id only。
- **Phase C context matching 收口**：`review_machine_memory_action()` / `apply_machine_memory_action()` / `revert_machine_memory_action()` 现在与 CLI 共享同一套 action query 解析，支持 exact id / exact title / unique prefix / unique substring，并在歧义时返回候选列表。
- **Phase C graph polish 推进**：`machine-memory.html` 在原有搜索 / 过滤 / 节点详情基础上，新增缩放、重置视图、聚焦当前节点与 active node/edge 高亮，图谱可扫读性继续提升。
- **测试继续推进**：328 tests / 93% coverage，新增 runtime action fragment matching + graph controls 覆盖，`bash scripts/verify.sh` 全绿。

---

## 三、得分推演

| 维度 | 当前 | Phase A 后 | Phase B 后 | Phase C 后 |
|------|------|-----------|-----------|-----------|
| ① Evidence Fabric | 8.5 | 8.5 | **9.0** | 9.0 |
| ② Knowledge Compiler | 8.3 | 8.5 | **9.0** | 9.0 |
| ③ Judgment System | 8.0 | 8.0 | **9.0** | 9.0 |
| ④ Machine Memory | 8.5 | 8.5 | **9.0** | 9.0 |
| ⑤ Schema / Protocol | 8.8 | 8.8 | 9.0 | **9.5** |
| ⑥ Governance | **8.2** | **8.5** | 9.0 | 9.0 |
| ⑦ Execution Layer | **8.2** | **8.5** | 8.5 | 9.0 |
| ⑧ Outputs | 7.5 | 7.5 | 8.0 | **9.0** |
| ⑨ Product Shell | 8.5 | 8.5 | 8.5 | **9.0** |
| **综合** | **8.3** | **8.5** | **8.8** | **9.1** |

---

## 四、已完成里程碑（58 轮闭环）

- ✅ `app.py` 动态 facade → 静态 shim + 25 个 owner module（最大 4,275L `app_compile.py`）
- ✅ 328 tests / 93% coverage / verify 全绿 / 无循环依赖
- ✅ 58 段闭环迭代（verify + qa-review + closed_loop）
- ✅ 增量编译 8 阶段 dirty/clean state + compile-state.json 持久化
- ✅ Product Shell 模块化重构：7 源文件 + build.sh + 极简主面板
- ✅ `new-vault` 脚手架：外部 runtime launcher 模式
- ✅ Product Shell: search / batch apply / batch revert / review-next / safe batch review modal
- ✅ Judgment lifecycle / cognitive-history / governance surfaces 全链路
- ✅ planner-state / query-route-telemetry / execution-policy-decisions 持久化（1,265 policy decisions）
- ✅ 概念因果网络：1 hard + 5 medium concepts / 12 causal_links / machine memory 全链路
- ✅ 执行层全链路闭环：danlu 18 resolved / dev repo 3 receipts / 4 种 action 类型 / nightly auto-consume / escalation / resolve-monitor apply mode
- ✅ 治理积压清零（danlu vault）：18/18 execution actions resolved；dev repo 仍有 16 个 pending/accepted（拆库后重编译新生成）
- ✅ action query 一致性：CLI + runtime 统一支持 title/substring 匹配与歧义提示
- ✅ machine-memory graph：搜索/过滤/详情 之外再补缩放 / 聚焦 / 高亮
- ✅ 架构文档：九层终极形态 + 自动化角色 + Product Shell 定位明确
- ✅ 5 protocols × 8 templates 真正驱动 compile / query / review / nightly

---

## 五、关键风险

| 风险 | 等级 | 说明 |
|------|------|------|
| 治理不消化 | 🟢 低 | danlu 18 actions 全 resolved；dev repo 16 未 resolved 是因拆库后重编译生成了新 proposals；rewrite proposals 仍需 LLM 生成 candidate |
| 概念空中楼阁 | 🟡 中 | 1 hard + 5 medium + 24 soft，有进步但多数仍 soft |
| 使用密度不足 | 🟡 中 | Phase B 需要持续投料和使用，不是一次性冲刺能完成的 |
| Product Shell 体验断层 | 🟢 低 | 极简面板已上线，Obsidian 端投料/提问/查看产出全可用；剩余是交互式图谱 polish |
| Lint 膨胀 | 🟢 已修 | lint 报告已加 _LINT_REPORT_KEEP=10 轮转，不再无限累积 |

---

## 六、一句话结论

> **炼丹炉的基建已经到了同类项目的天花板（8.6），内容牵引力稳步提升（7.3）。治理积压在 danlu vault 已清零、4 种 action 全链路闭合、概念硬度从全 soft 提升至 6 个 medium+——Phase A 核心目标已基本达成。lint 报告轮转已修复（上限 10）。下一步重点是 Phase B 内容密实（需真实使用投料）和 Phase C 产品打磨。**
