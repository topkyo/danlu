# D — 代码瘦身候选模块清单：6.5 万行的 ROI 排序

> Historical: 历史分析，LOC/状态可能过期；执行以 Cleanup Plan + Scorecard 为准。
> 只读静态分析。仅给出候选优先级，不动代码。
> SoT：`wc -l`、`grep -c ^def/class`、`git log --name-only` churn 数据、`src/aiwiki/` 各模块 docstring 中的 OWNER STATUS。

## 1. 数据基线（截至 2026-05-18）

- 全部 runtime：`src/aiwiki/**/*.py` 114 个 `.py`，约 **65,518 行**（不含 tests）。
- 顶层 runtime：`src/aiwiki/*.py` 35 个 `.py`，约 **24,289 行**。
- 子包数：12 个（`app_linting / app_shell / cli / compile / content / execution / memory / planner / render / runner / signals` + root）。
- 顶层大 hub 文件（>1000 行）：9 个，合计约 **13,863 行**，约占顶层 runtime **57%**。
- 近 3 个月 churn top：`app.py / runner.py / cli.py / drop.py` 高频改动。

## 2. 三维评分模型

每个候选按 **(Size, Risk, Reward)** 打分，1-5 整数：

- **Size**：当前 LoC / 占核心比例
- **Risk**：删除/拆分对 acceptance 的破坏概率（1=零风险，5=高破坏）
- **Reward**：能减少的真实 review 噪音 / 调用层数 / 维护成本（1=低，5=高）
- **ROI = Reward × (6 - Risk)**（越高越值得做）

## 3. 候选清单（按状态与 ROI）

### 保留项 — `app.py` (554 行) — 稳定外部兼容 shim
- **OWNER STATUS**: `"Static compatibility shim for the aiwiki runtime."`
- **内容**：纯 `from . import app_compile as _app_compile` + 全量 re-export，无业务逻辑。
- **Size**: 2 | **Risk**: 4 | **Reward**: 2
- **ROI**: 4
- **动作建议**：
  - **不要列为 delete-now**。README 明确承诺 `src/aiwiki/app.py` 是继续保留的 `aiwiki.app` import surface；AOS-003 审计也已经判定它不能删。
  - 只允许在明确 deprecation plan 后逐步减少内部依赖；外部兼容面保留。
- **预期收益**：短期主要是文档清晰化，不是删文件。
- **风险点**：删除会破坏外部 `aiwiki.app` 兼容承诺。

### 🥇 Top 1 — `app_content.py` (262 行) — facade-only，但仍是活跃 compat seam
- **OWNER STATUS**: `"OWNER STATUS: facade. DO NOT ADD LOGIC HERE. New code must import from aiwiki.content.* directly."`
- **内容**：100% re-export 自 `aiwiki.content.*`，唯一保留原因是 test patch seam。
- **Size**: 2 | **Risk**: 2 | **Reward**: 4
- **ROI**: 16
- **动作建议**：先做调用面迁移计划，再迁移到直接 `aiwiki.content.*` 导入；test patch target 同步更新。它是比 `app.py` 更合适的 facade retirement 候选，但不应和 `app.py` 绑定删除。
- **特殊价值**：facade 自己写明了"不要在这里加逻辑"，是最干净的删除候选。

### 🥈 Top 2 — `app_surfaces.py` (1846 行, 仅 9 个 top-level decl) — 巨函数嫌疑
- **Size**: 5 | **Risk**: 3 | **Reward**: 4
- **ROI**: 12
- **内容**：1846 行/9 个 decl ≈ 单函数平均 200+ 行。极可能是 render/format/dispatch 巨函数集合。
- **动作建议**：
  - 先做 `radon cc -s` 或人工识别 cyclomatic complexity top 3 函数。
  - 巨函数内部按 sub-render 拆为 helper（同文件即可），降低 review 噪音。
  - **拆函数比拆文件 ROI 更高**——facade 拆分会增加心智负担，函数级重构降低真实复杂度。

### 🥉 Top 3 — `app_memory_surfaces.py` (77 行) — facade-only，但仍有 public/test patch seam
- **OWNER STATUS**: `"OWNER STATUS: facade. DO NOT ADD LOGIC HERE. New code must import from aiwiki.memory.* directly."`
- **内容**：100% re-export 自 `aiwiki.memory.*` + `app_memory_query`。AOS-003 已经动过其中两个 private symbol，证明删除是安全路径。
- **Size**: 2 | **Risk**: 2 | **Reward**: 3
- **ROI**: 12
- **动作建议**：迁移调用方到 `aiwiki.memory.*` 直接导入，然后整个 facade 文件下线。

### 4️⃣ — `app_protocol.py` (1995 行) — 最大 hub，但有真实业务
- **Size**: 5 | **Risk**: 4 | **Reward**: 4
- **ROI**: 8
- **内容**：1995 行，37 个 top-level decl，**包含真实 manifest / pending_action / protocol 状态管理逻辑**，不是纯 facade。
- **动作建议**：
  - 不要整体拆。先做"内部主题分组"：识别 3-5 个内聚簇（如 `manifest_io`、`pending_actions`、`protocol_routing`、`review_history`）。
  - 仅当某个簇 ≥ 400 行 + 与其他簇耦合度低时，才抽到独立 module。
  - 严禁"为了 LoC 数字而拆"导致 facade-on-facade。
- **风险点**：1995 行高耦合，盲拆会产生循环依赖。

### 5️⃣ — `app_lifecycle.py` (1835 行, 49 个 top-level decl)
- **Size**: 5 | **Risk**: 4 | **Reward**: 3
- **ROI**: 6
- **内容**：49 个 decl，平均 37 行/decl，结构相对合理，不是巨函数堆积。
- **动作建议**：**暂不动**。LoC 大但函数粒度健康，拆分收益低于当前 Top 3 候选。

### 6️⃣ — `drop.py` (1736 行, 87 个 top-level decl) — 高 churn 但高内聚
- **Size**: 5 | **Risk**: 3 | **Reward**: 2
- **ROI**: 6
- **内容**：处理 drop-url / drop-pdf / drop-image / drop-repo 四种入口，churn 高（近 3 月 27 次改动）。
- **动作建议**：**暂不动**。87 个 decl 说明函数粒度健康；churn 高代表它仍在演进，不适合此时拆分。

### 7️⃣ — `app_state.py` (1450 行, 148 个 top-level decl)
- **Size**: 4 | **Risk**: 3 | **Reward**: 2
- **ROI**: 6
- **内容**：148 个 decl = 单个 decl 平均 < 10 行，结构非常细粒度，已经是好状态。
- **动作建议**：**暂不动**。

### 8️⃣ — `llm.py` (1016 行, 30 个 top-level decl) — 多 backend 抽象
- **Size**: 4 | **Risk**: 3 | **Reward**: 3
- **ROI**: 9
- **内容**：8 个 backend probe + 4-state 健康检查。
- **动作建议**：
  - **不是"拆文件"而是"减少 backend 数量"**。
  - 与 D 文档无关，留给 AOS-005b（详见 B 文档）。

### 9️⃣ — `app_compile.py` (717 行) — legacy owner
- **OWNER STATUS**: `"legacy owner. New large logic blocks should be extracted to aiwiki.compile.* rather than added here."`
- **Size**: 3 | **Risk**: 4 | **Reward**: 2
- **ROI**: 4
- **动作建议**：**保持现状**。"legacy owner" 说明项目已经设计好了演进路径——新代码进 `aiwiki.compile.*`，旧逻辑随自然 churn 逐步外迁，不要强拆。

## 4. ROI 总表（一览）

| 排名 | 模块 | LoC | Risk | Reward | ROI | 动作 |
|---|---|---|---|---|---|---|
| keep | `app.py` | 554 | 4 | 2 | 4 | 保留兼容 shim |
| 1 | `app_content.py` | 262 | 2 | 4 | **16** | 调用面迁移后退役 facade |
| 2 | `app_surfaces.py` | 1846 | 3 | 4 | **12** | 函数级拆分 |
| 3 | `app_memory_surfaces.py` | 77 | 2 | 3 | **12** | 调用面迁移后退役 facade |
| 4 | `llm.py` | 1016 | 3 | 3 | 9 | 减 backend 数量 |
| 5 | `app_protocol.py` | 1995 | 4 | 4 | 8 | 内部主题分组 |
| 6 | `app_lifecycle.py` | 1835 | 4 | 3 | 6 | 暂不动 |
| 7 | `drop.py` | 1736 | 3 | 2 | 6 | 暂不动 |
| 8 | `app_state.py` | 1450 | 3 | 2 | 6 | 暂不动 |
| 9 | `app_compile.py` | 717 | 4 | 2 | 4 | 自然演进 |

## 5. 推荐 AOS-005 candidate set

按 ROI ≥ 12 划线，且排除 README/PROGRESS 明确要求保留的 `app.py` 后，**真正值得做的下一轮候选只有 3 个**：

1. **`app_surfaces.py` 巨函数拆分**（1846 行 → 内部重构降复杂度，不一定减 LoC）
2. **`app_content.py` 调用面迁移后退役**（262 行 facade）
3. **`app_memory_surfaces.py` 调用面迁移后退役**（77 行 facade）

预期直接删除的 facade 噪音上限约 **339 行**（不含 `app.py`），但 `app_surfaces.py` 的复杂度下降可能比 LoC 删除更有价值。这比 AOS-003 只动 2 个 private re-export 更进一步，但不应承诺一次性删除 `app.py`。

## 6. 不推荐做的事

- ❌ **整体拆 `app_protocol.py` / `app_lifecycle.py`**：高耦合 + 高 risk，没有 receipt-backed gate 证明收益。
- ❌ **追求"每个文件 < 500 行"硬阈值**：会迫使形成 facade-on-facade。
- ❌ **删 `app.py`**：它是 README 承诺保留的 `aiwiki.app` 外部兼容 shim，不是 delete-now 候选。
- ❌ **删 `app_compile.py`**：legacy owner 是设计选择，不是欠债。
- ❌ **动 `drop.py` / `app_state.py`**：函数粒度健康，churn 数据说明它们仍在演进。

## 7. 单句结论

> **6.5 万行 runtime 里，短期不应删除 `app.py` 这个外部兼容 shim；真正可推进的是 `app_surfaces.py` 的函数级复杂度削薄，以及 `app_content.py` / `app_memory_surfaces.py` 两个小 facade 的调用面迁移。下一轮 slimdown 应优先降低真实 review 复杂度，而不是追求大 LoC 删除数字。**

## 8. AOS-005a 执行结果（2026-05-19）

AOS-005a 执行后，ROI 结论从“删除 339 行 facade”收敛为“先清 runtime 依赖和 review 复杂度”：

- `app_surfaces.py`：已抽出 4 个 compile-status 渲染 helper，并把该文件对 `app_content` / `app_memory` facade 的依赖迁到直接 owner module。
- `app_memory_surfaces.py`：`src/aiwiki` 内直接 runtime import 已清零；因 public/test patch seam 仍有效，文件保留。
- `app_content.py`：已迁移 owner 明确的低风险 import，但剩余 app shell / compile / lint / patch seam 调用仍真实存在，文件保留。
- `app.py`：未触碰，继续保留。

因此短期收益不是大规模 LoC 删除，而是减少 runtime facade-on-facade 路径、降低 `app_surfaces.py` 局部 review 难度，并为后续更细的 patch seam 清理建立证据。
