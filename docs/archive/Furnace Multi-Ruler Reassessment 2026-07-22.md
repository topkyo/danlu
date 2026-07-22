# 炼丹炉多尺子全量复评（2026-07-22）

> **性质**：Ask sync-chat 架构修正后的只读复评报告（史料 + 评分快照）。  
> **非**下一波执行计划 SoT（仍以 `docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md` 为准）。  
> **证据源**：四路并行审计 + 本机 `verify` / 计数实测。明细：`/tmp/eval-2026-07-22-{local-eng,live-dogfood,commercial,ask-arch}.md`。

**HEAD**：`efd6de2`（含 Ask sync + follow-ups + 软提示 timer 清理）

---

## 结论先行（四套尺子）

| 尺子 | 分 | 可否对外宣称 | Δ vs 先前 |
|------|---:|---|---|
| **Local Engineering Gate**（AGOS-9 八维加权） | **9.05** | ✅ 可宣称 engineering 就绪（≠ live 9 / ≠ 商业可售） | 自 07-19 ~8.4 回升；贴近 07-18 **9.07** |
| **Live Dogfood 维** | **7.0** | ❌ Gate 仍 **not-yet**（不得宣称 live PASS） | +0.5 vs Scorecard 旧 6.5 |
| **Live-gate 估算加权 overall** | **~8.3** | ❌ 不得宣称 AgentOS 9.0 **live** | +0.1 vs ~8.2 |
| **Commercial Go-Live** | **7.8** | ❌ 未达诚实可售门槛 ≥8.0 | 持平（Ask sync **非** commercial unlock） |
| **Ask 架构质量 A** | **8.0** | —（子尺） | 新评 |
| **Ask+Shell 可维护性 B** | **8.0** | —（子尺） | 新评 |

**一句话**：工程门禁回到 **~9.05**；Ask 路径显著变干净；dogfood 卫生改善但仍缺连续成熟窗口；商业分卡在 **EULA / PyPI / Demo 媒体**，与本轮架构无关。

---

## 1. Local Engineering（八维）

| 维度 | 权重 | 分 | 加权 | 要点 |
|------|------|---:|-----:|------|
| Dogfood / fixture & historical | 20% | 8.9 | 1.780 | acceptance 17 + AOS-C8 historical；不伪造 live |
| Product Shell | 12% | 9.3 | 1.116 | Jest **179**；同步 ask + 单飞 + 软提示 |
| Runtime correctness | 15% | 9.4 | 1.410 | fail-closed LLM；无 submit/resume 竞态面 |
| Planner / signal | 10% | 8.7 | 0.870 | 本轮未动 |
| LLM reliability | 12% | 9.0 | 1.080 | llm-integration **76** |
| Governance | 13% | 9.1 | 1.183 | 无假成功 fallback |
| Maintainability | 8% | 9.0 | 0.720 | `app_*.py`=0；净删 background 路径 |
| Docs SoT | 10% | 8.9 | 0.890 | docs_consistency PASS；本报告刷新 Scorecard |
| **合计** | 100% | — | **9.05** | |

**实测门禁**：acceptance **17** / llm-integration **76** / Jest **179** / `app_*.py` **0** / src 无 `run-ask-submit|resume` / docs_consistency exit 0 / `verify.sh all` PASS。

---

## 2. Live Dogfood

| 项 | 状态 |
|---|---|
| `background_status: submitted\|running` | **0** |
| `background-jobs/` 活动态 | **空** |
| Jul 21–22 `run-ask` | 全部 `llm-success`（含今日探针 25s / 43s） |
| 3-day natural maturity | **not-yet**（仅 2/3 日有 ask） |
| 14-day | **partial**（Jul 17–18 失败爆发拖尾） |
| Plugin `main.js` vs repo | **SHA 一致** |

**Live 维 7.0**：卫生与同步路径改善；连续 3 日 ask 成功可冲 ~7.5–8.0。

---

## 3. Commercial Go-Live（WS1–WS6）

| WS | 状态 |
|----|------|
| WS1 邮箱/询价/EULA | partial — EULA **未法律签收** |
| WS2 分发 | partial — **无 PyPI** |
| WS3 Demo 媒体 | partial — **零截图/录屏** |
| WS4 SoT | partial → 本轮刷新 Scorecard |
| WS5 验证 | **done** |
| WS6 Live 窗口 | **open** |

**商业 7.8**：Ask sync 对商业分影响 ≈0；阻断仍是法律/分发/媒体/长期 dogfood。

---

## 4. Ask 架构子尺

| 子尺 | 分 | 说明 |
|------|---:|------|
| A 执行架构 | 8.0 | 整段删除 background；单飞 + `excludePendingId`；fail-loud |
| B 可维护性 | 8.0 | 净删 ~数百行；Jest 回归；无 poller 复活 |

**残留风险（排序）**：长报告同步阻塞 UX（中高）→ Shell/CLI dogfood 覆盖缺口（中）→ `background_status=degraded` 读侧死分支记账债（低）。

---

## 5. 战略含义

```text
Local Eng ~9.05  ──可宣称──► engineering 就绪
        │
        ├──✗──► 不得写成「商业 9 分」或「live AgentOS 9」
        │
        ▼
下一刀仍是 Commercial Go-Live 残留（EULA 签收 / PyPI / Demo 媒体）
        + Live 连续 ask 窗口（WS6）
        │
明确不做：恢复 background job / hub 大拆 / SaaS
```

---

## 6. 更新记录

- 2026-07-22：四路并行审计 + 本报告；Scorecard 同步刷新计数与 Local Eng **9.05** / Live 维 **7.0**。
