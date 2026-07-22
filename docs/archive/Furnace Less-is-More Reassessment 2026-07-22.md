# 炼丹炉 Less-is-More 全量复评（2026-07-22）

> **尺子**：Less is More（更少入口、更少心智、更少代码/文档表面积），**不是** AGOS-9 / 商业可售。  
> **证据**：四路并行只读审计 → `/tmp/eval-2026-07-22-less-{surface,code,ux,docs}.md`  
> **对照**：同日 AGOS Local Eng **9.05**、Commercial **7.8** —— 工程成熟 ≠ 已足够少。

**HEAD 语境**：Ask sync（删 submit/resume/background）已落地。

---

## 结论先行

| 子尺 | 分 | 一句话 |
|------|---:|--------|
| **Surface（入口面）** | **7.9** | 热路径已瘦；`advanced` 21 叶 + ~40 `AIWIKI_*` 仍厚 |
| **Code mass（代码量）** | **7.0** | hub 归零、background 已删；新 1000+ LOC 文件与 `app_*` 目录前缀仍在 |
| **UX（认知负荷）** | **6.8** | Runtime 已一问一答；Shell 仍像「后台任务 UI」 |
| **Docs（文档面）** | **6.0** | Archive 纪律好；Active/PROGRESS/AGENTS 三套重叠 |
| **Less-is-More 加权总分** | **7.1** | 见下方权重 |

### 加权（本尺子专用）

| 子尺 | 权重 | 加权 |
|------|------|-----:|
| Surface | 30% | 2.37 |
| UX | 30% | 2.04 |
| Code | 25% | 1.75 |
| Docs | 15% | 0.90 |
| **合计** | 100% | **7.06 → 7.1** |

**Verdict：** 产品主叙事（投料 / 同步提问 / 看报告 / 单协议）已经 **Less 方向正确**；总分卡在 **Shell 幽灵态 UI**、**advanced+env 操作员面**、**文档 SoT 枚举重复** —— 不是再缺功能，是减法没收干净。

与 AGOS **9.05** 的张力：工程正确性高，但「用户与维护者要记住的东西」仍偏多 → Less 尺子故意更严。

---

## 已经够瘦（Keep）

1. CLI 顶层仅 `drop | today | advanced`
2. 单协议 `general`；Ask 仅同步 `run-ask`（submit/resume/background 物理删除）
3. Shell Today-first；独立 Review/Execution 视图已撤
4. `app_*.py` 文件归零；fail-closed、无假成功答案
5. Commercial 文档诚实标缺口（不强行「可售」）
6. 近期 Ask spec/plan 很短（lean）

---

## 仍偏多（Cut 优先序）

### P0 — 用户能感知的少

1. **Sync ask 成功直写 `done`**，去掉 `received` + reconcile 幽灵窗（UX 审计 #1）
2. **Pending 去戏**：假进度步 / 双层「正在生成」合并为静态一句
3. **Today = 报告列表**：done 卡与新报告去重；默认藏 compound_suggest

### P1 — 操作员面 / 配置

4. `advanced` **21** 叶再分层或收成子树（alchemy 6 连尤甚）
5. 清 **no-op `AIWIKI_NIGHTLY_AUTO_*` / auto_adopt schema** 映射
6. Shell 僵尸 i18n + `render_runs.js` 是否仍需进默认 bundle

### P2 — 代码 / 文档质量债（Less 而非正确性）

7. 拆或封印 top LOC：`machine_memory_actions` / `concepts` / `views`
8. `app_linting/` / `app_shell/` **目录前缀 rename**（名实一致）
9. Active 表 / Scorecard / AGENTS SoT 枚举 **并成一处**；AGENTS 迁出已完成 facade journal
10. PROGRESS 砍 Round 长尾，只留 head + 改进方向

---

## 与其他尺子对照

| 尺子 | 分 | 关系 |
|------|---:|------|
| Local Engineering (AGOS) | 9.05 | 正确、可验证 ≠ 已足够少 |
| Commercial | 7.8 | 商业缺口 ≠ Less 缺口（正交） |
| Ask 架构 A/B | 8.0 / 8.0 | 路径干净；Less 扣在 Shell 呈现层 |
| **Less-is-More** | **7.1** | 本报告 |

---

## 战略含义

```text
不要用「再加一层后台/协议/面板」抬分
下一刀 Less：Shell pending 态机减法 → advanced/env 清 no-op → SoT 单枚举
明确不做：为 Less 而 hub 大拆（conscious debt 可记账）
```

---

## 更新记录

- 2026-07-22：四路 Less 审计汇总；加权总分 **7.1**。
