# 炼丹炉 To Do List

> 基于 2026-04-16 全量代码 / 状态 / 内容 / 测试 / 运行态独立评估。
> 评估方法论：**双轴打分**——基建完成度（代码/架构/管线）× 内容牵引力（真实知识密度/治理闭合/执行落地）。
> 当前综合评分 **8.0 / 10**（基建 8.5 / 内容 6.9）。目标 **9.0+**。

---

## 一、全量评估快照（2026-04-16）

### 规模指标

| 指标 | 数据 |
|------|------|
| Python 源码 | 25 模块 / 33,416 行 |
| 测试 | 14 文件 / 10,305 行 / 314 tests / 92% coverage |
| CLI 命令 | 37 个（ingest × 6 / compile × 4 / query × 3 / review × 5 / execute × 5 / governance × 6 / shell × 4 / automation × 4） |
| 原料 | 46 raw files（30 images + 16 markdown） |
| 知识资产 | 16 sources → 30 concepts → 6 judgments → 4 decisions → 2 derived |
| Machine Memory | 259 edges（concept_causal 12 / concept_to_concept 125 / source_to_concept 60 / source_to_judgment 58 / j→j 2 / j→d 2）/ 1,023 terms |
| 输出产物 | 107 artifacts（lint 43 / reports 11 / decision-memos 10 / sop-drafts 8 / agents 7 / pilots 5 / slides 3 / figures 2） |
| 协议 | 5 套（general / investing / research / product / ops）× 8 模板 |
| Obsidian 插件 | furnace-product-shell v0.2.0（3,426 行 JS） |
| 状态文件 | 27 个 JSON/JSONL（machine-memory 19K 行 / nightly-health 11K 行 / execution-policy-decisions 1,265 行） |
| 闭环迭代 | 48 段（verify + qa-review + closed_loop） |

### 双轴打分

| 维度 | 基建分 | 内容分 | 综合 | 关键证据 |
|------|--------|--------|------|----------|
| ① Evidence Fabric | 9.0 | 7.5 | **8.5** | 5 drop 入口 + archive 闭环 ✓ / 但 46 raw → 16 compiled 量不大 |
| ② Knowledge Compiler | 9.0 | 6.5 | **8.0** | 增量 8 阶段 + dirty/clean 全链路 ✓ / 但 30 concepts 全 soft、0 rewrite 被 apply |
| ③ Judgment System | 8.5 | 7.0 | **8.0** | lifecycle + counter-evidence + revisit 完整 ✓ / 但仅 2 条 j→j 边、全 medium confidence |
| ④ Machine Memory | 8.5 | 7.0 | **8.0** | topology + planner + health 全链路 ✓ / 但 8 actions 全 proposed、仅消费 1 |
| ⑤ Schema / Protocol | 9.0 | 8.5 | **8.8** | 5 protocols 真正驱动 runtime ✓ / 仅 research 被深度运行 |
| ⑥ Governance | 8.5 | 6.0 | **7.5** | review → aging → repair 管线完整 ✓ / **但产生工作不消化**：39 warnings + 25 rewrites + 8 proposals 全 pending |
| ⑦ Execution Layer | 7.5 | 5.5 | **6.8** | apply→revert→re-apply 已证明 ✓ / 但仅 1 类 action、3 receipts、planner 未自动消费 |
| ⑧ Outputs | 8.0 | 6.5 | **7.5** | 107 artifacts 格式齐全 ✓ / 但 43 是 lint 报告、高价值 output 稀疏 |
| ⑨ Product Shell | 8.0 | 7.5 | **7.8** | Obsidian + HTML + new-vault + search + batch ✓ / 但无 context 推断、静态图谱、无 onboarding |
| **加权平均** | **8.5** | **6.9** | **8.0** | |

### 对比前次自评（8.4）的修正

前次自评 8.4 主要高估了三处：

1. **Governance 高估**（8.5 → 7.5）：管线完整不等于管线消化——39 lint warnings 未清、25 rewrite proposals 零 apply、8 execution proposals 零自动消费，治理层产生了大量工作但几乎没有闭合
2. **Execution 高估**（7.5 → 6.8）：3 receipts 仅证明路径可通，但 action 类型单一（仅 citation-refresh）、planner 自动消费完全未激活
3. **Output 高估**（8.0 → 7.5）：107 artifacts 数量可观，但 43 是 lint 报告、有效高价值输出（真实 reports/slides/figures）偏少

### 核心优势（值得保持）

1. **架构完整性极高**：九层全部存在且功能闭环，在同类项目中罕见
2. **测试纪律过硬**：314 tests / 92% coverage / 无循环依赖 / verify 一键可跑
3. **增量编译成熟**：8 阶段 dirty/clean 追踪 + compile-state 持久化，编译不再是黑箱
4. **协议体系真实**：5 protocols × 8 templates 真正影响 compile / query / review / nightly，不是装饰
5. **Judgment 数据模型精密**：counter-evidence / invalidation / revisit / escalation / cognitive-history 全链路可追溯
6. **Product Shell 骨架完善**：Obsidian 插件 + HTML fallback + shell-summary contract 三层联动

### 核心短板（必须解决）

1. **治理只产不消**：系统非常擅长"发现问题"（lint warnings / rewrite proposals / execution proposals / aging reports），但没有一个闭合——30 concepts 全标"待回看"、25 rewrite proposals 全 pending、8 execution proposals 全 proposed
2. **概念层全弱**：30 concepts 全部 soft hardness / low-medium confidence / evidence-gap 标记，judgment 层建在弱概念上的"空中楼阁"风险
3. **执行层窄且浅**：仅 1 种 action 类型被真实执行、planner 无自动消费循环、dry-run 不产出结构化产物
4. **内容密度低**：16 sources → 30 concepts 几乎 1:2，很多 concept 只有 1-2 个 source 支撑；有效知识内容约 4,000 行，元数据 overhead 高

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
| **C1. 交互式图谱** | machine-memory.html 升级为 vis.js/d3-force 力导向图，节点可点击跳转、按 kind 过滤、按 protocol 着色 |
| **C2. Context 自动推断** | `review-action` / `apply-action` 支持 title 子串模糊匹配；shell-summary 暴露 `suggested_next_actions` |
| **C3. First-run onboarding** | `new-vault` 后首次打开 Obsidian 展示引导面板（投料→编译→提问→审阅 四步走） |
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
- **Phase B 入口结论**：`ask` 现在在 Obsidian / CLI 两边都可直接使用；投料共享同一 runtime，其中 `drop-note` 已有双入口，其他 `drop-url / drop-pdf / drop-image / drop-repo` 仍以 CLI 为主，Obsidian 侧可直接整理 `raw/inbox/`。

---

## 三、得分推演

| 维度 | 当前 | Phase A 后 | Phase B 后 | Phase C 后 |
|------|------|-----------|-----------|-----------|
| ① Evidence Fabric | 8.5 | 8.5 | **9.0** | 9.0 |
| ② Knowledge Compiler | 8.0 | 8.0 | **9.0** | 9.0 |
| ③ Judgment System | 8.0 | 8.0 | **9.0** | 9.0 |
| ④ Machine Memory | 8.0 | 8.5 | **9.0** | 9.0 |
| ⑤ Schema / Protocol | 8.8 | 8.8 | 9.0 | **9.5** |
| ⑥ Governance | **7.5** | **8.5** | 9.0 | 9.0 |
| ⑦ Execution Layer | **6.8** | **8.5** | 8.5 | 9.0 |
| ⑧ Outputs | 7.5 | 7.5 | 8.0 | **9.0** |
| ⑨ Product Shell | 7.8 | 7.8 | 8.0 | **8.8** |
| **综合** | **8.0** | **8.3** | **8.8** | **9.1** |

---

## 四、已完成里程碑（48 轮闭环）

- ✅ `app.py` 动态 facade → 静态 shim + 25 个 owner module（最大 4,275L `app_compile.py`）
- ✅ 314 tests / 92% coverage / verify 全绿 / 无循环依赖
- ✅ 48 段闭环迭代（verify + qa-review + closed_loop）
- ✅ 增量编译 8 阶段 dirty/clean state + compile-state.json 持久化
- ✅ Product Shell Obsidian v0.2.0 + HTML 三中心 fallback
- ✅ `new-vault` 脚手架：外部 runtime launcher 模式
- ✅ Product Shell: search / batch apply / batch revert / review-next / safe batch review modal
- ✅ Judgment lifecycle / cognitive-history / governance surfaces 全链路
- ✅ planner-state / query-route-telemetry / execution-policy-decisions 持久化（1,265 policy decisions）
- ✅ 概念因果网络：5 hard/medium concepts / 12 causal_links / machine memory 全链路
- ✅ 执行层真实闭环：apply → revert → re-apply（3 receipts / 1 planner action consumed）
- ✅ 架构文档：九层终极形态 + 自动化角色 + Product Shell 定位明确
- ✅ 5 protocols × 8 templates 真正驱动 compile / query / review / nightly

---

## 五、关键风险

| 风险 | 等级 | 说明 |
|------|------|------|
| 治理不消化 | 🔴 高 | 如果 Phase A 不清零治理积压，系统会陷入"越跑越多 warning"的死循环 |
| 概念空中楼阁 | 🟡 中 | 30 concepts 全 soft + judgment 建在上面 = 判断资产可信度受限 |
| 使用密度不足 | 🟡 中 | Phase B 需要持续投料和使用，不是一次性冲刺能完成的 |
| Product Shell 体验断层 | 🟢 低 | Obsidian 插件已可用，剩余是 polish 不是 blocker |

---

## 六、一句话结论

> **炼丹炉的基建已经到了同类项目的天花板（8.5），但内容牵引力还在起步期（6.9）。当务之急不是继续修管线，而是清零积压、用系统产出真实知识、让治理链从"发现"走到"解决"。Phase A 确定能做，Phase B 需要持续使用，Phase C 是产品打磨——三阶段走完就稳过 9 分。**
