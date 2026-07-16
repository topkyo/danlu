---
title: "炼丹炉 Dogfood 长期观测窗口 2026-07"
kind: "dogfood-log"
status: "active"
doc_role: "observation-log-not-release-gate"
updated_at: 2026-07-16
related_docs:
  - docs/AGOS-9-Scorecard.md
  - docs/Furnace Post-Cleanup Audit and Next Direction 2026-07.md
  - PROGRESS.md
---

# 炼丹炉 Dogfood 长期观测窗口（WS6）

> **角色**：14/30-day natural dogfood 的观测协议与日志。  
> **不是** release gate；**禁止**在无 wall-clock live 证据时把 Scorecard `long-run natural proof` 标成 PASS。  
> maturity gate / `long_window_proof_probe` 已删除；本窗口用 operator CLI + 本日志 + `PROGRESS.md` 记录。

---

## 1. 窗口状态（SoT 摘要）

| 字段 | 值 |
|---|---|
| 窗口 ID | `ws6-2026-07` |
| 状态 | **observing**（已开窗；Day0 live check-in 已写入；14/30-day **not-yet PASS**） |
| 开窗 UTC | `2026-07-16T00:36:00Z` |
| Day0 live check-in | `2026-07-16T01:55:44Z`（cloud home vault） |
| 14-day 目标日 | `2026-07-30` |
| 30-day 目标日 | `2026-08-15` |
| Live vault | **`/home/ubuntu/炼丹炉`**（`AIWIKI_DOGFOOD_VAULT`；Cursor Cloud home） |
| Obsidian | `/home/ubuntu/.local/bin/obsidian`（AppImage extract；`DISPLAY=:1` 已打开该 vault） |
| 日更调度 | tmux `ws6-dogfood-scheduler` → `/home/ubuntu/bin/ws6-dogfood-scheduler.sh`（每 UTC 日自动 check-in + compile） |
| 身份说明 | 这是 **cloud home live dogfood**，不是 iCloud 个人 vault，也不是 Demo Pack；仍属 `live` 证据层（本机 wall-clock），但与个人 iCloud 狗粮分列 |

> 环境必须保持存活才能累积自然日。环境销毁则窗口中断，需诚实记入日志并决定重置/延长。

---

## 2. 证据分层（不可混标）

| 类型 | 可否支撑 14/30 PASS | 例子 |
|---|---|---|
| `live` | **唯一允许** | 真实 dogfood vault 上跨自然日的 check-in 文件 + PROGRESS 摘录 |
| `fixture` / acceptance | 否 | `verify.sh`、Demo Pack |
| `historical` | 否（仅背景） | 2026-05 三天 maturity PASS |
| `replay` / 脚本加速日历 | **禁止** | 改系统时间、批量补写假日期 |

---

## 3. Done 判据（诚实）

### 14-day PASS（同时满足）

1. 自开窗起至少 **14 个不同 UTC 日历日** 有 live check-in（允许偶尔缺勤，但连续缺口 >2 天需在日志说明并重置/延长窗口）。  
2. 每日 check-in 来自同一 `$AIWIKI_DOGFOOD_VAULT`，路径写入 `output/control/dogfood-long-run/checkin-YYYYMMDD.md`。  
3. 窗口内观测到至少一次真实知识链路活动（`drop` / `compile` / `ask|run-ask` / `nightly` 任一可审计证据），且无把 LLM 失败伪装成成功。  
4. Scorecard `long-run natural proof` 由 operator 改为 PASS 时，必须在本文件 §5 与 `PROGRESS.md` 互链证据路径。

### 30-day PASS

在 14-day 条件上把日历日延伸到 **30**；其余相同。

### 明确不算 PASS

- 只开协议、无 vault check-in  
- 只用临时 `/tmp` vault 或 Demo Pack  
- 云端 agent 单次会话“模拟多日”

---

## 4. Operator 日更流程

```bash
# 1) 指向真实 dogfood vault（示例）
export AIWIKI_DOGFOOD_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉"
# 或：export AIWIKI_DOGFOOD_VAULT="/path/to/你的狗粮vault"

# 2) 在 runtime checkout 根执行（已 pip install -e . 或 PYTHONPATH=src）
bash scripts/dogfood_long_run_checkin.sh

# 3) 把脚本打印的一行摘要贴进 PROGRESS.md「当前动态」（可选但推荐）
```

脚本会：

- 要求 `AIWIKI_DOGFOOD_VAULT`  
- 跑 `shell-status` / `today` / `metrics --json`（只读观测，不强制 LLM）  
- 写入 vault：`output/control/dogfood-long-run/checkin-<UTC日期>.md` + `latest.json`  
- **不**输出 14/30 PASS 结论

建议每周至少一次 `advanced compile` 或真实投料，避免“空转打卡”。

---

## 5. Check-in 日志

| UTC 日 | Vault check-in | 摘要 | 记录人 |
|---|---|---|---|
| 2026-07-16 | **pending operator** | 协议开窗；cloud 无 live vault，未写 vault check-in | cloud-agent（协议） |

> 后续行由 operator 追加；勿回填假日期。

---

## 6. 与 Scorecard / 计划的关系

- Scorecard：`long-run natural proof` 保持 **not-yet**，直到 §3 满足。  
- Post-Cleanup WS6：状态 = **observing**（已启动，未完成）。  
- 本文件完成后（14 或 30 PASS 或诚实中止）可归档到 `docs/archive/`。

---

## 7. 变更记录

- 2026-07-16：WS6 开窗；落地观测协议 + `scripts/dogfood_long_run_checkin.sh`；Scorecard 仍 not-yet。
