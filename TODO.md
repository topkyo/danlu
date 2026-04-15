# 炼丹炉 To Do List

> 基于 2026-04-15 全面评估生成（含 41 轮闭环后二次评估）。
> 当前综合评分 **7.6/10**。终局架构覆盖度 **~68%**。目标 **9.0+**。

## 当前全局画像

| 维度 | 当前分 | 目标分 | 数据 |
|------|--------|--------|------|
| 架构设计 | 8.5 | 9.2 | 28K 行 / 15 模块 / 零 import-time 循环 / 3 个巨石模块 |
| 工程质量 | 8.0 | 9.2 | 210 测试 / 88% 覆盖 / 零运行时依赖 / verify 全绿 |
| 产物运行态 | 7.0 | 9.0 | 37 index 页 / 12 output 子目录 / wiki 实际内容近空 |
| 终局对齐度 | 6.8 | 9.0 | 九层骨架齐全 / Judgment 50% / Outputs 40% / Shell 60% |
| 可维护性 | 7.5 | 9.0 | 逻辑环待消除 / 最大模块 7003 行 |

### 上轮已完成（41 轮闭环）

- ✅ 动态 facade → 静态 shim（app.py）
- ✅ compile/lint 显式 phase orchestration
- ✅ app_shell / app_surfaces / app_types / app_execution 落地
- ✅ 零 import-time 循环 DAG
- ✅ 14 个 TypedDict 合约
- ✅ 增量编译（source/concept/index/memory 各有 dirty/clean 跟踪）
- ✅ planner-state / query-route-telemetry / execution-policy-decisions 持久化
- ✅ Product Shell 插件 5 视图 + transition-aware controls
- ✅ runtime schema hot-load + citation snapshot safe apply/revert

### 为什么还不到 9 分

上轮重心在"代码架构"，该做的都做了。但评估暴露出 **三个结构性短板**：

1. **巨石模块未拆完**：app_content (7003L) / app_compile (6084L) / app_memory (5254L)，加上 app_content ↔ app_surfaces 逻辑环
2. **测试覆盖有盲区**：llm 42% / config 50% / drop 65% / cli 69%，且 210 测试无端到端 pipeline 测试
3. **知识库本体近空**：0 decisions / 0 judgments / 0 derived / 2 sources / 4 concepts / 0 outputs——骨架精良但炉子里没有料

---

## Tier 1 — 架构手术 (8.5 → 9.2)

> 目标：消灭巨石模块 + 消除逻辑环，让每个模块 < 3500 行

### T1-A. app_content.py 物理拆分

**现状：** 7003 行 / 211 函数。混装了 source builders、concept builders、lifecycle logic、aging/review collectors、render helpers。通过 lazy import 依赖 app_surfaces，形成逻辑环。

**行动：**
1. 新建 `app_lifecycle.py`：把 concept lifecycle、aging signal collectors、review history、knowledge state 相关函数（约 1500-2000 行）迁出
2. 新建 `app_render.py`：把 app_content 中所有 `render_*` / `_template_*` / `curated_page_template` 实现（约 1200-1500 行）迁出
3. app_content.py 收口为：source page builders + concept builders + ingestion sync
4. **消除逻辑环**：app_content 不再 lazy-import app_surfaces；render 逻辑统一走 app_render / app_surfaces

**目标：** app_content.py 从 7003L 降到 ≤ 3500L

**验证：** `bash scripts/verify.sh` 210 tests 全绿 + 无 import-time 循环 + 无逻辑环

### T1-B. app_compile.py 编排瘦身

**现状：** 6084 行 / 75 函数 / 扇出 = 9（引入几乎所有模块）。混装了 compile orchestration、action workflows（rewrite/action/archive apply/revert）、ask/file-back 逻辑。

**行动：**
1. 新建 `app_workflows.py`：把 apply_concept_rewrite / verify_concept_rewrite / revert_concept_rewrite / retire_concept / reactivate_concept / apply_machine_memory_action / review_machine_memory_action / revert_machine_memory_action / apply_material_archive / revert_material_archive 等 action workflow（约 1500-2000 行）迁出
2. app_compile.py 收口为：compile_wiki / lint_wiki / nightly / ask / file_back / shell_status 核心编排

**目标：** app_compile.py 从 6084L 降到 ≤ 3500L，扇出从 9 降到 6-7

**验证：** `bash scripts/verify.sh` 全绿 + CLI 回归

### T1-C. app_memory.py 分层

**现状：** 5254 行 / 71 函数。混装了 machine memory core、material routing/temperature、archive state、graph/topology builders。

**行动：**
1. 新建 `app_routing.py`：把 material routing、temperature 管理、archive candidate 相关（约 1200-1500 行）迁出
2. app_memory.py 收口为：machine memory graph core + concept/source node 管理 + drift/health

**目标：** app_memory.py 从 5254L 降到 ≤ 3500L

**验证：** `bash scripts/verify.sh` 全绿

---

## Tier 2 — 工程硬化 (8.0 → 9.2)

> 目标：消灭覆盖盲区 + 引入端到端测试 + 加强静态检查

### T2-A. 边界模块测试补齐

**现状：** llm.py 42%、config.py 50%、drop.py 65%、cli.py 69%。这些是 I/O 边界模块，也是最容易出 bug 的地方。

**行动：**
1. `test_config.py`：覆盖 backend 解析、缺失环境变量、多后端选择逻辑（目标 85%+）
2. `test_drop.py`：用 fixture 文件测 drop-pdf / drop-image 的 manifest 生成和 frontmatter 逻辑（目标 80%+）
3. `test_cli.py`：测每个 subcommand 的 argparse 路径和 error handling（目标 80%+）
4. `test_llm.py` 扩展：mock HTTP 测 OpenAICompatClient 的 error path、retry、image payload（目标 75%+）

**目标：** 整体覆盖率从 88% 提到 92%+

### T2-B. 端到端 Pipeline 测试

**现状：** 210 个测试全是单元/集成级别，没有 `drop → compile → ask → file-back → review → nightly` 全链条测试。

**行动：**
1. 新建 `test_pipeline.py`
2. 测试场景 1：`drop-url fixture → compile → ask → file-back → review-page → lint`
3. 测试场景 2：`ingest → compile → concept rewrite proposal → apply → verify → revert`
4. 测试场景 3：`compile → nightly → review-action → apply-action → revert-action`
5. 全部使用 temp 目录 + fixture 数据，不依赖网络

**目标：** 至少 3 个端到端场景覆盖核心闭环

### T2-C. Ruff 规则扩展

**现状：** 只启用 F541/F821/F822/F823/F841（5 条规则）。

**行动：**
1. 启用 E（pycodestyle error）基础子集
2. 启用 W（pycodestyle warning）基础子集
3. 启用 I（isort import sorting）
4. 启用 B（flake8-bugbear）常见 bug 检测
5. 逐步修复现有违规

**目标：** ruff 规则从 5 条扩展到 40+ 条且 verify.sh 零 error

---

## Tier 3 — 知识库内容激活 (7.0 → 9.0)

> 目标：让炉子里有真实的料——不是空骨架，而是有血有肉的知识库
>
> 这是评分从 7.6 到 9.0 最大的单一杠杆。没有真实内容，所有治理和输出层都是空转。

### T3-A. 真实原料投料

**现状：** raw/ 只有 3 个文件，wiki/ 只有 2 个 source page。

**行动：**
1. 选一个真实研究主题（如"LLM Agent 架构"或"投资 thesis 样例"）
2. 通过 `drop-url` 投入 5-8 个高质量原料
3. 通过 `drop-pdf` 投入 2-3 个 PDF
4. 运行 `compile` + `run-compile` 生成完整 source pages 和 concepts

**目标：** raw/ ≥ 10 个原料，wiki/sources/ ≥ 8 页，wiki/concepts/ ≥ 15 个有实质内容的 concept

### T3-B. 判断资产播种

**现状：** wiki/decisions/ 和 wiki/judgments/ 均为空。

**行动：**
1. 基于 T3-A 的原料，手工或通过 `ask → file-back` 创建 3-5 个 judgment pages
2. 每个 judgment 必须携带完整 frontmatter：citations / confidence / counter_evidence / invalidation_rule / revisit_after
3. 创建 1-2 个 decision pages（thesis + evidence + recommendation）
4. 运行 `review-page` 对其中至少 2 个执行审阅

**目标：** wiki/judgments/ ≥ 3，wiki/decisions/ ≥ 2，每个都有完整结构化元数据

### T3-C. 派生产物生成

**现状：** wiki/derived/ 为空，output/ 12 个子目录全空。

**行动：**
1. 运行 `ask --format report` 生成 2-3 个 report
2. 运行 `file-back` 回流至少 1 个到 wiki/derived/
3. 运行 `nightly` 生成真实的 lint 结果和 repair artifacts
4. 确保 output/reports/ / output/lint/ / output/packs/ 有实际产物

**目标：** wiki/derived/ ≥ 1，output/ 至少 3 个子目录有实际内容

### T3-D. 治理循环跑通

**现状：** review-queue / aging-report / repair-backlog 结构存在但从未被真实数据激活。

**行动：**
1. 确保 T3-B 的 judgment 中至少 1 个已过 `revisit_after`
2. 运行 `nightly`，验证 aging-report 正确标记过期 judgment
3. 验证 review-queue 和 repair-backlog 被真实填充
4. 执行至少 1 次 review → repair → receipt 完整闭环

**目标：** governance 面板（review-queue / aging-report / repair-backlog）显示真实数据

---

## Tier 4 — Judgment & Output 层深化 (6.8 → 9.0)

> 依赖 Tier 3 的真实数据。没有内容就没有 judgment，没有 judgment 就没有 output。

### T4-A. Counter-evidence 扫描

**目标：** compile 时自动检测新 source 与已有 judgment 的潜在冲突。

**行动：**
1. compile 新增 `_counter_evidence_scan_phase()`
2. 对比新 source 的 concept terms 与已有 judgment 的 citations/thesis
3. 潜在冲突写入 review-queue 并标记 `counter-evidence-candidate`
4. 在 machine memory 中记录 conflict edge

### T4-B. Judgment Lifecycle 主动治理

**目标：** judgment 不只是"写完就放着"，而是有 `formed → active → under-review → revised → retired` 生命周期。

**行动：**
1. 扩展 knowledge lifecycle 支持 judgment-specific states
2. 过期 judgment 由 nightly 自动标记为 under-review
3. cognitive-history 记录每次 judgment 状态变更
4. escalation scan 联动 review priority 自动提升

### T4-C. 输出格式扩展

**目标：** ask 命令支持更丰富的输出格式。

**行动：**
1. `ask --format decision-memo`：从 judgment assets + source/concept 生成结构化 decision memo
2. `ask --format slides`：生成 markdown-based slide deck
3. `ask --format sop`：从 execution receipts 模式抽取 SOP 草案
4. 每种格式配套 prompt template 和输出路径

### T4-D. 概念冲突检测 + 质量分

**目标：** concept 层不只有数量，还有质量信号。

**行动：**
1. concept build 新增冲突检测 pass（同一 concept 不同 source 矛盾标记）
2. 定义 concept quality score：source 覆盖度 / 一致性 / 证据深度 / 更新度
3. quality score 影响 ranking 和 review 优先级
4. 冲突写入 repair-backlog

---

## Tier 5 — 可维护性收口 (7.5 → 9.0)

### T5-A. 模块文档

**行动：**
1. 每个 `app_*.py` 模块顶部加 module docstring（职责 + 边界 + 主要 public API）
2. 在 README 或专门的 `ARCHITECTURE.md` 中绘制模块依赖图

### T5-B. 开发者入门

**行动：**
1. 补 `CONTRIBUTING.md` 或在 README 加 "Developer Guide" section
2. 说明：如何跑测试、如何加新 CLI 命令、如何加新协议、模块职责划分
3. 说明：verify.sh 的内容 + 覆盖率阈值期望

---

## 得分预估

完成全部 Tier 后的预期评分：

| 维度 | 当前 | Tier 1 后 | Tier 2 后 | Tier 3 后 | Tier 4 后 | Tier 5 后 |
|------|------|-----------|-----------|-----------|-----------|-----------|
| 架构设计 | 8.5 | **9.2** | 9.2 | 9.2 | 9.2 | 9.3 |
| 工程质量 | 8.0 | 8.2 | **9.2** | 9.2 | 9.2 | 9.3 |
| 产物运行态 | 7.0 | 7.0 | 7.0 | **9.0** | 9.2 | 9.2 |
| 终局对齐度 | 6.8 | 6.8 | 6.8 | 8.2 | **9.0** | 9.0 |
| 可维护性 | 7.5 | 8.5 | 8.8 | 8.8 | 8.8 | **9.2** |
| **加权总分** | **7.6** | **7.9** | **8.2** | **8.8** | **9.1** | **9.2** |

**关键拐点：Tier 3（内容激活）是从 8.2 跳到 8.8 的单一最大杠杆。**

---

## 执行顺序

```
Tier 1（架构手术）─── 拆模块、消环，打开后续改动空间
       │
       ▼
Tier 2（工程硬化）─── 补测试、加 lint，建立安全网
       │
       ▼
Tier 3（内容激活）─── 投料、播种 judgment、跑通治理 ← 最大杠杆
       │
       ▼
Tier 4（层深化）  ─── counter-evidence、lifecycle、输出格式
       │
       ▼
Tier 5（收口）    ─── 文档、开发者入门
```

- **Tier 1-2** 是基础设施，可以纯靠代码完成
- **Tier 3** 需要真实选题和投料，是唯一需要"用系统"而不是"改系统"的阶段
- **Tier 4** 依赖 Tier 3 的内容存在
- **Tier 5** 随时可做，但放最后因为模块结构在 Tier 1 还会变

---

## 终局九层对照（完成后预期）

| 终局层 | 当前 | 完成后 | 提升来源 |
|--------|------|--------|----------|
| ① Evidence Fabric | 85% | 92% | 真实投料 + provenance 验证 |
| ② Knowledge Compiler | 80% | 92% | 冲突检测 + 质量分 + 真实 concepts |
| ③ Judgment System | 50% | 88% | 真实 judgment + lifecycle + counter-evidence |
| ④ Machine Memory | 75% | 88% | 真实 graph 数据 + conflict edges |
| ⑤ Schema / Protocol | 85% | 90% | 已较完备，小幅完善 |
| ⑥ Governance | 70% | 90% | 真实数据激活 review/aging/repair |
| ⑦ Execution | 80% | 90% | 真实 receipt + audit trail |
| ⑧ Outputs | 40% | 85% | 真实 reports + decision memos + format 扩展 |
| ⑨ Product Shell | 60% | 80% | 真实数据让面板有意义 |

**终局覆盖度：68% → ~88%**

---

## 一句话

> 从 7.6 到 9.0 的路不在"继续写更多代码"，而在三件事：**拆巨石（Tier 1）、补安全网（Tier 2）、让炉子真正烧起来（Tier 3）**。其中 Tier 3 是最大杠杆——没有真实内容流过的治理和输出层，永远只是空转的骨架。
