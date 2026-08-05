---
title: "Structural Debt: Why It Remains & How to Clear It"
kind: "analysis"
status: "active"
created_at: "2026-08-05"
---

# 结构债：为何未消、如何彻底解决

> **性质**：设计分析（非执行计划）。实施须另开单 seam 任务，禁止 broad rewrite。  
> **背景**：2026-08-05 全量扫描 R2 工程实测 **8.2**；分层硬约束大多达标，但审计仍标「结构债未消」。

---

## 1. 「结构债未消」具体指什么

审计说的不是「分层全坏了」，而是：**产品层不变量已成立，包级依赖图仍有已知违规与巨石**。

| 已清（勿回退） | 仍开（结构债） |
|---|---|
| 根级 `app_*.py` = 0 | **content ↔ memory 双向 import**（环） |
| `memory ↛ execution` | ~~`app_shell` / `app_linting` 重 facade~~ **DONE 2026-08-05** |
| `state ↛ protocol` | **Top hub 778–921 LOC**（views / ask / io / concepts…） |
| CLI 仅 drop/today/advanced | **compile 静态 SCC 密度高**（运行时靠 lazy/TYPE_CHECKING 掩盖） |
| LLM 主路径 fail-closed | **memory/action_core 等 re-export compat seam** |

一句话：**门禁能绿的「运行时分层」≠ 依赖图上的「包单向分层」。** 前者是产品健康；后者是可维护性债。

---

## 2. 根因（为何刀了多次还在）

### 2.1 content↔memory 环是历史枢纽的残留形态

旧 `content/memory.py` 巨石拆成 `memory/*` 后，**业务语义仍交缠**：

- `content` 侧需要 machine-memory 的 path / scoring / load（例：`material.py` → `memory.paths|scoring|state`）
- `memory` 侧需要 wiki 页解析与 manifest sync（例：`action_core.py` → `content.concepts|io`）

已做的 Knife A/B / rewrite_readiness 外提，是**切断部分边**，不是重新划所有权。环的本质是：

> 没有第三层「只读共享契约」，两边互相借对方的实现细节。

### 2.2 Facade 服务的是测试 patch / 旧 import，不是产品

`app_shell/__init__.py` 的 `_CompatModule` 与 `app_linting/__init__.py` 重 export，价值几乎全在：

- `patch("aiwiki.app_shell....")` 历史习惯
- 调用方懒得改直引 owner

AGENTS 已定案：**纯 facade 一轮做干净，禁止半迁移**。债还在，是因为迁调用方成本 > 删文件成本，且未立项「compat 迁移波」。

### 2.3 Hub 行数是「功能簇未切 seam」，不是「没人动」

F-11 已外提 concept_quality / judgment_assets / phases_governance；views/ask/io 仍 800+ 行，因为：

- 单文件内多职责（渲染面 / ask 编排 / IO 聚合）仍粘在一起
- 续刀要求「单 seam、可验证、禁止 broad rewrite」——进度刻意慢

### 2.4 静态 SCC ≠ 运行时 import 失败

文档写「全库仅 1 个模块级 SCC」指**可触发 ImportError 的环**；静态 import 图仍可见 compile 簇大 SCC。两者口径不同，**不要用静态图否证「运行时可加载」**，但静态密度仍是结构债信号。

---

## 3. 彻底解决的目标态（Done 定义）

全部满足才可宣称「结构债清零」：

1. **单向分层硬约束（可 rg 门禁）**  
   - `content` 不得 import `memory`  
   - `memory` 可只读依赖 `content` 的**窄接口**（或改为双方只依赖新包）  
   - 或引入第三包后两边都只依赖第三包  
2. **零重 facade**：`app_shell` / `app_linting` 的 `__init__.py` 仅为包文档或最小 public API；无 `_CompatModule`；测试直 patch owner  
3. **无 ≥800 LOC 单文件**（建议阈值；views/ask/io/concepts 均切开）  
4. **无 `# re-export compat seam`** 于生产模块  
5. **静态 SCC**：compile 簇无 >N 节点环（N 待定，建议 ≤5），或全部环仅 TYPE_CHECKING 且有注释登记

非目标：再开一轮「删功能换分层」、改五层平面产品语义、hosted service。

---

## 4. 推荐解法（根因最优，非症状补丁）

### 方案 A（推荐）：抽出 `aiwiki.corpus` 只读共享层

把**环上交叉的符号**下沉到新包（名字可议：`corpus` / `wiki_read` / `shared_read`）：

| 迁入共享层 | 现今位置（示意） |
|---|---|
| path 常量（manual_link / concept_rewrite state） | `memory.paths` |
| scoring 纯函数（timestamp / recency / protocol_hints） | `memory.scoring` |
| 窄 snapshot API（concept_page_snapshot、source_summary、routing_snapshot） | `content.io` / `concepts` |
| placeholder / hardness 纯函数 | `content.concepts` |

规则：

- `content` 与 `memory` **只允许** import `corpus`（及 utils/state/protocol）  
- `corpus` **禁止** import `content` / `memory` / `execution` / `runner`  
- 一次迁完一个 seam（例如先 paths+scoring），`rg` 验证边消失后再迁下一 seam

升级路径：迁完删除双向边 → 加 `scripts` 或 docs_consistency 的 import 方向钉 → 删除过渡 re-export。

删除条件：`rg 'from \.\.memory' src/aiwiki/content` 与 `rg 'from \.\.content' src/aiwiki/memory'` 在约定例外表外均为空。

### 方案 B：规定单向 `memory → content`，把 scoring/paths 下沉 content

若不愿新包：

- 将 `memory.paths` / `memory.scoring` 中被 content 使用的符号迁入 `content`（或 `content/support`）  
- `memory` 改为从 `content` 引用  
- **禁止** content import memory

代价：content 包变「更胖」的 wiki+评分宿主；语义上 scoring 本属 machine-memory 更别扭。故 **不如方案 A 清晰**。

### 方案 C（不推荐）：保留环 + 仅文档声明

即现状。可跑、难改、审计永远扣分。

---

## 5. Facade / Hub 清法（与环正交，可并行）

### 5.1 Facade 一轮清干净（符合 AGENTS 定案）

1. `rg "aiwiki\.app_shell|aiwiki\.app_linting"` 列全部 import / patch 点  
2. 全部改为直引 owner 模块（`app_shell.summary`、`app_linting.phases` 等）  
3. 删 `_CompatModule` 与批量 re-export；`__init__.py` 留 docstring  
4. 验收：acceptance + unit + 相关 Jest；禁止「先删 facade 文件、不改 patch」

### 5.2 Hub 续刀（单 seam）

优先级建议：

1. `render/views.py`（921）— 再外提只读聚合块  
2. `execution/ask.py`（888）— 上下文装配 vs 写出  
3. `content/io.py`（881）— snapshot/routing 与写路径分离（可喂方案 A）

每刀：行数下降可测 + 调用方零行为变 + `verify` 绿。

---

## 6. 执行波次（若立项）

| 波 | 目标 | 验证 |
|---|---|---|
| S0 | 写 import 方向契约 + 现状边清单进本文件附录 | rg 基线 |
| S1 | 抽出 `corpus.paths` + `corpus.scoring`；断 content→memory 的 paths/scoring 边 | unit + acceptance |
| S2 | 抽出窄 snapshot API；断 memory→content 的粗 import 或改为 corpus | 同上 |
| S3 | facade 调用方迁移 + 删 `_CompatModule` | unit + acceptance |
| S4 | hub 单 seam ×2–3 | 行数 + verify |
| S5 | docs_consistency / scripts 加分层 import 钉 | CI 防回潮 |

**禁止**：一 PR 同时「新包 + 删 facade + 拆三个 hub」。

---

## 7. 与优先债的关系

优先债已收：文档计数、untrusted_source 测、alchemy-revert 测。  
**方案 A 首波已落地**（2026-08-05）：`aiwiki.corpus` + `content ↛ memory`（见 `docs/plans/2026-08-05-corpus-shared-layer.md`）。仍开：facade、hub、`memory→content` 窄依赖全迁。

Commercial 三阻断与结构债正交，互不阻塞。
