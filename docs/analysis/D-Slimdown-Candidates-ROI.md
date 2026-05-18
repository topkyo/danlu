# D — 代码瘦身候选模块清单：6.5 万行的 ROI 排序

> 只读静态分析。仅给出候选优先级，不动代码。
> SoT：`wc -l`、`grep -c ^def/class`、`git log --name-only` churn 数据、`src/aiwiki/` 各模块 docstring 中的 OWNER STATUS。

## 1. 数据基线（截至 2026-05-18）

- 核心 runtime：`src/aiwiki/` 114 个 `.py`，约 **24,289 行**（不含 tests）。
- 子包数：12 个（`app_linting / app_shell / cli / compile / content / execution / memory / planner / render / runner / signals` + root）。
- 大 hub 文件（>1000 行）：8 个，合计约 11,800 行 = **核心 ~48%**。
- 近 3 个月 churn top：`app.py / runner.py / cli.py / drop.py` 高频改动。

## 2. 三维评分模型

每个候选按 **(Size, Risk, Reward)** 打分，1-5 整数：

- **Size**：当前 LoC / 占核心比例
- **Risk**：删除/拆分对 acceptance 的破坏概率（1=零风险，5=高破坏）
- **Reward**：能减少的真实 review 噪音 / 调用层数 / 维护成本（1=低，5=高）
- **ROI = Reward × (6 - Risk)**（越高越值得做）

## 3. 候选清单（按 ROI 降序）

### 🥇 Top 1 — `app.py` (554 行) — 全模块 re-export shim
- **OWNER STATUS**: `"Static compatibility shim for the aiwiki runtime."`
- **内容**：纯 `from . import app_compile as _app_compile` + 全量 re-export，无业务逻辑。
- **Size**: 2 | **Risk**: 2 | **Reward**: 4
- **ROI**: 16
- **动作建议**：
  - 调用方扫描：`grep -r "from aiwiki.app import\|from aiwiki import app" src tests`。
  - 若调用者 ≤ 20 处，可一次性迁移到具体子模块直接导入，下线 `app.py`。
  - 若调用者 > 50 处（很可能），按 `app_compile / app_content / app_execution / app_memory / ...` 分批迁移，每批一次 commit。
- **预期收益**：删 554 行 + 减少一层 import 噪音 + 让"app 是什么"的心智消失。
- **风险点**：tests 中大量 `patch('aiwiki.app.<name>')` 必须同步改 patch target。

### 🥈 Top 2 — `app_content.py` (262 行) — facade-only
- **OWNER STATUS**: `"OWNER STATUS: facade. DO NOT ADD LOGIC HERE. New code must import from aiwiki.content.* directly."`
- **内容**：100% re-export 自 `aiwiki.content.*`，唯一保留原因是 test patch seam。
- **Size**: 2 | **Risk**: 2 | **Reward**: 4
- **ROI**: 16
- **动作建议**：与 Top 1 类似，迁移到直接 `aiwiki.content.*` 导入；test patch target 同步更新。
- **特殊价值**：facade 自己写明了"不要在这里加逻辑"，是最干净的删除候选。

### 🥉 Top 3 — `app_memory_surfaces.py` (77 行) — facade-only
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

### 5️⃣ — `app_surfaces.py` (1846 行, 仅 9 个 top-level decl) — 巨函数嫌疑
- **Size**: 5 | **Risk**: 3 | **Reward**: 4
- **ROI**: 12（高于 #4，因为 9 个 decl 暗示巨函数）
- **内容**：1846 行/9 个 decl ≈ 单函数平均 200+ 行。极可能是 render/format/dispatch 巨函数集合。
- **动作建议**：
  - 先做 `radon cc -s` 或人工识别 cyclomatic complexity top 3 函数。
  - 巨函数内部按 sub-render 拆为 helper（同文件即可），降低 review 噪音。
  - **拆函数比拆文件 ROI 更高**——facade 拆分会增加心智负担，函数级重构降低真实复杂度。
- **重新调整**：**这其实是 ROI Top 候选之一**，但 AOS-003 没动，因为风险评估时把 LoC 和函数粒度混淆了。

### 6️⃣ — `app_lifecycle.py` (1835 行, 49 个 top-level decl)
- **Size**: 5 | **Risk**: 4 | **Reward**: 3
- **ROI**: 6
- **内容**：49 个 decl，平均 37 行/decl，结构相对合理，不是巨函数堆积。
- **动作建议**：**暂不动**。LoC 大但函数粒度健康，拆分收益低于 #4 #5。

### 7️⃣ — `drop.py` (1736 行, 87 个 top-level decl) — 高 churn 但高内聚
- **Size**: 5 | **Risk**: 3 | **Reward**: 2
- **ROI**: 6
- **内容**：处理 drop-url / drop-pdf / drop-image / drop-repo 四种入口，churn 高（近 3 月 27 次改动）。
- **动作建议**：**暂不动**。87 个 decl 说明函数粒度健康；churn 高代表它仍在演进，不适合此时拆分。

### 8️⃣ — `app_state.py` (1450 行, 148 个 top-level decl)
- **Size**: 4 | **Risk**: 3 | **Reward**: 2
- **ROI**: 6
- **内容**：148 个 decl = 单个 decl 平均 < 10 行，结构非常细粒度，已经是好状态。
- **动作建议**：**暂不动**。

### 9️⃣ — `llm.py` (1016 行, 30 个 top-level decl) — 多 backend 抽象
- **Size**: 4 | **Risk**: 3 | **Reward**: 3
- **ROI**: 9
- **内容**：8 个 backend probe + 4-state 健康检查。
- **动作建议**：
  - **不是"拆文件"而是"减少 backend 数量"**。
  - 与 D 文档无关，留给 AOS-005b（详见 B 文档）。

### 🔟 — `app_compile.py` (717 行) — legacy owner
- **OWNER STATUS**: `"legacy owner. New large logic blocks should be extracted to aiwiki.compile.* rather than added here."`
- **Size**: 3 | **Risk**: 4 | **Reward**: 2
- **ROI**: 4
- **动作建议**：**保持现状**。"legacy owner" 说明项目已经设计好了演进路径——新代码进 `aiwiki.compile.*`，旧逻辑随自然 churn 逐步外迁，不要强拆。

## 4. ROI 总表（一览）

| 排名 | 模块 | LoC | Risk | Reward | ROI | 动作 |
|---|---|---|---|---|---|---|
| 1 | `app.py` | 554 | 2 | 4 | **16** | 下线 facade |
| 2 | `app_content.py` | 262 | 2 | 4 | **16** | 下线 facade |
| 3 | `app_surfaces.py` | 1846 | 3 | 4 | **12** | 函数级拆分 |
| 4 | `app_memory_surfaces.py` | 77 | 2 | 3 | **12** | 下线 facade |
| 5 | `llm.py` | 1016 | 3 | 3 | 9 | 减 backend 数量 |
| 6 | `app_protocol.py` | 1995 | 4 | 4 | 8 | 内部主题分组 |
| 7 | `app_lifecycle.py` | 1835 | 4 | 3 | 6 | 暂不动 |
| 8 | `drop.py` | 1736 | 3 | 2 | 6 | 暂不动 |
| 9 | `app_state.py` | 1450 | 3 | 2 | 6 | 暂不动 |
| 10 | `app_compile.py` | 717 | 4 | 2 | 4 | 自然演进 |

## 5. 推荐 AOS-005 candidate set

按 ROI ≥ 12 划线，**真正值得做的瘦身候选只有 4 个**：

1. **`app.py` 下线**（Top 1，554 行）
2. **`app_content.py` 下线**（Top 2，262 行）
3. **`app_memory_surfaces.py` 下线**（Top 4，77 行）
4. **`app_surfaces.py` 巨函数拆分**（Top 3，1846 行 → 内部重构降复杂度，不一定减 LoC）

预期减少 ~900 行 facade 噪音 + 1 个大文件复杂度降一半。这比 AOS-003 只动 2 个 private re-export 的收益高一个数量级。

## 6. 不推荐做的事

- ❌ **整体拆 `app_protocol.py` / `app_lifecycle.py`**：高耦合 + 高 risk，没有 receipt-backed gate 证明收益。
- ❌ **追求"每个文件 < 500 行"硬阈值**：会迫使形成 facade-on-facade。
- ❌ **删 `app_compile.py`**：legacy owner 是设计选择，不是欠债。
- ❌ **动 `drop.py` / `app_state.py`**：函数粒度健康，churn 数据说明它们仍在演进。

## 7. 单句结论

> **6.5 万行核心代码里，真正能干净删的纯 facade（`app.py + app_content.py + app_memory_surfaces.py`）合计约 900 行（占比 ~3.7%）；真正值得重构的巨函数集中在 `app_surfaces.py`。其余看似"肥胖"的大文件其实结构合理，强拆只会产生新的 facade-on-facade。**
